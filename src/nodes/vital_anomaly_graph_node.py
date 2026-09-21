"""VitalAnomalyGraphNode — the `main` slot GraphNode (HCR-C2-047, Cat 2).

Wraps the inner context-load -> detect -> classify -> draft -> dispatch subgraph. The
per-resident baseline + contact provider (sourced from InvocationContext, NOT State per APPI
Article 17) and severity thresholds are forwarded to the inner graph via _parent_config().

Architecture: this GraphNode enforces its own S-1 trust gate (declared below); S-2/S-3 content
gating on the inner workflow's own state is delegated to each inner node's own BaseNode
lifecycle (matches scaffold canonical — avoids a single-node probe pulling in the whole inner
subgraph). Boundary is verified by tests/proof_of_boundary/test_pb_graphnode_boundary.py.
"""

from __future__ import annotations

from typing import Any, ClassVar, cast

from framework.nodes.graph_node import GraphNode
from framework.schemas.agent_state import AgentState
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event


class VitalAnomalyGraphNode(GraphNode):
    """Cat 2 main slot — wraps the vital-anomaly + notification domain workflow."""

    # S-1: explicit by design. Outer main-slot boundary of the PHI pipeline —
    # trusted facility system caller required (matches agent.yaml default).
    # S-1: outer main slot (GraphNode wrapper) — receives caller input; matches agent.yaml required_trust_level.
    # VERIFIED_EXTERNAL not INTERNAL: the Marketplace runner stamps VERIFIED_EXTERNAL unconditionally and grants INTERNAL to nobody, so an INTERNAL requirement is refused before execute() on every invocation.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    error_strategy: ClassVar[str] = "propagate"
    propagate_hitl: ClassVar[bool] = False

    def __init__(self, baseline_provider: Any = None, notifier: Any = None, thresholds: Any = None):
        super().__init__()
        self._baseline_provider = baseline_provider
        self._notifier = notifier
        self._thresholds = thresholds or {}

    def get_subgraph(self) -> Any:
        from src.graph.domain_workflow_graph import VitalAnomalyWorkflowGraph

        sg = VitalAnomalyWorkflowGraph(config=self._parent_config())
        sg.compile()
        return sg

    def extract_input(self, state: AgentState) -> str:
        # S-4: runs inside GraphNode.execute() — audit the dispatch into the anomaly subgraph.
        emit_trace_event(
            "vital_anomaly_workflow_dispatched",
            {"resident_ref": state.get("resident_ref", "")},
            state,
        )
        return cast(str, state.get("validated_input", state.get("user_input", "")))

    def merge_output(self, state: AgentState, sub_result: dict[str, Any]) -> dict[str, Any]:
        # S-4: runs inside GraphNode.execute() — audit the subgraph outcome merged back out.
        emit_trace_event(
            "vital_anomaly_workflow_completed",
            {
                "resident_ref": state.get("resident_ref", ""),
                "severity": sub_result.get("severity", "NORMAL"),
                "n_anomalies": len(sub_result.get("anomalies", [])),
                "dispatched": bool(sub_result.get("dispatched", False)),
            },
            state,
        )
        # Note: baseline / contact are deliberately NOT merged back into outer State (APPI).
        return {
            "anomalies": sub_result.get("anomalies", []),
            "severity": sub_result.get("severity", "NORMAL"),
            "early_exit": bool(sub_result.get("early_exit", False)),
            "notification_draft": sub_result.get("notification_draft", ""),
            "dispatched": bool(sub_result.get("dispatched", False)),
            "dispatch_channel": sub_result.get("dispatch_channel", ""),
            "status": sub_result.get("status"),
        }

    def _parent_config(self) -> dict[str, Any]:
        return {
            "baseline_provider": self._baseline_provider,
            "notifier": self._notifier,
            "thresholds": self._thresholds,
        }
