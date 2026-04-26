# Ableton Playground Reverse Engineering

The Learning Music "The playground" page uses two playback paths:

- Drumkit (`beats`): `Tone.Players`
  - Base URL: `/lessons/sounds/`
  - One-shot playback
  - `fadeOut = 0.01`
  - Choke behavior is encoded in the sample map. In this page, `ClosedHat` (`midi 42`) chokes `OpenHat` (`midi 46`).
- Tonal instruments (`basslines`, `chords`, `melodies`): `Tone.Sampler`
  - Base URL: `/lessons/sounds/`
  - Sparse sample keymaps are stretched across other notes by changing playback rate
  - Release tails:
    - `basslines`: `0.10`
    - `chords`: `0.40`
    - `melodies`: `0.06`

The recreated renderer lives in `tools/ableton_playground_renderer.py`.

## Usage

Render a demo sequence:

```bash
python tools/ableton_playground_renderer.py render-sequence --sequence examples/ableton_playground_demo.json --output out/demo.wav
```

Render a single tonal note:

```bash
python tools/ableton_playground_renderer.py render-note --instrument chords --note C4 --duration-beats 2 --output out/c4.wav
```

Render a single drum hit:

```bash
python tools/ableton_playground_renderer.py render-note --instrument beats --midi 36 --output out/kick.wav
```

Render by frequency:

```bash
python tools/ableton_playground_renderer.py render-note --instrument melodies --frequency-hz 523.25 --pitch-mode playground --duration-seconds 1.0 --output out/c5-ish.wav
```

## Sequence JSON format

- Top level:
  - `tempo`: BPM
  - `tracks`: array
- Track:
  - `instrument`: one of `beats`, `basslines`, `chords`, `melodies`
  - `events`: array
- Event timing:
  - use either `time_beats` or `time_seconds`
- Tonal event pitch:
  - use one of `note`, `midi`, `frequency_hz`
  - for held length use `duration_beats` or `duration_seconds`
- Drum event pitch:
  - use `midi`
- Optional:
  - `velocity`: `0.0` to `1.0`

`frequency_hz` supports:

- `pitch_mode = "playground"`: rounds to the nearest MIDI note first, matching the page's `playNoteAtFrequency()`
- `pitch_mode = "tone_sampler"`: uses fractional MIDI before playback-rate conversion, matching raw `Tone.Sampler`
