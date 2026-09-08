"""Compose a paint file from a base, a template, and a concept pack.

The base is whatever fills the bodywork: a Kontext edit of the template, a flat
texture from the Textures tab, or a plain colour. The template supplies the
paintable mask and the block zones. The concept pack supplies motifs and the
wordmark. This module only places things - it never generates.

Placement rules, in order of who decided them:
  * iRacing decided where decals sit (the block layers). Motifs go there.
  * The curvature map decides which blocks are flat enough for a wordmark:
    lettering on a curved surface distorts, a skull does not care.
  * The paintable mask decides what survives.

Output is a 2048 PNG plus a 32-bit TGA in iRacing's expected orientation,
and a flat preview with the template's own shading multiplied in.
"""
import json
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

from . import template as T

OUT_DIR = Path(__file__).parent.parent / "out"


# ------------------------------------------------------------------- bases

def base_from_color(size, hex_color):
    return Image.new("RGB", size, _hex(hex_color))


def base_from_texture(size, path, mode="tile"):
    """Flat texture over the sheet. 'tile' repeats, 'stretch' fills once."""
    tex = Image.open(path).convert("RGB")
    if mode == "stretch":
        return tex.resize(size, Image.LANCZOS)
    out = Image.new("RGB", size)
    tw, th = tex.size
    for y in range(0, size[1], th):
        for x in range(0, size[0], tw):
            out.paste(tex, (x, y))
    return out


def base_from_image(size, path):
    """A full-sheet base already in template space (a Kontext edit, or a Clearcoat export)."""
    return Image.open(path).convert("RGB").resize(size, Image.LANCZOS)


def _hex(s):
    s = (s or "#000000").lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))


# --------------------------------------------------------------- placement

def fit_into(img, box, pad=0.08, rotate_to_fit=True):
    """Scale an RGBA asset to sit inside a block, centred, aspect preserved.

    A portrait asset in a landscape block is rotated 90 degrees before fitting
    if that lets it fill more of the space - a vertical wordmark on a side
    skirt is exactly how real cars carry them.
    """
    bw, bh = box["w"] * (1 - 2 * pad), box["h"] * (1 - 2 * pad)
    iw, ih = img.size
    if rotate_to_fit:
        s_plain = min(bw / iw, bh / ih)
        s_rot = min(bw / ih, bh / iw)
        if s_rot > s_plain * 1.25:
            img = img.rotate(90, expand=True)
            iw, ih = img.size
    s = min(bw / iw, bh / ih)
    nw, nh = max(1, int(iw * s)), max(1, int(ih * s))
    img = img.resize((nw, nh), Image.LANCZOS)
    x = box["x"] + (box["w"] - nw) // 2
    y = box["y"] + (box["h"] - nh) // 2
    return img, (x, y)


def _load_rgba(path):
    return Image.open(path).convert("RGBA")


def _number_image(text, box, color="#ffffff", outline="#000000"):
    """Race number rendered with PIL. Bold, outlined, sized to the block."""
    h = max(12, int(box["h"] * 0.9))
    font = None
    for name in ("arialbd.ttf", "Arial Bold.ttf", "DejaVuSans-Bold.ttf", "arial.ttf"):
        try:
            font = ImageFont.truetype(name, h)
            break
        except Exception:
            continue
    if font is None:
        font = ImageFont.load_default()
    # Measure, then draw with margin for the outline.
    tmp = Image.new("RGBA", (10, 10))
    l, t, r, b = ImageDraw.Draw(tmp).textbbox((0, 0), text, font=font, stroke_width=max(2, h // 14))
    img = Image.new("RGBA", (r - l + 8, b - t + 8), (0, 0, 0, 0))
    ImageDraw.Draw(img).text((4 - l, 4 - t), text, font=font, fill=_hex(color) + (255,),
                             stroke_width=max(2, h // 14), stroke_fill=_hex(outline) + (255,))
    return img


def plan(info, motifs, wordmark=None, number=None, wordmark_max_curv=0.30):
    """Decide what goes in which block. Returns a list of placements.

    Wordmark first, into the flattest large landscape sponsor blocks (up to
    two: one per side). Motifs fill the remaining sponsor blocks, largest
    first, cycling through the motif list. Numbers fill number blocks.
    """
    blocks = info.get("blocks") or []
    sponsor = sorted([b for b in blocks if b["kind"] == "sponsor"], key=lambda b: -b["area"])
    numbers = [b for b in blocks if b["kind"] == "number"]
    used = set()
    out = []

    if wordmark:
        flat_wide = [b for b in sponsor
                     if b.get("curvature", 0) <= wordmark_max_curv and b["orient"] == "landscape"]
        for b in flat_wide[:2]:
            out.append({"block": b["id"], "kind": "wordmark", "src": wordmark})
            used.add(b["id"])

    if motifs:
        i = 0
        for b in sponsor:
            if b["id"] in used:
                continue
            out.append({"block": b["id"], "kind": "motif", "src": motifs[i % len(motifs)]})
            used.add(b["id"])
            i += 1

    if number:
        for b in numbers:
            out.append({"block": b["id"], "kind": "number", "text": str(number)})
    return out


# ----------------------------------------------------------------- compose

def compose(info, base, placements, number_color="#ffffff", number_outline="#000000"):
    """Lay placements over the base and cut to the paintable mask. Returns RGBA."""
    size = tuple(info["size"])
    tdir = T.TEMPLATES_DIR / info["slug"]
    sheet = base.convert("RGBA").resize(size, Image.LANCZOS)
    by_id = {b["id"]: b for b in info.get("blocks") or []}
    log = []
    for p in placements:
        b = by_id.get(p["block"])
        if not b:
            continue
        if p["kind"] == "number":
            img = _number_image(p["text"], b, number_color, number_outline)
        else:
            img = _load_rgba(p["src"])
        img, pos = fit_into(img, b)
        sheet.alpha_composite(img, pos)
        log.append({"block": b["id"], "kind": p["kind"], "at": pos, "size": img.size,
                    "curvature": b.get("curvature")})
    mask = Image.open(tdir / "paintable_mask.png").convert("L").resize(size, Image.NEAREST)
    sheet.putalpha(mask)
    return sheet, log


def preview(info, sheet):
    """The sheet with the template's own shading multiplied in - a flat 'in-kit' look."""
    tdir = T.TEMPLATES_DIR / info["slug"]
    shade = Image.open(tdir / "shading.png").convert("L").resize(sheet.size, Image.LANCZOS)
    rgb = sheet.convert("RGB")
    s = np.asarray(shade).astype(np.float32) / 255.0
    # Lift the shading so it tints rather than crushes: 0.55..1.0
    s = 0.55 + 0.45 * s
    a = np.asarray(rgb).astype(np.float32) * s[..., None]
    out = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    dead = Image.new("RGB", sheet.size, (28, 30, 36))
    return Image.composite(out, dead, sheet.getchannel("A"))


def spec_map(sheet, metallic=0.35, roughness=0.25, clearcoat=0.9):
    """iRacing spec map derived, not painted: R metallic, G roughness, B clearcoat.

    Uniform values are what most painters export anyway. The one refinement is
    that pure black/white decal pixels get a touch less metallic so lettering
    reads as vinyl on paint rather than paint on paint.
    """
    rgb = np.asarray(sheet.convert("RGB")).astype(np.float32)
    sat = (rgb.max(axis=2) - rgb.min(axis=2)) / np.maximum(rgb.max(axis=2), 1)
    m = np.full(rgb.shape[:2], metallic * 255, np.float32)
    m[sat < 0.08] *= 0.6                       # greys/whites read as vinyl
    r = np.full(rgb.shape[:2], roughness * 255, np.float32)
    c = np.full(rgb.shape[:2], clearcoat * 255, np.float32)
    out = np.dstack([m, r, c]).astype(np.uint8)
    img = Image.fromarray(out, "RGB")
    img.putalpha(sheet.getchannel("A"))
    return img


def export(info, sheet, stem, with_spec=True):
    """PNG + TGA. iRacing wants a 32-bit TGA of the sheet as authored (no flip)."""
    folder = OUT_DIR / stem
    folder.mkdir(parents=True, exist_ok=True)
    sheet.save(folder / "paint.png")
    sheet.save(folder / "car.tga")
    prev = preview(info, sheet)
    prev.save(folder / "preview.png")
    files = {"paint": "paint.png", "tga": "car.tga", "preview": "preview.png"}
    if with_spec:
        sm = spec_map(sheet)
        sm.save(folder / "car_spec.tga")
        sm.save(folder / "spec.png")
        files.update({"spec_tga": "car_spec.tga", "spec": "spec.png"})
    return folder, files


# -------------------------------------------------------------------- jobs

import glob
import random
import threading
import uuid
import zipfile

from . import comfy, providers

JOBS = {}
_LOCK = threading.Lock()


def _set(job, **kw):
    with _LOCK:
        job.update(kw)


def get(job_id):
    j = JOBS.get(job_id)
    if not j:
        return None
    with _LOCK:
        return dict(j)


def list_packs():
    """Concept packs in out/, newest first, with what they hold."""
    out = []
    for d in sorted(glob.glob(str(OUT_DIR / "concept_*")), reverse=True):
        d = Path(d)
        m = d / "manifest.json"
        if not d.is_dir() or not m.exists():
            continue
        try:
            man = json.loads(m.read_text("utf-8"))
        except Exception:
            continue
        motifs = sorted(p.name for p in d.glob("motif_*.png"))
        out.append({"id": d.name, "brief": man.get("brief", ""), "team": man.get("team"),
                    "motifs": [f"/out/{d.name}/{n}" for n in motifs],
                    "wordmark": f"/out/{d.name}/{man['wordmark']}" if man.get("wordmark") else None,
                    "render": f"/out/{d.name}/render.png" if man.get("render") else None})
    return out


def list_textures():
    """Square PNGs in out/ that look like Textures-tab output."""
    out = []
    for p in sorted(OUT_DIR.glob("*.png"), key=lambda p: -p.stat().st_mtime):
        if p.name.startswith("_") or p.name.endswith("_squint.png") or p.name.startswith("analyze_"):
            continue
        out.append({"file": p.name, "url": f"/out/{p.name}"})
        if len(out) >= 40:
            break
    return out


def kontext_prompt(brief, palette_hint=None):
    """Instruction for Kontext: paint the sheet, do not redraw it."""
    pal = f" Colour scheme: {palette_hint}." if palette_hint else ""
    return (f"Paint a bold racing livery onto every grey car body part in this flat paint template "
            f"sheet, inspired by {brief}.{pal} The artwork is rich flat 2D vector illustration "
            f"with large shapes, sweeping stripes and detailed ornament, flowing across the panels. "
            f"Keep every part exactly where it is on the sheet, do not move, rotate or redraw any "
            f"outline, keep the dark background between the parts unchanged. "
            f"No text, no letters, no logos, no numbers, no photographs, no perspective, "
            f"no wireframe lines, evenly lit, sharp, high contrast.")


def gpt_prompt(info, brief, motif_names=None, palette_hint=None, has_render=False):
    """Instruction for the cloud edit model. The sheet is image 1, the render image 2."""
    car = info.get("name", "race car")
    motifs = ""
    if motif_names:
        motifs = " The design features " + ", ".join(m for m in motif_names[:6]) + "."
    pal = f" Colour scheme: {palette_hint}." if palette_hint else ""
    ref = (" The second image is the target livery design on the same car: reproduce that design "
           "on the sheet so it would look like the reference once wrapped onto the car."
           if has_render else "")
    return (f"The first image is a flat UV paint template sheet for a {car}: every grey shape is a body "
            f"panel laid flat. Paint a complete racing livery inspired by {brief} onto the sheet."
            f"{ref}{motifs}{pal} Place the main artwork on the large panels (doors, hood, roof, rear "
            f"wing) and let it flow across them; smaller parts get the base colour. Keep every panel "
            f"shape exactly where it is on the sheet, keep the dark background between panels. "
            f"Flat 2D artwork, no perspective, no text, no letters, no logos, no numbers.")


def start(body):
    job = {"id": uuid.uuid4().hex[:10], "done": False, "error": None, "step": "queued",
           "progress": 0, "total": 3, "result": None, "log": []}
    JOBS[job["id"]] = job
    threading.Thread(target=_run, args=(job, body), daemon=True).start()
    return job["id"]


def _run(job, body):
    try:
        _build(job, body)
    except Exception as e:
        _set(job, error=str(e), done=True, step="failed")


def _build(job, body):
    info = T.load_info(body.get("template") or "")
    if not info:
        raise ValueError("pick a template first")
    size = tuple(info["size"])
    seed = int(body.get("seed") or random.randint(1, 2**31 - 1))
    stem = f"paint_{info['slug']}_{int(time.time())}_{seed}"
    base_mode = body.get("base", "color")

    # ---- 1. base
    _set(job, step="building the base")
    if base_mode == "kontext":
        brief = (body.get("brief") or "").strip()
        if not brief:
            raise ValueError("Kontext needs a brief to paint from")
        if not comfy.is_up():
            raise RuntimeError("ComfyUI is not running. Start it first.")
        tdir = T.TEMPLATES_DIR / info["slug"]
        src = tdir / "clean.png"
        if not src.exists():                       # template ingested before clean.png existed
            src = tdir / "flat.png"
        _set(job, step="Kontext is painting the sheet (about a minute)")
        files, err = comfy.edit(src, kontext_prompt(brief, body.get("palette_hint")),
                                seed, steps=int(body.get("steps", 20)),
                                guidance=float(body.get("guidance", 2.5)))
        if err:
            raise RuntimeError(err)
        base = Image.open(files[0]).convert("RGB").resize(size, Image.LANCZOS)
        job["log"].append("kontext base done")
    elif base_mode == "gpt":
        brief = (body.get("brief") or "").strip()
        if not brief:
            raise ValueError("the cloud painter needs a brief")
        tdir = T.TEMPLATES_DIR / info["slug"]
        src = tdir / "clean.png"
        if not src.exists():
            src = tdir / "flat.png"
        images = [src]
        motif_names = []
        pack = body.get("pack")
        if pack:
            d = OUT_DIR / Path(pack).name
            man = {}
            try:
                man = json.loads((d / "manifest.json").read_text("utf-8"))
            except Exception:
                pass
            motif_names = [a.get("subject") for a in man.get("assets", []) if a.get("subject")]
            if body.get("use_render", True) and (d / "render.png").exists():
                images.append(d / "render.png")
        gsize = body.get("gpt_size", "1024x1024")
        if gsize not in ("1024x1024", "1536x1536", "2048x2048"):
            gsize = "1024x1024"
        _set(job, step=f"GPT Image 2 is painting the sheet at {gsize} (cloud, paid, about a minute)")
        prompt = gpt_prompt(info, brief, motif_names, body.get("palette_hint"), len(images) > 1)
        out = providers.edit_openai(images, prompt, size=gsize, quality=body.get("quality", "high"))
        base = Image.open(out).convert("RGB").resize(size, Image.LANCZOS)
        job["log"].append(f"gpt base done, {len(images)} reference image(s)")
        job["prompt"] = prompt
    elif base_mode == "texture":
        f = body.get("texture")
        if not f:
            raise ValueError("choose a texture file")
        base = base_from_texture(size, OUT_DIR / Path(f).name, body.get("texture_mode", "stretch"))
    elif base_mode == "image":
        base = base_from_image(size, body["image"])
    else:
        base = base_from_color(size, body.get("color", "#111111"))
    (OUT_DIR / stem).mkdir(parents=True, exist_ok=True)
    base.save(OUT_DIR / stem / "base.png")
    _set(job, progress=1)

    # ---- 2. placement
    _set(job, step="placing motifs, wordmark and numbers")
    pack = body.get("pack")
    motifs, wordmark = [], None
    if pack:
        d = OUT_DIR / Path(pack).name
        chosen = body.get("motifs")           # optional subset of file names
        for p in sorted(d.glob("motif_*.png")):
            if not chosen or p.name in chosen:
                motifs.append(str(p))
        if body.get("use_wordmark", True):
            for p in d.iterdir():
                if p.stem == "wordmark":
                    wordmark = str(p)
    if body.get("wordmark_file") and Path(body["wordmark_file"]).exists():
        wordmark = body["wordmark_file"]
    if not body.get("use_motifs", True):
        motifs = []
    placements = plan(info, motifs, wordmark, (body.get("number") or "").strip() or None,
                      wordmark_max_curv=float(body.get("wordmark_max_curv", 0.30)))
    sheet, log = compose(info, base, placements,
                         body.get("number_color", "#ffffff"), body.get("number_outline", "#000000"))
    _set(job, progress=2)

    # ---- 3. export
    _set(job, step="exporting")
    folder, files = export(info, sheet, stem)
    (folder / "placements.json").write_text(json.dumps(log, indent=1), "utf-8")
    (folder / "manifest.json").write_text(json.dumps({
        "template": info["slug"], "base": base_mode, "brief": body.get("brief"),
        "palette_hint": body.get("palette_hint"), "pack": body.get("pack"),
        "number": body.get("number"), "seed": seed, "prompt": job.get("prompt"),
    }, indent=1), "utf-8")
    zpath = OUT_DIR / f"{stem}.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(folder.iterdir()):
            z.write(p, f"{stem}/{p.name}")
    warn = [l for l in log if l["kind"] in ("wordmark", "number") and (l.get("curvature") or 0) > 0.45]
    _set(job, progress=3, done=True, step="done", result={
        "folder": stem,
        "preview": f"/out/{stem}/preview.png", "paint": f"/out/{stem}/paint.png",
        "base": f"/out/{stem}/base.png", "spec": f"/out/{stem}/spec.png",
        "tga": f"/out/{stem}/car.tga", "spec_tga": f"/out/{stem}/car_spec.tga",
        "zip": f"/out/{stem}.zip", "placements": log, "seed": seed,
        "warnings": [f"{w['kind']} in {w['block']} sits on a curved area (curvature {w['curvature']})" for w in warn],
    })
