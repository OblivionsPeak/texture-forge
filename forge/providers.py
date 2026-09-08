"""Image backend: local FLUX through ComfyUI. Free, offline, no keys.

Kept as a thin layer so a second backend could be added later by implementing
generate() and appending to PROVIDERS - but there is exactly one, on purpose.
Nothing here leaves the machine.
"""
from . import comfy


def generate_local(prompt, negative, width, height, seed, steps=20, guidance=3.5, **_):
    if not comfy.is_up():
        raise RuntimeError("ComfyUI is not running. Press Start engine.")
    files, err = comfy.generate(prompt, negative, width, height, seed, steps, guidance)
    if err:
        raise RuntimeError(err)
    return files[0]


PROVIDERS = {
    "local": {
        "name": "FLUX (local)", "fn": generate_local, "cloud": False,
        "hint": "Free, offline, needs the engine running. About 40s.",
        "sizes": ["1024", "1216", "1408"],
    },
}


def generate(provider, **kw):
    p = PROVIDERS.get(provider or "local")
    if not p:
        raise RuntimeError(f"unknown provider {provider}")
    return p["fn"](**kw)
