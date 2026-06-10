from redfish_test_tool.config import Config
from redfish_test_tool.exceptions import AssertionFailure
from redfish_test_tool.runner import (ERROR, FAIL, PASS, SKIP, Suite,
                                      SuiteRunner, TestContext)


class DummySuite(Suite):
    suite_id = "dummy"

    def collect(self, ctx):
        self.case("D-01", "passes", lambda c: c.check(True, "always true"))
        self.case("D-02", "fails", lambda c: c.check(False, "always false",
                                                     expected="x", actual="y"))
        self.case("D-03", "skips", lambda c: c.skip("not applicable"))
        self.case("D-04", "errors", self._boom)
        self.case("D-05", "gated", lambda c: None, gated=True)

    @staticmethod
    def _boom(ctx):
        raise ValueError("unexpected")


def make_ctx(**cfg_overrides):
    cfg = Config(host="h", username="u", password="p")
    for k, v in cfg_overrides.items():
        setattr(cfg, k, v)
    return TestContext(client=None, service_map=None, config=cfg)


def test_statuses_and_exit_code():
    runner = SuiteRunner(make_ctx())
    runner.run_suite(DummySuite())
    statuses = {r.test_id: r.status for r in runner.results}
    assert statuses == {"D-01": PASS, "D-02": FAIL, "D-03": SKIP,
                        "D-04": ERROR, "D-05": SKIP}
    assert runner.exit_code == 1
    counts = runner.summary()
    assert counts[PASS] == 1 and counts[FAIL] == 1
    assert counts[SKIP] == 2 and counts[ERROR] == 1


def test_gated_runs_with_destructive_flag():
    runner = SuiteRunner(make_ctx(include_destructive=True))
    runner.run_suite(DummySuite())
    statuses = {r.test_id: r.status for r in runner.results}
    assert statuses["D-05"] == PASS


def test_tests_filter():
    runner = SuiteRunner(make_ctx(tests=["D-01"]))
    runner.run_suite(DummySuite())
    assert [r.test_id for r in runner.results] == ["D-01"]
    assert runner.exit_code == 0


def test_failure_steps_recorded():
    runner = SuiteRunner(make_ctx())
    runner.run_suite(DummySuite())
    fail = next(r for r in runner.results if r.test_id == "D-02")
    assert fail.steps and fail.steps[-1].ok is False
    assert fail.steps[-1].expected == "x"


class AbortingSuite(Suite):
    suite_id = "abort"
    abort_on_failure = True

    def collect(self, ctx):
        self.case("A-01", "fails", lambda c: c.check(False, "boom"))
        self.case("A-02", "never runs", lambda c: c.check(True, "ok"))


def test_abort_on_failure():
    runner = SuiteRunner(make_ctx())
    runner.run_suite(AbortingSuite())
    statuses = {r.test_id: r.status for r in runner.results}
    assert statuses["A-01"] == FAIL
    assert statuses["A-02"] == SKIP
