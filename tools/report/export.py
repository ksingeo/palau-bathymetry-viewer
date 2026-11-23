"""Reproject decoded depth grids (UTM 53N) to Web Mercator and write the viewer's data files:
  <id>.depth.png  lossless: R,G = depth in decimetres (16 bit), B = 0 no data / 1 depth / 2 deeper than figure scale
  <id>.webp       shaded-relief colour image for display
  manifest.json   bounds and metadata for every area
Usage: python export.py config.json OUTDIR [area ...]   (run inside the work directory)"""
import sys, json, numpy as np
from PIL import Image
from pyproj import Transformer
from scipy import ndimage as ndi
cfg=json.load(open(sys.argv[1])); outdir=sys.argv[2]; names=sys.argv[3:] or list(cfg)
utm2ll=Transformer.from_crs(32653,4326,always_xy=True); ll2merc=Transformer.from_crs(4326,3857,always_xy=True)
merc2utm=Transformer.from_crs(3857,32653,always_xy=True)
FT=3.28084
# unified colour ramp (depth in feet, sqrt scale) -- warm = shallow, violet = deep
STOPS=[(0,(255,60,40)),(150,(255,110,20)),(600,(255,180,0)),(1500,(250,240,40)),(3000,(170,240,110)),
       (5000,(40,220,220)),(8000,(40,140,250)),(11500,(50,60,230)),(16500,(90,20,170))]
sx=np.sqrt([s[0] for s in STOPS]); sc=np.array([s[1] for s in STOPS],float)
def ramp(ft):
    t=np.sqrt(np.clip(ft,0,STOPS[-1][0]))
    return np.stack([np.interp(t,sx,sc[:,i]) for i in range(3)],-1)
manifest={'areas':[],'ramp':[{'ft':s[0],'rgb':s[1]} for s in STOPS]}
for name in names:
    c=cfg[name]
    depth=np.load(f"{name}_depth.npy"); clip=np.load(f"{name}_clip.npy")
    (px0,E0),(px1,E1)=c['geo']['x']; (py0,N0),(py1,N1)=c['geo']['y']
    sxm=(E1-E0)/(px1-px0); sym=(N1-N0)/(py1-py0)
    fx0,fx1,fy0,fy1=c['frame']
    H,W=depth.shape
    ok=~np.isnan(depth); rows=np.where(ok.any(1))[0]; cols=np.where(ok.any(0))[0]
    # UTM bounds of data (pixel centres in full-image coords)
    e_lo=E0+(cols[0]+fx0-px0)*sxm; e_hi=E0+(cols[-1]+fx0-px0)*sxm
    n_hi=N0+(rows[0]+fy0-py0)*sym; n_lo=N0+(rows[-1]+fy0-py0)*sym
    ee,nn=np.meshgrid([e_lo,e_hi],[n_lo,n_hi]); lon,lat=utm2ll.transform(ee.ravel(),nn.ravel())
    mx,my=ll2merc.transform(lon,lat)
    lat_c=np.mean(lat); res_ground=max(abs(sxm),c.get('minres',15))
    res=res_ground/np.cos(np.radians(lat_c))                   # mercator metres per pixel
    mx0,mx1,my0,my1=min(mx),max(mx),min(my),max(my)
    nx=int(np.ceil((mx1-mx0)/res)); ny=int(np.ceil((my1-my0)/res))
    mx1=mx0+nx*res; my0=my1-ny*res                              # exact extent of the pixel grid
    gx=mx0+(np.arange(nx)+0.5)*res; gy=my1-(np.arange(ny)+0.5)*res
    GX,GY=np.meshgrid(gx,gy)
    E,N=merc2utm.transform(GX.ravel(),GY.ravel())
    ci=((E-E0)/sxm+px0-fx0); ri=((N-N0)/sym+py0-fy0)
    # area-average when downsampling: pre-smooth source by the scale factor
    f=res_ground/abs(sxm)
    src=np.nan_to_num(depth); w=ok.astype(np.float32)
    if f>1.3:
        src=ndi.uniform_filter(src*w,int(round(f))); w2=ndi.uniform_filter(w,int(round(f)))
        src=np.where(w2>0,src/np.maximum(w2,1e-6),0)
    ii=np.clip(np.round(ri).astype(int),0,H-1); jj=np.clip(np.round(ci).astype(int),0,W-1)
    inside=(ri>=0)&(ri<H)&(ci>=0)&(ci<W)
    d=np.where(inside&ok[ii,jj],src[ii,jj],np.nan).reshape(ny,nx)
    cl=(inside&clip[ii,jj]).reshape(ny,nx)&~np.isnan(d)
    valid=~np.isnan(d)
    # --- depth-encoded PNG: R,G = decimetres (16 bit), B = 0 nodata / 1 depth / 2 deeper than scale
    dm=np.round(np.nan_to_num(d)*10).clip(0,65535).astype(np.uint16)
    enc=np.zeros((ny,nx,3),np.uint8); enc[...,0]=dm>>8; enc[...,1]=dm&255
    enc[...,2]=np.where(valid,np.where(cl,2,1),0)
    Image.fromarray(enc,'RGB').save(f"{outdir}/{name}.depth.png",optimize=True)
    # --- display PNG: colour ramp x hillshade
    dd=np.where(valid,d,np.nan); fill=np.where(valid,d,ndi.grey_dilation(np.nan_to_num(d),size=3))
    z=-fill; gyd,gxd=np.gradient(z,res_ground)
    ex=c.get('hs_exag',2.0)
    slope=np.arctan(ex*np.hypot(gxd,gyd)); aspect=np.arctan2(-gxd,gyd)
    az,alt=np.radians(315),np.radians(45)
    hs=np.sin(alt)*np.cos(slope)+np.cos(alt)*np.sin(slope)*np.cos(az-aspect)
    hs=np.clip(hs,0,1)
    col=ramp(np.nan_to_num(dd)*FT)*(0.45+0.65*hs[...,None])
    # areas deeper than the source figure's colour scale: desaturate + diagonal hatch
    jj_,ii_=np.meshgrid(np.arange(nx),np.arange(ny)); hatch=((ii_+jj_)//5)%3==0
    g=col.mean(-1,keepdims=True); col=np.where(cl[...,None],0.55*col+0.45*g,col)
    col=np.where((cl&hatch)[...,None],col*0.55,col)
    rgba=np.zeros((ny,nx,4),np.uint8); rgba[...,:3]=col.clip(0,255); rgba[...,3]=np.where(valid,255,0)
    Image.fromarray(rgba,'RGBA').save(f"{outdir}/{name}.webp",quality=82,method=6)
    lon0,lat0=Transformer.from_crs(3857,4326,always_xy=True).transform(mx0,my0)
    lon1,lat1=Transformer.from_crs(3857,4326,always_xy=True).transform(mx1,my1)
    lo,hi=c['range']
    manifest['areas'].append({'id':name,'name':c['label'],'figure':c['figure'],
        'bounds':[[lat0,lon0],[lat1,lon1]],'mercBounds':[mx0,my0,mx1,my1],'width':nx,'height':ny,
        'groundRes_m':round(res_ground,1),'scaleMin_m':lo,'scaleMax_m':hi,
        # the legend's red end has ~constant hue for its first ~4%: depths below this cannot be resolved
        'shallowLimit_m':round(lo+c.get('shallow_f',0.04)*(hi-lo)),
        'depthRange_m':[round(float(np.nanmin(d)),1),round(float(np.nanmax(d)),1)]})
    print(name,nx,ny,'res',round(res_ground,1),'m')
json.dump(manifest,open(f"{outdir}/manifest.json",'w'),indent=1)
