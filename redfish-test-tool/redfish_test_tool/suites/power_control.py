"""Suite 3: power control via ComputerSystem.Reset (PC-01 ~ PC-10).

The whole suite is gated behind --include-power-tests because it changes the
power state of real hardware. Transitions are verified by polling PowerState.
A failed transition aborts the remaining tests (abort_on_failure) and the
teardown attempts to restore the initial power state.
"""

from redfish_test_tool.exceptions import RedfishError
from redfish_test_tool.runner import Suite
from redfish_test_tool.utils.polling import wait_for


class PowerControlSuite(Suite):
    suite_id = "power"
    title = "Power Control"
    abort_on_failure = True

    def __init__(self):
        super().__init__()
        self.reset_target = None
        self.allowed = None
        self.initial_state = None

    def collect(self, ctx):
        self.case("PC-01", "Reset action discoverable", self.pc01)
        self.case("PC-02", "Record initial state; ensure powered On", self.pc02)
        self.case("PC-03", "GracefulShutdown transitions to Off", self.pc03)
        self.case("PC-04", "On transitions to On", self.pc04)
        self.case("PC-05", "ForceOff transitions to Off", self.pc05)
        self.case("PC-06", "On (restore) transitions to On", self.pc06)
        self.case("PC-07", "ForceRestart accepted, returns to On", self.pc07)
        self.case("PC-08", "GracefulRestart accepted, returns to On", self.pc08)
        self.case("PC-09", "Invalid ResetType rejected with 4xx", self.pc09)
        self.case("PC-10", "Initial power state restored", self.pc10)

    def gate_reason(self, ctx):
        if not ctx.config.include_power_tests:
            return "Power tests change machine state; pass --include-power-tests"
        return None

    # -- helpers ------------------------------------------------------------

    def _power_state(self, ctx):
        return ctx.map.refresh_system().get("PowerState")

    def _reset(self, ctx, reset_type):
        resp = ctx.client.post(self.reset_target, json={"ResetType": reset_type})
        ctx.check_status(resp, (200, 202, 204), f"POST Reset {reset_type} accepted")
        if resp.status_code == 202:
            self._await_task(ctx, resp)
        return resp

    def _await_task(self, ctx, resp):
        """Poll a Task monitor returned by a 202 response until it finishes."""
        monitor = resp.headers.get("Location")
        if not monitor:
            return
        def task_done():
            task_resp = ctx.client.get(monitor)
            if task_resp.status_code in (200, 201):
                state = task_resp.json().get("TaskState")
                return state in ("Completed", "Exception", "Cancelled", None)
            return task_resp.status_code == 204
        wait_for(task_done, timeout=ctx.config.power_timeout,
                 description="task monitor completion")

    def _wait_state(self, ctx, expected, timeout=None):
        timeout = timeout or ctx.config.power_timeout
        wait_for(lambda: self._power_state(ctx) == expected,
                 timeout=timeout, interval=5,
                 description=f"PowerState == {expected}")
        ctx.step(f"PowerState reached {expected}", expected=expected, actual=expected)

    def _supported(self, ctx, reset_type):
        if self.allowed is not None and reset_type not in self.allowed:
            ctx.skip(f"ResetType {reset_type} not in AllowableValues")

    # -- tests --------------------------------------------------------------

    def pc01(self, ctx):
        self.reset_target, self.allowed = ctx.map.reset_action()
        ctx.check(self.reset_target, "Reset action target URI found",
                  expected="target URI", actual=str(self.reset_target))
        ctx.step("AllowableValues", expected="-", actual=str(self.allowed))

    def pc02(self, ctx):
        if not self.reset_target:
            ctx.skip("Reset action not discovered (PC-01)")
        self.initial_state = self._power_state(ctx)
        ctx.step("Initial PowerState recorded",
                 expected="-", actual=str(self.initial_state))
        if self.initial_state != "On":
            self._supported(ctx, "On")
            self._reset(ctx, "On")
            self._wait_state(ctx, "On")

    def pc03(self, ctx):
        self._supported(ctx, "GracefulShutdown")
        self._reset(ctx, "GracefulShutdown")
        # OS-dependent: give it the full timeout; a hung OS fails here clearly
        self._wait_state(ctx, "Off")

    def pc04(self, ctx):
        self._supported(ctx, "On")
        self._reset(ctx, "On")
        self._wait_state(ctx, "On")

    def pc05(self, ctx):
        self._supported(ctx, "ForceOff")
        self._reset(ctx, "ForceOff")
        self._wait_state(ctx, "Off")

    def pc06(self, ctx):
        self._supported(ctx, "On")
        self._reset(ctx, "On")
        self._wait_state(ctx, "On")
        ctx.step(f"Waiting boot_wait={ctx.config.boot_wait}s before restart tests")
        import time
        time.sleep(ctx.config.boot_wait)

    def pc07(self, ctx):
        self._supported(ctx, "ForceRestart")
        self._reset(ctx, "ForceRestart")
        self._wait_state(ctx, "On")

    def pc08(self, ctx):
        self._supported(ctx, "GracefulRestart")
        self._reset(ctx, "GracefulRestart")
        self._wait_state(ctx, "On")

    def pc09(self, ctx):
        resp = ctx.client.post(self.reset_target,
                               json={"ResetType": "BogusValue_RFTEST"})
        ctx.check(400 <= resp.status_code < 500,
                  "Invalid ResetType rejected with 4xx",
                  expected="HTTP 4xx", actual=f"HTTP {resp.status_code}")

    def pc10(self, ctx):
        if self.initial_state is None:
            ctx.skip("Initial state unknown (PC-02 did not run)")
        current = self._power_state(ctx)
        if current != self.initial_state:
            self._reset(ctx, "On" if self.initial_state == "On" else "ForceOff")
            self._wait_state(ctx, self.initial_state)
        ctx.check_eq(self._power_state(ctx), self.initial_state,
                     "PowerState restored to initial value")

    def teardown(self, ctx):
        """Best-effort restore if the suite aborted mid-way."""
        if not self.reset_target or self.initial_state is None:
            return
        try:
            current = self._power_state(ctx)
            if current != self.initial_state:
                reset_type = "On" if self.initial_state == "On" else "ForceOff"
                ctx.client.post(self.reset_target, json={"ResetType": reset_type})
        except RedfishError:
            pass
