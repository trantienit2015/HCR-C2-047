# PB-6: Invoke Execution Order Verification
# Verifies BaseNode.__call__() enforces: S-1 trust gate -> S-4 node_start ->
# S-2 _security_gate_input() -> execute() -> S-3 _security_gate_output() ->
# S-4 node_complete, for every concrete node under src/nodes/.
#
# Template adaptation (HCR-C2-047, Cat 2) — scaffold test with one documented
# deviation: GraphNode subclasses are excluded from discovery. VitalAnomalyGraphNode
# wraps the ENTIRE inner anomaly subgraph; invoking it in a single-node order probe
# would interleave every inner node's framework node_start/complete events into the
# spy and can never match the single-node expected order. The inner nodes
# (VitalContextLoad, AnomalyDetect, AnomalySeverityClassify, FamilyNotificationDraft,
# NotificationDispatch) are discovered and order-verified individually below.

import importlib
import inspect
import pkgutil

import pytest


def _discover_node_classes() -> list[type]:
    """Import every module under src/nodes/ and collect concrete BaseNode subclasses."""
    from framework.nodes.base_node import BaseNode
    from framework.nodes.graph_node import GraphNode

    try:
        pkg = importlib.import_module("src.nodes")
    except ImportError:
        return []

    discovered = []
    for _, modname, _ in pkgutil.walk_packages(pkg.__path__, prefix="src.nodes."):
        module = importlib.import_module(modname)
        for attr in vars(module).values():
            if (
                isinstance(attr, type)
                and issubclass(attr, BaseNode)
                and attr is not BaseNode
                and attr.__module__ == modname
                and not inspect.isabstract(attr)
                # Adaptation: subgraph wrappers are out of PB-6 single-node scope.
                and not issubclass(attr, GraphNode)
            ):
                discovered.append(attr)
    return discovered


class TestInvokeOrder:
    """PB-6: __call__ must run S-1 -> node_start -> S-2 -> execute() -> S-3 -> node_complete."""

    def test_call_order_for_every_node(self, monkeypatch):
        node_classes = _discover_node_classes()
        if not node_classes:
            pytest.skip("no concrete BaseNode subclasses found under src/nodes/")

        import framework.nodes.base_node as base_node_module

        if not hasattr(base_node_module, "emit_trace_event"):
            # Legacy local wheel (1.0.0rc1) does not emit S-4 events from __call__;
            # the CI wheel (agenticstar-agentcore==1.0.0) does, and is the gate of record.
            pytest.skip("framework wheel lacks __call__ S-4 emission (rc1) — PB-6 runs on CI wheel 1.0.0")

        failures: list[str] = []
        for node_cls in node_classes:
            order: list[str] = []
            monkeypatch.setattr(
                base_node_module,
                "emit_trace_event",
                lambda event_type, _payload, _state, _o=order: _o.append(f"event:{event_type}"),
            )

            for method_name, label in (
                ("_security_gate_input", "security_gate_input"),
                ("execute", "execute"),
                ("_security_gate_output", "security_gate_output"),
            ):
                original = getattr(node_cls, method_name)

                def spy(self, arg, _o=order, _label=label, _orig=original):
                    _o.append(_label)
                    return _orig(self, arg)

                monkeypatch.setattr(node_cls, method_name, spy)

            instance = node_cls()
            state = {
                "caller_trust_level": node_cls.required_trust_level.value,
                "correlation_id": "pb6-invoke-order-test",
            }
            instance(state)

            expected = [
                "event:node_start",
                "security_gate_input",
                "execute",
                "security_gate_output",
                "event:node_complete",
            ]
            if order != expected:
                failures.append(
                    f"{node_cls.__name__}: invoke order violation.\n" f"expected: {expected}\nactual:   {order}"
                )

        assert not failures, "\n\n".join(failures)
