from redfish_test_tool.suites.basic_info import BasicInfoSuite
from redfish_test_tool.suites.sensors_health import SensorsHealthSuite
from redfish_test_tool.suites.power_control import PowerControlSuite
from redfish_test_tool.suites.accounts_sessions_sel import AccountsSessionsSelSuite

SUITE_REGISTRY = {
    "basic": BasicInfoSuite,
    "sensors": SensorsHealthSuite,
    "power": PowerControlSuite,
    "accounts": AccountsSessionsSelSuite,
}
