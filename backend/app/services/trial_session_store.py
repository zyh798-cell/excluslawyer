# -*- coding: utf-8 -*-
"""模拟法庭会话持久化：data/trial_sessions/{session_id}.json。

每次 start/step 后落盘完整快照（含案情、主张、证据、辩论、裁判），
前端刷新/服务重启后可经 GET /api/trial/session/{id} 完整恢复；
配合 SqliteSaver checkpointer 实现跨重启的中断恢复。
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

_SAFE_ID = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")


class TrialSessionStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, session_id: str) -> Path:
        if not _SAFE_ID.match(session_id or ""):
            raise ValueError(f"非法会话 ID: {session_id!r}")
        return self.root / f"{session_id}.json"

    def save(self, record: dict) -> None:
        """原子写快照（tmp + replace）。"""
        session_id = str(record.get("session_id", ""))
        path = self._path(session_id)
        payload = {"updated_at": time.strftime("%Y-%m-%d %H:%M:%S"), "record": record}
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    def load(self, session_id: str) -> dict | None:
        path = self._path(session_id)
        if not path.exists():
            return None
        try:
            blob = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        return blob.get("record")

    def exists(self, session_id: str) -> bool:
        try:
            return self._path(session_id).exists()
        except ValueError:
            return False

    def list_ids(self) -> list[str]:
        return sorted(p.stem for p in self.root.glob("*.json"))
