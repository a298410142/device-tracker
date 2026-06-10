"""Redact credentials from logged HTTP headers and bodies."""

import json
import re

SENSITIVE_HEADERS = {"authorization", "x-auth-token"}
SENSITIVE_BODY_KEYS = {"password", "Password"}

_PASSWORD_RE = re.compile(r'("password"\s*:\s*)"[^"]*"', re.IGNORECASE)


def redact_headers(headers):
    return {
        k: ("***REDACTED***" if k.lower() in SENSITIVE_HEADERS else v)
        for k, v in headers.items()
    }


def redact_body(body):
    """Redact password values in a JSON string or dict; pass through otherwise."""
    if body is None:
        return body
    if isinstance(body, dict):
        return {
            k: ("***REDACTED***" if k in SENSITIVE_BODY_KEYS else v)
            for k, v in body.items()
        }
    if isinstance(body, (bytes, bytearray)):
        try:
            body = body.decode("utf-8")
        except UnicodeDecodeError:
            return "<binary>"
    if isinstance(body, str):
        return _PASSWORD_RE.sub(r'\1"***REDACTED***"', body)
    return body


def redact_json(data):
    """Deep-redact a parsed JSON structure (used for trace logging)."""
    if isinstance(data, dict):
        return {
            k: ("***REDACTED***" if k in SENSITIVE_BODY_KEYS else redact_json(v))
            for k, v in data.items()
        }
    if isinstance(data, list):
        return [redact_json(v) for v in data]
    return data
