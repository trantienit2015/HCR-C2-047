"""Outer graph for HCR-C2-047 — Elderly Care Vital Anomaly & Family Notification Agent (Cat 2).

Backbone: initialize -> pre_process (VitalDataInput) -> main (VitalAnomalyGraphNode)
-> post_process (ResponseValidate) -> finalize. The `main` slot wraps the inner
context-load -> detect -> classify -> draft -> dispatch subgraph (Cat 2 composition).
"""

from __future__ import annotations

from framework.graph.agent_base_graph import AgentBaseGraph

from src.nodes.vital_data_input_node import VitalDataInputNode
from src.nodes.vital_anomaly_graph_node import VitalAnomalyGraphNode
from src.nodes.response_validate_node import ResponseValidateNode
from src.schemas.state import State


class VitalAnomalyNotificationGraph(AgentBaseGraph):
    """Cat 2 outer graph for elderly-care vital anomaly detection + family notification."""

    @property
    def name(self) -> str:
        return "hcr-c2-047"

    @property
    def state_schema(self) -> type:
        return State

    def register_nodes(self) -> None:
        super().register_nodes()  # injects initialize + finalize
        cfg = self.config if hasattr(self, "config") and self.config else {}
        thresholds = {
            "critical_deviation_pct": cfg.get("critical_deviation_pct", 30),
            "warning_deviation_pct": cfg.get("warning_deviation_pct", 15),
        }
        self._nodes["pre_process"] = VitalDataInputNode()
        self._nodes["main"] = VitalAnomalyGraphNode(
            baseline_provider=cfg.get("baseline_provider"),
            notifier=cfg.get("notifier"),
            thresholds=thresholds,
        )
        self._nodes["post_process"] = ResponseValidateNode()


# Alias for agent.yaml `module: "src.graph"` / AgentRegistry discovery.
Graph = VitalAnomalyNotificationGraph
