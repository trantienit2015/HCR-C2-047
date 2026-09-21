"""VitalDataInputNode — outer pre_process slot (HCR-C2-047).

S-1 gate (INTERNAL): validate + normalize the incoming vital sign payload, range-check,
reject malformed input. Serializes only the vitals + opaque resident_ref into
`validated_input` (JSON string) for the inner subgraph. The per-resident baseline and contact
profile are NOT placed here — they flow via InvocationContext/config (APPI Article 17).
"""

from __future__ import annotations

import json
import re
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

_METRICS = ("heart_rate", "bp_systolic", "spo2", "temperature", "respiration")

# Free-text aliases for each metric, for the conversational path only. Kept
# deliberately narrow: a number is only accepted when it follows a metric word,
# so an unrelated figure in the sentence is never read as a vital sign.
_PROSE_ALIASES: dict[str, tuple[str, ...]] = {
    "heart_rate": ("heart rate", "pulse", "hr", "心拍"),
    "bp_systolic": ("systolic", "blood pressure", "bp", "血圧"),
    "spo2": ("spo2", "oxygen saturation", "oxygen", "sao2", "酸素"),
    "temperature": ("temperature", "temp", "fever", "体温"),
    "respiration": ("respiration", "respiratory rate", "breathing", "呼吸"),
}


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


class VitalDataInputNode(FunctionNode):
    """Validate + normalize vital sign payload (outer pre_process)."""

    # Privileged: handles 要配慮個人情報 (sensitive PII).
    # S-1: outer pre_process — first node to receive caller input; matches agent.yaml required_trust_level.
    # VERIFIED_EXTERNAL not INTERNAL: the Marketplace runner stamps VERIFIED_EXTERNAL unconditionally and grants INTERNAL to nobody, so an INTERNAL requirement is refused before execute() on every invocation.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        ctx = state.get("input_context", {}) or {}
        vitals = ctx.get("vitals")
        resident_ref = ctx.get("resident_ref", "")

        # A facility system supplies structured vitals in input_context. A person
        # chatting supplies a sentence, which would otherwise be rejected as
        # "missing_or_invalid_vitals" and return an empty reply — indistinguishable
        # from a dead pod. Fall back to reading the metrics out of the prose.
        if not isinstance(vitals, dict) or not vitals:
            vitals = self._vitals_from_prose(state.get("user_input", ""))
            if vitals and not resident_ref:
                resident_ref = "chat-session"

        if not isinstance(vitals, dict) or not vitals:
            emit_trace_event(
                "vital_input_rejected",
                {"resident_ref": resident_ref, "reason": "missing_or_invalid_vitals"},
                state,
            )
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["VitalDataInputNode: missing or invalid 'vitals' payload"],
            }

        # Range-check: every present metric must be a positive number.
        normalized = {}
        for m in _METRICS:
            v = vitals.get(m)
            if v is None:
                continue
            if not isinstance(v, (int, float)) or v <= 0:
                emit_trace_event(
                    "vital_input_rejected",
                    {"resident_ref": resident_ref, "reason": f"invalid_value_{m}"},
                    state,
                )
                return {
                    "status": AgentStatus.ERROR.value,
                    "error_log": [f"VitalDataInputNode: invalid value for '{m}': {v!r}"],
                }
            normalized[m] = v

        if not normalized:
            emit_trace_event(
                "vital_input_rejected",
                {"resident_ref": resident_ref, "reason": "no_valid_metrics"},
                state,
            )
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["VitalDataInputNode: no valid vital metrics provided"],
            }

        payload = {"vitals": normalized, "resident_ref": resident_ref}

        # S-4: audit the validated intake — opaque resident_ref + metric count only, no raw PHI.
        emit_trace_event(
            "vital_input_validated",
            {"resident_ref": resident_ref, "n_metrics": len(normalized)},
            state,
        )

        # Progress shown to the caller while the run is in flight, so a
        # multi-second cold start does not read as a frozen chat. Counts
        # and stage only — never caller content.
        _emit_progress(f"Vital signs validated ({len(normalized)} metric(s)).", "pre_process")
        return {
            "resident_ref": resident_ref,
            "vitals": normalized,
            "validated_input": json.dumps(payload, ensure_ascii=False),
            "status": AgentStatus.SUCCESS.value,
        }

    @staticmethod
    def _vitals_from_prose(raw: Any) -> dict[str, Any]:
        """Extract vital metrics from a free-text sentence (chat path).

        Returns {} when nothing recognizable is present, so the caller falls
        through to the normal rejection path rather than inventing readings.
        The range check in execute() still applies to whatever is found here.
        """
        if not isinstance(raw, str) or not raw.strip():
            return {}
        text = raw.lower()
        found: dict[str, float] = {}
        for metric, aliases in _PROSE_ALIASES.items():
            for alias in aliases:
                # the number must follow the metric word, within a short window
                match = re.search(re.escape(alias) + r"[^0-9]{0,15}(\d{1,3}(?:\.\d{1,2})?)", text)
                if match:
                    found[metric] = float(match.group(1))
                    break
        return found
