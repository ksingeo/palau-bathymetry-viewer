"""Decode CRRF's rendered bathymetry tiles back into depth.
Tiles are drawn with one colour ramp (tools/tiles/ramp.json, from the services' own legend) stretched
linearly between each service's legend limits and laid ~10% transparent over a hillshade, so
pixel ~= a * ramp(f) + b. Each pixel is matched to the ramp position f that fits best.
Output: CACHE/<service>.z13.npz with depth (m, float32), flag (1 depth, 2 deeper than scale,
4 shallower than scale) on the global zoom-13 Web Mercator pixel grid (origin x0, y0).
Usage: python decode_tiles.py services.json ramp.json CACHE_DIR [service ...]"""
import json, sys, os, glob, numpy as np
from PIL import Image
svcs = json.load(open(sys.argv[1])); ramp = np.array(json.load(open(sys.argv[2])), np.float32)
cache = sys.argv[3]; names = sys.argv[4:] or list(svcs)
Z = 14
# lookup table over a 6-bit colour cube: best ramp position + fit residual
N = 600
t = np.linspace(0, 1, N); x = np.linspace(0, 1, len(ramp))
L = np.stack([np.interp(t, x, ramp[:, i]) for i in range(3)], 1).astype(np.float32)
q = np.arange(64) * 4 + 2
P = np.stack(np.meshgrid(q, q, q, indexing='ij'), -1).reshape(-1, 3).astype(np.float32)
best = np.full(len(P), 1e9, np.float32); bf = np.zeros(len(P), np.float32)
for i, C in enumerate(L):
    G = np.linalg.pinv(np.stack([C, np.ones(3, np.float32)], 1))
    ab = P @ G.T
    r = np.linalg.norm(P - (ab[:, :1] * C + ab[:, 1:]), axis=1)
    ok = (ab[:, 0] > 0.5) & (ab[:, 0] < 1.2) & (ab[:, 1] > -25) & (ab[:, 1] < 90)
    r = np.where(ok, r, 1e9); m = r < best; best[m] = r[m]; bf[m] = t[i]
LUT_F = bf.reshape(64, 64, 64); LUT_R = best.reshape(64, 64, 64)

for s in names:
    files = glob.glob(os.path.join(cache, s, str(Z), '*', '*.*'))
    tiles = [(int(f.split(os.sep)[-2]), int(os.path.splitext(os.path.basename(f))[0]), f) for f in files if not f.endswith('.none')]
    ys = [a for a, _, _ in tiles]; xs = [b for _, b, _ in tiles]
    y0, x0 = min(ys) & ~1, min(xs) & ~1                      # even, so 2x2 blocks align with zoom 13
    H = (max(ys) - y0 + 2) // 2 * 2 * 256; W = (max(xs) - x0 + 2) // 2 * 2 * 256
    rgba = np.zeros((H, W, 4), np.uint8)
    for ty, tx, f in tiles:
        im = np.asarray(Image.open(f).convert('RGBA'))
        rgba[(ty - y0) * 256:(ty - y0 + 1) * 256, (tx - x0) * 256:(tx - x0 + 1) * 256] = im
    c = rgba[..., :3].astype(np.int32) >> 2
    f = LUT_F[c[..., 0], c[..., 1], c[..., 2]]; r = LUT_R[c[..., 0], c[..., 1], c[..., 2]]
    valid = (rgba[..., 3] >= 200) & (r < 12)       # some services are drawn ~10% transparent
    lo, hi = svcs[s]['range']
    # 2x2 block average -> zoom 13 (~19 m, the survey's 20 m grid)
    def blk(a): return a.reshape(H // 2, 2, W // 2, 2).sum((1, 3))
    n = blk(valid.astype(np.float32))
    fm = blk(np.where(valid, f, 0)) / np.maximum(n, 1)
    deep = blk((valid & (f >= 0.997)).astype(np.float32)); shal = blk((valid & (f <= 0.003)).astype(np.float32))
    ok = n >= 2
    depth = np.where(ok, lo + fm * (hi - lo), np.nan).astype(np.float32)
    flag = np.where(ok, 1, 0).astype(np.uint8)
    flag[ok & (deep * 2 > n)] = 2; flag[ok & (shal * 2 > n)] = 4
    np.savez_compressed(os.path.join(cache, f'{s}.z13.npz'), depth=depth, flag=flag, x0=(x0 * 256) // 2, y0=(y0 * 256) // 2,
                        resid=np.float32(np.median(r[valid])))
    print(f'{s:22s} {W//2}x{H//2} px  valid {ok.mean():.2f}  deeper {np.mean(flag==2):.3f}  median fit residual {np.median(r[valid]):.2f}', flush=True)
