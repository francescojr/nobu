"""
Demo biome OST — 8-track chiptune soundtrack generator (game-agnostic example).

Composes 4 biomes × 2 states (calm/combat) using midiutil.
Follows game-music-producer skill conventions:
- Vertical layering: calm/combat crossfade pairs share same key and leitmotif
- Independent channel lengths (bass loops shorter than melody phrases)
- Drums with off-beat hi-hats (never purely straight)
- Mood→scale mapping from music-theory-for-games.md

Demo biome params (replace with your game's data):
  1. Surface: C2 (36), dorian, heroic_exploration
  2. Caves:   Eb2 (39), natural_minor, melancholic_dungeon
  3. Ruins:   F#2 (42), phrygian, hostile_exotic_biome
  4. Core:    A2 (45), minor_pentatonic, combat

Output: assets/midi/biome{N}_{calm,combat}.mid

Then run: python scripts/render_midi.py  →  output/audio/{project}/wav|ogg/
"""

from midiutil import MIDIFile
import os

OUT_DIR = os.path.join(
    os.path.dirname(__file__), "..", "assets", "midi"
)
BPM = 120
BEATS_PER_BAR = 4
BARS = 8
TOTAL_BEATS = BEATS_PER_BAR * BARS  # 32 beats

# ─── GM Programs ────────────────────────────────────────────────────
PULSE_LEAD = 80     # Square Lead — NES Pulse 1 approximation
PULSE_HARMONY = 81  # Lead 2 (sawtooth) — NES Pulse 2 approximation
TRIANGLE_BASS = 38  # Synth Bass 1 — NES Triangle approximation

# ─── Drum map (GM percussion on channel 9) ──────────────────────────
KICK = 36
SNARE = 38
HIHAT_CLOSED = 42
HIHAT_OPEN = 46
CRASH = 49

# ─── Scales ─────────────────────────────────────────────────────────
def build_scale(root_midi: int, intervals: list[int], octaves: int = 2) -> list[int]:
    """Generate MIDI pitch list from root + semitone intervals."""
    notes = []
    for oct_i in range(octaves):
        for iv in intervals:
            notes.append(root_midi + iv + 12 * oct_i)
    return notes

SCALE_INTERVALS = {
    "dorico": [0, 2, 3, 5, 7, 9, 10],
    "menor_natural": [0, 2, 3, 5, 7, 8, 10],
    "frigio": [0, 1, 3, 5, 7, 8, 10],
    "pentatonica_menor": [0, 3, 5, 7, 10],
}

SCALES = {}
for name, intervals in SCALE_INTERVALS.items():
    SCALES[name] = intervals

# ─── Biome definitions ──────────────────────────────────────────────
BIOMES = [
    {
        "id": 1,
        "name": "Surface",
        "root": 36,       # C2
        "scale": "dorico",  # internal interval key (same as dorian)
        "mood": "heroic_exploration",
        "description": "Adventurous, hopeful. Ascending dorian lines.",
    },
    {
        "id": 2,
        "name": "Caves",
        "root": 39,       # Eb2
        "scale": "menor_natural",
        "mood": "melancholic_dungeon",
        "description": "Dark, echoing. Descending minor passages.",
    },
    {
        "id": 3,
        "name": "Ruins",
        "root": 42,       # F#2
        "scale": "frigio",
        "mood": "hostile_exotic_biome",
        "description": "Tense, exotic. Flat-2nd unease. Ostinato bass.",
    },
    {
        "id": 4,
        "name": "Core",
        "root": 45,       # A2
        "scale": "pentatonica_menor",
        "mood": "combat",
        "description": "Intense. Pentatonic runs. Percussion-heavy.",
    },
]


def pick(scale_notes: list[int], degree: int, octave: int = 0) -> int:
    """Pick a scale degree (0-based index) from the scale, at given octave offset."""
    notes_per_octave = len(SCALE_INTERVALS.get("dorico", []))  # any scale works here
    # Actually, just index into the flat scale_notes list
    idx = degree + octave * len([i for i in SCALE_INTERVALS.get("dorico", [])])
    # Simpler: scale_notes is already flattened across octaves. Degree is absolute index.
    return scale_notes[degree % len(scale_notes)]


# ═══════════════════════════════════════════════════════════════════════
# Melody composers — each returns list of [pitch, start_beat, duration]
# ═══════════════════════════════════════════════════════════════════════

def compose_melody_surface(scale: list[int], calm: bool) -> list[list[float]]:
    """
    Surface / Dorico — hopeful ascending phrases.
    Leitmotif: rising dorian 5th, answered by descending thirds.
    Calm: longer notes, space for bass to breathe.
    Combat: denser, 8th-note runs.
    """
    notes = []
    if calm:
        # 8 bars, flowing melody. Each phrase = 2 bars (8 beats)
        phrases = [
            # Bar 1-2: "Call" — ascending dorian
            [scale[0], 0, 2.0], [scale[2], 2, 1.5], [scale[4], 3.5, 0.5],
            [scale[5], 4, 2.0], [scale[7], 6, 2.0],
            # Bar 3-4: "Response" — descending with dorian 6th
            [scale[9], 8, 1.5], [scale[7], 9.5, 0.5],
            [scale[5], 10, 1.0], [scale[4], 11, 1.0],
            [scale[2], 12, 2.0], [scale[0], 14, 2.0],
            # Bar 5-6: Mid-register arpeggiation
            [scale[4], 16, 1.0], [scale[5], 17, 1.0],
            [scale[7], 18, 1.0], [scale[9], 19, 1.0],
            [scale[10], 20, 1.5], [scale[9], 21.5, 0.5],
            [scale[7], 22, 2.0],
            # Bar 7-8: Resolution — rest then soft landing
            [scale[4], 24, 1.0], [scale[5], 25, 1.0],
            [scale[4], 26, 1.0], [scale[2], 27, 1.0],
            [scale[0], 28, 3.0],  # fermata-ish
        ]
    else:
        # Combat: denser, 8th-note runs, more staccato
        phrases = [
            # Bar 1-2: Aggressive ascending run
            [scale[0], 0, 0.5], [scale[2], 0.5, 0.5], [scale[4], 1, 0.5],
            [scale[5], 1.5, 0.5], [scale[7], 2, 0.5], [scale[9], 2.5, 0.5],
            [scale[10], 3, 1.0],
            [scale[9], 4, 0.5], [scale[7], 4.5, 0.5],
            [scale[5], 5, 0.5], [scale[9], 5.5, 0.5],
            [scale[10], 6, 1.0], [scale[12], 7, 0.5],
            # Bar 3-4: Staccato answer
            [scale[10], 8, 0.25], [scale[9], 8.25, 0.25],
            [scale[7], 8.5, 0.5], [scale[5], 9.25, 0.25],
            [scale[4], 9.5, 0.5], [scale[5], 10.25, 0.25],
            [scale[7], 10.5, 0.5], [scale[9], 11.25, 0.25],
            [scale[10], 11.5, 0.5],
            [scale[12], 12, 1.0], [scale[10], 13, 1.0],
            [scale[9], 14, 1.0], [scale[7], 15, 0.5],
            # Bar 5-6: Variation of bars 1-2, higher
            [scale[7], 16, 0.5], [scale[9], 16.5, 0.5],
            [scale[10], 17, 0.5], [scale[12], 17.5, 0.5],
            [scale[14], 18, 1.0], [scale[12], 19, 1.0],
            [scale[10], 20, 0.5], [scale[9], 20.5, 0.5],
            [scale[10], 21, 0.5], [scale[7], 21.5, 0.5],
            [scale[5], 22, 1.0], [scale[7], 23, 0.5],
            # Bar 7-8: Climactic resolution
            [scale[9], 24, 0.5], [scale[10], 24.5, 0.5],
            [scale[12], 25, 0.5], [scale[14], 25.5, 0.5],
            [scale[15], 26, 2.0],
            [scale[14], 28.5, 0.5], [scale[12], 29, 0.5],
            [scale[10], 29.5, 0.5], [scale[7], 30, 1.0],
        ]
    return phrases


def compose_melody_caves(scale: list[int], calm: bool) -> list[list[float]]:
    """
    Caves / Menor Natural — dark, echoing, descending.
    Leitmotif: descending minor scale with wide leaps.
    """
    notes = []
    if calm:
        phrases = [
            # Bar 1-2: Descending minor — "dark descent"
            [scale[14], 0, 1.5], [scale[12], 1.5, 0.5],
            [scale[10], 2, 1.0], [scale[7], 3, 1.0],
            [scale[5], 4, 2.0], [scale[4], 6, 1.0], [scale[2], 7, 1.0],
            # Bar 3-4: Echo response — same shape, lower
            [scale[10], 8, 1.5], [scale[7], 9.5, 0.5],
            [scale[5], 10, 1.0], [scale[4], 11, 1.0],
            [scale[2], 12, 1.5], [scale[0], 13.5, 0.5],
            [scale[2], 14, 2.0],
            # Bar 5-6: Wide melancholic leaps
            [scale[7], 16, 2.0], [scale[14], 18, 1.0],
            [scale[12], 19, 1.0], [scale[10], 20, 1.0],
            [scale[7], 21, 1.0], [scale[5], 22, 2.0],
            # Bar 7-8: Slow resolution
            [scale[4], 24, 1.5], [scale[2], 25.5, 0.5],
            [scale[0], 26, 1.5], [scale[2], 27.5, 0.5],
            [scale[0], 28, 3.0],
        ]
    else:
        phrases = [
            # Bar 1-2: Tense, fast descending run
            [scale[14], 0, 0.5], [scale[12], 0.5, 0.5],
            [scale[10], 1, 0.25], [scale[7], 1.25, 0.25],
            [scale[5], 1.5, 0.5], [scale[10], 2, 0.5],
            [scale[7], 2.5, 0.5], [scale[14], 3, 1.0],
            [scale[12], 4, 0.5], [scale[10], 4.5, 0.5],
            [scale[7], 5, 0.5], [scale[5], 5.5, 0.25],
            [scale[4], 5.75, 0.25], [scale[5], 6, 1.0],
            [scale[7], 7, 0.5],
            # Bar 3-4: Staccato tension
            [scale[10], 8, 0.25], [scale[7], 8.25, 0.25],
            [scale[5], 8.5, 0.25], [scale[10], 8.75, 0.25],
            [scale[7], 9, 0.25], [scale[12], 9.25, 0.25],
            [scale[10], 9.5, 0.5], [scale[14], 10, 0.5],
            [scale[12], 10.5, 0.5], [scale[10], 11, 0.5],
            [scale[7], 11.5, 0.5], [scale[5], 12, 1.0],
            [scale[7], 13, 1.0], [scale[5], 14, 1.0],
            [scale[10], 15, 0.5],
            # Bar 5-6: Ascending minor burst
            [scale[7], 16, 0.5], [scale[10], 16.5, 0.5],
            [scale[12], 17, 0.5], [scale[14], 17.5, 0.5],
            [scale[15], 18, 1.0], [scale[14], 19, 1.0],
            [scale[12], 20, 0.5], [scale[10], 20.5, 0.5],
            [scale[7], 21, 0.5], [scale[5], 21.5, 0.5],
            [scale[7], 22, 1.0], [scale[10], 23, 0.5],
            # Bar 7-8: Dramatic close
            [scale[12], 24, 0.5], [scale[14], 24.5, 0.5],
            [scale[15], 25, 2.0],
            [scale[14], 27.5, 0.5], [scale[12], 28, 1.0],
            [scale[10], 29, 1.0], [scale[7], 30, 1.0],
        ]
    return phrases


def compose_melody_ruins(scale: list[int], calm: bool) -> list[list[float]]:
    """
    Ruins / Frigio — exotic, tense. Flat 2nd (scale[1]) creates unease.
    Ostinato-driven with semitone movement.
    """
    notes = []
    if calm:
        phrases = [
            # Bar 1-2: Exotic semitone oscillation — frigio signature
            [scale[0], 0, 1.0], [scale[1], 1, 1.0],
            [scale[0], 2, 0.5], [scale[1], 2.5, 0.5],
            [scale[3], 3, 1.0], [scale[4], 4, 1.5],
            [scale[1], 5.5, 0.5], [scale[0], 6, 2.0],
            # Bar 3-4: Wide, unsettling intervals
            [scale[7], 8, 1.5], [scale[8], 9.5, 0.5],
            [scale[10], 10, 1.0], [scale[8], 11, 1.0],
            [scale[7], 12, 1.5], [scale[3], 13.5, 0.5],
            [scale[4], 14, 2.0],
            # Bar 5-6: Descending frigio phrase
            [scale[10], 16, 1.0], [scale[8], 17, 1.0],
            [scale[7], 18, 1.0], [scale[4], 19, 1.0],
            [scale[3], 20, 1.0], [scale[1], 21, 1.0],
            [scale[0], 22, 2.0],
            # Bar 7-8: Ambiguous resolution — never truly resolves
            [scale[3], 24, 1.5], [scale[4], 25.5, 0.5],
            [scale[7], 26, 1.5], [scale[8], 27.5, 0.5],
            [scale[7], 28, 3.0],
        ]
    else:
        phrases = [
            # Bar 1-2: Aggressive semitone stabs
            [scale[0], 0, 0.25], [scale[1], 0.25, 0.25],
            [scale[0], 0.5, 0.25], [scale[1], 0.75, 0.25],
            [scale[3], 1, 0.5], [scale[4], 1.5, 0.5],
            [scale[7], 2, 0.5], [scale[8], 2.5, 0.5],
            [scale[10], 3, 1.0],
            [scale[8], 4, 0.25], [scale[7], 4.25, 0.25],
            [scale[4], 4.5, 0.25], [scale[3], 4.75, 0.25],
            [scale[1], 5, 0.5], [scale[3], 5.5, 0.5],
            [scale[7], 6, 1.0], [scale[8], 7, 0.5],
            # Bar 3-4: Frantic frigio runs
            [scale[10], 8, 0.25], [scale[8], 8.25, 0.25],
            [scale[7], 8.5, 0.25], [scale[4], 8.75, 0.25],
            [scale[3], 9, 0.25], [scale[7], 9.25, 0.25],
            [scale[8], 9.5, 0.25], [scale[10], 9.75, 0.25],
            [scale[11], 10, 1.0],
            [scale[10], 11.5, 0.5], [scale[8], 12, 1.0],
            [scale[7], 13, 0.5], [scale[4], 13.5, 0.5],
            [scale[3], 14, 1.0], [scale[7], 15, 0.5],
            # Bar 5-6: High-register tension
            [scale[14], 16, 0.5], [scale[15], 16.5, 0.5],
            [scale[14], 17, 0.5], [scale[11], 17.5, 0.5],
            [scale[10], 18, 1.0], [scale[8], 19, 1.0],
            [scale[7], 20, 0.5], [scale[4], 20.5, 0.5],
            [scale[3], 21, 0.5], [scale[1], 21.5, 0.5],
            [scale[0], 22, 1.0], [scale[3], 23, 0.5],
            # Bar 7-8: Dramatic close — unresolved
            [scale[7], 24, 0.5], [scale[10], 24.5, 0.5],
            [scale[14], 25, 1.5],
            [scale[15], 27, 0.5], [scale[14], 27.5, 0.5],
            [scale[15], 28.25, 0.25], [scale[14], 28.5, 0.5],
            [scale[10], 29.5, 0.5], [scale[7], 30, 1.0],
        ]
    return phrases


def compose_melody_core(scale: list[int], calm: bool) -> list[list[float]]:
    """
    Core / Pentatonica Menor — intense, punchy pentatonic runs.
    All notes fit, so we can be very melodic and driving.
    """
    notes = []
    if calm:
        phrases = [
            # Bar 1-2: Strong pentatonic statement
            [scale[0], 0, 0.5], [scale[2], 0.5, 0.5],
            [scale[4], 1, 1.0], [scale[2], 2, 0.5],
            [scale[0], 2.5, 0.5], [scale[2], 3, 0.5],
            [scale[4], 3.5, 0.5], [scale[7], 4, 2.0],
            [scale[5], 6, 1.0], [scale[4], 7, 0.5],
            # Bar 3-4: Call-response pentatonic
            [scale[2], 8, 0.5], [scale[4], 8.5, 0.5],
            [scale[7], 9, 1.0], [scale[5], 10, 0.5],
            [scale[4], 10.5, 0.5], [scale[2], 11, 1.0],
            [scale[5], 12, 1.5], [scale[4], 13.5, 0.5],
            [scale[2], 14, 1.5], [scale[0], 15.5, 0.5],
            # Bar 5-6: Driving mid-register
            [scale[4], 16, 1.0], [scale[5], 17, 0.5],
            [scale[7], 17.5, 0.5], [scale[5], 18, 0.5],
            [scale[4], 18.5, 0.5], [scale[2], 19, 1.0],
            [scale[7], 20, 1.0], [scale[9], 21, 1.0],
            [scale[10], 22, 2.0],
            # Bar 7-8: Resolution — satisfying pentatonic landing
            [scale[7], 24, 0.5], [scale[9], 24.5, 0.5],
            [scale[10], 25, 0.5], [scale[9], 25.5, 0.5],
            [scale[7], 26, 1.0], [scale[5], 27, 1.0],
            [scale[4], 28, 1.5], [scale[2], 29.5, 0.5],
            [scale[0], 30, 1.5],
        ]
    else:
        phrases = [
            # Bar 1-2: Blazing pentatonic run — maximum energy
            [scale[0], 0, 0.25], [scale[2], 0.25, 0.25],
            [scale[4], 0.5, 0.25], [scale[5], 0.75, 0.25],
            [scale[7], 1, 0.25], [scale[9], 1.25, 0.25],
            [scale[10], 1.5, 0.5],
            [scale[9], 2, 0.25], [scale[7], 2.25, 0.25],
            [scale[5], 2.5, 0.25], [scale[4], 2.75, 0.25],
            [scale[2], 3, 0.5], [scale[4], 3.5, 0.5],
            [scale[5], 4, 0.5], [scale[7], 4.5, 0.5],
            [scale[9], 5, 0.5], [scale[10], 5.5, 0.5],
            [scale[12], 6, 1.0], [scale[10], 7, 0.5],
            # Bar 3-4: Staccato punch
            [scale[9], 8, 0.25], [scale[10], 8.25, 0.25],
            [scale[9], 8.5, 0.25], [scale[7], 8.75, 0.25],
            [scale[5], 9, 0.5], [scale[7], 9.5, 0.5],
            [scale[5], 10, 0.25], [scale[4], 10.25, 0.25],
            [scale[5], 10.5, 0.25], [scale[7], 10.75, 0.25],
            [scale[9], 11, 0.5], [scale[10], 11.5, 0.5],
            [scale[12], 12, 0.5], [scale[10], 12.5, 0.5],
            [scale[9], 13, 0.5], [scale[7], 13.5, 0.5],
            [scale[5], 14, 1.0], [scale[9], 15, 0.5],
            # Bar 5-6: Ascending peak
            [scale[7], 16, 0.25], [scale[9], 16.25, 0.25],
            [scale[10], 16.5, 0.25], [scale[12], 16.75, 0.25],
            [scale[14], 17, 1.0], [scale[12], 18, 0.5],
            [scale[10], 18.5, 0.5], [scale[9], 19, 0.5],
            [scale[10], 19.5, 0.5], [scale[12], 20, 0.5],
            [scale[14], 20.5, 0.5], [scale[14], 21, 1.0],
            [scale[14], 22, 1.0], [scale[12], 23, 0.5],
            # Bar 7-8: Climactic finish — driving to loop
            [scale[10], 24, 0.25], [scale[9], 24.25, 0.25],
            [scale[10], 24.5, 0.25], [scale[9], 24.75, 0.25],
            [scale[7], 25, 0.5], [scale[5], 25.5, 0.5],
            [scale[7], 26, 0.5], [scale[9], 26.5, 0.5],
            [scale[10], 27, 0.5], [scale[12], 27.5, 0.5],
            [scale[14], 28, 0.5], [scale[12], 28.5, 0.5],
            [scale[10], 29, 0.5], [scale[9], 29.5, 0.5],
            [scale[7], 30, 1.0], [scale[5], 31, 0.5],
        ]
    return phrases


# ═══════════════════════════════════════════════════════════════════════
# Bass composers — simpler, shorter loops, root+5th movement
# ═══════════════════════════════════════════════════════════════════════

def compose_bass(biome: dict, calm: bool) -> list[list[float]]:
    """
    Bass line — roots and fifths, half-note rhythm.
    Loops every 4 bars (16 beats), while melody spans 8 bars.
    This independent length creates organic non-synchronized feel.
    """
    root = biome["root"]
    scale_name = biome["scale"]
    intervals = SCALE_INTERVALS[scale_name]
    scale = [root + iv + 12 * o for o in range(2) for iv in intervals]

    if scale_name == "dorico":
        # i - IV - i - v - VI - III - VII - i
        bass_degrees = [0, 3, 0, 4, 5, 2, 6, 0]  # scale degrees
    elif scale_name == "menor_natural":
        # i - VI - III - VII - i - iv - V - i
        bass_degrees = [0, 5, 2, 6, 0, 3, 4, 0]
    elif scale_name == "frigio":
        # i - II - III - i - VI - VII - i - II (frigio character)
        bass_degrees = [0, 1, 2, 0, 5, 6, 0, 1]
    elif scale_name == "pentatonica_menor":
        # i - iv - i - v - III - VII - i - v
        bass_degrees = [0, 1, 0, 2, 3, 4, 0, 2]

    notes = []
    for bar in range(BARS):
        deg = bass_degrees[bar % len(bass_degrees)]
        pitch = scale[deg % len(scale)]
        start = bar * BEATS_PER_BAR
        if calm:
            # Calm: whole notes or half notes
            notes.append([pitch, start, 3.5])
        else:
            # Combat: more rhythmic, 8th-note pattern with octave jumps
            notes.append([pitch, start, 1.0])
            notes.append([pitch + 12, start + 1, 0.5])
            notes.append([pitch, start + 1.5, 0.5])
            notes.append([pitch, start + 2, 1.0])
            notes.append([pitch - 12, start + 3, 0.5])
        notes.append([pitch, start + BEATS_PER_BAR - 0.5, 0.5])  # pickup to next bar

    return notes


# ═══════════════════════════════════════════════════════════════════════
# Harmony composers — chord pads for combat tracks
# ═══════════════════════════════════════════════════════════════════════

def compose_harmony(biome: dict) -> list[list[float]]:
    """
    Harmony layer (pulse_harmony) — sustained chord tones.
    One chord per bar, 3-note voicings.
    Only used in combat tracks.
    """
    root = biome["root"]
    scale_name = biome["scale"]
    intervals = SCALE_INTERVALS[scale_name]
    scale = [root + iv + 12 * o for o in range(3) for iv in intervals]

    # Chord maps: each bar gets a triad (root, 3rd, 5th in scale degrees)
    chord_map = {
        "dorico": [[0, 2, 4], [3, 5, 7], [0, 2, 4], [4, 6, 8],
                     [5, 7, 9], [2, 4, 6], [6, 8, 10], [0, 2, 4]],
        "menor_natural": [[0, 2, 4], [5, 7, 9], [2, 4, 6], [6, 8, 10],
                            [0, 2, 4], [3, 5, 7], [4, 6, 8], [0, 2, 4]],
        "frigio": [[0, 2, 4], [1, 3, 5], [2, 4, 6], [0, 2, 4],
                    [5, 7, 9], [6, 8, 10], [0, 2, 4], [1, 3, 5]],
        "pentatonica_menor": [[0, 1, 2], [1, 2, 3], [0, 1, 2], [2, 3, 4],
                               [3, 4, 0], [4, 0, 1], [0, 1, 2], [2, 3, 4]],
    }

    chords = chord_map[scale_name]
    notes = []
    for bar in range(BARS):
        chord = chords[bar]
        start = bar * BEATS_PER_BAR
        for deg in chord:
            pitch = scale[deg % len(scale)]
            notes.append([pitch, start, float(BEATS_PER_BAR) - 0.1])

    return notes


# ═══════════════════════════════════════════════════════════════════════
# Drum composers — groove with off-beat hi-hats (never fully straight)
# ═══════════════════════════════════════════════════════════════════════

def compose_drums(intensity: str = "combat") -> list[list[float]]:
    """
    Drum pattern with off-beat hi-hats for organic groove.
    Kick on 1 & 3, snare on 2 & 4, hi-hat on all 8th notes
    with slight swing on odd-numbered bars.
    """
    notes = []
    for bar in range(BARS):
        base = bar * BEATS_PER_BAR
        # Kick — beats 0, 2 (on the 1 and 3)
        notes.append([KICK, base + 0, 0.5])
        notes.append([KICK, base + 2, 0.5])
        # Snare — beats 1, 3 (on the 2 and 4) = backbeat
        notes.append([SNARE, base + 1, 0.5])
        notes.append([SNARE, base + 3, 0.5])
        # Hi-hat — 8th notes (every 0.5 beats)
        for eighth in range(8):
            t = base + eighth * 0.5
            # Light swing: every other hi-hat is slightly displaced
            vol = 70 if eighth % 2 == 1 else 60  # accent on off-beats for groove
            notes.append([HIHAT_CLOSED, t, 0.25, vol])
        # Crash on bar 0 and bar 4 (start of each phrase)
        if bar == 0:
            notes.append([CRASH, base + 0, 0.8, 100])
        if bar == 4:
            notes.append([CRASH, base + 0, 0.8, 90])
        # Open hi-hat at end of 4-bar phrase for buildup
        if bar == 3 or bar == 7:
            notes.append([HIHAT_OPEN, base + 3.5, 0.5, 75])

    return notes


# ═══════════════════════════════════════════════════════════════════════
# MIDI file assembly
# ═══════════════════════════════════════════════════════════════════════

MELODY_COMPOSERS = {
    1: compose_melody_surface,
    2: compose_melody_caves,
    3: compose_melody_ruins,
    4: compose_melody_core,
}


def build_midi(biome: dict, calm: bool, output_path: str) -> dict:
    """
    Build a MIDI file for one biome/state pair.
    Returns metadata dict with loop info.
    """
    biome_id = biome["id"]
    scale_name = biome["scale"]
    root = biome["root"]
    intervals = SCALE_INTERVALS[scale_name]
    scale = build_scale(root, intervals, octaves=3)

    # Determine number of tracks
    # Track 0: Melody (pulse_lead)
    # Track 1: Bass (triangle_bass)
    # Track 2: Drums (ch 9) — combat only
    # Track 3: Harmony (pulse_harmony) — combat only
    num_tracks = 4 if not calm else 2
    midi = MIDIFile(numTracks=num_tracks, deinterleave=False)

    # Add tempo to all tracks
    for t in range(num_tracks):
        midi.addTempo(track=t, time=0, tempo=BPM)

    # Track 0: Melody
    melody_notes = MELODY_COMPOSERS[biome_id](scale, calm)
    midi.addProgramChange(tracknum=0, channel=0, time=0, program=PULSE_LEAD)
    for n in melody_notes:
        pitch = int(n[0])
        start = float(n[1])
        dur = float(n[2])
        vol = int(n[3]) if len(n) > 3 else 95
        if 0 <= pitch <= 127 and dur > 0:
            midi.addNote(track=0, channel=0, pitch=pitch, time=start, duration=dur, volume=vol)

    # Track 1: Bass
    bass_notes = compose_bass(biome, calm)
    midi.addProgramChange(tracknum=1, channel=1, time=0, program=TRIANGLE_BASS)
    for n in bass_notes:
        pitch = int(n[0])
        start = float(n[1])
        dur = float(n[2])
        vol = int(n[3]) if len(n) > 3 else 90
        if 0 <= pitch <= 127 and dur > 0:
            midi.addNote(track=1, channel=1, pitch=pitch, time=start, duration=dur, volume=vol)

    if not calm:
        # Track 2: Drums (channel 9)
        drum_notes = compose_drums("combat")
        for n in drum_notes:
            pitch = int(n[0])
            start = float(n[1])
            dur = float(n[2])
            vol = int(n[3]) if len(n) > 3 else 85
            if 0 <= pitch <= 127 and dur > 0:
                midi.addNote(track=2, channel=9, pitch=pitch, time=start, duration=dur, volume=vol)

        # Track 3: Harmony
        harmony_notes = compose_harmony(biome)
        midi.addProgramChange(tracknum=3, channel=2, time=0, program=PULSE_HARMONY)
        for n in harmony_notes:
            pitch = int(n[0])
            start = float(n[1])
            dur = float(n[2])
            vol = int(n[3]) if len(n) > 3 else 65
            if 0 <= pitch <= 127 and dur > 0:
                midi.addNote(track=3, channel=2, pitch=pitch, time=start, duration=dur, volume=vol)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "wb") as f:
        midi.writeFile(f)

    # Max end time
    all_notes = melody_notes + bass_notes
    if not calm:
        all_notes += compose_drums("combat") + compose_harmony(biome)
    max_end = max((n[1] + n[2] for n in all_notes if len(n) >= 3), default=0)
    return {
        "file": output_path,
        "biome": biome["name"],
        "state": "calm" if calm else "combat",
        "bpm": BPM,
        "scale": scale_name,
        "root_midi": root,
        "total_beats": round(max_end, 1),
        "total_bars_approx": round(max_end / BEATS_PER_BAR, 1),
        "tracks": num_tracks,
    }


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    results = []

    for biome in BIOMES:
        for state in ["calm", "combat"]:
            calm = state == "calm"
            fname = f"biome{biome['id']}_{state}.mid"
            path = os.path.join(OUT_DIR, fname)

            print(f"Composing {biome['name']} ({biome['scale']}) — {state}...")
            meta = build_midi(biome, calm, path)
            results.append(meta)
            print(f"  OK {fname} - {meta['total_beats']} beats, {meta['tracks']} tracks")

    print(f"\n{'='*60}")
    print(f"Done! {len(results)} MIDI files written to {OUT_DIR}")
    print(f"\nLoop metadata for engine integration:")
    for r in results:
        print(f"  {r['biome']:8s} {r['state']:6s} — "
              f"{r['total_beats']:5.1f} beats / ~{r['total_bars_approx']:4.1f} bars "
              f"({r['scale']})")
    print(f"\nNext: python scripts/render_midi.py")


if __name__ == "__main__":
    main()
