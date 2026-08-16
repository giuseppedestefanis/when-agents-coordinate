"""Graph data model for the session parser.

A run is a heterogeneous temporal graph. Nodes are agents and files. Edges are
typed, timestamped and weighted. See PLAN.md, section "Graph definition".
"""

from __future__ import annotations

from dataclasses import dataclass

# Edge type values.
AGENT_TO_AGENT = "agent_to_agent"
AGENT_TO_FILE = "agent_to_file"
FILE_TO_AGENT = "file_to_agent"

# Node type values.
AGENT = "agent"
FILE = "file"


@dataclass
class Node:
    node_id: str
    node_type: str   # AGENT or FILE
    run_id: str
    label: str = ""


@dataclass
class Edge:
    run_id: str
    source: str
    target: str
    source_type: str
    target_type: str
    edge_type: str   # AGENT_TO_AGENT, AGENT_TO_FILE or FILE_TO_AGENT
    subtype: str     # create, edit, append, delete, read, message, spawn
    timestamp: str
    token_cost: float
    byte_size: int
    turn_uuid: str = ""
    tool: str = ""
    # Classification of the target side of a message edge: one of
    # TARGET_KIND_CANONICAL, TARGET_KIND_ALIAS, TARGET_KIND_BROADCAST,
    # TARGET_KIND_ROLE or TARGET_KIND_UNKNOWN. Empty for non-message
    # edges (agent-to-file and file-to-agent). See
    # `agent_comms.parser.addressing` for the classification rules.
    target_kind: str = ""


@dataclass
class Turn:
    run_id: str
    agent: str
    turn_uuid: str
    timestamp: str
    is_sidechain: bool
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_creation_tokens: int
    model: str


class RunGraph:
    """The heterogeneous temporal graph for one run."""

    def __init__(self, run_id: str):
        self.run_id = run_id
        self.nodes: dict[str, Node] = {}
        self.edges: list[Edge] = []

    def ensure_node(self, node_id: str, node_type: str, label: str = "") -> Node:
        if node_id not in self.nodes:
            self.nodes[node_id] = Node(
                node_id, node_type, self.run_id, label or node_id)
        return self.nodes[node_id]

    def has_node(self, node_id: str) -> bool:
        return node_id in self.nodes

    def add_edge(self, **kwargs) -> Edge:
        edge = Edge(run_id=self.run_id, **kwargs)
        self.edges.append(edge)
        return edge

    def counts(self) -> dict:
        """Return node and edge counts by type, for the run-level dataset.

        Includes both the total agent-to-agent event count
        (`n_agent_to_agent`, every non-empty-`to` message) and the
        directed subset (`n_agent_to_agent_directed`, messages whose
        target classifies as TARGET_KIND_CANONICAL or
        TARGET_KIND_ALIAS — that is, messages addressed to a
        resolvable specific agent). The total count is invariant
        under the 2026-05-30 addressing-convention change; the
        directed count is the new metric introduced by that change.
        """
        agents = sum(1 for n in self.nodes.values()
                     if n.node_type == AGENT)
        files = sum(1 for n in self.nodes.values()
                    if n.node_type == FILE)
        by_type: dict[str, int] = {}
        for edge in self.edges:
            by_type[edge.edge_type] = by_type.get(edge.edge_type, 0) + 1
        directed = sum(
            1 for edge in self.edges
            if edge.edge_type == AGENT_TO_AGENT
            and edge.target_kind in ("canonical", "alias"))
        return {
            "n_nodes": len(self.nodes),
            "n_edges": len(self.edges),
            "n_agent_nodes": agents,
            "n_file_nodes": files,
            "n_agent_to_agent": by_type.get(AGENT_TO_AGENT, 0),
            "n_agent_to_agent_directed": directed,
            "n_agent_to_file": by_type.get(AGENT_TO_FILE, 0),
            "n_file_to_agent": by_type.get(FILE_TO_AGENT, 0),
        }
