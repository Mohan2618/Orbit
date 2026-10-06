import json
import os
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


base_url = os.getenv("ORBIT_API_URL", "").rstrip("/")
key = os.getenv("ORBIT_API_KEY", "")
repository = os.getenv("REPOSITORY_URL", "")

if not base_url or not key or not repository:
    print("Orbit CI skipped: configure ORBIT_API_URL and ORBIT_API_KEY secrets.")
    sys.exit(0)


def call(path, method="GET", body=None):
    payload = json.dumps(body).encode() if body is not None else None
    request = Request(
        base_url + path,
        data=payload,
        method=method,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read())


try:
    run = call("/api/v1/test-runs", "POST", {"repository_url": repository})
    print(f"Orbit run queued: {run['id']}", flush=True)
    deadline = time.monotonic() + 900
    while time.monotonic() < deadline:
        result = call(f"/api/v1/test-runs/{run['id']}")
        print(f"Run status: {result['status']}", flush=True)
        if result["status"] in {"completed", "failed"}:
            report = result.get("result") or {}
            print(json.dumps(report, indent=2))
            if result["status"] != "completed" or report.get("outcome") != "passed":
                sys.exit(1)
            sys.exit(0)
        time.sleep(10)
    print("Orbit run timed out after 15 minutes.", file=sys.stderr)
    sys.exit(1)
except (HTTPError, URLError, TimeoutError, KeyError) as error:
    print(f"Orbit QA failed: {error}", file=sys.stderr)
    sys.exit(1)
