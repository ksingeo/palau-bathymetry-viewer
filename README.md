# Palau Bathymetry Viewer

An interactive web map that combines the Coral Reef Research Foundation's (CRRF) outer-reef
bathymetry for Palau into one viewer. **Hover anywhere on the map to read the depth in feet**
(meters shown alongside). On a phone, tap.

The map shows CRRF's published bathymetry tiles from their
[Outer Reef](https://experience.arcgis.com/experience/e5d3c2bb8642421f94da0b982eb12733) web experience:
15 reef sections, each its own ArcGIS Online tile service.

| Group | Sections | Colour scale |
|---|---|---|
| Main island group | Western Reef 1–3, Eastern Reef 1–4 (2 = Ngarrard), Northern Reef, Peleliu – German Channel | < 5 m – > 2,000 m |
| | Angaur | < 10 m – > 2,000 m |
| | Kayangel | < 5 m – > 750 m |
| Southwest Islands | Sonsorol & Fana | < 2 m – > 1,000 m |
| | Merir | < 2 m – > 1,500 m |
| | Hatohobei (Tobi), Helen Reef | < 5 m – > 2,000 m |

## How the depth readout works, and how accurate it is

CRRF publishes the depths as coloured map tiles, not as numbers. The readout is **decoded from the tile
colours**:

1. Tiles for every section are fetched at zoom 14 (~5 m pixels) from `tiles.arcgis.com`.
2. Each pixel is matched to CRRF's own colour ramp (taken from the services' legends). Tiles are drawn
   ~10% transparent over a hillshade, so the match allows for that (`pixel ≈ a · ramp + b`). The median fit
   residual is 0.2–0.4 colour units, so the colours are matched almost exactly.
3. Ramp position is converted to depth with each section's legend limits (a linear stretch), then averaged
   to a ~19 m grid, which matches CRRF's 20 m survey grid.
4. Where the tiles only say "deeper than the scale" (e.g. > 2,000 m), the depth is filled in from the
   figures in the 2025 technical report, which extend to about 4,000 m (and are less precise).

What that means for the numbers:

* **Cross-check:** decoding the 2025 report's figures independently gives depths that correlate at
  r = 0.93–0.98 with the tile values at the same spots, but the tiles read **about 5–10% shallower**. Which
  rendering is closer to the true depth hasn't been checked against soundings. Treat readings as ±10%.
* **Reef top:** water shallower than a section's scale minimum (2–10 m) is shown as "< 16 ft" etc.
* **Beyond the scale:** where neither source resolves the depth, it's shown as "> 6,562 ft" etc.
* Vertical datum: MLLW (UHSLC Malakal tide station). CRRF states the data isn't IHO S-44 compliant.

**Not for navigation.** If CRRF can share the original 20 m DEM rasters, the readout can use them
directly with the same front end.

## Run locally

```bash
python3 -m http.server 8000
```

Then open http://localhost:8000.

## Publish with GitHub Pages

Settings → Pages → *Deploy from a branch* → `main` / `(root)`. The site has no build step.

## Rebuild the data

```bash
pip install -r tools/requirements.txt
```

```bash
tools/build.sh path/to/CRRF-Outer-Reef-Bathymetry-Technical-Report-2025-09.pdf
```

The PDF argument is optional; it only provides the deep-water fill (needs `pdfimages` from poppler-utils).
Downloaded tiles and intermediates go to `build/` (git-ignored); outputs go to `data/`.

| Step | Script | Output |
|---|---|---|
| Report figures → depth (optional) | `tools/report/*.py`, `tools/report/config.json` | `build/report/` |
| Fetch CRRF tiles | `tools/tiles/fetch_tiles.py` | `build/tiles/<section>/14/y/x` |
| Colour → depth | `tools/tiles/decode_tiles.py`, `tools/tiles/ramp.json` | `build/tiles/<section>.z13.npz` |
| Merge & encode | `tools/tiles/build_data.py` | `data/<section>.depth.png`, `data/manifest.json` |

`tools/tiles/services.json` lists each section's service extent, maximum zoom and legend limits.

`data/<section>.depth.png` is a lossless image on the global zoom-13 Web Mercator pixel grid
(origin `x0`, `y0` in the manifest):

* **R·256 + G** is the depth in metres.
* **B** is a flag:

| B | Meaning |
|---|---|
| 0 | no data |
| 1 | depth from tiles |
| 2 | deeper than the scale (value is the limit) |
| 3 | depth from the report figure |
| 4 | shallower than the scale (value is the limit) |

## Project layout

```
index.html          viewer page (Leaflet 1.9.4 from cdnjs)
assets/app.js       map, CRRF tile layers, hover depth lookup, legend
assets/style.css
data/               depth grids + manifest.json (generated)
tools/tiles/        CRRF tile pipeline
tools/report/       2025 report figure pipeline (deep-water fill)
```

## Credits

Bathymetry map copyright © 2026 Coral Reef Research Foundation (https://www.coralreefpalau.org).
"No guarantee is made as to the accuracy of this map." Image credit: Coral Reef Research Foundation (2026).

Ferrier-Loh, A. and P. L. Colin. 2025. *Bathymetry of Palau's Outer Reef Slope.* Technical Report, Coral Reef
Research Foundation. Funded by the US Department of the Interior, Office of Insular Affairs (D19AP00149),
with assistance from Scripps Institution of Oceanography; deep-water data from the NOAA NCEI Multibeam
Bathymetry Database.

Basemaps: Esri World Imagery / World Ocean Base, CARTO, OpenStreetMap contributors.
