"""Render the self-contained HTML report via Jinja2."""

import sys
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

LABELS = {
    "zh-TW": {
        "title": "Redfish 測試報告",
        "environment": "測試環境",
        "summary": "測試結果摘要",
        "total": "總計",
        "pass": "通過",
        "fail": "失敗",
        "error": "錯誤",
        "skip": "略過",
        "results": "測試結果明細",
        "test_id": "編號",
        "test_name": "測試項目",
        "suite": "套件",
        "status": "結果",
        "duration": "耗時(秒)",
        "reason": "原因",
        "steps": "步驟",
        "expected": "預期",
        "actual": "實際",
        "generated": "產生時間",
        "host": "BMC 位址",
    },
    "en": {
        "title": "Redfish Test Report",
        "environment": "Environment",
        "summary": "Summary",
        "total": "Total",
        "pass": "Pass",
        "fail": "Fail",
        "error": "Error",
        "skip": "Skip",
        "results": "Test Results",
        "test_id": "ID",
        "test_name": "Test",
        "suite": "Suite",
        "status": "Status",
        "duration": "Duration (s)",
        "reason": "Reason",
        "steps": "Steps",
        "expected": "Expected",
        "actual": "Actual",
        "generated": "Generated",
        "host": "BMC Host",
    },
}


def _template_dir():
    # PyInstaller onefile extracts bundled data under sys._MEIPASS
    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS) / "redfish_test_tool" / "reporting"
    else:
        base = Path(__file__).parent
    return base / "templates"


def write_html_report(path, results, environment, counts, lang="zh-TW"):
    env = Environment(
        loader=FileSystemLoader(str(_template_dir())),
        autoescape=select_autoescape(["html"]),
    )
    template = env.get_template("report.html.j2")
    labels = LABELS.get(lang, LABELS["zh-TW"])
    html = template.render(
        labels=labels,
        environment=environment,
        counts=counts,
        results=results,
        generated=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )
    Path(path).write_text(html, encoding="utf-8")
    return path
