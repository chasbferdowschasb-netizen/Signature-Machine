# -*- coding: utf-8 -*-
from __future__ import annotations

import base64, json, re, time, math
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import cv2
import numpy as np
from PIL import Image
try:
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
except ModuleNotFoundError:
    canvas = None

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "online_training_final.html"
DATA_DIR = ROOT / "online_training_data"
REFERENCE_DIR = DATA_DIR / "reference_learning"
SAMPLES_DIR = REFERENCE_DIR / "samples"
SAMPLES_DIR.mkdir(parents=True, exist_ok=True)

HOST, PORT = "127.0.0.1", 8765

PKG = "CUSTOMER_PACKAGE"
FINAL = Path(PKG) / "01_FINAL_ASSETS"
TRAIN = Path(PKG) / "02_TRAINING"
ASSET_NAMES = [
    "01_FINAL_BLACK_ON_WHITE.png",
    "02_BLACK_TRANSPARENT.png",
    "03_WHITE_ON_BLACK.png",
    "04_WHITE_TRANSPARENT.png",
]
FPS = 60
VW, VH = 1336, 512
MX, MY = .16, .20
MINSEC, MAXSEC = 5.0, 20.0
PATH_SPEED = 115.0
PRACTICE_COPIES = 20

def next_sample_id():
    nums=[]
    for p in SAMPLES_DIR.iterdir():
        if p.is_dir():
            m=re.fullmatch(r"sample_(\d{6})",p.name)
            if m: nums.append(int(m.group(1)))
    for legacy in ("APPROVED","MASTER"):
        d=REFERENCE_DIR/legacy
        if d.exists():
            for p in d.iterdir():
                if p.is_dir():
                    m=re.fullmatch(r"sample_(\d{6})",p.name)
                    if m: nums.append(int(m.group(1)))
    return f"sample_{max(nums,default=0)+1:06d}"

def _loadj(p): return json.loads(p.read_text(encoding="utf-8"))

def _pv(v):
    try: return max(0.0,min(1.0,float(v)))
    except: return .35

def _smooth(ps,n=12):
    if len(ps)<3:
        return [(float(p["x"]),float(p["y"]),_pv(p.get("pressure"))) for p in ps]
    P=[(float(p["x"]),float(p["y"]),_pv(p.get("pressure"))) for p in ps]
    out=[P[0]]
    for i in range(len(P)-1):
        p0,p1,p2,p3=P[max(0,i-1)],P[i],P[i+1],P[min(len(P)-1,i+2)]
        for k in range(1,n+1):
            t=k/n; t2=t*t; t3=t2*t
            def cr(a,b,c,d):
                return .5*(2*b+(-a+c)*t+(2*a-5*b+4*c-d)*t2+(-a+3*b-3*c+d)*t3)
            out.append((cr(p0[0],p1[0],p2[0],p3[0]),
                        cr(p0[1],p1[1],p2[1],p3[1]),
                        max(0,min(1,cr(p0[2],p1[2],p2[2],p3[2])))))
    return out

def _slen(ps):
    if len(ps)<2:return 1.
    return max(sum(math.hypot(float(b["x"])-float(a["x"]),float(b["y"])-float(a["y"]))
                   for a,b in zip(ps,ps[1:])),1.)

def _fountain_width(p):
    return .85 + (_pv(p)**.82)*3.35

def _build_assets(sd):
    d=sd/FINAL; d.mkdir(parents=True,exist_ok=True)
    raw=sd/"raw.png"; sp=sd/"strokes.json"
    data=_loadj(sp); strokes=[s for s in data.get("strokes",[]) if s.get("points")]
    if not raw.exists() or not strokes: raise FileNotFoundError("raw.png/strokes.json missing")
    raw_w,raw_h=Image.open(raw).size
    pts=[(float(q["x"]),float(q["y"])) for s in strokes for q in s["points"]]
    xs=[p[0] for p in pts]; ys=[p[1] for p in pts]
    pad=max(8.,min(raw_w,raw_h)*.035)
    x0=max(0,min(xs)-pad); y0=max(0,min(ys)-pad)
    x1=min(raw_w,max(xs)+pad); y1=min(raw_h,max(ys)+pad)
    sw=max(1,x1-x0); sh=max(1,y1-y0)
    TARGET=2400; scale=TARGET/max(sw,sh)
    ow,oh=max(1,round(sw*scale)),max(1,round(sh*scale))
    SS=4
    mask=np.zeros((oh*SS,ow*SS),np.uint8)
    for s in strokes:
        sm=_smooth(s["points"],12)
        mapped=[((x-x0)*scale*SS,(y-y0)*scale*SS,p) for x,y,p in sm]
        for a,b in zip(mapped,mapped[1:]):
            xa,ya,pa=a; xb,yb,pb=b
            w=max(1,round(_fountain_width((pa+pb)/2)*scale*SS))
            cv2.line(mask,(round(xa),round(ya)),(round(xb),round(yb)),255,w,cv2.LINE_AA)
    mask=cv2.resize(mask,(ow,oh),interpolation=cv2.INTER_AREA)
    mask=cv2.GaussianBlur(mask,(3,3),0)
    m=Image.fromarray(mask,"L")
    specs=[
      (ASSET_NAMES[0],"RGB",(255,255,255),(0,0,0)),
      (ASSET_NAMES[1],"RGBA",(0,0,0,0),(0,0,0,255)),
      (ASSET_NAMES[2],"RGB",(0,0,0),(255,255,255)),
      (ASSET_NAMES[3],"RGBA",(0,0,0,0),(255,255,255,255))]
    for name,mode,bg,fg in specs:
        im=Image.new(mode,m.size,bg); im.paste(fg,mask=m)
        im.save(d/name,compress_level=1)
    return {"size":[ow,oh],"target_long_side":2400,"render_profile":"fountain_pen_v1","supersampling":4}

def _build_video(sd):
    data=_loadj(sd/"strokes.json")
    strokes=[s for s in data.get("strokes",[]) if s.get("points")]
    pts=[(float(p["x"]),float(p["y"])) for s in strokes for p in s["points"]]
    xs=[p[0] for p in pts]; ys=[p[1] for p in pts]
    padx=max(8,(max(xs)-min(xs))*.055); pady=max(8,(max(ys)-min(ys))*.08)
    bx0,by0,bx1,by1=min(xs)-padx,min(ys)-pady,max(xs)+padx,max(ys)+pady
    sw=max(1,bx1-bx0); sh=max(1,by1-by0)
    scale=min(VW*(1-2*MX)/sw,VH*(1-2*MY)/sh)
    ox=(VW-sw*scale)/2; oy=(VH-sh*scale)/2
    lens=[_slen(s["points"]) for s in strokes]; total=max(sum(lens),1)
    duration=max(MINSEC,min(MAXSEC,total/PATH_SPEED))
    base=[max(.22,duration*L/total) for L in lens]
    fac=duration/max(sum(base),1e-9); durations=[d*fac for d in base]
    timeline=[]; cur=0
    for s,d in zip(strokes,durations):
        sm=_smooth(s["points"],12); ts=np.linspace(cur,cur+d,len(sm))
        timeline.append([(ox+(x-bx0)*scale,oy+(y-by0)*scale,p,float(t))
                         for (x,y,p),t in zip(sm,ts)])
        cur+=d
    out=sd/TRAIN/"01_TRAINING.mp4"; out.parent.mkdir(parents=True,exist_ok=True)
    writer=cv2.VideoWriter(str(out),cv2.VideoWriter_fourcc(*"mp4v"),FPS,(VW,VH))
    if not writer.isOpened(): raise RuntimeError("Could not create MP4 writer")
    R=2
    for fi in range(max(1,int(math.ceil(cur*FPS)))):
        t=fi/FPS; hi=np.full((VH*R,VW*R,3),255,np.uint8)
        for tl in timeline:
            if not tl or t<tl[0][3]: continue
            vis=[]
            for j,(x,y,p,tt) in enumerate(tl):
                if t>=tt: vis.append((x,y,p))
                elif j:
                    x0,y0,p0,t0=tl[j-1]; q=max(0,min(1,(t-t0)/max(tt-t0,1e-9)))
                    vis.append((x0+(x-x0)*q,y0+(y-y0)*q,p0+(p-p0)*q))
                    break
            for A,B in zip(vis,vis[1:]):
                x0,y0,p0=A; x1,y1,p1=B
                w=max(2,round(_fountain_width((p0+p1)/2)*R))
                cv2.line(hi,(round(x0*R),round(y0*R)),(round(x1*R),round(y1*R)),(0,0,0),w,cv2.LINE_AA)
        writer.write(cv2.resize(hi,(VW,VH),interpolation=cv2.INTER_AREA))
    writer.release()
    return {"frame_size":[VW,VH],"fps":FPS,"duration_seconds":round(cur,2),"centered":True}

def _build_pdf(sd):
    if canvas is None: raise RuntimeError("reportlab is not installed")
    asset=sd/FINAL/ASSET_NAMES[0]
    if not asset.exists(): _build_assets(sd)
    rgb=np.asarray(Image.open(asset).convert("RGB"),dtype=np.uint8)
    gray=.299*rgb[...,0]+.587*rgb[...,1]+.114*rgb[...,2]
    ink=np.clip(255-gray,0,255).astype(np.uint8)
    alpha=np.clip(ink.astype(np.float32)*.58,0,255).astype(np.uint8)
    ys,xs=np.where(alpha>8)
    if len(xs)==0: raise ValueError("No visible signature")
    x0,y0,x1,y1=xs.min(),ys.min(),xs.max()+1,ys.max()+1
    crop=alpha[y0:y1,x0:x1]
    rgba=np.zeros((*crop.shape,4),np.uint8); rgba[...,3]=crop
    tmp=sd/".practice.png"; Image.fromarray(rgba,"RGBA").save(tmp)
    out=sd/TRAIN/"01_PRACTICE.pdf"; out.parent.mkdir(parents=True,exist_ok=True)
    c=canvas.Canvas(str(out),pagesize=A4); W,H=A4
    cols,rows=4,5; mx=9*mm; top=18*mm; bottom=7*mm
    cw=(W-2*mx)/cols; ch=(H-top-bottom)/rows; iw,ih=crop.shape[1],crop.shape[0]
    for i in range(20):
        r,col=divmod(i,cols)
        fit=min(cw*.90/iw,ch*.72/ih); dw,dh=iw*fit,ih*fit
        x=mx+col*cw+(cw-dw)/2
        y=H-top-(r+1)*ch+(ch-dh)/2
        c.drawImage(str(tmp),x,y,width=dw,height=dh,mask="auto",preserveAspectRatio=True)
    c.save(); tmp.unlink(missing_ok=True)
    return {"format":"A4","copies":20,"layout":"4x5","print_alpha":.58}

def build_customer_package(sd):
    result={"assets":_build_assets(sd),"video":_build_video(sd),"pdf":_build_pdf(sd)}
    manifest={
      "package_version":"025_plus_v2",
      "sample_id":sd.name,
      "standards":result,
      "files":{
        "assets":ASSET_NAMES,
        "training":["01_TRAINING.mp4","01_PRACTICE.pdf"]
      }
    }
    (sd/PKG/"package_manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    return result

class Handler(BaseHTTPRequestHandler):
    server_version="SignatureMachineOnlineTraining/0.5"
    def _send(self,status,ct,body):
        self.send_response(status); self.send_header("Content-Type",ct)
        self.send_header("Content-Length",str(len(body))); self.send_header("Cache-Control","no-store")
        self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        if urlparse(self.path).path in ("/","/online_training_final.html"):
            self._send(200,"text/html; charset=utf-8",WEB.read_bytes())
        else:self._send(404,"text/plain; charset=utf-8",b"Not found")
    def do_POST(self):
        if urlparse(self.path).path!="/api/save":
            self._send(404,"text/plain; charset=utf-8",b"Not found"); return
        try:
            n=int(self.headers.get("Content-Length","0"))
            payload=json.loads(self.rfile.read(n).decode("utf-8"))
            strokes=payload.get("strokes",[]); png=payload.get("png_data","")
            if not strokes: raise ValueError("No strokes were supplied.")
            if not png.startswith("data:image/png;base64,"): raise ValueError("PNG payload missing.")
            sid=next_sample_id(); sd=SAMPLES_DIR/sid; sd.mkdir(parents=True,exist_ok=False)
            (sd/"raw.png").write_bytes(base64.b64decode(png.split(",",1)[1]))
            render=payload.get("render_png_data","")
            if render.startswith("data:image/png;base64,"):
                (sd/"render.png").write_bytes(base64.b64decode(render.split(",",1)[1]))
            created=time.time(); stats=payload.get("stats",{})
            record={"schema_version":"online_pen_sample_v0.5","sample_id":sid,
                    "created_at_unix":created,"training_status":"REFERENCE",
                    "label":str(payload.get("label","unlabeled")).strip() or "unlabeled",
                    "source":{"device_input":"Pointer Events","expected_pointer_type":"pen",
                              "raw_points_preserved":True,"touch_points_preserved":True},
                    "strokes":strokes,"stats":stats}
            (sd/"strokes.json").write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding="utf-8")
            meta={"schema_version":"reference_metadata_v0.5","sample_id":sid,
                  "training_status":"REFERENCE","created_at_unix":created,
                  "point_count":stats.get("point_count",0),"stroke_count":stats.get("stroke_count",0),
                  "duration_ms":stats.get("duration_ms",0),"pressure_available":stats.get("pressure_available",False),
                  "pointer_types":stats.get("pointer_types",[]),"render_profile":"fountain_pen_v1",
                  "stroke_profile":{"baseline":.85,"pressure_gain":3.35,"pressure_curve":.82}}
            (sd/"metadata.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding="utf-8")
            package=build_customer_package(sd)
            self._send(200,"application/json; charset=utf-8",
                       json.dumps({"ok":True,"sample_id":sid,"training_status":"REFERENCE",
                                   "path":str(sd.relative_to(ROOT)),"customer_package":package},
                                  ensure_ascii=False).encode("utf-8"))
        except Exception as e:
            self._send(400,"application/json; charset=utf-8",
                       json.dumps({"ok":False,"error":str(e)},ensure_ascii=False).encode("utf-8"))
    def log_message(self,fmt,*args): print("[HTTP]",fmt%args)

def main():
    print("="*72); print("SIGNATURE MACHINE - ONLINE PEN TRAINING v0.5")
    print("="*72)
    print(f"REFERENCE SAMPLES: {SAMPLES_DIR}")
    print("Sample 025+: Save Reference => PNG x4 + MP4 + A4 PDF + manifest")
    print(f"Open: http://{HOST}:{PORT}/")
    print("Stop with Ctrl+C"); print("="*72)
    server=ThreadingHTTPServer((HOST,PORT),Handler)
    try: server.serve_forever()
    except KeyboardInterrupt: print("\nStopping...")
    finally: server.server_close()

if __name__=="__main__": main()
