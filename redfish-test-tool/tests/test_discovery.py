import pytest

from redfish_test_tool.client import RedfishClient
from redfish_test_tool.discovery import ServiceMap
from redfish_test_tool.exceptions import ResourceNotFound
from tests.conftest import make_config


@pytest.fixture
def client(mock_bmc):
    c = RedfishClient(make_config())
    c.login()
    yield c
    c.logout()


def test_discover_core_resources(client):
    smap = ServiceMap(client).discover()
    assert smap.system_uri == "/redfish/v1/Systems/System.Embedded.1"
    assert smap.system["Manufacturer"] == "Dell Inc."
    assert len(smap.chassis_list) == 1
    assert smap.manager_uri == "/redfish/v1/Managers/iDRAC.Embedded.1"


def test_reset_action_with_allowable_values(client):
    smap = ServiceMap(client).discover()
    target, allowed = smap.reset_action()
    assert target.endswith("/Actions/ComputerSystem.Reset")
    assert "ForceRestart" in allowed


def test_system_id_selection(client):
    smap = ServiceMap(client, system_id="System.Embedded.1").discover()
    assert smap.system_uri.endswith("System.Embedded.1")
    with pytest.raises(ResourceNotFound):
        ServiceMap(client, system_id="NoSuchSystem").discover()


def test_find_sel(client):
    smap = ServiceMap(client).discover()
    owner, uri, payload = smap.find_sel()
    assert owner == "Manager"
    assert payload["Id"] == "Sel"


def test_collections_uris(client):
    smap = ServiceMap(client).discover()
    assert smap.sessions_collection_uri() == "/redfish/v1/SessionService/Sessions"
    assert smap.accounts_collection_uri() == "/redfish/v1/AccountService/Accounts"
