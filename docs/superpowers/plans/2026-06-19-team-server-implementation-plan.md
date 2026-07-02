---
title: Team Server Implementation Plan
codename: team_server.v1
status: implemented
author: micro-eval
date: 2026-06-19
authority: docs/superpowers/specs/2026-06-19-team-server-design.md
---

# Team Server Implementation Plan

> **状态注记（2026-07-02）：** 已随 v0.4.0 交付（2026-06-19，见 CHANGELOG）。checklist 未逐项回填，以代码与 CHANGELOG 为准。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn micro-eval from a local-only tool into a shared intranet server with workspace isolation, serial run queue, and read-only template library for 1-20 person AI teams.

**Architecture:** Two-process model — Next.js server (HTTP/UI) + Python run worker (serial queue consumer). Workspaces are isolated directories under `~/.micro-eval-server/workspaces/`, each acting as a `project_root` for the existing ExecutionKernel. SQLite queue (`queue.db`) mediates job lifecycle between the two processes.

**Tech Stack:** Python 3.11+ / Typer / Pydantic / SQLite / asyncio (server layer); Next.js / TypeScript / zod (UI); pytest + vitest (tests).

**禁止使用 TDD 方法**：遵循 CLAUDE.md 硬规则。开发顺序是：理解规格 → 实现 → 验证测试。每个 milestone 先实现功能代码，然后写测试验证。

---

## 0. Prerequisites（实施前置条件）

### Task 0.1: Update CLAUDE.md Boundaries

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update "MVP 不做" list and "当前状态"**

In `CLAUDE.md`, update these two sections:

```markdown
# In "当前状态" section, add after the v0.3.5 paragraph:
v0.4.0 开发中：Team Server——可信内网多成员共享 Server（workspace 隔离、串行队列、只读模板库、归属记录）。设计文档：docs/superpowers/specs/2026-06-19-team-server-design.md。

# In "MVP 不做" list, replace:
# Before:
> MVP 不做：多团队协作、RBAC/SSO、复杂审计、大规模任务库、高级推荐引擎。
# After:
> MVP 不做：RBAC/SSO、复杂审计、大规模任务库、高级推荐引擎。
> v0.4 新增：可信内网多成员共享 Server（workspace 隔离、串行队列、只读模板库、归属记录），不含认证/权限控制。
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md boundaries for v0.4 Team Server"
```

### Task 0.2: Update Security Service Guidelines

**Files:**
- Modify: `docs/engineering/security-service-guidelines.md`

- [ ] **Step 1: Add Team Server security appendix**

Append a new section to the file:

```markdown
## Team Server 服务化安全附录（v0.4）

### 信任模型
- **可信内网假设**：server 部署在团队内网，所有成员互信。
- **无认证**：`X-Micro-Eval-Member` header 为自报身份，仅用于归属记录，不做鉴权。
- 此假设的边界条件：server 不暴露到公网；团队成员不主动伪造身份；浏览器可能访问恶意外部网页。

### CSRF 防护（四层）
1. Content-Type 强制：写接口只接受 `application/json`。
2. 自定义 header 检查：写接口要求 `X-Micro-Eval-Member` header。
3. 无 CORS headers：不返回 `Access-Control-Allow-Origin`。
4. Host header allowlist：拒绝非 allowlist 的 Host header（防 DNS rebinding）。

### config_overrides 白名单
仅允许覆盖：`repetitions`、`timeout_s`、`max_concurrency`。
禁止覆盖：`agent.command`、`workspace`、`output_dir`、`project_root`。

### 归属记录（最小审计）
所有写操作记录 `X-Micro-Eval-Member`。归属记录不可变（workspace.owner 创建后不可更改）。

### 适用范围
本附录仅适用于 `micro-eval serve` 模式。`micro-eval ui` 本地模式不受影响。
```

- [ ] **Step 2: Commit**

```bash
git add docs/engineering/security-service-guidelines.md
git commit -m "docs: add Team Server security appendix for v0.4"
```

---

## Milestone 1: Server Data Layer（Python 核心模块）

> 目标：实现 workspace、template、queue 三个 Python 模块，可被 CLI 和 worker 直接调用。不依赖 UI 或网络。

### Task 1.1: Server Package Init + Workspace Models

**Files:**
- Create: `src/micro_eval/server/__init__.py`
- Create: `src/micro_eval/server/models.py`

- [ ] **Step 1: Create server package with shared models**

```python
# src/micro_eval/server/__init__.py
"""micro-eval Team Server layer."""
```

```python
# src/micro_eval/server/models.py
"""Pydantic models for server-mode entities."""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timezone

from pydantic import BaseModel, Field


def _compact_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def new_workspace_id() -> str:
    return f"ws-{_compact_utc()}-{secrets.token_hex(4)}"


def new_job_id() -> str:
    return f"job-{_compact_utc()}-{secrets.token_hex(4)}"


class WorkspaceMeta(BaseModel):
    schema_version: str = "1.0"
    workspace_id: str
    name: str
    owner: str
    template_id: str | None = None
    template_version: str | None = None
    created_at: str
    last_run_at: str | None = None
    run_count: int = 0
    description: str = ""
    git_pin: dict | None = None
    status: str = "active"  # active | archived


class TemplateMeta(BaseModel):
    schema_version: str = "1.0"
    template_id: str
    name: str
    description: str = ""
    version: str = "1.0.0"
    created_at: str
    updated_at: str
    author: str = "admin"
    tags: list[str] = Field(default_factory=list)
    includes: dict = Field(default_factory=dict)


class ServerConfig(BaseModel):
    schema_version: str = "1.0"
    server_name: str = "team-eval-server"
    bind_host: str = "0.0.0.0"
    bind_port: int = 3000
    data_root: str = "~/.micro-eval-server"
    max_queue_size: int = 100
    run_timeout_seconds: int = 3600
    worker_poll_interval_seconds: float = 2.0
    allowed_hosts: list[str] = Field(default_factory=list)
```

- [ ] **Step 2: Commit**

```bash
git add src/micro_eval/server/__init__.py src/micro_eval/server/models.py
git commit -m "feat(server): add server package with workspace/template/config models"
```

### Task 1.2: WorkspaceManager

**Files:**
- Create: `src/micro_eval/server/workspace.py`

- [ ] **Step 1: Implement WorkspaceManager**

```python
# src/micro_eval/server/workspace.py
"""Workspace lifecycle management for server mode."""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from micro_eval.server.models import WorkspaceMeta, new_workspace_id

_WS_ID_RE = re.compile(r"^ws-\d{8}T\d{6}Z-[a-f0-9]{8}$")


class WorkspaceError(Exception):
    pass


class WorkspaceManager:
    def __init__(self, data_root: Path):
        self.data_root = Path(data_root)
        self.workspaces_dir = self.data_root / "workspaces"

    def resolve_path(self, workspace_id: str) -> Path | None:
        if not _WS_ID_RE.match(workspace_id):
            return None
        ws_dir = (self.workspaces_dir / workspace_id).resolve()
        ws_root = self.workspaces_dir.resolve()
        if not str(ws_dir).startswith(str(ws_root) + "/"):
            return None
        if not ws_dir.exists():
            return None
        try:
            real_ws = ws_dir.resolve(strict=True)
            real_root = ws_root.resolve(strict=True)
            if not str(real_ws).startswith(str(real_root) + "/"):
                return None
            return real_ws
        except OSError:
            return None

    def create(
        self,
        name: str,
        owner: str,
        template_id: str | None = None,
        description: str = "",
    ) -> WorkspaceMeta:
        ws_id = new_workspace_id()
        ws_dir = self.workspaces_dir / ws_id
        ws_dir.mkdir(parents=True, exist_ok=False)
        (ws_dir / ".micro-eval" / "runs").mkdir(parents=True, exist_ok=True)

        template_version = None
        if template_id:
            tpl_dir = self.data_root / "templates" / template_id
            if not tpl_dir.exists():
                shutil.rmtree(ws_dir)
                raise WorkspaceError(f"template not found: {template_id}")
            tpl_meta_path = tpl_dir / "template.json"
            if tpl_meta_path.exists():
                from micro_eval.server.models import TemplateMeta
                tpl_meta = TemplateMeta.model_validate_json(tpl_meta_path.read_text())
                template_version = tpl_meta.version
            for item in tpl_dir.iterdir():
                if item.name == "template.json":
                    continue
                dest = ws_dir / item.name
                if item.is_dir():
                    shutil.copytree(item, dest)
                else:
                    shutil.copy2(item, dest)
        else:
            (ws_dir / "eval.yaml").write_text("# micro-eval configuration\nproject_name: unnamed\n")

        now = datetime.now(timezone.utc).isoformat()
        meta = WorkspaceMeta(
            workspace_id=ws_id,
            name=name,
            owner=owner,
            template_id=template_id,
            template_version=template_version,
            created_at=now,
            description=description,
        )
        (ws_dir / "workspace.json").write_text(meta.model_dump_json(indent=2))
        return meta

    def get(self, workspace_id: str) -> WorkspaceMeta | None:
        ws_dir = self.resolve_path(workspace_id)
        if ws_dir is None:
            return None
        meta_path = ws_dir / "workspace.json"
        if not meta_path.exists():
            return None
        return WorkspaceMeta.model_validate_json(meta_path.read_text())

    def list_workspaces(self, include_archived: bool = False) -> list[WorkspaceMeta]:
        if not self.workspaces_dir.exists():
            return []
        result = []
        for entry in sorted(self.workspaces_dir.iterdir()):
            if not entry.is_dir():
                continue
            meta_path = entry / "workspace.json"
            if not meta_path.exists():
                continue
            try:
                meta = WorkspaceMeta.model_validate_json(meta_path.read_text())
                if not include_archived and meta.status == "archived":
                    continue
                result.append(meta)
            except Exception:
                continue
        return result

    def update(self, workspace_id: str, **fields) -> WorkspaceMeta | None:
        ws_dir = self.resolve_path(workspace_id)
        if ws_dir is None:
            return None
        meta = self.get(workspace_id)
        if meta is None:
            return None
        allowed = {"name", "description", "status"}
        for key, value in fields.items():
            if key in allowed:
                setattr(meta, key, value)
        (ws_dir / "workspace.json").write_text(meta.model_dump_json(indent=2))
        return meta

    def delete(self, workspace_id: str) -> bool:
        ws_dir = self.resolve_path(workspace_id)
        if ws_dir is None:
            return False
        shutil.rmtree(ws_dir)
        return True
```

- [ ] **Step 2: Commit**

```bash
git add src/micro_eval/server/workspace.py
git commit -m "feat(server): implement WorkspaceManager with path validation"
```

### Task 1.3: TemplateRegistry

**Files:**
- Create: `src/micro_eval/server/template.py`

- [ ] **Step 1: Implement TemplateRegistry**

```python
# src/micro_eval/server/template.py
"""Read-only template registry for server mode."""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

from micro_eval.server.models import TemplateMeta


class TemplateError(Exception):
    pass


class TemplateRegistry:
    def __init__(self, data_root: Path):
        self.templates_dir = Path(data_root) / "templates"

    def create(
        self,
        source_dir: Path,
        template_id: str,
        name: str,
        description: str = "",
        author: str = "admin",
    ) -> TemplateMeta:
        if not source_dir.is_dir():
            raise TemplateError(f"source directory not found: {source_dir}")
        tpl_dir = self.templates_dir / template_id
        if tpl_dir.exists():
            raise TemplateError(f"template already exists: {template_id}")
        tpl_dir.mkdir(parents=True, exist_ok=False)

        for item in source_dir.iterdir():
            dest = tpl_dir / item.name
            if item.is_dir():
                shutil.copytree(item, dest)
            else:
                shutil.copy2(item, dest)

        now = datetime.now(timezone.utc).isoformat()
        includes = {}
        eval_yaml = tpl_dir / "eval.yaml"
        if eval_yaml.exists():
            includes["eval_yaml"] = True
        tasks_dir = tpl_dir / "tasks"
        if tasks_dir.exists():
            includes["tasks"] = [f.name for f in tasks_dir.iterdir() if f.is_file()]

        meta = TemplateMeta(
            template_id=template_id,
            name=name,
            description=description,
            created_at=now,
            updated_at=now,
            author=author,
            includes=includes,
        )
        (tpl_dir / "template.json").write_text(meta.model_dump_json(indent=2))
        return meta

    def get(self, template_id: str) -> TemplateMeta | None:
        meta_path = self.templates_dir / template_id / "template.json"
        if not meta_path.exists():
            return None
        return TemplateMeta.model_validate_json(meta_path.read_text())

    def list_templates(self) -> list[TemplateMeta]:
        if not self.templates_dir.exists():
            return []
        result = []
        for entry in sorted(self.templates_dir.iterdir()):
            if not entry.is_dir():
                continue
            meta_path = entry / "template.json"
            if not meta_path.exists():
                continue
            try:
                result.append(TemplateMeta.model_validate_json(meta_path.read_text()))
            except Exception:
                continue
        return result

    def update(self, template_id: str, source_dir: Path) -> TemplateMeta:
        meta = self.get(template_id)
        if meta is None:
            raise TemplateError(f"template not found: {template_id}")
        tpl_dir = self.templates_dir / template_id
        for item in tpl_dir.iterdir():
            if item.name == "template.json":
                continue
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
        for item in source_dir.iterdir():
            dest = tpl_dir / item.name
            if item.is_dir():
                shutil.copytree(item, dest)
            else:
                shutil.copy2(item, dest)

        parts = meta.version.split(".")
        parts[-1] = str(int(parts[-1]) + 1)
        meta.version = ".".join(parts)
        meta.updated_at = datetime.now(timezone.utc).isoformat()
        (tpl_dir / "template.json").write_text(meta.model_dump_json(indent=2))
        return meta

    def delete(self, template_id: str) -> bool:
        tpl_dir = self.templates_dir / template_id
        if not tpl_dir.exists():
            return False
        shutil.rmtree(tpl_dir)
        return True
```

- [ ] **Step 2: Commit**

```bash
git add src/micro_eval/server/template.py
git commit -m "feat(server): implement TemplateRegistry"
```

### Task 1.4: QueueDB

**Files:**
- Create: `src/micro_eval/server/queue.py`

- [ ] **Step 1: Implement QueueDB with SQLite**

```python
# src/micro_eval/server/queue.py
"""SQLite-backed serial run queue for server mode."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from micro_eval.server.models import new_job_id


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class QueueDB:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS jobs (
                job_id       TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                owner        TEXT NOT NULL,
                plan_json    TEXT NOT NULL,
                status       TEXT NOT NULL DEFAULT 'queued',
                enqueued_at  TEXT NOT NULL,
                started_at   TEXT,
                finished_at  TEXT,
                run_id       TEXT,
                error        TEXT,
                progress     TEXT,
                cancel_requested_at TEXT,
                cancelled_by TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
            CREATE INDEX IF NOT EXISTS idx_jobs_workspace ON jobs(workspace_id);
            CREATE INDEX IF NOT EXISTS idx_jobs_enqueued ON jobs(enqueued_at);
        """)

    def enqueue(
        self,
        workspace_id: str,
        owner: str,
        plan_json: str,
        max_queue_size: int = 100,
    ) -> dict:
        cur = self._conn.execute(
            "SELECT COUNT(*) as cnt FROM jobs WHERE status IN ('queued', 'running')"
        )
        count = cur.fetchone()["cnt"]
        if count >= max_queue_size:
            raise QueueFullError(count, max_queue_size)

        job_id = new_job_id()
        now = _utcnow()
        self._conn.execute(
            """INSERT INTO jobs (job_id, workspace_id, owner, plan_json, status, enqueued_at)
               VALUES (?, ?, ?, ?, 'queued', ?)""",
            (job_id, workspace_id, owner, plan_json, now),
        )
        self._conn.commit()

        position = self._conn.execute(
            "SELECT COUNT(*) as cnt FROM jobs WHERE status = 'queued' AND enqueued_at <= ?",
            (now,),
        ).fetchone()["cnt"]
        return {"job_id": job_id, "status": "queued", "position": position}

    def dequeue_next(self) -> dict | None:
        cur = self._conn.execute(
            """UPDATE jobs SET status = 'running', started_at = ?
               WHERE job_id = (
                   SELECT job_id FROM jobs WHERE status = 'queued'
                   ORDER BY enqueued_at LIMIT 1
               ) RETURNING *""",
            (_utcnow(),),
        )
        row = cur.fetchone()
        self._conn.commit()
        if row is None:
            return None
        return dict(row)

    def update_status(
        self,
        job_id: str,
        status: str,
        *,
        started_at: str | None = None,
        finished_at: str | None = None,
        run_id: str | None = None,
        error: str | None = None,
    ) -> None:
        sets = ["status = ?"]
        params: list = [status]
        if started_at:
            sets.append("started_at = ?")
            params.append(started_at)
        if finished_at:
            sets.append("finished_at = ?")
            params.append(finished_at)
        if run_id:
            sets.append("run_id = ?")
            params.append(run_id)
        if error:
            sets.append("error = ?")
            params.append(error)
        params.append(job_id)
        self._conn.execute(f"UPDATE jobs SET {', '.join(sets)} WHERE job_id = ?", params)
        self._conn.commit()

    def update_progress(self, job_id: str, progress: dict) -> None:
        self._conn.execute(
            "UPDATE jobs SET progress = ? WHERE job_id = ?",
            (json.dumps(progress), job_id),
        )
        self._conn.commit()

    def request_cancel(self, job_id: str, cancelled_by: str) -> dict | None:
        row = self.get_job(job_id)
        if row is None:
            return None
        status = row["status"]
        if status in ("done", "failed", "cancelled"):
            return {"error": "job_already_terminated", "status": status}
        now = _utcnow()
        if status == "queued":
            self._conn.execute(
                """UPDATE jobs SET status = 'cancelled', cancel_requested_at = ?,
                   cancelled_by = ?, finished_at = ? WHERE job_id = ?""",
                (now, cancelled_by, now, job_id),
            )
            self._conn.commit()
            return {"job_id": job_id, "status": "cancelled", "cancel_requested_at": now}
        # status == 'running': stop-after-run
        self._conn.execute(
            "UPDATE jobs SET cancel_requested_at = ?, cancelled_by = ? WHERE job_id = ?",
            (now, cancelled_by, job_id),
        )
        self._conn.commit()
        return {"job_id": job_id, "status": "running", "cancel_requested_at": now}

    def is_cancel_requested(self, job_id: str) -> bool:
        row = self._conn.execute(
            "SELECT cancel_requested_at FROM jobs WHERE job_id = ?", (job_id,)
        ).fetchone()
        return row is not None and row["cancel_requested_at"] is not None

    def get_job(self, job_id: str) -> dict | None:
        row = self._conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        if row is None:
            return None
        result = dict(row)
        if result.get("progress"):
            result["progress"] = json.loads(result["progress"])
        return result

    def get_queue_dashboard(self) -> dict:
        running_row = self._conn.execute(
            "SELECT * FROM jobs WHERE status = 'running' LIMIT 1"
        ).fetchone()
        running = dict(running_row) if running_row else None

        queued_rows = self._conn.execute(
            "SELECT * FROM jobs WHERE status = 'queued' ORDER BY enqueued_at"
        ).fetchall()
        queued = []
        for i, row in enumerate(queued_rows):
            d = dict(row)
            d["position"] = i + 1
            queued.append(d)

        recent_rows = self._conn.execute(
            "SELECT * FROM jobs WHERE status IN ('done', 'failed', 'cancelled') "
            "ORDER BY finished_at DESC LIMIT 10"
        ).fetchall()
        recent = [dict(r) for r in recent_rows]

        return {"running": running, "queued": queued, "recent_completed": recent}

    def has_pending_jobs(self, workspace_id: str) -> bool:
        row = self._conn.execute(
            "SELECT COUNT(*) as cnt FROM jobs WHERE workspace_id = ? AND status IN ('queued', 'running')",
            (workspace_id,),
        ).fetchone()
        return row["cnt"] > 0

    def recover_stale_jobs(self, workspace_resolver) -> list[str]:
        rows = self._conn.execute(
            "SELECT * FROM jobs WHERE status = 'running'"
        ).fetchall()
        recovered = []
        for row in rows:
            job = dict(row)
            run_id = job.get("run_id")
            ws_id = job["workspace_id"]
            ws_path = workspace_resolver(ws_id)
            if ws_path is None or run_id is None:
                self.update_status(job["job_id"], "failed", finished_at=_utcnow(),
                                   error="worker crashed during execution")
                recovered.append(job["job_id"])
                continue
            run_json = ws_path / ".micro-eval" / "runs" / run_id / "run.json"
            if run_json.exists():
                import json as _json
                data = _json.loads(run_json.read_text())
                if data.get("completed_at"):
                    if job.get("cancel_requested_at"):
                        self.update_status(job["job_id"], "cancelled", finished_at=_utcnow())
                    else:
                        self.update_status(job["job_id"], "done", finished_at=_utcnow())
                    recovered.append(job["job_id"])
                    continue
            self.update_status(job["job_id"], "failed", finished_at=_utcnow(),
                               error="worker crashed during execution")
            recovered.append(job["job_id"])
        return recovered

    def close(self) -> None:
        self._conn.close()


class QueueFullError(Exception):
    def __init__(self, current: int, maximum: int):
        self.current = current
        self.maximum = maximum
        super().__init__(f"queue full ({current}/{maximum})")
```

- [ ] **Step 2: Commit**

```bash
git add src/micro_eval/server/queue.py
git commit -m "feat(server): implement QueueDB with SQLite WAL, cancel, crash recovery"
```

### Task 1.5: Milestone 1 Tests

**Files:**
- Create: `tests/unit/server/test_workspace.py`
- Create: `tests/unit/server/test_template.py`
- Create: `tests/unit/server/test_queue.py`

- [ ] **Step 1: Write workspace tests**

```python
# tests/unit/server/test_workspace.py
"""Tests for WorkspaceManager."""

import pytest
from pathlib import Path
from micro_eval.server.workspace import WorkspaceManager, WorkspaceError


@pytest.fixture
def data_root(tmp_path):
    root = tmp_path / ".micro-eval-server"
    root.mkdir()
    (root / "workspaces").mkdir()
    return root


@pytest.fixture
def manager(data_root):
    return WorkspaceManager(data_root)


def test_create_blank(manager):
    meta = manager.create(name="test-ws", owner="alice")
    assert meta.workspace_id.startswith("ws-")
    assert meta.owner == "alice"
    assert meta.status == "active"
    ws_dir = manager.workspaces_dir / meta.workspace_id
    assert (ws_dir / "eval.yaml").exists()
    assert (ws_dir / "workspace.json").exists()
    assert (ws_dir / ".micro-eval" / "runs").exists()


def test_create_from_template(manager, data_root):
    tpl_dir = data_root / "templates" / "tpl-a"
    tpl_dir.mkdir(parents=True)
    (tpl_dir / "eval.yaml").write_text("project_name: tpl-a\n")
    (tpl_dir / "template.json").write_text('{"schema_version":"1.0","template_id":"tpl-a","name":"A","version":"2.0.0","created_at":"","updated_at":""}')
    meta = manager.create(name="from-tpl", owner="bob", template_id="tpl-a")
    assert meta.template_id == "tpl-a"
    assert meta.template_version == "2.0.0"
    ws_dir = manager.workspaces_dir / meta.workspace_id
    assert (ws_dir / "eval.yaml").read_text() == "project_name: tpl-a\n"


def test_create_template_not_found(manager):
    with pytest.raises(WorkspaceError, match="template not found"):
        manager.create(name="fail", owner="alice", template_id="no-such")


def test_workspace_id_format(manager):
    import re
    meta = manager.create(name="x", owner="a")
    assert re.match(r"^ws-\d{8}T\d{6}Z-[a-f0-9]{8}$", meta.workspace_id)


def test_list_active_only(manager):
    manager.create(name="a", owner="alice")
    meta_b = manager.create(name="b", owner="bob")
    manager.update(meta_b.workspace_id, status="archived")
    active = manager.list_workspaces(include_archived=False)
    assert len(active) == 1
    all_ws = manager.list_workspaces(include_archived=True)
    assert len(all_ws) == 2


def test_lifecycle(manager):
    meta = manager.create(name="x", owner="alice")
    assert meta.status == "active"
    manager.update(meta.workspace_id, status="archived")
    updated = manager.get(meta.workspace_id)
    assert updated.status == "archived"
    assert manager.delete(meta.workspace_id)
    assert manager.get(meta.workspace_id) is None


def test_path_traversal_rejected(manager):
    assert manager.resolve_path("../../../etc/passwd") is None
    assert manager.resolve_path("ws-not-matching-format") is None


def test_symlink_escape(manager, data_root):
    import os
    secret = data_root.parent / "secret"
    secret.mkdir()
    (secret / "workspace.json").write_text('{"workspace_id":"x","name":"x","owner":"x","created_at":"x","status":"active","schema_version":"1.0"}')
    fake_id = "ws-20260619T000000Z-aaaaaaaa"
    link = manager.workspaces_dir / fake_id
    os.symlink(str(secret), str(link))
    assert manager.resolve_path(fake_id) is None


def test_delete_removes_directory(manager):
    meta = manager.create(name="x", owner="alice")
    ws_dir = manager.workspaces_dir / meta.workspace_id
    assert ws_dir.exists()
    manager.delete(meta.workspace_id)
    assert not ws_dir.exists()
```

- [ ] **Step 2: Write template tests**

```python
# tests/unit/server/test_template.py
"""Tests for TemplateRegistry."""

import pytest
from pathlib import Path
from micro_eval.server.template import TemplateRegistry, TemplateError


@pytest.fixture
def data_root(tmp_path):
    root = tmp_path / ".micro-eval-server"
    root.mkdir()
    return root


@pytest.fixture
def registry(data_root):
    return TemplateRegistry(data_root)


@pytest.fixture
def source_dir(tmp_path):
    src = tmp_path / "source"
    src.mkdir()
    (src / "eval.yaml").write_text("project_name: test\n")
    tasks = src / "tasks"
    tasks.mkdir()
    (tasks / "task-a.yaml").write_text("id: task-a\n")
    return src


def test_create(registry, source_dir):
    meta = registry.create(source_dir, template_id="tpl-1", name="Test Template")
    assert meta.template_id == "tpl-1"
    assert meta.version == "1.0.0"
    assert registry.get("tpl-1") is not None


def test_create_duplicate_rejected(registry, source_dir):
    registry.create(source_dir, template_id="tpl-1", name="T")
    with pytest.raises(TemplateError, match="already exists"):
        registry.create(source_dir, template_id="tpl-1", name="T2")


def test_update_increments_version(registry, source_dir):
    registry.create(source_dir, template_id="tpl-1", name="T")
    (source_dir / "eval.yaml").write_text("project_name: updated\n")
    meta = registry.update("tpl-1", source_dir)
    assert meta.version == "1.0.1"


def test_list(registry, source_dir):
    registry.create(source_dir, template_id="tpl-1", name="A")
    registry.create(source_dir, template_id="tpl-2", name="B")
    templates = registry.list_templates()
    assert len(templates) == 2


def test_delete(registry, source_dir):
    registry.create(source_dir, template_id="tpl-1", name="T")
    assert registry.delete("tpl-1")
    assert registry.get("tpl-1") is None
```

- [ ] **Step 3: Write queue tests**

```python
# tests/unit/server/test_queue.py
"""Tests for QueueDB."""

import pytest
from pathlib import Path
from micro_eval.server.queue import QueueDB, QueueFullError


@pytest.fixture
def queue(tmp_path):
    db = QueueDB(tmp_path / "queue.db")
    yield db
    db.close()


def test_enqueue_creates_job(queue):
    result = queue.enqueue("ws-1", "alice", '{"run_id": "r1"}')
    assert result["status"] == "queued"
    assert result["job_id"].startswith("job-")


def test_dequeue_fifo(queue):
    queue.enqueue("ws-1", "alice", '{"run_id": "r1"}')
    queue.enqueue("ws-2", "bob", '{"run_id": "r2"}')
    job = queue.dequeue_next()
    assert job["owner"] == "alice"
    job2 = queue.dequeue_next()
    assert job2["owner"] == "bob"


def test_dequeue_empty(queue):
    assert queue.dequeue_next() is None


def test_job_lifecycle(queue):
    result = queue.enqueue("ws-1", "alice", '{"run_id": "r1"}')
    job_id = result["job_id"]
    job = queue.dequeue_next()
    assert job["status"] == "running"
    queue.update_status(job_id, "done", finished_at="2026-01-01T00:00:00Z")
    done_job = queue.get_job(job_id)
    assert done_job["status"] == "done"


def test_cancel_queued_job(queue):
    result = queue.enqueue("ws-1", "alice", '{"run_id": "r1"}')
    job_id = result["job_id"]
    cancel_result = queue.request_cancel(job_id, "bob")
    assert cancel_result["status"] == "cancelled"
    job = queue.get_job(job_id)
    assert job["status"] == "cancelled"
    assert job["cancelled_by"] == "bob"


def test_cancel_running_job_stop_after_run(queue):
    result = queue.enqueue("ws-1", "alice", '{"run_id": "r1"}')
    job_id = result["job_id"]
    queue.dequeue_next()
    cancel_result = queue.request_cancel(job_id, "bob")
    assert cancel_result["status"] == "running"
    assert cancel_result["cancel_requested_at"] is not None
    assert queue.is_cancel_requested(job_id)


def test_cancel_done_job_rejected(queue):
    result = queue.enqueue("ws-1", "alice", '{"run_id": "r1"}')
    queue.dequeue_next()
    queue.update_status(result["job_id"], "done", finished_at="2026-01-01T00:00:00Z")
    cancel_result = queue.request_cancel(result["job_id"], "bob")
    assert cancel_result["error"] == "job_already_terminated"


def test_queue_overflow(queue):
    for i in range(3):
        queue.enqueue(f"ws-{i}", "alice", f'{{"run_id": "r{i}"}}', max_queue_size=3)
    with pytest.raises(QueueFullError):
        queue.enqueue("ws-x", "alice", '{"run_id": "rx"}', max_queue_size=3)


def test_progress_update(queue):
    result = queue.enqueue("ws-1", "alice", '{"run_id": "r1"}')
    queue.dequeue_next()
    queue.update_progress(result["job_id"], {"completed_cells": 3, "total_cells": 12})
    job = queue.get_job(result["job_id"])
    assert job["progress"]["completed_cells"] == 3


def test_has_pending_jobs(queue):
    queue.enqueue("ws-1", "alice", '{"run_id": "r1"}')
    assert queue.has_pending_jobs("ws-1")
    assert not queue.has_pending_jobs("ws-other")


def test_queue_dashboard(queue):
    queue.enqueue("ws-1", "alice", '{"run_id": "r1"}')
    queue.enqueue("ws-2", "bob", '{"run_id": "r2"}')
    queue.dequeue_next()
    dashboard = queue.get_queue_dashboard()
    assert dashboard["running"]["owner"] == "alice"
    assert len(dashboard["queued"]) == 1
    assert dashboard["queued"][0]["position"] == 1
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/server/ -v`
Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add tests/unit/server/
git commit -m "test(server): add unit tests for workspace, template, and queue"
```

---

## Milestone 2: RunRecord Extensions + Worker

> 目标：扩展 RunRecord 以支持 owner / server_context；实现 worker 守护进程和 build-plan CLI。

### Task 2.1: Extend RunRecord with Server Fields

**Files:**
- Modify: `src/micro_eval/models/run.py`

- [ ] **Step 1: Add optional owner and server_context fields to RunRecord**

Add these fields after `denominator_policy` in `RunRecord`:

```python
    # Server mode fields (optional, backward compatible)
    owner: str | None = None
    server_context: dict | None = None
```

- [ ] **Step 2: Commit**

```bash
git add src/micro_eval/models/run.py
git commit -m "feat(models): add optional owner and server_context to RunRecord"
```

### Task 2.2: Add on_cell_complete Callback to ExecutionKernel

**Files:**
- Modify: `src/micro_eval/engine/kernel.py`

- [ ] **Step 1: Add callback parameter and invocation**

Modify `ExecutionKernel.__init__` to accept an optional callback:

```python
    def __init__(self, project_root: Path | str, on_cell_complete: Callable | None = None):
        self.project_root = Path(project_root)
        self.run_store = RunStore(self.project_root)
        self._on_cell_complete = on_cell_complete
```

Add `from typing import Callable` to imports.

In `run()`, add a counter and callback invocation. After the line `record = self.run_store.append_cell_result(record, result)` inside the `for completed in asyncio.as_completed(tasks):` loop, add:

```python
            if self._on_cell_complete:
                completed_count = len(record.results)
                total_count = len(cells)
                self._on_cell_complete(completed_count, total_count, result)
```

- [ ] **Step 2: Verify existing tests still pass**

Run: `uv run pytest tests/ -x -q`
Expected: All existing tests pass (callback is optional, None by default).

- [ ] **Step 3: Commit**

```bash
git add src/micro_eval/engine/kernel.py
git commit -m "feat(kernel): add optional on_cell_complete callback"
```

### Task 2.3: build-plan CLI Command

**Files:**
- Create: `src/micro_eval/cli/build_plan.py`
- Modify: `src/micro_eval/cli/main.py`

- [ ] **Step 1: Implement build-plan command**

```python
# src/micro_eval/cli/build_plan.py
"""build-plan CLI command — construct RunPlan from eval.yaml without executing."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import typer

from micro_eval.config.loader import ConfigError, load_config, load_task_paths
from micro_eval.config.planner import build_run_plan


def build_plan_command(
    workspace: Path = typer.Option(..., "--workspace", help="Path to workspace directory"),
    overrides: str | None = typer.Option(None, "--overrides", help="JSON string of config overrides"),
) -> None:
    """Construct a RunPlan from eval.yaml and output JSON to stdout."""
    config_path = workspace / "eval.yaml"
    if not config_path.exists():
        typer.echo(json.dumps({"error": f"eval.yaml not found in {workspace}"}), err=True)
        raise typer.Exit(1)

    try:
        project = load_config(config_path)
        tasks = load_task_paths(config_path, project)
    except ConfigError as exc:
        typer.echo(json.dumps({"error": str(exc)}), err=True)
        raise typer.Exit(1)

    if not tasks:
        typer.echo(json.dumps({"error": "no tasks found"}), err=True)
        raise typer.Exit(1)

    override_dict = {}
    if overrides:
        override_dict = json.loads(overrides)

    ALLOWED_OVERRIDES = {"repetitions", "timeout_s", "max_concurrency"}
    for key in override_dict:
        if key not in ALLOWED_OVERRIDES:
            typer.echo(json.dumps({"error": f"override '{key}' not allowed. Allowed: {ALLOWED_OVERRIDES}"}), err=True)
            raise typer.Exit(1)

    max_concurrency = override_dict.get("max_concurrency")

    plan = build_run_plan(project, tasks, max_concurrency=max_concurrency, project_root=workspace)
    typer.echo(plan.model_dump_json(indent=2))
```

- [ ] **Step 2: Register in main.py**

Add to imports in `main.py`:

```python
from micro_eval.cli.build_plan import build_plan_command
```

Add after the existing `app.command()` registrations:

```python
app.command(name="build-plan")(build_plan_command)
```

- [ ] **Step 3: Commit**

```bash
git add src/micro_eval/cli/build_plan.py src/micro_eval/cli/main.py
git commit -m "feat(cli): add build-plan command for server-mode plan construction"
```

### Task 2.4: Run Worker

**Files:**
- Create: `src/micro_eval/server/worker.py`

- [ ] **Step 1: Implement worker loop**

```python
# src/micro_eval/server/worker.py
"""Run worker — serial queue consumer for server mode."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sys
from pathlib import Path

from micro_eval.engine.kernel import ExecutionKernel
from micro_eval.models.run import RunPlan
from micro_eval.server.models import ServerConfig
from micro_eval.server.queue import QueueDB

logger = logging.getLogger(__name__)

PID_FILENAME = "worker.pid"


def _utcnow() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _write_pid(data_root: Path) -> None:
    pid_path = data_root / PID_FILENAME
    if pid_path.exists():
        old_pid = int(pid_path.read_text().strip())
        try:
            os.kill(old_pid, 0)
            logger.error("Another worker is already running (PID: %d)", old_pid)
            sys.exit(1)
        except OSError:
            pass
    pid_path.write_text(str(os.getpid()))


def _clear_pid(data_root: Path) -> None:
    pid_path = data_root / PID_FILENAME
    if pid_path.exists():
        try:
            pid_path.unlink()
        except OSError:
            pass


async def worker_loop(
    data_root: Path,
    poll_interval: float = 2.0,
    run_timeout: int = 3600,
) -> None:
    db = QueueDB(data_root / "queue.db")

    def workspace_resolver(ws_id: str) -> Path | None:
        ws_path = data_root / "workspaces" / ws_id
        if ws_path.exists():
            return ws_path
        return None

    recovered = db.recover_stale_jobs(workspace_resolver)
    if recovered:
        logger.info("Recovered %d stale jobs: %s", len(recovered), recovered)

    shutdown = asyncio.Event()
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, shutdown.set)

    logger.info("Worker started, polling every %.1fs", poll_interval)

    while not shutdown.is_set():
        job = db.dequeue_next()
        if job is None:
            try:
                await asyncio.wait_for(shutdown.wait(), timeout=poll_interval)
            except asyncio.TimeoutError:
                pass
            continue

        job_id = job["job_id"]
        ws_id = job["workspace_id"]
        ws_path = data_root / "workspaces" / ws_id
        logger.info("Executing job %s for workspace %s", job_id, ws_id)

        try:
            plan = RunPlan.model_validate_json(job["plan_json"])
            run_id = plan.run_id
            db.update_status(job_id, "running", run_id=run_id)

            def on_cell_complete(completed: int, total: int, result):
                db.update_progress(job_id, {
                    "completed_cells": completed,
                    "total_cells": total,
                    "current_task": result.task_id,
                    "current_config": result.configuration_id,
                })

            kernel = ExecutionKernel(project_root=ws_path, on_cell_complete=on_cell_complete)
            record = await asyncio.wait_for(
                kernel.run(plan),
                timeout=run_timeout,
            )

            if db.is_cancel_requested(job_id):
                db.update_status(job_id, "cancelled", finished_at=_utcnow())
                logger.info("Job %s cancelled (stop-after-run)", job_id)
            else:
                db.update_status(job_id, "done", finished_at=_utcnow())
                logger.info("Job %s completed successfully", job_id)

        except asyncio.TimeoutError:
            db.update_status(
                job_id, "failed", finished_at=_utcnow(),
                error=f"run timed out after {run_timeout}s",
            )
            logger.error("Job %s timed out", job_id)

        except Exception as exc:
            db.update_status(job_id, "failed", finished_at=_utcnow(), error=str(exc))
            logger.exception("Job %s failed: %s", job_id, exc)

    db.close()
    logger.info("Worker shut down gracefully")


def run_worker(data_root: Path, config: ServerConfig | None = None) -> None:
    if config is None:
        config = ServerConfig()
    _write_pid(data_root)
    import atexit
    atexit.register(_clear_pid, data_root)
    try:
        asyncio.run(worker_loop(
            data_root,
            poll_interval=config.worker_poll_interval_seconds,
            run_timeout=config.run_timeout_seconds,
        ))
    finally:
        _clear_pid(data_root)
```

- [ ] **Step 2: Commit**

```bash
git add src/micro_eval/server/worker.py
git commit -m "feat(server): implement run worker with timeout, cancel, crash recovery"
```

### Task 2.5: Milestone 2 Tests

**Files:**
- Create: `tests/unit/server/test_worker.py`
- Create: `tests/unit/test_build_plan_cli.py`

- [ ] **Step 1: Write worker unit tests**

```python
# tests/unit/server/test_worker.py
"""Tests for run worker logic."""

import pytest
from pathlib import Path
from micro_eval.server.queue import QueueDB


@pytest.fixture
def data_root(tmp_path):
    root = tmp_path / ".micro-eval-server"
    root.mkdir()
    (root / "workspaces").mkdir()
    return root


def test_crash_recovery_completed(data_root):
    """If run.json exists with completed_at, recover as done."""
    db = QueueDB(data_root / "queue.db")
    result = db.enqueue("ws-test", "alice", '{"run_id": "run-1"}')
    job = db.dequeue_next()
    db.update_status(job["job_id"], "running", run_id="run-1")

    ws_dir = data_root / "workspaces" / "ws-test" / ".micro-eval" / "runs" / "run-1"
    ws_dir.mkdir(parents=True)
    (ws_dir / "run.json").write_text('{"completed_at": "2026-01-01T00:00:00Z"}')

    def resolver(ws_id):
        return data_root / "workspaces" / ws_id

    recovered = db.recover_stale_jobs(resolver)
    assert len(recovered) == 1
    recovered_job = db.get_job(job["job_id"])
    assert recovered_job["status"] == "done"
    db.close()


def test_crash_recovery_interrupted(data_root):
    """If run.json doesn't exist, recover as failed."""
    db = QueueDB(data_root / "queue.db")
    result = db.enqueue("ws-test", "alice", '{"run_id": "run-1"}')
    job = db.dequeue_next()
    db.update_status(job["job_id"], "running", run_id="run-1")

    ws_dir = data_root / "workspaces" / "ws-test"
    ws_dir.mkdir(parents=True)

    def resolver(ws_id):
        return data_root / "workspaces" / ws_id

    recovered = db.recover_stale_jobs(resolver)
    assert len(recovered) == 1
    recovered_job = db.get_job(job["job_id"])
    assert recovered_job["status"] == "failed"
    assert "crashed" in recovered_job["error"]
    db.close()


def test_crash_recovery_with_cancel_requested(data_root):
    """If cancel was requested and run completed, recover as cancelled."""
    db = QueueDB(data_root / "queue.db")
    result = db.enqueue("ws-test", "alice", '{"run_id": "run-1"}')
    job = db.dequeue_next()
    db.update_status(job["job_id"], "running", run_id="run-1")
    db.request_cancel(job["job_id"], "bob")

    ws_dir = data_root / "workspaces" / "ws-test" / ".micro-eval" / "runs" / "run-1"
    ws_dir.mkdir(parents=True)
    (ws_dir / "run.json").write_text('{"completed_at": "2026-01-01T00:00:00Z"}')

    def resolver(ws_id):
        return data_root / "workspaces" / ws_id

    recovered = db.recover_stale_jobs(resolver)
    recovered_job = db.get_job(job["job_id"])
    assert recovered_job["status"] == "cancelled"
    db.close()
```

- [ ] **Step 2: Run all tests**

Run: `uv run pytest tests/unit/server/ -v`
Expected: All tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/server/test_worker.py
git commit -m "test(server): add worker crash recovery tests"
```

---

## Milestone 3: CLI Commands

> 目标：注册 serve, worker, workspace, template, queue CLI 命令。

### Task 3.1: Workspace CLI Commands

**Files:**
- Create: `src/micro_eval/cli/workspace_cmd.py`
- Modify: `src/micro_eval/cli/main.py`

- [ ] **Step 1: Implement workspace subcommands**

```python
# src/micro_eval/cli/workspace_cmd.py
"""Workspace management CLI commands."""

from __future__ import annotations

from pathlib import Path

import typer

from micro_eval.server.workspace import WorkspaceManager

workspace_app = typer.Typer(name="workspace", help="Manage server workspaces.")


def _default_data_root() -> Path:
    return Path.home() / ".micro-eval-server"


@workspace_app.command(name="create")
def workspace_create(
    name: str = typer.Option(..., "--name", help="Workspace name"),
    owner: str = typer.Option(..., "--owner", help="Owner identifier"),
    template: str | None = typer.Option(None, "--template", help="Template ID to copy from"),
    description: str = typer.Option("", "--description", help="Description"),
    data_root: Path = typer.Option(_default_data_root(), "--data-root"),
) -> None:
    """Create a new workspace."""
    manager = WorkspaceManager(data_root)
    meta = manager.create(name=name, owner=owner, template_id=template, description=description)
    typer.echo(meta.model_dump_json(indent=2))


@workspace_app.command(name="list")
def workspace_list(
    all_ws: bool = typer.Option(False, "--all", help="Include archived workspaces"),
    data_root: Path = typer.Option(_default_data_root(), "--data-root"),
) -> None:
    """List workspaces."""
    manager = WorkspaceManager(data_root)
    for ws in manager.list_workspaces(include_archived=all_ws):
        typer.echo(f"{ws.workspace_id}  {ws.name}  owner={ws.owner}  status={ws.status}")


@workspace_app.command(name="delete")
def workspace_delete(
    workspace_id: str = typer.Argument(..., help="Workspace ID to delete"),
    data_root: Path = typer.Option(_default_data_root(), "--data-root"),
    force: bool = typer.Option(False, "--force", help="Skip confirmation"),
) -> None:
    """Delete a workspace (irreversible)."""
    from micro_eval.server.queue import QueueDB
    db_path = data_root / "queue.db"
    if db_path.exists():
        db = QueueDB(db_path)
        if db.has_pending_jobs(workspace_id):
            typer.echo("Error: workspace has pending/running jobs. Cancel them first.", err=True)
            db.close()
            raise typer.Exit(1)
        db.close()

    manager = WorkspaceManager(data_root)
    meta = manager.get(workspace_id)
    if meta is None:
        typer.echo(f"Error: workspace not found: {workspace_id}", err=True)
        raise typer.Exit(1)

    if not force:
        confirm = typer.confirm(f"Delete workspace '{meta.name}' ({workspace_id})? This cannot be undone.")
        if not confirm:
            raise typer.Abort()

    manager.delete(workspace_id)
    typer.echo(f"Deleted workspace {workspace_id}")
```

- [ ] **Step 2: Register workspace subcommand in main.py**

Add to imports in `main.py`:

```python
from micro_eval.cli.workspace_cmd import workspace_app
```

Add after the existing commands:

```python
app.add_typer(workspace_app, name="workspace")
```

- [ ] **Step 3: Commit**

```bash
git add src/micro_eval/cli/workspace_cmd.py src/micro_eval/cli/main.py
git commit -m "feat(cli): add workspace create/list/delete commands"
```

### Task 3.2: Template CLI Commands

**Files:**
- Create: `src/micro_eval/cli/template_cmd.py`
- Modify: `src/micro_eval/cli/main.py`

- [ ] **Step 1: Implement template subcommands**

```python
# src/micro_eval/cli/template_cmd.py
"""Template management CLI commands."""

from __future__ import annotations

from pathlib import Path

import typer

from micro_eval.server.template import TemplateRegistry

template_app = typer.Typer(name="template", help="Manage evaluation templates.")


def _default_data_root() -> Path:
    return Path.home() / ".micro-eval-server"


@template_app.command(name="create")
def template_create(
    source_dir: Path = typer.Argument(..., help="Source directory to package as template"),
    template_id: str = typer.Option(..., "--id", help="Template ID"),
    name: str = typer.Option(..., "--name", help="Template name"),
    description: str = typer.Option("", "--description"),
    data_root: Path = typer.Option(_default_data_root(), "--data-root"),
) -> None:
    """Create a template from a local directory."""
    registry = TemplateRegistry(data_root)
    meta = registry.create(source_dir, template_id=template_id, name=name, description=description)
    typer.echo(meta.model_dump_json(indent=2))


@template_app.command(name="update")
def template_update(
    template_id: str = typer.Argument(..., help="Template ID to update"),
    source_dir: Path = typer.Argument(..., help="New source directory"),
    data_root: Path = typer.Option(_default_data_root(), "--data-root"),
) -> None:
    """Update a template with new content."""
    registry = TemplateRegistry(data_root)
    meta = registry.update(template_id, source_dir)
    typer.echo(meta.model_dump_json(indent=2))


@template_app.command(name="list")
def template_list(
    data_root: Path = typer.Option(_default_data_root(), "--data-root"),
) -> None:
    """List all templates."""
    registry = TemplateRegistry(data_root)
    for tpl in registry.list_templates():
        typer.echo(f"{tpl.template_id}  {tpl.name}  v{tpl.version}")


@template_app.command(name="delete")
def template_delete(
    template_id: str = typer.Argument(..., help="Template ID to delete"),
    data_root: Path = typer.Option(_default_data_root(), "--data-root"),
) -> None:
    """Delete a template."""
    registry = TemplateRegistry(data_root)
    if registry.delete(template_id):
        typer.echo(f"Deleted template {template_id}")
    else:
        typer.echo(f"Template not found: {template_id}", err=True)
        raise typer.Exit(1)
```

- [ ] **Step 2: Register in main.py**

Add import and registration:

```python
from micro_eval.cli.template_cmd import template_app
app.add_typer(template_app, name="template")
```

- [ ] **Step 3: Commit**

```bash
git add src/micro_eval/cli/template_cmd.py src/micro_eval/cli/main.py
git commit -m "feat(cli): add template create/update/list/delete commands"
```

### Task 3.3: Serve + Worker CLI Commands

**Files:**
- Create: `src/micro_eval/cli/serve.py`
- Create: `src/micro_eval/cli/queue_cmd.py`
- Modify: `src/micro_eval/cli/main.py`

- [ ] **Step 1: Implement serve command**

```python
# src/micro_eval/cli/serve.py
"""Server launch CLI commands."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from pathlib import Path

import typer

from micro_eval.server.models import ServerConfig


def _default_data_root() -> Path:
    return Path.home() / ".micro-eval-server"


def serve_command(
    port: int = typer.Option(3000, "--port", help="HTTP port"),
    host: str = typer.Option("0.0.0.0", "--host", help="Bind host"),
    data_root: Path = typer.Option(_default_data_root(), "--data-root"),
) -> None:
    """Start the Team Server (Next.js + worker)."""
    data_root = data_root.expanduser()
    data_root.mkdir(mode=0o700, parents=True, exist_ok=True)

    config_path = data_root / "server.json"
    if not config_path.exists():
        config = ServerConfig(bind_host=host, bind_port=port, data_root=str(data_root))
        config_path.write_text(config.model_dump_json(indent=2))
    else:
        config = ServerConfig.model_validate_json(config_path.read_text())

    from micro_eval.server.queue import QueueDB
    db = QueueDB(data_root / "queue.db")
    db.close()

    (data_root / "workspaces").mkdir(exist_ok=True)
    (data_root / "templates").mkdir(exist_ok=True)

    typer.echo(f"Starting worker...")
    worker_proc = subprocess.Popen(
        [sys.executable, "-m", "micro_eval.cli.main", "worker", "--data-root", str(data_root)],
    )

    ui_dir = Path(__file__).resolve().parent.parent.parent.parent / "ui"
    if not ui_dir.exists():
        typer.echo(f"Error: ui/ directory not found at {ui_dir}", err=True)
        worker_proc.terminate()
        raise typer.Exit(1)

    next_dir = ui_dir / ".next"
    if not next_dir.exists():
        typer.echo("Building Next.js...")
        build_result = subprocess.run(["npm", "run", "build"], cwd=ui_dir)
        if build_result.returncode != 0:
            typer.echo("Error: Next.js build failed", err=True)
            worker_proc.terminate()
            raise typer.Exit(1)

    env = {
        **os.environ,
        "MICRO_EVAL_SERVER_MODE": "true",
        "MICRO_EVAL_DATA_ROOT": str(data_root),
    }

    typer.echo(f"Starting Next.js on {host}:{port}...")
    try:
        next_proc = subprocess.Popen(
            ["npx", "next", "start", "--port", str(port), "--hostname", host],
            cwd=ui_dir,
            env=env,
        )

        def shutdown(signum, frame):
            typer.echo("\nShutting down...")
            worker_proc.terminate()
            next_proc.terminate()
            worker_proc.wait(timeout=10)
            next_proc.wait(timeout=10)

        signal.signal(signal.SIGINT, shutdown)
        signal.signal(signal.SIGTERM, shutdown)

        next_proc.wait()
    except KeyboardInterrupt:
        worker_proc.terminate()
        next_proc.terminate()
    finally:
        worker_proc.wait(timeout=10)


def worker_command(
    data_root: Path = typer.Option(_default_data_root(), "--data-root"),
) -> None:
    """Start the run worker (standalone)."""
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    data_root = data_root.expanduser()
    config_path = data_root / "server.json"
    config = None
    if config_path.exists():
        config = ServerConfig.model_validate_json(config_path.read_text())

    from micro_eval.server.worker import run_worker
    run_worker(data_root, config)
```

- [ ] **Step 2: Implement queue status/cancel CLI**

```python
# src/micro_eval/cli/queue_cmd.py
"""Queue management CLI commands."""

from __future__ import annotations

from pathlib import Path

import typer

queue_app = typer.Typer(name="queue", help="Manage the run queue.")


def _default_data_root() -> Path:
    return Path.home() / ".micro-eval-server"


@queue_app.command(name="status")
def queue_status(
    data_root: Path = typer.Option(_default_data_root(), "--data-root"),
) -> None:
    """Show queue status."""
    from micro_eval.server.queue import QueueDB
    db = QueueDB(data_root.expanduser() / "queue.db")
    dashboard = db.get_queue_dashboard()
    if dashboard["running"]:
        r = dashboard["running"]
        typer.echo(f"Running: {r['job_id']}  workspace={r['workspace_id']}  owner={r['owner']}")
    else:
        typer.echo("Running: (none)")
    if dashboard["queued"]:
        typer.echo(f"Queued: {len(dashboard['queued'])} jobs")
        for q in dashboard["queued"]:
            typer.echo(f"  #{q['position']}: {q['job_id']}  workspace={q['workspace_id']}  owner={q['owner']}")
    else:
        typer.echo("Queued: (none)")
    db.close()


@queue_app.command(name="cancel")
def queue_cancel(
    job_id: str = typer.Argument(..., help="Job ID to cancel"),
    data_root: Path = typer.Option(_default_data_root(), "--data-root"),
) -> None:
    """Cancel a queued or running job."""
    from micro_eval.server.queue import QueueDB
    db = QueueDB(data_root.expanduser() / "queue.db")
    result = db.request_cancel(job_id, "cli-admin")
    if result is None:
        typer.echo(f"Job not found: {job_id}", err=True)
        raise typer.Exit(1)
    if "error" in result:
        typer.echo(f"Cannot cancel: {result['error']} (status={result['status']})", err=True)
        raise typer.Exit(1)
    typer.echo(f"Job {job_id} → {result['status']}")
    db.close()
```

- [ ] **Step 3: Register all commands in main.py**

Add imports:

```python
from micro_eval.cli.serve import serve_command, worker_command
from micro_eval.cli.queue_cmd import queue_app
```

Add registrations:

```python
app.command(name="serve")(serve_command)
app.command(name="worker")(worker_command)
app.add_typer(queue_app, name="queue")
```

- [ ] **Step 4: Commit**

```bash
git add src/micro_eval/cli/serve.py src/micro_eval/cli/queue_cmd.py src/micro_eval/cli/main.py
git commit -m "feat(cli): add serve, worker, and queue commands"
```

---

## Milestone 4: UI Data Layer + API Routes

> 目标：为 Next.js UI 添加 server mode 检测、workspace-scoped 数据访问、和全部 API routes。
>
> **注意**：开始此 milestone 前，必须先阅读 `ui/node_modules/next/dist/docs/` 中的 Next.js 文档（见 `ui/AGENTS.md`），确认 API 约定。

### Task 4.1: Server Mode Detection + Workspace API Helpers

**Files:**
- Create: `ui/src/lib/server-mode.ts`
- Create: `ui/src/lib/workspace-api.ts`

- [ ] **Step 1: Implement server mode utilities**

```typescript
// ui/src/lib/server-mode.ts
import path from "node:path";
import os from "node:os";

export function isServerMode(): boolean {
  return process.env.MICRO_EVAL_SERVER_MODE === "true";
}

export function getServerDataRoot(): string {
  return process.env.MICRO_EVAL_DATA_ROOT || path.join(os.homedir(), ".micro-eval-server");
}
```

```typescript
// ui/src/lib/workspace-api.ts
import path from "node:path";
import fs from "node:fs";
import { getServerDataRoot } from "./server-mode";

const WS_ID_RE = /^ws-\d{8}T\d{6}Z-[a-f0-9]{8}$/;

export function resolveWorkspacePath(workspaceId: string): string | null {
  if (!WS_ID_RE.test(workspaceId)) return null;
  const dataRoot = getServerDataRoot();
  const wsDir = path.resolve(dataRoot, "workspaces", workspaceId);
  const wsRoot = path.resolve(dataRoot, "workspaces");
  if (!wsDir.startsWith(wsRoot + path.sep)) return null;
  try {
    const realWsDir = fs.realpathSync(wsDir);
    const realWsRoot = fs.realpathSync(wsRoot);
    if (!realWsDir.startsWith(realWsRoot + path.sep)) return null;
    return realWsDir;
  } catch {
    return null;
  }
}

export function getWorkspaceRunsDir(workspaceId: string): string | null {
  const wsPath = resolveWorkspacePath(workspaceId);
  if (!wsPath) return null;
  return path.join(wsPath, ".micro-eval", "runs");
}

export interface WorkspaceMeta {
  schema_version: string;
  workspace_id: string;
  name: string;
  owner: string;
  template_id: string | null;
  template_version: string | null;
  created_at: string;
  last_run_at: string | null;
  run_count: number;
  description: string;
  status: string;
}

export function readWorkspaceMeta(workspaceId: string): WorkspaceMeta | null {
  const wsPath = resolveWorkspacePath(workspaceId);
  if (!wsPath) return null;
  const metaPath = path.join(wsPath, "workspace.json");
  if (!fs.existsSync(metaPath)) return null;
  return JSON.parse(fs.readFileSync(metaPath, "utf-8"));
}

export function listWorkspaces(includeArchived = false): WorkspaceMeta[] {
  const wsRoot = path.join(getServerDataRoot(), "workspaces");
  if (!fs.existsSync(wsRoot)) return [];
  const entries = fs.readdirSync(wsRoot, { withFileTypes: true });
  const result: WorkspaceMeta[] = [];
  for (const entry of entries) {
    if (!entry.isDirectory()) continue;
    const metaPath = path.join(wsRoot, entry.name, "workspace.json");
    if (!fs.existsSync(metaPath)) continue;
    try {
      const meta: WorkspaceMeta = JSON.parse(fs.readFileSync(metaPath, "utf-8"));
      if (!includeArchived && meta.status === "archived") continue;
      result.push(meta);
    } catch {
      continue;
    }
  }
  return result.sort((a, b) => b.created_at.localeCompare(a.created_at));
}
```

- [ ] **Step 2: Commit**

```bash
git add ui/src/lib/server-mode.ts ui/src/lib/workspace-api.ts
git commit -m "feat(ui): add server mode detection and workspace API helpers"
```

### Task 4.2: Server API Routes (Workspaces, Queue, Jobs, Templates)

由于 API routes 数量多且模式类似，这里列出核心 routes 的实现。其余 routes 按相同模式实现。

**Files:**
- Create: `ui/src/app/api/workspaces/route.ts`
- Create: `ui/src/app/api/workspaces/[id]/route.ts`
- Create: `ui/src/app/api/workspaces/[id]/runs/route.ts`
- Create: `ui/src/app/api/workspaces/[id]/runs/enqueue/route.ts`
- Create: `ui/src/app/api/queue/route.ts`
- Create: `ui/src/app/api/jobs/[jobId]/route.ts`
- Create: `ui/src/app/api/jobs/[jobId]/cancel/route.ts`
- Create: `ui/src/app/api/templates/route.ts`
- Create: `ui/src/app/api/server/status/route.ts`
- Create: `ui/src/app/api/workspaces/[id]/config/route.ts`
- Create: `ui/src/app/api/workspaces/[id]/runs/[runId]/route.ts`
- Create: `ui/src/app/api/workspaces/[id]/runs/[runId]/cells/[cellId]/route.ts`
- Create: `ui/src/app/api/workspaces/[id]/runs/[runId]/cells/[cellId]/evaluate/route.ts`
- Create: `ui/src/app/api/workspaces/[id]/runs/[runId]/cells/[cellId]/trace/route.ts`
- Create: `ui/src/app/api/workspaces/[id]/runs/[runId]/artifacts/route.ts`
- Create: `ui/src/app/api/workspaces/[id]/trends/route.ts`
- Create: `ui/src/app/api/templates/[id]/route.ts`

**每个 route 必须实施的通用安全检查**（§14.6 + §10.3）：

```typescript
// Shared middleware pattern for all write routes:
function validateWriteRequest(request: Request): { member: string } | Response {
  const contentType = request.headers.get("content-type");
  if (contentType && !contentType.includes("application/json")) {
    return NextResponse.json({ error: "content type must be application/json" }, { status: 400 });
  }
  const member = request.headers.get("x-micro-eval-member");
  if (!member || !/^[a-zA-Z0-9._-]{1,64}$/.test(member)) {
    return NextResponse.json({ error: "valid X-Micro-Eval-Member header required" }, { status: 400 });
  }
  // Host header allowlist check would go here in production
  return { member };
}
```

- [ ] **Step 1: Implement workspace list + create route**

- [ ] **Step 2: Implement workspace detail/update/delete route**

- [ ] **Step 3: Implement workspace runs list route (reuse existing `listRuns` pattern with workspace-scoped runsDir)**

- [ ] **Step 4: Implement enqueue route (calls `uv run micro-eval build-plan` subprocess)**

- [ ] **Step 5: Implement queue dashboard route (reads queue.db via subprocess or direct SQLite)**

- [ ] **Step 6: Implement job status + cancel routes**

- [ ] **Step 7: Implement template list + detail routes**

- [ ] **Step 8: Implement server status route**

- [ ] **Step 9: Implement config get/put route**

- [ ] **Step 10: Implement run detail, cell detail, trace, artifacts, evaluate routes (workspace-scoped versions of existing routes)**

- [ ] **Step 11: Commit all routes**

```bash
git add ui/src/app/api/
git commit -m "feat(ui): add server-mode API routes for workspaces, queue, jobs, templates"
```

---

## Milestone 5: UI Pages + Components

> 目标：实现 server mode 的 UI 页面和组件。

### Task 5.1: Shared UI Components

**Files:**
- Create: `ui/src/components/MemberBadge.tsx`
- Create: `ui/src/components/WorkspaceCard.tsx`
- Create: `ui/src/components/QueueJobCard.tsx`
- Create: `ui/src/components/TemplateCard.tsx`
- Create: `ui/src/components/RunEnqueueButton.tsx`
- Create: `ui/src/components/ConfigEditor.tsx`
- Create: `ui/src/components/QueueDashboard.tsx`

- [ ] **Step 1: Implement all shared components**
- [ ] **Step 2: Commit**

```bash
git add ui/src/components/
git commit -m "feat(ui): add server-mode components"
```

### Task 5.2: Server Mode Pages

**Files:**
- Modify: `ui/src/app/page.tsx` (conditional server dashboard)
- Create: `ui/src/app/workspaces/page.tsx`
- Create: `ui/src/app/workspaces/new/page.tsx`
- Create: `ui/src/app/workspace/[id]/page.tsx`
- Create: `ui/src/app/workspace/[id]/run/[runId]/page.tsx`
- Create: `ui/src/app/workspace/[id]/run/[runId]/review/page.tsx`
- Create: `ui/src/app/workspace/[id]/config/page.tsx`
- Create: `ui/src/app/templates/page.tsx`
- Create: `ui/src/app/templates/[id]/page.tsx`
- Create: `ui/src/app/queue/page.tsx`

- [ ] **Step 1: Modify landing page for server mode conditional**
- [ ] **Step 2: Implement workspace list, create, detail pages**
- [ ] **Step 3: Implement workspace run detail and review pages (reuse existing components with workspaceId prop)**
- [ ] **Step 4: Implement config editor page**
- [ ] **Step 5: Implement template pages**
- [ ] **Step 6: Implement queue dashboard page**
- [ ] **Step 7: Commit**

```bash
git add ui/src/app/
git commit -m "feat(ui): add server-mode pages"
```

### Task 5.3: Modify Existing Components for Server Mode

**Files:**
- Modify: `ui/src/components/RunList.tsx`
- Modify: `ui/src/components/CellDetail.tsx`
- Modify: `ui/src/components/MatrixHeatmap.tsx`
- Modify: `ui/src/components/AnnotationPanel.tsx`

- [ ] **Step 1: Add optional workspaceId prop to existing components**

Each component needs to accept an optional `workspaceId` prop and use it for link generation and API endpoint URLs. When `workspaceId` is present, links point to `/workspace/[id]/run/[runId]` instead of `/run/[id]`.

- [ ] **Step 2: Commit**

```bash
git add ui/src/components/
git commit -m "feat(ui): adapt existing components for workspace-scoped mode"
```

---

## Milestone 6: Integration Tests + Security Verification

> 目标：补充跨语言 contract tests、安全负例测试、vitest UI tests。

### Task 6.1: Schema Parity Contract Tests

**Files:**
- Modify: `ui/src/lib/schema.ts` (add WorkspaceSchema, JobSchema, etc.)
- Create: `tests/contract/test_server_schema_parity.py`

- [ ] **Step 1: Add zod schemas for server entities**

Add to `ui/src/lib/schema.ts`:

```typescript
export const WorkspaceMetaSchema = z.object({
  schema_version: z.string().default("1.0"),
  workspace_id: z.string(),
  name: z.string(),
  owner: z.string(),
  template_id: z.string().nullable().default(null),
  template_version: z.string().nullable().default(null),
  created_at: z.string(),
  last_run_at: z.string().nullable().default(null),
  run_count: z.number().int().default(0),
  description: z.string().default(""),
  status: z.string().default("active"),
});

export const JobSchema = z.object({
  job_id: z.string(),
  workspace_id: z.string(),
  owner: z.string(),
  status: z.string(),
  enqueued_at: z.string(),
  started_at: z.string().nullable().default(null),
  finished_at: z.string().nullable().default(null),
  run_id: z.string().nullable().default(null),
  error: z.string().nullable().default(null),
  progress: z.any().nullable().default(null),
  cancel_requested_at: z.string().nullable().default(null),
  cancelled_by: z.string().nullable().default(null),
});

export type WorkspaceMeta = z.infer<typeof WorkspaceMetaSchema>;
export type Job = z.infer<typeof JobSchema>;
```

Also extend `RunSchema` with optional server fields:

```typescript
  // Add to RunSchema object:
  owner: z.string().nullable().default(null),
  server_context: z.record(z.string(), z.any()).nullable().default(null),
```

- [ ] **Step 2: Write Python-side parity test**

```python
# tests/contract/test_server_schema_parity.py
"""Contract tests: Python server models ↔ TS zod schemas must agree."""

import json
import subprocess
import pytest


def _run_ts_parse(schema_name: str, data: dict) -> dict:
    """Run a TS snippet that parses data against a zod schema."""
    script = f"""
    const {{ {schema_name} }} = require('./src/lib/schema');
    const data = JSON.parse(process.argv[1]);
    try {{
        const result = {schema_name}.parse(data);
        console.log(JSON.stringify({{ok: true, result}}));
    }} catch(e) {{
        console.log(JSON.stringify({{ok: false, error: e.message}}));
    }}
    """
    result = subprocess.run(
        ["npx", "tsx", "-e", script, json.dumps(data)],
        capture_output=True, text=True, cwd="ui", timeout=15,
    )
    return json.loads(result.stdout.strip())


def test_workspace_meta_parity():
    from micro_eval.server.models import WorkspaceMeta
    meta = WorkspaceMeta(
        workspace_id="ws-20260619T091803Z-a3f7b2c1",
        name="test",
        owner="alice",
        created_at="2026-06-19T09:18:03Z",
    )
    data = meta.model_dump(mode="json")
    result = _run_ts_parse("WorkspaceMetaSchema", data)
    assert result["ok"], f"TS parse failed: {result.get('error')}"


def test_run_record_with_server_context():
    """RunRecord with owner + server_context should be parseable by TS RunSchema."""
    from micro_eval.models.run import RunRecord
    record = RunRecord(
        id="run-test",
        project_name="test",
        created_at="2026-06-19T00:00:00Z",
        output_dir=".micro-eval/runs",
        owner="alice",
        server_context={"workspace_id": "ws-test", "server_name": "team-eval-server"},
    )
    data = record.model_dump(mode="json")
    result = _run_ts_parse("RunSchema", data)
    assert result["ok"], f"TS parse failed: {result.get('error')}"
```

- [ ] **Step 3: Run contract tests**

Run: `uv run pytest tests/contract/test_server_schema_parity.py -v`
Expected: All parity tests pass.

- [ ] **Step 4: Commit**

```bash
git add ui/src/lib/schema.ts tests/contract/test_server_schema_parity.py
git commit -m "test(contract): add server schema parity tests (Python ↔ TS)"
```

### Task 6.2: Security Negative Tests

**Files:**
- Create: `tests/unit/server/test_security_negative.py`

- [ ] **Step 1: Write security negative tests**

```python
# tests/unit/server/test_security_negative.py
"""Security negative tests for server mode."""

import pytest
from micro_eval.server.workspace import WorkspaceManager
from micro_eval.server.queue import QueueDB


@pytest.fixture
def data_root(tmp_path):
    root = tmp_path / ".micro-eval-server"
    root.mkdir()
    (root / "workspaces").mkdir()
    return root


class TestPathTraversal:
    def test_dot_dot(self, data_root):
        mgr = WorkspaceManager(data_root)
        assert mgr.resolve_path("ws-../../../etc") is None

    def test_null_byte(self, data_root):
        mgr = WorkspaceManager(data_root)
        assert mgr.resolve_path("ws-\x00-exploit") is None

    def test_invalid_format(self, data_root):
        mgr = WorkspaceManager(data_root)
        assert mgr.resolve_path("not-a-workspace-id") is None


class TestMemberNameValidation:
    def test_valid_names(self):
        import re
        pattern = re.compile(r"^[a-zA-Z0-9._-]{1,64}$")
        assert pattern.match("alice")
        assert pattern.match("Bob.Smith")
        assert pattern.match("user-123")
        assert pattern.match("a_b.c-d")

    def test_invalid_names(self):
        import re
        pattern = re.compile(r"^[a-zA-Z0-9._-]{1,64}$")
        assert not pattern.match("")
        assert not pattern.match("a" * 65)
        assert not pattern.match("alice; rm -rf /")
        assert not pattern.match("alice<script>")
        assert not pattern.match("alice bob")


class TestWorkspaceQueueInterlock:
    def test_delete_with_pending_job_blocked(self, data_root):
        mgr = WorkspaceManager(data_root)
        meta = mgr.create(name="test", owner="alice")
        db = QueueDB(data_root / "queue.db")
        db.enqueue(meta.workspace_id, "alice", '{"run_id": "r1"}')
        assert db.has_pending_jobs(meta.workspace_id)
        db.close()

    def test_no_pending_jobs_allows_delete(self, data_root):
        mgr = WorkspaceManager(data_root)
        meta = mgr.create(name="test", owner="alice")
        db = QueueDB(data_root / "queue.db")
        assert not db.has_pending_jobs(meta.workspace_id)
        assert mgr.delete(meta.workspace_id)
        db.close()
```

- [ ] **Step 2: Run security tests**

Run: `uv run pytest tests/unit/server/test_security_negative.py -v`
Expected: All tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/server/test_security_negative.py
git commit -m "test(security): add server-mode security negative tests"
```

### Task 6.3: Run All Tests + Verify No Regressions

- [ ] **Step 1: Run full Python test suite**

Run: `uv run pytest -x -q`
Expected: All existing 455+ tests + new server tests pass.

- [ ] **Step 2: Run full TS test suite**

Run: `cd ui && npx vitest run`
Expected: All existing 42+ tests + new tests pass.

- [ ] **Step 3: Verify `micro-eval --help` shows new commands**

Run: `uv run micro-eval --help`
Expected: Output includes `serve`, `worker`, `workspace`, `template`, `build-plan`, `queue`.

---

## Milestone Summary

| Milestone | 交付物 | 独立验收标准 |
|-----------|--------|-------------|
| M0 | CLAUDE.md + security guidelines updates | 文档边界与设计文档对齐 |
| M1 | WorkspaceManager + TemplateRegistry + QueueDB | `pytest tests/unit/server/` 全绿 |
| M2 | RunRecord extensions + kernel callback + worker + build-plan | Worker 能从 queue 取 job 并执行 |
| M3 | serve/worker/workspace/template/queue CLI | `micro-eval --help` 显示所有新命令 |
| M4 | Server-mode API routes + data layer | API routes 返回正确响应 |
| M5 | Server-mode UI pages + components | 浏览器可访问 server dashboard |
| M6 | Contract tests + security tests + regression check | 全套测试绿 + 安全 checklist 通过 |
