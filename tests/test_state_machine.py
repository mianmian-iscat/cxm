"""test_state_machine.py — 状态机引擎单元测试"""

import os
import sys
import unittest
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.state_machine import StateMachineEngine, StateMachineDefinition, Transition


class TestStateMachineEngine(unittest.TestCase):

    def setUp(self):
        self.engine = StateMachineEngine.from_dict({
            "name": "test_sm",
            "state_machine": {
                "entity": "test_entity",
                "id_field": "id",
                "initial_state": "A",
                "states": ["A", "B", "C", "D"],
                "transitions": [
                    {"from": "A", "to": "B", "trigger": "go_b", "guard": "x == 1"},
                    {"from": "B", "to": "C", "trigger": "go_c"},
                    {"from": "A", "to": "C", "trigger": "direct_c"},
                    {"from": "C", "to": "D", "trigger": "go_d",
                     "side_effects": [{"set": "status = done"}]},
                ],
            },
        })

    def test_valid_transition(self):
        result = self.engine.validate_transition("A", "B", context={"x": 1})
        self.assertTrue(result.valid)
        self.assertEqual(result.from_state, "A")
        self.assertEqual(result.to_state, "B")

    def test_invalid_state(self):
        result = self.engine.validate_transition("X", "B")
        self.assertFalse(result.valid)
        self.assertTrue(any("非法源状态" in e for e in result.errors))

    def test_undefined_transition(self):
        result = self.engine.validate_transition("D", "A")
        self.assertFalse(result.valid)

    def test_guard_not_satisfied(self):
        result = self.engine.validate_transition("A", "B", context={"x": 0})
        self.assertFalse(result.valid)
        self.assertTrue(any("Guard" in e for e in result.errors))

    def test_guard_satisfied(self):
        result = self.engine.validate_transition("A", "B", context={"x": 1})
        self.assertTrue(result.valid)

    def test_no_guard_transition(self):
        result = self.engine.validate_transition("B", "C")
        self.assertTrue(result.valid)

    def test_side_effects_verification(self):
        result = self.engine.validate_transition(
            "C", "D",
            actual_side_effects=["SET: status = done"],
        )
        self.assertTrue(result.valid)

    def test_validate_sequence(self):
        seq = [
            {"from": "A", "to": "B", "context": {"x": 1}},
            {"from": "B", "to": "C"},
            {"from": "C", "to": "D"},
        ]
        results = self.engine.validate_sequence(seq)
        self.assertEqual(len(results), 3)
        self.assertTrue(all(r.valid for r in results))

    def test_sequence_discontinuity(self):
        seq = [
            {"from": "A", "to": "B", "context": {"x": 1}},
            {"from": "C", "to": "D"},  # B→C 缺失
        ]
        results = self.engine.validate_sequence(seq)
        self.assertFalse(results[1].valid)
        self.assertTrue(any("不连续" in e for e in results[1].errors))

    def test_illegal_jump_detection(self):
        """A→D 不是直接转换但 D 可达"""
        # A→D 未定义，但 A→B→C→D 可达
        result = self.engine.validate_transition("A", "D")
        self.assertFalse(result.valid)

    def test_get_legal_transitions(self):
        transitions = self.engine.get_legal_transitions("A")
        self.assertEqual(len(transitions), 2)  # A→B, A→C

    def test_get_all_paths(self):
        paths = self.engine.get_all_paths("A", "D")
        self.assertGreater(len(paths), 0)

    def test_from_yaml(self):
        yaml_content = """
name: yaml_test
state_machine:
  states: [X, Y]
  transitions:
    - from: X
      to: Y
      trigger: test
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()
            engine = StateMachineEngine.from_yaml(f.name)
            self.assertEqual(len(engine.definition.states), 2)
            os.unlink(f.name)


class TestGuardEvaluation(unittest.TestCase):

    def setUp(self):
        self.engine = StateMachineEngine(StateMachineDefinition(
            name="guard_test", states=["A", "B"], transitions=[],
        ))

    def test_simple_equality(self):
        self.assertTrue(self.engine._evaluate_guard("x == 1", {"x": 1}))
        self.assertFalse(self.engine._evaluate_guard("x == 1", {"x": 2}))

    def test_string_equality(self):
        self.assertTrue(self.engine._evaluate_guard('status == "DONE"', {"status": "DONE"}))

    def test_and_condition(self):
        self.assertTrue(self.engine._evaluate_guard(
            "x == 1 AND y == 2", {"x": 1, "y": 2}
        ))
        self.assertFalse(self.engine._evaluate_guard(
            "x == 1 AND y == 2", {"x": 1, "y": 3}
        ))

    def test_or_condition(self):
        self.assertTrue(self.engine._evaluate_guard(
            "x == 1 OR x == 2", {"x": 2}
        ))

    def test_comparison_operators(self):
        self.assertTrue(self.engine._evaluate_guard("x >= 10", {"x": 10}))
        self.assertTrue(self.engine._evaluate_guard("x > 5", {"x": 6}))
        self.assertTrue(self.engine._evaluate_guard("x <= 10", {"x": 10}))
        self.assertTrue(self.engine._evaluate_guard("x < 10", {"x": 9}))
        self.assertTrue(self.engine._evaluate_guard("x != 5", {"x": 3}))

    def test_nested_field(self):
        self.assertTrue(self.engine._evaluate_guard(
            "user.role == admin", {"user": {"role": "admin"}}
        ))

    def test_boolean_field(self):
        self.assertTrue(self.engine._evaluate_guard("active", {"active": True}))
        self.assertFalse(self.engine._evaluate_guard("active", {"active": False}))


if __name__ == "__main__":
    unittest.main()
