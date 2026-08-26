"""Image backends.

Local FLUX is the default and the only one that is free and offline. Cloud
backends are opt-in, cost money per image, and send the prompt off the machine -
so they are labelled as such everywhere rather than quietly swapped in.

Adding one means implementing generate() and appending to PROVIDERS.
"""
import base64
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

from . import comfy

CONFIG_PATH = Path(__file__).parent.parent / "config.json"
OUT_DIR = Path(__file__).parent.parent / "out"


def load_config():
    """Local, gitignored. Keys never enter the repo."""
    try:
        return json.loads(CONFIG_PATH.read_text("utf-8"))
    except Exception:
        return {}


def save_config(cfg):
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2), "utf-8")


def api_key(name):
    import os
    cfg = load_config()
    return (cfg.get(name) or os.environ.get(name.upper()) or "").strip()


# ------------------------------------------------------------------- local

def generate_local(prompt, negative, width, height, seed, steps=20, guidance=3.5, **_):
    if not comfy.is_up():
        raise RuntimeError("ComfyUI is not running. Press Start engine.")
    files, err = comfy.generate(prompt, negative, width, height, seed, steps, guidance)
    if err:
        raise RuntimeError(err)
    return files[0]


# ------------------------------------------------------------------ openai

# gpt-image-2 takes arbitrary WxH with both sides divisible by 16, but anything
# above 2560x1440 is flagged experimental, so the offered sizes stay inside the
# well-trodden range and post-processing scales to 2048 as before.
OPENAI_SIZES = ["1024x1024", "1536x1536", "2048x2048"]


def _flatten_negative(prompt, negative):
    """Cloud image APIs have no negative prompt field.

    FLUX takes a separate negative conditioning; gpt-image-2 is prompt-only, so
    the exclusions have to become instructions inside the prompt. Dropping them
    is not an option - they are what keeps a vignette or a watermark out.
    """
    if not negative:
        return prompt
    return (f"{prompt}\n\n"
            f"Strictly avoid all of the following: {negative}. "
            f"The result must be a flat repeating surface texture with no border, "
            f"no framing, no subject isolated on a background, and no text of any kind.")


def generate_openai(prompt, negative, width, height, seed=None, quality="high", **_):
    key = api_key("openai_api_key")
    if not key:
        raise RuntimeError("No OpenAI API key set. Add one in the Setup tab. "
                           "Note a ChatGPT subscription does not include API access - "
                           "the key comes from platform.openai.com and is billed separately.")

    size = f"{width}x{height}"
    if size not in OPENAI_SIZES:
        size = "1024x1024"

    body = json.dumps({
        "model": "gpt-image-2",
        "prompt": _flatten_negative(prompt, negative),
        "size": size,
        "quality": quality,
        "n": 1,
    }).encode()

    req = urllib.request.Request(
        "https://api.openai.com/v1/images/generations", data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            payload = json.loads(r.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        try:
            detail = json.loads(detail)["error"]["message"]
        except Exception:
            detail = detail[:300]
        if e.code == 401:
            raise RuntimeError(f"OpenAI rejected the key: {detail}")
        if e.code == 429:
            raise RuntimeError(f"Rate limited or out of credit: {detail}")
        if e.code == 400:
            raise RuntimeError(f"Request refused: {detail}")
        raise RuntimeError(f"OpenAI error {e.code}: {detail}")

    item = (payload.get("data") or [{}])[0]
    if item.get("b64_json"):
        raw = base64.b64decode(item["b64_json"])
    elif item.get("url"):
        with urllib.request.urlopen(item["url"], timeout=120) as r:
            raw = r.read()
    else:
        raise RuntimeError("OpenAI returned no image data")

    OUT_DIR.mkdir(exist_ok=True)
    path = OUT_DIR / f"_openai_{int(time.time())}.png"
    path.write_bytes(raw)

    usage = payload.get("usage") or {}
    if usage:
        print(f"  gpt-image-2 usage: {usage}")
    return path


def test_openai():
    """Cheap credential check - lists models rather than buying an image."""
    key = api_key("openai_api_key")
    if not key:
        return False, "no key set"
    req = urllib.request.Request("https://api.openai.com/v1/models",
                                 headers={"Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            ids = {m["id"] for m in json.loads(r.read()).get("data", [])}
        if "gpt-image-2" in ids:
            return True, "key works and gpt-image-2 is available"
        return True, ("key works, but gpt-image-2 is not listed for this account - "
                      "it may need a verified organisation")
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}: {e.read().decode('utf-8','replace')[:200]}"
    except Exception as e:
        return False, str(e)


PROVIDERS = {
    "local": {
        "name": "FLUX (local)", "fn": generate_local, "cloud": False,
        "hint": "Free, offline, needs the engine running. About 40s.",
        "sizes": ["1024", "1216", "1408"],
    },
    "openai": {
        "name": "GPT Image 2", "fn": generate_openai, "cloud": True,
        "hint": "Cloud. Costs roughly $0.01-0.21 per image and sends the prompt to OpenAI.",
        "sizes": ["1024", "1536", "2048"],
    },
}


def generate(provider, **kw):
    p = PROVIDERS.get(provider or "local")
    if not p:
        raise RuntimeError(f"unknown provider {provider}")
    return p["fn"](**kw)
