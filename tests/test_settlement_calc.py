"""test_settlement_calc.py — 结算计算器单元测试"""

import os
import sys
import unittest
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.settlement_calc import (
    SettlementCalculator, CaseData, EnforcementResults,
    ContractInfo, SettlementRecord, ChargeRecord,
)


class TestEffectGamble(unittest.TestCase):

    def setUp(self):
        self.calc = SettlementCalculator()

    def test_full_takedown_full_settlement(self):
        """下架率 ≥ 70% → 全额确收"""
        case = CaseData(
            enforcement_results=EnforcementResults(total_count=100, takedown_count=85),
            contract=ContractInfo(service_fee=Decimal("2000")),
            settlement_record=SettlementRecord(amount=Decimal("2000")),
        )
        result = self.calc.verify_effect_gamble(case)
        self.assertTrue(result.passed)

    def test_partial_takedown_proportional(self):
        """下架率 30%-70% → 按比例结算"""
        case = CaseData(
            enforcement_results=EnforcementResults(total_count=100, takedown_count=45),
            contract=ContractInfo(service_fee=Decimal("1500")),
            settlement_record=SettlementRecord(amount=Decimal("964.29")),
        )
        result = self.calc.verify_effect_gamble(case)
        self.assertTrue(result.passed)

    def test_low_takedown_full_refund(self):
        """下架率 < 30% → 全额退款"""
        case = CaseData(
            enforcement_results=EnforcementResults(total_count=100, takedown_count=20),
            contract=ContractInfo(service_fee=Decimal("3000")),
            settlement_record=SettlementRecord(amount=Decimal("0")),
        )
        result = self.calc.verify_effect_gamble(case)
        self.assertTrue(result.passed)

    def test_zero_takedown(self):
        """0% 下架率"""
        case = CaseData(
            enforcement_results=EnforcementResults(total_count=50, takedown_count=0),
            contract=ContractInfo(service_fee=Decimal("1000")),
            settlement_record=SettlementRecord(amount=Decimal("0")),
        )
        result = self.calc.verify_effect_gamble(case)
        self.assertTrue(result.passed)

    def test_deviation_detected(self):
        """金额偏差不超过1分钱"""
        case = CaseData(
            enforcement_results=EnforcementResults(total_count=100, takedown_count=85),
            contract=ContractInfo(service_fee=Decimal("1500")),
            settlement_record=SettlementRecord(amount=Decimal("1499.98")),
        )
        result = self.calc.verify_effect_gamble(case)
        self.assertFalse(result.passed)
        self.assertIsNotNone(result.deviation)


class TestAtomicDeduction(unittest.TestCase):

    def setUp(self):
        self.calc = SettlementCalculator()

    def test_deducted_and_done(self):
        """扣费成功 + 状态DONE → 一致"""
        result = self.calc.verify_atomic_deduction(
            ChargeRecord(status="DEDUCTED"), "FIRST_EXAM_IN_PROGRESS", "DONE"
        )
        self.assertTrue(result.passed)

    def test_deducted_but_not_done(self):
        """扣费成功但状态非DONE → 不一致"""
        result = self.calc.verify_atomic_deduction(
            ChargeRecord(status="DEDUCTED"), "PRE_EXAM_REJECTED", "TODO"
        )
        self.assertFalse(result.passed)

    def test_refunded_with_todo(self):
        """退款 + TODO → 合法"""
        result = self.calc.verify_atomic_deduction(
            ChargeRecord(status="REFUNDED"), "PRE_EXAM_REJECTED", "TODO"
        )
        self.assertTrue(result.passed)

    def test_refunded_with_done(self):
        """退款但状态DONE → 异常"""
        result = self.calc.verify_atomic_deduction(
            ChargeRecord(status="REFUNDED"), "FIRST_EXAM_IN_PROGRESS", "DONE"
        )
        self.assertFalse(result.passed)


class TestPrecision(unittest.TestCase):

    def setUp(self):
        self.calc = SettlementCalculator()

    def test_exact_precision(self):
        result = self.calc.verify_precision(Decimal("964.29"), Decimal("964.29"))
        self.assertTrue(result.passed)

    def test_sub_cent_deviation(self):
        result = self.calc.verify_precision(Decimal("964.295"), Decimal("964.29"))
        self.assertTrue(result.passed)  # 偏差 < 0.01

    def test_over_cent_deviation(self):
        result = self.calc.verify_precision(Decimal("964.30"), Decimal("964.29"))
        self.assertFalse(result.passed)


class TestCalculateSettlement(unittest.TestCase):

    def setUp(self):
        self.calc = SettlementCalculator()

    def test_high_rate(self):
        amount = self.calc.calculate_settlement(Decimal("2000"), 80, 100)
        self.assertEqual(amount, Decimal("2000"))

    def test_mid_rate(self):
        amount = self.calc.calculate_settlement(Decimal("2000"), 50, 100)
        self.assertEqual(amount, Decimal("1428.57"))

    def test_low_rate(self):
        amount = self.calc.calculate_settlement(Decimal("2000"), 10, 100)
        self.assertEqual(amount, Decimal("0"))

    def test_zero_total(self):
        amount = self.calc.calculate_settlement(Decimal("2000"), 0, 0)
        self.assertEqual(amount, Decimal("0"))


if __name__ == "__main__":
    unittest.main()
