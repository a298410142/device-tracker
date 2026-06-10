"""Generic condition polling with timeout."""

import time

from redfish_test_tool.exceptions import PollTimeout


def wait_for(predicate, timeout, interval=5, description="condition", sleep=None,
             clock=None):
    """Poll `predicate()` until truthy or `timeout` seconds elapse.

    Returns the truthy value from the predicate. Raises PollTimeout on expiry.
    `sleep`/`clock` are injectable for unit tests; resolved lazily so that
    monkeypatching time.sleep also works.
    """
    sleep = sleep or time.sleep
    clock = clock or time.monotonic
    deadline = clock() + timeout
    last_error = None
    while True:
        try:
            result = predicate()
            if result:
                return result
        except Exception as exc:  # transient errors (e.g. BMC rebooting) keep polling
            last_error = exc
        if clock() >= deadline:
            suffix = f" (last error: {last_error})" if last_error else ""
            raise PollTimeout(
                f"Timed out after {timeout}s waiting for {description}{suffix}"
            )
        sleep(interval)
