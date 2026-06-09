#!/usr/bin/env bash
# Generate Pydantic models from specs/openapi.yaml → brain/models/generated/
#
# Run inside the Docker container:
#   docker compose exec app bash scripts/generate_models.sh
#
# The generated file is committed to source control so CI never needs
# the generator installed in production. Re-run whenever openapi.yaml changes.

set -euo pipefail

SPEC="$(dirname "$0")/../specs/openapi.yaml"
OUT_DIR="$(dirname "$0")/../brain/models/generated"
OUT_FILE="$OUT_DIR/models.py"

mkdir -p "$OUT_DIR"

echo "→ Generating Pydantic models from $SPEC"

datamodel-codegen \
  --input        "$SPEC" \
  --input-file-type openapi \
  --output       "$OUT_FILE" \
  --output-model-type pydantic_v2.BaseModel \
  --use-annotated \
  --use-double-quotes \
  --target-python-version 3.10 \
  --use-default \
  --strict-nullable \
  --enum-field-as-literal one \
  --use-field-description \
  --reuse-model \
  --collapse-root-models \
  --wrap-string-literal \
  --disable-timestamp

# Stamp an __init__.py so the package is importable
if [ ! -f "$OUT_DIR/__init__.py" ]; then
  echo '"""Auto-generated Pydantic models — DO NOT EDIT. Run scripts/generate_models.sh."""' \
    > "$OUT_DIR/__init__.py"
fi

echo "✓ Models written to $OUT_FILE"
echo "  Next: review the diff, then run: pytest tests/test_api_contracts.py"
