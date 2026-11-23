"""Download CRRF's public bathymetry map tiles (ArcGIS Online) for every reef section.
Usage: python fetch_tiles.py services.json CACHE_DIR [zoom=14]
Tiles are cached as CACHE_DIR/<service>/<z>/<y>/<x>.(png|jpg); re-running skips cached tiles."""
import json, os, sys, time, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor
BASE = 'https://tiles.arcgis.com/tiles/UhegwRIXa8Qj9weD/arcgis/rest/services'
R = 20037508.342789244
svcs = json.load(open(sys.argv[1])); cache = sys.argv[2]; z = int(sys.argv[3]) if len(sys.argv) > 3 else 14

def tile_range(ext, z):
    size = 2 * R / 2 ** z
    return (int((ext[0] + R) // size), int((ext[2] + R) // size), int((R - ext[3]) // size), int((R - ext[1]) // size))

def get(url, tries=4):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'palau-bathymetry-viewer'}), timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (404, 400): return None
            time.sleep(2 ** i)
        except Exception:
            time.sleep(2 ** i)
    raise RuntimeError('failed ' + url)

def fetch(job):
    s, y, x = job
    d = os.path.join(cache, s, str(z), str(y))
    for ext in ('png', 'jpg', 'none'):
        if os.path.exists(os.path.join(d, f'{x}.{ext}')): return 'cached'
    data = get(f'{BASE}/{s}/MapServer/tile/{z}/{y}/{x}')
    os.makedirs(d, exist_ok=True)
    ext = 'none' if not data else ('png' if data[:4] == b'\x89PNG' else 'jpg')
    open(os.path.join(d, f'{x}.{ext}'), 'wb').write(data or b'')
    return ext

for s, m in svcs.items():
    c0, c1, r0, r1 = tile_range(m['extent'], z)
    # request every tile in the extent (the service's tilemap index proved unreliable); empty tiles 404
    jobs = [(s, y, x) for y in range(r0, r1 + 1) for x in range(c0, c1 + 1)]
    with ThreadPoolExecutor(8) as ex:
        res = list(ex.map(fetch, jobs))
    print(s, 'tiles', len(jobs), {k: res.count(k) for k in set(res)}, flush=True)
