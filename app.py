"""Texture Forge — flat livery textures from local FLUX, plus the silhouette
layers diffusion does badly.

Local Flask UI on http://localhost:4796. Nothing leaves the machine.
"""
import io
import random
import time
from pathlib import Path

from flask import Flask, jsonify, request, send_file, send_from_directory
from PIL import Image

from forge import (comfy, concept, paint, post, prompts, providers, setup as fsetup,
                   silhouette, template as tmpl)

ROOT = Path(__file__).parent
OUT = ROOT / "out"
OUT.mkdir(exist_ok=True)

app = Flask(__name__, static_folder=str(ROOT / "static"), static_url_path="/static")


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/out/<path:name>")
def out_file(name):
    return send_from_directory(str(OUT), name)


@app.route("/api/status")
def status():
    up = comfy.is_up()
    return jsonify({
        "comfy_up": up,
        "vram": comfy.vram() if up else None,
        "presets": [{k: p[k] for k in ("id", "name", "hint", "color")} for p in prompts.PRESETS],
        "treatments": [{"id": k, "name": v["name"], "hint": v["hint"]}
                       for k, v in prompts.TREATMENTS.items()],
        "styles": [{"id": k, "name": v["name"], "hint": v["hint"]}
                   for k, v in prompts.SUBJECT_STYLES.items()],
        "mediums": [{"id": k, "name": v["name"], "hint": v["hint"]}
                    for k, v in prompts.ARTWORK_MEDIUMS.items()],
        "shapes": [{"id": k, "name": v["name"], "hint": v["hint"], "seamless": v["seamless"]}
                   for k, v in silhouette.SHAPES.items()],
    })


@app.route("/api/providers")
def list_providers():
    return jsonify({
        "providers": [{"id": k, "name": v["name"], "cloud": v["cloud"],
                       "hint": v["hint"], "sizes": v["sizes"]}
                      for k, v in providers.PROVIDERS.items()],
    })


@app.route("/api/setup")
def setup_status():
    return jsonify(fsetup.status())


@app.route("/api/setup/install", methods=["POST"])
def setup_install():
    kind = (request.get_json(silent=True) or {}).get("kind", "checkpoint")
    ok, msg = fsetup.install_model(kind)
    return jsonify({"ok": ok, "message": msg}), (200 if ok else 409)


@app.route("/api/comfy/<action>", methods=["POST"])
def comfy_control(action):
    if action == "start":
        ok, msg = comfy.start()
    elif action == "stop":
        ok, msg = comfy.stop()
    else:
        return jsonify({"ok": False, "error": "unknown action"}), 400
    return jsonify({"ok": ok, "message": msg, "vram": comfy.vram() if comfy.is_up() else None})


def _finish(img, body, stem, keep_aspect=False):
    """Post-process, save, measure, and return the payload the UI needs."""
    if keep_aspect:
        # Artwork keeps its panel shape: long side to 2048, no tiling.
        tex = post.punch(post.devignette(img.convert("RGB")) if body.get("devignette", True)
                         else img.convert("RGB"),
                         float(body.get("contrast", 1.0)), float(body.get("saturation", 1.0)))
        w, h = tex.size
        s = 2048 / max(w, h)
        tex = tex.resize((max(1, int(w * s)), max(1, int(h * s))), Image.LANCZOS)
    else:
        tex = post.to_texture(
            img,
            size=int(body.get("size", 2048)),
            do_devignette=bool(body.get("devignette", True)),
            tile=bool(body.get("tile", False)),
            contrast=float(body.get("contrast", 1.0)),
            saturation=float(body.get("saturation", 1.0)),
        )
    name = f"{stem}.png"
    tex.save(OUT / name)
    sq = post.squint(tex)
    sq_name = f"{stem}_squint.png"
    sq.save(OUT / sq_name)
    return {
        "file": name, "url": f"/out/{name}",
        "squint_url": f"/out/{sq_name}",
        "value_range": post.value_range(tex),
        "size": tex.size,
    }


def _finish_decal(img, stem, provider):
    """Decals keep their alpha and their aspect - no tiling, no square crop."""
    removed = 0.0
    if img.mode != "RGBA" or img.getchannel("A").getextrema()[0] == 255:
        # FLUX returns no alpha, so knock the flat background out ourselves.
        img, removed = post.cutout(img)
    img = post.trim_to_subject(img)
    name = f"{stem}.png"
    img.save(OUT / name)
    return {
        "file": name, "url": f"/out/{name}", "size": img.size,
        "cutout": round(removed * 100, 1),
        "transparent": img.mode == "RGBA" and img.getchannel("A").getextrema()[0] < 255,
    }


@app.route("/api/generate", methods=["POST"])
def generate():
    body = request.get_json(force=True) or {}
    preset = body.get("preset", "storm")
    provider = body.get("provider", "local")
    if provider == "local" and not comfy.is_up():
        return jsonify({"ok": False, "error": "ComfyUI is not running. Start it first."}), 409
    kind = body.get("kind", "texture")
    try:
        if kind == "decal":
            pos, neg = prompts.compile_single(
                body.get("subject"), body.get("style", "woodblock"), body.get("color"))
            preset = "decal"
        elif kind == "artwork":
            pos, neg = prompts.compile_artwork(
                body.get("subject"), body.get("medium", "photo"), body.get("color"))
            preset = "artwork"
        elif body.get("freeform"):
            pos, neg = prompts.compile_freeform(
                body.get("subject"), body.get("treatment", "surface"), body.get("color"))
            preset = "freeform"
        else:
            pos, neg = prompts.build(preset, body.get("color"), body.get("extra"))
    except (KeyError, ValueError) as e:
        return jsonify({"ok": False, "error": str(e) or f"unknown preset {preset}"}), 400

    seed = int(body.get("seed") or random.randint(1, 2**31 - 1))
    w = int(body.get("width", 1024))
    h = int(body.get("height", 1024))
    if kind == "artwork":
        w, h = prompts.ARTWORK_SHAPES.get(body.get("shape", "square"), (1024, 1024))
    try:
        src = providers.generate(provider, prompt=pos, negative=neg, width=w, height=h,
                                 seed=seed, steps=int(body.get("steps", 20)),
                                 guidance=float(body.get("guidance", 3.5)),
                                 transparent=(kind == "decal"))
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

    img = Image.open(src)
    stem = f"{preset}_{seed}_{int(time.time())}"
    if kind == "decal":
        payload = _finish_decal(img, stem, provider)
    else:
        payload = _finish(img, body, stem, keep_aspect=(kind == "artwork"))
    payload.update({"ok": True, "seed": seed, "prompt": pos, "provider": provider})
    return jsonify(payload)


@app.route("/api/silhouette", methods=["POST"])
def make_silhouette():
    body = request.get_json(force=True) or {}
    shape = body.get("shape", "mountains")
    seed = int(body.get("seed") or random.randint(1, 10**6))
    try:
        img = silhouette.render(
            shape,
            width=int(body.get("width", 2048)),
            height=int(body.get("height", 640)),
            seed=seed,
            layers=int(body.get("layers", 4)),
            rows=int(body.get("rows", 2)),
            density=float(body.get("density", 1.0)),
            size=float(body.get("scale", 1.0)),
            roughness=float(body.get("roughness", 1.0)),
            sharpness=float(body.get("sharpness", 1.6)),
            count=int(body.get("count", 7)),
            angle=float(body.get("angle", 18)),
        )
    except KeyError:
        return jsonify({"ok": False, "error": f"unknown shape {shape}"}), 400

    name = f"{shape}_{seed}.png"
    img.save(OUT / name)
    seamless = silhouette.SHAPES[shape]["seamless"]
    return jsonify({"ok": True, "file": name, "url": f"/out/{name}",
                    "seed": seed, "size": img.size, "seamless": seamless,
                    "note": "Alpha-only shape — recolour it in Clearcoat. " +
                            ("Seamless left-to-right, so it wraps the car."
                             if seamless else
                             "Does NOT tile — the angled ends cannot meet. Place it on a panel.")})


@app.route("/api/analyze", methods=["POST"])
def analyze():
    """Squint test + value range for any image you already have."""
    f = request.files.get("image")
    if not f:
        return jsonify({"ok": False, "error": "no image"}), 400
    img = Image.open(io.BytesIO(f.read())).convert("RGB")
    # A full car render must have the paint isolated first, or background,
    # tyres and lettering inflate the score past anything meaningful.
    is_render = request.form.get("mode", "render") == "render"
    stem = f"analyze_{int(time.time())}"
    sq = post.squint(img)
    sq.save(OUT / f"{stem}_squint.png")
    return jsonify({"ok": True,
                    "value_range": post.value_range(img, isolate_paint=is_render),
                    "squint_url": f"/out/{stem}_squint.png"})


@app.route("/api/concept/suggest", methods=["POST"])
def concept_suggest():
    """Turn a brief into an editable motif list before anything is generated."""
    body = request.get_json(force=True) or {}
    return jsonify({"ok": True, **concept.suggest(body.get("brief", "")),
                    "cars": [{"id": k, "name": v.split(" with")[0].replace("a ", "", 1)}
                             for k, v in concept.CARS.items()]})


@app.route("/api/concept/wordmark", methods=["POST"])
def concept_wordmark():
    """Stash an uploaded logo so the pack can carry it through untouched."""
    f = request.files.get("image")
    if not f:
        return jsonify({"ok": False, "error": "no image"}), 400
    ext = Path(f.filename or "wordmark.png").suffix.lower() or ".png"
    if ext not in (".png", ".svg", ".webp"):
        return jsonify({"ok": False, "error": "use a PNG, SVG or WebP with transparency"}), 400
    path = OUT / f"_wordmark_{int(time.time())}{ext}"
    f.save(path)
    return jsonify({"ok": True, "file": str(path), "url": f"/out/{path.name}"})


@app.route("/api/concept/start", methods=["POST"])
def concept_start():
    body = request.get_json(force=True) or {}
    provider = body.get("provider", "local")
    if provider == "local" and not comfy.is_up():
        return jsonify({"ok": False, "error": "ComfyUI is not running. Start it first."}), 409
    if not (body.get("brief") or "").strip():
        return jsonify({"ok": False, "error": "write a brief first"}), 400
    if not body.get("render", True) and not body.get("motifs"):
        return jsonify({"ok": False, "error": "nothing to make: enable the render or add a motif"}), 400
    return jsonify({"ok": True, "job": concept.start(body)})


@app.route("/api/concept/job/<job_id>")
def concept_job(job_id):
    j = concept.get(job_id)
    if not j:
        return jsonify({"ok": False, "error": "no such job"}), 404
    return jsonify({"ok": True, **j})


@app.route("/api/concept/palette", methods=["POST"])
def concept_palette():
    """Palette from any render you already have."""
    f = request.files.get("image")
    if not f:
        return jsonify({"ok": False, "error": "no image"}), 400
    img = Image.open(io.BytesIO(f.read()))
    return jsonify({"ok": True, "palette": concept.extract_palette(img)})


# ------------------------------------------------------------ templates / paint

@app.route("/api/templates")
def templates_list():
    return jsonify({"ok": True, "templates": tmpl.list_templates(),
                    "kontext_ready": comfy.kontext_ready()})


@app.route("/api/templates/<slug>")
def templates_info(slug):
    info = tmpl.load_info(slug)
    if not info:
        return jsonify({"ok": False, "error": "no such template"}), 404
    return jsonify({"ok": True, **info})


@app.route("/api/templates/ingest", methods=["POST"])
def templates_ingest():
    """Accept an uploaded PSD, or a path to one already on disk."""
    f = request.files.get("psd")
    if f:
        name = Path(f.filename or "template.psd").name
        if not name.lower().endswith((".psd", ".psb")):
            return jsonify({"ok": False, "error": "upload the .psd from the iRacing paint kit"}), 400
        keep = OUT / "templates" / "_uploads"
        keep.mkdir(parents=True, exist_ok=True)
        path = keep / name
        f.save(path)
    else:
        path = Path((request.get_json(silent=True) or {}).get("path", ""))
        if not path.exists():
            return jsonify({"ok": False, "error": "file not found"}), 400
    try:
        info = tmpl.ingest(path, force=True)
    except Exception as e:
        return jsonify({"ok": False, "error": f"could not read that template: {e}"}), 500
    return jsonify({"ok": True, **info})


@app.route("/api/packs")
def packs_list():
    return jsonify({"ok": True, "packs": paint.list_packs(), "textures": paint.list_textures()})


@app.route("/api/paint/start", methods=["POST"])
def paint_start():
    body = request.get_json(force=True) or {}
    if body.get("base") == "kontext":
        if not comfy.kontext_ready():
            return jsonify({"ok": False, "error": "The Kontext model is not installed yet."}), 409
        if not comfy.is_up():
            return jsonify({"ok": False, "error": "ComfyUI is not running. Start it first."}), 409
    return jsonify({"ok": True, "job": paint.start(body)})


@app.route("/api/paint/job/<job_id>")
def paint_job(job_id):
    j = paint.get(job_id)
    if not j:
        return jsonify({"ok": False, "error": "no such job"}), 404
    return jsonify({"ok": True, **j})


def _already_running(port=4796):
    """Windows lets a second server bind the same port, after which requests
    are split between old and new code at random. Refuse to be the second."""
    import socket
    s = socket.socket()
    s.settimeout(0.5)
    try:
        return s.connect_ex(("127.0.0.1", port)) == 0
    finally:
        s.close()


if __name__ == "__main__":
    if _already_running():
        print("Texture Forge is already running at http://localhost:4796 - "
              "close that window first (or just use it).")
        raise SystemExit(1)
    print("Texture Forge  ->  http://localhost:4796")
    app.run(host="127.0.0.1", port=4796, debug=False, threaded=True)
