#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_BUILD="${1:-$ROOT_DIR/build/prod/colette}"
TARGET_PATH="${2:-$HOME/.local/bin/colette}"

if [[ ! -f "$SOURCE_BUILD" ]]; then
  echo "Build not found at $SOURCE_BUILD" >&2
  echo "Run ./scripts/build.sh and optionally ./scripts/build.sh prod first." >&2
  exit 1
fi

mkdir -p "$(dirname "$TARGET_PATH")"
cp "$SOURCE_BUILD" "$TARGET_PATH"
chmod +x "$TARGET_PATH"
echo "Installed $SOURCE_BUILD to $TARGET_PATH"
