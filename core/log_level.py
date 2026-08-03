"""
log_level.py — 日志级别常量与过滤函数

提供 DEBUG/INFO/WARNING/ERROR 四级日志过滤，
MetricsLogger 在 flush 时根据 min_level 决定哪些条目写入全局日志。

使用方式：
    from core.log_level import LogLevel, passes_filter

    passes_filter("INFO", "WARNING")  # False
    passes_filter("ERROR", "WARNING") # True
"""

import os
from typing import Optional


class LogLevel:
    """日志级别常量，与 Python logging 数值对齐"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


# 级别数值映射（越高越严重）
_LEVEL_VALUES = {
    LogLevel.DEBUG: 10,
    LogLevel.INFO: 20,
    LogLevel.WARNING: 30,
    LogLevel.ERROR: 40,
}

# 默认最小级别（可通过环境变量覆盖）
_DEFAULT_MIN_LEVEL = LogLevel.INFO


def get_min_level_from_env() -> str:
    """从环境变量 WEB_AUTO_LOG_LEVEL 读取最小日志级别，不存在时返回默认值"""
    env_val = os.environ.get("WEB_AUTO_LOG_LEVEL", "").upper()
    if env_val in _LEVEL_VALUES:
        return env_val
    return _DEFAULT_MIN_LEVEL


def passes_filter(entry_level: str, min_level: str) -> bool:
    """判断 entry_level 是否满足 min_level 过滤条件

    Args:
        entry_level: 日志条目的级别（DEBUG/INFO/WARNING/ERROR）
        min_level: 最小输出级别

    Returns:
        True 表示该条目应被输出，False 表示应被过滤
    """
    entry_val = _LEVEL_VALUES.get(entry_level, 0)
    min_val = _LEVEL_VALUES.get(min_level, 0)
    return entry_val >= min_val


def validate_level(level: str) -> str:
    """校验级别字符串是否合法，不合法时返回 INFO"""
    if level in _LEVEL_VALUES:
        return level
    return LogLevel.INFO
