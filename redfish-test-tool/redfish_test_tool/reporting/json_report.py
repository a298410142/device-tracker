"""Machine-readable JSON results writer."""

import json
from dataclasses import asdict
from datetime import datetime, timezone


def write_json_report(path, results, environment, counts):
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "environment": environment,
        "summary": counts,
        "results": [asdict(r) for r in results],
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    return path
