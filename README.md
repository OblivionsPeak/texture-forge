# Texture Forge

Flat livery textures from local FLUX, plus the silhouette layers diffusion does
badly. Browser UI on `http://localhost:4796`. Nothing leaves the machine, no API
keys, no cost per image.

```bash
pip install -r requirements.txt
python app.py
```

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

## Three tabs

**Textures** — 12 FLUX presets (storm lightning, nebula swirl, fractured glass,
cracked lava, liquid metal, ink in water, circuit grid, high-contrast camo,
marble, aurora, carbon weave, topographic). Colour is a plain-language field
because FLUX reads "electric violet", not `#7B2FBE`. Output is 2048×2048, ready
to drop into Clearcoat as a Custom Image layer. About 55 s per texture at 1024
on a 5070.

**Silhouettes** — mountain ridgelines, pine treelines, city skylines and speed
stripes, drawn mathematically rather than generated. Diffusion gives these mushy
asymmetric edges that won't mirror and go soft when scaled. Drawn, they're crisp
at any size, horizontally seamless so they wrap the car, and pure alpha so you
recolour them in Clearcoat without regenerating anything.

**Squint check** — drop in any render and see what it looks like at track
distance, with a measured value range.

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

It launches ComfyUI through **its own venv** (`ComfyUI/venv/Scripts/python.exe`),
not the system interpreter. The system Python here has neither torch nor
sqlalchemy, so a bare `python main.py` dies on import long before the model
loader.

**Stop the engine before racing.** ComfyUI holds ~8 GB of VRAM that iRacing
wants. The Stop button frees it; restarting takes about 40 seconds.

## Where this sits

- **SimTex Pro** — 552 repeating patterns, already bridges to Clearcoat.
- **Texture Forge** — one-off organic artwork and crisp procedural shapes.
- **Clearcoat** — assembly, numbers, sponsors, TGA export.

Never let diffusion draw numbers or sponsor logos. It melts them every time.
Composite those in Clearcoat over generated art.
