def preprocess(image, height=32, width=128):
    from PIL import Image, ImageOps, ImageEnhance
    image=ImageOps.exif_transpose(image).convert("L"); image=ImageOps.autocontrast(image)
    scale=min(width/image.width,height/image.height); size=(max(1,int(image.width*scale)),max(1,int(image.height*scale)))
    image=image.resize(size,Image.Resampling.LANCZOS); canvas=Image.new("L",(width,height),255); canvas.paste(image,(0,(height-image.height)//2))
    import numpy as np
    return (np.asarray(canvas,dtype="float32")[None,...]/127.5-1.0)
