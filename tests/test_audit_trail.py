"""test_audit_trail.py — 审计轨迹单元测试"""

import os
import sys
import json
import unittest
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.audit_trail import AuditTrail


class TestAuditTrail(unittest.TestCase):

    def setUp(self):
        self.trail = AuditTrail(run_id="test-run-001")

    def test_record_state_transition(self):
        entry = self.trail.record_state_transition(
            entity="patent_application",
            entity_id="APP_001",
            from_state="SUBMITTED",
            to_state="PRE_EXAM_PASSED",
            guard_evaluated={"material_complete": True},
        )
        self.assertEqual(entry.action, "STATE_TRANSITION")
        self.assertEqual(entry.from_state, "SUBMITTED")
        self.assertEqual(entry.to_state, "PRE_EXAM_PASSED")
        self.assertTrue(entry.checksum.startswith("sha256:"))

    def test_record_settlement(self):
        entry = self.trail.record_settlement(
            entity_id="CO_001",
            amount=500.00,
            action="SETTLEMENT",
        )
        self.assertEqual(entry.amount, 500.00)
        self.assertEqual(entry.action, "SETTLEMENT")

    def test_chain_integrity(self):
        self.trail.record_state_transition("app", "A1", "S1", "S2")
        self.trail.record_settlement("CO1", 100.0)
        self.trail.record_state_transition("app", "A1", "S2", "S3")

        verification = self.trail.verify_integrity()
        self.assertTrue(verification["valid"])
        self.assertEqual(verification["entries_checked"], 3)

    def test_prev_checksum_linkage(self):
        e1 = self.trail.record_state_transition("app", "A1", "S1", "S2")
        e2 = self.trail.record_state_transition("app", "A1", "S2", "S3")

        self.assertEqual(e2.prev_checksum, e1.checksum)

    def test_query_by_action(self):
        self.trail.record_state_transition("app", "A1", "S1", "S2")
        self.trail.record_settlement("CO1", 100.0)
        self.trail.record_state_transition("app", "A1", "S2", "S3")

        transitions = self.trail.get_entries(action="STATE_TRANSITION")
        self.assertEqual(len(transitions), 2)

        settlements = self.trail.get_entries(action="SETTLEMENT")
        self.assertEqual(len(settlements), 1)

    def test_query_by_entity(self):
        self.trail.record_state_transition("app", "A1", "S1", "S2")
        self.trail.record_state_transition("order", "O1", "P", "D")

        app_entries = self.trail.get_entries(entity="app")
        self.assertEqual(len(app_entries), 1)

    def test_get_state_history(self):
        self.trail.record_state_transition("app", "A1", "S1", "S2")
        self.trail.record_state_transition("app", "A1", "S2", "S3")

        history = self.trail.get_state_history("app", "A1")
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["from"], "S1")
        self.assertEqual(history[1]["to"], "S3")

    def test_financial_summary(self):
        self.trail.record_settlement("CO1", 500.0)
        self.trail.record_settlement("CO2", 300.0)

        summary = self.trail.get_financial_summary()
        self.assertEqual(summary["total_transactions"], 2)
        self.assertEqual(summary["total_amount"], 800.0)

    def test_flush_to_file(self):
        self.trail.record_state_transition("app", "A1", "S1", "S2")

        with tempfile.TemporaryDirectory() as tmpdir:
            path = self.trail.flush(tmpdir)
            self.assertTrue(os.path.exists(path))
            with open(path) as f:
                data = json.load(f)
            self.assertEqual(data["total_entries"], 1)
            self.assertTrue(data["integrity"]["valid"])

    def test_to_json(self):
        self.trail.record_settlement("CO1", 100.0)
        json_str = self.trail.to_json()
        data = json.loads(json_str)
        self.assertEqual(data["total_entries"], 1)

    def test_record_compliance_check(self):
        entry = self.trail.record_compliance_check(
            entity="patent_application",
            entity_id="APP_001",
            check_name="签章验证",
            passed=True,
        )
        self.assertEqual(entry.action, "COMPLIANCE_CHECK")

    def test_record_rollback(self):
        entry = self.trail.record_rollback(
            entity="patent_application",
            entity_id="APP_001",
            from_state="FIRST_EXAM_IN_PROGRESS",
            to_state="PRE_EXAM_REJECTED",
            reason="测试数据清理",
        )
        self.assertEqual(entry.action, "ROLLBACK")

    def test_entry_count(self):
        self.assertEqual(self.trail.entry_count, 0)
        self.trail.record_settlement("CO1", 100.0)
        self.assertEqual(self.trail.entry_count, 1)


if __name__ == "__main__":
    unittest.main()
