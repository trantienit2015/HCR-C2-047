"""VitalContextLoadNode — inner subgraph step 1 (HCR-C2-047).

Parses the vitals payload from the outer pre_process and confirms a per-resident baseline is
available from the InvocationContext-provided provider (APPI Article 17 — the baseline itself
is loaded in-memory at use time by downstream nodes and is NEVER written to State). This node
only verifies availability and forwards the opaque resident_ref + vitals.
"""

from __future__ import annotations

import json

from typing import Any, ClassVar, cast

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event


class VitalContextLoadNode(FunctionNode):
    """Verify per-resident baseline availability (APPI: no baseline persisted in State)."""

    # S-1: explicit by design. Touches the per-resident PHI baseline
    # provider — trusted facility system caller required (matches agent.yaml default).
    # S-1: inner subgraph node — trust is authenticated once at the outer
    # backbone. An inner INTERNAL requirement is privilege escalation an
    # external caller can never satisfy (see the S-1 trust-gate contract).
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def __init__(self, baseline_provider: Any = None):
        # baseline_provider: callable(resident_ref) -> {"baseline": {...}, "contact": {...}}
        super().__init__()
        self._baseline_provider = baseline_provider

    def _parse(self, raw: Any) -> dict[str, Any]:
        if isinstance(raw, dict):
            return raw
        try:
            return cast(dict[str, Any], json.loads(raw) if raw else {})
        except (ValueError, TypeError):
            return {}

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        payload = self._parse(state.get("user_input", ""))
        vitals = payload.get("vitals", {})
        resident_ref = payload.get("resident_ref", "")

        if not vitals:
            emit_trace_event(
                "vital_context_load_rejected",
                {"resident_ref": resident_ref, "reason": "empty_vitals"},
                state,
            )
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["VitalContextLoadNode: empty vitals in inner input"],
            }

        # Touch the provider to confirm a baseline exists for this resident, but do NOT place
        # the baseline (sensitive PII) into State — downstream nodes re-resolve it in-memory.
        baseline_available = True
        if self._baseline_provider is not None:
            ctx_data = self._baseline_provider(resident_ref) or {}
            baseline_available = bool(ctx_data.get("baseline"))

        # S-4: audit the baseline availability check — opaque ref + flag only, no PHI.
        emit_trace_event(
            "vital_context_loaded",
            {"resident_ref": resident_ref, "baseline_available": baseline_available},
            state,
        )

        return {
            "resident_ref": resident_ref,
            "vitals": vitals,
            "status": AgentStatus.SUCCESS.value,
        }
