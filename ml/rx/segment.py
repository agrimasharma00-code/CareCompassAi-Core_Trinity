def segment(image, max_boxes=30):
    """Return conservative word-box proposals in the original image coordinate space.

    Steps: grayscale -> blur -> adaptive threshold -> horizontal dilation
    (joins letters into words) -> contours -> filter -> sort in reading order.
    Returns a list of {"x", "y", "w", "h"} dicts. An empty list is a valid result.
    The user can always delete wrong boxes or draw missing ones in the UI.
    """
    import numpy as np

    try:
        import cv2
    except ImportError:
        return []

    # Convert safely; anything that isn't a real image gives no boxes instead of crashing
    try:
        arr = np.asarray(image.convert("RGB"))
    except Exception:
        return []
    if arr.dtype == object or arr.ndim != 3:
        return []

    # 1. Grayscale + light blur to remove noise
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)

    # 2. Adaptive threshold: ink becomes white, paper becomes black
    binary = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 12
    )

    # 3. Wide, flat kernel joins nearby letters into one word blob
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (18, 3))
    joined = cv2.dilate(binary, kernel, iterations=1)

    # 4. Find each blob's outline
    h, w = gray.shape
    contours, _ = cv2.findContours(joined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    boxes = []
    for cnt in contours:
        x, y, bw, bh = cv2.boundingRect(cnt)
        area = bw * bh
        ratio = bw / max(1, bh)

        # 5. Filters (all relative to image size, so they work for small and large photos)
        too_small = area < max(80, (w * h) * 0.008)                  # dots, specks, stray marks
        too_wide = bw > w * 0.85                                     # full-width lines / page edges
        too_tall = bh > h * 0.5                                      # vertical page edges / shadows
        touches_side = (x <= 2 or x + bw >= w - 2) and bh > h * 0.3  # tall blobs on the image border
        thin_line = ratio > 4 and bh < h * 0.08                      # underlines and strike-through lines
        if too_small or too_wide or too_tall or touches_side or thin_line:
            continue

        # 6. Add a little padding, kept inside the image
        pad = 3
        x0 = max(0, x - pad)
        y0 = max(0, y - pad)
        x1 = min(w, x + bw + pad)
        y1 = min(h, y + bh + pad)
        boxes.append({"x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0})

    # 7. Reading order: top-to-bottom (by approximate row), then left-to-right
    boxes.sort(key=lambda b: (round(b["y"] / max(1, b["h"])), b["x"]))
    return boxes[:max_boxes]