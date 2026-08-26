# Texture Forge

Flat livery textures from local FLUX, plus the silhouette layers diffusion does
badly. Browser UI on `http://localhost:4796`.

**Local FLUX is the default**: free, offline, no keys, nothing leaves the
machine. A cloud engine can be selected instead — see [Engines](#engines) — and
that does send your prompt to a third party and cost money per image, so it is
opt-in and labelled everywhere it appears.

**Windows:** double-click **`Start Texture Forge.bat`**.
**macOS / Linux:** run `./start-texture-forge.sh`.

Either one creates a private Python environment, installs what it needs, starts
the app and opens it in your browser. No terminal required after that.

If you would rather do it by hand:

```bash
pip install -r requirements.txt
python app.py
```

## Setup

Texture Forge is a client. It does not ship a model — it drives a **ComfyUI**
install you provide, so you need that working first.

### 1. Requirements

- **A CUDA GPU with 12 GB VRAM or more.** Developed on an RTX 5070 (12 GB).
  1024×1024 fits comfortably; 1408 may run out of memory.
- Blackwell cards (50-series) need a **cu128** torch build.
- ~24 GB of disk for the model files.

### 2. ComfyUI

Install from [comfyanonymous/ComfyUI](https://github.com/comfyanonymous/ComfyUI)
and run it once on its own before going further — that first run creates the
venv holding torch, which Texture Forge then launches it with. A system Python
usually has neither torch nor sqlalchemy and dies on import.

**You do not need to configure a path.** Texture Forge searches the usual
install locations. If yours is somewhere unusual, set `COMFYUI_DIR` to point at
it and that wins:

```bash
set COMFYUI_DIR=D:\path\to\ComfyUI        # Windows
export COMFYUI_DIR=/path/to/ComfyUI       # macOS / Linux
```

### 3. The FLUX model

**Open the Setup tab and press "Download model".** It fetches the ~16 GB
all-in-one FLUX.1-dev checkpoint into the right folder, shows progress, and
verifies the result before accepting it. Nothing else to do.

That checkpoint bundles the UNet, both text encoders and the VAE in one file
(1442 tensors), which is why setup is one download rather than four. It is also
**not gated** — Black Forest Labs' own repo returns 401 without an account and
an accepted licence, which is exactly the wall a non-technical user stops at.

Texture Forge supports both layouts and detects which you have:

| Layout | Files |
|---|---|
| **Checkpoint** (what Setup installs) | `flux1-dev-fp8.safetensors` in `models/checkpoints/` |
| **Split** (many existing installs) | UNet in `models/diffusion_models/`, `clip_l` + `t5xxl_fp8_e4m3fn_scaled` in `models/text_encoders/`, `ae.safetensors` in `models/vae/` |

Downloads are checked two ways: a pinned SHA256 where the file was verified
byte-for-byte against a known-good install, and a structural check that the
safetensors header parses and holds the expected tensor count. A truncated file,
or an HTML error page saved under a `.safetensors` name, is caught here rather
than surfacing later as something cryptic from ComfyUI.

Restart ComfyUI after the download.

### 4. Licensing

**FLUX.1-dev is released under a non-commercial licence.** Texture Forge itself
is MIT and carries no model weights, but anything you generate is governed by
[Black Forest Labs' terms](https://huggingface.co/black-forest-labs/FLUX.1-dev).
Read them before putting output on a paid commission.

Swapping in a permissively licensed model is a matter of editing the four
constants at the top of `forge/comfy.py` and adjusting the workflow graph.

### 5. Check it works

The **Setup** tab shows a checklist: ComfyUI found, its venv, the model, free
disk, engine state. Anything red tells you what to do about it.

Then press **Start engine** in the header. The dot goes green and reports free
VRAM once ComfyUI answers — roughly 40 seconds.

The **Silhouettes** and **Squint check** tabs need none of this and work with no
GPU at all.

## The problem it solves

Ask an image model for "a purple lightning race car" and you get a *picture of a
car*: the artwork is wrapped in perspective onto 3D bodywork, so there is no way
to get it onto an iRacing template. Ask for "a photo of lightning" and you get
depth-of-field blur, a corner vignette, and — verified on a real generation from
this machine's own history — a hallucinated watermark reading
`© Kabiyripr es. 2012`.

Every preset here is written for **flat 2D artwork, orthographic, evenly lit,
no depth of field, no vignette, no text**. That single change is the difference
between a nice picture and a usable texture.

## Four tabs

**Textures** — two ways in.

*Describe it* takes any subject in plain language. Raw free text is what produces
the failures above, so a subject is compiled through a motif table into one of
five treatments: **Surface**, **Energy**, **Marks**, **Silhouette**,
**Atmosphere**. "A dragon" becomes overlapping reptilian scales, or roaring fire,
or raking claw slashes — never a dragon standing in a field. Wolf becomes fur,
engine becomes machined plating. Unmatched subjects get a generic surface
treatment rather than an error, and the compiled prompt is shown under every
result so the translation is visible rather than magic.

*Presets* gives 12 ready-made looks (storm lightning, nebula swirl, fractured
glass, cracked lava, liquid metal, ink in water, circuit grid, high-contrast
camo, marble, aurora, carbon weave, topographic).

Colour is a plain-language field because FLUX reads "electric violet", not
`#7B2FBE`. Output is 2048×2048, ready to drop into Clearcoat as a Custom Image
layer. About 55 s per texture at 1024 on a 12 GB card.

**Silhouettes** — mountain ridgelines, pine treelines, city skylines and speed
stripes, drawn mathematically rather than generated. Diffusion gives these mushy
asymmetric edges that won't mirror and go soft when scaled. Drawn, they're crisp
at any size, horizontally seamless so they wrap the car, and pure alpha so you
recolour them in Clearcoat without regenerating anything.

**Squint check** — drop in any render and see what it looks like at track
distance, with a measured value range.

**Setup** — a checklist of what is and isn't in place, and the model downloader.

## Value range, and why it is the number that matters

Hue vanishes with distance before brightness does. A design whose patches all
share one brightness reads as a single flat mass on a moving car however good it
looks up close. Measured on real examples:

| Image | Value range | Verdict |
|---|---|---|
| Purple camo late model | **31** | reads as one solid colour on track |
| AI storm-livery concept | **91** | weak, but ~3× the camo |
| Storm Lightning preset | **107** | good — holds at mid distance |

**On a car render the paint is isolated first.** This matters more than it
sounds: measured naively, the camo car scores 199 — "excellent" — because the
studio backdrop, black tyres and white sidewall lettering span nearly the full
luminance range. The livery itself is flat. Isolating the dominant hue band
gives 31, which matches what the squint test plainly shows. A metric that rates
a provably-invisible livery as excellent is worse than no metric.

## ComfyUI

Uses `flux1-dev-fp8` with `clip_l` + `t5xxl_fp8` and the `ae` VAE, driven over
the HTTP API — queue at `POST /prompt`, poll `/history/<id>`. The Start/Stop
buttons manage the server.

It launches ComfyUI through **its own venv** (`ComfyUI/venv/Scripts/python.exe`
or `venv/bin/python`), not the system interpreter — a system Python typically has
neither torch nor sqlalchemy, so a bare `python main.py` dies on import long
before the model loader. ComfyUI itself is located by searching the usual install
paths, with `COMFYUI_DIR` as an override.

**Stop the engine before racing.** ComfyUI holds ~8 GB of VRAM that iRacing
wants. The Stop button frees it; restarting takes about 40 seconds.

## Engines

| Engine | Cost | Notes |
|---|---|---|
| **FLUX (local)** | free | Default. Offline, ~40 s, needs a 12 GB GPU and the engine running. |
| **GPT Image 2** | ~$0.01 low / $0.05 medium / $0.21 high per image | Cloud. Sends the prompt to OpenAI. Generates up to 2048² directly. |

The key goes in the **Setup** tab and is stored in `config.json`, which is
gitignored and never committed. `OPENAI_API_KEY` in the environment also works.

**A ChatGPT subscription does not include API access.** They are separate
products with separate billing. The key comes from `platform.openai.com` and
needs its own pay-as-you-go credit.

Two behavioural differences worth knowing. Cloud image APIs have **no negative
prompt field**, so the exclusions that keep vignettes and watermarks out are
folded into the prompt as explicit instructions instead. And the motif compiler
matters less on a cloud model — it exists because FLUX paints the noun rather
than its texture, and stronger instruction-following needs less hand-holding.

## Where this sits

- **SimTex Pro** — 552 repeating patterns, already bridges to Clearcoat.
- **Texture Forge** — one-off organic artwork and crisp procedural shapes.
- **Clearcoat** — assembly, numbers, sponsors, TGA export.

Never let diffusion draw numbers or sponsor logos. It melts them every time.
Composite those in Clearcoat over generated art.
