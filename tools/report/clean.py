"""Turn raw decoded pixels into a clean depth grid: drop background/satellite speckle."""
import sys, json, numpy as np
from PIL import Image
from scipy import ndimage as ndi
cfg=json.load(open(sys.argv[1])); name=sys.argv[2]; c=cfg[name]  # run inside the work directory
d=np.load(f"{name}_raw.npz"); depth=d['depth']; valid=d['valid'].copy()
im=np.asarray(Image.open(f"{name}.png").convert('RGB')).astype(int)
x0,x1,y0,y1=c['frame']; sub=im[y0:y1,x0:x1]
mx=sub.max(2); ch=mx-sub.min(2)
valid&=(mx>=c.get('vmin',75))&(ch>=c.get('cmin',45))
for (ax0,ay0,ax1,ay1) in c.get('exclude',[]):           # legend box, logo (image px)
    valid[max(ay0-y0,0):ay1-y0, max(ax0-x0,0):ax1-x0]=False
clipped=d['clipped']
mpp=abs((c['geo']['x'][1][1]-c['geo']['x'][0][1])/(c['geo']['x'][1][0]-c['geo']['x'][0][0]))
lo=c['range'][0]
shallow=valid&(depth<lo+250)
dist=ndi.distance_transform_edt(~shallow)*mpp
valid&=~(depth>lo+250+c.get('maxslope',2.0)*dist)
# local smoothness: satellite imagery decodes to speckle, real data is smooth
w=c.get('win',11)
v=valid.astype(np.float32); dz=np.where(valid,depth,0)
cnt=ndi.uniform_filter(v,w); m1=ndi.uniform_filter(dz,w); m2=ndi.uniform_filter(dz*dz,w)
mean=m1/np.maximum(cnt,1e-6); std=np.sqrt(np.maximum(m2/np.maximum(cnt,1e-6)-mean**2,0))
rng=c['range'][1]-c['range'][0]
good=valid&(cnt>0.6)&(std<c.get('stdmax',0.06)*rng)
good=ndi.binary_opening(good,iterations=2)
lab,n=ndi.label(good); sz=ndi.sum(good,lab,range(1,n+1))
keep=np.zeros(n+1,bool); keep[1:]=sz>=c.get('minarea',20000)
good=keep[lab]
# region = filled footprint; fill small holes (shadows) by nearest-neighbour from good pixels
region=ndi.binary_closing(good,iterations=4)
holes=ndi.binary_fill_holes(region)&~region
hl,hn=ndi.label(holes)
# fill holes ringed by deep water (hillshade shadows); keep holes ringed by shallow reef (islands, lagoons)
ring=ndi.binary_dilation(holes,iterations=2)&good
idx0=ndi.distance_transform_edt(~good,return_distances=False,return_indices=True)
near=depth[idx0[0],idx0[1]]
ringlab=hl[ndi.distance_transform_edt(hl==0,return_distances=False,return_indices=True)[0],ndi.distance_transform_edt(hl==0,return_distances=False,return_indices=True)[1]]
mins=ndi.minimum(np.where(ring,depth,1e9),np.where(ring,ringlab,0),range(1,hn+1)) if hn else []
fill=np.zeros(hn+1,bool)
for i,m in enumerate(mins): fill[i+1]= m>lo+c.get('islanddepth',120)
region|=fill[hl]
idx=ndi.distance_transform_edt(~good,return_distances=False,return_indices=True)
filled=depth[idx[0],idx[1]]
out=np.where(region,filled,np.nan).astype(np.float32)
# light smoothing to suppress JPEG/hillshade noise
sm=ndi.gaussian_filter(np.nan_to_num(out),c.get('sigma',1.5)); wt=ndi.gaussian_filter(region.astype(np.float32),c.get('sigma',1.5))
out=np.where(region,sm/np.maximum(wt,1e-6),np.nan).astype(np.float32)
clip=clipped[idx[0],idx[1]]&region
clip=ndi.binary_opening(clip,iterations=1)
out[clip]=c['range'][1]
np.save(f"{name}_depth.npy",out); np.save(f"{name}_clip.npy",clip)
vis=np.zeros(out.shape+(3,),np.uint8); f=(np.nan_to_num(out)-c['range'][0])/rng
vis[region]=np.stack([255*(1-f),40+0*f,255*f],-1)[region].clip(0,255).astype(np.uint8)
Image.fromarray(vis).resize((vis.shape[1]//3,vis.shape[0]//3)).save(f"{name}_clean.png")
print(name,'coverage',region.mean().round(3),'depth range',np.nanmin(out).round(),np.nanmax(out).round())
