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
python - <<'PY'
from pathlib import Path
import site

project_root = Path.cwd()
for site_dir in site.getsitepackages():
    Path(site_dir, "tally_cfo_dev.pth").write_text(f"{project_root}\n")

launcher = project_root / ".venv" / "bin" / "tally"
text = launcher.read_text()
insert = f"import sys\nsys.path.insert(0, {str(project_root)!r})\n"
if insert not in text:
    text = text.replace("import sys\n", insert, 1)
    launcher.write_text(text)
PY
uv run playwright install chromium
rm -f uv.lock
tally setup

echo ""
echo "Next steps:"
echo "1. Fill in ~/.tally/.env"
echo "2. Register a Telegram bot with BotFather"
echo "3. Run tally status"
