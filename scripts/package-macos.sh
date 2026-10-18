#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"

"$project_root/scripts/build-macos.sh"

dmg="$project_root/dist/Keeper.dmg"
rm -f "$dmg"
hdiutil create \
    -volname Keeper \
    -srcfolder "$project_root/dist/Keeper.app" \
    -ov \
    -format UDZO \
    "$dmg"

echo "Package complete: $dmg"
