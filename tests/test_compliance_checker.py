"""test_compliance_checker.py — 合规检查器单元测试"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.compliance_checker import (
    ComplianceChecker, ComplianceCaseData, SignatureInfo,
    MerchantQualification, ProtectionPeriod, SensitiveData,
)


class TestSignatureCheck(unittest.TestCase):

    def setUp(self):
        self.checker = ComplianceChecker()

    def test_valid_signature(self):
        sig = SignatureInfo(
            signer_identity="张三(ID:12345)",
            sign_time="2026-07-01T10:00:00",
            document_hash="abc123",
            actual_hash="abc123",
            certificate_valid=True,
        )
        results = self.checker.check_signature(sig)
        self.assertTrue(all(r.passed for r in results))

    def test_tampered_document(self):
        sig = SignatureInfo(
            signer_identity="张三(ID:12345)",
            sign_time="2026-07-01T10:00:00",
            document_hash="abc123",
            actual_hash="xyz789",
            certificate_valid=True,
        )
        results = self.checker.check_signature(sig)
        tamper_check = [r for r in results if r.check_name == "文档防篡改校验"]
        self.assertFalse(tamper_check[0].passed)

    def test_missing_identity(self):
        sig = SignatureInfo(sign_time="2026-07-01T10:00:00", certificate_valid=True)
        results = self.checker.check_signature(sig)
        identity_check = [r for r in results if r.check_name == "签署人身份校验"]
        self.assertFalse(identity_check[0].passed)


class TestQualificationCheck(unittest.TestCase):

    def setUp(self):
        self.checker = ComplianceChecker()

    def test_valid_qualification(self):
        qual = MerchantQualification(
            merchant_id="M001",
            business_license_expiry="2027-12-31",
            brand_authorization_expiry="2027-06-30",
            qualification_status="VALID",
        )
        results = self.checker.check_qualification(qual, reference_time="2026-07-01")
        self.assertTrue(all(r.passed for r in results))

    def test_expired_license(self):
        qual = MerchantQualification(
            business_license_expiry="2025-01-01",
            qualification_status="VALID",
        )
        results = self.checker.check_qualification(qual, reference_time="2026-07-01")
        bl_check = [r for r in results if r.check_name == "营业执照有效期"]
        self.assertFalse(bl_check[0].passed)

    def test_invalid_status(self):
        qual = MerchantQualification(qualification_status="REVOKED")
        results = self.checker.check_qualification(qual)
        status_check = [r for r in results if r.check_name == "资质状态校验"]
        self.assertFalse(status_check[0].passed)


class TestProtectionPeriod(unittest.TestCase):

    def setUp(self):
        self.checker = ComplianceChecker()

    def test_valid_period(self):
        period = ProtectionPeriod(
            start_date="2026-01-01",
            end_date="2026-06-30",
            expected_days=180,
            tolerance_days=1,
        )
        results = self.checker.check_protection_period(period)
        days_check = [r for r in results if r.check_name == "保护期天数校验"]
        self.assertTrue(days_check[0].passed)

    def test_deviation_exceeds_tolerance(self):
        period = ProtectionPeriod(
            start_date="2026-01-01",
            end_date="2026-05-01",
            expected_days=180,
            tolerance_days=1,
        )
        results = self.checker.check_protection_period(period)
        days_check = [r for r in results if r.check_name == "保护期天数校验"]
        self.assertFalse(days_check[0].passed)


class TestDataMasking(unittest.TestCase):

    def setUp(self):
        self.checker = ComplianceChecker()

    def test_masked_id_card(self):
        data = [SensitiveData(field_name="身份证", raw_value="110***********1234", data_type="id_card")]
        results = self.checker.check_data_masking(data)
        self.assertTrue(results[0].passed)

    def test_unmasked_phone(self):
        data = [SensitiveData(field_name="手机号", raw_value="13812345678", data_type="phone")]
        results = self.checker.check_data_masking(data)
        self.assertFalse(results[0].passed)

    def test_masked_phone(self):
        data = [SensitiveData(field_name="手机号", raw_value="138****5678", data_type="phone")]
        results = self.checker.check_data_masking(data)
        self.assertTrue(results[0].passed)

    def test_masked_bank_card(self):
        data = [SensitiveData(field_name="银行卡", raw_value="************1234", data_type="bank_card")]
        results = self.checker.check_data_masking(data)
        self.assertTrue(results[0].passed)


class TestCheckAll(unittest.TestCase):

    def setUp(self):
        self.checker = ComplianceChecker()

    def test_empty_case(self):
        case = ComplianceCaseData()
        report = self.checker.check_all(case)
        self.assertEqual(report.total_checks, 0)
        self.assertTrue(report.passed)


if __name__ == "__main__":
    unittest.main()
