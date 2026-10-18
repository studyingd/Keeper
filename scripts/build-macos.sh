#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$project_root"

# Keeper.spec carries the bundle identifier and the version, which the
# command-line flags cannot express; prefer the project venv, where
# PyInstaller usually lives rather than in the system interpreter.
python_bin="python3"
if [ -x "$project_root/.venv/bin/python" ]; then
    python_bin="$project_root/.venv/bin/python"
fi

"$python_bin" -m PyInstaller --noconfirm --clean Keeper.spec

# Same trim as the Windows build: PyInstaller bundles every QML module in the
# PySide6 wheel; Keeper only needs QtQuick/.Controls.Basic/.Layouts/.Dialogs.
"$python_bin" scripts/trim_dist.py dist/Keeper.app

echo "Build complete: $project_root/dist/Keeper.app"
