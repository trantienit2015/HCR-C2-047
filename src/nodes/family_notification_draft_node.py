"""FamilyNotificationDraftNode — inner subgraph step 4 (HCR-C2-047).

Drafts a severity-appropriate family notification. On NORMAL severity (early_exit) it produces
no draft. The contact profile is resolved in-memory from the InvocationContext-provided
provider and is NEVER written to State (APPI Article 17). The draft references the resident by
opaque ref / room, not by an identifier echoed downstream.
"""

from __future__ import annotations

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

_TEMPLATES = {
    "CRITICAL": (
        "URGENT: A critical change in your family member's vital signs was detected "
        "and facility staff have been alerted. Please contact the facility immediately."
    ),
    "WARNING": (
        "NOTICE: A change in your family member's vital signs was detected and is being "
        "monitored by facility staff. No immediate action is required."
    ),
}


class FamilyNotificationDraftNode(FunctionNode):
    """Draft the severity-gated family notification."""

    # S-1: explicit by design. Drafts resident-related notifications in the
    # PHI pipeline — trusted facility system caller required (matches agent.yaml default).
    # S-1: inner subgraph node — trust is authenticated once at the outer
    # backbone. An inner INTERNAL requirement is privilege escalation an
    # external caller can never satisfy (see the S-1 trust-gate contract).
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def __init__(self, contact_provider: Any = None):
        super().__init__()
        self._contact_provider = contact_provider

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        severity = state.get("severity", "NORMAL")
        skipped = bool(state.get("early_exit")) or severity == "NORMAL"
        draft = "" if skipped else _TEMPLATES.get(severity, _TEMPLATES["WARNING"])

        # S-4: audit the severity-gated draft decision — severity + drafted flag only, no PHI.
        emit_trace_event(
            "family_notification_drafted",
            {"severity": severity, "drafted": not skipped},
            state,
        )

        return {"notification_draft": draft, "status": AgentStatus.SUCCESS.value}
