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

from forge import comfy, post, prompts, setup as fsetup, silhouette

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
        "shapes": [{"id": k, "name": v["name"], "hint": v["hint"], "seamless": v["seamless"]}
                   for k, v in silhouette.SHAPES.items()],
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


def _finish(img, body, stem):
    """Post-process, save, measure, and return the payload the UI needs."""
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


@app.route("/api/generate", methods=["POST"])
def generate():
    body = request.get_json(force=True) or {}
    preset = body.get("preset", "storm")
    if not comfy.is_up():
        return jsonify({"ok": False, "error": "ComfyUI is not running. Start it first."}), 409
    try:
        if body.get("freeform"):
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
    files, err = comfy.generate(pos, neg, w, h, seed,
                                steps=int(body.get("steps", 20)),
                                guidance=float(body.get("guidance", 3.5)))
    if err:
        return jsonify({"ok": False, "error": err}), 500

    img = Image.open(files[0])
    stem = f"{preset}_{seed}_{int(time.time())}"
    payload = _finish(img, body, stem)
    payload.update({"ok": True, "seed": seed, "prompt": pos})
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


if __name__ == "__main__":
    print("Texture Forge  ->  http://localhost:4796")
    app.run(host="127.0.0.1", port=4796, debug=False, threaded=True)
