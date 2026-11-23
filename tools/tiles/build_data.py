"""Assemble the viewer's depth files from the decoded CRRF tiles.
For every reef section writes data/<service>.depth.png on the global zoom-13 Web Mercator pixel grid:
  R*256 + G = depth in metres
  B = 0 no data | 1 depth | 2 deeper than the section's colour scale (value = deepest known limit)
      | 3 depth taken from the 2025 report figure (water deeper than the tiles' scale; less precise)
      | 4 shallower than the colour scale (value = scale minimum)
and data/manifest.json. If the report-figure grids exist (REPORT_DIR, made by tools/report), they fill in
water deeper than each section's tile scale.
Usage: python build_data.py services.json TILE_CACHE OUT_DIR [REPORT_DIR]"""
import json, sys, os, math, numpy as np
from PIL import Image
svcs = json.load(open(sys.argv[1])); cache, out = sys.argv[2], sys.argv[3]
rep = sys.argv[4] if len(sys.argv) > 4 else None
R = 20037508.342789244; RES13 = 2 * R / (256 * 2 ** 13)
BASE = 'https://tiles.arcgis.com/tiles/UhegwRIXa8Qj9weD/arcgis/rest/services'
report = {}
if rep and os.path.exists(os.path.join(rep, 'manifest.json')):
    for a in json.load(open(os.path.join(rep, 'manifest.json')))['areas']:
        im = np.asarray(Image.open(os.path.join(rep, a['id'] + '.depth.png'))).astype(np.int32)
        report[a['id']] = (a, (im[..., 0] * 256 + im[..., 1]) / 10.0, im[..., 2])
def lonlat(px, py):
    mx = px * RES13 - R; my = R - py * RES13
    return math.degrees(mx / 6378137.0), math.degrees(2 * math.atan(math.exp(my / 6378137.0)) - math.pi / 2)
areas = []
for s, m in svcs.items():
    t = np.load(os.path.join(cache, f'{s}.z13.npz'))
    d, f = t['depth'].copy(), t['flag'].copy(); x0, y0 = int(t['x0']), int(t['y0'])
    rows = np.where((f > 0).any(1))[0]; cols = np.where((f > 0).any(0))[0]
    d = d[rows[0]:rows[-1] + 1, cols[0]:cols[-1] + 1]; f = f[rows[0]:rows[-1] + 1, cols[0]:cols[-1] + 1]
    x0 += int(cols[0]); y0 += int(rows[0]); H, W = d.shape
    lo, hi = m['range']
    # within 1% of the scale ends the colour saturates: treat as beyond the scale
    f[(f == 1) & (d >= hi - 0.01 * (hi - lo))] = 2
    d[f == 2] = hi; d[f == 4] = lo
    filled = 0
    if report:
        yy, xx = np.mgrid[0:H, 0:W]
        mx = (x0 + xx + 0.5) * RES13 - R; my = R - (y0 + yy + 0.5) * RES13
        for a, rd, rf in report.values():
            ax0, ay0, ax1, ay1 = a['mercBounds']
            c = ((mx - ax0) / (ax1 - ax0) * a['width']).astype(int); r = ((ay1 - my) / (ay1 - ay0) * a['height']).astype(int)
            ins = (c >= 0) & (r >= 0) & (c < a['width']) & (r < a['height'])
            c = np.clip(c, 0, a['width'] - 1); r = np.clip(r, 0, a['height'] - 1)
            v, vf = rd[r, c], rf[r, c]
            need = (f == 2) & ins & (vf > 0) & (v > hi)
            use = need & (vf == 1); d[use] = v[use]; f[use] = 3                  # measured deeper value
            lim = need & (vf == 2); d[lim] = np.maximum(d[lim], v[lim])          # still clipped, but a deeper limit
            filled += int(use.sum())
    dm = np.nan_to_num(np.round(d)).clip(0, 65535).astype(np.uint16)
    enc = np.zeros((H, W, 3), np.uint8); enc[..., 0] = dm >> 8; enc[..., 1] = dm & 255; enc[..., 2] = f
    Image.fromarray(enc, 'RGB').save(os.path.join(out, f'{s}.depth.png'), optimize=True)
    lon0, lat1 = lonlat(x0, y0); lon1, lat0 = lonlat(x0 + W, y0 + H)
    areas.append({'id': s, 'name': m['name'], 'group': m['group'], 'tiles': f'{BASE}/{s}/MapServer/tile/{{z}}/{{y}}/{{x}}',
                  'maxNativeZoom': m['maxLevel'], 'scaleMin_m': lo, 'scaleMax_m': hi, 'x0': x0, 'y0': y0, 'width': W, 'height': H,
                  'bounds': [[lat0, lon0], [lat1, lon1]], 'tileFit': round(float(t['resid']), 2)})
    print(f'{s:22s} {W}x{H}  depth {np.mean(f==1):.2f}  deeper {np.mean(f==2):.3f}  from report {filled}  ->',
          os.path.getsize(os.path.join(out, f"{s}.depth.png")) // 1024, 'KB', flush=True)
ramp = json.load(open(os.path.join(os.path.dirname(sys.argv[1]), 'ramp.json')))
json.dump({'zoom': 13, 'ramp': [ramp[i] for i in range(0, len(ramp), 10)] + [ramp[-1]], 'areas': areas},
          open(os.path.join(out, 'manifest.json'), 'w'), indent=1)
