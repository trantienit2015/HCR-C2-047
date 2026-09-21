# HCR-C2-047 — Integration Test: full Cat 2 graph compile + invoke

from framework.schemas.agent_status import AgentStatus
from framework.schemas.invocation_context import InvocationContext
from framework.schemas.trust_level import TrustLevel
from src.graph.graph import Graph


def _baseline_provider(resident_ref):
    return {"baseline": {"heart_rate": 70, "spo2": 98, "temperature": 36.5,
                         "bp_systolic": 120, "respiration": 16},
            "contact": {"channel": "sms"}}


class FakeNotifier:
    def __init__(self):
        self.sent = []

    def send(self, contact, draft):
        self.sent.append((contact, draft))


def _invoke(vitals, notifier=None):
    agent = Graph(config={
        "max_retry": 1,
        "critical_deviation_pct": 30,
        "warning_deviation_pct": 15,
        "baseline_provider": _baseline_provider,
        "notifier": notifier or FakeNotifier(),
    })
    agent.compile()
    ctx = InvocationContext(
        session_id="hcr-it", caller_trust_level=TrustLevel.INTERNAL, caller_id="facility-monitor"
    )
    return agent.invoke("", ctx=ctx, input_context={"resident_ref": "R-1", "vitals": vitals})


class TestVitalAnomalyNotificationGraph:
    def test_critical_dispatches_notification(self):
        notifier = FakeNotifier()
        result = _invoke({"spo2": 85, "heart_rate": 72}, notifier=notifier)  # spo2 absolute critical
        assert result["status"] in (AgentStatus.SUCCESS, AgentStatus.SUCCESS.value)
        assert "CRITICAL" in (result.get("output") or "")
        assert len(notifier.sent) == 1

    def test_normal_no_notification(self):
        notifier = FakeNotifier()
        result = _invoke({"spo2": 98, "heart_rate": 70, "temperature": 36.5}, notifier=notifier)
        assert result["status"] in (AgentStatus.SUCCESS, AgentStatus.SUCCESS.value)
        assert "normal range" in (result.get("output") or "").lower()
        assert len(notifier.sent) == 0

    def test_node_history_covers_backbone(self):
        result = _invoke({"heart_rate": 120})
        joined = " ".join(result.get("node_history", []))
        assert "VitalDataInputNode" in joined
        assert "VitalAnomalyGraphNode" in joined
        assert "ResponseValidateNode" in joined

    def test_invalid_input_does_not_crash(self):
        result = _invoke({"heart_rate": -1})
        assert result["status"] in (
            AgentStatus.SUCCESS, AgentStatus.SUCCESS.value,
            AgentStatus.ERROR, AgentStatus.ERROR.value,
        )
