#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run the learned signature cleaner on one image or a directory."""
from pathlib import Path
import argparse, joblib, cv2, numpy as np
from train_signature_cleaner import features

EXTS={'.png','.jpg','.jpeg','.bmp','.tif','.tiff','.webp'}

def predict_mask(img, bundle, threshold=0.50):
    X,scale=features(img,max_side=1200)
    h,w=X.shape[:2]
    flat=X.reshape(-1,X.shape[-1])
    clf=bundle['model']
    probs=[]
    for i in range(0,len(flat),150000):
        probs.append(clf.predict_proba(flat[i:i+150000])[:,1])
    p=np.concatenate(probs).reshape(h,w)
    mask=(p>=threshold).astype(np.uint8)*255
    # Remove tiny speckles, close tiny gaps.
    mask=cv2.morphologyEx(mask,cv2.MORPH_OPEN,np.ones((2,2),np.uint8))
    mask=cv2.morphologyEx(mask,cv2.MORPH_CLOSE,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(3,3)))
    if scale!=1:
        mask=cv2.resize(mask,(img.shape[1],img.shape[0]),cv2.INTER_NEAREST)
    return mask,p

def remove_template_geometry(mask):
    h,w=mask.shape
    out=mask.copy()
    # long straight rules
    hk=max(35,w//20); vk=max(35,h//20)
    hor=cv2.morphologyEx(out,cv2.MORPH_OPEN,cv2.getStructuringElement(cv2.MORPH_RECT,(hk,1)))
    ver=cv2.morphologyEx(out,cv2.MORPH_OPEN,cv2.getStructuringElement(cv2.MORPH_RECT,(1,vk)))
    rules=cv2.dilate((hor|ver),np.ones((3,3),np.uint8),1)
    out[rules>0]=0
    # page-edge bands used by the known templates
    out[:int(h*.045),:]=0
    out[int(h*.92):,:]=0
    # Remove compact dense corner logos, but preserve sparse signature strokes.
    n,lab,stats,_=cv2.connectedComponentsWithStats(out,8)
    clean=np.zeros_like(out)
    for i in range(1,n):
        x,y,ww,hh,area=stats[i]
        if area<max(8,h*w*2e-6): continue
        fill=area/max(1,ww*hh)
        corner=(x<w*.20 or x+ww>w*.80) and (y<h*.20 or y+hh>h*.80)
        if corner and fill>.38 and area>h*w*.00025: continue
        if area>h*w*.10 and fill>.30: continue
        clean[lab==i]=255
    return clean

def clean_image(img,mask):
    out=np.full(img.shape,255,np.uint8)
    out[mask>0]=(0,0,0)
    return out

def clean_color(img,mask):
    out=np.full(img.shape,255,np.uint8)
    out[mask>0]=img[mask>0]
    return out

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('input')
    ap.add_argument('--model',required=True)
    ap.add_argument('--output',default='cleaned')
    ap.add_argument('--threshold',type=float,default=.50)
    args=ap.parse_args()
    inp=Path(args.input); out=Path(args.output); out.mkdir(parents=True,exist_ok=True)
    bundle=joblib.load(args.model)
    files=[inp] if inp.is_file() else sorted(p for p in inp.rglob('*') if p.suffix.lower() in EXTS)
    for src in files:
        img=cv2.imread(str(src),cv2.IMREAD_COLOR)
        if img is None: print('ERR',src); continue
        mask,_=predict_mask(img,bundle,args.threshold)
        mask=remove_template_geometry(mask)
        bw=clean_image(img,mask); color=clean_color(img,mask)
        cv2.imwrite(str(out/f'{src.stem}_mask.png'),mask)
        cv2.imwrite(str(out/f'{src.stem}_clean.png'),bw)
        cv2.imwrite(str(out/f'{src.stem}_clean_color.png'),color)
        print('OK',src)

if __name__=='__main__': main()
