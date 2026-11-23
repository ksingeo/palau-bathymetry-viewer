"""Decode a rendered bathymetry figure back into a depth grid.
Model: pixel = a * legend(f) + b*(1,1,1); a = hillshade factor, b = gray floor."""
import sys, json, numpy as np
from PIL import Image
cfg=json.load(open(sys.argv[1])); name=sys.argv[2]; c=cfg[name]  # run inside the work directory
im=np.asarray(Image.open(f"{name}.png").convert('RGB')).astype(np.float32)
bx0,bx1,by0,by1=c['bar']
leg=im[by0+8:by1-8, bx0+4:bx1-3].mean(0)            # (N,3)
N=len(leg); fvals=np.linspace(0,1,N)
# LUT over quantized colour cube (5 bits/channel)
q=np.arange(32)*8+4
P=np.stack(np.meshgrid(q,q,q,indexing='ij'),-1).reshape(-1,3).astype(np.float32)  # (M,3)
ones=np.ones(3,np.float32)
best_r=np.full(len(P),1e9,np.float32); best_f=np.zeros(len(P),np.float32)
for i in range(N):
    C=leg[i]
    # least squares for [a,b]: A=[C,1]
    A=np.stack([C,ones],1)                      # 3x2
    G=np.linalg.pinv(A)                         # 2x3
    ab=P@G.T                                    # (M,2)
    a,b=ab[:,0],ab[:,1]
    ok=(a>c.get('amin',0.18))&(a<1.15)&(b>-20)&(b<c.get('bmax',75))
    r=np.linalg.norm(P-(a[:,None]*C+b[:,None]),axis=1)
    r=np.where(ok,r,1e9)
    m=r<best_r; best_r[m]=r[m]; best_f[m]=fvals[i]
lut_f=best_f.reshape(32,32,32); lut_r=best_r.reshape(32,32,32)
x0,x1,y0,y1=c['frame']
sub=im[y0:y1,x0:x1].astype(int)//8
f=lut_f[sub[...,0],sub[...,1],sub[...,2]]; r=lut_r[sub[...,0],sub[...,1],sub[...,2]]
valid=r<c.get('rmax',12)
px=im[y0:y1,x0:x1]; R,G,B=px[...,0],px[...,1],px[...,2]
mx=px.max(2); mn=px.min(2); chroma=mx-mn
hue=np.degrees(np.arctan2(np.sqrt(3)*(G-B),2*R-G-B))%360
clipped=(~valid)&(hue>245)&(hue<300)&(chroma>70)&(B>120)
f=np.where(clipped,1.0,f); valid=valid|clipped
lo,hi=c['range']
depth=lo+f*(hi-lo)
np.savez_compressed(f"{name}_raw.npz",depth=depth.astype(np.float32),valid=valid,clipped=clipped,resid=r.astype(np.float32))
# diagnostic
vis=np.zeros(depth.shape+(3,),np.uint8)
vis[valid]=(np.stack([255*(1-f),255*np.abs(0.5-f)*0,255*f],-1)[valid]).astype(np.uint8)
Image.fromarray(vis).resize((vis.shape[1]//3,vis.shape[0]//3)).save(f"{name}_diag.png")
print(name,'valid frac',valid.mean().round(3))
