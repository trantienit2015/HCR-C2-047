"""AnomalySeverityClassifyNode — inner subgraph step 3 (HCR-C2-047).

Classifies the detected anomalies as CRITICAL / WARNING / NORMAL. NORMAL exits the pipeline
with no notification dispatched (early_exit flag). Thresholds are config-driven per facility.
"""

from __future__ import annotations

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.services.vital_service import classify_severity


class AnomalySeverityClassifyNode(FunctionNode):
    """Severity classification with NORMAL early-exit."""

    # S-1: explicit by design. Classifies resident vital anomalies (PHI
    # pipeline) — trusted facility system caller required (matches agent.yaml default).
    # S-1: inner subgraph node — trust is authenticated once at the outer
    # backbone. An inner INTERNAL requirement is privilege escalation an
    # external caller can never satisfy (see the S-1 trust-gate contract).
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def __init__(self, critical_pct: float = 30, warning_pct: float = 15):
        super().__init__()
        self._critical_pct = critical_pct
        self._warning_pct = warning_pct

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        anomalies = state.get("anomalies", []) or []
        severity = classify_severity(anomalies, self._critical_pct, self._warning_pct)
        early_exit = severity == "NORMAL"

        emit_trace_event(
            "vital_severity_classified",
            {"resident_ref": state.get("resident_ref", ""), "severity": severity},
            state,
        )

        return {
            "severity": severity,
            "early_exit": early_exit,
            "status": AgentStatus.SUCCESS.value,
        }
