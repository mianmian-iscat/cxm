"""
desensitize_filter.py — 证据脱敏过滤器

安全红线子系统。职责：
- 递归脱敏 dict/list 中的敏感字段
- 内置敏感字段列表 + 正则匹配
- 支持对 EvidenceStore trace 全量脱敏

使用方式：
    from core.desensitize_filter import DesensitizeFilter
    f = DesensitizeFilter()
    safe_data = f.filter_dict(data)
    safe_trace = f.filter_evidence(evidence_trace)
"""

import copy
import re
from typing import Any, Optional, Set

# ── 默认敏感字段 ──

_DEFAULT_SENSITIVE_KEYS = {
    "cookie", "cookies", "token", "accessToken", "access_token",
    "password", "passwd", "secret", "secretKey", "secret_key",
    "apiKey", "api_key", "idCard", "id_card", "idNumber",
    "phone", "mobile", "empId", "emp_id", "empNo",
    "loginCredentials", "authorization", "auth",
    "session", "sessionId", "session_id",
}

# ── 正则模式 ──

_PATTERNS = [
    (re.compile(r'\b\d{17}[\dXx]\b'), "<身份证已脱敏>"),       # 身份证号
    (re.compile(r'\b1[3-9]\d{9}\b'), "<手机号已脱敏>"),        # 手机号
    (re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'),
     "<邮箱已脱敏>"),                                          # 邮箱
    (re.compile(r'(?:bearer|token)\s+[A-Za-z0-9\-_.]{20,}', re.I),
     "<token已脱敏>"),                                         # Bearer token
    (re.compile(r'[A-Za-z0-9+/]{40,}={0,2}'), "<长凭证已脱敏>"),  # Base64 长串
]

class DesensitizeFilter:
    """
    递归脱敏过滤器。
    对 dict/list 结构中的敏感字段值进行替换脱敏。
    """

    def __init__(self, extra_keys: Optional[Set[str]] = None):
        """
        Args:
            extra_keys: 额外的敏感字段名集合（与内置列表合并）
        """
        self._sensitive_keys = _DEFAULT_SENSITIVE_KEYS.copy()
        if extra_keys:
            self._sensitive_keys.update(extra_keys)
        self._stats = {"keys_masked": 0, "patterns_masked": 0}

    # ── 主入口 ──

    def filter_dict(self, data: Any, _depth: int = 0) -> Any:
        """
        递归脱敏。

        Args:
            data: 任意 JSON 可序列化数据

        Returns:
            脱敏后的副本（深拷贝）
        """
        if _depth > 20:
            return data  # 防止无限递归

        if isinstance(data, dict):
            result = {}
            for key, value in data.items():
                if self._is_sensitive_key(key):
                    result[key] = self._mask_value(value)
                    self._stats["keys_masked"] += 1
                else:
                    result[key] = self.filter_dict(value, _depth + 1)
            return result

        elif isinstance(data, list):
            return [self.filter_dict(item, _depth + 1) for item in data]

        elif isinstance(data, str):
            return self._apply_patterns(data)

        return data

    def filter_evidence(self, evidence_trace: dict) -> dict:
        """
        对 EvidenceStore 的完整 trace 进行脱敏。

        Args:
            evidence_trace: EvidenceStore.to_trace() 的输出

        Returns:
            脱敏后的 trace dict
        """
        return self.filter_dict(evidence_trace)

    # ── 内部方法 ──

    def _is_sensitive_key(self, key: str) -> bool:
        """检查字段名是否敏感"""
        key_lower = key.lower()
        for sk in self._sensitive_keys:
            if sk.lower() == key_lower:
                return True
        return False

    def _mask_value(self, value: Any) -> Any:
        """脱敏值（保留类型信息但隐藏内容）"""
        if value is None:
            return None
        if isinstance(value, str):
            if len(value) > 10:
                return f"<{value[:4]}...已脱敏>"
            return "<已脱敏>"
        if isinstance(value, list):
            return f"<list:{len(value)}项,已脱敏>"
        if isinstance(value, dict):
            return f"<dict:{len(value)}键,已脱敏>"
        return "<已脱敏>"

    def _apply_patterns(self, text: str) -> str:
        """对字符串应用正则脱敏"""
        result = text
        for pattern, replacement in _PATTERNS:
            new_result, count = pattern.subn(replacement, result)
            if count > 0:
                self._stats["patterns_masked"] += count
                result = new_result
        return result

    # ── 统计 ──

    def get_stats(self) -> dict:
        """返回脱敏统计"""
        return dict(self._stats)

    def reset_stats(self):
        """重置统计"""
        self._stats = {"keys_masked": 0, "patterns_masked": 0}
