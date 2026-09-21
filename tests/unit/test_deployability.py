"""HCR-C2-047 — deployability + human-usability regression locks.

Two classes of defect that leave the agent looking dead rather than broken:
an S-1 level the Marketplace runner can never satisfy, and an input contract
that only a structured caller can meet.
"""

import json
from pathlib import Path

from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel

from src.nodes.anomaly_detect_node import AnomalyDetectNode
from src.nodes.anomaly_severity_classify_node import AnomalySeverityClassifyNode
from src.nodes.family_notification_draft_node import FamilyNotificationDraftNode
from src.nodes.notification_dispatch_node import NotificationDispatchNode
from src.nodes.response_validate_node import ResponseValidateNode
from src.nodes.vital_anomaly_graph_node import VitalAnomalyGraphNode
from src.nodes.vital_context_load_node import VitalContextLoadNode
from src.nodes.vital_data_input_node import VitalDataInputNode

OUTER = (VitalDataInputNode, VitalAnomalyGraphNode, ResponseValidateNode)
INNER = (
    VitalContextLoadNode,
    AnomalyDetectNode,
    AnomalySeverityClassifyNode,
    FamilyNotificationDraftNode,
    NotificationDispatchNode,
)


class TestTrustLevelsAreDeployable:
    """The Marketplace runner stamps VERIFIED_EXTERNAL and grants INTERNAL to nobody.

    A node requiring INTERNAL is refused by the S-1 gate before execute() on every
    invocation, so the agent can never run — the symptom is an empty chat reply,
    which is indistinguishable from a crashed pod.
    """

    def test_no_node_requires_internal(self):
        offenders = [
            cls.__name__
            for cls in OUTER + INNER
            if cls.required_trust_level is TrustLevel.INTERNAL
        ]
        assert not offenders, (
            f"{offenders} require INTERNAL — unreachable on the Marketplace runner"
        )

    def test_outer_nodes_match_the_manifest(self):
        for cls in OUTER:
            assert cls.required_trust_level is TrustLevel.VERIFIED_EXTERNAL, cls.__name__

    def test_inner_nodes_do_not_escalate(self):
        """Trust is authenticated once at the outer backbone (see the S-1 trust-gate contract)."""
        for cls in INNER:
            assert cls.required_trust_level is TrustLevel.ANONYMOUS, cls.__name__

    def test_manifest_agrees_with_the_code(self):
        import yaml

        manifest = yaml.safe_load(
            (Path("config/agent.yaml")).read_text(encoding="utf-8")
        )
        assert manifest["required_trust_level"] == "VERIFIED_EXTERNAL"
        # root-level schema, not nested under `agent:` (invisible to AgentRegistry)
        assert "agent" not in manifest
        assert manifest["class"] == "src.graph.graph.VitalAnomalyNotificationGraph"


class TestProseInputAccepted:
    """A carer types a sentence; a facility system posts structured vitals."""

    def test_prose_vitals_are_extracted(self):
        out = VitalDataInputNode().execute(
            {
                "user_input": "Resident A-12: heart rate 128, SpO2 88, temperature 38.6 "
                "this morning.",
            }
        )
        assert out["status"] == AgentStatus.SUCCESS.value
        assert out["vitals"]["heart_rate"] == 128
        assert out["vitals"]["spo2"] == 88
        assert out["vitals"]["temperature"] == 38.6
        assert out["resident_ref"] == "chat-session"

    def test_structured_caller_still_wins(self):
        out = VitalDataInputNode().execute(
            {
                "input_context": {
                    "vitals": {"heart_rate": 72},
                    "resident_ref": "R-900",
                },
                "user_input": "heart rate 128",
            }
        )
        assert out["vitals"] == {"heart_rate": 72}
        assert out["resident_ref"] == "R-900"

    def test_prose_without_vitals_is_still_rejected(self):
        """No readings must be invented from a sentence that has none."""
        out = VitalDataInputNode().execute({"user_input": "he seems fine today"})
        assert out["status"] == AgentStatus.ERROR.value

    def test_unrelated_numbers_are_not_read_as_vitals(self):
        out = VitalDataInputNode().execute({"user_input": "room 305 needs cleaning"})
        assert out["status"] == AgentStatus.ERROR.value

    def test_prose_values_are_still_range_checked(self):
        """The conversational path does not bypass validation."""
        out = VitalDataInputNode().execute({"user_input": "heart rate 0"})
        assert out["status"] == AgentStatus.ERROR.value


class TestChatReplyIsProse:
    def test_response_is_readable_not_json(self):
        out = ResponseValidateNode().execute(
            {
                "severity": "CRITICAL",
                "dispatched": True,
                "dispatch_channel": "sms",
                "anomalies": [{"metric": "spo2", "value": 88, "deviation_pct": 40}],
            }
        )
        rendered = out["formatted_output"]
        try:
            json.loads(rendered)
        except json.JSONDecodeError:
            pass
        else:
            raise AssertionError("formatted_output parsed as JSON — unreadable in chat")
        assert "CRITICAL" in rendered

    def test_normal_severity_says_so_plainly(self):
        out = ResponseValidateNode().execute({"severity": "NORMAL"})
        assert "normal range" in out["formatted_output"].lower()


class TestReplyIsActionable:
    """A severity label alone is not usable: the reader needs which metric, and what to do."""

    ANOMALIES = [
        {"metric": "spo2", "value": 88, "deviation_pct": 0, "absolute_critical": True},
        {"metric": "heart_rate", "value": 128, "deviation_pct": 18.5, "absolute_critical": False},
    ]

    def test_names_each_abnormal_metric_with_its_value_and_unit(self):
        out = ResponseValidateNode().execute(
            {
                "severity": "CRITICAL",
                "dispatched": True,
                "dispatch_channel": "SMS",
                "anomalies": self.ANOMALIES,
            }
        )
        rendered = out["formatted_output"]
        assert "SpO2" in rendered and "88%" in rendered
        assert "Heart rate" in rendered and "128bpm" in rendered
        assert "absolute safety threshold" in rendered

    def test_states_what_happens_next_when_dispatched(self):
        out = ResponseValidateNode().execute(
            {
                "severity": "CRITICAL",
                "dispatched": True,
                "dispatch_channel": "SMS",
                "anomalies": self.ANOMALIES,
            }
        )
        assert "sent to the registered family contact" in out["formatted_output"]

    def test_critical_without_dispatch_tells_the_carer_to_escalate(self):
        """A failed dispatch must not read as a completed one."""
        out = ResponseValidateNode().execute(
            {
                "severity": "CRITICAL",
                "dispatched": False,
                "dispatch_channel": "",
                "anomalies": self.ANOMALIES,
            }
        )
        assert "escalate" in out["formatted_output"].lower()

    def test_no_resident_identifier_reaches_the_reply(self):
        """APPI Article 17: the opaque resident_ref is not printed either."""
        out = ResponseValidateNode().execute(
            {
                "severity": "CRITICAL",
                "dispatched": True,
                "dispatch_channel": "SMS",
                "resident_ref": "R-SECRET-900",
                "anomalies": self.ANOMALIES,
            }
        )
        assert "R-SECRET-900" not in out["formatted_output"]
