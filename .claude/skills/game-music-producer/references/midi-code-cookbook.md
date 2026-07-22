# Cookbook de Geração de MIDI via Python

> **Priority note:** if the **nobu** MCP server is available (tools
> `start_project`, `add_layer`, `export_midi`, etc.), **PREFER using it**
> instead of the manual recipes below — it already handles independent
> channels, note validation, mood→scale, and swing. See `mcp-integration.md`.
> Use this manual cookbook only when MCP is unavailable, or for MIDI
> analysis/manipulation that MCP does not cover (e.g. read/write CC,
> transpose existing files, extract chroma).

Bibliotecas de referência: `pretty_midi` (craffel/pretty-midi, docs oficiais) e `mido` (mido.readthedocs.io).
Instalação: `pip install pretty_midi mido python-rtmidi`

## 1. Diferença entre as bibliotecas
- **pretty_midi**: API de alto nível, orientada a objetos (Note, Instrument, PrettyMIDI). Ideal para COMPOR/gerar música do zero, análise musical (chroma, tempo estimation), e síntese direta em áudio.
- **mido**: API de baixo nível, trabalha diretamente com MENSAGENS MIDI (note_on, note_off, control_change) e PORTAS MIDI em tempo real. Ideal para I/O em tempo real (tocar via teclado MIDI, enviar para sintetizador externo) e manipulação fina de eventos.
- Regra prática: use `pretty_midi` para gerar composições/arquivos .mid; use `mido` quando precisar de controle de baixo nível ou I/O em tempo real com hardware/software MIDI.

## 2. Estrutura básica com pretty_midi
```python
import pretty_midi

pm = pretty_midi.PrettyMIDI(initial_tempo=120)
instrument = pretty_midi.Instrument(program=pretty_midi.instrument_name_to_program('Square Lead'))

note = pretty_midi.Note(velocity=100, pitch=60, start=0.0, end=0.5)
instrument.notes.append(note)

pm.instruments.append(instrument)
pm.write('output.mid')
```

## 3. Gerando uma progressão de acordes (leitmotif harmônico)
```python
import pretty_midi

def make_chord_progression(chords, bpm=120, beats_per_chord=2, program=0):
    pm = pretty_midi.PrettyMIDI(initial_tempo=bpm)
    inst = pretty_midi.Instrument(program=program)
    beat_dur = 60.0 / bpm
    t = 0.0
    for chord in chords:
        for pitch in chord:
            inst.notes.append(pretty_midi.Note(
                velocity=90, pitch=pitch,
                start=t, end=t + beat_dur * beats_per_chord
            ))
        t += beat_dur * beats_per_chord
    pm.instruments.append(inst)
    return pm

C = [60, 64, 67]
G = [55, 59, 62]
Am = [57, 60, 64]
F = [53, 57, 60]

pm = make_chord_progression([C, G, Am, F], bpm=100)
pm.write('progression.mid')
```

## 4. Gerando melodia procedural sobre uma escala
```python
import pretty_midi
import random

def generate_melody(scale, length=16, bpm=120, note_dur_beats=0.5, program=80, seed=None):
    if seed is not None:
        random.seed(seed)
    pm = pretty_midi.PrettyMIDI(initial_tempo=bpm)
    inst = pretty_midi.Instrument(program=program)
    beat_dur = 60.0 / bpm
    t = 0.0
    prev_idx = len(scale) // 2
    for _ in range(length):
        step = random.choice([-2, -1, -1, 0, 1, 1, 2])
        prev_idx = max(0, min(len(scale) - 1, prev_idx + step))
        pitch = scale[prev_idx]
        dur = beat_dur * note_dur_beats
        inst.notes.append(pretty_midi.Note(velocity=95, pitch=pitch, start=t, end=t + dur * 0.95))
        t += dur
    pm.instruments.append(inst)
    return pm

C_major_pentatonic = [60, 62, 64, 67, 69, 72, 74, 76, 79, 81]
pm = generate_melody(C_major_pentatonic, length=32, bpm=140, program=80, seed=42)
pm.write('melody.mid')
```

## 5. Loop perfeito para exploração (garantindo compassos exatos)
```python
import pretty_midi

def make_seamless_loop(notes_pattern, bpm, bars=8, beats_per_bar=4, program=0):
    pm = pretty_midi.PrettyMIDI(initial_tempo=bpm)
    inst = pretty_midi.Instrument(program=program)
    beat_dur = 60.0 / bpm
    total_beats = bars * beats_per_bar
    t = 0.0
    i = 0
    while t < total_beats * beat_dur:
        pitch, dur_beats = notes_pattern[i % len(notes_pattern)]
        end = min(t + dur_beats * beat_dur, total_beats * beat_dur)
        inst.notes.append(pretty_midi.Note(velocity=90, pitch=pitch, start=t, end=end))
        t = end
        i += 1
    pm.instruments.append(inst)
    return pm
```

## 6. Sistema de camadas para vertical layering (multi-instrumento sincronizado)
```python
import pretty_midi

def build_layered_track(bpm=110, bars=8):
    pm = pretty_midi.PrettyMIDI(initial_tempo=bpm)
    beat = 60.0 / bpm
    total = bars * 4 * beat

    pad = pretty_midi.Instrument(program=pretty_midi.instrument_name_to_program('String Ensemble 1'))
    for i, p in enumerate([60, 64, 67, 64] * bars):
        s = i * beat
        pad.notes.append(pretty_midi.Note(velocity=70, pitch=p, start=s, end=s + beat * 0.95))

    drums = pretty_midi.Instrument(program=0, is_drum=True)
    for i in range(bars * 4):
        s = i * beat
        drums.notes.append(pretty_midi.Note(velocity=100, pitch=36, start=s, end=s + 0.1))

    pm.instruments.append(pad)
    pm.instruments.append(drums)
    return pm
```
Nota: para vertical layering real numa engine (FMOD/Wwise/Godot/Unity), exporte cada camada como um ARQUIVO DE ÁUDIO SEPARADO (stem), não dependa de mutar instrumentos dentro de um único MIDI — o MIDI serve para PROTOTIPAR a composição antes do render final em áudio.

## 7. Convertendo escala/acordes com music21 (alternativa com teoria musical embutida)
```python
from music21 import stream, note, chord, midi

s = stream.Stream()
s.append(chord.Chord(['C4', 'E4', 'G4'], quarterLength=2))
s.append(chord.Chord(['G3', 'B3', 'D4'], quarterLength=2))
s.write('midi', fp='music21_output.mid')
```

## 8. Mido — enviando MIDI em tempo real (útil para prototipagem interativa)
```python
import mido
import time

outport = mido.open_output()
notes = [60, 64, 67, 72]
for n in notes:
    outport.send(mido.Message('note_on', note=n, velocity=100))
    time.sleep(0.3)
    outport.send(mido.Message('note_off', note=n))
```

## 9. Boas práticas de nomenclatura de programa (General MIDI)
Ao usar `pretty_midi.instrument_name_to_program()`, os nomes seguem o padrão General MIDI (128 programas, ex.: 0=Acoustic Grand Piano, 80=Lead 1 Square, 81=Lead 2 Sawtooth, 38=Synth Bass 1). Para simular chiptune via MIDI padrão, prefira os programas 80-87 (Synth Lead) que se aproximam do timbre de onda quadrada/dente-de-serra.

## 10. Checklist ao entregar código de geração MIDI
- O BPM e a assinatura de tempo estão explícitos e documentados no código?
- O loop (se houver) tem duração em número exato de compassos, sem arredondamento de ponto flutuante acumulado?
- Cada camada/instrumento está em um `Instrument` separado, para permitir exportação de stems?
- Existe uma seed determinística se a geração for procedural (para reprodutibilidade)?
- O código inclui comentário indicando a escala/progressão teórica usada, para facilitar ajuste manual posterior?
