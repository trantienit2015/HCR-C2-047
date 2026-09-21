"""AnomalyDetectNode — inner subgraph step 2 (HCR-C2-047).

Compares the resident's readings against the per-resident baseline using a deterministic
threshold + statistical-deviation engine (non-suppressible for critical vital thresholds).
The baseline is resolved in-memory from the InvocationContext-provided provider at compute
time and is NEVER written to State (APPI Article 17).
"""

from __future__ import annotations

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.services.vital_service import detect_anomalies


def _emit_progress(message: str, stage: str) -> None:
    """Emit a caller-visible progress event; no-op if unsupported.

    Imported lazily: shared.services.events ships with agentcore 1.0.2+, and a
    module-level import would break test collection on an older local wheel even
    though the deployed image has it. Outside the Marketplace the emitter is a
    no-op, so a failure here must never affect the run.
    """
    try:
        from shared.services.events import emitter
        from shared.services.events.types import EventType

        emitter().emit_event(
            event_type=EventType.PROGRESS_UPDATE,
            message=message,
            metadata={"stage": stage},
        )
    except Exception:  # noqa: BLE001 — progress is cosmetic, never blocking
        pass


class AnomalyDetectNode(FunctionNode):
    """Deterministic vital anomaly detection vs baseline."""

    # S-1: explicit by design. Resolves the per-resident PHI baseline —
    # trusted facility system caller required (matches agent.yaml default).
    # S-1: inner subgraph node — trust is authenticated once at the outer
    # backbone. An inner INTERNAL requirement is privilege escalation an
    # external caller can never satisfy (see the S-1 trust-gate contract).
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def __init__(self, baseline_provider: Any = None):
        super().__init__()
        self._baseline_provider = baseline_provider

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        vitals = state.get("vitals", {}) or {}
        resident_ref = state.get("resident_ref", "")

        # Resolve baseline in-memory (not persisted in State).
        baseline = {}
        if self._baseline_provider is not None:
            ctx_data = self._baseline_provider(resident_ref) or {}
            baseline = ctx_data.get("baseline", {})

        anomalies = detect_anomalies(vitals, baseline)

        # Audit event carries only the resident_ref (opaque) + anomaly count — no raw PHI.
        emit_trace_event(
            "vital_anomaly_detected",
            {"resident_ref": resident_ref, "n_anomalies": len(anomalies)},
            state,
        )

        # Progress shown to the caller while the run is in flight, so a
        # multi-second cold start does not read as a frozen chat. Counts
        # and stage only — never caller content.
        _emit_progress(f"Checked vitals against thresholds ({len(anomalies)} anomaly(ies)).", "main")
        return {"anomalies": anomalies, "status": AgentStatus.SUCCESS.value}
