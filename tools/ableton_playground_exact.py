#!/usr/bin/env python3
"""Render a state format aligned to Ableton Learning Music's The playground page.

Aligned freedoms:
- Global tempo.
- Beats: fixed 8 drum lanes, fixed 16-grid layout, each cell is on/off only.
- Basslines / Chords / Melodies:
  - fixed 16-grid layout
  - fixed lane count derived from root/scale and widget range
  - user can only control root, scale, and note blocks (lane/start/length)

Out-of-band render options such as output directory and master gain are CLI flags,
not part of the musical state itself.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ableton_playground_renderer import (
    FFMPEG_BIN,
    OUTPUT_SAMPLE_RATE,
    RendererError,
    create_voices_from_sequence,
    render_voices,
    resolve_asset_root,
    run_command,
)


BEATS_PER_BAR = 4
TOTAL_BARS = 4
TOTAL_BEATS = BEATS_PER_BAR * TOTAL_BARS
STEPS_PER_BEAT = 1
TOTAL_STEPS = TOTAL_BEATS * STEPS_PER_BEAT

BEAT_LANES = [
    ("Kick", 36),
    ("Rim", 37),
    ("Snare", 38),
    ("Clap", 39),
    ("ClosedHat", 42),
    ("OpenHat", 46),
    ("Tom", 48),
    ("Ride", 51),
]

TONAL_WIDGETS = {
    "basslines": {"default_octave": 2, "octave_count": 2},
    "chords": {"default_octave": 5, "octave_count": 2},
    "melodies": {"default_octave": 5, "octave_count": 2},
}

ROOT_TO_SEMITONE = {
    "C": 0,
    "Db": 1,
    "C#": 1,
    "D": 2,
    "Eb": 3,
    "D#": 3,
    "E": 4,
    "F": 5,
    "F#": 6,
    "Gb": 6,
    "G": 7,
    "Ab": 8,
    "G#": 8,
    "A": 9,
    "Bb": 10,
    "A#": 10,
    "B": 11,
}

SCALE_INTERVALS = {
    "Major/Ionian": [0, 2, 4, 5, 7, 9, 11],
    "Minor/Aeolian": [0, 2, 3, 5, 7, 8, 10],
    "Dorian": [0, 2, 3, 5, 7, 9, 10],
    "Phrygian": [0, 1, 3, 5, 7, 8, 10],
    "Lydian": [0, 2, 4, 6, 7, 9, 11],
    "Mixolydian": [0, 2, 4, 5, 7, 9, 10],
    "Locrian": [0, 1, 3, 5, 6, 8, 10],
}


def clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))


def load_state(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise RendererError(f"Playground state file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def note_name_to_midi_c(root: str, octave: int) -> int:
    if root not in ROOT_TO_SEMITONE:
        raise RendererError(f"Unsupported root '{root}'")
    return (octave + 1) * 12 + ROOT_TO_SEMITONE[root]


def validate_step(step: int) -> int:
    if not isinstance(step, int):
        raise RendererError("step must be an integer")
    if step < 0 or step >= TOTAL_STEPS:
        raise RendererError(f"step must be between 0 and {TOTAL_STEPS - 1}")
    return step


def validate_length(length: int) -> int:
    if not isinstance(length, int):
        raise RendererError("length must be an integer")
    if length < 1 or length > TOTAL_STEPS:
        raise RendererError(f"length must be between 1 and {TOTAL_STEPS}")
    return length


def build_drum_sequence(section: Dict[str, Any]) -> Dict[str, Any]:
    active = section.get("active_steps", {})
    if not isinstance(active, dict):
        raise RendererError("'beats.active_steps' must be an object")

    lane_map = {name: midi for name, midi in BEAT_LANES}
    events: List[Dict[str, Any]] = []

    for lane_name, steps in active.items():
        if lane_name not in lane_map:
            raise RendererError(f"Unsupported beat lane '{lane_name}'")
        if not isinstance(steps, list):
            raise RendererError(f"Lane '{lane_name}' must be an array of step indices")
        for raw_step in steps:
            step = validate_step(int(raw_step))
            events.append({"time_beats": step / STEPS_PER_BEAT, "midi": lane_map[lane_name]})

    events.sort(key=lambda item: (item["time_beats"], item["midi"]))
    return {"tempo": 85, "tracks": [{"instrument": "beats", "events": events}]}


def tonal_lane_to_midi(
    widget_name: str,
    root: str,
    scale: str,
    lane: int,
) -> int:
    if scale not in SCALE_INTERVALS:
        raise RendererError(f"Unsupported scale '{scale}'")
    if widget_name not in TONAL_WIDGETS:
        raise RendererError(f"Unsupported widget '{widget_name}'")

    widget = TONAL_WIDGETS[widget_name]
    lane_count = widget["octave_count"] * 7 + 1
    if lane < 0 or lane >= lane_count:
        raise RendererError(f"lane must be between 0 and {lane_count - 1} for '{widget_name}'")

    base_midi = note_name_to_midi_c(root, widget["default_octave"])
    degree = lane % 7
    octave_offset = lane // 7
    if lane == lane_count - 1:
        return base_midi + widget["octave_count"] * 12
    return base_midi + octave_offset * 12 + SCALE_INTERVALS[scale][degree]


def build_tonal_sequence(widget_name: str, section: Dict[str, Any]) -> Dict[str, Any]:
    root = str(section.get("root", "C"))
    scale = str(section.get("scale", "Major/Ionian"))
    notes = section.get("notes", [])
    if not isinstance(notes, list):
        raise RendererError(f"'{widget_name}.notes' must be an array")

    events: List[Dict[str, Any]] = []
    for note in notes:
        if not isinstance(note, dict):
            raise RendererError("Each tonal note must be an object")
        lane = int(note["lane"])
        step = validate_step(int(note["start"]))
        length = validate_length(int(note["length"]))
        if step + length > TOTAL_STEPS:
            raise RendererError(
                f"Note in '{widget_name}' exceeds pattern length: start={step}, length={length}"
            )
        midi = tonal_lane_to_midi(widget_name, root, scale, lane)
        events.append(
            {
                "time_beats": step / STEPS_PER_BEAT,
                "duration_beats": length / STEPS_PER_BEAT,
                "midi": midi,
            }
        )

    events.sort(key=lambda item: (item["time_beats"], item["midi"]))
    return {"tempo": 85, "tracks": [{"instrument": widget_name, "events": events}]}


def render_silence(duration_seconds: float, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    run_command(
        (
            FFMPEG_BIN,
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"anullsrc=channel_layout=stereo:sample_rate={OUTPUT_SAMPLE_RATE}",
            "-t",
            f"{duration_seconds:.6f}",
            str(output_path),
        )
    )


def mix_audio_files(
    inputs: Sequence[Path],
    output_path: Path,
    master_gain: float,
) -> None:
    ffmpeg_inputs: List[str] = []
    labels: List[str] = []
    filters: List[str] = []
    for index, path in enumerate(inputs):
        ffmpeg_inputs.extend(["-i", str(path)])
        label = f"[s{index}]"
        filters.append(f"[{index}:a]anull{label}")
        labels.append(label)

    filters.append(
        "".join(labels)
        + f"amix=inputs={len(labels)}:dropout_transition=0:normalize=0,volume={master_gain:.6f},alimiter=limit=0.97[out]"
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    run_command(
        (
            FFMPEG_BIN,
            "-y",
            *ffmpeg_inputs,
            "-filter_complex",
            ";".join(filters),
            "-map",
            "[out]",
            str(output_path),
        )
    )


def estimate_duration_seconds() -> float:
    return TOTAL_BEATS * 60.0 / 85.0


def render_playground_state(
    state: Dict[str, Any],
    output_dir: Path,
    asset_root: Path,
    master_gain: float,
    source_state_path: Optional[Path] = None,
) -> Dict[str, str]:
    tempo = float(state.get("tempo", 85.0))
    if tempo <= 0:
        raise RendererError("tempo must be > 0")

    name = str(state.get("name", "playground-exact")).strip() or "playground-exact"

    beats_sequence = build_drum_sequence(state.get("beats", {}))
    beats_sequence["tempo"] = tempo

    bass_sequence = build_tonal_sequence("basslines", state.get("basslines", {}))
    bass_sequence["tempo"] = tempo

    chords_sequence = build_tonal_sequence("chords", state.get("chords", {}))
    chords_sequence["tempo"] = tempo

    melodies_sequence = build_tonal_sequence("melodies", state.get("melodies", {}))
    melodies_sequence["tempo"] = tempo

    output_dir.mkdir(parents=True, exist_ok=True)
    duration_seconds = TOTAL_BEATS * 60.0 / tempo
    outputs: Dict[str, str] = {}
    audio_paths: List[Path] = []

    sections = [
        ("beats", beats_sequence, output_dir / "beats.wav"),
        ("basslines", bass_sequence, output_dir / "basslines.wav"),
        ("chords", chords_sequence, output_dir / "chords.wav"),
        ("melodies", melodies_sequence, output_dir / "melodies.wav"),
    ]

    for name_key, sequence, path in sections:
        voices = create_voices_from_sequence(sequence, asset_root)
        if voices:
            render_voices(voices, path)
        else:
            render_silence(duration_seconds, path)
        outputs[name_key] = str(path)
        audio_paths.append(path)

    full_mix = output_dir / f"{name}-full.wav"
    mix_audio_files(audio_paths, full_mix, master_gain=master_gain)
    outputs["full_mix"] = str(full_mix)

    if source_state_path is not None:
        copied_input = output_dir / "input-state.json"
        copied_input.write_text(
            source_state_path.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        outputs["input_config"] = str(copied_input)

    manifest = {
        "name": name,
        "tempo": tempo,
        "steps": TOTAL_STEPS,
        "bars": TOTAL_BARS,
        "beats": TOTAL_BEATS,
        "master_gain": master_gain,
        "files": outputs,
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    outputs["manifest"] = str(manifest_path)
    return outputs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render an exact-state clone of Ableton Learning Music The playground."
    )
    parser.add_argument("--state", required=True, help="Playground state JSON path")
    parser.add_argument("--output-dir", required=True, help="Output directory")
    parser.add_argument(
        "--asset-root",
        help="Directory containing manifest.json and the beats/basslines/chords/melodies folders",
    )
    parser.add_argument(
        "--master-gain",
        type=float,
        default=1.0,
        help="Final full-mix output gain multiplier",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        state_path = Path(args.state).resolve()
        state = load_state(state_path)
        asset_root = resolve_asset_root(args.asset_root)
        render_playground_state(
            state=state,
            output_dir=Path(args.output_dir).resolve(),
            asset_root=asset_root,
            master_gain=clamp(float(args.master_gain), 0.0, 16.0),
            source_state_path=state_path,
        )
        return 0
    except RendererError as exc:
        print(f"Error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
