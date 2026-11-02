"""Heuristic Rx word-box proposals; user drawing/editing remains the primary path."""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageOps


def propose_boxes(image: Image.Image, max_boxes: int = 30) -> list[dict[str,int]]:
    try: import cv2
    except ImportError: return []
    image=ImageOps.exif_transpose(image).convert("RGB"); width,height=image.size; gray=cv2.cvtColor(np.asarray(image),cv2.COLOR_RGB2GRAY)
    gray=cv2.GaussianBlur(gray,(3,3),0); binary=cv2.adaptiveThreshold(gray,255,cv2.ADAPTIVE_THRESH_GAUSSIAN_C,cv2.THRESH_BINARY_INV,31,13)
    kernel=cv2.getStructuringElement(cv2.MORPH_RECT,(19,3)); merged=cv2.dilate(binary,kernel,iterations=1); contours,_=cv2.findContours(merged,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    boxes=[]
    for contour in contours:
        x,y,w,h=cv2.boundingRect(contour); area=w*h; ratio=w/max(1,h)
        if area<120 or ratio<0.7 or (w>width*0.94 and h<height*0.08): continue
        pad=max(2,int(h*0.12)); x0=max(0,x-pad); y0=max(0,y-pad); x1=min(width,x+w+pad); y1=min(height,y+h+pad)
        boxes.append({"x":x0,"y":y0,"w":x1-x0,"h":y1-y0})
    boxes.sort(key=lambda box:(box["y"],box["x"]))
    return boxes[:max_boxes]
