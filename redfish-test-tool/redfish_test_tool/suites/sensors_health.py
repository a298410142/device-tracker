"""Suite 2: sensors and health checks (SH-01 ~ SH-09)."""

from redfish_test_tool.exceptions import RedfishError
from redfish_test_tool.runner import Suite

OK_HEALTH = ("OK", "Warning")


def _enabled(item):
    return (item.get("Status") or {}).get("State") == "Enabled"


class SensorsHealthSuite(Suite):
    suite_id = "sensors"
    title = "Sensors & Health"

    def collect(self, ctx):
        self.case("SH-01", "Legacy Thermal: temperatures within thresholds", self.sh01)
        self.case("SH-02", "Legacy Thermal: fans spinning and healthy", self.sh02)
        self.case("SH-03", "Legacy Power: voltages within thresholds", self.sh03)
        self.case("SH-04", "Legacy Power: power supplies healthy", self.sh04)
        self.case("SH-05", "Modern ThermalSubsystem fans", self.sh05)
        self.case("SH-06", "Modern PowerSubsystem power supplies", self.sh06)
        self.case("SH-07", "Sensors collection readings sane", self.sh07)
        self.case("SH-08", "Chassis/Manager component health", self.sh08)
        self.case("SH-09", "System health rollup", self.sh09)

    # -- helpers ------------------------------------------------------------

    def _chassis_resource(self, ctx, link_name):
        """Fetch the first chassis sub-resource of the given name, or None."""
        for uri, chassis in ctx.map.chassis_list:
            sub_uri = ctx.map.chassis_link(chassis, link_name)
            if sub_uri:
                try:
                    return ctx.map.fetch(sub_uri)
                except RedfishError:
                    continue
        return None

    @staticmethod
    def _within(reading, low, high):
        if reading is None:
            return True  # absent reading handled by caller
        if low is not None and reading <= low:
            return False
        if high is not None and reading >= high:
            return False
        return True

    # -- tests -------------------------------------------------------------

    def sh01(self, ctx):
        thermal = self._chassis_resource(ctx, "Thermal")
        if not thermal:
            ctx.skip("No legacy Thermal resource on any chassis")
        temps = [t for t in thermal.get("Temperatures", []) if _enabled(t)]
        if not temps:
            ctx.skip("No enabled temperature sensors")
        for t in temps:
            name = t.get("Name", t.get("MemberId", "?"))
            reading = t.get("ReadingCelsius")
            ctx.check(reading is not None, f"{name}: ReadingCelsius present",
                      expected="numeric reading", actual=repr(reading))
            low = t.get("LowerThresholdCritical")
            high = t.get("UpperThresholdCritical")
            ctx.check(self._within(reading, low, high),
                      f"{name}: within critical thresholds",
                      expected=f"({low}, {high})", actual=str(reading))

    def sh02(self, ctx):
        thermal = self._chassis_resource(ctx, "Thermal")
        if not thermal:
            ctx.skip("No legacy Thermal resource on any chassis")
        fans = [f for f in thermal.get("Fans", []) if _enabled(f)]
        if not fans:
            ctx.skip("No enabled fans in Thermal")
        for f in fans:
            name = f.get("Name", f.get("FanName", f.get("MemberId", "?")))
            reading = f.get("Reading")
            ctx.check(reading is not None and reading > 0,
                      f"{name}: fan reading > 0",
                      expected="> 0", actual=repr(reading))
            health = (f.get("Status") or {}).get("Health")
            ctx.check_in(health, OK_HEALTH, f"{name}: fan health acceptable")

    def sh03(self, ctx):
        power = self._chassis_resource(ctx, "Power")
        if not power:
            ctx.skip("No legacy Power resource on any chassis")
        voltages = [v for v in power.get("Voltages", []) if _enabled(v)]
        if not voltages:
            ctx.skip("No enabled voltage sensors")
        for v in voltages:
            name = v.get("Name", v.get("MemberId", "?"))
            reading = v.get("ReadingVolts")
            low = v.get("LowerThresholdCritical")
            high = v.get("UpperThresholdCritical")
            ctx.check(self._within(reading, low, high),
                      f"{name}: voltage within critical thresholds",
                      expected=f"({low}, {high})", actual=str(reading))

    def sh04(self, ctx):
        power = self._chassis_resource(ctx, "Power")
        if not power:
            ctx.skip("No legacy Power resource on any chassis")
        psus = power.get("PowerSupplies", [])
        if not psus:
            ctx.skip("No PowerSupplies in Power resource")
        for psu in psus:
            name = psu.get("Name", psu.get("MemberId", "?"))
            status = psu.get("Status") or {}
            if status.get("State") != "Enabled":
                ctx.step(f"{name}: not enabled, skipped", ok=True)
                continue
            ctx.check_in(status.get("Health"), OK_HEALTH,
                         f"{name}: PSU health acceptable")
            watts = psu.get("PowerInputWatts", psu.get("LastPowerOutputWatts"))
            ctx.step(f"{name}: input watts (informational)",
                     expected="-", actual=repr(watts))

    def sh05(self, ctx):
        subsystem = self._chassis_resource(ctx, "ThermalSubsystem")
        if not subsystem:
            ctx.skip("No ThermalSubsystem (modern model) on any chassis")
        fans_uri = (subsystem.get("Fans") or {}).get("@odata.id")
        if not fans_uri:
            ctx.skip("ThermalSubsystem has no Fans collection")
        coll = ctx.map.fetch(fans_uri)
        members = coll.get("Members", [])
        ctx.check(members, "ThermalSubsystem Fans collection non-empty",
                  expected=">= 1 fan", actual=f"{len(members)} fans")
        for member in members:
            fan = ctx.map.fetch(member["@odata.id"])
            name = fan.get("Name", fan.get("Id", "?"))
            health = (fan.get("Status") or {}).get("Health")
            ctx.check_in(health, OK_HEALTH, f"{name}: fan health acceptable")

    def sh06(self, ctx):
        subsystem = self._chassis_resource(ctx, "PowerSubsystem")
        if not subsystem:
            ctx.skip("No PowerSubsystem (modern model) on any chassis")
        psu_uri = (subsystem.get("PowerSupplies") or {}).get("@odata.id")
        if not psu_uri:
            ctx.skip("PowerSubsystem has no PowerSupplies collection")
        coll = ctx.map.fetch(psu_uri)
        for member in coll.get("Members", []):
            psu = ctx.map.fetch(member["@odata.id"])
            name = psu.get("Name", psu.get("Id", "?"))
            status = psu.get("Status") or {}
            if status.get("State") != "Enabled":
                continue
            ctx.check_in(status.get("Health"), OK_HEALTH,
                         f"{name}: PSU health acceptable")

    def sh07(self, ctx):
        sensors = self._chassis_resource(ctx, "Sensors")
        if not sensors:
            ctx.skip("No Sensors collection on any chassis")
        members = sensors.get("Members", [])
        if not members:
            ctx.skip("Sensors collection is empty")
        for member in members:
            sensor = ctx.map.fetch(member["@odata.id"])
            name = sensor.get("Name", sensor.get("Id", "?"))
            reading = sensor.get("Reading")
            ctx.check(reading is None or isinstance(reading, (int, float)),
                      f"{name}: Reading is numeric or absent",
                      expected="number/None", actual=repr(reading))
            health = (sensor.get("Status") or {}).get("Health")
            ctx.check(health != "Critical", f"{name}: not Critical",
                      expected="not Critical", actual=repr(health))

    def sh08(self, ctx):
        components = [("Chassis " + uri.rstrip("/").split("/")[-1], payload)
                      for uri, payload in ctx.map.chassis_list]
        if ctx.map.manager:
            components.append(("Manager", ctx.map.manager))
        if not components:
            ctx.skip("No chassis or manager resources discovered")
        for name, payload in components:
            status = payload.get("Status") or {}
            if status.get("State") not in (None, "Enabled"):
                ctx.step(f"{name}: state {status.get('State')}, health not checked",
                         ok=True)
                continue
            ctx.check_in(status.get("Health"), OK_HEALTH,
                         f"{name}: health acceptable")

    def sh09(self, ctx):
        system = ctx.map.refresh_system()
        status = system.get("Status") or {}
        rollup = status.get("HealthRollup", status.get("Health"))
        ctx.check(rollup is not None, "System health rollup readable",
                  expected="Health value", actual=repr(rollup))
        ctx.check_in(rollup, OK_HEALTH, "System health rollup OK/Warning")
        if rollup == "Warning":
            ctx.step("System health is Warning (passed with warning)", ok=True)
