"""Concept packs: one brief in, a studio render + cut-out motifs + palette out.

This is the "ChatGPT mock-up" workflow, done locally. A brief like "Day of the
Dead, inspired by Operation Motorsport" becomes:

  1. a side-profile studio render of the car wearing the concept, for pitching;
  2. every motif in the concept as its own alpha-cut PNG, for Clearcoat;
  3. the palette the render actually used, as hex, for Clearcoat's colour picker;
  4. a manifest and a zip so the whole thing travels as one file.

What it deliberately does NOT do is turn the render into a paint file. The
render shows one side of a 3D car; the template is a flattened UV sheet, and
there is no honest projection from one to the other without the car's mesh.
Placement stays in Clearcoat, where the real geometry is in front of you.

Wordmarks are never generated. Diffusion melts lettering, so the team logo is
supplied as a PNG and shipped through the pack untouched.
"""
import json
import random
import shutil
import threading
import time
import uuid
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image

from . import post, prompts, providers

OUT_DIR = Path(__file__).parent.parent / "out"

# ------------------------------------------------------------------ themes

# A theme is a starting list of motifs, not a cage. The UI shows the list and
# the user edits it before anything is generated. Keys are matched as
# substrings of the lowercased brief, so "dia de los muertos" and "day of the
# dead" both land on the same entry.
THEMES = [
    {
        "match": ["day of the dead", "dia de los muertos", "día de los muertos", "sugar skull"],
        "name": "Day of the Dead",
        "motifs": [
            "an ornate sugar skull with floral eye sockets",
            "a papel picado banner with cut-paper skull and flower pattern",
            "a marigold flower in full bloom",
            "a lit memorial candle with a soft flame",
            "a cluster of roses with ornate leaves",
            "a decorative filigree scroll flourish",
        ],
        "palette_hint": "black base with orange, magenta, violet and white",
        "style": "vinyl",
    },
    {
        "match": ["memorial", "remembrance", "poppy", "veterans day", "armistice"],
        "name": "Remembrance",
        "motifs": [
            "a red remembrance poppy",
            "a folded flag triangle emblem",
            "a laurel wreath",
            "a single military dog tag on a chain",
            "an eternal flame emblem",
        ],
        "palette_hint": "matte black base with crimson red, gold and white",
        "style": "vinyl",
    },
    {
        "match": ["camo", "camouflage", "military", "army", "tactical"],
        "name": "Tactical",
        "motifs": [
            "a chevron rank insignia",
            "a stencil star emblem",
            "a shield crest with crossed swords",
            "a stencil serial number plate without any characters",
        ],
        "palette_hint": "olive drab, sand, charcoal and a single bright accent",
        "style": "vinyl",
    },
    {
        "match": ["japan", "japanese", "oni", "koi", "sakura", "samurai", "ukiyo"],
        "name": "Japanese",
        "motifs": [
            "a Japanese Oni demon mask",
            "a koi carp curling through water",
            "a spray of cherry blossom on a branch",
            "a great wave crest",
            "a rising sun emblem",
        ],
        "palette_hint": "deep indigo, vermilion red, white and gold",
        "style": "woodblock",
    },
    {
        "match": ["halloween", "spooky", "haunted", "pumpkin", "ghost"],
        "name": "Halloween",
        "motifs": [
            "a grinning jack-o-lantern",
            "a flying bat silhouette",
            "a spider web corner",
            "a floating cartoon ghost",
            "a bare twisted dead tree",
        ],
        "palette_hint": "black base with pumpkin orange, acid green and violet",
        "style": "vinyl",
    },
    {
        "match": ["space", "galaxy", "cosmic", "nebula", "astronaut", "rocket"],
        "name": "Cosmic",
        "motifs": [
            "a ringed planet",
            "a retro rocket ship",
            "an astronaut helmet",
            "a shooting star with a long trail",
            "a crescent moon with stars",
        ],
        "palette_hint": "deep navy and black with violet, cyan and white",
        "style": "painted",
    },
    {
        "match": ["christmas", "holiday", "winter", "snow", "festive"],
        "name": "Holiday",
        "motifs": [
            "a crystalline snowflake",
            "a holly sprig with red berries",
            "a candy cane",
            "a wrapped gift with a bow",
            "a pine tree silhouette",
        ],
        "palette_hint": "deep green and red with white and gold",
        "style": "vinyl",
    },
    {
        "match": ["pride", "rainbow"],
        "name": "Pride",
        "motifs": [
            "a heart emblem",
            "a burst of confetti shapes",
            "a bold star emblem",
            "a stylised flag ribbon",
        ],
        "palette_hint": "full rainbow spectrum on white or black",
        "style": "vinyl",
    },
]

GENERIC_MOTIFS = [
    "an emblem that captures the theme",
    "a decorative flourish that captures the theme",
    "a bold icon that captures the theme",
]

CARS = {
    "prototype": "a Le Mans hypercar prototype with a large rear wing, low sleek closed cockpit",
    "gt3": "a wide-body GT3 racing car with a large rear wing and front splitter",
    "gt4": "a GT4 racing car with a modest rear wing",
    "stock": "a NASCAR-style stock car",
    "openwheel": "an open-wheel formula racing car",
    "touring": "a TCR touring car with a rear wing",
    "rally": "a rally car with mud flaps and roof scoop",
}

RENDER_NEGATIVE = (
    "blurry, low quality, deformed, extra wheels, extra wings, cropped, "
    "cut off, watermark, signature, people, crowd, driver standing, "
    "track, grass, gravel, trees, sky, buildings, motion blur, "
    "top-down view, rear view, front view, three-quarter view"
)


def match_theme(brief):
    b = (brief or "").lower()
    for t in THEMES:
        if any(k in b for k in t["match"]):
            return t
    return None


def suggest(brief):
    """What the UI shows before anything is generated: an editable motif list."""
    t = match_theme(brief)
    if t:
        return {"theme": t["name"], "motifs": list(t["motifs"]),
                "palette_hint": t["palette_hint"], "style": t["style"]}
    return {"theme": None, "motifs": list(GENERIC_MOTIFS),
            "palette_hint": None, "style": "vinyl"}


# ----------------------------------------------------------------- prompts

def render_prompt(brief, car="prototype", team=None, palette=None, motifs=None,
                  text_capable=False):
    """Studio side-profile render of the car wearing the concept.

    text_capable is the fork that matters. FLUX will try to write the team name
    and produce alphabet soup, so the local prompt asks for a BLANK panel where
    the wordmark goes and says "no text" as hard as it can. GPT Image renders
    text well, so that route asks for the name outright.
    """
    car_desc = CARS.get(car, CARS["prototype"])
    motif_txt = ""
    if motifs:
        motif_txt = " The artwork features " + ", ".join(m.strip() for m in motifs[:5] if m.strip()) + "."
    pal_txt = f" Colour scheme: {palette}." if palette else ""
    if text_capable and team:
        text_txt = (f' The words "{team.upper()}" are printed large and legible in a clean bold '
                    f"sans-serif on the side of the car, above the side skirt.")
    elif team:
        text_txt = (" A large plain flat solid white rectangle sits on the door where a sponsor "
                    "name would go, completely empty, no lettering.")
    else:
        text_txt = ""
    return (
        f"Professional studio photograph of {car_desc}, exact side profile view, "
        f"perfectly perpendicular to the camera, whole car in frame with margin, "
        f"seamless light grey studio backdrop, soft even studio lighting, "
        f"gloss paint with clean reflections. "
        f"The car wears a full custom livery inspired by {brief.strip()}: "
        f"the artwork flows across the bodywork as one designed composition.{motif_txt}{pal_txt}"
        f"{text_txt} No text anywhere else, no logos, no sponsor decals, no numbers. "
        f"Photorealistic, 8k, automotive press photo."
    ), RENDER_NEGATIVE


# ----------------------------------------------------------------- palette

def extract_palette(img, k=6):
    """Dominant paint colours from a render, as hex.

    The studio backdrop and the tyres are the two biggest colour masses in any
    car render and neither is paint, so pixels are filtered to the same
    coloured-not-crushed band the squint test uses before quantising.
    """
    rgb = np.asarray(img.convert("RGB").resize((256, 256), Image.LANCZOS)).astype(np.float32)
    mx, mn = rgb.max(axis=2), rgb.min(axis=2)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1), 0)
    lum = 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]
    keep = (sat > 0.18) & (lum > 20) & (lum < 245)
    px = rgb[keep]
    if len(px) < 200:
        px = rgb.reshape(-1, 3)
    # Median cut with only k bins averages neighbouring hues into mud (a
    # magenta and a violet become one dull mauve). Over-quantise, then keep
    # the most populous bins that are visibly distinct from what is kept.
    flat = Image.fromarray(px.reshape(1, -1, 3).astype(np.uint8))
    q = flat.quantize(colors=k * 4, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette()
    counts = sorted(q.getcolors(), reverse=True)
    kept, out = [], []
    for n, idx in counts:
        c = np.array(pal[idx * 3: idx * 3 + 3], dtype=np.float32)
        if any(np.abs(c - kc).sum() < 90 for kc in kept):
            continue
        kept.append(c)
        r, g, b = c.astype(int)
        out.append({"hex": "#%02x%02x%02x" % (r, g, b), "share": round(n / max(1, len(px)), 3)})
        if len(out) >= k:
            break
    # A dark base is always present on a real car even if the filter removed it.
    dark = rgb[lum < 40]
    if len(dark) > len(rgb.reshape(-1, 3)) * 0.05:
        r, g, b = dark.mean(axis=0).astype(int)
        out.append({"hex": "#%02x%02x%02x" % (r, g, b), "share": round(len(dark) / rgb[..., 0].size, 3),
                    "role": "base"})
    return out


# -------------------------------------------------------------------- jobs

JOBS = {}
_LOCK = threading.Lock()


def _set(job, **kw):
    with _LOCK:
        job.update(kw)


def _log(job, msg):
    with _LOCK:
        job["log"].append(msg)


def start(body):
    """Kick off a pack build in the background and return its id."""
    job = {
        "id": uuid.uuid4().hex[:10],
        "started": time.time(),
        "done": False,
        "error": None,
        "step": "queued",
        "progress": 0,
        "total": 0,
        "log": [],
        "render": None,
        "palette": [],
        "assets": [],
        "wordmark": None,
        "zip": None,
        "folder": None,
    }
    JOBS[job["id"]] = job
    t = threading.Thread(target=_run, args=(job, body), daemon=True)
    t.start()
    return job["id"]


def get(job_id):
    j = JOBS.get(job_id)
    if not j:
        return None
    with _LOCK:
        return dict(j)


def _run(job, body):
    try:
        _build(job, body)
    except Exception as e:                       # surfaced to the UI, never lost
        _set(job, error=str(e), done=True, step="failed")


def _build(job, body):
    brief = (body.get("brief") or "").strip()
    if not brief:
        raise ValueError("write a brief first")
    provider = body.get("provider", "local")
    prov = providers.PROVIDERS.get(provider)
    if not prov:
        raise ValueError(f"unknown engine {provider}")
    team = (body.get("team") or "").strip() or None
    car = body.get("car", "prototype")
    motifs = [m for m in (body.get("motifs") or []) if m and m.strip()]
    style = body.get("style", "vinyl")
    palette_hint = (body.get("palette_hint") or "").strip() or None
    want_render = bool(body.get("render", True))
    quality = body.get("quality", "high")
    steps = int(body.get("steps", 20))
    seed0 = int(body.get("seed") or random.randint(1, 2**31 - 1))

    stem = f"concept_{int(time.time())}_{seed0}"
    folder = OUT_DIR / stem
    folder.mkdir(parents=True, exist_ok=True)
    _set(job, folder=stem, total=(1 if want_render else 0) + len(motifs) + 1)

    # ---- 1. render
    if want_render:
        _set(job, step="rendering the concept car")
        pos, neg = render_prompt(brief, car, team, palette_hint, motifs,
                                 text_capable=prov["cloud"])
        # Landscape, because a side profile is wide. 1408x1024 is the largest
        # FLUX frame that fits the 12GB card; gpt-image-2 takes any /16 size.
        w, h = (1408, 1024) if provider == "local" else (1536, 1024)
        src = providers.generate(provider, prompt=pos, negative=neg, width=w, height=h,
                                 seed=seed0, steps=steps, guidance=3.5, quality=quality)
        img = Image.open(src).convert("RGB")
        img.save(folder / "render.png")
        pal = extract_palette(img)
        _set(job, render={"url": f"/out/{stem}/render.png", "size": img.size,
                          "prompt": pos, "seed": seed0},
             palette=pal, progress=1)
        _log(job, f"render done ({img.size[0]}x{img.size[1]})")

    # ---- 2. motifs, each as an alpha-cut decal
    assets = []
    for i, m in enumerate(motifs):
        _set(job, step=f"motif {i + 1}/{len(motifs)}: {m}")
        # "photo realistic X" under the Vinyl style fought itself: the style
        # wrapper asked for flat vector art and won. Let the subject decide.
        st = "photo" if ("photo" in m.lower() or "realistic" in m.lower()) else style
        pos, neg = prompts.compile_single(m, st, palette_hint)
        seed = seed0 + i + 1
        src = providers.generate(provider, prompt=pos, negative=neg, width=1024, height=1024,
                                 seed=seed, steps=steps, guidance=3.5, quality=quality,
                                 transparent=True)
        img = Image.open(src)
        removed = 0.0
        if img.mode != "RGBA" or img.getchannel("A").getextrema()[0] == 255:
            img, removed = post.cutout(img)
        img = post.trim_to_subject(img)
        name = f"motif_{i + 1:02d}_{_slug(m)}.png"
        img.save(folder / name)
        a = {"name": name, "url": f"/out/{stem}/{name}", "subject": m, "seed": seed,
             "size": img.size, "cutout": round(removed * 100, 1),
             "transparent": img.mode == "RGBA" and img.getchannel("A").getextrema()[0] < 255}
        assets.append(a)
        _set(job, assets=list(assets), progress=(1 if want_render else 0) + i + 1)
        _log(job, f"motif {i + 1} done: {m}")

    # ---- 3. wordmark passes through untouched
    wm = body.get("wordmark_file")
    if wm and Path(wm).exists():
        dst = folder / ("wordmark" + Path(wm).suffix.lower())
        shutil.copy(wm, dst)
        _set(job, wordmark={"url": f"/out/{stem}/{dst.name}", "name": dst.name})
        _log(job, "wordmark added to pack")

    # ---- 4. manifest + zip
    _set(job, step="packing")
    j = get(job["id"])
    manifest = {
        "brief": brief, "team": team, "car": car, "engine": provider, "style": style,
        "palette_hint": palette_hint, "seed": seed0,
        "render": "render.png" if want_render else None,
        "render_prompt": j["render"]["prompt"] if j["render"] else None,
        "palette": j["palette"],
        "assets": [{k: a[k] for k in ("name", "subject", "seed", "size", "transparent")} for a in assets],
        "wordmark": j["wordmark"]["name"] if j["wordmark"] else None,
        "note": ("Place these in Clearcoat on the real template. The render is a pitch "
                 "image, not a paint file: it cannot be projected onto the UV sheet."),
    }
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2), "utf-8")
    zpath = OUT_DIR / f"{stem}.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(folder.iterdir()):
            z.write(p, f"{stem}/{p.name}")
    _set(job, zip=f"/out/{stem}.zip", progress=j["total"], step="done", done=True)


def _slug(s):
    s = "".join(c if c.isalnum() else "-" for c in s.lower()).strip("-")
    while "--" in s:
        s = s.replace("--", "-")
    return s[:40] or "motif"
