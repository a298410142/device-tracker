class RedfishError(Exception):
    """Base error for all tool-level failures."""


class ConfigError(RedfishError):
    """Invalid or incomplete configuration."""


class AuthError(RedfishError):
    """Authentication / session establishment failed."""


class ResourceNotFound(RedfishError):
    """A required Redfish resource link could not be discovered."""


class PollTimeout(RedfishError):
    """A polled condition did not become true within the timeout."""


class AssertionFailure(RedfishError):
    """A test assertion failed; carries expected/actual for reporting."""

    def __init__(self, message, expected=None, actual=None):
        super().__init__(message)
        self.expected = expected
        self.actual = actual
