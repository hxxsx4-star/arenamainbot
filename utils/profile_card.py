"""프로필 카드 이미지 생성 (/프로필, /레벨).

1024x1024 정사각 카드:
  · 좌상단 원형 프레임 = 서버 프로필 사진 (보라 링 + 다이아 장식)
  · 우측 상단 = "GAME ARENA" 라벨 + 서버 닉네임 + 슬로건
  · 중단 4패널 = 음성 레벨(순위) / 채팅 레벨(순위) / 롤 솔랭 티어 / 발로 경쟁 티어
    (티어는 보유한 티어 역할 기준, 색상 엠블럼으로 표시)
  · 하단 바 = 보유 포인트
배경은 profile_bg.png (성 이미지) 를 그대로 사용.
"""
import io
import os
import asyncio
import math

import aiohttp
import discord
from PIL import Image, ImageDraw, ImageFilter

from utils.stats import (get_xp, get_voice_xp, get_points, get_rank, level_from_xp)
from utils.tiers import get_tier_info
from utils.tier_assets import get_tier_icon

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TITLE_FONT = os.path.join(BASE_DIR, "font.ttf")     # 나눔스퀘어라운드 Bold
UI_FONT = os.path.join(BASE_DIR, "font_ui.ttf")     # 나눔스퀘어라운드 Regular
BG_PATH = os.path.join(BASE_DIR, "profile_bg.png")

W = H = 1024
LAVENDER = (205, 190, 255)
LAVENDER_DIM = (170, 155, 220)
PURPLE = (155, 120, 255)
WHITE = (245, 243, 255)
BLACK = (8, 4, 20)
PANEL_BG = (16, 9, 38, 208)
VOICE_ACCENT = (167, 139, 250)
CHAT_ACCENT = (96, 165, 250)
GOLD = (255, 205, 90)

from PIL import ImageFont


def _font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def _fit_font(draw, text, path, max_w, start_size, min_size=28):
    for size in range(start_size, min_size - 1, -2):
        f = _font(path, size)
        if draw.textlength(text, font=f) <= max_w:
            return f
    return _font(path, min_size)


def _spaced_text(draw, center_x, y, text, font, fill, spacing=6, stroke=0, stroke_fill=None):
    """글자 사이 간격을 두고 중앙 정렬로 그린다."""
    widths = [draw.textlength(ch, font=font) for ch in text]
    total = sum(widths) + spacing * (len(text) - 1)
    x = center_x - total / 2
    for ch, w in zip(text, widths):
        draw.text((x, y), ch, font=font, fill=fill,
                  stroke_width=stroke, stroke_fill=stroke_fill)
        x += w + spacing


def _diamond(draw, cx, cy, r, fill, outline=None, width=2):
    pts = [(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)]
    draw.polygon(pts, fill=fill, outline=outline, width=width)


def _hexagon(cx, cy, r):
    """pointy-top 육각형 좌표."""
    return [(cx + r * math.sin(math.radians(a)), cy - r * math.cos(math.radians(a)))
            for a in range(0, 360, 60)]


def _tier_badge(draw, cx, cy, size, color):
    """티어 엠블럼: 육각 방패 + 이중 테두리 + 쉐브론."""
    dark = (14, 8, 34, 235)
    # 뒤 글로우
    glow = tuple(list(color) + [70])
    draw.polygon(_hexagon(cx, cy, size + 7), fill=glow)
    # 본체 + 테두리
    draw.polygon(_hexagon(cx, cy, size), fill=dark, outline=tuple(color), width=5)
    draw.polygon(_hexagon(cx, cy, size - 12), outline=tuple(list(color) + [110]), width=2)
    # 쉐브론(∨ 2개)
    cw, ch, gap = size * 0.52, size * 0.30, size * 0.34
    for i in range(2):
        oy = cy - size * 0.22 + i * gap
        draw.line([(cx - cw, oy), (cx, oy + ch), (cx + cw, oy)],
                  fill=tuple(color), width=int(max(5, size * 0.11)), joint="curve")


def _panel(img, draw, x, y, w, h, accent):
    draw.rounded_rectangle([x, y, x + w, y + h], radius=20, fill=PANEL_BG,
                           outline=tuple(list(accent) + [200]), width=2)
    # 상단 얇은 액센트 라인
    draw.line([(x + 18, y + 3), (x + w - 18, y + 3)], fill=tuple(list(accent) + [120]), width=2)


def generate_profile_image(avatar_bytes, name, chat_xp, voice_xp, points,
                           chat_rank=None, voice_rank=None,
                           lol_tier=("언랭크", (120, 125, 140), None),
                           val_tier=("언랭크", (120, 125, 140), None)):
    """lol_tier/val_tier = (한글 티어명, 대표색, 아이콘 파일 경로 또는 None)."""
    # ---------- 배경 ----------
    try:
        bg = Image.open(BG_PATH).convert("RGBA")
    except Exception:
        bg = Image.new("RGBA", (W, H), (26, 15, 46, 255))
    # cover 크롭 → 정사각
    ratio = max(W / bg.width, H / bg.height)
    bg = bg.resize((int(bg.width * ratio) + 1, int(bg.height * ratio) + 1), Image.LANCZOS)
    left, top = (bg.width - W) // 2, (bg.height - H) // 2
    bg = bg.crop((left, top, left + W, top + H))
    bg = Image.alpha_composite(bg, Image.new("RGBA", (W, H), (10, 5, 28, 96)))
    # 하단을 조금 더 어둡게 (패널 가독성)
    grad = Image.new("L", (1, H))
    for yy in range(H):
        grad.putpixel((0, yy), int(max(0, (yy - 380) / (H - 380)) * 120) if yy > 380 else 0)
    dark = Image.new("RGBA", (W, H), (8, 4, 24, 255))
    dark.putalpha(grad.resize((W, H)))
    bg = Image.alpha_composite(bg, dark)

    img = bg
    draw = ImageDraw.Draw(img, "RGBA")

    # 외곽 라운드 보더
    draw.rounded_rectangle([6, 6, W - 7, H - 7], radius=38,
                           outline=(150, 110, 230, 200), width=3)
    draw.rounded_rectangle([12, 12, W - 13, H - 13], radius=34,
                           outline=(90, 60, 160, 120), width=1)

    # ---------- 아바타 (좌상단 원형 프레임) ----------
    AX, AY, AR = 250, 258, 158   # 중심/반지름
    # 글로우
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([AX - AR - 18, AY - AR - 18, AX + AR + 18, AY + AR + 18],
               outline=(160, 110, 255, 160), width=14)
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(10)))

    if avatar_bytes:
        try:
            av = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
            av = av.resize((AR * 2, AR * 2), Image.LANCZOS)
            mask = Image.new("L", (AR * 2, AR * 2), 0)
            ImageDraw.Draw(mask).ellipse([0, 0, AR * 2, AR * 2], fill=255)
            img.paste(av, (AX - AR, AY - AR), mask)
        except Exception:
            pass
    # 이중 링
    draw.ellipse([AX - AR - 4, AY - AR - 4, AX + AR + 4, AY + AR + 4],
                 outline=(30, 18, 58), width=9)
    draw.ellipse([AX - AR - 10, AY - AR - 10, AX + AR + 10, AY + AR + 10],
                 outline=PURPLE, width=5)
    draw.ellipse([AX - AR - 16, AY - AR - 16, AX + AR + 16, AY + AR + 16],
                 outline=(90, 60, 160), width=2)
    # 다이아 장식 (상/하/좌/우)
    for dx, dy in [(0, -AR - 10), (0, AR + 10), (-AR - 10, 0), (AR + 10, 0)]:
        _diamond(draw, AX + dx, AY + dy, 16, fill=(40, 24, 74), outline=PURPLE, width=3)
        _diamond(draw, AX + dx, AY + dy, 6, fill=LAVENDER)

    # ---------- 우측 텍스트 ----------
    TCX = 712  # 우측 블록 중심
    # 텍스트 가독성을 위한 부드러운 그림자 패널
    soft = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(soft).rounded_rectangle(
        [TCX - 270, 96, TCX + 270, 346], radius=40, fill=(10, 5, 28, 150))
    img.alpha_composite(soft.filter(ImageFilter.GaussianBlur(26)))

    f_label = _font(UI_FONT, 30)
    _diamond(draw, TCX - 205, 152, 8, fill=PURPLE)
    _diamond(draw, TCX + 205, 152, 8, fill=PURPLE)
    _spaced_text(draw, TCX, 134, "GAME ARENA", f_label, LAVENDER, spacing=12,
                 stroke=1, stroke_fill=BLACK)

    f_name = _fit_font(draw, name, TITLE_FONT, 470, 96, 40)
    draw.text((TCX, 236), name, font=f_name, fill=WHITE, anchor="mm",
              stroke_width=4, stroke_fill=(50, 25, 95))
    f_slog = _font(UI_FONT, 24)
    _spaced_text(draw, TCX, 306, "PLAY TOGETHER, WIN TOGETHER.", f_slog,
                 LAVENDER_DIM, spacing=2, stroke=1, stroke_fill=BLACK)

    # ---------- 중단 4패널 ----------
    PW, PH, GAP = 219, 300, 17
    total = PW * 4 + GAP * 3
    x0 = (W - total) // 2
    PY = 452

    f_ptitle = _font(TITLE_FONT, 30)
    f_big = _font(TITLE_FONT, 92)
    f_rank = _font(UI_FONT, 26)
    f_tname = _font(TITLE_FONT, 32)

    chat_lv, voice_lv = level_from_xp(chat_xp), level_from_xp(voice_xp)

    def level_panel(idx, label, lv, rank, accent):
        x = x0 + idx * (PW + GAP)
        _panel(img, draw, x, PY, PW, PH, accent)
        cx = x + PW // 2
        draw.text((cx, PY + 46), label, font=f_ptitle, fill=WHITE, anchor="mm",
                  stroke_width=2, stroke_fill=BLACK)
        draw.text((cx, PY + 148), str(lv), font=f_big, fill=accent, anchor="mm",
                  stroke_width=3, stroke_fill=BLACK)
        rank_txt = f"순위  # {rank}" if rank else "순위  -"
        draw.text((cx, PY + 252), rank_txt, font=f_rank, fill=LAVENDER_DIM, anchor="mm",
                  stroke_width=1, stroke_fill=BLACK)

    def tier_panel(idx, label, tier):
        tname, tcolor, icon_path = (tier + (None,))[:3]
        x = x0 + idx * (PW + GAP)
        _panel(img, draw, x, PY, PW, PH, tcolor)
        cx = x + PW // 2
        draw.text((cx, PY + 46), label, font=f_ptitle, fill=WHITE, anchor="mm",
                  stroke_width=2, stroke_fill=BLACK)
        pasted = False
        if icon_path:
            try:
                icon = Image.open(icon_path).convert("RGBA")
                # 라이엇 원본은 투명 여백이 매우 큼 → 실제 문양 영역만 잘라 크게 표시
                bbox = icon.getchannel("A").getbbox()
                if bbox:
                    icon = icon.crop(bbox)
                icon.thumbnail((172, 172), Image.LANCZOS)
                # 은은한 글로우 후 중앙 부착
                halo = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                hd = ImageDraw.Draw(halo)
                hd.ellipse([cx - 72, PY + 152 - 72, cx + 72, PY + 152 + 72],
                           fill=tuple(list(tcolor) + [70]))
                img.alpha_composite(halo.filter(ImageFilter.GaussianBlur(18)))
                img.alpha_composite(icon, (cx - icon.width // 2, PY + 152 - icon.height // 2))
                pasted = True
            except Exception:
                pasted = False
        if not pasted:
            _tier_badge(draw, cx, PY + 152, 62, tcolor)
        draw.text((cx, PY + 252), tname, font=f_tname, fill=tcolor, anchor="mm",
                  stroke_width=2, stroke_fill=BLACK)

    level_panel(0, "음성 레벨", voice_lv, voice_rank, VOICE_ACCENT)
    level_panel(1, "채팅 레벨", chat_lv, chat_rank, CHAT_ACCENT)
    tier_panel(2, "롤 솔랭 티어", lol_tier)
    tier_panel(3, "발로 경쟁 티어", val_tier)

    # ---------- 하단 포인트 바 ----------
    BY, BH = 796, 150
    draw.rounded_rectangle([x0, BY, x0 + total, BY + BH], radius=24, fill=PANEL_BG,
                           outline=(150, 110, 230, 200), width=2)
    # 보석 아이콘
    gx, gy = x0 + 82, BY + BH // 2
    _diamond(draw, gx, gy, 40, fill=(60, 34, 110), outline=PURPLE, width=4)
    _diamond(draw, gx, gy, 22, fill=(150, 105, 250), outline=LAVENDER, width=2)
    _diamond(draw, gx, gy, 8, fill=WHITE)

    f_ptlabel = _font(TITLE_FONT, 44)
    draw.text((gx + 78, gy), "보유 포인트", font=f_ptlabel, fill=WHITE, anchor="lm",
              stroke_width=2, stroke_fill=BLACK)

    f_pts = _font(TITLE_FONT, 76)
    f_p = _font(TITLE_FONT, 44)
    pts_txt = f"{points:,}"
    p_w = draw.textlength("P", font=f_p)
    num_right = x0 + total - 52 - p_w - 14
    draw.text((num_right, gy), pts_txt, font=f_pts, fill=WHITE, anchor="rm",
              stroke_width=3, stroke_fill=(50, 25, 95))
    draw.text((num_right + 14, gy + 12), "P", font=f_p, fill=PURPLE, anchor="lm",
              stroke_width=2, stroke_fill=BLACK)

    out = io.BytesIO()
    img.convert("RGB").save(out, "PNG")
    out.seek(0)
    return out.getvalue()


async def build_profile_card(target) -> discord.File:
    """유저의 레벨·순위·티어(역할 기준)·포인트를 담은 프로필 카드를 만듭니다."""
    chat_xp = await get_xp(target.id)
    voice_xp = await get_voice_xp(target.id)
    points = await get_points(target.id)
    chat_rank = await get_rank(target.id, "경험치")
    voice_rank = await get_rank(target.id, "음성경험치")
    # (한글명, 색, 약자) → 실제 티어 이미지 다운로드/캐시 후 (한글명, 색, 아이콘경로)
    ln, lc, ll = get_tier_info(target, "lol")
    vn, vc, vl = get_tier_info(target, "val")
    lol_tier = (ln, lc, await get_tier_icon("lol", ll))
    val_tier = (vn, vc, await get_tier_icon("val", vl))

    avatar_bytes = b""
    if target.display_avatar:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(target.display_avatar.url) as resp:
                    if resp.status == 200:
                        avatar_bytes = await resp.read()
        except Exception:
            pass

    data = await asyncio.to_thread(
        generate_profile_image, avatar_bytes, target.display_name,
        chat_xp, voice_xp, points, chat_rank, voice_rank, lol_tier, val_tier,
    )
    return discord.File(fp=io.BytesIO(data), filename="profile_card.png")
