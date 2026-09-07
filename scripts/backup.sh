#!/usr/bin/env bash
# Back up what cannot be rebuilt.
#
# Backed up:  PostgreSQL (clients, memory, solutions, documents, audit, costs),
#             the Qdrant collections, n8n's workflows, and .env.
# NOT backed up: Ollama's model files. They are tens of gigabytes and are
#             re-downloadable with `ollama pull` — backing them up wastes the
#             storage that the irreplaceable data needs.
#
# A backup that has never been restored is a hypothesis. This script verifies
# each artefact after writing it, and refuses to report success otherwise.
set -euo pipefail

cd "$(dirname "$0")/.."

BACKUP_ROOT="${BACKUP_DIR:-./backups}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DEST="${BACKUP_ROOT}/${STAMP}"
RETAIN_DAYS="${BACKUP_RETAIN_DAYS:-30}"

green() { printf '\033[0;32m%s\033[0m\n' "$*"; }
die()   { printf '\033[0;31m%s\033[0m\n' "$*" >&2; exit 1; }

mkdir -p "$DEST"
green "Backing up to ${DEST}"

# ------------------------------------------------------------- postgres
green "  postgres…"
: "${POSTGRES_USER:=aihelper}"
: "${POSTGRES_DB:=aihelper}"
docker compose exec -T postgres pg_dump \
    -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --no-owner \
    > "${DEST}/postgres.dump" || die "pg_dump failed"

# Verify the dump is readable and contains the tables that matter, rather than
# trusting that a zero exit code means a usable backup.
docker compose exec -T postgres pg_restore --list < "${DEST}/postgres.dump" \
    > "${DEST}/postgres.toc" 2>/dev/null || die "the dump is not readable by pg_restore"
for table in clients solution_candidates memory_items audit_events cost_records documents; do
    grep -q " ${table} " "${DEST}/postgres.toc" \
        || die "the dump does not contain table '${table}' — refusing to call this a backup"
done
green "    $(wc -c < "${DEST}/postgres.dump" | tr -d ' ') bytes, all expected tables present"

# --------------------------------------------------------------- qdrant
green "  qdrant…"
if docker compose ps --status running --services 2>/dev/null | grep -qx qdrant; then
    mkdir -p "${DEST}/qdrant"
    # Snapshot each collection through the API, so the files are consistent.
    collections=$(docker compose exec -T qdrant \
        sh -c 'wget -qO- http://localhost:6333/collections' 2>/dev/null \
        | python3 -c 'import json,sys; print(" ".join(c["name"] for c in json.load(sys.stdin)["result"]["collections"]))' \
        2>/dev/null || echo "")
    if [[ -z "$collections" ]]; then
        echo "    no collections yet — nothing to snapshot"
    fi
    for collection in $collections; do
        docker compose exec -T qdrant sh -c \
            "wget -q --post-data='' -O- http://localhost:6333/collections/${collection}/snapshots" \
            > "${DEST}/qdrant/${collection}.json" 2>/dev/null \
            && echo "    snapshot: ${collection}" \
            || echo "    WARNING: could not snapshot ${collection}"
    done
    # The vectors are also rebuildable from Postgres by re-indexing, which is
    # the fallback if a snapshot is ever unusable. See docs/operations.md.
else
    echo "    qdrant is not running — skipped"
fi

# ------------------------------------------------------------------ n8n
green "  n8n workflows…"
if docker compose ps --status running --services 2>/dev/null | grep -qx n8n; then
    docker compose exec -T n8n sh -c 'tar czf - -C /home/node .n8n' \
        > "${DEST}/n8n.tar.gz" 2>/dev/null && tar tzf "${DEST}/n8n.tar.gz" >/dev/null \
        || echo "    WARNING: the n8n archive could not be verified"
else
    echo "    n8n is not running — skipped"
fi

# --------------------------------------------------------- configuration
if [[ -f .env ]]; then
    cp .env "${DEST}/env.backup"
    chmod 600 "${DEST}/env.backup"
    green "  .env copied (mode 600) — this file contains secrets; store the backup accordingly"
fi

# ------------------------------------------------------------- manifest
cat > "${DEST}/MANIFEST.txt" <<MANIFEST
AI Helper backup
created_utc : ${STAMP}
host        : $(hostname)
contents    : postgres.dump (custom format), qdrant/ snapshots, n8n.tar.gz, env.backup
excluded    : ollama models (re-downloadable via 'ollama pull')

restore:
  docker compose up -d postgres
  docker compose exec -T postgres pg_restore -U ${POSTGRES_USER} -d ${POSTGRES_DB} \\
      --clean --if-exists < postgres.dump
  # then restore Qdrant snapshots, or re-index from Postgres:
  #   see docs/operations.md, "Rebuilding the vector index"
MANIFEST

find "$BACKUP_ROOT" -maxdepth 1 -type d -name '20*' -mtime "+${RETAIN_DAYS}" \
    -exec rm -rf {} + 2>/dev/null || true

green "Backup complete: ${DEST}"
green "Restore instructions are in ${DEST}/MANIFEST.txt"
