"""Redfish HTTP client: auth, session lifecycle, tracing, retries."""

import logging
import time

import requests
import urllib3

from redfish_test_tool.exceptions import AuthError, RedfishError
from redfish_test_tool.utils.redact import redact_body, redact_headers

logger = logging.getLogger("redfish.trace")

GET_RETRIES = 2
RETRY_BACKOFF = 2  # seconds, doubled per attempt


class HttpExchange:
    """One request/response pair, kept for reports and the trace log."""

    def __init__(self, method, url, status, elapsed, request_body=None,
                 response_body=None):
        self.method = method
        self.url = url
        self.status = status
        self.elapsed = elapsed
        self.request_body = request_body
        self.response_body = response_body

    def summary(self):
        return f"{self.method} {self.url} -> {self.status} ({self.elapsed:.2f}s)"


class RedfishClient:
    """requests.Session wrapper with Redfish session-token or Basic auth."""

    def __init__(self, config):
        self.config = config
        self.base_url = config.base_url
        self._session = requests.Session()
        self._session.verify = config.ssl_verify
        self._session.headers["Accept"] = "application/json"
        self._token = None
        self._session_uri = None
        self.exchanges = []  # all HttpExchange objects, in order

        if not config.ssl_verify:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    # -- auth ---------------------------------------------------------------

    def login(self):
        """Establish auth. Session-token preferred, Basic as fallback/explicit."""
        if self.config.auth == "basic":
            self._use_basic()
            return
        try:
            self._create_session()
        except (AuthError, RedfishError):
            raise
        except requests.RequestException as exc:
            raise RedfishError(f"Cannot connect to {self.base_url}: {exc}") from exc

    def _use_basic(self):
        self._session.auth = (self.config.username, self.config.password)
        # Probe a protected resource to fail fast on bad credentials
        resp = self.get("/redfish/v1/Systems")
        if resp.status_code == 401:
            raise AuthError("Basic authentication rejected (401)")

    def _create_session(self):
        sessions_uri = self._find_sessions_collection()
        resp = self.request(
            "POST", sessions_uri,
            json={"UserName": self.config.username, "Password": self.config.password},
        )
        if resp.status_code not in (200, 201):
            if resp.status_code == 401:
                raise AuthError(f"Session login rejected (401) at {sessions_uri}")
            raise AuthError(
                f"Session create failed: {resp.status_code} at {sessions_uri}"
            )
        token = resp.headers.get("X-Auth-Token")
        if not token:
            raise AuthError("Session created but no X-Auth-Token header returned")
        self._token = token
        self._session_uri = resp.headers.get("Location")
        self._session.headers["X-Auth-Token"] = token

    def _find_sessions_collection(self):
        """Resolve the Sessions collection URI from the service root (unauthenticated)."""
        resp = self.get("/redfish/v1/")
        if resp.status_code != 200:
            raise RedfishError(f"Service root returned {resp.status_code}")
        root = resp.json()
        links = root.get("Links", {}).get("Sessions", {})
        uri = links.get("@odata.id")
        if not uri:
            svc = root.get("SessionService", {}).get("@odata.id")
            if svc:
                uri = svc.rstrip("/") + "/Sessions"
        return uri or "/redfish/v1/SessionService/Sessions"

    def logout(self):
        """Delete the Redfish session. Always call in a finally block."""
        if self._token and self._session_uri:
            try:
                self.request("DELETE", self._session_uri)
            except requests.RequestException:
                logger.warning("Failed to delete session %s", self._session_uri)
        self._token = None
        self._session_uri = None
        self._session.headers.pop("X-Auth-Token", None)

    # -- HTTP ---------------------------------------------------------------

    def get(self, path, **kwargs):
        """GET with small retry on connection errors / 5xx."""
        attempt = 0
        while True:
            try:
                resp = self.request("GET", path, **kwargs)
                if resp.status_code < 500 or attempt >= GET_RETRIES:
                    return resp
            except requests.ConnectionError:
                if attempt >= GET_RETRIES:
                    raise
            time.sleep(RETRY_BACKOFF * (2 ** attempt))
            attempt += 1

    def get_json(self, path):
        """GET expecting 200 + JSON body; raises RedfishError otherwise."""
        resp = self.get(path)
        if resp.status_code != 200:
            raise RedfishError(f"GET {path} returned {resp.status_code}")
        try:
            return resp.json()
        except ValueError as exc:
            raise RedfishError(f"GET {path} returned non-JSON body") from exc

    def post(self, path, **kwargs):
        return self.request("POST", path, **kwargs)

    def patch(self, path, **kwargs):
        return self.request("PATCH", path, **kwargs)

    def delete(self, path, **kwargs):
        return self.request("DELETE", path, **kwargs)

    def request(self, method, path, **kwargs):
        url = path if path.startswith("http") else self.base_url + path
        kwargs.setdefault("timeout", self.config.timeout)
        start = time.monotonic()
        resp = self._session.request(method, url, **kwargs)
        elapsed = time.monotonic() - start
        self._trace(method, url, kwargs.get("json"), resp, elapsed)
        return resp

    def _trace(self, method, url, req_body, resp, elapsed):
        body_text = resp.text if len(resp.content) <= 64 * 1024 else "<truncated>"
        exchange = HttpExchange(
            method, url, resp.status_code, elapsed,
            request_body=redact_body(req_body),
            response_body=body_text,
        )
        self.exchanges.append(exchange)
        logger.debug(
            "%s %s\n  request headers: %s\n  request body: %s\n"
            "  status: %s (%.2fs)\n  response body: %s",
            method, url,
            redact_headers(dict(self._session.headers)),
            exchange.request_body,
            resp.status_code, elapsed,
            redact_body(body_text),
        )
