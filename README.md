# Palau Bathymetry Viewer

An interactive web map that combines the five outer-reef bathymetry maps of Palau from the
Coral Reef Research Foundation (CRRF) 2025 technical report into one viewer.
**Hover anywhere on the map to read the depth in feet** (meters shown alongside). On a phone, tap.

| Area | Report figure | Source colour scale | Grid resolution |
|---|---|---|---|
| Palau main island group | Fig. 6 | < 30 m – > 4,000 m | 51 m |
| Sonsorol & Fana | Fig. 7 | < 30 m – 1,500 m | 15 m |
| Merir | Fig. 8 | < 20 m – 2,000 m | 15 m |
| Hatohobei (Tobi) | Fig. 9 | < 30 m – 3,000 m | 15 m |
| Helen Reef | Fig. 10 | < 30 m – 3,000 m | 22 m |

All five areas are drawn with one shared colour scale in feet (square-root stretched so the reef slope
keeps its detail) over a satellite, ocean or dark basemap.

## Important: how accurate are the depths?

The report contains rendered map images, not the underlying 20 m DEM. The depths here were
**reconstructed from the colours of those images**:

1. Each figure was georeferenced from its UTM Zone 53N grid ticks.
2. Each pixel's colour was matched against that figure's legend, which allows for hillshade
   darkening (`pixel ≈ shade × legend colour + grey`). Satellite imagery, land and lagoons were
   rejected with colour-fit, smoothness and physical-slope tests.
3. The grids were reprojected to Web Mercator for display.

What that means for the numbers:

* **Pixel noise is about ±1% of each figure's depth scale** (90th percentile 20–50 m, depending on
  the map). Systematic error from the report's own rendering hasn't been measured and may be larger.
* **The reef crest can't be resolved.** The legend's red end is a single colour for its first ~4%, so
  shallow water is reported as a limit, e.g. "< 620 ft" on the main-island map and "< 292 ft" at Sonsorol.
* **Areas deeper than a figure's scale** (e.g. > 4,000 m east of the main islands) are hatched and
  reported as "> 13,123 ft".
* The legends were assumed to be linear between their end labels (every mid-point label agrees).
* Vertical datum: MLLW (UHSLC Malakal tide station). The source report states the data
  isn't IHO S-44 compliant.

**Not for navigation.** If CRRF can share the original DEM rasters (GeoTIFF/ASCII grid), the
viewer can use them directly with no change to the front end, and all of the limits above go away.

## Run locally

Any static file server works:

```bash
python3 -m http.server 8000
```

Then open http://localhost:8000.

## Publish with GitHub Pages

Settings → Pages → *Deploy from a branch* → `main` / `(root)`. The site has no build step.

## Rebuild the data from the report

```bash
pip install -r tools/requirements.txt
```

```bash
tools/build.sh path/to/CRRF-Outer-Reef-Bathymetry-Technical-Report-2025-09.pdf
```

This needs `pdfimages` from poppler-utils. Intermediate files go to `build/` (git-ignored); outputs go
to `data/`. Georeferencing ticks, legend positions and depth ranges for each figure are in
`tools/config.json`.

| Step | Script | Output |
|---|---|---|
| Extract & stitch figures | `tools/extract_figures.py` | `build/<area>.png` |
| Colour → depth | `tools/decode.py` | `build/<area>_raw.npz` |
| Mask & clean | `tools/clean.py` | `build/<area>_depth.npy` |
| Reproject & encode | `tools/export.py` | `data/<area>.webp`, `data/<area>.depth.png`, `data/manifest.json` |

`data/<area>.depth.png` stores depth losslessly: **R·256 + G = depth in decimetres**, and
**B = 0** (no data), **1** (depth) or **2** (deeper than the figure's scale).

## Project layout

```
index.html          viewer page (Leaflet 1.9.4 from cdnjs)
assets/app.js       map, layers, hover depth lookup, legend
assets/style.css
data/               generated layers + manifest.json
tools/              Python pipeline that turns the report's figures into data/
```

## Credits

Bathymetry: Ferrier-Loh, A. and P. L. Colin. 2025. *Bathymetry of Palau's Outer Reef Slope.*
Technical Report, Coral Reef Research Foundation. https://www.coralreefpalau.org. Survey work was
funded by the US Department of the Interior, Office of Insular Affairs (D19AP00149), with assistance
from Scripps Institution of Oceanography; deep-water data from the NOAA NCEI Multibeam Bathymetry Database.
The report and its figures remain © Coral Reef Research Foundation.

Basemaps: Esri World Imagery / World Ocean Base, CARTO, OpenStreetMap contributors.
