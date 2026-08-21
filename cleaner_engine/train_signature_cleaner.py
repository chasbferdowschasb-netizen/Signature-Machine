#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Train the signature cleaner from the approved V4 masks.

The existing V4 masks are used as pseudo-ground-truth. This makes the engine learn
from the actual project images instead of relying only on generic thresholds.
"""
from pathlib import Path
import argparse, joblib
import cv2, numpy as np
from sklearn.ensemble import ExtraTreesClassifier

EXTS={'.png','.jpg','.jpeg','.bmp','.tif','.tiff','.webp'}

def features(img, max_side=1200):
    h0,w0=img.shape[:2]
    scale=min(1.0,max_side/max(h0,w0))
    if scale<1:
        img=cv2.resize(img,(round(w0*scale),round(h0*scale)),cv2.INTER_AREA)
    h,w=img.shape[:2]
    lab=cv2.cvtColor(img,cv2.COLOR_BGR2LAB).astype(np.float32)/255.0
    hsv=cv2.cvtColor(img,cv2.COLOR_BGR2HSV).astype(np.float32)/255.0
    gray=cv2.cvtColor(img,cv2.COLOR_BGR2GRAY).astype(np.float32)/255.0
    blur=cv2.GaussianBlur(gray,(0,0),3)
    blur9=cv2.GaussianBlur(gray,(0,0),9)
    local=np.abs(gray-blur)
    local9=np.abs(gray-blur9)
    gx=cv2.Sobel(gray,cv2.CV_32F,1,0,ksize=3)
    gy=cv2.Sobel(gray,cv2.CV_32F,0,1,ksize=3)
    grad=cv2.magnitude(gx,gy)
    yy,xx=np.mgrid[0:h,0:w].astype(np.float32)
    xx/=max(1,w-1); yy/=max(1,h-1)
    X=np.stack([lab[:,:,0],lab[:,:,1],lab[:,:,2],
                hsv[:,:,0],hsv[:,:,1],hsv[:,:,2],
                gray,blur,local,local9,grad,xx,yy],axis=-1)
    return X, scale

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--original',required=True)
    ap.add_argument('--masks',required=True)
    ap.add_argument('--model',required=True)
    ap.add_argument('--per-class',type=int,default=60000)
    args=ap.parse_args()
    op=Path(args.original); mp=Path(args.masks)
    Xs=[]; ys=[]
    rng=np.random.default_rng(42)
    mask_files=sorted(mp.glob('*_mask.png'))
    for mf in mask_files:
        name=mf.name.replace('_mask.png','')
        candidates=[op/(name+'.png'),op/(name+'.jpg'),op/(name+'.jpeg')]
        src=next((p for p in candidates if p.exists()),None)
        if src is None: continue
        img=cv2.imread(str(src),cv2.IMREAD_COLOR)
        m=cv2.imread(str(mf),cv2.IMREAD_GRAYSCALE)
        if img is None or m is None: continue
        X,scale=features(img)
        if scale!=1:
            # reference mask and feature canvas should match after downscale
            m=cv2.resize(m,(X.shape[1],X.shape[0]),cv2.INTER_NEAREST)
        y=(m>127).ravel().astype(np.uint8)
        x=X.reshape(-1,X.shape[-1])
        pos=np.flatnonzero(y==1); neg=np.flatnonzero(y==0)
        n=min(args.per_class,len(pos),len(neg))
        if n<100: continue
        pi=rng.choice(pos,n,replace=False); ni=rng.choice(neg,n,replace=False)
        idx=np.concatenate([pi,ni]); rng.shuffle(idx)
        Xs.append(x[idx]); ys.append(y[idx])
        print(f'{src.name}: pos={len(pos)} neg={len(neg)} used={2*n}')
    if not Xs: raise SystemExit('No training pairs found')
    X=np.concatenate(Xs); y=np.concatenate(ys)
    clf=ExtraTreesClassifier(n_estimators=140,max_depth=18,min_samples_leaf=2,
                             class_weight='balanced',n_jobs=-1,random_state=42)
    clf.fit(X,y)
    Path(args.model).parent.mkdir(parents=True,exist_ok=True)
    joblib.dump({'model':clf,'feature_names':['LabL','LabA','LabB','H','S','V','gray','blur3','local3','local9','grad','x','y']},args.model,compress=3)
    print('saved',args.model,'samples',len(y))

if __name__=='__main__': main()
