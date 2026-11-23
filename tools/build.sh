#!/usr/bin/env bash
# Rebuild data/ from the CRRF technical report PDF.
#   tools/build.sh path/to/CRRF-Outer-Reef-Bathymetry-Technical-Report-2025-09.pdf
set -euo pipefail
PDF="$(realpath "$1")"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="${WORK:-$ROOT/build}"
mkdir -p "$WORK"
python3 "$ROOT/tools/extract_figures.py" "$PDF" "$ROOT/tools/config.json" "$WORK"
cd "$WORK"
for area in main sonsorol merir hatohobei helen; do
  python3 "$ROOT/tools/decode.py" "$ROOT/tools/config.json" "$area"
  python3 "$ROOT/tools/clean.py"  "$ROOT/tools/config.json" "$area"
done
python3 "$ROOT/tools/export.py" "$ROOT/tools/config.json" "$ROOT/data"
echo "Done: $ROOT/data"
