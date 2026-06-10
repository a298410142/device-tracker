"""Suite 1: basic resource info queries (BI-01 ~ BI-08)."""

from redfish_test_tool.discovery import odata_id
from redfish_test_tool.runner import Suite


class BasicInfoSuite(Suite):
    suite_id = "basic"
    title = "Basic Info"

    def collect(self, ctx):
        self.case("BI-01", "Service Root reachable with required links", self.bi01)
        self.case("BI-02", "Systems collection has members", self.bi02)
        self.case("BI-03", "System has identity properties", self.bi03)
        self.case("BI-04", "System BiosVersion present", self.bi04)
        self.case("BI-05", "Chassis identity properties", self.bi05)
        self.case("BI-06", "Manager (BMC) firmware version and health", self.bi06)
        self.case("BI-07", "OData sanity on core resources", self.bi07)
        self.case("BI-08", "Nonexistent resource returns 404", self.bi08)

    def bi01(self, ctx):
        resp = ctx.client.get("/redfish/v1/")
        ctx.check_status(resp, 200, "GET service root")
        root = resp.json()
        ctx.check_prop(root, "RedfishVersion", "ServiceRoot")
        for link in ("Systems", "Chassis", "Managers"):
            ctx.check(odata_id(root.get(link)), f"ServiceRoot has {link} link",
                      expected="@odata.id present", actual=str(root.get(link)))

    def bi02(self, ctx):
        uri = odata_id(ctx.map.root.get("Systems"))
        coll = ctx.client.get_json(uri)
        count = len(coll.get("Members", []))
        ctx.check(count >= 1, "Systems collection has at least one member",
                  expected=">= 1 member", actual=f"{count} members")
        for member in coll.get("Members", []):
            resp = ctx.client.get(odata_id(member))
            ctx.check_status(resp, 200, f"Member {odata_id(member)} resolvable")

    def bi03(self, ctx):
        system = ctx.map.system
        for prop in ("Manufacturer", "Model", "SerialNumber", "PowerState"):
            ctx.check_prop(system, prop, "System")
        ctx.check(isinstance(system.get("Status"), dict), "System.Status present",
                  expected="Status object", actual=str(system.get("Status")))

    def bi04(self, ctx):
        ctx.check_prop(ctx.map.system, "BiosVersion", "System")

    def bi05(self, ctx):
        if not ctx.map.chassis_list:
            ctx.skip("No Chassis members found")
        uri, chassis = ctx.map.chassis_list[0]
        ctx.check_prop(chassis, "Manufacturer", "Chassis")
        # Model/SerialNumber can legitimately be absent on some chassis types
        for prop in ("Model", "SerialNumber"):
            value = chassis.get(prop)
            ctx.step(f"Chassis.{prop} (informational)",
                     expected="non-empty preferred", actual=repr(value),
                     ok=value not in (None, ""))

    def bi06(self, ctx):
        if not ctx.map.manager:
            ctx.skip("No Managers members found")
        manager = ctx.map.manager
        ctx.check_prop(manager, "FirmwareVersion", "Manager")
        health = (manager.get("Status") or {}).get("Health")
        ctx.check(health is not None, "Manager.Status.Health readable",
                  expected="Health value", actual=repr(health))

    def bi07(self, ctx):
        targets = [("ServiceRoot", "/redfish/v1/", ctx.map.root),
                   ("System", ctx.map.system_uri, ctx.map.system)]
        if ctx.map.manager:
            targets.append(("Manager", ctx.map.manager_uri, ctx.map.manager))
        for name, uri, payload in targets:
            ctx.check_prop(payload, "@odata.id", name)
            got = payload["@odata.id"].rstrip("/")
            ctx.check_eq(got, uri.rstrip("/"), f"{name} @odata.id matches request URI")
            if name != "ServiceRoot":
                ctx.check_prop(payload, "@odata.type", name)
                ctx.check_prop(payload, "Id", name)
                ctx.check_prop(payload, "Name", name)

    def bi08(self, ctx):
        resp = ctx.client.get("/redfish/v1/NonExistentResource_RFTEST")
        ctx.check_status(resp, 404, "GET nonexistent resource returns 404")
