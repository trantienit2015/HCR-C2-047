# HCR-C2-047 — Unit Tests: FamilyNotificationDraft + NotificationDispatch + ResponseValidate

from framework.schemas.agent_status import AgentStatus
from src.nodes.family_notification_draft_node import FamilyNotificationDraftNode
from src.nodes.notification_dispatch_node import NotificationDispatchNode
from src.nodes.response_validate_node import ResponseValidateNode


def _provider(resident_ref):
    return {"baseline": {}, "contact": {"channel": "sms"}}


class FakeNotifier:
    def __init__(self):
        self.sent = []

    def send(self, contact, draft):
        self.sent.append((contact, draft))


def _state(**extra):
    s = {"resident_ref": "R-1", "node_history": [], "error_log": [], "execution_time": {}}
    s.update(extra)
    return s


class TestFamilyNotificationDraftNode:
    def test_critical_draft(self):
        node = FamilyNotificationDraftNode(contact_provider=_provider)
        result = node.execute(_state(severity="CRITICAL", early_exit=False))
        assert result["status"] == AgentStatus.SUCCESS
        assert "URGENT" in result["notification_draft"]

    def test_normal_no_draft(self):
        node = FamilyNotificationDraftNode(contact_provider=_provider)
        result = node.execute(_state(severity="NORMAL", early_exit=True))
        assert result["notification_draft"] == ""


class TestNotificationDispatchNode:
    def test_dispatch_when_draft(self):
        notifier = FakeNotifier()
        node = NotificationDispatchNode(notifier=notifier, contact_provider=_provider)
        result = node.execute(_state(severity="CRITICAL", notification_draft="URGENT msg"))
        assert result["dispatched"] is True
        assert result["dispatch_channel"] == "sms"
        assert len(notifier.sent) == 1

    def test_no_dispatch_when_no_draft(self):
        node = NotificationDispatchNode(notifier=FakeNotifier(), contact_provider=_provider)
        result = node.execute(_state(severity="NORMAL", notification_draft=""))
        assert result["dispatched"] is False

    def test_dispatch_failure_returns_error(self):
        class BoomNotifier:
            def send(self, contact, draft):
                raise RuntimeError("notification gateway down")

        node = NotificationDispatchNode(notifier=BoomNotifier(), contact_provider=_provider)
        result = node.execute(_state(severity="CRITICAL", notification_draft="URGENT msg"))
        assert result["status"] == AgentStatus.ERROR
        assert "dispatch failed" in result["error_log"][0]
        assert result["dispatched"] is False


class TestResponseValidateNode:
    def test_critical_summary_no_phi(self):
        node = ResponseValidateNode()
        result = node.execute(_state(severity="CRITICAL", dispatched=True, dispatch_channel="sms",
                                     anomalies=[{"metric": "spo2"}]))
        assert result["status"] == AgentStatus.SUCCESS
        assert result["phi_stripped"] is True
        assert "CRITICAL" in result["result"]
        assert "様" not in result["result"]

    def test_normal_summary(self):
        node = ResponseValidateNode()
        result = node.execute(_state(severity="NORMAL", dispatched=False))
        assert "normal range" in result["result"].lower()
