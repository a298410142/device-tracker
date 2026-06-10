import pytest

from redfish_test_tool.cli import build_parser
from redfish_test_tool.config import build_config, load_config_file
from redfish_test_tool.exceptions import ConfigError


def parse_run(argv):
    return build_parser().parse_args(["run"] + argv)


def test_cli_args_only():
    args = parse_run(["-H", "10.0.0.5", "-u", "root", "-p", "calvin"])
    cfg = build_config(args, interactive=False)
    assert cfg.host == "10.0.0.5"
    assert cfg.username == "root"
    assert cfg.password == "calvin"
    assert cfg.port == 443
    assert cfg.auth == "session"
    assert cfg.ssl_verify is False
    assert cfg.suites == ["basic", "sensors", "accounts"]


def test_config_file_and_cli_precedence(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        "bmc:\n  host: 10.0.0.9\n  username: fileuser\n  password: filepass\n"
        "  port: 8443\nssl_verify: true\nsuites: [basic]\n"
        "power:\n  power_timeout: 120\noutput:\n  dir: out\n  lang: en\n",
        encoding="utf-8",
    )
    args = parse_run(["-c", str(cfg_file), "-u", "cliuser"])
    cfg = build_config(args, interactive=False)
    assert cfg.host == "10.0.0.9"          # from file
    assert cfg.username == "cliuser"       # CLI wins
    assert cfg.password == "filepass"
    assert cfg.port == 8443
    assert cfg.ssl_verify is True
    assert cfg.suites == ["basic"]
    assert cfg.power_timeout == 120
    assert cfg.output_dir == "out"
    assert cfg.lang == "en"


def test_password_from_env(monkeypatch):
    monkeypatch.setenv("REDFISH_PASSWORD", "envpass")
    args = parse_run(["-H", "h", "-u", "u"])
    cfg = build_config(args, interactive=False)
    assert cfg.password == "envpass"


def test_suites_all_and_tests_filter():
    args = parse_run(["-H", "h", "-u", "u", "-p", "p",
                      "--suites", "all", "--tests", "bi-01,sh-03"])
    cfg = build_config(args, interactive=False)
    assert cfg.suites == ["basic", "sensors", "power", "accounts"]
    assert cfg.tests == ["BI-01", "SH-03"]


def test_missing_host_rejected():
    args = parse_run(["-u", "u", "-p", "p"])
    with pytest.raises(ConfigError):
        build_config(args, interactive=False)


def test_unknown_suite_rejected():
    args = parse_run(["-H", "h", "-u", "u", "-p", "p", "--suites", "bogus"])
    with pytest.raises(ConfigError):
        build_config(args, interactive=False)


def test_missing_config_file():
    with pytest.raises(ConfigError):
        load_config_file("/nonexistent/config.yaml")
