def fake_words(count=2000, seed=17):
    import random
    random.seed(seed); names=["Amoxicillin","Paracetamol","Cetirizine","Metformin","Aspirin","Azithromycin","Omeprazole","Ibuprofen","Losartan","Vitamin C"]
    return [random.choice(names) for _ in range(count)]
def render_words(words, out_dir="ml/data/rx_synthetic"):
    from pathlib import Path
    from PIL import Image,ImageDraw,ImageFont,ImageFilter
    import random
    out=Path(out_dir);out.mkdir(parents=True,exist_ok=True); paths=[]
    for i,word in enumerate(words):
        im=Image.new("L",(256,64),255); draw=ImageDraw.Draw(im)
        try: font=ImageFont.truetype("arial.ttf",random.randint(22,38))
        except OSError: font=ImageFont.load_default()
        draw.text((4,8),word,fill=random.randint(0,70),font=font); im=im.rotate(random.uniform(-3,3),fillcolor=255); im=im.filter(ImageFilter.GaussianBlur(.2))
        path=out/f"{i:05}.png";im.save(path);paths.append((str(path),word))
    return paths
