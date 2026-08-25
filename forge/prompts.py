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


# ---------------------------------------------------------------- free-form

# Ask FLUX for "a dragon" and it paints a dragon: one creature, in perspective,
# on a landscape, with a horizon and a vignette. Useless on a car. What you
# actually want from "dragon" is its SURFACE - overlapping scales - or its
# ENERGY, or the marks it leaves. These treatments do that translation.
TREATMENTS = {
    "surface": {
        "name": "Surface",
        "hint": "The thing's skin, tiled edge to edge. Scales, hide, bark, plating.",
        "template": "extreme close-up of tightly packed {motif} filling the entire "
                    "frame, {color} tones, deep shadow between each one, sharp "
                    "raking light picking out every edge",
    },
    "energy": {
        "name": "Energy",
        "hint": "What it emits. Fire, lightning, plasma, glow.",
        "template": "violent {energy} erupting across the whole frame, brilliant "
                    "glowing {color} cores against near-black, intense contrast, "
                    "streaming filaments and sparks",
    },
    "marks": {
        "name": "Marks",
        "hint": "What it leaves behind. Claw rakes, gouges, scorches, cracks.",
        "template": "deep {marks} torn across a dark surface, ragged edges, "
                    "glowing {color} light bleeding from inside each tear, "
                    "hard shadow, high contrast",
    },
    "form": {
        "name": "Silhouette",
        "hint": "Its shape as flat pattern. Bold graphic, reads at distance.",
        "template": "bold flat silhouettes of {subject} repeated as a decorative "
                    "pattern, solid {color} shapes on near-black, stencil-like, "
                    "no shading, strong negative space",
    },
    "atmosphere": {
        "name": "Atmosphere",
        "hint": "The air around it. Smoke, mist, aura, embers.",
        "template": "dense swirling {atmos} evoking {subject}, luminous {color} "
                    "billows against deep black, drifting embers, soft depth "
                    "with bright cores",
    },
}

# Keyword -> motif. Encodes the bit a designer does automatically: knowing that
# "dragon" means scales, "wolf" means fur, and "engine" means machined plate.
MOTIF_TABLE = [
    (("dragon", "serpent", "snake", "lizard", "reptile", "wyvern", "basilisk",
      "fish", "koi", "shark", "naga"), "overlapping reptilian scales", "roaring fire and embers",
     "raking claw slashes", "curling smoke"),
    (("wolf", "bear", "lion", "tiger", "fox", "boar", "panther", "cat", "hound"),
     "dense animal fur", "snarling heat haze", "raking claw slashes", "cold breath vapour"),
    (("phoenix", "eagle", "hawk", "raven", "crow", "owl", "bird", "falcon"),
     "layered feathers", "blazing plumage fire", "talon rakes", "drifting ash and embers"),
    (("insect", "beetle", "wasp", "hornet", "spider", "mantis", "scarab"),
     "iridescent chitin plating", "crackling static", "chitin fracture lines", "fine web filaments"),
    (("skull", "bone", "skeleton", "reaper", "death"),
     "cracked bone surface", "spectral flame", "deep gouges", "graveyard mist"),
    (("volcano", "lava", "magma", "ember", "inferno", "fire", "flame"),
     "cracked volcanic crust", "molten eruption", "scorch fractures", "smoke and cinders"),
    (("ice", "frost", "glacier", "winter", "arctic", "blizzard"),
     "fractured ice planes", "freezing crystal bloom", "shatter cracks", "frozen fog"),
    (("storm", "thunder", "lightning", "tempest", "hurricane"),
     "churning storm cloud", "forked lightning", "wind-torn gouges", "driving rain haze"),
    (("ocean", "wave", "water", "tide", "sea", "storm surge"),
     "breaking wave crests", "bioluminescent surge", "spray-carved channels", "sea mist"),
    (("machine", "engine", "robot", "mech", "industrial", "gear", "turbine", "piston"),
     "machined metal plating with rivets", "arcing electrical discharge",
     "gouged metal scoring", "exhaust haze"),
    (("circuit", "cyber", "digital", "data", "neon", "tech", "matrix"),
     "dense circuit traces", "streaming data light", "glitch fractures", "neon haze"),
    (("forest", "tree", "wood", "jungle", "leaf", "vine"),
     "gnarled bark and grain", "sunlight shafts", "splintered wood gouges", "forest mist"),
    (("stone", "rock", "granite", "marble", "mountain", "canyon"),
     "riven stone strata", "glowing mineral veins", "chisel fractures", "dust haze"),
    (("galaxy", "nebula", "cosmic", "space", "star", "void", "celestial"),
     "star-flecked cosmic dust", "stellar flare", "rifts torn in space", "nebula clouds"),
    (("snake", "camo", "military", "tactical", "armour", "armor", "knight"),
     "riveted armour plating", "forge sparks", "battle scoring", "smoke of battle"),
]

DEFAULT_MOTIF = ("richly detailed surface texture", "surging energy",
                 "deep torn gouges", "swirling haze")


def motifs_for(subject):
    s = (subject or "").lower()
    for keys, surface, energy, marks, atmos in MOTIF_TABLE:
        if any(k in s for k in keys):
            return surface, energy, marks, atmos
    return DEFAULT_MOTIF


def compile_freeform(subject, treatment="surface", color=None):
    """Turn a plain-language idea into a livery-grade texture prompt.

    Rule-based on purpose. An LLM would expand these more fluently, but it
    would need a key, cost money per generation and put the one offline tool in
    the stack behind someone's API - all to do a job a lookup table does well.
    """
    subject = (subject or "").strip()
    if not subject:
        raise ValueError("describe what you want first")
    t = TREATMENTS.get(treatment) or TREATMENTS["surface"]
    surface, energy, marks, atmos = motifs_for(subject)

    body = t["template"].format(
        subject=subject, motif=surface, energy=energy, marks=marks, atmos=atmos,
        color=(color or "").strip() or "richly saturated",
    )
    # The subject is named once for flavour, but the treatment carries the
    # composition - leading with the bare noun is what summons a portrait.
    text = f"{body}, inspired by {subject}, {FLAT}"
    return text, NEGATIVE


def build(preset_id, color=None, extra=None):
    """Return (positive, negative) for a preset with an optional colour override."""
    p = BY_ID.get(preset_id)
    if not p:
        raise KeyError(preset_id)
    text = p["prompt"].replace("{color}", (color or p["color"]).strip())
    if extra:
        text = f"{extra.strip()}, {text}"
    return text, NEGATIVE
