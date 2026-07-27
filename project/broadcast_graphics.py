"""
Broadcast-style static frames (previa) and overlay helpers.
Renders 1920x1080 frames with PIL for a cleaner look than TextClip-only layouts.
"""

import glob
import os
from typing import Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

W, H = 1920, 1080

# Broadcast palette
BG_TOP = (8, 12, 28)
BG_BOTTOM = (18, 32, 68)
ACCENT = (255, 196, 0)  # goal overlays only
WHITE = (255, 255, 255)
MUTED = (160, 175, 200)
# Previa UI (readable on photo backgrounds — no yellow)
PREVIA_TITLE = (245, 248, 255)
PREVIA_SUBTITLE = (170, 210, 255)
PREVIA_CYAN = (90, 200, 255)
PREVIA_GLASS = (14, 22, 42, 168)
PREVIA_GLASS_EDGE = (120, 200, 255, 90)
# Export for pipeline (all segments target this resolution)
OUTPUT_SIZE = (W, H)

# Minimum bytes for a real jersey PNG (placeholders from setup are ~1.5 KB solids)
MIN_KIT_FILE_BYTES = 20_000

_FONT_CACHE = {}


def _project_root():
    return os.path.dirname(os.path.abspath(__file__))


def _asset(*parts):
    return os.path.join(_project_root(), "02_assets", *parts)


def _font_candidates(bold: bool) -> list:
    names = (
        ["DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf", "NotoSans-Bold.ttf",
         "Carlito-Bold.ttf", "DroidSans-Bold.ttf", "AdwaitaSans-Bold.ttf",
         "Ubuntu-B.ttf", "FreeSansBold.ttf"]
        if bold
        else ["DejaVuSans.ttf", "LiberationSans-Regular.ttf", "NotoSans-Regular.ttf",
              "Carlito-Regular.ttf", "DroidSans-Regular.ttf", "AdwaitaSans-Regular.ttf",
              "Ubuntu-R.ttf", "FreeSans.ttf"]
    )
    roots = [
        "/usr/share/fonts",
        "/usr/local/share/fonts",
        os.path.expanduser("~/.local/share/fonts"),
        os.path.expanduser("~/.fonts"),
    ]
    found = []
    for root in roots:
        if not os.path.isdir(root):
            continue
        for name in names:
            found.extend(glob.glob(os.path.join(root, "**", name), recursive=True))
    # Variable Noto on Fedora
    if bold:
        found.extend(glob.glob("/usr/share/fonts/google-noto-vf/NotoSans*.ttf"))
    return found


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    key = (size, bold)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]

    for path in _font_candidates(bold):
        try:
            font = ImageFont.truetype(path, size)
            _FONT_CACHE[key] = font
            return font
        except OSError:
            continue

    for path in glob.glob("/usr/share/fonts/**/*.ttf", recursive=True)[:80]:
        try:
            font = ImageFont.truetype(path, size)
            _FONT_CACHE[key] = font
            return font
        except OSError:
            continue

    font = ImageFont.load_default()
    _FONT_CACHE[key] = font
    return font


def previa_background_path() -> Optional[str]:
    """User background: project/02_assets/base_background.{png,jpg,...}"""
    for name in (
        "base_background.png",
        "base_background.jpg",
        "base_background.jpeg",
        "base_background.webp",
    ):
        path = _asset(name)
        if os.path.isfile(path):
            return path
    return None


def _gradient_background() -> Image.Image:
    img = Image.new("RGB", (W, H), BG_TOP)
    draw = ImageDraw.Draw(img)
    for y in range(H):
        t = y / max(H - 1, 1)
        r = int(BG_TOP[0] + (BG_BOTTOM[0] - BG_TOP[0]) * t)
        g = int(BG_TOP[1] + (BG_BOTTOM[1] - BG_TOP[1]) * t)
        b = int(BG_TOP[2] + (BG_BOTTOM[2] - BG_TOP[2]) * t)
        draw.line([(0, y), (W, y)], fill=(r, g, b))
    return img


def _load_previa_background() -> Image.Image:
    """Full-frame cover crop of base_background.*, else blue gradient."""
    path = previa_background_path()
    if path:
        try:
            bg = Image.open(path).convert("RGB")
            ow, oh = bg.size
            scale = max(W / ow, H / oh)
            nw, nh = max(1, int(ow * scale)), max(1, int(oh * scale))
            bg = bg.resize((nw, nh), Image.Resampling.LANCZOS)
            left = (nw - W) // 2
            top = (nh - H) // 2
            return bg.crop((left, top, left + W, top + H)).convert("RGBA")
        except OSError:
            pass
    return _gradient_background().convert("RGBA")


def _enhance_vivid(
    im: Image.Image,
    color: float = 1.38,
    contrast: float = 1.18,
    sharpness: float = 1.25,
) -> Image.Image:
    """Boost saturation/contrast for jerseys and crests."""
    im = im.convert("RGBA")
    r, g, b, a = im.split()
    rgb = Image.merge("RGB", (r, g, b))
    rgb = ImageEnhance.Color(rgb).enhance(color)
    rgb = ImageEnhance.Contrast(rgb).enhance(contrast)
    rgb = ImageEnhance.Sharpness(rgb).enhance(sharpness)
    r, g, b = rgb.split()
    return Image.merge("RGBA", (r, g, b, a))


def _drop_shadow_layer(
    base: Image.Image,
    box: Tuple[int, int, int, int],
    blur: int = 18,
    offset: Tuple[int, int] = (0, 10),
    opacity: int = 110,
) -> None:
    x0, y0, x1, y1 = box
    shadow = Image.new("RGBA", base.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    cx = (x0 + x1) // 2 + offset[0]
    cy = (y0 + y1) // 2 + offset[1]
    rw, rh = (x1 - x0) // 2 + 8, (y1 - y0) // 2 + 8
    sd.ellipse([cx - rw, cy - rh, cx + rw, cy + rh], fill=(0, 0, 0, opacity))
    shadow = shadow.filter(ImageFilter.GaussianBlur(blur))
    base.alpha_composite(shadow)


def _load_rgba(path: str) -> Optional[Image.Image]:
    if not path or not os.path.isfile(path):
        return None
    try:
        return Image.open(path).convert("RGBA")
    except OSError:
        return None


def _paste_rgba_image(
    base: Image.Image,
    overlay: Image.Image,
    box: Tuple[int, int, int, int],
) -> None:
    x0, y0, x1, y1 = box
    tw, th = x1 - x0, y1 - y0
    ow, oh = overlay.size
    scale = min(tw / ow, th / oh)
    nw, nh = max(1, int(ow * scale)), max(1, int(oh * scale))
    overlay = overlay.resize((nw, nh), Image.Resampling.LANCZOS)
    px = x0 + (tw - nw) // 2
    py = y0 + (th - nh) // 2
    base.paste(overlay, (px, py), overlay)


def _paste_contain(
    base: Image.Image,
    path: str,
    box: Tuple[int, int, int, int],
    vivid: bool = False,
    shadow: bool = False,
) -> None:
    overlay = _load_rgba(path)
    if overlay is None:
        return
    if vivid:
        overlay = _enhance_vivid(overlay)
    if shadow:
        _drop_shadow_layer(base, box)
    x0, y0, x1, y1 = box
    tw, th = x1 - x0, y1 - y0
    ow, oh = overlay.size
    scale = min(tw / ow, th / oh)
    nw, nh = max(1, int(ow * scale)), max(1, int(oh * scale))
    overlay = overlay.resize((nw, nh), Image.Resampling.LANCZOS)
    px = x0 + (tw - nw) // 2
    py = y0 + (th - nh) // 2
    base.paste(overlay, (px, py), overlay)


def _paste_square_cover(
    base: Image.Image,
    path: str,
    box: Tuple[int, int, int, int],
    vivid: bool = True,
    corner_radius: int = 10,
) -> None:
    """Center-crop to square, fill box (for player headshots)."""
    overlay = _load_rgba(path)
    if overlay is None:
        return
    if vivid:
        overlay = _enhance_vivid(overlay, color=1.22, contrast=1.12, sharpness=1.15)

    x0, y0, x1, y1 = box
    size = min(x1 - x0, y1 - y0)
    ow, oh = overlay.size
    side = min(ow, oh)
    left = (ow - side) // 2
    top = (oh - side) // 2
    overlay = overlay.crop((left, top, left + side, top + side))
    overlay = overlay.resize((size, size), Image.Resampling.LANCZOS)

    if corner_radius > 0:
        mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, size, size), corner_radius, fill=255)
        overlay.putalpha(mask)

    px = x0 + (x1 - x0 - size) // 2
    py = y0 + (y1 - y0 - size) // 2
    base.paste(overlay, (px, py), overlay)


def _rounded_rect(draw, xy, radius, fill):
    draw.rounded_rectangle(xy, radius=radius, fill=fill)


def _draw_glass_panel(
    img: Image.Image,
    box: Tuple[int, int, int, int],
    radius: int = 22,
    accent_left: bool = False,
) -> None:
    """Clean panel — no full-frame blur glow."""
    x0, y0, x1, y1 = box
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    ld.rounded_rectangle(box, radius, fill=PREVIA_GLASS)
    ld.rounded_rectangle(box, radius, outline=PREVIA_GLASS_EDGE, width=2)
    if accent_left:
        ld.rounded_rectangle((x0, y0 + 12, x0 + 5, y1 - 12), 3, fill=(*PREVIA_CYAN[:3], 200))
    img.alpha_composite(layer)


def _team_slug(team: str) -> str:
    return team.strip().lower().replace(" ", "_")


def team_logo_path(team: str) -> str:
    slug = _team_slug(team)
    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        path = _asset("logos", f"{slug}{ext}")
        if os.path.isfile(path):
            return path
    return _asset("logos", f"{slug}.png")


def team_kit_path(team: str) -> str:
    slug = _team_slug(team)
    for ext in (".png", ".webp", ".jpg", ".jpeg"):
        path = _asset("kits", f"{slug}{ext}")
        if os.path.isfile(path):
            return path
    return _asset("kits", f"{slug}.png")


def kit_is_real_asset(path: str) -> bool:
    """Ignore tiny solid-color placeholders; only show real jersey images."""
    if not path or not os.path.isfile(path):
        return False
    if os.path.getsize(path) < MIN_KIT_FILE_BYTES:
        return False
    try:
        with Image.open(path) as im:
            im = im.convert("RGBA")
            if max(im.size) < 200:
                return False
            # Solid placeholder squares have very few distinct colors
            colors = im.resize((64, 64)).getcolors(maxcolors=64)
            if colors and len(colors) <= 3:
                return False
    except OSError:
        return False
    return True


def player_image_path(scorer: str) -> Optional[str]:
    name = scorer.split("(")[0].strip().lower().replace(" ", "_")
    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        path = _asset("players", f"{name}{ext}")
        if os.path.isfile(path):
            return path
    return None


def format_score(home_score: int, away_score: int) -> str:
    return f"{home_score}  –  {away_score}"


_HOME_KIT_BOX = (110, 420, 510, 760)
_AWAY_KIT_BOX = (W - 510, 420, W - 110, 760)


def render_previa_frame(
    home_team: str,
    away_team: str,
    stadium: str,
    referee: str,
    competition: str = "",
    home_kit_path: Optional[str] = None,
    away_kit_path: Optional[str] = None,
) -> np.ndarray:
    """Kickoff previa card (0–0). Returns RGB numpy array for MoviePy."""
    img = _load_previa_background()
    draw = ImageDraw.Draw(img)

    font_title = _load_font(58, bold=True)
    font_big = _load_font(110, bold=True)
    font_team = _load_font(68, bold=True)
    font_score = _load_font(130, bold=True)
    font_meta = _load_font(44)
    font_label = _load_font(52, bold=True)

    # Competition header — glass pill, light text
    _draw_glass_panel(img, (60, 36, W - 60, 132), radius=18)
    comp_text = (competition or "MATCHDAY HIGHLIGHTS").upper()
    bbox = draw.textbbox((0, 0), comp_text, font=font_title)
    tw = bbox[2] - bbox[0]
    draw.text(((W - tw) // 2, 52), comp_text, fill=PREVIA_TITLE, font=font_title)

    draw.text((W // 2, 178), "PRÉVIA", fill=PREVIA_SUBTITLE, font=font_label, anchor="mm")

    # Team side cards
    _draw_glass_panel(img, (80, 210, 540, 800), radius=26, accent_left=True)
    _draw_glass_panel(img, (W - 540, 210, W - 80, 800), radius=26, accent_left=False)

    home_kit_file = home_kit_path or team_kit_path(home_team)
    away_kit_file = away_kit_path or team_kit_path(away_team)
    home_logo = team_logo_path(home_team)
    away_logo = team_logo_path(away_team)

    _paste_contain(img, home_logo, (120, 240, 500, 400), vivid=True, shadow=True)
    _paste_contain(img, away_logo, (W - 500, 240, W - 120, 400), vivid=True, shadow=True)

    if kit_is_real_asset(home_kit_file):
        _drop_shadow_layer(img, _HOME_KIT_BOX)
        _paste_contain(img, home_kit_file, _HOME_KIT_BOX, vivid=True)
    else:
        _paste_contain(img, home_logo, (140, 450, 480, 730), vivid=True, shadow=True)

    if kit_is_real_asset(away_kit_file):
        _drop_shadow_layer(img, _AWAY_KIT_BOX)
        _paste_contain(img, away_kit_file, _AWAY_KIT_BOX, vivid=True)
    else:
        _paste_contain(img, away_logo, (W - 480, 450, W - 140, 730), vivid=True, shadow=True)

    # Center score card
    _draw_glass_panel(img, (700, 290, 1220, 710), radius=30)
    draw.text((W // 2, 388), "VS", fill=PREVIA_CYAN, font=font_big, anchor="mm")
    draw.text((W // 2, 518), "0  –  0", fill=PREVIA_TITLE, font=font_score, anchor="mm")
    draw.text((W // 2, 638), "KICK OFF", fill=MUTED, font=font_meta, anchor="mm")

    # Plain team names (no glow effect)
    draw.text((310, 850), home_team.upper(), fill=PREVIA_TITLE, font=font_team, anchor="mm")
    draw.text((W - 310, 850), away_team.upper(), fill=PREVIA_TITLE, font=font_team, anchor="mm")

    _draw_glass_panel(img, (100, 918, W - 100, 1022), radius=14)
    meta = f"{stadium}   ·   ÁRBITRO: {referee}"
    draw.text((W // 2, 970), meta, fill=MUTED, font=font_meta, anchor="mm")

    return np.array(img.convert("RGB"))


def render_goal_overlay_frame(
    home_team: str,
    away_team: str,
    home_score: int,
    away_score: int,
    scorer: str,
    minute: str,
    scoring_team: str,
    width: int,
    height: int,
) -> np.ndarray:
    """
    Top-right overlay: crests + score, then compact goal line (scorer + minute).
    """
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    font_score = _load_font(34, bold=True)
    font_scorer = _load_font(22, bold=True)
    font_min = _load_font(18, bold=True)
    font_tag = _load_font(16, bold=True)

    score_text = format_score(home_score, away_score)
    is_home_goal = scoring_team.lower() in ("home", "h", home_team.lower())

    margin = 22
    logo_box = 44
    pad_x = 10
    pad_y = 7

    score_bbox = draw.textbbox((0, 0), score_text, font=font_score)
    score_w = score_bbox[2] - score_bbox[0]
    score_h = score_bbox[3] - score_bbox[1]

    bar_w = pad_x * 2 + logo_box + 12 + score_w + 12 + logo_box
    bar_h = pad_y * 2 + max(score_h, logo_box)
    bar_x1 = width - margin
    bar_x0 = bar_x1 - bar_w
    bar_y0 = margin

    _rounded_rect(draw, (bar_x0, bar_y0, bar_x1, bar_y0 + bar_h), 10, (0, 0, 0, 200))

    home_logo_x0 = bar_x0 + pad_x
    home_logo_y0 = bar_y0 + (bar_h - logo_box) // 2
    _paste_contain(
        img,
        team_logo_path(home_team),
        (home_logo_x0, home_logo_y0, home_logo_x0 + logo_box, home_logo_y0 + logo_box),
        vivid=True,
    )

    score_x = home_logo_x0 + logo_box + 12
    score_y = bar_y0 + (bar_h - score_h) // 2 - score_bbox[1]
    score_color = ACCENT if is_home_goal else WHITE
    draw.text((score_x, score_y), score_text, fill=score_color, font=font_score)

    away_logo_x0 = score_x + score_w + 12
    _paste_contain(
        img,
        team_logo_path(away_team),
        (away_logo_x0, home_logo_y0, away_logo_x0 + logo_box, home_logo_y0 + logo_box),
        vivid=True,
    )

    if is_home_goal:
        _rounded_rect(draw, (bar_x0, bar_y0, bar_x0 + 5, bar_y0 + bar_h), 3, (*ACCENT[:3], 255))
    else:
        _rounded_rect(draw, (bar_x1 - 5, bar_y0, bar_x1, bar_y0 + bar_h), 3, (*ACCENT[:3], 255))

    minute_clean = minute if minute else ""
    if minute_clean and not minute_clean.endswith("'"):
        minute_clean += "'"

    face = 76
    pad_goal = 8
    goal_y0 = bar_y0 + bar_h + 6
    goal_x1 = bar_x1

    scorer_line = scorer.split("(")[0].strip().upper()
    tag_bbox = draw.textbbox((0, 0), "GOL", font=font_tag)
    name_bbox = draw.textbbox((0, 0), scorer_line, font=font_scorer)
    text_block_h = (tag_bbox[3] - tag_bbox[1]) + (name_bbox[3] - name_bbox[1]) + 4
    goal_h = max(face + pad_goal * 2, text_block_h + pad_goal * 2)

    text_w = max(name_bbox[2] - name_bbox[0], tag_bbox[2] - tag_bbox[0])
    goal_w = pad_goal + face + 10 + text_w + 48  # room for minute
    goal_x0 = goal_x1 - max(goal_w, bar_w)

    _rounded_rect(draw, (goal_x0, goal_y0, goal_x1, goal_y0 + goal_h), 8, (10, 20, 50, 225))

    face_x0 = goal_x0 + pad_goal
    face_y0 = goal_y0 + (goal_h - face) // 2
    player_path = player_image_path(scorer)
    if player_path:
        _paste_square_cover(
            img, player_path, (face_x0, face_y0, face_x0 + face, face_y0 + face), vivid=True
        )
    else:
        draw.rounded_rectangle(
            (face_x0, face_y0, face_x0 + face, face_y0 + face), radius=10, fill=(40, 55, 90, 255)
        )
        initials = "".join(p[0] for p in scorer.split()[:2]).upper() or "?"
        draw.text(
            (face_x0 + face // 2, face_y0 + face // 2),
            initials,
            fill=WHITE,
            font=font_scorer,
            anchor="mm",
        )

    text_x = face_x0 + face + 10
    text_y0 = goal_y0 + (goal_h - text_block_h) // 2
    draw.text((text_x, text_y0), "GOL", fill=ACCENT, font=font_tag)
    draw.text((text_x, text_y0 + (tag_bbox[3] - tag_bbox[1]) + 2), scorer_line, fill=WHITE, font=font_scorer)
    if minute_clean:
        draw.text((goal_x1 - 10, goal_y0 + goal_h // 2), minute_clean, fill=MUTED, font=font_min, anchor="rm")

    return np.array(img)
