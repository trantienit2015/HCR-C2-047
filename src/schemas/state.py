"""AgentCore Platform v1.0 — HCR-C2-047 State schema.

APPI Article 17 (要配慮個人情報): vital signs + resident identity are sensitive personal
information. State is checkpointed to the DB, so this schema deliberately does NOT persist
the resident baseline or contact profile — those are loaded from InvocationContext per
invocation only. The resident is referenced by an opaque, non-identifying `resident_ref`.
"""

from typing import NotRequired

from framework.schemas.agent_state import AgentState


# Type-check note: the wheel ships no py.typed, so mypy resolves AgentState to
# Any and reports every NotRequired below as valid-type. The fields are correct
# (NotRequired is required here) -- the report is a packaging artifact, suppressed
# per field. Drop these ignores once the wheel ships py.typed.
class State(AgentState):
    """Vital anomaly + family notification state (APPI-safe).

    Shared fields inherited from AgentState. Agent-specific fields only below.
    """

    # VitalDataInputNode (outer pre_process) outputs
    resident_ref: NotRequired[str]  # type: ignore[valid-type]  # opaque reference, NOT a patient identifier
    vitals: NotRequired[dict]  # type: ignore[valid-type]  # {"heart_rate","bp_systolic","spo2","temperature","respiration"}

    # AnomalyDetectNode (inner) output
    anomalies: NotRequired[list]  # type: ignore[valid-type]  # list of {"metric","value","deviation_pct"}

    # AnomalySeverityClassifyNode (inner) output
    severity: NotRequired[str]  # type: ignore[valid-type]  # "CRITICAL" | "WARNING" | "NORMAL"
    early_exit: NotRequired[bool]  # type: ignore[valid-type]  # True when NORMAL (no notification dispatched)

    # FamilyNotificationDraftNode (inner) output
    notification_draft: NotRequired[str]  # type: ignore[valid-type]

    # NotificationDispatchNode (inner) output
    dispatched: NotRequired[bool]  # type: ignore[valid-type]
    dispatch_channel: NotRequired[str]  # type: ignore[valid-type]

    # ResponseValidateNode (outer post_process) output
    phi_stripped: NotRequired[bool]  # type: ignore[valid-type]
