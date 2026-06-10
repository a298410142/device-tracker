"""Suite 4: sessions, accounts, and SEL (AS-01 ~ AS-10).

Sessions/accounts created here are secondary objects, separate from the
runner's own session, and are removed in per-test try/finally plus a final
suite teardown so failures never leave debris on the BMC.
"""

import secrets
import string

import requests

from redfish_test_tool.exceptions import RedfishError
from redfish_test_tool.runner import Suite

TEST_USERNAME = "rf_test_user"


def _gen_password():
    """BMC-friendly generated password: upper/lower/digit/special, 16 chars."""
    alphabet = string.ascii_letters + string.digits
    core = "".join(secrets.choice(alphabet) for _ in range(12))
    return f"Rf1!{core}"


class AccountsSessionsSelSuite(Suite):
    suite_id = "accounts"
    title = "Accounts / Sessions / SEL"

    def __init__(self):
        super().__init__()
        self.test_account_uri = None
        self.test_password = _gen_password()
        self.sel = None  # (owner, uri, payload)

    def collect(self, ctx):
        self.case("AS-01", "Session create returns token", self.as01)
        self.case("AS-02", "New token grants access", self.as02)
        self.case("AS-03", "Session delete invalidates token", self.as03)
        self.case("AS-04", "Wrong password rejected with 401", self.as04)
        self.case("AS-05", "Account list enumerable", self.as05)
        self.case("AS-06", "Test account creation", self.as06)
        self.case("AS-07", "Test account can authenticate", self.as07)
        self.case("AS-08", "Test account deletion", self.as08)
        self.case("AS-09", "SEL entries readable", self.as09)
        self.case("AS-10", "SEL ClearLog empties the log", self.as10, gated=True)

    # -- session helpers ------------------------------------------------------

    def _sessions_uri(self, ctx):
        uri = ctx.map.sessions_collection_uri()
        if not uri:
            ctx.skip("SessionService/Sessions collection not found")
        return uri

    def _create_session(self, ctx, username, password):
        """Create a secondary session; returns (token, session_uri, response)."""
        resp = ctx.client.post(self._sessions_uri(ctx),
                               json={"UserName": username, "Password": password})
        token = resp.headers.get("X-Auth-Token")
        return token, resp.headers.get("Location"), resp

    def _raw_get(self, ctx, path, token):
        """GET using ONLY the given token (no runner credentials)."""
        url = path if path.startswith("http") else ctx.config.base_url + path
        return requests.get(url, headers={"X-Auth-Token": token},
                            verify=ctx.config.ssl_verify,
                            timeout=ctx.config.timeout)

    # -- tests ----------------------------------------------------------------

    def as01(self, ctx):
        token, session_uri, resp = self._create_session(
            ctx, ctx.config.username, ctx.config.password)
        try:
            ctx.check_status(resp, (200, 201), "POST Sessions")
            ctx.check(token, "X-Auth-Token header returned",
                      expected="token", actual="present" if token else "missing")
            ctx.check(session_uri, "Location header returned",
                      expected="session URI", actual=str(session_uri))
        finally:
            if token and session_uri:
                ctx.client.request("DELETE", session_uri,
                                   headers={"X-Auth-Token": token})

    def as02(self, ctx):
        token, session_uri, resp = self._create_session(
            ctx, ctx.config.username, ctx.config.password)
        if not token:
            ctx.skip("Could not create secondary session")
        try:
            probe = self._raw_get(ctx, ctx.map.system_uri, token)
            ctx.check_status(probe, 200, "GET System with new token only")
        finally:
            if session_uri:
                ctx.client.request("DELETE", session_uri,
                                   headers={"X-Auth-Token": token})

    def as03(self, ctx):
        token, session_uri, resp = self._create_session(
            ctx, ctx.config.username, ctx.config.password)
        if not (token and session_uri):
            ctx.skip("Could not create secondary session")
        del_resp = ctx.client.request("DELETE", session_uri,
                                      headers={"X-Auth-Token": token})
        ctx.check_status(del_resp, (200, 204), "DELETE session")
        probe = self._raw_get(ctx, ctx.map.system_uri, token)
        ctx.check_status(probe, 401, "Deleted token rejected")

    def as04(self, ctx):
        token, session_uri, resp = self._create_session(
            ctx, ctx.config.username, "WrongPassword_RFTEST_123!")
        if token and session_uri:  # should not happen; clean up if it does
            ctx.client.request("DELETE", session_uri,
                               headers={"X-Auth-Token": token})
        ctx.check_status(resp, 401, "Session create with wrong password")
        ctx.check(not token, "No token leaked on auth failure",
                  expected="no token", actual="token issued!" if token else "no token")

    # -- accounts -------------------------------------------------------------

    def as05(self, ctx):
        uri = ctx.map.accounts_collection_uri()
        if not uri:
            ctx.skip("AccountService/Accounts not found")
        coll = ctx.client.get_json(uri)
        members = coll.get("Members", [])
        ctx.check(members, "Accounts collection non-empty",
                  expected=">= 1 account", actual=f"{len(members)} accounts")
        usernames = []
        for member in members:
            acct = ctx.client.get_json(member["@odata.id"])
            if acct.get("UserName"):
                usernames.append(acct["UserName"])
        ctx.step("Enumerated accounts", expected="-", actual=", ".join(usernames))

    def as06(self, ctx):
        uri = ctx.map.accounts_collection_uri()
        if not uri:
            ctx.skip("AccountService/Accounts not found")
        body = {"UserName": TEST_USERNAME, "Password": self.test_password,
                "RoleId": "ReadOnly", "Enabled": True}
        resp = ctx.client.post(uri, json=body)
        if resp.status_code in (200, 201, 204):
            self.test_account_uri = resp.headers.get("Location")
        elif resp.status_code == 405:
            # Dell-style: PATCH credentials into a pre-allocated empty slot
            ctx.step("POST returned 405; trying PATCH-into-empty-slot fallback")
            self._patch_empty_slot(ctx, uri, body)
        else:
            ctx.check_status(resp, (200, 201, 204), "POST new account")
        if not self.test_account_uri:
            self.test_account_uri = self._find_account_uri(ctx, uri, TEST_USERNAME)
        ctx.check(self.test_account_uri, "Test account exists in collection",
                  expected="account URI", actual=str(self.test_account_uri))

    def _patch_empty_slot(self, ctx, collection_uri, body):
        coll = ctx.client.get_json(collection_uri)
        for member in coll.get("Members", []):
            acct_uri = member["@odata.id"]
            acct = ctx.client.get_json(acct_uri)
            if not acct.get("UserName") and not acct.get("Enabled"):
                resp = ctx.client.patch(acct_uri, json=body)
                if resp.status_code in (200, 204):
                    self.test_account_uri = acct_uri
                    return

    def _find_account_uri(self, ctx, collection_uri, username):
        coll = ctx.client.get_json(collection_uri)
        for member in coll.get("Members", []):
            acct = ctx.client.get_json(member["@odata.id"])
            if acct.get("UserName") == username:
                return member["@odata.id"]
        return None

    def as07(self, ctx):
        if not self.test_account_uri:
            ctx.skip("Test account was not created (AS-06)")
        token, session_uri, resp = self._create_session(
            ctx, TEST_USERNAME, self.test_password)
        try:
            ctx.check_status(resp, (200, 201), "Session create as test account")
            ctx.check(token, "Test account received a token",
                      expected="token", actual="present" if token else "missing")
        finally:
            if token and session_uri:
                ctx.client.request("DELETE", session_uri,
                                   headers={"X-Auth-Token": token})

    def as08(self, ctx):
        if not self.test_account_uri:
            ctx.skip("Test account was not created (AS-06)")
        resp = self._delete_account(ctx)
        ctx.check_status(resp, (200, 204), "DELETE test account")
        uri = ctx.map.accounts_collection_uri()
        ctx.check(not self._find_account_uri(ctx, uri, TEST_USERNAME),
                  "Test account gone from collection",
                  expected="absent", actual="still present" if
                  self._find_account_uri(ctx, uri, TEST_USERNAME) else "absent")
        self.test_account_uri = None

    def _delete_account(self, ctx):
        resp = ctx.client.delete(self.test_account_uri)
        if resp.status_code == 405:
            # Dell-style slots: disable instead of delete
            resp = ctx.client.patch(self.test_account_uri,
                                    json={"UserName": "", "Enabled": False})
        return resp

    # -- SEL --------------------------------------------------------------------

    def as09(self, ctx):
        self.sel = ctx.map.find_sel()
        if not self.sel:
            ctx.skip("No LogServices found on Manager or System")
        owner, uri, payload = self.sel
        ctx.step(f"Using log service on {owner}", expected="-",
                 actual=f"{payload.get('Id', '?')} ({uri})")
        entries_uri = (payload.get("Entries") or {}).get("@odata.id")
        ctx.check(entries_uri, "LogService has Entries link",
                  expected="Entries URI", actual=str(entries_uri))
        resp = ctx.client.get(entries_uri)
        ctx.check_status(resp, 200, "GET log entries")
        entries = resp.json().get("Members", [])
        ctx.step("Entry count", expected="-", actual=str(len(entries)))
        for entry in entries[:5]:
            ctx.check("Created" in entry or "EventTimestamp" in entry,
                      "Entry has timestamp", expected="Created/EventTimestamp",
                      actual=str(sorted(set(entry) & {"Created", "EventTimestamp"})))
            ctx.check("Severity" in entry, "Entry has Severity",
                      expected="Severity", actual=str(entry.get("Severity")))
            ctx.check("Message" in entry, "Entry has Message",
                      expected="Message", actual="present" if "Message" in entry
                      else "missing")

    def as10(self, ctx):
        if not self.sel:
            self.sel = ctx.map.find_sel()
        if not self.sel:
            ctx.skip("No LogServices found")
        owner, uri, payload = self.sel
        action = (payload.get("Actions", {}) or {}).get("#LogService.ClearLog", {})
        target = action.get("target")
        if not target:
            ctx.skip("ClearLog action not advertised")
        resp = ctx.client.post(target, json={})
        ctx.check_status(resp, (200, 202, 204), "POST ClearLog")
        entries_uri = (payload.get("Entries") or {}).get("@odata.id")
        after = ctx.client.get_json(entries_uri)
        count = len(after.get("Members", []))
        # Clearing itself often logs one "log cleared" event
        ctx.check(count <= 1, "Log emptied (<= 1 entry remains)",
                  expected="<= 1 entry", actual=f"{count} entries")

    def teardown(self, ctx):
        """Remove the test account if any test left it behind."""
        if self.test_account_uri:
            try:
                self._delete_account(ctx)
            except (RedfishError, requests.RequestException):
                pass
            self.test_account_uri = None
