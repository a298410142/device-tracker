"""CLI entry point: argument parsing and run orchestration."""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

from redfish_test_tool import __version__
from redfish_test_tool.client import RedfishClient
from redfish_test_tool.config import ALL_SUITES, build_config
from redfish_test_tool.discovery import ServiceMap
from redfish_test_tool.exceptions import ConfigError, RedfishError
from redfish_test_tool.reporting.console import ConsoleReporter, setup_console
from redfish_test_tool.reporting.html_report import write_html_report
from redfish_test_tool.reporting.json_report import write_json_report
from redfish_test_tool.runner import SuiteRunner, TestContext
from redfish_test_tool.suites import SUITE_REGISTRY

EXIT_OK = 0
EXIT_FAILURES = 1
EXIT_CONFIG = 2


def build_parser():
    parser = argparse.ArgumentParser(
        prog="redfish-test",
        description="BMC Redfish API automation testing tool",
    )
    sub = parser.add_subparsers(dest="command")

    run_p = sub.add_parser("run", help="Run test suites against a BMC")
    _add_connection_args(run_p)
    run_p.add_argument("--suites",
                       help="Comma-separated suites: basic,sensors,power,accounts "
                            "or 'all' (default: all non-gated)")
    run_p.add_argument("--tests", help="Comma-separated test IDs, e.g. BI-01,SH-03")
    run_p.add_argument("--include-power-tests", action="store_true",
                       help="Allow the power suite to actually reset the machine")
    run_p.add_argument("--include-destructive", action="store_true",
                       help="Allow destructive tests (e.g. SEL ClearLog)")
    run_p.add_argument("--power-timeout", type=int, default=None,
                       help="Seconds to wait for PowerState transitions (default 300)")
    run_p.add_argument("--boot-wait", type=int, default=None,
                       help="Seconds to wait after power-on before restarts (default 60)")
    run_p.add_argument("--output-dir", default=None, help="Report output directory")
    run_p.add_argument("--report-name", default=None, help="Report directory prefix")
    run_p.add_argument("--lang", choices=["zh-TW", "en"], default=None,
                       help="HTML report language (default zh-TW)")
    run_p.add_argument("--no-color", action="store_true")
    run_p.add_argument("--verbose", "-v", action="store_true",
                       help="Echo HTTP trace to console")

    disc_p = sub.add_parser("discover",
                            help="Dump the discovered Redfish resource tree")
    _add_connection_args(disc_p)
    disc_p.add_argument("--verbose", "-v", action="store_true")

    sub.add_parser("list-suites", help="List suites and their test cases")
    sub.add_parser("version", help="Show version")
    return parser


def _add_connection_args(p):
    p.add_argument("--host", "-H", help="BMC IP or hostname")
    p.add_argument("--port", type=int, default=None, help="HTTPS port (default 443)")
    p.add_argument("--username", "-u", help="BMC username")
    p.add_argument("--password", "-p", help="BMC password "
                   "(prefer env REDFISH_PASSWORD or interactive prompt)")
    p.add_argument("--auth", choices=["session", "basic"], default=None,
                   help="Authentication mode (default session)")
    p.add_argument("--verify-ssl", action="store_true",
                   help="Verify TLS certificates (default: no, BMCs self-sign)")
    p.add_argument("--timeout", type=int, default=None,
                   help="HTTP request timeout in seconds (default 30)")
    p.add_argument("--system-id", default=None,
                   help="Select a specific Systems member by Id")
    p.add_argument("--config", "-c", help="YAML/JSON config file")


def _fill_run_defaults(args):
    """discover/list-suites parsers lack some run-only attributes."""
    for name in ("suites", "tests", "include_power_tests", "include_destructive",
                 "power_timeout", "boot_wait", "output_dir", "report_name",
                 "lang", "no_color", "verbose"):
        if not hasattr(args, name):
            setattr(args, name, None)


def main(argv=None):
    setup_console()
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command in (None, "version"):
        if args.command is None:
            parser.print_help()
            return EXIT_OK
        print(f"redfish-test {__version__}")
        return EXIT_OK

    if args.command == "list-suites":
        return cmd_list_suites()

    _fill_run_defaults(args)
    try:
        config = build_config(args)
    except ConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return EXIT_CONFIG

    if args.command == "discover":
        return cmd_discover(config)
    return cmd_run(config)


def cmd_list_suites():
    class _Probe:
        """collect() only registers cases; a None ctx is fine for listing."""
    for suite_id, suite_cls in SUITE_REGISTRY.items():
        suite = suite_cls()
        suite.collect(_Probe())
        print(f"\n{suite_id}: {suite.title}")
        for case in suite.tests:
            gate = "  [gated]" if case.gated else ""
            print(f"  {case.test_id}  {case.name}{gate}")
    return EXIT_OK


def cmd_discover(config):
    try:
        client = RedfishClient(config)
        client.login()
        try:
            service_map = ServiceMap(client, config.system_id).discover()
            tree = {
                "ServiceRoot": "/redfish/v1/",
                "RedfishVersion": service_map.root.get("RedfishVersion"),
                "System": service_map.system_uri,
                "Chassis": [uri for uri, _ in service_map.chassis_list],
                "Manager": service_map.manager_uri,
                "Sessions": service_map.sessions_collection_uri(),
                "Accounts": service_map.accounts_collection_uri(),
                "LogServices": [uri for _, uri, _ in service_map.log_services()],
            }
            try:
                target, allowed = service_map.reset_action()
                tree["ResetAction"] = {"target": target, "AllowableValues": allowed}
            except RedfishError:
                tree["ResetAction"] = None
            print(json.dumps(tree, indent=2, ensure_ascii=False))
        finally:
            client.logout()
    except RedfishError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    return EXIT_OK


def cmd_run(config):
    out_dir = _make_output_dir(config)
    _setup_trace_log(out_dir, config.verbose)
    console = ConsoleReporter(no_color=config.no_color)

    console.on_message(f"Target: {config.base_url} (auth: {config.auth})")
    try:
        client = RedfishClient(config)
        client.login()
    except RedfishError as exc:
        print(f"Connection/auth error: {exc}", file=sys.stderr)
        return EXIT_CONFIG

    try:
        try:
            service_map = ServiceMap(client, config.system_id).discover()
        except RedfishError as exc:
            print(f"Discovery error: {exc}", file=sys.stderr)
            return EXIT_CONFIG

        ctx = TestContext(client, service_map, config)
        runner = SuiteRunner(ctx, reporters=[console])
        for suite_id in config.suites:
            suite_cls = SUITE_REGISTRY[suite_id]
            console.on_message(f"\n=== Suite: {suite_id} ===")
            runner.run_suite(suite_cls())
    finally:
        client.logout()

    counts = runner.summary()
    environment = _environment_info(config, service_map)
    write_json_report(out_dir / "results.json", runner.results, environment, counts)
    html_path = write_html_report(out_dir / "report.html", runner.results,
                                  environment, counts, lang=config.lang)
    console.print_summary(counts, report_path=html_path)
    return runner.exit_code


def _make_output_dir(config):
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    name = f"{config.report_name}-{stamp}" if config.report_name else stamp
    out_dir = Path(config.output_dir) / name
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def _setup_trace_log(out_dir, verbose):
    trace_logger = logging.getLogger("redfish.trace")
    trace_logger.setLevel(logging.DEBUG)
    handler = logging.FileHandler(out_dir / "http_trace.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    trace_logger.addHandler(handler)
    if verbose:
        echo = logging.StreamHandler()
        echo.setFormatter(logging.Formatter("%(message)s"))
        trace_logger.addHandler(echo)


def _environment_info(config, service_map):
    system = service_map.system or {}
    manager = service_map.manager or {}
    return {
        "BMC Host": config.base_url,
        "Manufacturer": system.get("Manufacturer", "-"),
        "Model": system.get("Model", "-"),
        "SerialNumber": system.get("SerialNumber", "-"),
        "BIOS Version": system.get("BiosVersion", "-"),
        "BMC Firmware": manager.get("FirmwareVersion", "-"),
        "Redfish Version": (service_map.root or {}).get("RedfishVersion", "-"),
        "Tool Version": __version__,
    }


if __name__ == "__main__":
    raise SystemExit(main())
