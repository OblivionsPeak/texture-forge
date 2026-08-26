"""First-run setup: find ComfyUI, report what's missing, fetch the model.

The command line was never the real barrier - downloading roughly 16 GB of
weights into exactly the right folder is. This does that, verifies it, and
reports progress, so a new user never opens a terminal or a Hugging Face page.
"""
import hashlib
import json
import os
import shutil
import struct
import threading
import time
import urllib.request
from pathlib import Path

from . import comfy

UA = {"User-Agent": "TextureForge/0.2 (+https://github.com/OblivionsPeak/texture-forge)"}

# The all-in-one Comfy-Org checkpoint: UNet + both text encoders + VAE in one
# file (1442 tensors). One download into one folder, and crucially it is NOT
# gated - Black Forest Labs' own repo returns 401 without an account and an
# accepted licence, which is a wall a non-technical user simply stops at.
CHECKPOINT = {
    "name": comfy.CHECKPOINT,
    "url": "https://huggingface.co/Comfy-Org/flux1-dev/resolve/main/flux1-dev-fp8.safetensors",
    "folder": "checkpoints",
    "approx_gb": 16.1,
    # No pinned hash: this is the one file not verified against a known-good
    # local copy. It is validated structurally instead - see verify_safetensors.
    "sha256": None,
    "expect_tensors": 1442,
}

# Split-layout files, each verified byte-for-byte against a working install.
SPLIT = [
    {"name": comfy.CLIP_L, "folder": "text_encoders", "approx_gb": 0.24,
     "url": "https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/clip_l.safetensors",
     "sha256": "660c6f5b1abae9dc498ac2d21e1347d2abdb0cf6c0c0c8576cd796491d9a6cdd"},
    {"name": comfy.T5, "folder": "text_encoders", "approx_gb": 4.8,
     "url": "https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp8_e4m3fn_scaled.safetensors",
     "sha256": "a498f0485dc9536735258018417c3fd7758dc3bccc0a645feaa472b34955557a"},
    {"name": comfy.VAE, "folder": "vae", "approx_gb": 0.32,
     "url": "https://huggingface.co/ffxvs/vae-flux/resolve/main/ae.safetensors",
     "sha256": "afc8e28272cd15db3919bacdb6918ce9c1ed22e96cb12c4d5ed0fba823529e38"},
]

PROGRESS = {"active": False, "file": None, "done": 0, "total": 0,
            "percent": 0, "speed": 0, "message": "", "error": None, "finished": False}
_lock = threading.Lock()


# ------------------------------------------------------------------ checks

def free_disk_gb(path):
    try:
        return shutil.disk_usage(str(path)).free / 2**30
    except Exception:
        return None


def status():
    """Everything the Setup panel needs to tell someone what to do next."""
    d = comfy.COMFY_DIR
    found = (d / "main.py").exists()
    lay = comfy.layout() if found else None
    venv = found and comfy.python_exe() != "python"

    missing = []
    if found and not lay:
        missing.append({"name": CHECKPOINT["name"], "gb": CHECKPOINT["approx_gb"],
                        "folder": CHECKPOINT["folder"]})

    return {
        "comfy_found": found,
        "comfy_dir": str(d),
        "comfy_venv": venv,
        "layout": lay,
        "model_ready": lay is not None,
        "missing": missing,
        "free_disk_gb": round(free_disk_gb(d.anchor or d) or 0, 1),
        "running": comfy.is_up(),
        "progress": dict(PROGRESS),
    }


def verify_safetensors(path, expect_tensors=None):
    """Structural check: does it parse, and does it hold what it should?

    A truncated or HTML-error-page download is the common failure, and both are
    caught here long before ComfyUI reports something cryptic.
    """
    try:
        with open(path, "rb") as f:
            n = struct.unpack("<Q", f.read(8))[0]
            if n <= 0 or n > 100_000_000:
                return False, "header length is implausible - download is corrupt"
            hdr = json.loads(f.read(n))
        keys = [k for k in hdr if k != "__metadata__"]
        if expect_tensors and len(keys) != expect_tensors:
            return False, f"expected {expect_tensors} tensors, found {len(keys)}"
        return True, f"{len(keys)} tensors"
    except Exception as e:
        return False, f"not a valid safetensors file ({type(e).__name__})"


# --------------------------------------------------------------- download

def _set(**kw):
    with _lock:
        PROGRESS.update(kw)


def download(spec, dest_dir):
    """Stream one file to disk with progress, then verify before accepting it."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    final = dest_dir / spec["name"]
    part = dest_dir / (spec["name"] + ".part")

    _set(file=spec["name"], done=0, total=0, percent=0, message="connecting…")
    req = urllib.request.Request(spec["url"], headers=UA)
    with urllib.request.urlopen(req, timeout=120) as r:
        total = int(r.headers.get("Content-Length") or 0)
        _set(total=total, message="downloading")
        h = hashlib.sha256()
        done = 0
        t0 = time.time()
        with open(part, "wb") as f:
            while True:
                chunk = r.read(1 << 22)
                if not chunk:
                    break
                f.write(chunk)
                h.update(chunk)
                done += len(chunk)
                el = max(0.001, time.time() - t0)
                _set(done=done, speed=done / el,
                     percent=round(100 * done / total, 1) if total else 0)

    if spec.get("sha256") and h.hexdigest() != spec["sha256"]:
        part.unlink(missing_ok=True)
        raise RuntimeError(f"{spec['name']} failed its checksum - the download was corrupt")

    ok, detail = verify_safetensors(part, spec.get("expect_tensors"))
    if not ok:
        part.unlink(missing_ok=True)
        raise RuntimeError(f"{spec['name']}: {detail}")

    part.replace(final)
    return final, detail


def install_model(kind="checkpoint"):
    """Background worker. Returns immediately; poll status() for progress."""
    if PROGRESS["active"]:
        return False, "a download is already running"
    if not (comfy.COMFY_DIR / "main.py").exists():
        return False, f"ComfyUI not found. Install it, or set COMFYUI_DIR."

    specs = [CHECKPOINT] if kind == "checkpoint" else SPLIT
    need = sum(s["approx_gb"] for s in specs)
    free = free_disk_gb(comfy.COMFY_DIR.anchor or comfy.COMFY_DIR)
    if free is not None and free < need + 2:
        return False, f"needs about {need:.0f} GB free, only {free:.0f} GB available"

    def work():
        _set(active=True, finished=False, error=None, message="starting")
        try:
            for spec in specs:
                dest = comfy.COMFY_DIR / "models" / spec["folder"]
                if (dest / spec["name"]).exists():
                    continue
                _, detail = download(spec, dest)
                _set(message=f"{spec['name']} verified ({detail})")
            _set(message="model ready", finished=True, percent=100)
        except Exception as e:
            _set(error=str(e), message="failed")
        finally:
            _set(active=False)

    threading.Thread(target=work, daemon=True).start()
    return True, f"downloading about {need:.0f} GB"
