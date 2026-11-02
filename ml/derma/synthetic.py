def make_synthetic(root, per_class=20, size=224, seed=17):
    from pathlib import Path
    import random
    try:
        from PIL import Image, ImageDraw
    except ImportError as exc: raise RuntimeError("Install Pillow in the ML environment") from exc
    from .config import CLASSES
    rng=random.Random(seed); root=Path(root); root.mkdir(parents=True,exist_ok=True)
    rows=[]
    for idx,code in enumerate(CLASSES):
        folder=root/code; folder.mkdir(exist_ok=True)
        for n in range(per_class):
            image=Image.new("RGB",(size,size),(218+rng.randrange(30),188+rng.randrange(35),159+rng.randrange(35)))
            draw=ImageDraw.Draw(image); x=rng.randrange(size//4,3*size//4); y=rng.randrange(size//4,3*size//4); rad=rng.randrange(15,60)
            draw.ellipse((x-rad,y-rad,x+rad,y+rad),fill=(55+idx*22,35+idx*12,25+idx*10),outline=(30,20,18),width=3)
            path=folder/f"{code}_{n:03d}.png"; image.save(path); rows.append({"image":str(path),"dx":code,"lesion_id":f"synthetic-{code}-{n}"})
    return rows
