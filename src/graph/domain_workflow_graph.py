"""Inner domain workflow graph for HCR-C2-047 (Cat 2).

Topology: START -> vital_context_load -> anomaly_detect -> anomaly_severity_classify
-> family_notification_draft -> notification_dispatch -> END.
Instantiated by VitalAnomalyGraphNode.get_subgraph(). The per-resident baseline / contact
provider is supplied via config (InvocationContext-derived), never via State (APPI Article 17).
"""

from __future__ import annotations

from typing import Any
from langgraph.graph import END, START

from framework.graph.base_graph import BaseGraph
from framework.schemas.agent_state import AgentState
from framework.schemas.agent_status import AgentStatus

from src.nodes.vital_context_load_node import VitalContextLoadNode
from src.nodes.anomaly_detect_node import AnomalyDetectNode
from src.nodes.anomaly_severity_classify_node import AnomalySeverityClassifyNode
from src.nodes.family_notification_draft_node import FamilyNotificationDraftNode
from src.nodes.notification_dispatch_node import NotificationDispatchNode
from src.schemas.state import State


class VitalAnomalyWorkflowGraph(BaseGraph):
    """context-load -> detect -> classify -> draft -> dispatch inner workflow."""

    @property
    def name(self) -> str:
        return "vital_anomaly_workflow"

    @property
    def state_schema(self) -> type:
        return State

    def _validate_config(self) -> None:
        pass

    def register_nodes(self) -> None:
        cfg = self.config if hasattr(self, "config") and self.config else {}
        provider = cfg.get("baseline_provider")
        thresholds = cfg.get("thresholds", {}) or {}
        self._nodes["vital_context_load"] = VitalContextLoadNode(baseline_provider=provider)
        self._nodes["anomaly_detect"] = AnomalyDetectNode(baseline_provider=provider)
        self._nodes["anomaly_severity_classify"] = AnomalySeverityClassifyNode(
            critical_pct=thresholds.get("critical_deviation_pct", 30),
            warning_pct=thresholds.get("warning_deviation_pct", 15),
        )
        self._nodes["family_notification_draft"] = FamilyNotificationDraftNode(contact_provider=provider)
        self._nodes["notification_dispatch"] = NotificationDispatchNode(
            notifier=cfg.get("notifier"), contact_provider=provider
        )

    def add_edges(self) -> None:
        self._sg.add_edge(START, "vital_context_load")
        self._sg.add_edge("vital_context_load", "anomaly_detect")
        self._sg.add_edge("anomaly_detect", "anomaly_severity_classify")
        self._sg.add_edge("anomaly_severity_classify", "family_notification_draft")
        self._sg.add_edge("family_notification_draft", "notification_dispatch")
        self._sg.add_edge("notification_dispatch", END)

    def route(self, state: AgentState) -> str:
        return END if state.get("status") == AgentStatus.ERROR else "notification_dispatch"

    def get_output(self, state: AgentState) -> dict[str, Any]:
        return {
            "anomalies": state.get("anomalies", []),
            "severity": state.get("severity", "NORMAL"),
            "early_exit": bool(state.get("early_exit", False)),
            "notification_draft": state.get("notification_draft", ""),
            "dispatched": bool(state.get("dispatched", False)),
            "dispatch_channel": state.get("dispatch_channel", ""),
            "status": state.get("status"),
            "trace_id": state.get("trace_id"),
            "correlation_id": state.get("correlation_id"),
            "node_history": state.get("node_history", []),
        }
