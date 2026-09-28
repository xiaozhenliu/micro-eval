"""Pydantic models for server-mode entities."""

from __future__ import annotations

import secrets
import socket
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, model_validator


def _compact_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def new_workspace_id() -> str:
    return f"ws-{_compact_utc()}-{secrets.token_hex(4)}"


def new_job_id() -> str:
    return f"job-{_compact_utc()}-{secrets.token_hex(4)}"


def host_with_port(host: str, port: int) -> str:
    """Format a Host header value, including brackets for IPv6 literals."""
    host = host.strip()
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    return f"{host}:{port}"


def default_allowed_hosts(bind_host: str, bind_port: int) -> list[str]:
    """Names written to a newly generated server.json on this machine."""
    names = (socket.gethostname(), socket.getfqdn(), bind_host)
    return list(dict.fromkeys(host_with_port(name, bind_port) for name in names if name.strip()))


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

    @model_validator(mode="after")
    def populate_default_allowed_hosts(self) -> ServerConfig:
        # An explicit [] in an existing server.json must remain admin-controlled.
        if "allowed_hosts" not in self.model_fields_set:
            self.allowed_hosts = default_allowed_hosts(self.bind_host, self.bind_port)
        return self


class JobProgress(BaseModel):
    """Cell counts and latest completed cell written by the worker."""

    completed_cells: int = Field(ge=0)
    total_cells: int = Field(ge=0)
    current_task: str | None = None
    current_config: str | None = None


class JobDTO(BaseModel):
    """Public queue job fields shared by job lookup and queue dashboard."""

    job_id: str
    workspace_id: str
    owner: str
    status: Literal["queued", "running", "done", "failed", "cancelled"]
    enqueued_at: str
    started_at: str | None = None
    finished_at: str | None = None
    run_id: str | None = None
    error: str | None = None
    progress: JobProgress | None = None
    cancel_requested_at: str | None = None
    cancelled_by: str | None = None
    position: int | None = Field(default=None, ge=1)
