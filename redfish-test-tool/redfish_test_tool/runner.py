"""Test model and sequential suite runner."""

import time
import traceback
from dataclasses import dataclass, field

from redfish_test_tool.exceptions import AssertionFailure, PollTimeout, RedfishError

PASS, FAIL, SKIP, ERROR = "PASS", "FAIL", "SKIP", "ERROR"


@dataclass
class TestStep:
    message: str
    expected: str = ""
    actual: str = ""
    ok: bool = True


@dataclass
class TestResult:
    test_id: str
    name: str
    suite: str
    status: str = PASS
    reason: str = ""
    duration: float = 0.0
    steps: list = field(default_factory=list)


class TestContext:
    """Shared state handed to every test: client, service map, config, steps."""

    def __init__(self, client, service_map, config):
        self.client = client
        self.map = service_map
        self.config = config
        self._steps = None  # bound to the running test's step list

    # -- step recording -------------------------------------------------------

    def step(self, message, expected="", actual="", ok=True):
        if self._steps is not None:
            self._steps.append(TestStep(str(message), str(expected), str(actual), ok))

    # -- assertion helpers ------------------------------------------------------

    def check(self, condition, message, expected="", actual=""):
        self.step(message, expected, actual, ok=bool(condition))
        if not condition:
            raise AssertionFailure(message, expected=expected, actual=actual)

    def check_eq(self, actual, expected, message):
        self.check(actual == expected, message, expected=expected, actual=actual)

    def check_in(self, actual, allowed, message):
        self.check(actual in allowed, message,
                   expected=f"one of {sorted(allowed)}", actual=actual)

    def check_status(self, resp, allowed, message):
        allowed = (allowed,) if isinstance(allowed, int) else tuple(allowed)
        self.check(resp.status_code in allowed, message,
                   expected=f"HTTP {' or '.join(map(str, allowed))}",
                   actual=f"HTTP {resp.status_code}")

    def check_prop(self, payload, prop, resource_name):
        """Property must exist and be non-empty."""
        value = payload.get(prop)
        self.check(value not in (None, ""),
                   f"{resource_name}.{prop} present and non-empty",
                   expected="non-empty value", actual=repr(value))
        return value

    def skip(self, reason):
        raise SkipTest(reason)


class SkipTest(Exception):
    """Raised inside a test body to mark the test as SKIP."""


@dataclass
class TestCase:
    test_id: str
    name: str
    func: object            # callable(ctx) -> None
    gated: bool = False     # requires an explicit safety flag


class Suite:
    """Ordered list of test cases. Subclasses populate self.tests."""

    suite_id = ""
    title = ""
    abort_on_failure = False  # power suite stops on failed transition

    def __init__(self):
        self.tests = []

    def case(self, test_id, name, func, gated=False):
        self.tests.append(TestCase(test_id, name, func, gated))

    def collect(self, ctx):
        """Populate self.tests; called once before the suite runs."""
        raise NotImplementedError

    def gate_reason(self, ctx):
        """Return a skip reason if the whole gated suite must be skipped, else None."""
        return None

    def teardown(self, ctx):
        """Always called after the suite, even on abort."""


class SuiteRunner:
    def __init__(self, ctx, reporters=()):
        self.ctx = ctx
        self.reporters = list(reporters)
        self.results = []

    def run_suite(self, suite):
        suite.collect(self.ctx)
        gate_reason = suite.gate_reason(self.ctx)
        selected = self.ctx.config.tests
        aborted = False
        for case in suite.tests:
            if selected and case.test_id.upper() not in selected:
                continue
            if gate_reason or (case.gated and not self._gate_open(case)):
                reason = gate_reason or self._gate_hint(case)
                result = TestResult(case.test_id, case.name, suite.suite_id,
                                    status=SKIP, reason=reason)
            elif aborted:
                result = TestResult(case.test_id, case.name, suite.suite_id,
                                    status=SKIP,
                                    reason="Previous power transition failed; aborted")
            else:
                result = self._run_case(suite, case)
                if suite.abort_on_failure and result.status in (FAIL, ERROR):
                    aborted = True
            self.results.append(result)
            for reporter in self.reporters:
                reporter.on_result(result)
        try:
            suite.teardown(self.ctx)
        except Exception as exc:  # teardown must never crash the run
            for reporter in self.reporters:
                reporter.on_message(f"[{suite.suite_id}] teardown warning: {exc}")

    def _gate_open(self, case):
        return self.ctx.config.include_destructive

    @staticmethod
    def _gate_hint(case):
        return "Destructive test; pass --include-destructive to run"

    def _run_case(self, suite, case):
        result = TestResult(case.test_id, case.name, suite.suite_id)
        self.ctx._steps = result.steps
        start = time.monotonic()
        try:
            case.func(self.ctx)
            result.status = PASS
        except SkipTest as exc:
            result.status = SKIP
            result.reason = str(exc)
        except AssertionFailure as exc:
            result.status = FAIL
            result.reason = str(exc)
        except PollTimeout as exc:
            result.status = FAIL
            result.reason = str(exc)
        except RedfishError as exc:
            result.status = FAIL
            result.reason = str(exc)
        except Exception as exc:
            result.status = ERROR
            result.reason = f"{type(exc).__name__}: {exc}"
            result.steps.append(TestStep(traceback.format_exc(limit=5), ok=False))
        finally:
            result.duration = time.monotonic() - start
            self.ctx._steps = None
        return result

    def summary(self):
        counts = {PASS: 0, FAIL: 0, SKIP: 0, ERROR: 0}
        for r in self.results:
            counts[r.status] += 1
        return counts

    @property
    def exit_code(self):
        counts = self.summary()
        return 1 if (counts[FAIL] or counts[ERROR]) else 0
