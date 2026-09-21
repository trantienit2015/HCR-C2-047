# PB — GraphNode outer boundary (Cat 2 blind spot; PB-6 only discovers src/nodes/ FunctionNode
# subclasses, so the outer main-slot GraphNode — the real security boundary that receives the
# caller's first input — needs its own probe here). See test-artifacts.md §PB-6.

from framework.nodes.graph_node import GraphNode
from framework.schemas.trust_level import TrustLevel

from src.nodes.vital_anomaly_graph_node import VitalAnomalyGraphNode
from src.nodes.vital_context_load_node import VitalContextLoadNode


class TestGraphNodeS1TrustGate:
    def test_insufficient_trust_denied_before_execute(self):
        node = VitalAnomalyGraphNode()
        state = {
            "caller_trust_level": TrustLevel.ANONYMOUS.value,
            "validated_input": '{"resident_ref": "R-1", "vitals": {"heart_rate": 72}}',
            "resident_ref": "R-1",
        }
        out = node(state)
        assert str(out.get("status")).lower().endswith("error")
        assert any("trust" in e.lower() for e in out.get("error_log", []))


class TestGraphNodeBoundaryMapping:
    def test_extract_input_only_forwards_validated_payload(self):
        node = VitalAnomalyGraphNode()
        state = {"resident_ref": "R-1", "validated_input": '{"resident_ref": "R-1"}', "user_input": "raw-caller-text"}
        forwarded = node.extract_input(state)
        # Only the validated (pre_process-sanitized) payload crosses the boundary — never the
        # raw caller input directly.
        assert forwarded == state["validated_input"]

    def test_merge_output_maps_fields_explicitly_no_raw_passthrough(self):
        node = VitalAnomalyGraphNode()
        state = {"resident_ref": "R-1"}
        sub_result = {
            "severity": "CRITICAL",
            "anomalies": [{"metric": "spo2", "value": 85}],
            "dispatched": True,
            "dispatch_channel": "sms",
            "notification_draft": "URGENT: ...",
            "status": "success",
            "baseline": {"heart_rate": 70},  # sensitive inner-only field — must NOT leak out
            "contact": {"channel": "sms"},  # sensitive inner-only field — must NOT leak out
        }
        merged = node.merge_output(state, sub_result)
        assert "baseline" not in merged
        assert "contact" not in merged
        assert merged["severity"] == "CRITICAL"
        assert merged["dispatched"] is True
        assert merged["dispatch_channel"] == "sms"


class TestGraphNodeDelegatesGatingToInner:
    def test_inner_entry_node_has_own_s1_gate(self):
        # Design: VitalAnomalyGraphNode.__call__ (framework GraphNode) does not run S-2/S-3
        # content gating on the inner subgraph's own state fields — that is the inner
        # subgraph's own responsibility, enforced per-node at its own S-1 boundary
        # (framework/nodes/graph_node.py delegates subgraph execution to BaseGraph.invoke(),
        # which re-applies each inner node's own BaseNode.__call__ pipeline). Assert the first
        # inner node still declares and enforces its own trust gate.
        assert VitalContextLoadNode.required_trust_level in (
            TrustLevel.ANONYMOUS, TrustLevel.VERIFIED_EXTERNAL, TrustLevel.INTERNAL,
        )
        out = VitalContextLoadNode()({"caller_trust_level": TrustLevel.ANONYMOUS.value, "user_input": ""})
        if VitalContextLoadNode.required_trust_level != TrustLevel.ANONYMOUS:
            assert str(out.get("status")).lower().endswith("error")


def test_graphnode_is_real_graphnode_subclass():
    assert issubclass(VitalAnomalyGraphNode, GraphNode)
