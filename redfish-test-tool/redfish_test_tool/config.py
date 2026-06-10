"""Configuration handling: CLI args > config file > defaults."""

import getpass
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from redfish_test_tool.exceptions import ConfigError

DEFAULT_SUITES = ["basic", "sensors", "accounts"]
ALL_SUITES = ["basic", "sensors", "power", "accounts"]

PASSWORD_ENV_VAR = "REDFISH_PASSWORD"


@dataclass
class Config:
    host: str = ""
    port: int = 443
    username: str = ""
    password: str = ""
    auth: str = "session"          # "session" | "basic"
    ssl_verify: bool = False
    timeout: int = 30
    suites: list = field(default_factory=lambda: list(DEFAULT_SUITES))
    tests: list = field(default_factory=list)   # specific test IDs; empty = all
    system_id: str = ""            # select a specific Systems member
    include_power_tests: bool = False
    include_destructive: bool = False
    power_timeout: int = 300
    boot_wait: int = 60
    output_dir: str = "reports"
    report_name: str = ""
    lang: str = "zh-TW"
    no_color: bool = False
    verbose: bool = False

    @property
    def base_url(self):
        return f"https://{self.host}:{self.port}"

    def validate(self):
        if not self.host:
            raise ConfigError("BMC host is required (use --host or config file)")
        if not self.username:
            raise ConfigError("Username is required (use --username or config file)")
        if self.auth not in ("session", "basic"):
            raise ConfigError(f"Invalid auth mode: {self.auth}")
        unknown = [s for s in self.suites if s not in ALL_SUITES]
        if unknown:
            raise ConfigError(f"Unknown suite(s): {', '.join(unknown)}")


def load_config_file(path):
    """Load a YAML or JSON config file into a flat dict matching Config fields."""
    p = Path(path)
    if not p.is_file():
        raise ConfigError(f"Config file not found: {path}")
    text = p.read_text(encoding="utf-8")
    if p.suffix.lower() == ".json":
        data = json.loads(text)
    else:
        data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ConfigError(f"Config file is not a mapping: {path}")
    return _flatten(data)


def _flatten(data):
    """Map the nested config-file schema onto flat Config field names."""
    flat = {}
    bmc = data.get("bmc", {}) or {}
    for key in ("host", "port", "username", "password", "auth"):
        if key in bmc:
            flat[key] = bmc[key]
    for key in ("ssl_verify", "timeout", "suites", "system_id"):
        if key in data:
            flat[key] = data[key]
    power = data.get("power", {}) or {}
    for key in ("power_timeout", "boot_wait"):
        if key in power:
            flat[key] = power[key]
    output = data.get("output", {}) or {}
    if "dir" in output:
        flat["output_dir"] = output["dir"]
    for key in ("lang", "report_name"):
        if key in output:
            flat[key] = output[key]
    return flat


def build_config(args, interactive=True):
    """Merge argparse namespace over optional config file over defaults."""
    file_values = load_config_file(args.config) if getattr(args, "config", None) else {}

    cfg = Config()
    for key, value in file_values.items():
        if hasattr(cfg, key):
            setattr(cfg, key, value)

    # CLI overrides (only when explicitly provided; argparse defaults are None)
    overrides = {
        "host": args.host,
        "port": args.port,
        "username": args.username,
        "password": args.password,
        "auth": args.auth,
        "timeout": args.timeout,
        "system_id": args.system_id,
        "power_timeout": args.power_timeout,
        "boot_wait": args.boot_wait,
        "output_dir": args.output_dir,
        "report_name": args.report_name,
        "lang": args.lang,
    }
    for key, value in overrides.items():
        if value is not None:
            setattr(cfg, key, value)

    if args.suites is not None:
        names = [s.strip() for s in args.suites.split(",") if s.strip()]
        cfg.suites = ALL_SUITES[:] if names == ["all"] else names
    if args.tests is not None:
        cfg.tests = [t.strip().upper() for t in args.tests.split(",") if t.strip()]

    if args.verify_ssl:
        cfg.ssl_verify = True
    cfg.include_power_tests = bool(args.include_power_tests)
    cfg.include_destructive = bool(args.include_destructive)
    cfg.no_color = bool(args.no_color)
    cfg.verbose = bool(args.verbose)

    # Password resolution: CLI > env > config file > interactive prompt
    if not cfg.password:
        cfg.password = os.environ.get(PASSWORD_ENV_VAR, "")
    if not cfg.password and interactive:
        cfg.password = getpass.getpass(f"Password for {cfg.username}@{cfg.host}: ")

    cfg.validate()
    return cfg
