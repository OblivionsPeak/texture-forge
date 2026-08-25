"""Livery-tuned FLUX prompt library.

Every preset is written for FLAT ARTWORK, not a photograph. That distinction is
the whole point: asking FLUX for "a photo of X" returns depth-of-field blur,
perspective, corner vignetting and hallucinated watermarks — all of which make
an image useless as a car texture. Asking for flat 2D artwork does not.
"""

# Appended to every prompt. Kills the photographic habits that ruin a texture.
FLAT = (
    "flat 2D digital artwork, orthographic straight-on view, completely flat surface, "
    "evenly lit edge to edge, sharp focus everywhere, uniform brightness, "
    "seamless full-bleed pattern filling the entire frame"
)

# FLUX ignores negatives more than SDXL does, so the positive carries most of
# the load. This still helps at the margins.
NEGATIVE = (
    "photograph, 3D render, car, vehicle, perspective, depth of field, bokeh, blurry, "
    "vignette, dark corners, drop shadow, text, letters, words, watermark, signature, "
    "logo, frame, border, mockup, product shot"
)


def _p(desc, extra=""):
    return f"{desc}, {extra + ', ' if extra else ''}{FLAT}"


PRESETS = [
    {
        "id": "storm",
        "name": "Storm Lightning",
        "hint": "Forked lightning over churning cloud. The look from that render — huge value range, reads at distance.",
        "prompt": _p("violent forked {color} lightning bolts branching across churning near-black storm clouds, "
                     "brilliant glowing electric arcs, deep shadow between strikes, dramatic contrast"),
        "color": "electric violet",
    },
    {
        "id": "nebula",
        "name": "Nebula Swirl",
        "hint": "Van Gogh turbulence. Organic flow with strong light/dark separation.",
        "prompt": _p("swirling turbulent {color} nebula, thick expressive brushstroke vortices, "
                     "glowing bright cores against deep black voids, cosmic dust, Van Gogh starry night energy"),
        "color": "violet and magenta",
    },
    {
        "id": "fracture",
        "name": "Fractured Glass",
        "hint": "Shattered planes with bright fracture lines. Very sharp, very graphic.",
        "prompt": _p("shattered glass fracture pattern, sharp angular shards, brilliant {color} light "
                     "blazing along every crack, near-black facets between, high contrast"),
        "color": "cyan",
    },
    {
        "id": "lava",
        "name": "Cracked Lava",
        "hint": "Molten fissures through cooled black crust.",
        "prompt": _p("cracked volcanic crust, glowing molten {color} magma in deep fissures, "
                     "charred black rock plates, intense heat glow, strong light and dark"),
        "color": "orange and gold",
    },
    {
        "id": "liquid",
        "name": "Liquid Metal",
        "hint": "Flowing chrome ripples. Pairs well with a single accent hue.",
        "prompt": _p("flowing liquid metal, rippling molten chrome waves, mirror-bright highlights, "
                     "deep dark troughs, {color} iridescent sheen across the surface"),
        "color": "violet",
    },
    {
        "id": "ink",
        "name": "Ink in Water",
        "hint": "Billowing smoke plumes. Soft organic shapes, good under numbers.",
        "prompt": _p("billowing {color} ink diffusing through water, soft smoky tendrils and plumes, "
                     "dense black background, luminous wisps, fluid organic movement"),
        "color": "violet and white",
    },
    {
        "id": "circuit",
        "name": "Circuit Grid",
        "hint": "Tech traces. Hard geometry, glowing paths.",
        "prompt": _p("glowing {color} circuit board traces on matte black, intricate right-angle pathways, "
                     "bright illuminated lines, dense technical grid, luminous nodes"),
        "color": "electric blue",
    },
    {
        "id": "camo",
        "name": "High-Contrast Camo",
        "hint": "Camo that survives the squint test — wide value range, not a single hue band.",
        "prompt": _p("bold angular camouflage pattern, large hard-edged geometric patches, "
                     "extreme range from near-white through mid {color} to near-black, "
                     "crisp boundaries, no gradients"),
        "color": "violet",
    },
    {
        "id": "marble",
        "name": "Marble Vein",
        "hint": "Luxury stone. Fine bright veining over a dark field.",
        "prompt": _p("polished marble, fine branching {color} veins threading through deep dark stone, "
                     "luminous mineral striations, subtle depth, elegant"),
        "color": "gold",
    },
    {
        "id": "aurora",
        "name": "Aurora Ribbon",
        "hint": "Sweeping light curtains. Big soft shapes, strong at distance.",
        "prompt": _p("aurora borealis light curtains, sweeping vertical {color} ribbons of luminous gas, "
                     "star-flecked black sky, glowing translucent bands"),
        "color": "violet and teal",
    },
    {
        "id": "carbon",
        "name": "Carbon Weave",
        "hint": "Technical base layer. Best under a graphic, not alone.",
        "prompt": _p("carbon fibre twill weave, tight diagonal interlocking pattern, "
                     "subtle {color} sheen catching the fibres, deep black substrate, crisp repeating texture"),
        "color": "violet",
    },
    {
        "id": "topo",
        "name": "Topographic",
        "hint": "Contour lines. Clean, modern, mirrors beautifully.",
        "prompt": _p("topographic contour map lines, concentric flowing elevation rings, "
                     "fine bright {color} lines on deep dark ground, cartographic precision"),
        "color": "white and violet",
    },
]

BY_ID = {p["id"]: p for p in PRESETS}


def build(preset_id, color=None, extra=None):
    """Return (positive, negative) for a preset with an optional colour override."""
    p = BY_ID.get(preset_id)
    if not p:
        raise KeyError(preset_id)
    text = p["prompt"].replace("{color}", (color or p["color"]).strip())
    if extra:
        text = f"{extra.strip()}, {text}"
    return text, NEGATIVE
