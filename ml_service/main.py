import base64, os
from contextlib import asynccontextmanager
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from .inference import Models,derma_info,predict_derma,predict_rx,rx_info,validate_image

@asynccontextmanager
async def lifespan(_app):
    global models
    models=Models()
    yield

app=FastAPI(title="Niramaya Vision Inference",version="0.1.0",lifespan=lifespan)
origins=[x.strip() for x in os.getenv("FRONTEND_ORIGIN","http://localhost:3000,http://localhost:5173").split(",") if x.strip()]
app.add_middleware(CORSMiddleware,allow_origins=origins,allow_methods=["*"],allow_headers=["*"])
models=None
@app.get("/health")
def health():
    m=models or Models()
    return {"status":"ok","models":{"derma":m.derma,"rx":m.rx}}
@app.get("/derma/info")
def get_derma_info(): return derma_info(models or Models())
@app.post("/derma/predict")
async def derma_predict(image:UploadFile=File(...)):
    content=await image.read(10*1024*1024+1); img=validate_image(content,image.filename); return predict_derma(models or Models(),img)
@app.get("/rx/info")
def get_rx_info(): return rx_info(models or Models())
@app.post("/rx/segment")
async def rx_segment(image:UploadFile=File(...)):
    img=validate_image(await image.read(10*1024*1024+1),image.filename)
    from ml.rx.segment import segment
    return {"status":"ok","boxes":segment(img),"image_width":img.width,"image_height":img.height}
class Box(BaseModel): x:int;y:int;w:int;h:int
@app.post("/rx/predict")
async def rx_predict(image:UploadFile|None=File(None),crops:list[UploadFile]|None=File(None),boxes:str=Form("[]")):
    import json
    if bool(image)==bool(crops): raise HTTPException(400,"Provide exactly one of image with boxes or crops.")
    if crops and len(crops)>20: raise HTTPException(400,"At most 20 crops are supported.")
    if image:
        original=validate_image(await image.read(10*1024*1024+1),image.filename)
        try: requested=json.loads(boxes)
        except ValueError: raise HTTPException(400,"boxes must be a JSON array.")
        if not isinstance(requested,list): raise HTTPException(400,"boxes must be a JSON array.")
    else:
        from PIL import Image
        requested=[]
        for i,item in enumerate(crops):
            data=await item.read(10*1024*1024+1); crop=validate_image(data,item.filename); requested.append({"x":0,"y":0,"w":crop.width,"h":crop.height,"_crop":crop})
        original=None
    if original is not None: return predict_rx(models or Models(),original,requested)
    # Reuse the same recognizer for crop inputs by placing crops on a horizontal sheet with non-overlapping boxes.
    from PIL import Image
    imgs=[b.pop("_crop") for b in requested]; height=max(i.height for i in imgs); width=sum(i.width for i in imgs)
    sheet=Image.new("RGB",(width,height),"white"); boxes=[]; offset=0
    for im in imgs: sheet.paste(im,(offset,0));boxes.append({"x":offset,"y":0,"w":im.width,"h":im.height});offset+=im.width
    return predict_rx(models or Models(),sheet,boxes)
