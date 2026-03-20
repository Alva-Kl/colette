#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BETA_BUILD="$ROOT_DIR/build/beta/colette"
PROD_BUILD="$ROOT_DIR/build/prod/colette"
MODE="${1:-beta}"
PYTHON_BIN="${PYTHON:-python3}"

build_beta() {
  local tmp_dir
  tmp_dir="$(mktemp -d)"
  trap "rm -rf '$tmp_dir'" EXIT

  mkdir -p "$tmp_dir/colette_cli"
  cp -R "$ROOT_DIR/colette_cli/." "$tmp_dir/colette_cli/"
  cat > "$tmp_dir/__main__.py" <<'PY'
from colette_cli.main import main

if __name__ == "__main__":
    main()
PY

  mkdir -p "$(dirname "$BETA_BUILD")"
  "$PYTHON_BIN" -m zipapp "$tmp_dir" -p "/usr/bin/env python3" -o "$BETA_BUILD"
  chmod +x "$BETA_BUILD"
  echo "Built beta executable at $BETA_BUILD"
}

promote_beta() {
  if [[ ! -f "$BETA_BUILD" ]]; then
    echo "Beta build not found at $BETA_BUILD" >&2
    echo "Run ./scripts/build.sh first." >&2
    exit 1
  fi

  mkdir -p "$(dirname "$PROD_BUILD")"
  cp "$BETA_BUILD" "$PROD_BUILD"
  chmod +x "$PROD_BUILD"
  echo "Promoted beta build to $PROD_BUILD"
}

case "$MODE" in
  beta)
    build_beta
    ;;
  prod|promote)
    promote_beta
    ;;
  *)
    echo "Usage: ./scripts/build.sh [beta|prod]" >&2
    exit 1
    ;;
esac
