#!/usr/bin/env bash
# Report component status in the shape the work order asks for.
# Exit 0 when everything is OK or deliberately DISABLED, 1 otherwise, so this
# can be used as a deploy gate.
set -uo pipefail

BASE_URL="${AI_HELPER_URL:-http://localhost:8000}"

response=$(curl -fsS --max-time 15 "${BASE_URL}/health" 2>/dev/null) || {
    printf 'AI HELPER\n---------\nGateway       UNREACHABLE at %s\n' "$BASE_URL"
    exit 1
}

python3 - "$response" <<'PY'
import json, sys

data = json.loads(sys.argv[1])
print("AI HELPER")
print("---------")
width = max((len(c["name"]) for c in data["components"]), default=10) + 2
bad = False
for component in data["components"]:
    status = component["status"]
    detail = component.get("detail") or ""
    print(f"{component['name']:<{width}}{status}" + (f"   {detail}" if detail else ""))
    if status in ("DOWN", "UNAVAILABLE"):
        bad = True
print("---------")
print(f"overall       {data['status']}   (v{data['version']}, {data['environment']})")
sys.exit(1 if bad or data["status"] == "down" else 0)
PY
