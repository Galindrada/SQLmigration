"""
Matchday highlight pipeline.

Modes (from project/ directory):
  python main_pipeline.py build     — previa + per-goal overlays from matchday_config.json
  python main_pipeline.py assemble  — opening + finished segments + closing
"""

import argparse
import json
import os
import random
import sys

import PIL.Image

if not hasattr(PIL.Image, "ANTIALIAS"):
    PIL.Image.ANTIALIAS = PIL.Image.Resampling.LANCZOS

from moviepy.editor import AudioFileClip
from moviepy.video.VideoClip import ImageClip
from moviepy.video.compositing.CompositeVideoClip import CompositeVideoClip
from moviepy.video.compositing.concatenate import concatenate_videoclips
from moviepy.video.fx.resize import resize
from moviepy.video.io.VideoFileClip import VideoFileClip

from broadcast_graphics import (
    W,
    H,
    format_score,
    player_image_path,
    render_goal_overlay_frame,
    render_previa_frame,
    team_kit_path,
)

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
RAW_CLIPS = os.path.join(PROJECT_DIR, "01_raw_clips")
OUTPUT_DIR = os.path.join(PROJECT_DIR, "03_output")
MUSIC_DIR = os.path.join(PROJECT_DIR, "02_assets", "music")
SFX_DIR = os.path.join(PROJECT_DIR, "02_assets", "sfx")
CONFIG_PATH = os.path.join(PROJECT_DIR, "matchday_config.json")

FPS = 30
PREVIA_DURATION = 10.0
DEFAULT_TRANSITION_SEC = 0.55
MUSIC_EXTENSIONS = (".mp3", ".wav", ".m4a", ".ogg", ".flac")


def _resolve(path: str) -> str:
    if os.path.isabs(path):
        return path
    return os.path.join(PROJECT_DIR, path)


def _transition_duration(config: dict) -> float:
    show = config.get("show") or {}
    return float(show.get("transition_seconds", DEFAULT_TRANSITION_SEC))


def normalize_to_broadcast(clip):
    """Scale + center-crop every clip to 1920x1080 (matches previa)."""
    w, h = clip.size
    if w == W and h == H:
        return clip
    scale = max(W / w, H / h)
    nw, nh = int(w * scale), int(h * scale)
    clip = resize(clip, (nw, nh))
    x0 = max(0, (nw - W) // 2)
    y0 = max(0, (nh - H) // 2)
    return clip.crop(x1=x0, y1=y0, x2=x0 + W, y2=y0 + H)


def _apply_segment_fades(clip, fade_in: float, fade_out: float):
    if fade_in > 0:
        clip = clip.crossfadein(fade_in)
    if fade_out > 0:
        clip = clip.crossfadeout(fade_out)
    if clip.audio is not None:
        audio = clip.audio
        if fade_in > 0:
            audio = audio.audio_fadein(fade_in)
        if fade_out > 0:
            audio = audio.audio_fadeout(fade_out)
        clip = clip.set_audio(audio)
    return clip


def concatenate_with_transitions(clips, transition: float):
    """Video + audio crossfade between segments."""
    if not clips:
        return None
    if len(clips) == 1:
        return clips[0]

    transition = max(0.1, min(transition, 2.0))
    prepared = []
    for i, clip in enumerate(clips):
        fin = transition if i > 0 else 0
        fout = transition if i < len(clips) - 1 else 0
        prepared.append(_apply_segment_fades(clip, fin, fout))

    return concatenate_videoclips(prepared, method="compose", padding=-transition)


def _list_music_files() -> list:
    if not os.path.isdir(MUSIC_DIR):
        return []
    return sorted(
        os.path.join(MUSIC_DIR, name)
        for name in os.listdir(MUSIC_DIR)
        if name.lower().endswith(MUSIC_EXTENSIONS)
    )


def _crop_music_to_duration(duration: float):
    tracks = _list_music_files()
    if not tracks:
        return None, None

    path = random.choice(tracks)
    audio = AudioFileClip(path)
    try:
        if audio.duration <= duration:
            segment = audio.subclip(0, audio.duration)
            if segment.duration < duration - 0.05:
                segment = segment.audio_loop(duration=duration)
            else:
                segment = segment.set_duration(duration)
        else:
            max_start = max(0.0, audio.duration - duration)
            start = random.uniform(0.0, max_start) if max_start > 0 else 0.0
            segment = audio.subclip(start, start + duration)
        return segment.set_duration(duration), path
    except Exception:
        audio.close()
        raise


def generate_previa_clip(game: dict, duration: float = PREVIA_DURATION):
    """One kickoff previa per fixture (1920x1080 + optional music)."""
    frame = render_previa_frame(
        home_team=game["home_team"],
        away_team=game["away_team"],
        stadium=game.get("stadium", ""),
        referee=game.get("referee", ""),
        competition=game.get("competition", ""),
        home_kit_path=_resolve(game["home_kit"]) if game.get("home_kit") else team_kit_path(game["home_team"]),
        away_kit_path=_resolve(game["away_kit"]) if game.get("away_kit") else team_kit_path(game["away_team"]),
    )
    clip = ImageClip(frame).set_duration(duration).set_fps(FPS)

    music, music_path = _crop_music_to_duration(duration)
    if music is not None:
        print(f"    Previa music: {os.path.basename(music_path)} ({duration:.1f}s)")
        clip = clip.set_audio(music)
    else:
        print("    Previa: no audio in 02_assets/music/", file=sys.stderr)

    return normalize_to_broadcast(clip)


def apply_goal_overlay(
    gameplay_video_path: str,
    home_team: str,
    away_team: str,
    home_score: int,
    away_score: int,
    scorer: str,
    minute: str = "",
    scoring_team: str = "home",
):
    """Gameplay at full 1920x1080 with broadcast overlay."""
    clip = VideoFileClip(gameplay_video_path)
    clip = normalize_to_broadcast(clip)

    overlay_rgba = render_goal_overlay_frame(
        home_team=home_team,
        away_team=away_team,
        home_score=home_score,
        away_score=away_score,
        scorer=scorer,
        minute=minute,
        scoring_team=scoring_team,
        width=W,
        height=H,
    )

    rgb = overlay_rgba[:, :, :3]
    alpha = overlay_rgba[:, :, 3] / 255.0
    overlay_clip = (
        ImageClip(rgb)
        .set_duration(clip.duration)
        .set_fps(clip.fps or FPS)
        .set_mask(
            ImageClip(alpha, ismask=True)
            .set_duration(clip.duration)
            .set_fps(clip.fps or FPS)
        )
    )

    return CompositeVideoClip([clip, overlay_clip], size=(W, H))


def build_game_package(game: dict, game_index: int) -> list:
    home = game["home_team"]
    away = game["away_team"]
    goals = game.get("goals") or []

    print(f"  Fixture: {home} vs {away} ({len(goals)} goal(s))")
    previa_duration = float(game.get("previa_duration", PREVIA_DURATION))
    segments = [generate_previa_clip(game, duration=previa_duration)]

    for i, goal in enumerate(goals, start=1):
        raw_name = goal["video_filename"]
        raw_path = raw_name if os.path.isabs(raw_name) else os.path.join(RAW_CLIPS, raw_name)
        if not os.path.isfile(raw_path):
            print(f"    WARNING: missing clip {raw_path}", file=sys.stderr)
            continue

        home_score = int(goal["home_score"])
        away_score = int(goal["away_score"])
        scorer = goal.get("scorer", "Unknown")
        minute = goal.get("minute", "")
        scoring_team = goal.get("scoring_team", "home")

        print(
            f"    Goal {i}: {scorer} @ {minute or '?'} "
            f"({format_score(home_score, away_score)}) <- {raw_name}"
        )
        if not player_image_path(scorer):
            print(f"      (no player image in 02_assets/players for '{scorer}')")

        segments.append(
            apply_goal_overlay(
                gameplay_video_path=raw_path,
                home_team=home,
                away_team=away,
                home_score=home_score,
                away_score=away_score,
                scorer=scorer,
                minute=minute,
                scoring_team=scoring_team,
            )
        )

    return segments


def run_build(config: dict, output_name: str = "matchday_show_final.mp4") -> str:
    all_segments = []

    for idx, game in enumerate(config.get("games", []), start=1):
        print(f"Game {idx}/{len(config.get('games', []))}")
        all_segments.extend(build_game_package(game, idx))

    if not all_segments:
        print("No segments to render. Check matchday_config.json 'games' and goal clips.", file=sys.stderr)
        sys.exit(1)

    transition = _transition_duration(config)
    print(f"Concatenating {len(all_segments)} segments (transition={transition}s, {W}x{H})")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(OUTPUT_DIR, output_name)
    final = concatenate_with_transitions(all_segments, transition)
    final.write_videofile(out_path, fps=FPS, codec="libx264", audio_codec="aac")
    print(f"Built: {out_path}")
    return out_path


def run_assemble(config: dict, output_name: str = "matchday_show_final.mp4") -> str:
    show = config.get("show", {})
    paths = []

    opening = show.get("opening")
    if opening:
        paths.append(_resolve(opening))

    for seg in show.get("segments") or []:
        paths.append(_resolve(seg))

    closing = show.get("closing")
    if closing:
        paths.append(_resolve(closing))

    if not paths:
        print("Nothing to assemble.", file=sys.stderr)
        sys.exit(1)

    clips = []
    for p in paths:
        if not os.path.isfile(p):
            print(f"WARNING: missing {p}", file=sys.stderr)
            continue
        clips.append(normalize_to_broadcast(VideoFileClip(p)))

    if not clips:
        sys.exit(1)

    transition = _transition_duration(config)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(OUTPUT_DIR, output_name)
    concatenate_with_transitions(clips, transition).write_videofile(
        out_path, fps=FPS, codec="libx264", audio_codec="aac"
    )
    print(f"Assembled: {out_path}")
    return out_path


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser(description="Matchday highlight pipeline")
    parser.add_argument(
        "command",
        nargs="?",
        default="build",
        choices=("build", "assemble", "all"),
    )
    parser.add_argument("-o", "--output", default="matchday_show_final.mp4")
    args = parser.parse_args()

    os.chdir(PROJECT_DIR)
    config = load_config()

    if args.command == "build":
        run_build(config, args.output)
    elif args.command == "assemble":
        run_assemble(config, args.output)
    elif args.command == "all":
        run_build(config, "matchday_built.mp4")
        show = config.setdefault("show", {})
        if not show.get("segments"):
            show["segments"] = ["03_output/matchday_built.mp4"]
        run_assemble(config, args.output)


if __name__ == "__main__":
    main()
