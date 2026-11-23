#!/usr/bin/env bash
# Rebuild data/ from CRRF's public bathymetry tiles, optionally using the 2025 report PDF
# to fill water deeper than each section's colour scale.
#   tools/build.sh [path/to/CRRF-Outer-Reef-Bathymetry-Technical-Report-2025-09.pdf]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD="${BUILD:-$ROOT/build}"
mkdir -p "$BUILD/report" "$BUILD/tiles"

if [ "${1:-}" != "" ]; then
  echo "== Report figures (deep-water fill)"
  PDF="$(realpath "$1")"
  python3 "$ROOT/tools/report/extract_figures.py" "$PDF" "$ROOT/tools/report/config.json" "$BUILD/report"
  ( cd "$BUILD/report"
    for area in main sonsorol merir hatohobei helen; do
      python3 "$ROOT/tools/report/decode.py" "$ROOT/tools/report/config.json" "$area"
      python3 "$ROOT/tools/report/clean.py"  "$ROOT/tools/report/config.json" "$area"
    done
    python3 "$ROOT/tools/report/export.py" "$ROOT/tools/report/config.json" "$BUILD/report" )
fi

echo "== CRRF tiles"
python3 "$ROOT/tools/tiles/fetch_tiles.py"  "$ROOT/tools/tiles/services.json" "$BUILD/tiles" 14
python3 "$ROOT/tools/tiles/decode_tiles.py" "$ROOT/tools/tiles/services.json" "$ROOT/tools/tiles/ramp.json" "$BUILD/tiles"
python3 "$ROOT/tools/tiles/build_data.py"   "$ROOT/tools/tiles/services.json" "$BUILD/tiles" "$ROOT/data" "$BUILD/report"
echo "Done: $ROOT/data"
