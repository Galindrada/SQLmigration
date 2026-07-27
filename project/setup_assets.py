import os
from PIL import Image, ImageDraw, ImageFont

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(PROJECT_DIR, "02_assets")


def build_test_environment():
    directories = [
        "01_raw_clips",
        "02_assets",
        "02_assets/kits",
        "02_assets/logos",
        "02_assets/players",
        "02_assets/music",
        "03_output",
        "04_game_segments",
    ]

    for directory in directories:
        path = os.path.join(PROJECT_DIR, directory)
        os.makedirs(path, exist_ok=True)
        print(f"Created: {path}")

    print("\n=== Asset folders (replace placeholders with your files) ===\n")
    print("PREVIA BACKGROUND:")
    print("  File: project/02_assets/base_background.png  (or .jpg / .webp)")
    print("  Size: 1920x1080 recommended (other sizes are cover-cropped)\n")
    print("PREVIA MUSIC (random 15s crop per previa):")
    print("  Folder: project/02_assets/music/")
    print("  Format: .mp3, .wav, .m4a, .ogg, .flac\n")
    print("JERSEYS (previa screen):")
    print("  Folder: project/02_assets/kits/")
    print("  Naming: {team_slug}.png  — same slug as home_team in config, lowercased")
    print("          Examples: inter.png, napoli.png, ac_milan.png")
    print("  Format: PNG with transparent background (recommended)")
    print("  Size:   ~400–800 px tall; full shirt visible; portrait aspect (~2:3)")
    print("  Note:   Delete old red/yellow test squares if present — they are ignored")
    print("          until the file is a real image (>20 KB).\n")
    print("TEAM CRESTS (goal overlay scorebar + previa):")
    print("  Folder: project/02_assets/logos/")
    print("  Naming: {team_slug}.png")
    print("  Format: PNG, square-ish, 256–512 px\n")
    print("PLAYER FACES (goal overlay):")
    print("  Folder: project/02_assets/players/")
    print("  Naming: {player_name}.jpg  e.g. gignac.jpg\n")
    print("OPENING / CLOSING (optional):")
    print("  project/02_assets/opening.mp4")
    print("  project/02_assets/closing.mp4\n")


if __name__ == "__main__":
    build_test_environment()
