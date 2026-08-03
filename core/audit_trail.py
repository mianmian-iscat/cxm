"""
audit_trail.py — 审计轨迹

原创保护 Harness 不可篡改审计日志：
- SHA256 checksum 链式哈希（每条记录包含前一条的哈希）
- 记录所有状态变更和资金操作
- 支持审计轨迹查询和导出
- 与 ArtifactManager 集成持久化

使用方式:
    from core.audit_trail import AuditTrail
    trail = AuditTrail(run_id="run-001")
    trail.record_state_transition(entity="patent_application", entity_id="APP_001", ...)
    trail.record_settlement(charge_order_id="CO_001", amount=500.00, ...)
    trail.flush(output_dir="./artifacts/run-001")
"""

import os
import json
import hashlib
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional


@dataclass
class AuditEntry:
    """单条审计记录"""
    audit_id: str = ""
    actor: str = ""
    action: str = ""                    # STATE_TRANSITION / SETTLEMENT / COMPLIANCE_CHECK / ROLLBACK
    entity: str = ""                    # patent_application / charge_order / etc.
    entity_id: str = ""
    from_state: str = ""
    to_state: str = ""
    guard_evaluated: dict = field(default_factory=dict)
    side_effects_executed: list = field(default_factory=list)
    amount: Optional[float] = None
    currency: str = "CNY"
    details: dict = field(default_factory=dict)
    timestamp: str = ""
    prev_checksum: str = ""
    checksum: str = ""

    def compute_checksum(self) -> str:
        """计算本条记录的 SHA256 校验和（含前一条的 checksum）"""
        payload = {
            "audit_id": self.audit_id,
            "actor": self.actor,
            "action": self.action,
            "entity": self.entity,
            "entity_id": self.entity_id,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "guard_evaluated": self.guard_evaluated,
            "side_effects_executed": self.side_effects_executed,
            "amount": self.amount,
            "timestamp": self.timestamp,
            "prev_checksum": self.prev_checksum,
        }
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return f"sha256:{hashlib.sha256(raw.encode('utf-8')).hexdigest()}"


class AuditTrail:
    """
    审计轨迹：不可篡改的链式哈希审计日志。

    每条记录包含前一条的 SHA256 校验和，形成链式结构，
    任何篡改都会导致后续校验和失效。
    """

    def __init__(self, run_id: str = "", actor: str = "harness-exec-engine"):
        self.run_id = run_id
        self.actor = actor
        self._entries: list[AuditEntry] = []
        self._last_checksum: str = "sha256:genesis"
        self._seq: int = 0

    @property
    def entry_count(self) -> int:
        return len(self._entries)

    # ── 记录操作 ──

    def record_state_transition(
        self,
        entity: str,
        entity_id: str,
        from_state: str,
        to_state: str,
        guard_evaluated: dict = None,
        side_effects_executed: list = None,
        details: dict = None,
    ) -> AuditEntry:
        """记录状态转换"""
        entry = self._create_entry(
            action="STATE_TRANSITION",
            entity=entity,
            entity_id=entity_id,
            from_state=from_state,
            to_state=to_state,
            guard_evaluated=guard_evaluated or {},
            side_effects_executed=side_effects_executed or [],
            details=details or {},
        )
        return entry

    def record_settlement(
        self,
        entity_id: str,
        amount: float,
        currency: str = "CNY",
        action: str = "SETTLEMENT",
        details: dict = None,
    ) -> AuditEntry:
        """记录结算/资金操作"""
        entry = self._create_entry(
            action=action,
            entity="charge_order",
            entity_id=entity_id,
            amount=amount,
            currency=currency,
            details=details or {},
        )
        return entry

    def record_compliance_check(
        self,
        entity: str,
        entity_id: str,
        check_name: str,
        passed: bool,
        details: dict = None,
    ) -> AuditEntry:
        """记录合规检查结果"""
        entry = self._create_entry(
            action="COMPLIANCE_CHECK",
            entity=entity,
            entity_id=entity_id,
            details={
                "check_name": check_name,
                "passed": passed,
                **(details or {}),
            },
        )
        return entry

    def record_rollback(
        self,
        entity: str,
        entity_id: str,
        from_state: str,
        to_state: str,
        reason: str = "",
        details: dict = None,
    ) -> AuditEntry:
        """记录回滚操作"""
        entry = self._create_entry(
            action="ROLLBACK",
            entity=entity,
            entity_id=entity_id,
            from_state=from_state,
            to_state=to_state,
            details={
                "reason": reason,
                **(details or {}),
            },
        )
        return entry

    def record_custom(
        self,
        action: str,
        entity: str,
        entity_id: str,
        details: dict = None,
        **kwargs,
    ) -> AuditEntry:
        """记录自定义操作"""
        entry = self._create_entry(
            action=action,
            entity=entity,
            entity_id=entity_id,
            details=details or {},
            **kwargs,
        )
        return entry

    # ── 查询与导出 ──

    def get_entries(
        self,
        action: str = "",
        entity: str = "",
        entity_id: str = "",
        since: str = "",
        until: str = "",
    ) -> list[AuditEntry]:
        """按条件查询审计记录"""
        results = self._entries

        if action:
            results = [e for e in results if e.action == action]
        if entity:
            results = [e for e in results if e.entity == entity]
        if entity_id:
            results = [e for e in results if e.entity_id == entity_id]
        if since:
            results = [e for e in results if e.timestamp >= since]
        if until:
            results = [e for e in results if e.timestamp <= until]

        return results

    def get_state_history(self, entity: str, entity_id: str) -> list[dict]:
        """获取某实体的状态变更历史"""
        entries = self.get_entries(action="STATE_TRANSITION", entity=entity, entity_id=entity_id)
        return [
            {
                "from": e.from_state,
                "to": e.to_state,
                "timestamp": e.timestamp,
                "guard": e.guard_evaluated,
            }
            for e in entries
        ]

    def get_financial_summary(self) -> dict:
        """获取资金操作摘要"""
        settlements = self.get_entries(action="SETTLEMENT")
        total_amount = sum(e.amount or 0 for e in settlements)
        return {
            "total_transactions": len(settlements),
            "total_amount": total_amount,
            "currency": "CNY",
            "transactions": [
                {"entity_id": e.entity_id, "amount": e.amount, "timestamp": e.timestamp}
                for e in settlements
            ],
        }

    # ── 完整性校验 ──

    def verify_integrity(self) -> dict:
        """校验审计日志完整性（链式哈希校验）"""
        if not self._entries:
            return {"valid": True, "entries_checked": 0, "errors": []}

        errors = []
        prev_checksum = "sha256:genesis"

        for i, entry in enumerate(self._entries):
            # 校验 prev_checksum 链路
            if entry.prev_checksum != prev_checksum:
                errors.append(
                    f"条目 {i} 链路断裂: 期望 prev_checksum={prev_checksum}, "
                    f"实际={entry.prev_checksum}"
                )

            # 重新计算 checksum
            expected_checksum = entry.compute_checksum()
            if entry.checksum != expected_checksum:
                errors.append(
                    f"条目 {i} 校验和不匹配: 期望={expected_checksum}, "
                    f"实际={entry.checksum}"
                )

            prev_checksum = entry.checksum

        return {
            "valid": len(errors) == 0,
            "entries_checked": len(self._entries),
            "errors": errors,
        }

    # ── 持久化 ──

    def flush(self, output_dir: str) -> str:
        """将审计日志写入文件"""
        os.makedirs(output_dir, exist_ok=True)
        path = os.path.join(output_dir, "audit_trail.json")

        data = {
            "run_id": self.run_id,
            "total_entries": len(self._entries),
            "integrity": self.verify_integrity(),
            "entries": [asdict(e) for e in self._entries],
        }

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return path

    def to_json(self) -> str:
        """导出为 JSON 字符串"""
        return json.dumps(
            {
                "run_id": self.run_id,
                "total_entries": len(self._entries),
                "entries": [asdict(e) for e in self._entries],
            },
            ensure_ascii=False,
            indent=2,
        )

    # ── 内部方法 ──

    def _create_entry(self, action: str, entity: str, entity_id: str, **kwargs) -> AuditEntry:
        """创建并追加一条审计记录"""
        self._seq += 1
        now = datetime.now().isoformat()

        entry = AuditEntry(
            audit_id=f"aud-{self.run_id}-{self._seq:04d}" if self.run_id else f"aud-{self._seq:04d}",
            actor=self.actor,
            action=action,
            entity=entity,
            entity_id=entity_id,
            from_state=kwargs.get("from_state", ""),
            to_state=kwargs.get("to_state", ""),
            guard_evaluated=kwargs.get("guard_evaluated", {}),
            side_effects_executed=kwargs.get("side_effects_executed", []),
            amount=kwargs.get("amount"),
            currency=kwargs.get("currency", "CNY"),
            details=kwargs.get("details", {}),
            timestamp=now,
            prev_checksum=self._last_checksum,
        )

        entry.checksum = entry.compute_checksum()
        self._last_checksum = entry.checksum
        self._entries.append(entry)

        return entry
