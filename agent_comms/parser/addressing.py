"""Addressing convention for the `to` field of message events.

The message protocol log records every inter-agent message as one event
with a sender (`from`) and a recipient (`to`). The recipient field is
free-form text written by the agent; in practice it shows up in five
shapes:

  - canonical: the runner-assigned `agent-N` identifier the runner used
    in the per-agent prompts.
  - alias: a variant of the canonical form that resolves to a single
    canonical agent (no dash, alternative separator, mixed case, or a
    leading zero on the index).
  - broadcast: a fixed token addressing the whole team rather than one
    agent. Five tokens are recognised: `all`, `broadcast`, `*`,
    `everyone`, `team`. Case-insensitive.
  - role: an addressable role name surfaced in the prompts as a per-step
    deliverable filename (parse, validate, aggregate, format_output,
    and analogues for the other Family 2 tasks). The set of role names
    is per-run and is supplied to the parser through `run_record.role_names`
    by the runner; see `agent_comms.task_generator.library.role_names_for`.
    Family 1 ships with an empty role-name list because Family 1 prompts
    do not surface component labels as addressable names. Family 2 ships
    with the instance's step names, excluding the shared `pipeline` slot
    (which is by design unassigned at run time and addressing it is
    ambiguous; it surfaces as TARGET_KIND_UNKNOWN as a separate signal).
  - unknown: anything else (typos, made-up names, the `pipeline` slot,
    obsolete tokens). The graph node identity is kept as the literal
    string the agent wrote.

The recipient is classified by `normalise_target(raw_to, role_names)`,
which returns (canonical_node_id, target_kind). Empty input returns the
empty string for both; the caller treats this as "drop the edge", which
preserves the historical "empty `to` means do not record" behaviour.

This module is the single source of truth for the classification rules.
Tests are in `tests/test_parser_addressing.py`.
"""

from __future__ import annotations

import re

TARGET_KIND_CANONICAL = "canonical"
TARGET_KIND_ALIAS = "alias"
TARGET_KIND_BROADCAST = "broadcast"
TARGET_KIND_ROLE = "role"
TARGET_KIND_UNKNOWN = "unknown"
TARGET_KINDS = (
    TARGET_KIND_CANONICAL,
    TARGET_KIND_ALIAS,
    TARGET_KIND_BROADCAST,
    TARGET_KIND_ROLE,
    TARGET_KIND_UNKNOWN,
)

# Canonical and alias forms of agent identifiers. The regex matches:
#   agent-1, agent-12        (canonical)
#   agent_1, agent 1, agent1 (alias variants)
#   AGENT-1, Agent_2         (alias via case)
#   agent-01                 (alias via leading zero; defensive case;
#                             the runner never produces leading zeros)
#
# After matching, the canonical id is reconstructed as `agent-N` where
# N is the integer index with any leading zeros stripped. A string that
# matched the regex but whose verbatim form is not exactly `agent-N`
# (the canonical spelling, lower-cased, dash separator, no leading
# zero) is classified as an alias rather than canonical.
_CANONICAL_AGENT_RE = re.compile(r"^agent[-_ ]?(\d+)$", re.IGNORECASE)

# Broadcast tokens. Case-insensitive comparison. The graph node identity
# for a broadcast is the literal `*` (one synthetic node per run), so
# that all broadcasts collapse to one edge endpoint regardless of which
# token the agent used.
_BROADCAST_TOKENS = frozenset({"all", "broadcast", "*", "everyone", "team"})
_BROADCAST_NODE = "*"


def normalise_target(raw_to, role_names=()):
    """Classify a message's `to` field and return (node_id, target_kind).

    raw_to: the string in the `to` field of the message log event.
    role_names: iterable of role-name strings for this run, as
        supplied by `agent_comms.task_generator.library.role_names_for`.
        Pass an empty iterable for runs that have no per-step roles
        (every Family 1 run).

    The returned node_id is the string the parser should use as the
    edge's target. For canonical and alias targets it is the
    canonical `agent-N` form. For broadcasts it is `*`. For roles it
    is the role name as it appears in `role_names` (so a `Parse` in
    the message log normalises to whatever case the role_names list
    uses). For unknown targets it is the original string stripped of
    surrounding whitespace.

    The returned target_kind is one of the TARGET_KIND_* constants.
    An empty raw_to returns ("", "") and the caller drops the event.
    """
    if raw_to is None:
        return "", ""
    stripped = raw_to.strip()
    if not stripped:
        return "", ""

    lower = stripped.lower()

    # Broadcasts first: they take precedence over any other pattern.
    if lower in _BROADCAST_TOKENS:
        return _BROADCAST_NODE, TARGET_KIND_BROADCAST

    # Canonical or alias.
    m = _CANONICAL_AGENT_RE.match(stripped)
    if m:
        # Strip leading zeros via int conversion.
        canonical = f"agent-{int(m.group(1))}"
        kind = (TARGET_KIND_CANONICAL if stripped == canonical
                else TARGET_KIND_ALIAS)
        return canonical, kind

    # Role classification (case-insensitive). Preserve the spelling
    # supplied by the runner so the graph node identity matches the
    # role-names registry exactly.
    if role_names:
        for role in role_names:
            if role.lower() == lower:
                return role, TARGET_KIND_ROLE

    return stripped, TARGET_KIND_UNKNOWN
