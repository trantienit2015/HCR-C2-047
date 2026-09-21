"""ResponseValidateNode — outer post_process slot (HCR-C2-047).

APPI Article 17 output gate: build an anonymized dispatch confirmation + anomaly summary and
strip any residual PHI / resident identifiers before the response leaves the agent. This is
deterministic, not an LLM self-check.
"""

from __future__ import annotations

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.services.vital_service import strip_phi


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


class ResponseValidateNode(FunctionNode):
    """Anonymized output assembly + PHI stripping (outer post_process)."""

    # S-1: explicit by design. Final APPI output gate of the PHI pipeline —
    # trusted facility system caller required (matches agent.yaml default).
    # S-1: outer post_process — agent response boundary; matches agent.yaml required_trust_level.
    # VERIFIED_EXTERNAL not INTERNAL: the Marketplace runner stamps VERIFIED_EXTERNAL unconditionally and grants INTERNAL to nobody, so an INTERNAL requirement is refused before execute() on every invocation.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        severity = state.get("severity", "NORMAL")
        dispatched = bool(state.get("dispatched", False))
        channel = state.get("dispatch_channel", "")

        if severity == "NORMAL":
            summary = "Vitals within normal range for this resident. No notification dispatched."
        else:
            summary = self._render(severity, state.get("anomalies") or [], dispatched, channel)

        # APPI: strip any residual identifiers from the final response string.
        clean = strip_phi(summary)

        emit_trace_event(
            "response_validated",
            {"resident_ref": state.get("resident_ref", ""), "severity": severity, "dispatched": dispatched},
            state,
        )

        # Progress shown to the caller while the run is in flight, so a
        # multi-second cold start does not read as a frozen chat. Counts
        # and stage only — never caller content.
        _emit_progress("Preparing the notification summary.", "post_process")
        return {
            "phi_stripped": True,
            "result": clean,
            "formatted_output": clean,
            "status": AgentStatus.SUCCESS.value,
        }

    # Reader-facing labels. The state keys are machine names; a carer reading the
    # chat needs the metric in words and the unit, or the reply is unactionable.
    _LABELS = {
        "heart_rate": ("Heart rate", "bpm"),
        "bp_systolic": ("Blood pressure (systolic)", "mmHg"),
        "spo2": ("SpO2", "%"),
        "temperature": ("Temperature", "°C"),
        "respiration": ("Respiration", "breaths/min"),
    }

    @classmethod
    def _render(cls, severity: str, anomalies: list[Any], dispatched: bool, channel: str) -> str:
        """Multi-line reader-facing summary: what was abnormal, and what happens next.

        Values only — never the resident name or any identifier (APPI Article 17);
        the caller-supplied resident_ref is an opaque reference and is not printed.
        """
        lines = [f"Severity: {severity} — {len(anomalies)} vital sign(s) outside the expected range.", ""]
        for item in anomalies:
            label, unit = cls._LABELS.get(item.get("metric"), (str(item.get("metric")), ""))
            value = item.get("value")
            note = " (absolute safety threshold breached)" if item.get("absolute_critical") else ""
            deviation = item.get("deviation_pct") or 0
            drift = f", {deviation}% from this resident's baseline" if deviation else ""
            lines.append(f"- {label}: {value}{unit}{note}{drift}")
        lines.append("")
        if dispatched:
            lines.append(f"A notification has been sent to the registered family contact via {channel}.")
        elif severity == "CRITICAL":
            lines.append("No notification could be sent — escalate to the on-duty nurse manually.")
        else:
            lines.append("No family notification was required at this severity.")
        return "\n".join(lines)
