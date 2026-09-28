"""Pydantic models for server-mode entities."""

from __future__ import annotations

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
