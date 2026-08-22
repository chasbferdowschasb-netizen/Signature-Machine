# -*- coding: utf-8 -*-
"""Signature Machine Customer Package Builder v2.1
Archive migration/repair tool for samples 001-024.
Never modifies raw.png, render.png, strokes.json or metadata.json.
Modes: --audit, --assets, --video, --pdf, --full. Existing files are kept unless --rebuild.
"""
from __future__ import annotations
import argparse,json,math,shutil
from pathlib import Path
import cv2,numpy as np
from PIL import Image
try:
 from reportlab.pdfgen import canvas
 from reportlab.lib.pagesizes import A4
 from reportlab.lib.units import mm
except ModuleNotFoundError:
 canvas=None
ROOT=Path(__file__).resolve().parent
SAMPLES=ROOT/'online_training_data'/'reference_learning'/'samples'
PKG=Path('CUSTOMER_PACKAGE'); FINAL=PKG/'01_FINAL_ASSETS'; TRAIN=PKG/'02_TRAINING'
ASSETS=['01_FINAL_BLACK_ON_WHITE.png','02_BLACK_TRANSPARENT.png','03_WHITE_ON_BLACK.png','04_WHITE_TRANSPARENT.png']
TRAINING={'01_TRAINING.mp4','01_PRACTICE.pdf'}
PRACTICE_COPIES=20; PRACTICE_ALPHA=.48
FPS=60; VW,VH=1280,720; MX,MY=.10,.18; MINSEC,MAXSEC=5.,20.; PATH_SPEED=115.

def loadj(p): return json.loads(p.read_text(encoding='utf-8'))
def source(sd):
 p=sd/'render.png'
 if p.exists(): return p
 p=sd/'raw.png'
 if p.exists(): return p
 raise FileNotFoundError('Neither render.png nor raw.png exists.')
def validate(sd):
 if not sd.is_dir(): raise FileNotFoundError(f'Sample directory missing: {sd}')
 if not (sd/'strokes.json').exists(): raise FileNotFoundError('strokes.json is missing.')
 source(sd)
def alpha(path):
 a=np.asarray(Image.open(path).convert('RGBA'),dtype=np.uint8); rgb=a[...,:3].astype(np.float32); al=a[...,3].astype(np.float32)
 g=.299*rgb[...,0]+.587*rgb[...,1]+.114*rgb[...,2]; d=np.clip(255-g,0,255)
 ink=np.maximum(d,al) if np.mean(al<250)>.05 else d; ink[g>250]=0
 return np.clip(ink,0,255).astype(np.uint8)
def bbox(a,pad=.035):
 ys,xs=np.where(a>8); h,w=a.shape
 if len(xs)==0:return 0,0,w,h
 p=max(8,int(round(min(w,h)*pad))); return max(0,int(xs.min())-p),max(0,int(ys.min())-p),min(w,int(xs.max())+1+p),min(h,int(ys.max())+1+p)
def build_assets(sd):
    """Re-render FINAL_ASSETS from stroke geometry at high resolution.
    Does not upscale the old small bitmap and never modifies engine data.
    """
    d=sd/FINAL; d.mkdir(parents=True,exist_ok=True)
    raw=sd/'raw.png'; sp=sd/'strokes.json'
    if not raw.exists(): raise FileNotFoundError('raw.png is missing.')
    if not sp.exists(): raise FileNotFoundError('strokes.json is missing.')
    data=loadj(sp); strokes=[s for s in data.get('strokes',[]) if s.get('points')]
    if not strokes: raise ValueError('No strokes in strokes.json.')
    raw_w,raw_h=Image.open(raw).size
    pts=[]
    for s in strokes:
        for q in s['points']:
            try: pts.append((float(q['x']),float(q['y'])))
            except: pass
    if not pts: raise ValueError('No valid stroke coordinates found.')
    xs=[q[0] for q in pts]; ys=[q[1] for q in pts]
    pad=max(8.0,min(raw_w,raw_h)*.035)
    x0=max(0.,min(xs)-pad); y0=max(0.,min(ys)-pad); x1=min(float(raw_w),max(xs)+pad); y1=min(float(raw_h),max(ys)+pad)
    sw=max(1.,x1-x0); sh=max(1.,y1-y0)
    TARGET=2400; scale=TARGET/max(sw,sh); ow=max(1,round(sw*scale)); oh=max(1,round(sh*scale)); SS=4
    mask_hi=np.zeros((oh*SS,ow*SS),np.uint8)
    for s in strokes:
        sm=smooth(s['points'],10)
        mapped=[((x-x0)*scale*SS,(y-y0)*scale*SS,p) for x,y,p in sm]
        if len(mapped)==1:
            x,y,pr=mapped[0]; r=max(1,round((1.25+pr*2.6)*scale*SS)); cv2.circle(mask_hi,(round(x),round(y)),r,255,-1,cv2.LINE_AA); continue
        for a,b in zip(mapped,mapped[1:]):
            xa,ya,pa=a; xb,yb,pb=b; pr=(pa+pb)/2
            ww=max(1,round((1.25+pr*5.2)*scale*SS))
            cv2.line(mask_hi,(round(xa),round(ya)),(round(xb),round(yb)),255,ww,cv2.LINE_AA)
    m=cv2.resize(mask_hi,(ow,oh),interpolation=cv2.INTER_AREA); m=cv2.GaussianBlur(m,(3,3),0); m=Image.fromarray(m,'L')
    im=Image.new('RGBA',m.size,(0,0,0,0)); im.paste((0,0,0,255),mask=m); im.save(d/ASSETS[1],optimize=True)
    im=Image.new('RGBA',m.size,(0,0,0,0)); im.paste((255,255,255,255),mask=m); im.save(d/ASSETS[3],optimize=True)
    im=Image.new('RGB',m.size,(255,255,255)); im.paste((0,0,0),mask=m); im.save(d/ASSETS[0],optimize=True)
    im=Image.new('RGB',m.size,(0,0,0)); im.paste((255,255,255),mask=m); im.save(d/ASSETS[2],optimize=True)
    return {'source':'strokes.json','source_canvas':[raw_w,raw_h],'render_method':'stroke_geometry_4x_supersampling','upscaled_bitmap':False,'target_long_side':TARGET,'output_size':[ow,oh],'scale_from_source':round(scale,4),'smooth_curves':True}

def pv(v):
 try:return max(0.,min(1.,float(v)))
 except:return .5
def xy(p):return float(p['x']),float(p['y'])
def slen(ps):return max(sum(math.hypot(xy(b)[0]-xy(a)[0],xy(b)[1]-xy(a)[1]) for a,b in zip(ps,ps[1:])),1.) if len(ps)>1 else 1.
def smooth(ps,n=10):
 if len(ps)<3:return [(float(p['x']),float(p['y']),pv(p.get('pressure'))) for p in ps]
 P=[(float(p['x']),float(p['y']),pv(p.get('pressure'))) for p in ps]; out=[P[0]]
 for i in range(len(P)-1):
  p0,p1,p2,p3=P[max(0,i-1)],P[i],P[i+1],P[min(len(P)-1,i+2)]
  for k in range(1,n+1):
   t=k/n;t2=t*t;t3=t2*t
   def cr(a,b,c,d):return .5*(2*b+(-a+c)*t+(2*a-5*b+4*c-d)*t2+(-a+3*b-3*c+d)*t3)
   out.append((cr(p0[0],p1[0],p2[0],p3[0]),cr(p0[1],p1[1],p2[1],p3[1]),max(0,min(1,cr(p0[2],p1[2],p2[2],p3[2])))))
 return out
def build_video(sd):
 data=loadj(sd/'strokes.json'); strokes=[s for s in data.get('strokes',[]) if s.get('points')];
 if not strokes:raise ValueError('No strokes in strokes.json.')
 a=alpha(sd/'raw.png'); bx0,by0,bx1,by1=bbox(a,.02); sw,sh=max(1,bx1-bx0),max(1,by1-by0); scale=min(VW*(1-2*MX)/sw,VH*(1-2*MY)/sh,3.0); ox,oy=(VW-sw*scale)/2,(VH-sh*scale)/2
 def mp(x,y):return ox+(x-bx0)*scale,oy+(y-by0)*scale
 lens=[slen(s['points']) for s in strokes]; total=max(sum(lens),1); dur=max(MINSEC,min(MAXSEC,total/PATH_SPEED)); base=[max(.22,dur*l/total) for l in lens]; f=dur/sum(base); ds=[d*f for d in base]; timeline=[];cur=0
 for s,d in zip(strokes,ds):
  sm=smooth(s['points']); ts=np.linspace(cur,cur+d,len(sm)); timeline.append([(*mp(x,y),p,float(t)) for (x,y,p),t in zip(sm,ts)]);cur+=d
 out=sd/TRAIN/'01_TRAINING.mp4'; out.parent.mkdir(parents=True,exist_ok=True); w=cv2.VideoWriter(str(out),cv2.VideoWriter_fourcc(*'mp4v'),FPS,(VW,VH))
 if not w.isOpened():raise RuntimeError('Could not create MP4 writer.')
 R=2; frames=max(1,int(math.ceil(cur*FPS)))
 for fi in range(frames):
  t=fi/FPS; hi=np.full((VH*R,VW*R,3),255,np.uint8)
  for pts in timeline:
   if not pts or t<pts[0][3]:continue
   vis=[]
   for j,(x,y,p,tt) in enumerate(pts):
    if t>=tt:vis.append((x,y,p))
    elif j:
     x0,y0,p0,t0=pts[j-1]; q=max(0,min(1,(t-t0)/max(tt-t0,1e-9)));vis.append((x0+(x-x0)*q,y0+(y-y0)*q,p0+(p-p0)*q));break
   for A,B in zip(vis,vis[1:]):
    x0,y0,p0=A;x1,y1,p1=B;ww=max(2,int(round((1.25+(p0+p1)/2*5.2)*R)));cv2.line(hi,(round(x0*R),round(y0*R)),(round(x1*R),round(y1*R)),(0,0,0),ww,cv2.LINE_AA)
  w.write(cv2.resize(hi,(VW,VH),interpolation=cv2.INTER_AREA))
 w.release();return {'duration_seconds':round(cur,2),'fps':FPS,'frame_size':[VW,VH],'centered':True,'idle_gaps_removed':True,'smooth_rendering':True,'raw_coordinates_preserved':True,'scale':round(scale,4)}
def build_pdf(sd):
 if canvas is None:raise RuntimeError('reportlab is not installed. Run: python -m pip install reportlab')
 s=source(sd); a=alpha(s);x0,y0,x1,y1=bbox(a,.02); crop=a[y0:y1,x0:x1]; rgba=np.zeros((*crop.shape,4),np.uint8);rgba[...,:3]=95;rgba[...,3]=np.clip(crop.astype(np.float32)*PRACTICE_ALPHA,0,255).astype(np.uint8);tmp=sd/'.practice_faint.png';Image.fromarray(rgba,'RGBA').save(tmp)
 out=sd/TRAIN/'01_PRACTICE.pdf';out.parent.mkdir(parents=True,exist_ok=True);c=canvas.Canvas(str(out),pagesize=A4);W,H=A4;c.setFillColorRGB(.35,.35,.35);c.setFont('Helvetica',11);c.drawString(18*mm,H-15*mm,'Signature Practice');cols,rows=4,5;mx=9*mm;top=22*mm;bottom=7*mm;cw=(W-2*mx)/cols;ch=(H-top-bottom)/rows;iw,ih=crop.shape[1],crop.shape[0]
 for i in range(20):
  r,col=divmod(i,cols);scale=min(cw*.90/max(iw,1),ch*.68/max(ih,1));dw,dh=iw*scale,ih*scale;x=mx+col*cw+(cw-dw)/2;y=H-top-(r+1)*ch+(ch-dh)/2;c.drawImage(str(tmp),x,y,width=dw,height=dh,mask='auto',preserveAspectRatio=True);c.setFillColorRGB(.5,.5,.5);c.setFont('Helvetica',6.5);c.drawString(x+2,y+2,str(i+1))
 c.save();tmp.unlink(missing_ok=True)
def status(sd):
 d=sd;fd=d/FINAL;td=d/TRAIN;return {'assets':{n:(fd/n).exists() for n in ASSETS},'training':{n:(td/n).exists() for n in TRAINING},'manifest':(d/PKG/'manifest.json').exists(),'obsolete':[p.name for p in td.iterdir()] if td.exists() else []}
def manifest(sd,vi=None,ai=None):
 st=status(sd);pkg=sd/PKG;pkg.mkdir(exist_ok=True);meta={};mp=sd/'metadata.json'
 if mp.exists():
  try:meta=loadj(mp)
  except:pass
 obj={'schema_version':'customer_package_archive_v2_2','sample_id':sd.name,'label':meta.get('label','unlabeled'),'engine_data_untouched':True,'customer_package':{'final_assets':[f'CUSTOMER_PACKAGE/01_FINAL_ASSETS/{n}' for n in ASSETS],'training':['CUSTOMER_PACKAGE/02_TRAINING/01_PRACTICE.pdf','CUSTOMER_PACKAGE/02_TRAINING/01_TRAINING.mp4']},'practice_sheet':{'format':'A4','copies':20,'layout':'4x5','print_faintness_alpha':PRACTICE_ALPHA},'training_video':vi,'final_assets':ai,'status':st}
 (pkg/'manifest.json').write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
def clean(td):
 td.mkdir(parents=True,exist_ok=True)
 for p in list(td.iterdir()):
  if p.is_file() and p.name not in TRAINING:p.unlink()
  elif p.is_dir():shutil.rmtree(p)
def full(sd,rebuild=False):
 validate(sd);fd=sd/FINAL;td=sd/TRAIN;fd.mkdir(parents=True,exist_ok=True);td.mkdir(parents=True,exist_ok=True);ai=vi=None
 if rebuild or not all((fd/n).exists() for n in ASSETS):ai=build_assets(sd)
 if rebuild or not (td/'01_TRAINING.mp4').exists():vi=build_video(sd)
 if rebuild or not (td/'01_PRACTICE.pdf').exists():build_pdf(sd)
 clean(td);manifest(sd,vi,ai);return 'full package complete'
def audit(sd):
 validate(sd);st=status(sd);print(f'[{sd.name}]');print('Assets:',st['assets']);print('Training:',st['training']);print('Manifest:',st['manifest']);print('Training files:',st['obsolete'])
def main():
 p=argparse.ArgumentParser();p.add_argument('--sample',action='append',required=True);g=p.add_mutually_exclusive_group(required=True);g.add_argument('--audit',action='store_true');g.add_argument('--assets',action='store_true');g.add_argument('--video',action='store_true');g.add_argument('--pdf',action='store_true');g.add_argument('--full',action='store_true');p.add_argument('--rebuild',action='store_true');a=p.parse_args();mode='audit' if a.audit else 'assets' if a.assets else 'video' if a.video else 'pdf' if a.pdf else 'full';print('='*72);print('CUSTOMER PACKAGE BUILDER v2.2');print('Mode:',mode,' Rebuild:',a.rebuild);print('='*72)
 for name in a.sample:
  sd=SAMPLES/name
  try:
   if mode=='audit':audit(sd);continue
   if mode=='full':msg=full(sd,a.rebuild)
   elif mode=='assets':
    validate(sd);fd=sd/FINAL;exists=all((fd/n).exists() for n in ASSETS);ai=None if exists and not a.rebuild else build_assets(sd);manifest(sd,ai,None);msg='assets already exist; kept' if exists and not a.rebuild else 'assets rebuilt'
   elif mode=='video':
    validate(sd);td=sd/TRAIN;target=td/'01_TRAINING.mp4';exists=target.exists();vi=None if exists and not a.rebuild else build_video(sd);clean(td);manifest(sd,vi,None);msg='video already exists; kept' if exists and not a.rebuild else 'video rebuilt'
   else:
    validate(sd);target=sd/TRAIN/'01_PRACTICE.pdf';exists=target.exists();
    if not exists or a.rebuild:build_pdf(sd)
    clean(sd/TRAIN);manifest(sd);msg='PDF already exists; kept' if exists and not a.rebuild else 'PDF rebuilt'
   print(f'{name}: {msg}')
  except Exception as e:print(f'{name}: ERROR: {e}')
 print('Done.')
if __name__=='__main__':main()
