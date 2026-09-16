#!/usr/bin/env bash
# Add the proxy timeouts a local model needs to one nginx site file.
#
#   sudo bash scripts/nginx_add_timeouts.sh /etc/nginx/sites-available/ai.signalmesh.dev [seconds]
#
# Anchor-safe, in the deploy-ceremony sense: backs the file up, refuses when
# the anchor (a proxy_pass line) is missing or ambiguous, inserts the two
# directives just above it, then runs nginx -t and reloads only if that passes.
# Re-running on a file that already has the directives is a no-op.
set -euo pipefail

site="${1:-}"
seconds="${2:-180}"
[[ -n "$site" && -f "$site" ]] || { echo "usage: $0 /etc/nginx/sites-available/<site> [seconds]" >&2; exit 2; }
[[ "$seconds" =~ ^[0-9]+$ ]] || { echo "seconds must be a number" >&2; exit 2; }

if grep -qE '^\s*proxy_read_timeout' "$site"; then
    echo "already set:"; grep -nE '^\s*proxy_(read|send)_timeout' "$site"
    # An edit made by hand may never have been reloaded; make sure it is live.
    nginx -t && systemctl reload nginx && echo "nginx reloaded"
    exit 0
fi

anchors=$(grep -cE '^\s*proxy_pass\s' "$site" || true)
if [[ "$anchors" -ne 1 ]]; then
    echo "REFUSED: expected exactly one proxy_pass line in $site, found $anchors — edit by hand" >&2
    exit 1
fi

backup="${site}.bak.$(date +%Y%m%d%H%M%S)"
cp -p "$site" "$backup"
echo "backup: $backup"

indent=$(grep -E '^\s*proxy_pass\s' "$site" | sed -E 's/^(\s*).*/\1/')
sed -i -E "0,/^\s*proxy_pass\s/s//${indent}proxy_read_timeout ${seconds}s;\n${indent}proxy_send_timeout ${seconds}s;\n&/" "$site"

echo "now:"; grep -nE '^\s*proxy_(read|send)_timeout|^\s*proxy_pass\s' "$site"

if nginx -t; then
    systemctl reload nginx
    echo "nginx reloaded"
else
    echo "nginx -t FAILED — restoring $backup" >&2
    cp -p "$backup" "$site"
    exit 1
fi
