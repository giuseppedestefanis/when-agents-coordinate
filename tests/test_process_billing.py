"""Tests for the H8 process_billing task (Family 2, Instance 6): registration,
the 16-step structure, n=16 full decomposition, and the reference pipeline's
behaviour (so the main suite covers it, not only the standalone verifier)."""

from __future__ import annotations

import os
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOLUTION = os.path.join(REPO, "tasks", "family-2", "instance-6", "solution")

from agent_comms.task_generator import get_task                  # noqa: E402
from agent_comms.task_generator.library import role_names_for    # noqa: E402
from agent_comms.task_generator.instance import generate_instance  # noqa: E402


def test_registered_16_step_family2():
    t = get_task("process_billing")
    assert t.family == "family-2"
    assert t.n_components == 16
    # 16 step files + pipeline.py
    assert t.deliverable_paths()[-1] == "pipeline.py"
    assert len(t.deliverable_paths()) == 17


def test_role_names_match_step_basenames():
    t = get_task("process_billing")
    roles = role_names_for(t)
    assert len(roles) == 16
    assert sorted(roles) == sorted(
        c.deliverable_path[:-3] for c in t.components)
    # pipeline.py is deliberately NOT a role name
    assert "pipeline" not in roles


def test_deliverables_match_reference_solution():
    t = get_task("process_billing")
    ref = {f for f in os.listdir(SOLUTION) if f.endswith(".py")}
    assert ref == set(t.deliverable_paths())


def test_n16_full_decomposition():
    t = get_task("process_billing")
    d = tempfile.mkdtemp()
    manifest = generate_instance(t, agent_count=16, pattern="clean", out_dir=d)
    assert len(manifest["agents"]) == 16
    for a in manifest["agents"]:
        held = [a[k] for k in a if isinstance(a[k], list)]
        assert held and len(held[0]) == 1          # one step per agent
    prompts = [f for f in os.listdir(os.path.join(d, "prompts"))
               if f.endswith(".txt")]
    assert len(prompts) == 16
    assert "agent-16.txt" in prompts


def test_reference_pipeline_behaviour():
    sys.path.insert(0, SOLUTION)
    try:
        # fresh import of the reference pipeline
        for m in list(sys.modules):
            if m in ("pipeline",) or m in _STEP_MODULES:
                del sys.modules[m]
        from pipeline import process_billing
        orders = [
            {"order_id": "O3", "customer_id": "C1", "product_id": "P1",
             "quantity": "200", "price_per_unit": "10.0"},   # gold/taxable
            {"order_id": "O1", "customer_id": "C2", "product_id": "P2",
             "quantity": "5", "price_per_unit": "4.0"},       # silver/digital
            {"order_id": "O1", "customer_id": "C2", "product_id": "P2",
             "quantity": "9", "price_per_unit": "4.0"},       # dup -> dropped
            {"order_id": "O2", "customer_id": "C3", "product_id": "P1",
             "quantity": "1", "price_per_unit": "10.0"},      # embargo -> drop
        ]
        reference = {
            "customers": {
                "C1": {"name": "Alice", "tier": "gold", "region": "azure"},
                "C2": {"name": "Bob", "tier": "silver", "region": "azure"},
                "C3": {"name": "Cara", "tier": "gold", "region": "crimson"},
            },
            "products": {
                "P1": {"category": "standard", "taxable": True},
                "P2": {"category": "digital", "taxable": False},
            },
        }
        out = process_billing(orders, reference)
        assert out == [("O3", "Alice", 2189.0, 1), ("O1", "Bob", 19.0, 2)]
    finally:
        sys.path.remove(SOLUTION)


_STEP_MODULES = {
    "parse", "validate", "dedupe", "resolve_customer", "resolve_product",
    "filter_embargo", "compute_line_totals", "apply_volume_surcharge",
    "apply_discount", "apply_loyalty_credit", "compute_taxable_base",
    "compute_tax", "apply_shipping", "compute_final_amount", "rank_orders",
    "format_billing",
}
