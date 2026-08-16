"""Tests for the parser's addressing-convention module.

The 2026-05-30 (b)-refined convention is the single source of truth for
classifying the `to` field of message events into one of five target
kinds. Each test below corresponds to a commitment in the
data-side / writer-side exchange recorded in memory/decisions.md
2026-05-30; if the convention ever changes, the tests change first.
"""

from __future__ import annotations

from agent_comms.parser.addressing import (
    TARGET_KIND_ALIAS, TARGET_KIND_BROADCAST, TARGET_KIND_CANONICAL,
    TARGET_KIND_ROLE, TARGET_KIND_UNKNOWN,
    normalise_target,
)


# --- canonical agent IDs ----------------------------------------------------

def test_canonical_agent_id_unchanged():
    """The runner's canonical spelling is recognised as canonical."""
    node, kind = normalise_target("agent-1")
    assert node == "agent-1"
    assert kind == TARGET_KIND_CANONICAL


def test_canonical_agent_with_two_digits():
    node, kind = normalise_target("agent-12")
    assert node == "agent-12"
    assert kind == TARGET_KIND_CANONICAL


# --- alias forms ------------------------------------------------------------

def test_alias_without_separator_normalises_to_canonical():
    """`agent1` is an alias of `agent-1`, target_kind=alias."""
    node, kind = normalise_target("agent1")
    assert node == "agent-1"
    assert kind == TARGET_KIND_ALIAS


def test_alias_with_underscore_separator():
    """`Agent_2` is a case-and-separator alias of `agent-2`."""
    node, kind = normalise_target("Agent_2")
    assert node == "agent-2"
    assert kind == TARGET_KIND_ALIAS


def test_alias_with_uppercase_canonical_form():
    """`AGENT-3` differs from the canonical only in case; alias."""
    node, kind = normalise_target("AGENT-3")
    assert node == "agent-3"
    assert kind == TARGET_KIND_ALIAS


def test_alias_with_leading_zero_strips_to_canonical():
    """Defensive case: `agent-01` -> `agent-1`. Leading zeros stripped."""
    node, kind = normalise_target("agent-01")
    assert node == "agent-1"
    assert kind == TARGET_KIND_ALIAS


def test_alias_with_space_separator():
    """`agent 4` (space) is an alias."""
    node, kind = normalise_target("agent 4")
    assert node == "agent-4"
    assert kind == TARGET_KIND_ALIAS


# --- broadcast tokens -------------------------------------------------------

def test_broadcast_all_canonicalises_to_star():
    node, kind = normalise_target("all")
    assert node == "*"
    assert kind == TARGET_KIND_BROADCAST


def test_broadcast_token_set_complete():
    """Every token in the locked broadcast set classifies correctly."""
    for token in ("all", "broadcast", "*", "everyone", "team"):
        node, kind = normalise_target(token)
        assert kind == TARGET_KIND_BROADCAST, token
        assert node == "*"


def test_broadcast_tokens_are_case_insensitive_mixed_case():
    """Lock test for the case-insensitivity rule on broadcasts."""
    for token in ("ALL", "Broadcast", "*"):
        node, kind = normalise_target(token)
        assert kind == TARGET_KIND_BROADCAST, token


# --- role classification ----------------------------------------------------

ROLES = ("parse", "validate", "aggregate", "format_output")


def test_role_target_matches_exact_role_name():
    """`to=parse` with parse in role_names -> role."""
    node, kind = normalise_target("parse", role_names=ROLES)
    assert node == "parse"
    assert kind == TARGET_KIND_ROLE


def test_role_target_case_insensitive_mixed_case():
    """Lock test for case-insensitive role matching."""
    for spelled in ("Parse", "AGGREGATE", "validate"):
        node, kind = normalise_target(spelled, role_names=ROLES)
        assert kind == TARGET_KIND_ROLE
        # The normalised node identity uses the spelling in role_names.
        assert node.lower() == spelled.lower()


def test_role_target_does_not_partial_match():
    """`format` is not the role `format_output` (strict equality)."""
    node, kind = normalise_target("format", role_names=ROLES)
    assert kind == TARGET_KIND_UNKNOWN
    assert node == "format"


def test_role_with_no_role_names_falls_through_to_unknown():
    """Family 1 ships role_names=[], so role-shaped names are unknown."""
    node, kind = normalise_target("parse", role_names=())
    assert kind == TARGET_KIND_UNKNOWN


# --- unknown bucket ---------------------------------------------------------

def test_unknown_for_arbitrary_string():
    """A made-up token with no role registration is unknown."""
    node, kind = normalise_target("orchestrator")
    assert kind == TARGET_KIND_UNKNOWN
    assert node == "orchestrator"


def test_unknown_for_pipeline_when_excluded_from_roles():
    """Family 2 excludes pipeline from role_names; to=pipeline is unknown."""
    node, kind = normalise_target("pipeline", role_names=ROLES)
    assert kind == TARGET_KIND_UNKNOWN
    assert node == "pipeline"


# --- empty / whitespace input ----------------------------------------------

def test_empty_to_returns_empty_strings():
    """Caller treats empty result as `drop this event`."""
    node, kind = normalise_target("")
    assert node == ""
    assert kind == ""


def test_none_to_returns_empty_strings():
    node, kind = normalise_target(None)
    assert node == ""
    assert kind == ""


def test_whitespace_only_to_returns_empty_strings():
    """Whitespace-only `to` is treated as empty after stripping."""
    node, kind = normalise_target("   ")
    assert node == ""
    assert kind == ""


# --- realistic addressing cases pulled from real data ----------------------

def test_real_data_short_alias_a1():
    """`a1` appeared in Family 1 master CSV; not a recognised alias."""
    # The regex requires the literal substring "agent"; "a1" alone is unknown.
    node, kind = normalise_target("a1")
    assert kind == TARGET_KIND_UNKNOWN


def test_real_data_underscore_alias_agent_2():
    """`agent_2` appeared in the Family 1 broader pilot; alias."""
    node, kind = normalise_target("agent_2")
    assert node == "agent-2"
    assert kind == TARGET_KIND_ALIAS


def test_real_data_step_role_aggregate():
    """`aggregate` appeared in Family 2 pilot; role when in role_names."""
    node, kind = normalise_target("aggregate", role_names=ROLES)
    assert kind == TARGET_KIND_ROLE


def test_real_data_filter_not_in_role_set():
    """`filter` appeared in Family 2 pilot but is not a step in
    summarise_transactions; unknown."""
    node, kind = normalise_target("filter", role_names=ROLES)
    assert kind == TARGET_KIND_UNKNOWN
