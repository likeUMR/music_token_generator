#!/usr/bin/env python3
"""Arrange and render a Playground-style multi-stem composition.

The config format is designed around four synchronized stems:
- beat
- bassline
- chord
- melody

Each stem contains one or more tracks, and each track contains a time series of
events. Every event can trigger one or more plays at the same time, which makes
it suitable for drum hits, chord voicings, doubled melody notes, and layered
phrases.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from ableton_playground_renderer import (
    FFMPEG_BIN,
    OUTPUT_SAMPLE_RATE,
    RendererError,
    BANKS,
    beats_to_seconds,
    canonical_bank_name,
    create_voices_from_sequence,
    render_voices,
    resolve_asset_root,
    run_command,
)


STEM_ALIASES = {
    "beat": "beat",
    "beats": "beat",
    "drum": "beat",
    "drums": "beat",
    "bass": "bassline",
    "bassline": "bassline",
    "baseline": "bassline",
    "basslines": "bassline",
    "chord": "chord",
    "chords": "chord",
    "harmony": "chord",
    "melody": "melody",
    "melodies": "melody",
    "lead": "melody",
}

STEM_ORDER = ("beat", "bassline", "chord", "melody")
STEM_TO_BANK = {
    "beat": "beats",
    "bassline": "basslines",
    "chord": "chords",
    "melody": "melodies",
}


def clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))


def canonical_stem_name(name: str) -> str:
    key = name.strip().lower()
    if key not in STEM_ALIASES:
        raise RendererError(
            f"Unknown stem '{name}'. Valid names: {', '.join(sorted(STEM_ALIASES))}"
        )
    return STEM_ALIASES[key]


def stem_bank_name(stem_name: str) -> str:
    return STEM_TO_BANK[canonical_stem_name(stem_name)]


def load_json_file(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise RendererError(f"Arrangement file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def extract_stem_map(arrangement: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    raw_stems = arrangement.get("stems")
    if not isinstance(raw_stems, dict):
        raise RendererError("Arrangement JSON must contain an object field named 'stems'")

    normalized: Dict[str, Dict[str, Any]] = {}
    for raw_name, raw_value in raw_stems.items():
        stem_name = canonical_stem_name(str(raw_name))
        if stem_name in normalized:
            raise RendererError(f"Duplicate stem definition for '{stem_name}'")
        if raw_value is None:
            normalized[stem_name] = {}
            continue
        if not isinstance(raw_value, dict):
            raise RendererError(f"Stem '{raw_name}' must be an object")
        normalized[stem_name] = raw_value
    return normalized


def expand_event_plays(event: Dict[str, Any]) -> List[Dict[str, Any]]:
    common = {
        key: value
        for key, value in event.items()
        if key not in {"plays", "notes", "midis"}
    }

    if "plays" in event:
        plays = event["plays"]
        if not isinstance(plays, list) or not plays:
            raise RendererError("'plays' must be a non-empty array when provided")
        expanded: List[Dict[str, Any]] = []
        for play in plays:
            if not isinstance(play, dict):
                raise RendererError("Each item in 'plays' must be an object")
            merged = dict(common)
            merged.update(play)
            expanded.append(merged)
        return expanded

    if "notes" in event:
        notes = event["notes"]
        if not isinstance(notes, list) or not notes:
            raise RendererError("'notes' must be a non-empty array when provided")
        return [dict(common, note=note) for note in notes]

    if "midis" in event:
        midis = event["midis"]
        if not isinstance(midis, list) or not midis:
            raise RendererError("'midis' must be a non-empty array when provided")
        return [dict(common, midi=midi) for midi in midis]

    return [common]


def require_time_field(play: Dict[str, Any]) -> None:
    if "time_beats" not in play and "time_seconds" not in play:
        raise RendererError("Every play requires time_beats or time_seconds")


def apply_time_shift(
    play: Dict[str, Any],
    time_offset_beats: float,
    time_offset_seconds: float,
    repeat_index: int,
    loop_length_beats: Optional[float],
    loop_length_seconds: Optional[float],
) -> Dict[str, Any]:
    result = dict(play)
    require_time_field(result)

    if "time_beats" in result:
        base = float(result["time_beats"]) + time_offset_beats
        if loop_length_beats is not None:
            base += repeat_index * loop_length_beats
        result["time_beats"] = base
    else:
        base = float(result["time_seconds"]) + time_offset_seconds
        if loop_length_seconds is not None:
            base += repeat_index * loop_length_seconds
        result["time_seconds"] = base

    return result


def normalize_track_events(
    stem_name: str,
    track: Dict[str, Any],
) -> Dict[str, Any]:
    if not isinstance(track, dict):
        raise RendererError(f"Track in stem '{stem_name}' must be an object")

    expected_bank = stem_bank_name(stem_name)
    instrument = canonical_bank_name(str(track.get("instrument", expected_bank)))
    if instrument != expected_bank:
        raise RendererError(
            f"Stem '{stem_name}' can only use instrument '{expected_bank}', got '{instrument}'"
        )

    events = track.get("events")
    if not isinstance(events, list) or not events:
        raise RendererError(f"Track in stem '{stem_name}' must contain a non-empty 'events' array")

    repeat = int(track.get("repeat", 1))
    if repeat < 1:
        raise RendererError("Track 'repeat' must be >= 1")

    loop_length_beats = track.get("loop_length_beats")
    loop_length_seconds = track.get("loop_length_seconds")
    if repeat > 1 and loop_length_beats is None and loop_length_seconds is None:
        raise RendererError(
            "Tracks with repeat > 1 require loop_length_beats or loop_length_seconds"
        )

    time_offset_beats = float(track.get("time_offset_beats", 0.0))
    time_offset_seconds = float(track.get("time_offset_seconds", 0.0))
    default_velocity = float(track.get("default_velocity", 1.0))
    track_gain = float(track.get("gain", 1.0))
    default_duration_beats = track.get("default_duration_beats")
    default_duration_seconds = track.get("default_duration_seconds")

    normalized_events: List[Dict[str, Any]] = []

    for repeat_index in range(repeat):
        for raw_event in events:
            if not isinstance(raw_event, dict):
                raise RendererError("Each event must be an object")

            for play in expand_event_plays(raw_event):
                event = apply_time_shift(
                    play,
                    time_offset_beats=time_offset_beats,
                    time_offset_seconds=time_offset_seconds,
                    repeat_index=repeat_index,
                    loop_length_beats=float(loop_length_beats)
                    if loop_length_beats is not None
                    else None,
                    loop_length_seconds=float(loop_length_seconds)
                    if loop_length_seconds is not None
                    else None,
                )

                velocity = float(event.get("velocity", default_velocity)) * track_gain
                event["velocity"] = clamp(velocity, 0.0, 1.0)

                if BANKS[instrument].kind == "tonal":
                    if (
                        "duration_beats" not in event
                        and "duration_seconds" not in event
                    ):
                        if default_duration_seconds is not None:
                            event["duration_seconds"] = float(default_duration_seconds)
                        elif default_duration_beats is not None:
                            event["duration_beats"] = float(default_duration_beats)
                        else:
                            event["duration_beats"] = 1.0

                normalized_events.append(event)

    return {"instrument": instrument, "events": normalized_events}


def stem_sequence_from_config(
    stem_name: str,
    stem_config: Optional[Dict[str, Any]],
    tempo_bpm: float,
) -> Dict[str, Any]:
    config = stem_config or {}
    tracks = config.get("tracks", [])
    if tracks is None:
        tracks = []
    if not isinstance(tracks, list):
        raise RendererError(f"Stem '{stem_name}' must contain a 'tracks' array")

    sequence_tracks = [normalize_track_events(stem_name, track) for track in tracks]
    return {"tempo": tempo_bpm, "tracks": sequence_tracks}


def estimate_voices_end_seconds(voices: Sequence[Any]) -> float:
    max_end = 0.0
    for voice in voices:
        duration = float(voice.trim_end_seconds or 0.0)
        max_end = max(max_end, float(voice.start_seconds) + duration)
    return max_end


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
    audio_inputs: Sequence[Tuple[Path, float]],
    output_path: Path,
    master_gain: float = 1.0,
) -> None:
    if not audio_inputs:
        raise RendererError("No audio files provided for mixing")

    ffmpeg_inputs: List[str] = []
    filter_parts: List[str] = []
    labels: List[str] = []

    for index, (path, gain) in enumerate(audio_inputs):
        ffmpeg_inputs.extend(["-i", str(path)])
        label = f"[s{index}]"
        filter_parts.append(f"[{index}:a]volume={float(gain):.6f}{label}")
        labels.append(label)

    filter_parts.append(
        "".join(labels)
        + f"amix=inputs={len(labels)}:dropout_transition=0:normalize=0,volume={float(master_gain):.6f},alimiter=limit=0.97[out]"
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    run_command(
        (
            FFMPEG_BIN,
            "-y",
            *ffmpeg_inputs,
            "-filter_complex",
            ";".join(filter_parts),
            "-map",
            "[out]",
            str(output_path),
        )
    )


def arrangement_length_seconds(arrangement: Dict[str, Any], tempo_bpm: float) -> float:
    explicit_seconds = arrangement.get("length_seconds")
    if explicit_seconds is not None:
        return float(explicit_seconds)

    explicit_beats = arrangement.get("length_beats")
    if explicit_beats is not None:
        return beats_to_seconds(float(explicit_beats), tempo_bpm)

    return 0.0


def render_arrangement(
    arrangement: Dict[str, Any],
    output_dir: Path,
    asset_root: Path,
    source_arrangement_path: Optional[Path] = None,
) -> Dict[str, str]:
    tempo_bpm = float(arrangement.get("tempo", 85.0))
    name = str(arrangement.get("name", "playground-arrangement")).strip() or "playground-arrangement"
    stem_configs = extract_stem_map(arrangement)

    stem_voices: Dict[str, List[Any]] = {}
    stem_mix_gains: Dict[str, float] = {}
    master_gain = float(arrangement.get("master_gain", 1.0))
    duration_seconds = arrangement_length_seconds(arrangement, tempo_bpm)

    for stem_name in STEM_ORDER:
        stem_config = stem_configs.get(stem_name, {})
        sequence = stem_sequence_from_config(stem_name, stem_config, tempo_bpm)
        if sequence["tracks"]:
            voices = create_voices_from_sequence(sequence, asset_root)
        else:
            voices = []
        stem_voices[stem_name] = voices
        stem_mix_gains[stem_name] = float(stem_config.get("mix_gain", 1.0))
        duration_seconds = max(duration_seconds, estimate_voices_end_seconds(voices))

    if duration_seconds <= 0:
        raise RendererError("Arrangement has no playable content")

    output_dir.mkdir(parents=True, exist_ok=True)
    output_files: Dict[str, str] = {}
    stem_audio_inputs: List[Tuple[Path, float]] = []

    for stem_name in STEM_ORDER:
        stem_path = output_dir / f"{stem_name}.wav"
        voices = stem_voices[stem_name]
        if voices:
            render_voices(voices, stem_path)
        else:
            render_silence(duration_seconds, stem_path)
        output_files[stem_name] = str(stem_path)
        stem_audio_inputs.append((stem_path, stem_mix_gains[stem_name]))

    final_path = output_dir / f"{name}-full.wav"
    mix_audio_files(stem_audio_inputs, final_path, master_gain=master_gain)
    output_files["full_mix"] = str(final_path)

    if source_arrangement_path is not None:
        copied_input = output_dir / "input-arrangement.json"
        copied_input.write_text(
            source_arrangement_path.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        output_files["input_config"] = str(copied_input)

    manifest = {
        "name": name,
        "tempo": tempo_bpm,
        "duration_seconds": duration_seconds,
        "files": output_files,
        "stem_mix_gains": stem_mix_gains,
        "master_gain": master_gain,
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    output_files["manifest"] = str(manifest_path)
    return output_files


def render_arrangement_command(args: argparse.Namespace) -> None:
    arrangement_path = Path(args.arrangement).resolve()
    arrangement = load_json_file(arrangement_path)
    asset_root = resolve_asset_root(args.asset_root)
    output_dir = Path(args.output_dir).resolve()
    render_arrangement(
        arrangement,
        output_dir,
        asset_root,
        source_arrangement_path=arrangement_path,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render a multi-stem Ableton Learning Music Playground arrangement."
    )
    parser.add_argument("--arrangement", required=True, help="Arrangement JSON path")
    parser.add_argument("--output-dir", required=True, help="Directory for stem files and final mix")
    parser.add_argument(
        "--asset-root",
        help="Directory containing manifest.json and the beats/basslines/chords/melodies folders",
    )
    parser.set_defaults(func=render_arrangement_command)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
        return 0
    except RendererError as exc:
        print(f"Error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
