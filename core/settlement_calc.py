"""
settlement_calc.py — 结算计算器

原创保护 Harness 结算断言核心：
- 效果对赌公式精确计算（维权下架率 × 服务费）
- 权益扣除原子性校验（扣费 + 状态更新事务一致性）
- 退款金额边界值校验（0%/70%/100% 三档）
- 小数精度校验（Decimal，精确到分，无浮点误差）

使用方式:
    from core.settlement_calc import SettlementCalculator
    calc = SettlementCalculator()
    result = calc.verify_effect_gamble(case_data)
"""

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

@dataclass
class EnforcementResults:
    """维权执行结果"""
    total_count: int = 0
    takedown_count: int = 0

    @property
    def takedown_rate(self) -> Decimal:
        if self.total_count == 0:
            return Decimal("0")
        return Decimal(str(self.takedown_count)) / Decimal(str(self.total_count))

@dataclass
class ContractInfo:
    """合同/服务信息"""
    service_fee: Decimal = Decimal("0")
    merchant_id: str = ""
    contract_no: str = ""

@dataclass
class SettlementRecord:
    """结算记录"""
    amount: Decimal = Decimal("0")
    status: str = ""  # PENDING / SETTLED / REFUNDED
    settlement_no: str = ""

@dataclass
class ChargeRecord:
    """权益扣费记录"""
    charge_order_id: str = ""
    amount: Decimal = Decimal("0")
    status: str = ""  # PENDING / DEDUCTED / REFUNDED / FAILED

@dataclass
class CaseData:
    """测试用例数据（结算相关）"""
    case_id: str = ""
    enforcement_results: EnforcementResults = field(default_factory=EnforcementResults)
    contract: ContractInfo = field(default_factory=ContractInfo)
    settlement_record: SettlementRecord = field(default_factory=SettlementRecord)
    charge_record: ChargeRecord = field(default_factory=ChargeRecord)
    application_state: str = ""  # 关联的专利申请状态
    to_regular_status: str = ""  # 转普通申请状态

@dataclass
class SettlementResult:
    """结算校验结果"""
    passed: bool = False
    check_type: str = ""
    expected: str = ""
    actual: str = ""
    deviation: Optional[Decimal] = None
    message: str = ""
    details: dict = field(default_factory=dict)

class SettlementCalculator:
    """
    结算计算器：原创保护专用金额校验引擎。

    使用 Decimal 精确计算，避免浮点误差。
    """

    # 精度：精确到分
    CENT = Decimal("0.01")

    # 效果对赌阈值
    GAMBLE_THRESHOLD_HIGH = Decimal("0.70")  # 下架率 ≥ 70% → 全额确收
    GAMBLE_THRESHOLD_LOW = Decimal("0.30")   # 下架率 < 30% → 全额退款

    def verify_effect_gamble(self, case: CaseData) -> SettlementResult:
        """
        效果对赌结算校验。
        
        规则:
        - 维权下架率 ≥ 70% → 全额确收（结算金额 = 服务费）
        - 维权下架率 30%~70% → 按比例结算（结算金额 = 服务费 × 下架率 / 0.70）
        - 维权下架率 < 30% → 全额退款（结算金额 = 0）
        """
        rate = case.enforcement_results.takedown_rate
        service_fee = case.contract.service_fee

        # 计算期望结算金额
        if rate >= self.GAMBLE_THRESHOLD_HIGH:
            expected = service_fee
        elif rate >= self.GAMBLE_THRESHOLD_LOW:
            expected = (service_fee * rate / self.GAMBLE_THRESHOLD_HIGH).quantize(
                self.CENT, rounding=ROUND_HALF_UP
            )
        else:
            expected = Decimal("0")

        actual = case.settlement_record.amount
        deviation = abs(expected - actual)

        passed = deviation < self.CENT
        return SettlementResult(
            passed=passed,
            check_type="effect_gamble",
            expected=str(expected),
            actual=str(actual),
            deviation=deviation,
            message=(
                f"效果对赌校验{'通过' if passed else '失败'}: "
                f"下架率={rate:.2%}, 服务费={service_fee}, "
                f"期望结算={expected}, 实际结算={actual}"
            ),
            details={
                "takedown_rate": float(rate),
                "takedown_count": case.enforcement_results.takedown_count,
                "total_count": case.enforcement_results.total_count,
                "service_fee": str(service_fee),
                "threshold_high": str(self.GAMBLE_THRESHOLD_HIGH),
                "threshold_low": str(self.GAMBLE_THRESHOLD_LOW),
            },
        )

    def verify_atomic_deduction(
        self,
        charge_record: ChargeRecord,
        application_state: str,
        to_regular_status: str,
    ) -> SettlementResult:
        """
        权益扣除原子性校验。
        
        扣费和状态更新必须同时成功或同时失败，不允许中间态。
        """
        errors = []

        if charge_record.status == "DEDUCTED":
            if to_regular_status != "DONE":
                errors.append(
                    f"权益已扣除(DEDUCTED)但 to_regular_status='{to_regular_status}'，"
                    f"期望 'DONE'，事务不一致"
                )
        elif charge_record.status == "REFUNDED":
            if to_regular_status not in ("TODO", "TIMEOUT"):
                errors.append(
                    f"权益已退款(REFUNDED)但 to_regular_status='{to_regular_status}'，"
                    f"期望 'TODO' 或 'TIMEOUT'"
                )
        elif charge_record.status == "PENDING":
            if to_regular_status == "DONE":
                errors.append(
                    "权益尚未扣除(PENDING)但状态已更新为DONE，事务不一致"
                )
        elif charge_record.status == "FAILED":
            if to_regular_status == "DONE":
                errors.append(
                    "权益扣除失败(FAILED)但状态已更新为DONE，事务不一致"
                )

        passed = len(errors) == 0
        return SettlementResult(
            passed=passed,
            check_type="atomic_deduction",
            expected="扣费与状态更新一致",
            actual=f"charge={charge_record.status}, to_regular={to_regular_status}",
            message="; ".join(errors) if errors else "原子性校验通过",
            details={
                "charge_status": charge_record.status,
                "application_state": application_state,
                "to_regular_status": to_regular_status,
            },
        )

    def verify_refund_boundary(
        self,
        takedown_rate: float,
        expected_refund: Decimal,
        actual_refund: Decimal,
    ) -> SettlementResult:
        """
        退款金额边界值校验。
        
        三档边界:
        - 下架率 = 0% → 全额退款
        - 下架率 = 70% → 临界点（全额确收 vs 按比例）
        - 下架率 = 100% → 全额确收
        """
        rate = Decimal(str(takedown_rate))
        deviation = abs(expected_refund - actual_refund)
        passed = deviation < self.CENT

        boundary_info = {
            "takedown_rate": float(rate),
            "boundary_zone": self._classify_boundary(rate),
        }

        return SettlementResult(
            passed=passed,
            check_type="refund_boundary",
            expected=str(expected_refund),
            actual=str(actual_refund),
            deviation=deviation,
            message=(
                f"边界值校验{'通过' if passed else '失败'}: "
                f"下架率={rate:.2%}, 期望退款={expected_refund}, 实际退款={actual_refund}"
            ),
            details=boundary_info,
        )

    def verify_precision(self, amount: Decimal, expected: Decimal) -> SettlementResult:
        """
        小数精度校验：确保金额精确到分，无浮点误差。
        """
        deviation = abs(amount - expected)
        passed = deviation < self.CENT

        actual_places = max(0, -amount.as_tuple().exponent)
        expected_places = max(0, -expected.as_tuple().exponent)

        return SettlementResult(
            passed=passed,
            check_type="precision",
            expected=str(expected),
            actual=str(amount),
            deviation=deviation,
            message=(
                f"精度校验{'通过' if passed else '失败'}: "
                f"金额={amount}({actual_places}位小数), "
                f"期望={expected}({expected_places}位小数)"
            ),
            details={
                "actual_decimal_places": actual_places,
                "expected_decimal_places": expected_places,
            },
        )

    def calculate_settlement(
        self,
        service_fee: Decimal,
        takedown_count: int,
        total_count: int,
    ) -> Decimal:
        """
        纯计算：根据服务费和下架数据计算应结金额。
        
        可用于构造期望值。
        """
        if total_count == 0:
            return Decimal("0")

        rate = Decimal(str(takedown_count)) / Decimal(str(total_count))

        if rate >= self.GAMBLE_THRESHOLD_HIGH:
            return service_fee
        elif rate >= self.GAMBLE_THRESHOLD_LOW:
            return (service_fee * rate / self.GAMBLE_THRESHOLD_HIGH).quantize(
                self.CENT, rounding=ROUND_HALF_UP
            )
        else:
            return Decimal("0")

    def _classify_boundary(self, rate: Decimal) -> str:
        """分类边界区间"""
        if rate == Decimal("0"):
            return "zero_takedown"
        elif rate < self.GAMBLE_THRESHOLD_LOW:
            return "below_30_percent"
        elif rate == self.GAMBLE_THRESHOLD_LOW:
            return "boundary_30_percent"
        elif rate < self.GAMBLE_THRESHOLD_HIGH:
            return "between_30_70_percent"
        elif rate == self.GAMBLE_THRESHOLD_HIGH:
            return "boundary_70_percent"
        elif rate < Decimal("1"):
            return "above_70_percent"
        else:
            return "full_takedown"
