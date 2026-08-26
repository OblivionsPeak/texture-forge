"""Post-processing that turns a nice picture into a usable texture.

Three jobs: strip the photographic artefacts FLUX adds even when told not to,
make the result tile, and tell you whether it will actually read on a moving
car — which is the test most liveries fail.
"""
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter


def devignette(img, strength=1.0):
    """Flatten radial corner darkening.

    FLUX adds a vignette to almost anything that smells like a photograph. On a
    car it shows up as a dirty smudge wherever the texture's corner lands.
    """
    a = np.asarray(img.convert("RGB")).astype(np.float32)
    h, w, _ = a.shape
    yy, xx = np.mgrid[0:h, 0:w]
    cy, cx = (h - 1) / 2, (w - 1) / 2
    r = np.sqrt(((yy - cy) / cy) ** 2 + ((xx - cx) / cx) ** 2) / np.sqrt(2)

    lum = a.mean(axis=2)
    # Compare the outer ring against the centre to size the correction.
    centre = lum[r < 0.35].mean() if (r < 0.35).any() else lum.mean()
    edge = lum[r > 0.80].mean() if (r > 0.80).any() else lum.mean()
    if centre <= 1 or edge >= centre * 0.97:
        return img                                    # no meaningful vignette
    deficit = 1.0 - (edge / centre)
    gain = 1.0 + strength * deficit * (r ** 2)
    out = np.clip(a * gain[..., None], 0, 255).astype(np.uint8)
    return Image.fromarray(out)


def mirror_tile(img):
    """Guaranteed-seamless 2x2 by mirroring. Never has a visible seam."""
    w, h = img.size
    out = Image.new("RGB", (w * 2, h * 2))
    out.paste(img, (0, 0))
    out.paste(img.transpose(Image.FLIP_LEFT_RIGHT), (w, 0))
    out.paste(img.transpose(Image.FLIP_TOP_BOTTOM), (0, h))
    out.paste(img.transpose(Image.FLIP_LEFT_RIGHT).transpose(Image.FLIP_TOP_BOTTOM), (w, h))
    return out


def punch(img, contrast=1.0, saturation=1.0):
    if contrast != 1.0:
        img = ImageEnhance.Contrast(img).enhance(contrast)
    if saturation != 1.0:
        img = ImageEnhance.Color(img).enhance(saturation)
    return img


def _paint_mask(a):
    """Pixels that are plausibly the paint, on a full car render.

    Measuring a whole photo is worthless for this: studio background, black
    tyres, white sidewall lettering and the numbers between them span nearly
    the full luminance range, so any livery scores "excellent" — including one
    whose pattern provably vanishes at distance. Isolating the dominant hue
    band leaves the bodywork and answers the question actually being asked.
    """
    mx = a.max(axis=2)
    mn = a.min(axis=2)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1), 0)
    lum = 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]

    # Coloured, not blown out, not crushed: excludes tyres, lettering, backdrop.
    cand = (sat > 0.12) & (lum > 18) & (lum < 240)
    if cand.sum() < a.shape[0] * a.shape[1] * 0.02:
        return None

    import colorsys
    r, g, b = a[..., 0] / 255, a[..., 1] / 255, a[..., 2] / 255
    mxf, mnf = np.maximum(np.maximum(r, g), b), np.minimum(np.minimum(r, g), b)
    d = np.maximum(mxf - mnf, 1e-6)
    hue = np.where(mxf == r, ((g - b) / d) % 6,
          np.where(mxf == g, (b - r) / d + 2, (r - g) / d + 4)) * 60

    hist, edges = np.histogram(hue[cand], bins=36, range=(0, 360))
    peak = int(np.argmax(hist))
    centre = (edges[peak] + edges[peak + 1]) / 2
    delta = np.abs((hue - centre + 180) % 360 - 180)
    return cand & (delta < 30)


def value_range(img, isolate_paint=False):
    """Spread of luminance — the number that predicts distance legibility.

    Hue vanishes with distance before value does. A texture whose patches all
    share one brightness reads as a single flat mass on a moving car no matter
    how much detail it holds up close. That is exactly why a purple-on-purple
    camo disappears.

    Set isolate_paint for a full car render; leave it off for a bare texture.
    """
    a = np.asarray(img.convert("RGB")).astype(np.float32)
    lum = 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]

    scope = "whole image"
    if isolate_paint:
        m = _paint_mask(a)
        if m is not None and m.sum() > 500:
            lum = lum[m]
            scope = f"paint only ({100 * m.mean():.0f}% of frame)"
        else:
            scope = "whole image (could not isolate paint)"

    p5, p95 = np.percentile(lum, 5), np.percentile(lum, 95)
    spread = float(p95 - p5)
    if spread >= 140:
        verdict, ok = "excellent — will read clearly at track distance", True
    elif spread >= 95:
        verdict, ok = "good — holds up at mid distance", True
    elif spread >= 60:
        verdict, ok = "weak — detail will mostly vanish beyond a few car lengths", False
    else:
        verdict, ok = "flat — this will read as one solid colour on track", False
    return {"spread": round(spread, 1), "std": round(float(lum.std()), 1),
            "verdict": verdict, "ok": ok, "scope": scope}


def squint(img, scale=0.06):
    """Downsample hard, then blow back up: what the texture looks like at speed."""
    w, h = img.size
    small = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
    return small.resize((w // 2, h // 2), Image.NEAREST)


def to_texture(img, size=2048, do_devignette=True, tile=False,
               contrast=1.0, saturation=1.0):
    """Full pipeline: clean, optionally tile, punch, resize to a power of two."""
    out = img.convert("RGB")
    if do_devignette:
        out = devignette(out)
    out = punch(out, contrast, saturation)
    if tile:
        out = mirror_tile(out)
    if out.size != (size, size):
        out = out.resize((size, size), Image.LANCZOS)
    return out


# --------------------------------------------------------------- decal cutout

def cutout(img, tolerance=38, feather=1.0, min_bg_frac=0.02):
    """Knock out a flat background so a decal can sit on a panel.

    Flood-fills inward from the four corners rather than keying one colour.
    Keying by colour eats matching pixels inside the subject too - an Oni mask
    with a white tooth loses the tooth. Only background actually connected to
    an edge is removed.

    Returns RGBA. If the corners disagree, or almost nothing is removed, the
    image comes back fully opaque rather than half-destroyed.
    """
    rgb = np.asarray(img.convert("RGB")).astype(np.int16)
    h, w, _ = rgb.shape
    corners = [rgb[0, 0], rgb[0, w - 1], rgb[h - 1, 0], rgb[h - 1, w - 1]]
    ref = np.median(np.stack(corners), axis=0)

    # If the corners are wildly different there is no flat background to cut.
    spread = max(int(np.abs(np.array(c) - ref).sum()) for c in corners)
    if spread > tolerance * 4:
        return img.convert("RGBA"), 0.0

    close = (np.abs(rgb - ref).sum(axis=2) <= tolerance * 3)

    # Iterative flood fill from the border, 4-connected, via binary dilation
    # against the `close` mask - simple and fast enough at this size.
    from collections import deque
    keep = np.zeros((h, w), bool)
    dq = deque()
    for x in range(w):
        for y in (0, h - 1):
            if close[y, x] and not keep[y, x]:
                keep[y, x] = True; dq.append((y, x))
    for y in range(h):
        for x in (0, w - 1):
            if close[y, x] and not keep[y, x]:
                keep[y, x] = True; dq.append((y, x))
    while dq:
        y, x = dq.popleft()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and close[ny, nx] and not keep[ny, nx]:
                keep[ny, nx] = True
                dq.append((ny, nx))

    frac = float(keep.mean())
    if frac < min_bg_frac:
        return img.convert("RGBA"), 0.0        # nothing meaningful to remove

    alpha = np.where(keep, 0, 255).astype(np.uint8)
    out = Image.fromarray(np.dstack([np.asarray(img.convert("RGB")), alpha]), "RGBA")
    if feather > 0:
        a = out.getchannel("A").filter(ImageFilter.GaussianBlur(feather))
        out.putalpha(a)
    return out, frac


def trim_to_subject(img, pad=0.04):
    """Crop to the opaque bounding box with a little breathing room."""
    if img.mode != "RGBA":
        return img
    bbox = img.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox()
    if not bbox:
        return img
    x0, y0, x1, y1 = bbox
    px, py = int((x1 - x0) * pad), int((y1 - y0) * pad)
    return img.crop((max(0, x0 - px), max(0, y0 - py),
                     min(img.width, x1 + px), min(img.height, y1 + py)))
