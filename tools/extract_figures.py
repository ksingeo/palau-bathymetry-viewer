"""Pull the five bathymetry figures (report Figures 6-10, pages 10-14) out of the CRRF PDF.
Each figure is embedded as two stacked JPEG strips; they are stitched back into <id>.png.
Usage: python extract_figures.py REPORT.pdf config.json WORKDIR   (needs poppler-utils: pdfimages)"""
import sys, json, os, glob, subprocess
from PIL import Image
pdf, cfgp, work = sys.argv[1:4]
cfg = json.load(open(cfgp)); os.makedirs(work, exist_ok=True)
for name, c in cfg.items():
    p = str(c['pages'])
    pre = os.path.join(work, f"_p{p}")
    subprocess.run(['pdfimages', '-png', '-f', p, '-l', p, pdf, pre], check=True)
    files = sorted(glob.glob(pre + '-*.png'))
    ims = sorted((Image.open(f) for f in files), key=lambda im: -im.width * im.height)
    # the two largest images share the figure width: top strip + bottom strip
    big = [im for im in ims if im.width == ims[0].width][:2]
    big.sort(key=lambda im: -im.height)
    top, bottom = big
    out = Image.new('RGB', (top.width, top.height + bottom.height))
    out.paste(top.convert('RGB'), (0, 0)); out.paste(bottom.convert('RGB'), (0, top.height))
    out.save(os.path.join(work, f"{name}.png"))
    for f in files: os.remove(f)
    print(name, out.size)
