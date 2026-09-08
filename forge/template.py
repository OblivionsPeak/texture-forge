"""Read what an iRacing paint template already knows about the car.

iRacing ships a layered PSD per car. Four hidden layers inside it carry
everything a generator needs to place artwork without anyone tracing panels:

  Mask            the dead space between UV islands (inverted: paintable is its complement)
  Wire            the full polygon mesh, so mesh density doubles as a curvature map
  Sponsor Blocks  rectangles where iRacing's own artists say a sponsor decal sits flat
  Number Blocks   rectangles where the race number goes

All four ship switched OFF, so composite() returns nothing for them - they are
read raw with layer.numpy() and placed at their own offset on the sheet.
Verified on the Porsche 992 GT3 R kit; other kits follow the same layout.

Templates are licensed downloads, so none are bundled. The user drops one in
and what is derived from it is cached under out/templates/<slug>/.
"""
import json
import re
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

OUT_DIR = Path(__file__).parent.parent / "out"
TEMPLATES_DIR = OUT_DIR / "templates"

WIRE_NAMES = ("wire", "wireframe")
MASK_NAMES = ("mask",)
GUIDE_HINTS = ("wireframe", "wire")
PAINTABLE_HINTS = ("mask",)


def slugify(name):
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s[:48] or "template"


# ------------------------------------------------------------------ reading

def _walk(group, out, depth=0):
    for layer in group:
        out.append((str(layer.name or ""), layer, depth))
        if layer.is_group():
            _walk(layer, out, depth + 1)


def load(path):
    from psd_tools import PSDImage
    path = Path(path)
    psd = PSDImage.open(path)
    layers = []
    _walk(psd, layers)
    return {"path": path, "psd": psd, "size": psd.size, "layers": layers}


def _find(t, exact, hints=()):
    for name, layer, _ in t["layers"]:
        if name.strip().lower() in exact:
            return name, layer
    for name, layer, _ in t["layers"]:
        if any(h in name.lower() for h in hints):
            return name, layer
    return None


def _raw_alpha(layer, size):
    """Layer alpha on the full sheet, ignoring visibility, honouring its offset."""
    try:
        arr = layer.numpy()
    except Exception:
        return None
    if arr is None or arr.ndim != 3 or arr.shape[2] < 4:
        return None
    alpha = arr[..., 3]
    canvas = np.zeros((size[1], size[0]), np.float32)
    top, left = int(layer.top), int(layer.left)
    h, w = alpha.shape
    y0, x0 = max(0, top), max(0, left)
    y1, x1 = min(size[1], top + h), min(size[0], left + w)
    if y1 <= y0 or x1 <= x0:
        return None
    canvas[y0:y1, x0:x1] = alpha[y0 - top:y1 - top, x0 - left:x1 - left]
    return canvas


def paintable_mask(t):
    """255 where paint reaches the bodywork. The Mask layer marks the OPPOSITE."""
    found = _find(t, MASK_NAMES, PAINTABLE_HINTS)
    if found:
        a = _raw_alpha(found[1], t["size"])
        if a is not None and (a > 0.03).any():
            return Image.fromarray(((a <= 0.03) * 255).astype(np.uint8), "L")
    comp = t["psd"].composite().convert("RGBA")
    ch = np.asarray(comp.getchannel("A"))
    if ch.min() >= 250:
        return Image.new("L", t["size"], 255)
    return Image.fromarray(((ch > 8) * 255).astype(np.uint8), "L")


def wire(t):
    found = _find(t, WIRE_NAMES, GUIDE_HINTS)
    if not found:
        return None
    a = _raw_alpha(found[1], t["size"])
    if a is None or not (a > 0.02).any():
        return None
    return Image.fromarray(((a > 0.02) * 255).astype(np.uint8), "L")


def curvature(wire_img, paint_mask, radius=24):
    """Mesh density as a 0..255 map. Dense mesh = curved surface = artwork distorts.

    Modellers subdivide where the surface bends, so line density over a window
    is a serviceable curvature estimate, free, with no 3D data. Used to steer
    motifs onto flat panels and to warn when a block sits on a curve.
    """
    if wire_img is None:
        return Image.new("L", paint_mask.size, 0)
    dens = wire_img.filter(ImageFilter.BoxBlur(radius))
    a = np.asarray(dens).astype(np.float32)
    inside = np.asarray(paint_mask) > 0
    if inside.any():
        hi = np.percentile(a[inside], 97) or 1.0
        a = np.clip(a / hi, 0, 1) * 255
    a[~inside] = 0
    return Image.fromarray(a.astype(np.uint8), "L")


# ------------------------------------------------------------------- blocks

BLOCK_KINDS = (("sponsor", ("sponsor",)), ("number", ("number",)))


def _components(mask, min_area):
    """Bounding boxes of 4-connected components, largest first."""
    h, w = mask.shape
    lab = np.zeros((h, w), np.int32)
    boxes = []
    n = 0
    ys_idx, xs_idx = np.nonzero(mask)
    for sy, sx in zip(ys_idx, xs_idx):
        if lab[sy, sx]:
            continue
        n += 1
        lab[sy, sx] = n
        q = deque([(sy, sx)])
        x0 = x1 = sx
        y0 = y1 = sy
        area = 0
        while q:
            y, x = q.popleft()
            area += 1
            x0, x1, y0, y1 = min(x0, x), max(x1, x), min(y0, y), max(y1, y)
            for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not lab[ny, nx]:
                    lab[ny, nx] = n
                    q.append((ny, nx))
        if area >= min_area:
            boxes.append({"x": int(x0), "y": int(y0), "w": int(x1 - x0 + 1),
                          "h": int(y1 - y0 + 1), "area": int(area)})
    boxes.sort(key=lambda b: -b["area"])
    return boxes


def blocks(t, curv=None):
    """iRacing's own decal zones, read from the hidden block layers."""
    out = []
    W, H = t["size"]
    for kind, hints in BLOCK_KINDS:
        for name, layer, _ in t["layers"]:
            low = name.lower()
            # 992 kit: "Sponsor Blocks" / "Number Blocks". P217 kit: "Sponsor" /
            # "Numbers". Leaderboard blocks are series overlays, not paint zones.
            if layer.is_group() or not any(h in low for h in hints) or "leaderboard" in low:
                continue
            a = _raw_alpha(layer, t["size"])
            if a is None:
                continue
            for i, b in enumerate(_components(a > 0.15, min_area=400)):
                b.update({"id": f"{kind}{len([o for o in out if o['kind'] == kind]) + 1:02d}",
                          "kind": kind, "layer": name,
                          "orient": "landscape" if b["w"] >= b["h"] else "portrait"})
                if curv is not None:
                    c = np.asarray(curv)[b["y"]:b["y"] + b["h"], b["x"]:b["x"] + b["w"]]
                    b["curvature"] = round(float(c.mean()) / 255, 3)
                out.append(b)
    return out


def auto_blocks(paint_mask, curv, max_curv=0.22, min_area=9000, erode=14):
    """Flat zones found from the curvature map, for kits with no block layers.

    Paintable pixels whose mesh density is low form the candidate set. Eroding
    it drops the thin strips and leaves the panels; each component's bounding
    box becomes a zone, shrunk to the box's inscribed extent.
    """
    m = (np.asarray(paint_mask) > 0) & (np.asarray(curv) < max_curv * 255)
    img = Image.fromarray((m * 255).astype(np.uint8), "L").filter(ImageFilter.MinFilter(erode * 2 + 1))
    comps = _components(np.asarray(img) > 0, min_area)
    out = []
    for i, b in enumerate(comps[:12]):
        b.update({"id": f"sponsor{i + 1:02d}", "kind": "sponsor", "layer": "(auto: flat area)",
                  "orient": "landscape" if b["w"] >= b["h"] else "portrait",
                  "curvature": round(float(np.asarray(curv)[b["y"]:b["y"] + b["h"],
                                                              b["x"]:b["x"] + b["w"]].mean()) / 255, 3),
                  "auto": True})
        out.append(b)
    return out


# ----------------------------------------------------------------- previews

def flat_composite(t):
    """The template as a painter first sees it: shaded body + mandatory decals."""
    return t["psd"].composite().convert("RGB")


BODY_HINTS = ("main car body", "base", "body")


def clean_sheet(t, paint_mask):
    """The shaded body alone, no decals, no mesh, dead space mid-grey.

    This is what an edit model should see. Feeding it the composite made it
    paint the kit's Porsche lettering and the faint wireframe into the livery.
    The base layer is the first plain layer of the Paintable Area group in
    every kit checked ('Main Car Body' on the 992, 'Base' on the P217).
    """
    layer = None
    for name, l, depth in t["layers"]:
        if not l.is_group() and name.strip().lower() in BODY_HINTS:
            layer = l
            break
    if layer is None:
        for name, l, depth in t["layers"]:
            if not l.is_group() and depth == 1:
                layer = l
                break
    canvas = Image.new("RGB", t["size"], (128, 128, 128))
    if layer is not None:
        try:
            img = layer.topil()
            if img is not None:
                canvas.paste(img.convert("RGB"), (int(layer.left), int(layer.top)))
        except Exception:
            pass
    dead = Image.new("RGB", t["size"], (40, 40, 44))
    return Image.composite(canvas, dead, paint_mask)


# ------------------------------------------------------------------ ingest

def ingest(path, force=False):
    """Extract everything once, cache it, return the summary."""
    path = Path(path)
    slug = slugify(path.stem)
    out = TEMPLATES_DIR / slug
    info_path = out / "info.json"
    if info_path.exists() and not force:
        return json.loads(info_path.read_text("utf-8"))
    out.mkdir(parents=True, exist_ok=True)

    t = load(path)
    mask = paintable_mask(t)
    w = wire(t)
    curv = curvature(w, mask)
    blk = blocks(t, curv)
    auto = False
    if not any(b["kind"] == "sponsor" for b in blk):
        blk = auto_blocks(mask, curv) + [b for b in blk if b["kind"] == "number"]
        auto = True
    flat = flat_composite(t)

    mask.save(out / "paintable_mask.png")
    (w or Image.new("L", t["size"], 0)).save(out / "wire.png")
    curv.save(out / "curvature.png")
    flat.save(out / "flat.png")
    # Kontext sees the shaded sheet with the mesh drawn faintly on top: enough
    # structure to respect panels, not so much that it paints the mesh.
    guide = flat.copy()
    if w is not None:
        faint = Image.new("RGB", t["size"], (255, 255, 255))
        guide = Image.composite(faint, guide, w.point(lambda v: int(v * 0.35)))
    guide.save(out / "guide.png")
    shade = flat.convert("L")
    shade.save(out / "shading.png")
    clean_sheet(t, mask).save(out / "clean.png")

    info = {
        "slug": slug, "name": path.stem, "source": str(path),
        "size": list(t["size"]), "layers": len(t["layers"]),
        "paintable": round(float((np.asarray(mask) > 0).mean()), 4),
        "has_wire": w is not None,
        "blocks_auto": auto,
        "blocks": blk,
        "sponsor_blocks": sum(1 for b in blk if b["kind"] == "sponsor"),
        "number_blocks": sum(1 for b in blk if b["kind"] == "number"),
        "files": {"mask": "paintable_mask.png", "wire": "wire.png", "curvature": "curvature.png",
                  "flat": "flat.png", "guide": "guide.png", "shading": "shading.png",
                  "clean": "clean.png"},
    }
    info_path.write_text(json.dumps(info, indent=1), "utf-8")
    return info


def list_templates():
    out = []
    if not TEMPLATES_DIR.exists():
        return out
    for d in sorted(TEMPLATES_DIR.iterdir()):
        p = d / "info.json"
        if p.exists():
            try:
                i = json.loads(p.read_text("utf-8"))
                out.append({k: i[k] for k in ("slug", "name", "size", "paintable", "has_wire",
                                              "sponsor_blocks", "number_blocks")})
            except Exception:
                continue
    return out


def load_info(slug):
    p = TEMPLATES_DIR / slug / "info.json"
    if not p.exists():
        return None
    return json.loads(p.read_text("utf-8"))
