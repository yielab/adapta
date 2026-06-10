#!/usr/bin/env bash
# Brain From Cero — backup (A4.12). Automates docs/reference/OPERATIONS.md §2.
#
# Backs up, from the same window (so a registered adapter row always has its file):
#   - Postgres (schema + data)         -> backup/brain-<date>.sql.gz
#   - ChromaDB named volume            -> backup/chroma-<date>.tgz
#   - adapters + uploads + datasets    -> backup/artifacts-<date>.tgz
# Then prunes backups older than RETENTION_DAYS.
#
# Online-safe (pg_dump + file copies); no need to stop the stack.
#
# Usage:   scripts/backup.sh
# Cron:    0 3 * * *  cd /opt/brainFromCero && scripts/backup.sh >> backup/backup.log 2>&1
#
# Env overrides:
#   BACKUP_DIR=backup            destination directory
#   RETENTION_DAYS=14            delete backups older than this (0 = keep all)
#   COMPOSE_PROJECT=brainfromcero  compose project name (chroma volume prefix)
set -euo pipefail

cd "$(dirname "$0")/.."  # repo root

BACKUP_DIR="${BACKUP_DIR:-backup}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
COMPOSE_PROJECT="${COMPOSE_PROJECT:-brainfromcero}"
DATE="$(date +%F)"
CHROMA_VOLUME="${COMPOSE_PROJECT}_chroma-data"

mkdir -p "$BACKUP_DIR"
echo "[backup] $(date -Is) → $BACKUP_DIR (retention ${RETENTION_DAYS}d)"

echo "[backup] Postgres…"
docker compose exec -T postgres pg_dump -U brain brain | gzip > "$BACKUP_DIR/brain-$DATE.sql.gz"

echo "[backup] ChromaDB volume ($CHROMA_VOLUME)…"
docker run --rm -v "${CHROMA_VOLUME}:/data" -v "$PWD/$BACKUP_DIR:/out" \
  alpine tar czf "/out/chroma-$DATE.tgz" -C /data .

echo "[backup] Artifacts (adapters + uploads + datasets)…"
tar czf "$BACKUP_DIR/artifacts-$DATE.tgz" data/adapters data/uploads data/datasets 2>/dev/null || \
  echo "[backup] (some artifact dirs missing — skipped what isn't there)"

if [ "$RETENTION_DAYS" -gt 0 ]; then
  echo "[backup] Pruning backups older than ${RETENTION_DAYS} days…"
  find "$BACKUP_DIR" -maxdepth 1 -type f \
    \( -name 'brain-*.sql.gz' -o -name 'chroma-*.tgz' -o -name 'artifacts-*.tgz' \) \
    -mtime "+${RETENTION_DAYS}" -print -delete
fi

echo "[backup] Done. Restore steps: docs/reference/OPERATIONS.md §2."
