"""Default and effective Team Server Host allowlists (GRO-578)."""

from unittest.mock import patch

from micro_eval.cli.serve import effective_allowed_hosts
from micro_eval.server.models import ServerConfig


def test_default_server_config_persists_machine_names_and_bind_address() -> None:
    with (
        patch("micro_eval.server.models.socket.gethostname", return_value="eval-box"),
        patch("micro_eval.server.models.socket.getfqdn", return_value="eval-box.example.test"),
    ):
        config = ServerConfig(bind_host="192.168.1.5", bind_port=8080)

    assert config.allowed_hosts == [
        "eval-box:8080",
        "eval-box.example.test:8080",
        "192.168.1.5:8080",
    ]
    assert ServerConfig.model_validate_json(config.model_dump_json()).allowed_hosts == config.allowed_hosts
    assert effective_allowed_hosts(config, "192.168.1.5", 8080) == [
        "localhost:8080",
        "127.0.0.1:8080",
        "[::1]:8080",
        *config.allowed_hosts,
    ]


def test_same_hostname_and_fqdn_are_not_duplicated() -> None:
    with (
        patch("micro_eval.server.models.socket.gethostname", return_value="eval-box"),
        patch("micro_eval.server.models.socket.getfqdn", return_value="eval-box"),
    ):
        assert ServerConfig().allowed_hosts == ["eval-box:3000", "0.0.0.0:3000"]


def test_config_without_allowed_hosts_uses_machine_defaults() -> None:
    with (
        patch("micro_eval.server.models.socket.gethostname", return_value="eval-box"),
        patch("micro_eval.server.models.socket.getfqdn", return_value="eval-box.example.test"),
    ):
        config = ServerConfig.model_validate_json('{"bind_host": "10.0.0.5", "bind_port": 8080}')
    assert config.allowed_hosts == [
        "eval-box:8080",
        "eval-box.example.test:8080",
        "10.0.0.5:8080",
    ]


def test_explicit_allowed_hosts_remains_admin_controlled() -> None:
    config = ServerConfig.model_validate_json('{"allowed_hosts": ["team.example.test:3000"]}')
    assert config.allowed_hosts == ["team.example.test:3000"]
    assert effective_allowed_hosts(config, "192.168.1.5", 3000) == [
        "localhost:3000",
        "127.0.0.1:3000",
        "[::1]:3000",
        "team.example.test:3000",
        "192.168.1.5:3000",
    ]

    empty_config = ServerConfig.model_validate_json('{"allowed_hosts": []}')
    assert empty_config.allowed_hosts == []
    assert "eval-box:3000" not in effective_allowed_hosts(empty_config, "0.0.0.0", 3000)
