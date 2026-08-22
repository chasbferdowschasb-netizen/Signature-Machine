# -*- coding: utf-8 -*-
from __future__ import annotations

import json, math, shutil, zipfile
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import cv2

ROOT = Path(__file__).resolve().parent
SAMPLES_DIR = ROOT / 'online_training_data' / 'reference_learning' / 'samples'

# Output standard agreed for every sample.
PACKAGE_REL = Path('CUSTOMER_PACKAGE')
FINAL_REL = PACKAGE_REL / '01_FINAL_ASSETS'
TRAIN_REL = PACKAGE_REL / '02_TRAINING'
VIDEO_FPS = 60
VIDEO_MIN_SEC = 5.0
VIDEO_MAX_SEC = 20.0
VIDEO_PATH_SPEED = 110.0
PRACTICE_COPIES = 20
PRACTICE_ALPHA = 0.34  # darker than the previous version for real printing
RENDER_SCALE = 4


def load_json(p: Path):
    return json.loads(p.read_text(encoding='utf-8'))


def ink_alpha_from_image(im: Image.Image) -> np.ndarray:
    rgba = np.asarray(im.convert('RGBA'), dtype=np.uint8)
    rgb = rgba[..., :3].astype(np.float32)
    a = rgba[..., 3].astype(np.float32)
    gray = 0.299*rgb[...,0] + 0.587*rgb[...,1] + 0.114*rgb[...,2]
    # Prefer real alpha when it contains meaningful visible ink, otherwise RGB.
    if np.mean(a >= 16) >= 0.05:
        alpha = np.minimum(a, 255.0)
        # For black ink, alpha is already the coverage; RGB darkness also helps antialiasing.
        darkness = np.clip(255.0 - gray, 0, 255)
        alpha = np.maximum(alpha, darkness)
    else:
        alpha = np.clip(255.0 - gray, 0, 255)
    alpha[gray > 250] = 0
    return np.clip(alpha, 0, 255).astype(np.uint8)


def bbox_from_alpha(alpha: np.ndarray, pad: int = 20):
    y, x = np.where(alpha > 8)
    if len(x) == 0:
        return (0, 0, alpha.shape[1], alpha.shape[0])
    return (
        max(0, int(x.min()) - pad),
        max(0, int(y.min()) - pad),
        min(alpha.shape[1], int(x.max()) + 1 + pad),
        min(alpha.shape[0], int(y.max()) + 1 + pad),
    )


def write_final_assets(sample_dir: Path, final_dir: Path):
    render = sample_dir / 'render.png'
    raw = sample_dir / 'raw.png'
    source = render if render.exists() else raw
    if not source.exists():
        raise FileNotFoundError(f'No render.png/raw.png in {sample_dir}')

    im = Image.open(source).convert('RGBA')
    alpha = ink_alpha_from_image(im)
    bbox = bbox_from_alpha(alpha, pad=max(12, int(min(alpha.shape)*0.012)))
    crop_alpha = alpha[bbox[1]:bbox[3], bbox[0]:bbox[2]]

    # High-resolution canvas around the actual signature. Preserve aspect ratio.
    # Use a 1600px long side baseline for customer assets.
    h, w = crop_alpha.shape
    target_long = 1800
    scale = target_long / max(w, h, 1)
    ow, oh = max(1, int(round(w*scale))), max(1, int(round(h*scale)))
    a = Image.fromarray(crop_alpha, 'L').resize((ow, oh), Image.Resampling.LANCZOS)

    black_trans = Image.new('RGBA', (ow, oh), (0,0,0,0))
    black_trans.paste((0,0,0,255), mask=a)
    black_trans.save(final_dir / '02_BLACK_TRANSPARENT.png')

    white_trans = Image.new('RGBA', (ow, oh), (0,0,0,0))
    white_trans.paste((255,255,255,255), mask=a)
    white_trans.save(final_dir / '04_WHITE_TRANSPARENT.png')

    black_white = Image.new('RGBA', (ow, oh), (255,255,255,255))
    black_white.paste((0,0,0,255), mask=a)
    black_white.convert('RGB').save(final_dir / '01_FINAL_BLACK_ON_WHITE.png', quality=100)

    white_black = Image.new('RGBA', (ow, oh), (0,0,0,255))
    white_black.paste((255,255,255,255), mask=a)
    white_black.convert('RGB').save(final_dir / '03_WHITE_ON_BLACK.png', quality=100)

    return {
        'source': source.name,
        'crop': {'x': bbox[0], 'y': bbox[1], 'width': bbox[2]-bbox[0], 'height': bbox[3]-bbox[1]},
        'output_size': {'width': ow, 'height': oh},
    }


def stroke_length(points):
    if len(points) < 2:
        return 1.0
    return sum(math.hypot(points[i]['x']-points[i-1]['x'], points[i]['y']-points[i-1]['y']) for i in range(1, len(points)))


def catmull_rom(points, samples_per_segment=8):
    if len(points) <= 2:
        return [(float(p['x']), float(p['y']), float(p.get('pressure', 0.5) if p.get('pressure') is not None else 0.5)) for p in points]
    P = [(float(p['x']), float(p['y']), float(p.get('pressure', 0.5) if p.get('pressure') is not None else 0.5)) for p in points]
    out = [P[0]]
    for i in range(len(P)-1):
        p0 = P[max(0,i-1)]; p1 = P[i]; p2 = P[i+1]; p3 = P[min(len(P)-1,i+2)]
        for k in range(1, samples_per_segment+1):
            t = k / samples_per_segment
            t2, t3 = t*t, t*t*t
            x = 0.5*((2*p1[0]) + (-p0[0]+p2[0])*t + (2*p0[0]-5*p1[0]+4*p2[0]-p3[0])*t2 + (-p0[0]+3*p1[0]-3*p2[0]+p3[0])*t3)
            y = 0.5*((2*p1[1]) + (-p0[1]+p2[1])*t + (2*p0[1]-5*p1[1]+4*p2[1]-p3[1])*t2 + (-p0[1]+3*p1[1]-3*p2[1]+p3[1])*t3)
            pr = max(0.0,min(1.0,0.5*((2*p1[2]) + (-p0[2]+p2[2])*t + (2*p0[2]-5*p1[2]+4*p2[2]-p3[2])*t2 + (-p0[2]+3*p1[2]-3*p2[2]+p3[2])*t3)))
            out.append((x,y,pr))
    return out


def make_training_video(sample_dir: Path, video_path: Path):
    data = load_json(sample_dir / 'strokes.json')
    strokes = [s for s in data.get('strokes', []) if s.get('points')]
    if not strokes:
        raise ValueError('No strokes in strokes.json')

    # Use path length rather than wall-clock time. This deliberately removes idle pauses.
    lengths = [stroke_length(s['points']) for s in strokes]
    total_len = max(sum(lengths), 1.0)
    duration = max(VIDEO_MIN_SEC, min(VIDEO_MAX_SEC, total_len / VIDEO_PATH_SPEED))
    min_dur = 0.22
    base = [max(min_dur, duration * L / total_len) for L in lengths]
    factor = duration / sum(base)
    durations = [d*factor for d in base]

    timeline = []
    cursor = 0.0
    for s, dur in zip(strokes, durations):
        smooth = catmull_rom(s['points'], samples_per_segment=8)
        n = len(smooth)
        times = np.linspace(cursor, cursor+dur, max(n,2))
        timeline.append([(smooth[i][0], smooth[i][1], smooth[i][2], float(times[i])) for i in range(n)])
        cursor += dur

    # Canvas dimensions from render.png or raw.png.
    src = Image.open(sample_dir / ('render.png' if (sample_dir/'render.png').exists() else 'raw.png'))
    W,H = src.size
    # The strokes are stored in browser CSS coordinates, not render coordinates.
    # Fit the video to the original raw coordinate space for training fidelity.
    raw = Image.open(sample_dir/'raw.png') if (sample_dir/'raw.png').exists() else src
    W,H = raw.size

    writer = cv2.VideoWriter(str(video_path), cv2.VideoWriter_fourcc(*'mp4v'), VIDEO_FPS, (W,H))
    if not writer.isOpened():
        raise RuntimeError('Could not create MP4')

    frames = max(1, int(math.ceil(cursor*VIDEO_FPS)))
    for fi in range(frames):
        t = fi/VIDEO_FPS
        frame = np.full((H,W,3),255,dtype=np.uint8)
        for pts in timeline:
            if not pts or t < pts[0][3]:
                continue
            visible=[]
            for j in range(len(pts)):
                x,y,p,tt=pts[j]
                if t >= tt:
                    visible.append((x,y,p))
                else:
                    if j>0:
                        x0,y0,p0,t0=pts[j-1]
                        frac=max(0.0,min(1.0,(t-t0)/max(tt-t0,1e-9)))
                        visible.append((x0+(x-x0)*frac,y0+(y-y0)*frac,p0+(p-p0)*frac))
                    break
            if len(visible)>=2:
                for j in range(1,len(visible)):
                    x0,y0,p0=visible[j-1]; x1,y1,p1=visible[j]
                    width=max(1,int(round(1.2+((p0+p1)/2)*5)))
                    cv2.line(frame,(round(x0),round(y0)),(round(x1),round(y1)),(0,0,0),width,cv2.LINE_AA)
            elif len(visible)==1:
                x,y,p=visible[0]
                cv2.circle(frame,(round(x),round(y)),max(1,int(round((1.2+p*5)/2))),(0,0,0),-1,cv2.LINE_AA)
        writer.write(frame)
    writer.release()
    return round(cursor,2)


def make_practice_pdf(sample_dir: Path, pdf_path: Path):
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm

    source = sample_dir / 'render.png'
    if not source.exists(): source = sample_dir / 'raw.png'
    im = Image.open(source).convert('RGBA')
    alpha = ink_alpha_from_image(im)
    bbox = bbox_from_alpha(alpha, pad=12)
    crop = alpha[bbox[1]:bbox[3], bbox[0]:bbox[2]]

    # Convert to an image suitable for reportlab; darker than prior version.
    rgba = np.zeros((crop.shape[0], crop.shape[1], 4), dtype=np.uint8)
    rgba[...,0:3] = 90
    rgba[...,3] = (crop.astype(np.float32) * PRACTICE_ALPHA).astype(np.uint8)
    temp = sample_dir / '.practice_faint.png'
    Image.fromarray(rgba,'RGBA').save(temp)

    c = canvas.Canvas(str(pdf_path), pagesize=A4)
    W,H = A4
    c.setFillColorRGB(0.35,0.35,0.35)
    c.setFont('Helvetica', 11)
    c.drawString(18*mm, H-15*mm, 'Signature Practice')

    cols, rows = 4,5
    margin_x = 10*mm
    top = 22*mm
    bottom = 8*mm
    cell_w = (W-2*margin_x)/cols
    cell_h = (H-top-bottom)/rows
    # Keep a visible signature in each cell without making it too large.
    iw,ih = crop.shape[1],crop.shape[0]
    for i in range(PRACTICE_COPIES):
        r,cidx=divmod(i,cols)
        maxw,maxh=cell_w*0.90,cell_h*0.70
        scale=min(maxw/iw,maxh/ih)
        dw,dh=iw*scale,ih*scale
        x=margin_x+cidx*cell_w+(cell_w-dw)/2
        y=H-top-(r+1)*cell_h+(cell_h-dh)/2
        c.drawImage(str(temp),x,y,width=dw,height=dh,mask='auto',preserveAspectRatio=True)
        c.setFillColorRGB(0.55,0.55,0.55)
        c.setFont('Helvetica',6.5)
        c.drawString(x+2,y+2,str(i+1))
    c.save()
    temp.unlink(missing_ok=True)


def build_sample(sample_dir: Path, overwrite=False):
    if not (sample_dir/'strokes.json').exists():
        return False, 'missing strokes.json'
    if not (sample_dir/'raw.png').exists() and not (sample_dir/'render.png').exists():
        return False, 'missing raw/render png'
    package = sample_dir/PACKAGE_REL
    final_dir = sample_dir/FINAL_REL
    train_dir = sample_dir/TRAIN_REL
    final_dir.mkdir(parents=True,exist_ok=True)
    train_dir.mkdir(parents=True,exist_ok=True)

    if overwrite or not (final_dir/'01_FINAL_BLACK_ON_WHITE.png').exists():
        final_info=write_final_assets(sample_dir,final_dir)
    else:
        final_info={'existing':True}

    video_path=train_dir/'01_TRAINING.mp4'
    pdf_path=train_dir/'01_PRACTICE.pdf'
    # Only one training video and one practice PDF. Remove obsolete training files.
    for p in train_dir.iterdir():
        if p.is_file() and p.name not in {'01_TRAINING.mp4','01_PRACTICE.pdf'}:
            p.unlink()
    if overwrite or not video_path.exists():
        duration=make_training_video(sample_dir,video_path)
    else:
        duration=None
    if overwrite or not pdf_path.exists():
        make_practice_pdf(sample_dir,pdf_path)

    meta={}
    mp=sample_dir/'metadata.json'
    if mp.exists():
        try: meta=load_json(mp)
        except: pass
    manifest={
        'schema_version':'customer_package_v1',
        'sample_id': sample_dir.name,
        'label': meta.get('label','unlabeled'),
        'customer_package':{
            'final_assets':[
                'CUSTOMER_PACKAGE/01_FINAL_ASSETS/01_FINAL_BLACK_ON_WHITE.png',
                'CUSTOMER_PACKAGE/01_FINAL_ASSETS/02_BLACK_TRANSPARENT.png',
                'CUSTOMER_PACKAGE/01_FINAL_ASSETS/03_WHITE_ON_BLACK.png',
                'CUSTOMER_PACKAGE/01_FINAL_ASSETS/04_WHITE_TRANSPARENT.png',
            ],
            'training':[
                'CUSTOMER_PACKAGE/02_TRAINING/01_PRACTICE.pdf',
                'CUSTOMER_PACKAGE/02_TRAINING/01_TRAINING.mp4',
            ],
        },
        'practice_sheet':{'format':'A4','copies':20,'layout':'4x5','print_faintness':PRACTICE_ALPHA},
        'training_video':{'fps':VIDEO_FPS,'continuous_timing':True,'idle_gaps_removed':True,'single_video':True,'duration_seconds':duration},
        'notes':'Customer-facing package is generated automatically from the reference sample; raw/strokes/metadata remain outside CUSTOMER_PACKAGE as engine data.'
    }
    (package/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    return True, 'built'


def main():
    import argparse
    ap=argparse.ArgumentParser()
    ap.add_argument('--root',default=str(SAMPLES_DIR))
    ap.add_argument('--sample',action='append',help='sample_000023; may be repeated')
    ap.add_argument('--overwrite',action='store_true')
    args=ap.parse_args()
    root=Path(args.root)
    samples=[root/s for s in args.sample] if args.sample else sorted([p for p in root.iterdir() if p.is_dir() and p.name.startswith('sample_')])
    print('CUSTOMER PACKAGE BUILDER')
    print('Samples:',len(samples))
    for s in samples:
        try:
            ok,msg=build_sample(s,args.overwrite)
            print(f'{s.name}: {msg}')
        except Exception as e:
            print(f'{s.name}: ERROR: {e}')
    print('Done.')

if __name__=='__main__': main()