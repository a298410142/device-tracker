import json

from redfish_test_tool.reporting.html_report import write_html_report
from redfish_test_tool.reporting.json_report import write_json_report
from redfish_test_tool.runner import TestResult, TestStep
from redfish_test_tool.utils.polling import wait_for
from redfish_test_tool.utils.redact import redact_body, redact_headers

import pytest

from redfish_test_tool.exceptions import PollTimeout


def sample_results():
    return [
        TestResult("BI-01", "Service root", "basic", status="PASS", duration=0.5,
                   steps=[TestStep("GET ok", "200", "200", True)]),
        TestResult("BI-03", "Identity", "basic", status="FAIL", duration=0.2,
                   reason="SerialNumber missing",
                   steps=[TestStep("prop check", "non-empty", "None", False)]),
        TestResult("PC-03", "Shutdown", "power", status="SKIP",
                   reason="gated"),
    ]


ENV = {"BMC Host": "https://bmc.test:443", "Model": "R740"}
COUNTS = {"PASS": 1, "FAIL": 1, "SKIP": 1, "ERROR": 0}


def test_json_report(tmp_path):
    path = tmp_path / "results.json"
    write_json_report(path, sample_results(), ENV, COUNTS)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["summary"]["FAIL"] == 1
    assert data["results"][1]["reason"] == "SerialNumber missing"
    assert data["environment"]["Model"] == "R740"


def test_html_report_zh_tw(tmp_path):
    path = tmp_path / "report.html"
    write_html_report(path, sample_results(), ENV, COUNTS, lang="zh-TW")
    html = path.read_text(encoding="utf-8")
    assert "Redfish 測試報告" in html
    assert "BI-01" in html and "SerialNumber missing" in html
    assert 'class="badge FAIL"' in html


def test_html_report_en(tmp_path):
    path = tmp_path / "report.html"
    write_html_report(path, sample_results(), ENV, COUNTS, lang="en")
    assert "Redfish Test Report" in path.read_text(encoding="utf-8")


def test_redact():
    headers = redact_headers({"X-Auth-Token": "abc", "Accept": "json"})
    assert headers["X-Auth-Token"] == "***REDACTED***"
    assert headers["Accept"] == "json"
    body = redact_body('{"UserName": "u", "Password": "topsecret"}')
    assert "topsecret" not in body
    assert redact_body({"Password": "x"})["Password"] == "***REDACTED***"


def test_wait_for_success_and_timeout():
    values = iter([False, False, True])
    fake_time = [0]

    def clock():
        return fake_time[0]

    def sleep(s):
        fake_time[0] += s

    assert wait_for(lambda: next(values), timeout=100, interval=1,
                    sleep=sleep, clock=clock) is True
    with pytest.raises(PollTimeout):
        wait_for(lambda: False, timeout=10, interval=1, sleep=sleep, clock=clock)
