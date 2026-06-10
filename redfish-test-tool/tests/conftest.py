"""Shared fixtures: an in-memory mock BMC served through `responses`."""

import copy
import json
import re

import pytest
import responses

from redfish_test_tool.config import Config

BASE = "https://bmc.test:443"


def make_config(**overrides):
    cfg = Config(host="bmc.test", username="admin", password="secret")
    for key, value in overrides.items():
        setattr(cfg, key, value)
    return cfg


class MockBMC:
    """Stateful mock Redfish service dispatching GET/POST/PATCH/DELETE.

    Resources live in self.resources (path -> payload). Sessions, accounts and
    power state mutate live so transition/polling logic is fully exercised.
    """

    def __init__(self, resources):
        self.resources = copy.deepcopy(resources)
        self.sessions = {}
        self.session_counter = 0
        self.reset_calls = []
        # number of PowerState polls before a transition "completes"
        self.transition_delay_polls = 0
        self._pending_state = None
        self._polls_remaining = 0

    # -- request dispatch -----------------------------------------------------

    def handle(self, request):
        path = request.path_url.split("?")[0].rstrip("/") or "/"
        if path != "/redfish/v1":
            path = path
        body = json.loads(request.body) if request.body else {}
        method = request.method
        if method == "GET":
            return self._get(path, request)
        if method == "POST":
            return self._post(path, body, request)
        if method == "PATCH":
            return self._patch(path, body)
        if method == "DELETE":
            return self._delete(path, request)
        return 405, {}, ""

    def _authorized(self, request):
        token = request.headers.get("X-Auth-Token")
        auth = request.headers.get("Authorization")
        return token in self.sessions.values() or auth is not None

    def _get(self, path, request):
        norm = "/redfish/v1/" if path in ("/redfish/v1", "/redfish/v1/") else path
        if norm != "/redfish/v1/" and not self._authorized(request):
            return 401, {}, json.dumps({"error": "unauthorized"})
        self._tick_transition(norm)
        payload = self.resources.get(norm)
        if payload is None:
            return 404, {}, json.dumps({"error": "not found"})
        return 200, {}, json.dumps(payload)

    def _tick_transition(self, path):
        if self._pending_state and path == self._system_path():
            if self._polls_remaining > 0:
                self._polls_remaining -= 1
            else:
                self.resources[path]["PowerState"] = self._pending_state
                self._pending_state = None

    def _system_path(self):
        coll = self.resources.get("/redfish/v1/Systems", {})
        members = coll.get("Members", [])
        return members[0]["@odata.id"] if members else None

    def _post(self, path, body, request):
        if path.endswith("/SessionService/Sessions"):
            return self._create_session(body)
        if not self._authorized(request):
            return 401, {}, json.dumps({"error": "unauthorized"})
        if path.endswith("/ComputerSystem.Reset"):
            return self._reset(body)
        if path.endswith("/Accounts"):
            return self._create_account(path, body)
        if path.endswith("/LogService.ClearLog"):
            return self._clear_log(path)
        return 404, {}, json.dumps({"error": "not found"})

    def _create_session(self, body):
        if body.get("Password") != "secret" and body.get("UserName") == "admin":
            return 401, {}, json.dumps({"error": "bad credentials"})
        if body.get("UserName") not in ("admin", "rf_test_user"):
            return 401, {}, json.dumps({"error": "unknown user"})
        self.session_counter += 1
        sid = f"session{self.session_counter}"
        token = f"token-{sid}"
        self.sessions[sid] = token
        uri = f"/redfish/v1/SessionService/Sessions/{sid}"
        return (201,
                {"X-Auth-Token": token, "Location": uri},
                json.dumps({"@odata.id": uri, "Id": sid}))

    def _reset(self, body):
        reset_type = body.get("ResetType")
        self.reset_calls.append(reset_type)
        allowed = ("On", "ForceOff", "GracefulShutdown",
                   "GracefulRestart", "ForceRestart")
        if reset_type not in allowed:
            return 400, {}, json.dumps({"error": {"message": "bad ResetType"}})
        target = "On" if reset_type in ("On", "GracefulRestart", "ForceRestart") \
            else "Off"
        if self.transition_delay_polls:
            self._pending_state = target
            self._polls_remaining = self.transition_delay_polls
        else:
            self.resources[self._system_path()]["PowerState"] = target
        return 204, {}, ""

    def _create_account(self, path, body):
        uri = f"{path}/99"
        self.resources[uri] = {
            "@odata.id": uri, "Id": "99",
            "UserName": body.get("UserName"),
            "RoleId": body.get("RoleId"),
            "Enabled": body.get("Enabled", True),
        }
        self.resources[path]["Members"].append({"@odata.id": uri})
        return 201, {"Location": uri}, json.dumps(self.resources[uri])

    def _clear_log(self, path):
        entries_path = path.replace("/Actions/LogService.ClearLog", "/Entries")
        if entries_path in self.resources:
            self.resources[entries_path]["Members"] = []
        return 204, {}, ""

    def _patch(self, path, body):
        if path not in self.resources:
            return 404, {}, json.dumps({"error": "not found"})
        self.resources[path].update(body)
        return 200, {}, json.dumps(self.resources[path])

    def _delete(self, path, request):
        if "/SessionService/Sessions/" in path:
            sid = path.rstrip("/").split("/")[-1]
            self.sessions.pop(sid, None)
            return 204, {}, ""
        if path in self.resources:
            del self.resources[path]
            for coll in self.resources.values():
                members = coll.get("Members")
                if isinstance(members, list):
                    coll["Members"] = [m for m in members
                                       if m.get("@odata.id") != path]
            return 204, {}, ""
        return 404, {}, json.dumps({"error": "not found"})

    # -- responses wiring ---------------------------------------------------

    def install(self, rsps):
        pattern = re.compile(re.escape(BASE) + r"/redfish.*")
        for method in ("GET", "POST", "PATCH", "DELETE"):
            rsps.add_callback(
                method, pattern,
                callback=lambda req, self=self: self.handle(req),
                content_type="application/json",
            )


@pytest.fixture
def mock_bmc(idrac_like_tree):
    bmc = MockBMC(idrac_like_tree)
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        bmc.install(rsps)
        yield bmc


@pytest.fixture
def idrac_like_tree():
    return build_idrac_tree()


def build_idrac_tree():
    """A compact Dell iDRAC-flavored Redfish tree (legacy Thermal/Power)."""
    sys_uri = "/redfish/v1/Systems/System.Embedded.1"
    cha_uri = "/redfish/v1/Chassis/System.Embedded.1"
    mgr_uri = "/redfish/v1/Managers/iDRAC.Embedded.1"
    return {
        "/redfish/v1/": {
            "@odata.id": "/redfish/v1/",
            "@odata.type": "#ServiceRoot.v1_5_0.ServiceRoot",
            "Id": "RootService", "Name": "Root Service",
            "RedfishVersion": "1.6.0",
            "Systems": {"@odata.id": "/redfish/v1/Systems"},
            "Chassis": {"@odata.id": "/redfish/v1/Chassis"},
            "Managers": {"@odata.id": "/redfish/v1/Managers"},
            "SessionService": {"@odata.id": "/redfish/v1/SessionService"},
            "AccountService": {"@odata.id": "/redfish/v1/AccountService"},
            "Links": {"Sessions": {
                "@odata.id": "/redfish/v1/SessionService/Sessions"}},
        },
        "/redfish/v1/Systems": {
            "@odata.id": "/redfish/v1/Systems",
            "Members": [{"@odata.id": sys_uri}],
            "Members@odata.count": 1,
        },
        sys_uri: {
            "@odata.id": sys_uri,
            "@odata.type": "#ComputerSystem.v1_10_0.ComputerSystem",
            "Id": "System.Embedded.1", "Name": "System",
            "Manufacturer": "Dell Inc.", "Model": "PowerEdge R740",
            "SerialNumber": "CN123456", "BiosVersion": "2.10.2",
            "PowerState": "On",
            "Status": {"State": "Enabled", "Health": "OK", "HealthRollup": "OK"},
            "Actions": {"#ComputerSystem.Reset": {
                "target": sys_uri + "/Actions/ComputerSystem.Reset",
                "ResetType@Redfish.AllowableValues": [
                    "On", "ForceOff", "GracefulShutdown",
                    "GracefulRestart", "ForceRestart"],
            }},
            "LogServices": {"@odata.id": sys_uri + "/LogServices"},
        },
        "/redfish/v1/Chassis": {
            "@odata.id": "/redfish/v1/Chassis",
            "Members": [{"@odata.id": cha_uri}],
        },
        cha_uri: {
            "@odata.id": cha_uri,
            "@odata.type": "#Chassis.v1_10_0.Chassis",
            "Id": "System.Embedded.1", "Name": "Chassis",
            "Manufacturer": "Dell Inc.", "Model": "PowerEdge R740",
            "SerialNumber": "CN123456",
            "Status": {"State": "Enabled", "Health": "OK"},
            "Thermal": {"@odata.id": cha_uri + "/Thermal"},
            "Power": {"@odata.id": cha_uri + "/Power"},
        },
        cha_uri + "/Thermal": {
            "@odata.id": cha_uri + "/Thermal",
            "Temperatures": [
                {"Name": "CPU1 Temp", "ReadingCelsius": 45,
                 "LowerThresholdCritical": 3, "UpperThresholdCritical": 95,
                 "Status": {"State": "Enabled", "Health": "OK"}},
                {"Name": "Inlet Temp", "ReadingCelsius": 22,
                 "LowerThresholdCritical": -7, "UpperThresholdCritical": 47,
                 "Status": {"State": "Enabled", "Health": "OK"}},
            ],
            "Fans": [
                {"Name": "Fan1", "Reading": 4200, "ReadingUnits": "RPM",
                 "Status": {"State": "Enabled", "Health": "OK"}},
            ],
        },
        cha_uri + "/Power": {
            "@odata.id": cha_uri + "/Power",
            "Voltages": [
                {"Name": "PS1 Voltage", "ReadingVolts": 12.1,
                 "LowerThresholdCritical": 10.8, "UpperThresholdCritical": 13.2,
                 "Status": {"State": "Enabled", "Health": "OK"}},
            ],
            "PowerSupplies": [
                {"Name": "PS1", "PowerInputWatts": 180,
                 "Status": {"State": "Enabled", "Health": "OK"}},
            ],
        },
        "/redfish/v1/Managers": {
            "@odata.id": "/redfish/v1/Managers",
            "Members": [{"@odata.id": mgr_uri}],
        },
        mgr_uri: {
            "@odata.id": mgr_uri,
            "@odata.type": "#Manager.v1_5_0.Manager",
            "Id": "iDRAC.Embedded.1", "Name": "Manager",
            "FirmwareVersion": "5.10.50.00",
            "Status": {"State": "Enabled", "Health": "OK"},
            "LogServices": {"@odata.id": mgr_uri + "/LogServices"},
        },
        mgr_uri + "/LogServices": {
            "@odata.id": mgr_uri + "/LogServices",
            "Members": [{"@odata.id": mgr_uri + "/LogServices/Sel"}],
        },
        mgr_uri + "/LogServices/Sel": {
            "@odata.id": mgr_uri + "/LogServices/Sel",
            "Id": "Sel", "Name": "SEL Log Service",
            "Entries": {"@odata.id": mgr_uri + "/LogServices/Sel/Entries"},
            "Actions": {"#LogService.ClearLog": {
                "target": mgr_uri + "/LogServices/Sel/Actions/LogService.ClearLog"}},
        },
        mgr_uri + "/LogServices/Sel/Entries": {
            "@odata.id": mgr_uri + "/LogServices/Sel/Entries",
            "Members": [
                {"Created": "2026-01-01T00:00:00Z", "Severity": "OK",
                 "Message": "System boot"},
            ],
        },
        sys_uri + "/LogServices": {
            "@odata.id": sys_uri + "/LogServices",
            "Members": [],
        },
        "/redfish/v1/SessionService": {
            "@odata.id": "/redfish/v1/SessionService",
            "Sessions": {"@odata.id": "/redfish/v1/SessionService/Sessions"},
        },
        "/redfish/v1/SessionService/Sessions": {
            "@odata.id": "/redfish/v1/SessionService/Sessions",
            "Members": [],
        },
        "/redfish/v1/AccountService": {
            "@odata.id": "/redfish/v1/AccountService",
            "Accounts": {"@odata.id": "/redfish/v1/AccountService/Accounts"},
        },
        "/redfish/v1/AccountService/Accounts": {
            "@odata.id": "/redfish/v1/AccountService/Accounts",
            "Members": [{"@odata.id": "/redfish/v1/AccountService/Accounts/1"}],
        },
        "/redfish/v1/AccountService/Accounts/1": {
            "@odata.id": "/redfish/v1/AccountService/Accounts/1",
            "Id": "1", "UserName": "admin", "RoleId": "Administrator",
            "Enabled": True,
        },
    }
