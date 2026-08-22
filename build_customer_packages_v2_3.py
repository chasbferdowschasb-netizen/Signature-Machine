# -*- coding: utf-8 -*-
"""Signature Machine Customer Package Builder v2.3
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
FPS=60; VW,VH=1336,512; MX,MY=.16,.20; MINSEC,MAXSEC=5.,20.; PATH_SPEED=115.

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
    """
    Build the single approved training video.

    Standard:
      - 1336x512, 60 fps (same canvas class as the approved Sample 001 video)
      - signature is centered from STROKE geometry, not from its original
        canvas position
      - real idle time between pen-down strokes is ignored
      - total path is played continuously at a slow, uniform teaching speed
      - curves are Catmull-Rom smoothed and rendered with 2x supersampling
      - no monitor/display mockup and no extra training files
    """
    data = loadj(sd / 'strokes.json')
    strokes = [s for s in data.get('strokes', []) if s.get('points')]
    if not strokes:
        raise ValueError('No strokes in strokes.json.')

    # Bounds come from stroke geometry. This is the key fix for signatures
    # drawn anywhere on the browser canvas: the video framing is independent
    # of the original canvas location.
    pts = []
    for s in strokes:
        for p in s.get('points', []):
            try:
                pts.append((float(p['x']), float(p['y'])))
            except Exception:
                pass

    if not pts:
        raise ValueError('No valid stroke coordinates found.')

    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]

    pad_x = max(8.0, (max(xs) - min(xs)) * 0.055)
    pad_y = max(8.0, (max(ys) - min(ys)) * 0.080)

    bx0 = min(xs) - pad_x
    by0 = min(ys) - pad_y
    bx1 = max(xs) + pad_x
    by1 = max(ys) + pad_y

    sw = max(1.0, bx1 - bx0)
    sh = max(1.0, by1 - by0)

    # Fit the signature inside the approved video canvas while keeping it
    # visually centered and leaving comfortable white margins.
    usable_w = VW * (1.0 - 2.0 * MX)
    usable_h = VH * (1.0 - 2.0 * MY)
    scale = min(usable_w / sw, usable_h / sh)

    draw_w = sw * scale
    draw_h = sh * scale

    ox = (VW - draw_w) / 2.0
    oy = (VH - draw_h) / 2.0

    def mp(x, y):
        return ox + (x - bx0) * scale, oy + (y - by0) * scale

    # Ignore actual pen-up gaps. Timing is based only on stroke path length.
    lens = [slen(s['points']) for s in strokes]
    total = max(sum(lens), 1.0)

    duration = max(MINSEC, min(MAXSEC, total / PATH_SPEED))
    base = [max(0.22, duration * L / total) for L in lens]
    factor = duration / max(sum(base), 1e-9)
    durations = [d * factor for d in base]

    timeline = []
    cur = 0.0

    for s, d in zip(strokes, durations):
        sm = smooth(s['points'], 12)
        ts = np.linspace(cur, cur + d, len(sm))
        timeline.append([
            (*mp(x, y), p, float(t))
            for (x, y, p), t in zip(sm, ts)
        ])
        cur += d

    out = sd / TRAIN / '01_TRAINING.mp4'
    out.parent.mkdir(parents=True, exist_ok=True)

    writer = cv2.VideoWriter(
        str(out),
        cv2.VideoWriter_fourcc(*'mp4v'),
        FPS,
        (VW, VH)
    )

    if not writer.isOpened():
        raise RuntimeError('Could not create MP4 writer.')

    R = 2
    frames = max(1, int(math.ceil(cur * FPS)))

    for fi in range(frames):
        t = fi / FPS
        hi = np.full((VH * R, VW * R, 3), 255, np.uint8)

        for pts_tl in timeline:
            if not pts_tl or t < pts_tl[0][3]:
                continue

            visible = []

            for j, (x, y, p, tt) in enumerate(pts_tl):
                if t >= tt:
                    visible.append((x, y, p))
                elif j:
                    x0, y0, p0, t0 = pts_tl[j - 1]
                    q = max(0.0, min(1.0, (t - t0) / max(tt - t0, 1e-9)))
                    visible.append((
                        x0 + (x - x0) * q,
                        y0 + (y - y0) * q,
                        p0 + (p - p0) * q
                    ))
                    break

            for A, B in zip(visible, visible[1:]):
                x0, y0, p0 = A
                x1, y1, p1 = B
                pr = (p0 + p1) / 2.0

                width = max(
                    2,
                    int(round((1.25 + pr * 5.2) * R))
                )

                cv2.line(
                    hi,
                    (round(x0 * R), round(y0 * R)),
                    (round(x1 * R), round(y1 * R)),
                    (0, 0, 0),
                    width,
                    cv2.LINE_AA
                )

        frame = cv2.resize(
            hi,
            (VW, VH),
            interpolation=cv2.INTER_AREA
        )
        writer.write(frame)

    writer.release()

    return {
        'duration_seconds': round(cur, 2),
        'fps': FPS,
        'frame_size': [VW, VH],
        'centered_from_strokes': True,
        'idle_gaps_removed': True,
        'uniform_teaching_speed': True,
        'smooth_rendering': True,
        'supersampling': 2,
        'original_canvas_position_ignored': True
    }

def build_pdf(sd):
    """
    Build the single A4 practice sheet from the approved high-resolution
    FINAL_BLACK_ON_WHITE asset.

    Standard:
      - A4
      - 20 copies, 4x5
      - print-visible faint black signature
      - one PDF only: 01_PRACTICE.pdf
    """
    if canvas is None:
        raise RuntimeError(
            'reportlab is not installed. Run: python -m pip install reportlab'
        )

    final_asset = sd / FINAL / '01_FINAL_BLACK_ON_WHITE.png'

    if not final_asset.exists():
        # Keep the builder self-contained if PDF is requested before assets.
        build_assets(sd)

    src = Image.open(final_asset).convert('RGB')
    rgb = np.asarray(src, dtype=np.uint8)

    # Convert the approved black-on-white asset to a print-friendly
    # grayscale alpha mask. This avoids using the old low-resolution
    # render/raw source for the practice sheet.
    gray = (
        0.299 * rgb[..., 0]
        + 0.587 * rgb[..., 1]
        + 0.114 * rgb[..., 2]
    )

    ink = np.clip(255.0 - gray, 0, 255).astype(np.uint8)

    # Keep a little more visible ink than the original faint version.
    alpha_channel = np.clip(
        ink.astype(np.float32) * 0.58,
        0,
        255
    ).astype(np.uint8)

    # Crop to actual ink while preserving a small margin.
    x0, y0, x1, y1 = bbox(alpha_channel, .025)
    crop = alpha_channel[y0:y1, x0:x1]

    rgba = np.zeros((*crop.shape, 4), dtype=np.uint8)
    rgba[..., :3] = 0
    rgba[..., 3] = crop

    tmp = sd / '.practice_faint.png'
    Image.fromarray(rgba, 'RGBA').save(tmp)

    out = sd / TRAIN / '01_PRACTICE.pdf'
    out.parent.mkdir(parents=True, exist_ok=True)

    c = canvas.Canvas(str(out), pagesize=A4)
    W, H = A4

    cols, rows = 4, 5
    mx = 9 * mm
    top = 18 * mm
    bottom = 7 * mm

    cw = (W - 2 * mx) / cols
    ch = (H - top - bottom) / rows

    iw, ih = crop.shape[1], crop.shape[0]

    for i in range(PRACTICE_COPIES):
        r, col = divmod(i, cols)

        fit = min(
            cw * 0.90 / max(iw, 1),
            ch * 0.72 / max(ih, 1)
        )

        dw = iw * fit
        dh = ih * fit

        x = mx + col * cw + (cw - dw) / 2
        y = H - top - (r + 1) * ch + (ch - dh) / 2

        c.drawImage(
            str(tmp),
            x,
            y,
            width=dw,
            height=dh,
            mask='auto',
            preserveAspectRatio=True
        )

    c.save()
    tmp.unlink(missing_ok=True)

    return {
        'format': 'A4',
        'copies': PRACTICE_COPIES,
        'layout': '4x5',
        'source': '01_FINAL_BLACK_ON_WHITE.png',
        'print_alpha': 0.58,
        'single_page': True
    }

def status(sd):
 d=sd;fd=d/FINAL;td=d/TRAIN;return {'assets':{n:(fd/n).exists() for n in ASSETS},'training':{n:(td/n).exists() for n in TRAINING},'manifest':(d/PKG/'manifest.json').exists(),'obsolete':[p.name for p in td.iterdir()] if td.exists() else []}
def manifest(sd,vi=None,ai=None):
 st=status(sd);pkg=sd/PKG;pkg.mkdir(exist_ok=True);meta={};mp=sd/'metadata.json'
 if mp.exists():
  try:meta=loadj(mp)
  except:pass
 obj={'schema_version':'customer_package_archive_v2_3','sample_id':sd.name,'label':meta.get('label','unlabeled'),'engine_data_untouched':True,'customer_package':{'final_assets':[f'CUSTOMER_PACKAGE/01_FINAL_ASSETS/{n}' for n in ASSETS],'training':['CUSTOMER_PACKAGE/02_TRAINING/01_PRACTICE.pdf','CUSTOMER_PACKAGE/02_TRAINING/01_TRAINING.mp4']},'practice_sheet':{'format':'A4','copies':20,'layout':'4x5','print_faintness_alpha':PRACTICE_ALPHA},'training_video':vi,'final_assets':ai,'status':st}
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
 p=argparse.ArgumentParser();p.add_argument('--sample',action='append',required=True);g=p.add_mutually_exclusive_group(required=True);g.add_argument('--audit',action='store_true');g.add_argument('--assets',action='store_true');g.add_argument('--video',action='store_true');g.add_argument('--pdf',action='store_true');g.add_argument('--full',action='store_true');p.add_argument('--rebuild',action='store_true');a=p.parse_args();mode='audit' if a.audit else 'assets' if a.assets else 'video' if a.video else 'pdf' if a.pdf else 'full';print('='*72);print('CUSTOMER PACKAGE BUILDER v2.3');print('Mode:',mode,' Rebuild:',a.rebuild);print('='*72)
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
