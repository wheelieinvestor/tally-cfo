#!/usr/bin/env bash
set -euo pipefail

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required."
  echo "Install it with: curl -LsSf https://astral.sh/uv/install.sh | sh"
  exit 1
fi

if [ -d ".venv" ]; then
  echo "Using existing .venv"
else
  uv venv --python 3.11
fi
# shellcheck disable=SC1091
source .venv/bin/activate

uv pip install -e .
uv run playwright install chromium
rm -f uv.lock
tally setup

echo ""
echo "Next steps:"
echo "1. Fill in ~/.tally/.env"
echo "2. Register a Telegram bot with BotFather"
echo "3. Run tally status"
