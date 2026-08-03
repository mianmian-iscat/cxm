"""
compliance_checker.py — 合规检查器

原创保护 Harness 合规断言核心：
- 电子签章法律效力校验（签署人身份 + 时间戳 + 防篡改）
- 商家资质有效期校验（营业执照 + 品牌授权书）
- 保护期时效校验（180天 ± 1天容差）
- 数据脱敏校验（身份证号/手机号/银行卡号掩码）

使用方式:
    from core.compliance_checker import ComplianceChecker
    checker = ComplianceChecker()
    result = checker.check_all(case_data)
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

@dataclass
class SignatureInfo:
    """电子签章信息"""
    signer_identity: str = ""       # 签署人身份标识
    sign_time: str = ""             # 签署时间 (ISO 8601)
    document_hash: str = ""         # 文档哈希
    actual_hash: str = ""           # 实际文档哈希（用于防篡改对比）
    timestamp_authority: str = ""   # 时间戳颁发机构
    certificate_valid: bool = True  # 证书是否有效

@dataclass
class MerchantQualification:
    """商家资质"""
    merchant_id: str = ""
    business_license_no: str = ""
    business_license_expiry: str = ""   # ISO 8601
    brand_authorization_no: str = ""
    brand_authorization_expiry: str = ""  # ISO 8601
    qualification_status: str = ""       # VALID / EXPIRED / REVOKED

@dataclass
class ProtectionPeriod:
    """保护期信息"""
    start_date: str = ""           # ISO 8601
    end_date: str = ""             # ISO 8601
    expected_days: int = 180       # 预期天数
    tolerance_days: int = 1        # 容差天数

@dataclass
class SensitiveData:
    """敏感数据样本"""
    field_name: str = ""
    raw_value: str = ""            # 待检查的值（应已脱敏）
    data_type: str = ""            # id_card / phone / bank_card

@dataclass
class ComplianceCaseData:
    """合规检查用例数据"""
    signature: Optional[SignatureInfo] = None
    qualification: Optional[MerchantQualification] = None
    protection_period: Optional[ProtectionPeriod] = None
    sensitive_data_list: list = field(default_factory=list)
    reference_time: str = ""       # 参考时间（ISO 8601），默认当前时间

@dataclass
class ComplianceResult:
    """单项合规检查结果"""
    passed: bool = False
    check_type: str = ""
    check_name: str = ""
    message: str = ""
    severity: str = "ERROR"        # ERROR / WARNING / INFO
    details: dict = field(default_factory=dict)

@dataclass
class ComplianceReport:
    """合规检查综合报告"""
    passed: bool = False
    results: list = field(default_factory=list)
    total_checks: int = 0
    passed_checks: int = 0
    failed_checks: int = 0
    skipped_checks: int = 0
    automation_rate: float = 0.0

    def add_result(self, result: ComplianceResult):
        self.results.append(result)
        self.total_checks += 1
        if result.passed:
            self.passed_checks += 1
        else:
            self.failed_checks += 1
        self.passed = self.failed_checks == 0
        if self.total_checks > 0:
            self.automation_rate = self.passed_checks / self.total_checks

    def to_summary(self) -> dict:
        return {
            "passed": self.passed,
            "total_checks": self.total_checks,
            "passed_checks": self.passed_checks,
            "failed_checks": self.failed_checks,
            "automation_rate": round(self.automation_rate, 2),
            "failures": [
                {"check": r.check_name, "message": r.message}
                for r in self.results if not r.passed
            ],
        }

class ComplianceChecker:
    """
    合规检查器：原创保护专用合规校验引擎。

    覆盖四大合规维度：
    1. 电子签章法律效力
    2. 商家资质有效期
    3. 保护期时效
    4. 数据脱敏
    """

    # ── 电子签章 ──

    def check_signature(self, sig: SignatureInfo) -> list[ComplianceResult]:
        """电子签章法律效力校验"""
        results = []

        # 1. 签署人身份校验
        identity_valid = bool(sig.signer_identity and len(sig.signer_identity) >= 2)
        results.append(ComplianceResult(
            passed=identity_valid,
            check_type="signature",
            check_name="签署人身份校验",
            message="签署人身份标识有效" if identity_valid else "签署人身份标识缺失或无效",
            details={"signer_identity": sig.signer_identity[:4] + "***" if sig.signer_identity else ""},
        ))

        # 2. 签署时间戳有效性
        time_valid = self._validate_timestamp(sig.sign_time)
        results.append(ComplianceResult(
            passed=time_valid,
            check_type="signature",
            check_name="签署时间戳校验",
            message="签署时间戳有效" if time_valid else f"签署时间戳无效或缺失: '{sig.sign_time}'",
            details={"sign_time": sig.sign_time},
        ))

        # 3. 防篡改校验（文档哈希比对）
        if sig.document_hash and sig.actual_hash:
            hash_match = sig.document_hash == sig.actual_hash
            results.append(ComplianceResult(
                passed=hash_match,
                check_type="signature",
                check_name="文档防篡改校验",
                message="文档哈希一致，未被篡改" if hash_match else "文档哈希不一致，可能存在篡改",
                severity="ERROR",
                details={
                    "expected_hash": sig.document_hash[:16] + "...",
                    "actual_hash": sig.actual_hash[:16] + "...",
                },
            ))
        elif sig.document_hash:
            results.append(ComplianceResult(
                passed=False,
                check_type="signature",
                check_name="文档防篡改校验",
                message="缺少实际文档哈希，无法校验防篡改",
                severity="WARNING",
            ))

        # 4. 证书有效性
        results.append(ComplianceResult(
            passed=sig.certificate_valid,
            check_type="signature",
            check_name="签章证书有效性",
            message="签章证书有效" if sig.certificate_valid else "签章证书已失效",
            severity="ERROR",
        ))

        return results

    # ── 商家资质 ──

    def check_qualification(self, qual: MerchantQualification, reference_time: str = "") -> list[ComplianceResult]:
        """商家资质有效期校验"""
        results = []
        ref_time = self._parse_time(reference_time) if reference_time else datetime.now()

        # 1. 资质状态
        status_valid = qual.qualification_status == "VALID"
        results.append(ComplianceResult(
            passed=status_valid,
            check_type="qualification",
            check_name="资质状态校验",
            message=f"资质状态: {qual.qualification_status}" + ("" if status_valid else "，非VALID状态"),
            details={"status": qual.qualification_status},
        ))

        # 2. 营业执照有效期
        if qual.business_license_expiry:
            expiry = self._parse_time(qual.business_license_expiry)
            if expiry:
                bl_valid = expiry > ref_time
                days_remaining = (expiry - ref_time).days
                results.append(ComplianceResult(
                    passed=bl_valid,
                    check_type="qualification",
                    check_name="营业执照有效期",
                    message=(
                        f"营业执照有效（剩余{days_remaining}天）" if bl_valid
                        else f"营业执照已过期（{qual.business_license_expiry}）"
                    ),
                    details={
                        "expiry": qual.business_license_expiry,
                        "days_remaining": days_remaining,
                    },
                ))

        # 3. 品牌授权书有效期
        if qual.brand_authorization_expiry:
            expiry = self._parse_time(qual.brand_authorization_expiry)
            if expiry:
                ba_valid = expiry > ref_time
                days_remaining = (expiry - ref_time).days
                results.append(ComplianceResult(
                    passed=ba_valid,
                    check_type="qualification",
                    check_name="品牌授权书有效期",
                    message=(
                        f"品牌授权书有效（剩余{days_remaining}天）" if ba_valid
                        else f"品牌授权书已过期（{qual.brand_authorization_expiry}）"
                    ),
                    details={
                        "expiry": qual.brand_authorization_expiry,
                        "days_remaining": days_remaining,
                    },
                ))

        return results

    # ── 保护期时效 ──

    def check_protection_period(self, period: ProtectionPeriod) -> list[ComplianceResult]:
        """保护期时效校验（180天 ± 1天容差）"""
        results = []

        start = self._parse_time(period.start_date)
        end = self._parse_time(period.end_date)

        if not start or not end:
            results.append(ComplianceResult(
                passed=False,
                check_type="protection_period",
                check_name="保护期日期解析",
                message=f"无法解析保护期日期: start='{period.start_date}', end='{period.end_date}'",
            ))
            return results

        actual_days = (end - start).days
        expected_days = period.expected_days
        tolerance = period.tolerance_days
        diff = abs(actual_days - expected_days)

        # 1. 保护期天数校验
        days_valid = diff <= tolerance
        results.append(ComplianceResult(
            passed=days_valid,
            check_type="protection_period",
            check_name="保护期天数校验",
            message=(
                f"保护期天数合规: 实际{actual_days}天, 期望{expected_days}天, "
                f"偏差{diff}天 (容差{tolerance}天)"
            ) if days_valid else (
                f"保护期天数不合规: 实际{actual_days}天, 期望{expected_days}天, "
                f"偏差{diff}天 超出容差{tolerance}天"
            ),
            details={
                "actual_days": actual_days,
                "expected_days": expected_days,
                "deviation": diff,
                "tolerance": tolerance,
            },
        ))

        # 2. 保护期是否已过期
        now = datetime.now()
        expired = now > end
        results.append(ComplianceResult(
            passed=not expired,
            check_type="protection_period",
            check_name="保护期是否过期",
            message="保护期内" if not expired else f"保护期已过期（结束于{period.end_date}）",
            severity="WARNING" if expired else "INFO",
            details={"expired": expired, "end_date": period.end_date},
        ))

        return results

    # ── 数据脱敏 ──

    def check_data_masking(self, data_list: list[SensitiveData]) -> list[ComplianceResult]:
        """数据脱敏校验"""
        results = []

        for data in data_list:
            masked = self._is_properly_masked(data.raw_value, data.data_type)
            results.append(ComplianceResult(
                passed=masked,
                check_type="data_masking",
                check_name=f"数据脱敏-{data.field_name}",
                message=(
                    f"{data.field_name} 脱敏合规" if masked
                    else f"{data.field_name} 未正确脱敏 (类型: {data.data_type})"
                ),
                details={
                    "field_name": data.field_name,
                    "data_type": data.data_type,
                    "masked": masked,
                    # 不暴露原始值，只报告是否合规
                },
            ))

        return results

    # ── 综合检查 ──

    def check_all(self, case_data: ComplianceCaseData) -> ComplianceReport:
        """执行所有合规检查，返回综合报告"""
        report = ComplianceReport()

        if case_data.signature:
            for r in self.check_signature(case_data.signature):
                report.add_result(r)

        if case_data.qualification:
            for r in self.check_qualification(case_data.qualification, case_data.reference_time):
                report.add_result(r)

        if case_data.protection_period:
            for r in self.check_protection_period(case_data.protection_period):
                report.add_result(r)

        if case_data.sensitive_data_list:
            for r in self.check_data_masking(case_data.sensitive_data_list):
                report.add_result(r)

        # 如果没有检查项，视为通过
        if report.total_checks == 0:
            report.passed = True

        return report

    # ── 工具方法 ──

    def _validate_timestamp(self, time_str: str) -> bool:
        """校验时间戳是否为有效 ISO 8601 格式"""
        if not time_str:
            return False
        return self._parse_time(time_str) is not None

    def _parse_time(self, time_str: str) -> Optional[datetime]:
        """解析 ISO 8601 时间字符串"""
        if not time_str:
            return None
        for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S.%f"):
            try:
                return datetime.strptime(time_str, fmt)
            except ValueError:
                continue
        # fallback: 替换 Z 为 +00:00
        try:
            return datetime.fromisoformat(time_str.replace("Z", "+00:00"))
        except ValueError:
            return None

    def _is_properly_masked(self, value: str, data_type: str) -> bool:
        """检查值是否已正确脱敏"""
        if not value:
            return False

        if data_type == "id_card":
            # 身份证号: 保留前3后4，中间用*掩码 (如 110***********1234)
            if len(value) < 7:
                return False
            pattern = r"^\d{3}[*xX]{8,12}\d{4}$"
            return bool(re.match(pattern, value))

        elif data_type == "phone":
            # 手机号: 保留前3后4，中间用*掩码 (如 138****1234)
            if len(value) < 7:
                return False
            pattern = r"^\d{3}[*]{3,5}\d{4}$"
            return bool(re.match(pattern, value))

        elif data_type == "bank_card":
            # 银行卡号: 保留后4位，其余用*掩码
            if len(value) < 5:
                return False
            pattern = r"^[*]{8,16}\d{4}$"
            return bool(re.match(pattern, value))

        else:
            # 通用规则: 包含至少一个 * 字符
            return "*" in value
