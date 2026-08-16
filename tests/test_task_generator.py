"""Tests for the task generator (infrastructure component 3).

These cover the distribution algorithm (clean, overlapping, conflicting) and
the generation of a run-ready instance directory from the task library.

Run with: pytest tests/test_task_generator.py
"""

import json
import os

import pytest

from agent_comms.task_generator import (
    CLEAN, CONFLICTING, OVERLAPPING, assign, clean_partition,
    generate_instance, get_task,
)


# --- task library ------------------------------------------------------------

def test_library_has_process_orders():
    task = get_task("process_orders")
    assert task.n_components == 4
    assert task.function_name == "process_orders"


def test_unknown_task_raises():
    with pytest.raises(KeyError):
        get_task("does_not_exist")


def test_validation_component_has_variant():
    task = get_task("process_orders")
    assert task.variant_components() == [1]
    assert "lenient" in task.components[1].variants


# --- clean partition ---------------------------------------------------------

def _flatten(partition):
    return sorted(i for agent in partition for i in agent)


def test_clean_partition_four_agents_four_components():
    partition = clean_partition(4, 4)
    assert [len(a) for a in partition] == [1, 1, 1, 1]
    assert _flatten(partition) == [0, 1, 2, 3]


def test_clean_partition_two_agents_four_components():
    partition = clean_partition(4, 2)
    assert [len(a) for a in partition] == [2, 2]
    assert _flatten(partition) == [0, 1, 2, 3]


def test_clean_partition_one_agent_holds_all():
    partition = clean_partition(4, 1)
    assert partition == [[0, 1, 2, 3]]


def test_clean_partition_more_agents_than_components_leaves_some_empty():
    partition = clean_partition(4, 8)
    assert [len(a) for a in partition] == [1, 1, 1, 1, 0, 0, 0, 0]
    assert _flatten(partition) == [0, 1, 2, 3]


# --- assignment patterns -----------------------------------------------------

def _holder_count(holdings, component_index):
    return sum(
        1 for agent in holdings
        for h in agent if h.component_index == component_index)


def test_clean_assignment_each_component_held_once():
    holdings = assign(4, 4, CLEAN)
    for index in range(4):
        assert _holder_count(holdings, index) == 1


def test_overlapping_assignment_duplicates_chosen_components():
    holdings = assign(4, 4, OVERLAPPING, overlap_indices=[1, 2])
    assert _holder_count(holdings, 1) == 2
    assert _holder_count(holdings, 2) == 2
    assert _holder_count(holdings, 0) == 1
    assert _holder_count(holdings, 3) == 1


def test_conflicting_assignment_second_holder_has_variant():
    holdings = assign(4, 4, CONFLICTING,
                      conflict_specs=[(1, "lenient")])
    variants = [h.variant for agent in holdings for h in agent
                if h.component_index == 1]
    assert sorted(v or "canonical" for v in variants) == \
        ["canonical", "lenient"]


def test_overlapping_with_one_agent_raises():
    with pytest.raises(ValueError):
        assign(4, 1, OVERLAPPING, overlap_indices=[1])


def test_unknown_pattern_raises():
    with pytest.raises(ValueError):
        assign(4, 4, "scrambled")


# --- instance generation -----------------------------------------------------

def test_generate_clean_instance_writes_manifest_and_prompts(tmp_path):
    task = get_task("process_orders")
    out = tmp_path / "inst"
    manifest = generate_instance(task, 4, CLEAN, str(out))
    assert os.path.exists(out / "instance.json")
    for i in range(1, 5):
        assert os.path.exists(out / "prompts" / f"agent-{i}.txt")
    assert manifest["agent_count"] == 4
    assert manifest["pattern"] == "clean"
    assert manifest["n_components"] == 4
    assert manifest["verifier_path"] == "tasks/family-1/instance-1/verifier.py"


def test_generate_clean_instance_covers_every_component(tmp_path):
    task = get_task("process_orders")
    manifest = generate_instance(task, 4, CLEAN, str(tmp_path / "inst"))
    held = [c["index"] for agent in manifest["agents"]
            for c in agent["components"]]
    assert sorted(held) == [0, 1, 2, 3]


def test_generated_prompt_names_function_and_solution_path(tmp_path):
    task = get_task("process_orders")
    out = tmp_path / "inst"
    generate_instance(task, 4, CLEAN, str(out))
    prompt = (out / "prompts" / "agent-1.txt").read_text(encoding="utf-8")
    assert "process_orders" in prompt
    assert "solution.py" in prompt
    # the prompt must not assign a role
    assert "role" not in prompt.lower()


def test_generate_overlapping_instance_duplicates_two_components(tmp_path):
    task = get_task("process_orders")
    manifest = generate_instance(task, 4, OVERLAPPING, str(tmp_path / "inst"))
    held = [c["index"] for agent in manifest["agents"]
            for c in agent["components"]]
    # four components plus two duplicated: six holdings in total
    assert len(held) == 6


def test_generate_conflicting_instance_places_variant_in_a_prompt(tmp_path):
    task = get_task("process_orders")
    out = tmp_path / "inst"
    manifest = generate_instance(task, 4, CONFLICTING, str(out))
    variants = [c["variant"] for agent in manifest["agents"]
                for c in agent["components"] if c["index"] == 1]
    assert "lenient" in variants
    assert None in variants
    # the lenient validation text admits quantity equal to 0
    prompts = "\n".join(
        (out / "prompts" / f"agent-{i}.txt").read_text(encoding="utf-8")
        for i in range(1, 5))
    assert "greater than or equal to 0" in prompts
    assert "greater than 0" in prompts


def test_instance_json_is_valid_json(tmp_path):
    task = get_task("process_orders")
    out = tmp_path / "inst"
    generate_instance(task, 2, CLEAN, str(out))
    with open(out / "instance.json", encoding="utf-8") as fh:
        loaded = json.load(fh)
    assert loaded["agent_count"] == 2
    assert len(loaded["agents"]) == 2


# --- Family 2 task library --------------------------------------------------

def test_library_has_summarise_transactions():
    task = get_task("summarise_transactions")
    assert task.family == "family-2"
    assert task.function_name == "summarise_transactions"
    assert task.solution_path == "pipeline.py"
    assert task.n_components == 4


def test_library_has_compute_invoices():
    task = get_task("compute_invoices")
    assert task.family == "family-2"
    assert task.n_components == 8


def test_library_has_summarise_transactions_v2():
    task = get_task("summarise_transactions_v2")
    assert task.family == "family-2"
    assert task.n_components == 4
    # Step 1's spec must define CATEGORY_ORDER; step 4's must reference it.
    assert "CATEGORY_ORDER" in task.components[0].text
    assert "CATEGORY_ORDER" in task.components[3].text


def test_summarise_transactions_has_validate_strict_variant():
    """Mirrors the Family 1 variant test; strict validate is B2 conflict."""
    task = get_task("summarise_transactions")
    assert task.variant_components() == [1]  # validate is component 1
    assert "strict" in task.components[1].variants


def test_family_2_deliverable_paths_include_pipeline_last():
    task = get_task("summarise_transactions")
    paths = task.deliverable_paths()
    assert paths == ["parse.py", "validate.py", "aggregate.py",
                     "format_output.py", "pipeline.py"]


def test_family_2_components_carry_deliverable_paths():
    task = get_task("compute_invoices")
    expected = ["parse.py", "validate.py", "resolve_customer.py",
                "resolve_product.py", "compute_line_totals.py",
                "apply_discount.py", "compute_tax.py", "format_invoices.py"]
    assert [c.deliverable_path for c in task.components] == expected


# --- Family 2 prompt rendering ----------------------------------------------

def test_family_2_prompt_uses_chain_framing(tmp_path):
    task = get_task("summarise_transactions")
    out = tmp_path / "inst"
    generate_instance(task, 4, CLEAN, str(out))
    prompt = (out / "prompts" / "agent-1.txt").read_text()
    # Family 2 framing: sequential, chain-of-step functions, pipeline.py
    assert "sequential software task" in prompt
    assert "chain of step functions" in prompt
    assert "pipeline.py" in prompt
    # The team-level signature is rendered verbatim
    assert "pipeline.summarise_transactions(records: list[dict])" in prompt
    # The agent's specific deliverable is named
    assert "`parse.py`" in prompt
    # Family 2 framing must NOT use the Family 1 wording
    assert "implement a single Python function" not in prompt


def test_family_2_prompt_hides_chain_length_and_position(tmp_path):
    """The prompt must explicitly state what the agent does not know."""
    task = get_task("summarise_transactions")
    out = tmp_path / "inst"
    generate_instance(task, 4, CLEAN, str(out))
    prompt = (out / "prompts" / "agent-2.txt").read_text()
    assert "do not know how many steps" in prompt
    assert "where in the chain your step sits" in prompt
    assert "what the other steps do" in prompt


def test_family_2_prompt_plural_for_two_steps_per_agent(tmp_path):
    """Agent holding two steps gets the plural deliverable phrasing."""
    task = get_task("compute_invoices")
    out = tmp_path / "inst"
    generate_instance(task, 4, CLEAN, str(out))
    # Agent 1 holds parse and validate.
    prompt = (out / "prompts" / "agent-1.txt").read_text()
    assert "Your deliverable files are:" in prompt
    assert "`parse.py`" in prompt
    assert "`validate.py`" in prompt
    # Singular for a 1-step agent doesn't apply here (every agent has 2 steps),
    # but the multi-piece spec wording does.
    assert "Your pieces of the specification" in prompt


def test_family_2_conflict_distributes_strict_validate_variant(tmp_path):
    task = get_task("summarise_transactions")
    out = tmp_path / "inst"
    manifest = generate_instance(task, 4, CONFLICTING, str(out))
    variants = [c["variant"] for ag in manifest["agents"]
                for c in ag["components"] if c["label"] == "Step: validate"]
    assert "strict" in variants
    assert None in variants
    # The strict text says "strictly greater than zero".
    joined = "\n".join(
        (out / "prompts" / f"agent-{i}.txt").read_text()
        for i in range(1, 5))
    assert "strictly greater than zero" in joined
    assert "greater than or equal to zero" in joined


def test_role_names_for_family_1_is_empty():
    """Family 1 component labels are descriptive, not addressable;
    role_names is always []. Pre-condition for the parser's
    role-classification step."""
    from agent_comms.task_generator.library import role_names_for
    assert role_names_for(get_task("process_orders")) == []


def test_role_names_for_summarise_transactions():
    """Family 2 ships the step deliverable basenames, excluding pipeline."""
    from agent_comms.task_generator.library import role_names_for
    assert role_names_for(get_task("summarise_transactions")) == [
        "parse", "validate", "aggregate", "format_output",
    ]


def test_role_names_for_compute_invoices():
    """Eight steps, eight role names (pipeline excluded)."""
    from agent_comms.task_generator.library import role_names_for
    assert role_names_for(get_task("compute_invoices")) == [
        "parse", "validate", "resolve_customer", "resolve_product",
        "compute_line_totals", "apply_discount", "compute_tax",
        "format_invoices",
    ]


def test_role_names_for_summarise_transactions_v2_excludes_pipeline():
    """The v2 task has parse, validate, aggregate, format_output;
    pipeline is excluded by design."""
    from agent_comms.task_generator.library import role_names_for
    names = role_names_for(get_task("summarise_transactions_v2"))
    assert names == ["parse", "validate", "aggregate", "format_output"]
    assert "pipeline" not in names


def test_family_1_prompt_still_uses_family_1_template(tmp_path):
    """Regression: Family 1 must still render the single-function template."""
    task = get_task("process_orders")
    out = tmp_path / "inst"
    generate_instance(task, 4, CLEAN, str(out))
    prompt = (out / "prompts" / "agent-1.txt").read_text()
    assert "implement a single Python function" in prompt
    assert "solution.py" in prompt
    # Family 2 wording must not leak into Family 1 prompts.
    assert "chain of step functions" not in prompt
    assert "pipeline.py" not in prompt
