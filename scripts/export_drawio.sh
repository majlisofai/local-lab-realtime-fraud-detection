#!/bin/sh
# Export every .drawio file in a folder to PNG with headless draw.io (one container per file).
# The brand fonts in build/fonts are mounted as system fonts: draw.io cannot load web fonts.
#   scripts/export_drawio.sh <folder>
set -u
dir=$(cd "$1" && pwd)
fonts=$(cd "$(dirname "$0")/.." && pwd)/build/fonts
for f in "$dir"/*.drawio; do
  name=$(basename "$f" .drawio)
  echo "  export $name.png"
  docker run --rm -w /data -v "$dir":/data -v "$fonts":/usr/local/share/fonts/brand:ro \
    rlespinasse/drawio-desktop-headless:v1.43.0 -x -f png -s 1.5 -b 20 -o "$name.png" "$name.drawio" \
    >/dev/null 2>&1 || echo "  failed: $f"
done
