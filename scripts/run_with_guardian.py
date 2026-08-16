#!/usr/bin/env python3
"""Wall-clock-bounded launcher wrapper.

Spawns an inner script in its own process group, watches the script's
combined log for output activity, and if the log goes idle longer than
the per-run threshold, kills the whole process group with SIGKILL.

The motivating problem: the experiment runner's per-agent wait
(`agent_comms/runner/launch.py::ClaudeCodeLauncher._run_agents`) calls
`subprocess.wait(timeout=900)` per agent, which is supposed to bound
each run to about 900 seconds. On 2026-05-30 a run ran 4046 seconds;
on 2026-05-31 another run was still running at 1529 seconds when the
external watchdog tripped, also far past the 900-second per-agent
budget. The launcher fix in commit `1c2b4d4` (monotonic clock + process
group kill + bounded post-kill wait) addressed the most obvious holes
but evidently the per-agent wait can still hang in some shapes
(observed: a 4-agent solo run where some agents produced no output at
all, and one hit a Claude API socket error and lingered).

The guardian sidesteps the launcher's internal timeout entirely: it
applies a wall-clock-bounded watchdog at the OS level, on top of the
inner script. The inner script runs in its own session (Popen with
start_new_session=True), so killing the group with os.killpg reaches
every descendant including the claude subprocesses and their MCP
children.

The guardian's signal: the inner script writes one progress header line
("[N/M] <run-id>") at the start of each run and a status= line at the
end. Between those two writes nothing else lands in the combined log
(claude itself writes to per-agent logs inside the run directory).
Therefore the combined log's mtime advancing means a run completed
and the next one started. A run that takes longer than per-run-timeout
seconds without finishing leaves the log idle for that duration; the
guardian detects it and kills the group.

Usage:

    .venv/bin/python scripts/run_with_guardian.py \\
        --log data/family-2-full-run.log \\
        --per-run-timeout 1000 \\
        -- .venv/bin/python scripts/run_family2_full.py --max-runs 50

The `--` separator passes everything after it as the inner command.
The wrapper does not strip ANTHROPIC_API_KEY itself; the inner
launcher does that via subscription_env().

Exit codes:
    0: inner script exited normally with code 0.
    N: inner script exited with code N (passes through).
    2: guardian killed the inner script on per-run timeout.
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time


# How often to poll the log for size changes. 30 s is a good balance:
# short enough to catch a hang within ~1.5 minutes of the threshold,
# long enough to add negligible overhead.
DEFAULT_POLL_INTERVAL_S = 30

# Default per-run wall-clock bound. Tuned to be just past the launcher's
# internal 900 s timeout plus a kill-reap buffer (commit 1c2b4d4 added a
# 10 s buffer per agent). 1000 s catches hangs that exceed the
# launcher's expected envelope without firing on legitimate long runs
# (the longest non-error wall time observed in Family 1 was 829 s).
DEFAULT_PER_RUN_TIMEOUT_S = 1000

# When the guardian fires, send SIGTERM first to give the inner script
# a chance to print a clean message, then SIGKILL after this grace
# period. The SIGKILL goes to the whole process group, so all claude
# subprocesses die too.
KILL_GRACE_S = 5


def main():
    parser = argparse.ArgumentParser(
        description="Wall-clock-bounded launcher wrapper.")
    parser.add_argument(
        "--log", required=True,
        help="path to the combined log file the inner script writes "
             "to via `tee`. The guardian polls this file's size.")
    parser.add_argument(
        "--per-run-timeout", type=int,
        default=DEFAULT_PER_RUN_TIMEOUT_S,
        help=f"wall-clock bound for any single inner-script run, in "
             f"seconds (default {DEFAULT_PER_RUN_TIMEOUT_S}). When the "
             f"log goes idle longer than this, the guardian kills the "
             f"inner script and its process group.")
    parser.add_argument(
        "--poll-interval", type=int,
        default=DEFAULT_POLL_INTERVAL_S,
        help=f"how often (seconds) to check the log (default "
             f"{DEFAULT_POLL_INTERVAL_S}).")
    parser.add_argument(
        "command", nargs=argparse.REMAINDER,
        help="the inner command, after `--`.")
    args = parser.parse_args()

    if not args.command or args.command[0] == "--":
        # argparse REMAINDER includes the `--` if it was used. Drop it.
        cmd = args.command[1:] if args.command and args.command[0] == "--" else args.command
    else:
        cmd = args.command
    if not cmd:
        parser.error("no inner command supplied; usage: "
                     "run_with_guardian.py --log L -- python script.py ...")

    log_fh = open(args.log, "ab")
    log_fh.write(
        f"\n=== guardian: starting at "
        f"{time.strftime('%Y-%m-%d %H:%M:%S')}, "
        f"per-run timeout {args.per_run_timeout}s ===\n".encode())
    log_fh.flush()

    process = subprocess.Popen(
        cmd, stdout=log_fh, stderr=subprocess.STDOUT,
        start_new_session=True)
    pgid = os.getpgid(process.pid)
    print(
        f"guardian: spawned PID {process.pid} PGID {pgid}; "
        f"watching {args.log} with per-run timeout "
        f"{args.per_run_timeout}s", flush=True)

    last_size = -1
    last_change = time.monotonic()
    exit_code = None
    try:
        while True:
            rc = process.poll()
            if rc is not None:
                exit_code = rc
                break
            time.sleep(args.poll_interval)
            try:
                size = os.path.getsize(args.log)
            except OSError:
                continue
            if size != last_size:
                last_size = size
                last_change = time.monotonic()
                continue
            idle = time.monotonic() - last_change
            if idle > args.per_run_timeout:
                msg = (f"\nGUARDIAN-KILLING: log idle {idle:.0f}s "
                       f"> {args.per_run_timeout}s; killing PGID "
                       f"{pgid}\n")
                print(msg, flush=True)
                log_fh.write(msg.encode())
                log_fh.flush()
                try:
                    _kill_group(pgid)
                except Exception as exc:
                    print(f"guardian: kill helper raised {exc!r}; "
                          f"continuing", flush=True)
                exit_code = 2
                break
    finally:
        if exit_code is None:
            # We fell out of the loop without setting exit_code; do
            # a best-effort wait and capture.
            try:
                exit_code = process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                _kill_group(pgid)
                exit_code = 2
        log_fh.close()

    sys.exit(exit_code)


def _kill_group(pgid: int) -> None:
    """SIGTERM then SIGKILL the process group, bounded by KILL_GRACE_S.

    Tolerant of every signal-related error path: ProcessLookupError
    means the group is already gone (good); PermissionError can occur
    when the group has reparented children we cannot signal directly
    (we still try SIGKILL anyway; the kernel will refuse and we
    return). Any failure during the check-alive poll is treated as
    "uncertain alive, proceed to SIGKILL". The guardian's own exit
    code is set by the caller; this helper must not raise.
    """
    try:
        os.killpg(pgid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        pass
    deadline = time.monotonic() + KILL_GRACE_S
    while time.monotonic() < deadline:
        try:
            os.killpg(pgid, 0)  # check if any process in group is alive
        except ProcessLookupError:
            return  # all dead
        except PermissionError:
            break  # cannot signal; treat as uncertain, proceed to SIGKILL
        time.sleep(0.5)
    try:
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        return


if __name__ == "__main__":
    main()
