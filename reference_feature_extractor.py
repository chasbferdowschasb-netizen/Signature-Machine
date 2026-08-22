# -*- coding: utf-8 -*-
from __future__ import annotations
import json, math, statistics, time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
SAMPLES_DIR = ROOT / "online_training_data" / "reference_learning" / "samples"
ANALYSIS_DIR = ROOT / "online_training_data" / "analysis"
OUTPUT_FILE = ANALYSIS_DIR / "reference_features.json"

def finite(v: Any) -> float | None:
    try:
        v=float(v); return v if math.isfinite(v) else None
    except (TypeError, ValueError): return None

def dist(a,b):
    ax,ay,bx,by=[finite(x) for x in (a.get("x"),a.get("y"),b.get("x"),b.get("y"))]
    return math.hypot(bx-ax,by-ay) if None not in (ax,ay,bx,by) else 0.0

def stroke_features(s):
    pts=s.get("points") or []
    pressures=[v for v in (finite(p.get("pressure")) for p in pts) if v is not None]
    times=[v for v in (finite(p.get("time_ms")) for p in pts) if v is not None]
    length=0.0; speeds=[]
    for a,b in zip(pts,pts[1:]):
        d=dist(a,b); length+=d
        ta,tb=finite(a.get("time_ms")),finite(b.get("time_ms"))
        if ta is not None and tb is not None and tb>ta: speeds.append(d/((tb-ta)/1000))
    xs=[v for v in (finite(p.get("x")) for p in pts) if v is not None]
    ys=[v for v in (finite(p.get("y")) for p in pts) if v is not None]
    first,last=(pts[0] if pts else {}),(pts[-1] if pts else {})
    x1,y1,x2,y2=[finite(v) for v in (first.get("x"),first.get("y"),last.get("x"),last.get("y"))]
    dx,dy=((x2-x1,y2-y1) if None not in (x1,y1,x2,y2) else (0,0))
    duration=max(0,times[-1]-times[0]) if len(times)>=2 else 0
    return {"stroke_index":s.get("stroke_index"),"point_count":len(pts),"duration_ms":round(duration,3),"path_length_px":round(length,3),"average_speed_px_s":round(length/(duration/1000),3) if duration>0 else 0,"max_segment_speed_px_s":round(max(speeds),3) if speeds else 0,"start":{"x":x1,"y":y1},"end":{"x":x2,"y":y2},"net_displacement_px":round(math.hypot(dx,dy),3),"direction_deg":round(math.degrees(math.atan2(dy,dx)),3) if dx or dy else None,"bounding_box":{"min_x":min(xs) if xs else None,"max_x":max(xs) if xs else None,"min_y":min(ys) if ys else None,"max_y":max(ys) if ys else None,"width":round(max(xs)-min(xs),3) if xs else 0,"height":round(max(ys)-min(ys),3) if ys else 0},"pressure":{"point_count":len(pressures),"min":min(pressures) if pressures else None,"max":max(pressures) if pressures else None,"mean":round(statistics.fmean(pressures),6) if pressures else None},"pointer_types":sorted({str(p.get("pointer_type","unknown")) for p in pts})}

def sample_features(d):
    mf=d/"metadata.json"; sf=d/"strokes.json"
    metadata=json.loads(mf.read_text(encoding="utf-8")); record=json.loads(sf.read_text(encoding="utf-8")); strokes=record.get("strokes") or []
    pts=[p for s in strokes for p in (s.get("points") or [])]
    xs=[v for v in (finite(p.get("x")) for p in pts) if v is not None]; ys=[v for v in (finite(p.get("y")) for p in pts) if v is not None]
    ps=[v for v in (finite(p.get("pressure")) for p in pts) if v is not None]
    ts=[v for v in (finite(p.get("time_ms")) for p in pts) if v is not None]
    per=[stroke_features(s) for s in strokes]; label=str(record.get("label") or metadata.get("label") or "unlabeled").strip() or "unlabeled"
    length=sum(x["path_length_px"] for x in per); duration=max(0,ts[-1]-ts[0]) if len(ts)>=2 else 0
    speeds=[x["average_speed_px_s"] for x in per if x["average_speed_px_s"]>0]; maxspeeds=[x["max_segment_speed_px_s"] for x in per if x["max_segment_speed_px_s"]>0]
    touch=sum(str(p.get("pointer_type","")).lower()=="touch" for p in pts)
    return {"sample_id":d.name,"label":label,"source_files":{"metadata":str(mf.relative_to(ROOT)),"strokes":str(sf.relative_to(ROOT)),"raw_png":str((d/"raw.png").relative_to(ROOT))},"composition":{"label":label,"character_count":len(label),"has_persian":any('\u0600'<=c<='\u06ff' for c in label),"has_latin":any('a'<=c.lower()<='z' for c in label),"has_space":" " in label},"geometry":{"width_px":round(max(xs)-min(xs),3) if xs else 0,"height_px":round(max(ys)-min(ys),3) if ys else 0,"aspect_ratio":round((max(xs)-min(xs))/(max(ys)-min(ys)),6) if xs and ys and max(ys)>min(ys) else None,"total_path_length_px":round(length,3)},"motion":{"duration_ms":round(duration,3),"average_stroke_speed_px_s":round(statistics.fmean(speeds),3) if speeds else 0,"max_segment_speed_px_s":round(max(maxspeeds),3) if maxspeeds else 0},"pressure":{"point_count":len(ps),"min":min(ps) if ps else None,"max":max(ps) if ps else None,"mean":round(statistics.fmean(ps),6) if ps else None},"input":{"pointer_types":sorted({str(p.get("pointer_type","unknown")) for p in pts}),"touch_point_count":touch,"touch_point_ratio":round(touch/len(pts),6) if pts else 0},"counts":{"strokes":len(strokes),"points":len(pts)},"strokes":per}

def main():
    print("="*80); print("SIGNATURE MACHINE"); print("REFERENCE FEATURE EXTRACTOR v0.1"); print("="*80); print(f"Reference directory: {SAMPLES_DIR}"); print("NOTE: This program is READ-ONLY.\n")
    if not SAMPLES_DIR.exists(): raise SystemExit(f"Reference directory not found: {SAMPLES_DIR}")
    dirs=sorted([p for p in SAMPLES_DIR.iterdir() if p.is_dir() and p.name.startswith("sample_")],key=lambda p:p.name)
    samples=[]
    print("-"*80); print(f"{'SAMPLE':<16}{'LABEL':<24}{'STROKES':>8}{'POINTS':>8}{'WIDTH':>10}{'HEIGHT':>10}"); print("-"*80)
    for d in dirs:
        f=sample_features(d); samples.append(f); print(f"{f['sample_id']:<16}{f['label'][:23]:<24}{f['counts']['strokes']:>8}{f['counts']['points']:>8}{f['geometry']['width_px']:>10.1f}{f['geometry']['height_px']:>10.1f}")
    ANALYSIS_DIR.mkdir(parents=True,exist_ok=True)
    report={"schema_version":"reference_features_v0.1","generated_at_unix":time.time(),"read_only":True,"dataset":{"directory":str(SAMPLES_DIR),"sample_count":len(samples),"sample_ids":[s["sample_id"] for s in samples]},"samples":samples}
    OUTPUT_FILE.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print("\n"+"="*80); print("REFERENCE FEATURE EXTRACTION COMPLETE"); print("="*80); print(f"Samples analyzed : {len(samples)}"); print(f"Output            : {OUTPUT_FILE}"); print("Source samples were NOT modified."); print("No model was trained."); print("No signature was generated."); print("="*80)
if __name__=="__main__": main()