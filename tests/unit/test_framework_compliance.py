# HCR-C2-047 - Framework compliance tests TC-01..TC-08.
# Reference shape: another template tests/unit/test_framework_compliance.py, adapted
# to this template's real architecture (Cat 2: outer pre/post + GraphNode-wrapped inner nodes).

import os
import re
import typing

import pytest
from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_state import AgentState
from framework.schemas.agent_status import AgentStatus
from framework.schemas.invocation_context import InvocationContext
from framework.schemas.trust_level import TrustLevel

from src.nodes import (
    anomaly_detect_node,
    anomaly_severity_classify_node,
    family_notification_draft_node,
    notification_dispatch_node,
    response_validate_node,
    vital_anomaly_graph_node,
    vital_context_load_node,
    vital_data_input_node,
)
from src.schemas.state import State

_SRC = os.path.join(os.path.dirname(__file__), "..", "..", "src")
TRUST = TrustLevel.INTERNAL.value

VITALS_OK = {"heart_rate": 72, "bp_systolic": 118, "spo2": 98, "temperature": 36.6, "respiration": 16}


def _src_files():
    for root, _d, files in os.walk(_SRC):
        for f in files:
            if f.endswith(".py"):
                yield os.path.join(root, f)


def _unwrap(ann):
    if typing.get_origin(ann) is typing.NotRequired:
        return typing.get_args(ann)[0]
    return ann


# TC-01 - State is a flat TypedDict extending AgentState; agent fields are NotRequired primitives.
class TestTC01StateContract:
    def test_state_is_typeddict_extending_agent_state(self):
        assert hasattr(State, "__annotations__")
        assert "user_input" in State.__annotations__
        assert set(AgentState.__annotations__).issubset(set(State.__annotations__))

    def test_added_fields_are_primitives(self):
        added = [k for k in State.__annotations__ if k not in AgentState.__annotations__]
        assert added, "State must declare agent-specific fields"
        allowed = {"str", "int", "bool", "float", "dict", "list"}
        for name in added:
            ann = State.__annotations__[name]
            unwrapped = _unwrap(ann)
            ann_str = getattr(unwrapped, "__name__", str(unwrapped))
            assert ann_str in allowed, f"{name}: {ann_str} - must be a JSON-serializable primitive"


# TC-02 - Empty/missing input yields a fail-closed ERROR outcome, no raise.
class TestTC02Validation:
    def test_empty_vitals_no_raise(self):
        node = vital_data_input_node.VitalDataInputNode()
        out = node.execute({"input_context": {}})
        assert out["status"] == AgentStatus.ERROR.value
        assert out["error_log"]

    def test_invalid_metric_value_no_raise(self):
        node = vital_data_input_node.VitalDataInputNode()
        out = node.execute({"input_context": {"vitals": {"heart_rate": -1}, "resident_ref": "R-1"}})
        assert out["status"] == AgentStatus.ERROR.value
        assert out["error_log"]

    def test_inner_context_load_empty_vitals_no_raise(self):
        node = vital_context_load_node.VitalContextLoadNode()
        out = node.execute({"user_input": ""})
        assert out["status"] == AgentStatus.ERROR.value
        assert out["error_log"]


# TC-03 - No JWT / API keys / secrets in src/; no direct os.environ reads.
class TestTC03NoCredentials:
    def test_no_credential_literals(self):
        pat = re.compile(r"(sk-[A-Za-z0-9]{16,}|AKIA[0-9A-Z]{16}|eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)")
        offenders = []
        for fp in _src_files():
            with open(fp, encoding="utf-8") as f:
                if pat.search(f.read()):
                    offenders.append(fp)
        assert offenders == []

    def test_no_os_environ_secret_reads(self):
        pat = re.compile(r"os\.environ(\[|\.get\()")
        offenders = []
        for fp in _src_files():
            with open(fp, encoding="utf-8") as f:
                content = f.read()
                if pat.search(content) and "server.py" not in fp:
                    offenders.append(fp)
        assert offenders == []


# TC-04 - InvocationContext is never stored in State after invoke.
class TestTC04ContextIsolation:
    def test_no_invocationcontext_in_state_after_invoke(self):
        from src.graph.graph import Graph

        def _baseline_provider(resident_ref):
            return {"baseline": {"heart_rate": 70, "spo2": 98}, "contact": {"channel": "sms"}}

        agent = Graph(config={"max_retry": 1, "baseline_provider": _baseline_provider})
        agent.compile()
        ctx = InvocationContext(session_id="tc04", caller_trust_level=TrustLevel.INTERNAL, caller_id="facility-tc04")
        result = agent.invoke("", ctx=ctx, input_context={"resident_ref": "R-1", "vitals": VITALS_OK})
        for v in result.values():
            assert not isinstance(v, InvocationContext)

    def test_from_state_available(self):
        assert hasattr(InvocationContext, "from_state")


# TC-05 - Domain events: every node emits >=1 domain event; no node under
# src/nodes/ ever re-emits a framework backbone lifecycle event.
class TestTC05Audit:
    def test_vital_data_input_emits_domain_event(self, monkeypatch):
        events = []
        monkeypatch.setattr(vital_data_input_node, "emit_trace_event", lambda e, p, s: events.append(e))
        out = vital_data_input_node.VitalDataInputNode().execute(
            {"input_context": {"vitals": VITALS_OK, "resident_ref": "R-1"}}
        )
        assert out["status"] == AgentStatus.SUCCESS.value
        assert "vital_input_validated" in events
        assert not ({"node_start", "node_complete", "node_error", "node_skip"} & set(events))

    def test_vital_data_input_emits_on_reject_path(self, monkeypatch):
        events = []
        monkeypatch.setattr(vital_data_input_node, "emit_trace_event", lambda e, p, s: events.append(e))
        out = vital_data_input_node.VitalDataInputNode().execute({"input_context": {}})
        assert out["status"] == AgentStatus.ERROR.value
        assert "vital_input_rejected" in events

    def test_source_has_no_backbone_events(self):
        pat = re.compile(r'emit_trace_event\(\s*["\'](node_start|node_complete|node_error|node_skip)["\']')
        offenders = []
        for fp in _src_files():
            with open(fp, encoding="utf-8") as f:
                if pat.search(f.read()):
                    offenders.append(fp)
        assert offenders == []


# TC-06 / TC-07 - S-2/S-3 gates are @final on FunctionNode (overriding raises TypeError at class def).
class TestTC0607FinalGates:
    def test_input_gate_is_final(self):
        with pytest.raises(TypeError):

            class BadIn(FunctionNode):  # noqa: N801
                def _security_gate_input(self, state):
                    return state

    def test_output_gate_is_final(self):
        with pytest.raises(TypeError):

            class BadOut(FunctionNode):  # noqa: N801
                def _security_gate_output(self, result):
                    return result

    def test_output_gate_blocks_credentials(self):
        # Built-in @final S-3 credential scan fires even without a node-specific
        # _extra_security_gate_output hook (none is defined in this template).
        node = response_validate_node.ResponseValidateNode()
        with pytest.raises(Exception):
            node._security_gate_output({"formatted_output": "token AKIAIOSFODNN7EXAMPLE leaked"})


# TC-08 - required_trust_level enforced: insufficient trust -> ERROR state, no raise.
class TestTC08TrustGate:
    def test_declared_trust_levels_valid(self):
        for cls in (
            vital_data_input_node.VitalDataInputNode,
            vital_anomaly_graph_node.VitalAnomalyGraphNode,
            vital_context_load_node.VitalContextLoadNode,
            anomaly_detect_node.AnomalyDetectNode,
            anomaly_severity_classify_node.AnomalySeverityClassifyNode,
            family_notification_draft_node.FamilyNotificationDraftNode,
            notification_dispatch_node.NotificationDispatchNode,
            response_validate_node.ResponseValidateNode,
        ):
            assert cls.required_trust_level in (TrustLevel.ANONYMOUS, TrustLevel.VERIFIED_EXTERNAL, TrustLevel.INTERNAL)

    def test_insufficient_trust_returns_error(self):
        node = vital_data_input_node.VitalDataInputNode()
        out = node({"caller_trust_level": TrustLevel.ANONYMOUS.value, "input_context": {"vitals": VITALS_OK, "resident_ref": "R-1"}})
        assert str(out.get("status")).lower().endswith("error")

    def test_sufficient_trust_succeeds(self):
        node = vital_data_input_node.VitalDataInputNode()
        out = node({"caller_trust_level": TRUST, "input_context": {"vitals": VITALS_OK, "resident_ref": "R-1"}})
        assert out["status"] == AgentStatus.SUCCESS.value
        assert out["resident_ref"] == "R-1"
