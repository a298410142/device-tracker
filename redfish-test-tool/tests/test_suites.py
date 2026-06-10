"""End-to-end suite runs against the mock BMC."""

import pytest

from redfish_test_tool.client import RedfishClient
from redfish_test_tool.discovery import ServiceMap
from redfish_test_tool.runner import FAIL, PASS, SKIP, SuiteRunner, TestContext
from redfish_test_tool.suites import SUITE_REGISTRY
from tests.conftest import make_config


def run_suite(suite_id, mock_bmc, **cfg_overrides):
    cfg = make_config(**cfg_overrides)
    client = RedfishClient(cfg)
    client.login()
    smap = ServiceMap(client, cfg.system_id).discover()
    ctx = TestContext(client, smap, cfg)
    runner = SuiteRunner(ctx)
    runner.run_suite(SUITE_REGISTRY[suite_id]())
    client.logout()
    return {r.test_id: r for r in runner.results}, runner


def test_basic_suite_all_pass(mock_bmc):
    results, runner = run_suite("basic", mock_bmc)
    statuses = {tid: r.status for tid, r in results.items()}
    assert statuses == {f"BI-0{i}": PASS for i in range(1, 9)}
    assert runner.exit_code == 0


def test_basic_suite_missing_serial_fails(mock_bmc):
    sys_uri = "/redfish/v1/Systems/System.Embedded.1"
    del mock_bmc.resources[sys_uri]["SerialNumber"]
    results, runner = run_suite("basic", mock_bmc)
    assert results["BI-03"].status == FAIL
    assert runner.exit_code == 1


def test_sensors_suite(mock_bmc):
    results, _ = run_suite("sensors", mock_bmc)
    assert results["SH-01"].status == PASS
    assert results["SH-02"].status == PASS
    assert results["SH-03"].status == PASS
    assert results["SH-04"].status == PASS
    # modern-model resources absent in the iDRAC-like tree -> SKIP not FAIL
    assert results["SH-05"].status == SKIP
    assert results["SH-06"].status == SKIP
    assert results["SH-07"].status == SKIP
    assert results["SH-08"].status == PASS
    assert results["SH-09"].status == PASS


def test_sensors_temperature_over_threshold(mock_bmc):
    thermal = mock_bmc.resources[
        "/redfish/v1/Chassis/System.Embedded.1/Thermal"]
    thermal["Temperatures"][0]["ReadingCelsius"] = 99
    results, _ = run_suite("sensors", mock_bmc)
    assert results["SH-01"].status == FAIL


def test_power_suite_gated_by_default(mock_bmc):
    results, runner = run_suite("power", mock_bmc)
    assert all(r.status == SKIP for r in results.values())
    assert mock_bmc.reset_calls == []
    assert runner.exit_code == 0


def test_power_suite_full_run(mock_bmc, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    mock_bmc.transition_delay_polls = 2  # exercise the polling loop
    results, runner = run_suite("power", mock_bmc,
                                include_power_tests=True,
                                power_timeout=60, boot_wait=0)
    statuses = {tid: r.status for tid, r in results.items()}
    assert statuses == {f"PC-{i:02d}": PASS for i in range(1, 11)}
    # state restored to On at the end
    sys_payload = mock_bmc.resources["/redfish/v1/Systems/System.Embedded.1"]
    assert sys_payload["PowerState"] == "On"
    assert "GracefulShutdown" in mock_bmc.reset_calls
    assert "ForceRestart" in mock_bmc.reset_calls


def test_power_invalid_reset_rejected(mock_bmc, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    results, _ = run_suite("power", mock_bmc,
                           include_power_tests=True,
                           power_timeout=60, boot_wait=0,
                           tests=["PC-01", "PC-02", "PC-09"])
    assert results["PC-09"].status == PASS


def test_accounts_suite(mock_bmc):
    results, runner = run_suite("accounts", mock_bmc)
    statuses = {tid: r.status for tid, r in results.items()}
    for tid in ("AS-01", "AS-02", "AS-03", "AS-04", "AS-05",
                "AS-06", "AS-07", "AS-08", "AS-09"):
        assert statuses[tid] == PASS, f"{tid}: {results[tid].reason}"
    assert statuses["AS-10"] == SKIP  # destructive, gated
    # no leftover sessions or test account
    assert len(mock_bmc.sessions) == 0
    accounts = mock_bmc.resources["/redfish/v1/AccountService/Accounts"]
    assert all("99" not in m["@odata.id"] for m in accounts["Members"])


def test_accounts_clearlog_with_destructive_flag(mock_bmc):
    results, _ = run_suite("accounts", mock_bmc, include_destructive=True)
    assert results["AS-10"].status == PASS
    entries = mock_bmc.resources[
        "/redfish/v1/Managers/iDRAC.Embedded.1/LogServices/Sel/Entries"]
    assert entries["Members"] == []


def test_accounts_teardown_removes_account_on_failure(mock_bmc):
    # Make AS-08 (delete) unreachable by running only AS-06; teardown must clean up
    results, _ = run_suite("accounts", mock_bmc, tests=["AS-06"])
    assert results["AS-06"].status == PASS
    accounts = mock_bmc.resources["/redfish/v1/AccountService/Accounts"]
    assert all("99" not in m["@odata.id"] for m in accounts["Members"])
