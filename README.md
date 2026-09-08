# Texture Forge

Flat livery textures from local FLUX, plus the silhouette layers diffusion does
badly. Browser UI on `http://localhost:4796`.

**Everything runs locally**: free, offline, no keys, nothing leaves the
machine. There is one engine, FLUX through ComfyUI, on purpose.

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

## Six tabs

**Textures** — two ways in.

*Describe it* takes any subject in plain language. Raw free text is what produces
the failures above, so a subject is compiled through a motif table into one of
five treatments: **Surface**, **Energy**, **Marks**, **Silhouette**,
**Atmosphere**. "A dragon" becomes overlapping reptilian scales, or roaring fire,
or raking claw slashes — never a dragon standing in a field. Wolf becomes fur,
engine becomes machined plating. Unmatched subjects get a generic surface
treatment rather than an error, and the compiled prompt is shown under every
result so the translation is visible rather than magic.

*Artwork* is the opposite of the other two: a whole scene or illustration
with a subject — a sunset over mesas, a lone rider — at door, hood or wing
end-plate proportions, in photo, painted, vector or vintage-poster medium. It
does not tile and is not meant to; it is the one mode that gives you a
*picture*, for placing on a single panel in Clearcoat. Typing a landscape into
*Describe it* gives you the landscape's rock texture instead, by design.

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

## Concept packs

The **Concept** tab is the "ask a chatbot for a mock-up" workflow, run locally.
One brief — *Day of the Dead, inspired by Operation Motorsport* — produces:

1. a **side-profile studio render** of the car wearing the concept, for pitching;
2. **every motif as its own alpha-cut PNG**, ready for Clearcoat;
3. the **palette** the render actually used, as hex swatches you click to copy;
4. a **manifest and a zip** so the whole thing travels as one file.

Known themes (Day of the Dead, Remembrance, Japanese, Halloween, Cosmic,
Holiday, Pride, Tactical) fill the motif list; anything else gets three generic
lines to rewrite. The list is editable before anything is generated.

Two things are deliberate. **Lettering is never generated**: diffusion melts it,
so the local render reserves a blank white door panel and the real wordmark is
dropped in as a file and shipped through the pack untouched. And **the render
is a pitch image, not a paint file**: it shows one
side of a 3D car, the template is a flattened UV sheet, and there is no honest
projection between them without the car's mesh. Placement stays in Clearcoat.

Measured on the first run (local FLUX, 4 motifs, 1408×1024 render): about five
minutes total. The corner flood-fill cutout leaves a backdrop disc behind when
the model paints the subject on a coloured circle, and "papel picado banner"
came back as another skull — both prompt-side fixes, not pipeline ones.

Two later fixes. "Photo realistic X" under the Vinyl style fought itself — the
style wrapper asked for flat vector art and won — so a subject that says photo
or realistic now takes the Photo style. And sticker-style subjects come with a
pale outline plus a tinted shadow that the flood fill stops at; the cutout now
samples the rim colour where the subject meets the background and peels
inward while pixels stay pale, so the decal lands on a dark panel without a
white halo. A marigold's orange edge fails the paleness test and is left alone.

## Painting the real template

The **Paint** tab produces a finished paint sheet for a
specific iRacing car, exported as TGA. Nothing is traced by hand.

**Drop in the car's paint-kit PSD.** Four hidden layers inside every kit carry
what a generator needs, and they are read raw (they ship switched off):

| Layer | What it gives |
|---|---|
| `Mask` | the paintable area (inverted: the layer marks dead space) |
| `Wire` | the polygon mesh — its density is a free curvature map |
| `Sponsor Blocks` / `Sponsor` | where iRacing's artists say a sponsor decal sits flat |
| `Number Blocks` / `Numbers` | where the race number goes |

Checked on four kits (992 GT3 R, M4 GT4, AMG GT3 2020, Dallara P217): all four
yielded 8–11 sponsor zones and 3–6 number zones. A kit with no block layers
falls back to flat areas found from the curvature map.

**Pick a base.** *Kontext* sends the clean shaded sheet to FLUX Kontext dev with
the brief and it paints straight onto the sheet, keeping every part where the
template put it — about 75 s on the 5070. Measured honestly, it does not
understand the car: it fills each panel with pattern centred on that panel,
and given a concept render as a second reference it draws the motifs and
throws the sheet layout away. It is a base, not a design. Motifs, wordmark and
numbers are placed on top by the zone logic below, which is where the design
comes from. *Texture* stretches or tiles anything from the Textures tab. *Colour* is a flat
fill.

**Add a concept pack and a number.** The wordmark lands on the two flattest wide
sponsor zones, motifs fill the rest, the number is rendered into every number
zone. Placements on curved zones are flagged.

**Export.** `car.tga`, a derived `car_spec.tga`, `paint.png` for Clearcoat, and a
shaded preview. The template still cannot say which panel edges meet in 3D, so
seams are checked in the sim, not here.

Feeding an edit model the composite (with the faint mesh and the kit's decals)
made it paint the mesh lines and the Porsche crest into the livery. The clean
sheet — body layer only, dead space dark — fixed that in one run.

The commercial "paint your real template" tools most plausibly run a hosted
image-edit model with the flattened sheet as input, priced per render into
credits. That route was tried here and it does reproduce a concept render onto
the sheet panel by panel; it was removed again because it needs an API key
and sends the template off the machine, which this tool does not do. Kontext ships as a split
UNet (`flux1-dev-kontext_fp8_scaled.safetensors`, 11.9 GB) and shares the FLUX
dev text encoders and VAE.

**Windows lets two servers bind port 4796 at once**, after which requests are
split between old and new code at random. That presented as "the new tab 404s"
and "auto-fill stopped working". The app now refuses to start if something
already answers on the port, and the launcher reinstalls dependencies whenever
`requirements.txt` changes.

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

## Engine

One engine: FLUX.1-dev through a local ComfyUI, plus FLUX Kontext dev for the
Paint tab's template base. Both are free, offline and hold VRAM only while the
engine is running — press **Stop** before racing. No API keys anywhere.

## Where this sits

- **SimTex Pro** — 552 repeating patterns, already bridges to Clearcoat.
- **Texture Forge** — one-off organic artwork and crisp procedural shapes.
- **Clearcoat** — assembly, numbers, sponsors, TGA export.

Never let diffusion draw numbers or sponsor logos. It melts them every time.
Composite those in Clearcoat over generated art.
