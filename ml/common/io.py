from pathlib import Path

def safe_image(path, mode="RGB"):
    from PIL import Image,ImageOps,UnidentifiedImageError
    try:
        with Image.open(Path(path)) as image: return ImageOps.exif_transpose(image).convert(mode).copy()
    except (OSError,UnidentifiedImageError,ValueError): return None
