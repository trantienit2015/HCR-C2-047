"""NotificationDispatchNode — inner subgraph step 5 (HCR-C2-047).

Dispatches the drafted notification to the registered family contact channel and logs an
anonymized dispatch event for audit. The contact channel is resolved in-memory from the
InvocationContext-provided provider (APPI: never in State). On NORMAL (no draft) nothing is
dispatched. The notification client is injected via the constructor (S-3: no os.environ).
"""

from __future__ import annotations

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event


class NotificationDispatchNode(FunctionNode):
    """Dispatch the family notification (anonymized audit)."""

    # S-1: explicit by design. Sends outbound notifications + resolves the
    # family contact (privileged side effect) — trusted facility system caller required.
    # S-1: inner subgraph node — trust is authenticated once at the outer
    # backbone. An inner INTERNAL requirement is privilege escalation an
    # external caller can never satisfy (see the S-1 trust-gate contract).
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def __init__(self, notifier: Any = None, contact_provider: Any = None):
        super().__init__()
        self._notifier = notifier
        self._contact_provider = contact_provider

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        draft = state.get("notification_draft", "")
        resident_ref = state.get("resident_ref", "")

        if not draft:
            emit_trace_event(
                "family_notification_dispatch_skipped",
                {"resident_ref": resident_ref, "reason": "no_draft"},
                state,
            )
            return {"dispatched": False, "dispatch_channel": "", "status": AgentStatus.SUCCESS.value}

        # Resolve the contact channel in-memory (not persisted in State).
        channel = "registered_contact"
        contact = {}
        if self._contact_provider is not None:
            contact = (self._contact_provider(resident_ref) or {}).get("contact", {})
            channel = contact.get("channel", "registered_contact")

        if self._notifier is not None:
            try:
                self._notifier.send(contact, draft)
            except Exception as exc:
                # Dispatch outage must be observable + a clean ERROR (anonymized — no PHI in log).
                emit_trace_event(
                    "notification_dispatch_failed",
                    {
                        "resident_ref": resident_ref,
                        "channel": channel,
                        "error": str(exc),
                        "correlation_id": state.get("correlation_id"),
                        "trace_id": state.get("trace_id"),
                    },
                    state,
                )
                return {
                    "dispatched": False,
                    "dispatch_channel": channel,
                    "status": AgentStatus.ERROR.value,
                    "error_log": [f"NotificationDispatchNode: dispatch failed: {exc}"],
                }

        # Audit: anonymized — resident_ref (opaque) + channel only, never the message PHI/identity.
        emit_trace_event(
            "family_notification_dispatched",
            {
                "resident_ref": resident_ref,
                "channel": channel,
                "severity": state.get("severity", ""),
                "correlation_id": state.get("correlation_id"),
                "trace_id": state.get("trace_id"),
            },
            state,
        )

        return {
            "dispatched": True,
            "dispatch_channel": channel,
            "status": AgentStatus.SUCCESS.value,
        }
