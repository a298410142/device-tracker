import pytest

from redfish_test_tool.client import RedfishClient
from redfish_test_tool.exceptions import AuthError
from tests.conftest import make_config


def test_session_login_logout(mock_bmc):
    client = RedfishClient(make_config())
    client.login()
    assert client._token is not None
    assert len(mock_bmc.sessions) == 1
    client.logout()
    assert len(mock_bmc.sessions) == 0


def test_session_login_bad_password(mock_bmc):
    client = RedfishClient(make_config(password="wrong"))
    with pytest.raises(AuthError):
        client.login()


def test_basic_auth_mode(mock_bmc):
    client = RedfishClient(make_config(auth="basic"))
    client.login()
    resp = client.get("/redfish/v1/Systems")
    assert resp.status_code == 200


def test_get_json_and_trace(mock_bmc):
    client = RedfishClient(make_config())
    client.login()
    root = client.get_json("/redfish/v1/")
    assert root["RedfishVersion"] == "1.6.0"
    assert any(e.method == "GET" for e in client.exchanges)
    client.logout()


def test_trace_redacts_password(mock_bmc):
    client = RedfishClient(make_config())
    client.login()
    login_posts = [e for e in client.exchanges
                   if e.method == "POST" and "Sessions" in e.url]
    assert login_posts
    assert "secret" not in str(login_posts[0].request_body)
    client.logout()
