"""Headless ComfyUI driver for FLUX.1-dev still images.

Talks to the local ComfyUI over its HTTP API: queue an API-format workflow at
POST /prompt, poll /history/<id>, then read the file out of ComfyUI/output.

ComfyUI holds VRAM while it runs, which iRacing needs, so the server is started
on demand and can be shut down again from the UI.
"""
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

COMFY_DIR = Path(os.environ.get("COMFYUI_DIR", r"C:\Users\onegu\ComfyUI"))
HOST = "127.0.0.1"
PORT = 8188
BASE = f"http://{HOST}:{PORT}"

UNET = "flux1-dev-fp8.safetensors"
CLIP_L = "clip_l.safetensors"
T5 = "t5xxl_fp8_e4m3fn_scaled.safetensors"
VAE = "ae.safetensors"


def _get(path, timeout=5):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
        return json.loads(r.read())


def is_up(timeout=3):
    try:
        _get("/system_stats", timeout)
        return True
    except Exception:
        return False


def vram():
    try:
        d = _get("/system_stats")
        dev = (d.get("devices") or [{}])[0]
        free = dev.get("vram_free")
        total = dev.get("vram_total")
        if free and total:
            return {"free_gb": round(free / 2**30, 1), "total_gb": round(total / 2**30, 1),
                    "name": dev.get("name", "")}
    except Exception:
        pass
    return None


def python_exe():
    """ComfyUI's own interpreter.

    It ships a venv holding torch+cu128 and sqlalchemy; the system Python has
    neither, so launching with a bare "python" dies on import before it ever
    reaches the model loader.
    """
    for rel in ("venv/Scripts/python.exe", "venv/bin/python",
                ".venv/Scripts/python.exe", ".venv/bin/python"):
        p = COMFY_DIR / rel
        if p.exists():
            return str(p)
    return "python"


def start(wait=240):
    """Launch ComfyUI in the background and wait for it to answer."""
    if is_up():
        return True, "already running"
    main = COMFY_DIR / "main.py"
    if not main.exists():
        return False, f"ComfyUI not found at {COMFY_DIR}"
    flags = ["--listen", HOST, "--port", str(PORT)]
    creation = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    subprocess.Popen(
        [python_exe(), str(main), *flags],
        cwd=str(COMFY_DIR),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=creation,
    )
    deadline = time.time() + wait
    while time.time() < deadline:
        if is_up(2):
            return True, "started"
        time.sleep(2)
    return False, f"ComfyUI did not answer within {wait}s"


def stop():
    """Free the VRAM. ComfyUI has no clean shutdown endpoint, so this is blunt."""
    if not is_up():
        return True, "not running"
    try:
        urllib.request.urlopen(BASE + "/free",
                               data=json.dumps({"unload_models": True, "free_memory": True}).encode(),
                               timeout=10)
    except Exception:
        pass
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/FI", "WINDOWTITLE eq ComfyUI*"],
                       capture_output=True)
        # Fall back to killing the python process holding port 8188.
        try:
            out = subprocess.run(["netstat", "-ano", "-p", "TCP"],
                                 capture_output=True, text=True).stdout
            for line in out.splitlines():
                if f":{PORT}" in line and "LISTENING" in line:
                    pid = line.split()[-1]
                    subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)
        except Exception:
            pass
    return True, "stopped"


def build_workflow(prompt, negative, width, height, seed, steps=20, guidance=3.5):
    """Minimal FLUX.1-dev graph in API format.

    FLUX runs through a plain KSampler at cfg=1.0 with guidance supplied by the
    FluxGuidance node instead — pushing cfg above 1 burns the image out.
    """
    return {
        "1": {"class_type": "UNETLoader",
              "inputs": {"unet_name": UNET, "weight_dtype": "fp8_e4m3fn"}},
        "2": {"class_type": "DualCLIPLoader",
              "inputs": {"clip_name1": CLIP_L, "clip_name2": T5, "type": "flux"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": VAE}},
        "4": {"class_type": "CLIPTextEncode",
              "inputs": {"text": prompt, "clip": ["2", 0]}},
        "5": {"class_type": "CLIPTextEncode",
              "inputs": {"text": negative or "", "clip": ["2", 0]}},
        "6": {"class_type": "FluxGuidance",
              "inputs": {"conditioning": ["4", 0], "guidance": guidance}},
        "7": {"class_type": "EmptySD3LatentImage",
              "inputs": {"width": width, "height": height, "batch_size": 1}},
        "8": {"class_type": "KSampler",
              "inputs": {"model": ["1", 0], "positive": ["6", 0], "negative": ["5", 0],
                         "latent_image": ["7", 0], "seed": seed, "steps": steps,
                         "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple",
                         "denoise": 1.0}},
        "9": {"class_type": "VAEDecode",
              "inputs": {"samples": ["8", 0], "vae": ["3", 0]}},
        "10": {"class_type": "SaveImage",
               "inputs": {"images": ["9", 0], "filename_prefix": "texforge"}},
    }


def queue(workflow):
    body = json.dumps({"prompt": workflow}).encode()
    req = urllib.request.Request(BASE + "/prompt", data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())["prompt_id"], None
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:500]
        return None, f"ComfyUI rejected the workflow: {detail}"
    except Exception as e:
        return None, str(e)


def wait_for(prompt_id, timeout=600, poll=2.0):
    """Block until the job appears in history, then return output file paths."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            hist = _get(f"/history/{prompt_id}", timeout=10)
        except Exception:
            time.sleep(poll)
            continue
        entry = hist.get(prompt_id)
        if entry:
            status = entry.get("status", {})
            if status.get("status_str") == "error":
                msgs = [m for m in status.get("messages", []) if m and m[0] == "execution_error"]
                return None, (json.dumps(msgs[-1][1])[:500] if msgs else "execution error")
            files = []
            for out in entry.get("outputs", {}).values():
                for img in out.get("images", []):
                    files.append(COMFY_DIR / img.get("type", "output") / img.get("subfolder", "") / img["filename"])
            if files:
                return files, None
        time.sleep(poll)
    return None, f"timed out after {timeout}s"


def generate(prompt, negative, width, height, seed, steps=20, guidance=3.5, timeout=600):
    wf = build_workflow(prompt, negative, width, height, seed, steps, guidance)
    pid, err = queue(wf)
    if err:
        return None, err
    return wait_for(pid, timeout=timeout)
