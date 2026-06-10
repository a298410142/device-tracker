"""Live colored console output."""

import sys

from colorama import Fore, Style, just_fix_windows_console

from redfish_test_tool.runner import ERROR, FAIL, PASS, SKIP

COLORS = {
    PASS: Fore.GREEN,
    FAIL: Fore.RED,
    ERROR: Fore.RED + Style.BRIGHT,
    SKIP: Fore.YELLOW,
}


def setup_console():
    just_fix_windows_console()
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


class ConsoleReporter:
    def __init__(self, no_color=False):
        self.no_color = no_color

    def _paint(self, text, color):
        if self.no_color:
            return text
        return f"{color}{text}{Style.RESET_ALL}"

    def on_result(self, result):
        status = self._paint(f"[{result.status:5}]", COLORS.get(result.status, ""))
        line = f"{status} {result.test_id:6} {result.name}"
        if result.reason:
            line += f"  ({result.reason})"
        print(line, flush=True)

    def on_message(self, message):
        print(message, flush=True)

    def print_summary(self, counts, report_path=None):
        total = sum(counts.values())
        print()
        print(f"Total: {total}  "
              + self._paint(f"PASS: {counts[PASS]}", COLORS[PASS]) + "  "
              + self._paint(f"FAIL: {counts[FAIL]}", COLORS[FAIL]) + "  "
              + self._paint(f"ERROR: {counts[ERROR]}", COLORS[ERROR]) + "  "
              + self._paint(f"SKIP: {counts[SKIP]}", COLORS[SKIP]))
        if report_path:
            print(f"Report: {report_path}")
