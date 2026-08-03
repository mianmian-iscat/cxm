"""
failure_clustering.py — 失败模式聚类与根因分析 (维度11)

对一次执行中的所有失败步骤进行聚类分析，识别系统性问题：
- 按 error_type + selector + URL 分组
- 同类失败超阈值时触发根因分析
- 生成失败模式报告
- 与熔断器联动实现"智能熔断"

使用方式：
    from core.failure_clustering import FailureClusterer
    clusterer = FailureClusterer()
    clusterer.record_failure(step_result, url="https://...")
    report = clusterer.analyze()
    if report.systemic_issue:
        # 系统性问题，建议只跳过同类步骤
"""

import re
import time
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from collections import defaultdict


@dataclass
class FailureCluster:
    """一个失败聚类"""
    cluster_key: str
    error_type: str = ""
    common_pattern: str = ""
    selectors: list = field(default_factory=list)
    urls: list = field(default_factory=list)
    step_indices: list = field(default_factory=list)
    count: int = 0
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    root_cause_hypothesis: str = ""

    def to_dict(self) -> dict:
        return {
            "cluster_key": self.cluster_key,
            "error_type": self.error_type,
            "common_pattern": self.common_pattern,
            "selectors": self.selectors[:5],
            "urls": list(set(self.urls))[:5],
            "count": self.count,
            "step_indices": self.step_indices,
            "root_cause_hypothesis": self.root_cause_hypothesis,
        }


@dataclass
class ClusterReport:
    """聚类分析报告"""
    total_failures: int = 0
    clusters: List[FailureCluster] = field(default_factory=list)
    systemic_issue: bool = False
    dominant_cluster: Optional[str] = None
    suggestion: str = ""

    def to_dict(self) -> dict:
        return {
            "total_failures": self.total_failures,
            "cluster_count": len(self.clusters),
            "systemic_issue": self.systemic_issue,
            "dominant_cluster": self.dominant_cluster,
            "suggestion": self.suggestion,
            "clusters": [c.to_dict() for c in self.clusters],
        }


class FailureClusterer:
    """
    失败模式聚类引擎。

    核心能力：
    1. 对失败步骤按 error_type + selector + URL 聚类
    2. 同类失败超过阈值时触发根因分析
    3. 生成聚类报告 + 修复建议
    4. 支持"智能熔断"（只跳过同类步骤）
    """

    # 触发系统性分析的聚类最小失败数
    SYSTEMIC_THRESHOLD = 3
    # 最大聚类数
    MAX_CLUSTERS = 20

    def __init__(self):
        self._failures: List[dict] = []
        self._clusters: Dict[str, FailureCluster] = {}

    def record_failure(self, step_result: dict, url: str = ""):
        """
        记录一个失败步骤。

        Args:
            step_result: 步骤执行结果 dict
            url: 当前页面 URL
        """
        error_msg = step_result.get("error", "")
        step_type = step_result.get("type", "unknown")
        step_index = step_result.get("index", -1)
        selector = step_result.get("selector", step_result.get("target", ""))

        failure = {
            "error": error_msg,
            "step_type": step_type,
            "step_index": step_index,
            "selector": selector,
            "url": url,
            "timestamp": time.time(),
        }
        self._failures.append(failure)

        # 计算聚类 key
        cluster_key = self._compute_cluster_key(failure)

        if cluster_key not in self._clusters:
            if len(self._clusters) >= self.MAX_CLUSTERS:
                return  # 聚类数超限
            self._clusters[cluster_key] = FailureCluster(
                cluster_key=cluster_key,
                error_type=self._classify_error_type(error_msg),
                common_pattern=error_msg[:100],
            )

        cluster = self._clusters[cluster_key]
        cluster.count += 1
        cluster.step_indices.append(step_index)
        cluster.last_seen = time.time()
        if selector and selector not in cluster.selectors:
            cluster.selectors.append(selector)
        if url and url not in cluster.urls:
            cluster.urls.append(url)

        # 更新 common_pattern（取所有错误消息的最长公共前缀）
        if cluster.count > 1:
            cluster.common_pattern = self._common_prefix(
                cluster.common_pattern, error_msg[:100]
            )

    def should_skip_step_type(self, step_type: str, selector: str = "") -> bool:
        """
        判断是否应跳过某类步骤（智能熔断）。
        当同类失败已超过阈值时，后续同类步骤直接跳过。
        """
        for cluster in self._clusters.values():
            if cluster.count >= self.SYSTEMIC_THRESHOLD:
                # 匹配 step_type
                if any(
                    f.get("step_type") == step_type
                    for f in self._failures
                    if self._compute_cluster_key(f) == cluster.cluster_key
                ):
                    # 如果有 selector，进一步匹配
                    if selector and cluster.selectors:
                        if any(selector in s or s in selector for s in cluster.selectors):
                            return True
                    elif not selector:
                        return True
        return False

    def analyze(self) -> ClusterReport:
        """
        生成聚类分析报告。
        """
        report = ClusterReport(total_failures=len(self._failures))

        # 排序聚类（按 count 降序）
        sorted_clusters = sorted(
            self._clusters.values(), key=lambda c: c.count, reverse=True
        )
        report.clusters = sorted_clusters

        # 根因分析
        for cluster in sorted_clusters:
            cluster.root_cause_hypothesis = self._hypothesize_root_cause(cluster)

        # 检测系统性问题
        if sorted_clusters and sorted_clusters[0].count >= self.SYSTEMIC_THRESHOLD:
            report.systemic_issue = True
            report.dominant_cluster = sorted_clusters[0].cluster_key
            dominant = sorted_clusters[0]

            # 生成建议
            if dominant.error_type == "selector_issue":
                report.suggestion = (
                    f"系统性选择器失效 ({dominant.count} 次)："
                    f"可能是前端发版导致 DOM 结构变化，"
                    f"建议全局选择器刷新或暂停执行"
                )
            elif dominant.error_type == "network_issue":
                report.suggestion = (
                    f"系统性网络异常 ({dominant.count} 次)："
                    f"可能是目标服务不可用，建议等待后重试"
                )
            elif dominant.error_type == "auth_issue":
                report.suggestion = (
                    f"系统性登录态失效 ({dominant.count} 次)："
                    f"需要重新登录或 SSO warmup"
                )
            else:
                report.suggestion = (
                    f"系统性失败 ({dominant.count} 次, 类型 {dominant.error_type})："
                    f"建议检查环境或数据"
                )

        elif len(sorted_clusters) >= 3:
            report.suggestion = (
                f"分散性失败 ({len(sorted_clusters)} 类)："
                f"无明显系统性问题，可能是测试数据不稳定"
            )

        return report

    def get_skippable_step_types(self) -> List[str]:
        """获取当前应跳过的步骤类型列表"""
        skippable = []
        for cluster in self._clusters.values():
            if cluster.count >= self.SYSTEMIC_THRESHOLD:
                for f in self._failures:
                    if self._compute_cluster_key(f) == cluster.cluster_key:
                        stype = f.get("step_type", "")
                        if stype and stype not in skippable:
                            skippable.append(stype)
                        break
        return skippable

    def get_stats(self) -> dict:
        return {
            "total_failures": len(self._failures),
            "cluster_count": len(self._clusters),
            "systemic_clusters": sum(
                1 for c in self._clusters.values()
                if c.count >= self.SYSTEMIC_THRESHOLD
            ),
        }

    # ── 内部 ──

    @staticmethod
    def _compute_cluster_key(failure: dict) -> str:
        """计算聚类 key（error_type + selector 前缀 + step_type）"""
        error_type = FailureClusterer._classify_error_type(failure.get("error", ""))
        selector = failure.get("selector", "")
        step_type = failure.get("step_type", "")

        # selector 取前缀（避免动态后缀影响聚类）
        sel_prefix = ""
        if selector:
            # 取到第一个 class hash 之前
            sel_prefix = re.sub(r'[a-z0-9]{4,}$', '', selector.split('.')[-1] if '.' in selector else selector)

        return f"{error_type}:{step_type}:{sel_prefix[:30]}"

    @staticmethod
    def _classify_error_type(error_msg: str) -> str:
        err_lower = error_msg.lower()
        if any(kw in err_lower for kw in ["selector", "find error", "queryselector", "not found", "未找到"]):
            return "selector_issue"
        if any(kw in err_lower for kw in ["timeout", "超时", "timeouterror"]):
            return "timeout_issue"
        if any(kw in err_lower for kw in ["login", "sso", "登录", "unauthorized", "401"]):
            return "auth_issue"
        if any(kw in err_lower for kw in ["connection", "econnrefused", "network", "fetch"]):
            return "network_issue"
        if any(kw in err_lower for kw in ["assert", "expect", "断言"]):
            return "assertion_issue"
        return "unknown"

    @staticmethod
    def _common_prefix(s1: str, s2: str) -> str:
        """计算两个字符串的最长公共前缀"""
        min_len = min(len(s1), len(s2))
        for i in range(min_len):
            if s1[i] != s2[i]:
                return s1[:i]
        return s1[:min_len]

    @staticmethod
    def _hypothesize_root_cause(cluster: FailureCluster) -> str:
        """为聚类生成根因假设"""
        if cluster.error_type == "selector_issue":
            if cluster.count >= 5:
                return "前端发版导致 DOM 结构变化（选择器大面积失效）"
            if len(cluster.selectors) == 1:
                return f"单一选择器失效: {cluster.selectors[0][:50]}"
            return "多个选择器失效，可能是页面布局变化"

        if cluster.error_type == "timeout_issue":
            if len(cluster.urls) == 1:
                return f"特定页面加载慢: {cluster.urls[0][:60]}"
            return "多页面超时，可能是网络或服务器负载问题"

        if cluster.error_type == "auth_issue":
            return "登录态过期，需要 SSO warmup 或重新登录"

        if cluster.error_type == "network_issue":
            return "网络连通性问题，检查目标服务是否可用"

        if cluster.error_type == "assertion_issue":
            return "业务逻辑变更或测试数据不匹配"

        return "未知根因，建议检查执行日志和截图"
