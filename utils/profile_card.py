"""프로필 카드 이미지 생성 (/프로필, /레벨).

1200x700 가로형 카드:
  · 좌측 원형 프레임 = 서버 프로필 사진 (보라 링 + 다이아 장식)
  · 우측 상단 = "GAME ARENA" 라벨 + 서버 닉네임 + 슬로건 + 보유 포인트
  · 중단 = 음성 레벨 / 채팅 레벨 경험치 바 (바 위 오른쪽에 순위 작게)
  · 하단 = 롤 솔랭 티어 / 발로 경쟁 티어 (보유 티어 역할 기준, 실제 엠블럼)
배경은 profile_bg.png (성 이미지) 를 그대로 사용.
"""
import io
import os
import asyncio
import math

import aiohttp
import discord
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from utils.stats import (get_xp, get_voice_xp, get_points, get_rank,
                         level_from_xp, xp_for_level)
from utils.tiers import get_tier_info
from utils.tier_assets import get_tier_icon

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TITLE_FONT = os.path.join(BASE_DIR, "font.ttf")     # 나눔스퀘어라운드 Bold
UI_FONT = os.path.join(BASE_DIR, "font_ui.ttf")     # 나눔스퀘어라운드 Regular
BG_PATH = os.path.join(BASE_DIR, "profile_bg.png")

W, H = 1200, 700
LAVENDER = (205, 190, 255)
LAVENDER_DIM = (175, 162, 220)
PURPLE = (155, 120, 255)
WHITE = (245, 243, 255)
BLACK = (8, 4, 20)
PANEL_BG = (16, 9, 38, 205)
BAR_BG = (26, 16, 54, 230)
VOICE_ACCENT = (167, 139, 250)
CHAT_ACCENT = (96, 165, 250)
GOLD = (255, 205, 90)


def _font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def _fit_font(draw, text, path, max_w, start_size, min_size=26):
    for size in range(start_size, min_size - 1, -2):
        f = _font(path, size)
        if draw.textlength(text, font=f) <= max_w:
            return f
    return _font(path, min_size)


def _spaced_text(draw, x, y, text, font, fill, spacing=6, stroke=0, stroke_fill=None,
                 center=None):
    """글자 사이 간격을 두고 그린다. center 를 주면 그 x 를 중심으로 정렬."""
    widths = [draw.textlength(ch, font=font) for ch in text]
    total = sum(widths) + spacing * (len(text) - 1)
    cur = (center - total / 2) if center is not None else x
    for ch, w in zip(text, widths):
        draw.text((cur, y), ch, font=font, fill=fill,
                  stroke_width=stroke, stroke_fill=stroke_fill)
        cur += w + spacing


def _diamond(draw, cx, cy, r, fill, outline=None, width=2):
    draw.polygon([(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)],
                 fill=fill, outline=outline, width=width)


def _hexagon(cx, cy, r):
    return [(cx + r * math.sin(math.radians(a)), cy - r * math.cos(math.radians(a)))
            for a in range(0, 360, 60)]


def _tier_badge(draw, cx, cy, size, color):
    """티어 이미지가 없을 때 쓰는 대체 엠블럼."""
    draw.polygon(_hexagon(cx, cy, size + 7), fill=tuple(list(color) + [70]))
    draw.polygon(_hexagon(cx, cy, size), fill=(14, 8, 34, 235), outline=tuple(color), width=5)
    draw.polygon(_hexagon(cx, cy, size - 12), outline=tuple(list(color) + [110]), width=2)
    cw, ch, gap = size * 0.52, size * 0.30, size * 0.34
    for i in range(2):
        oy = cy - size * 0.22 + i * gap
        draw.line([(cx - cw, oy), (cx, oy + ch), (cx + cw, oy)],
                  fill=tuple(color), width=int(max(5, size * 0.11)), joint="curve")


def _panel(draw, x, y, w, h, accent, radius=20):
    draw.rounded_rectangle([x, y, x + w, y + h], radius=radius, fill=PANEL_BG,
                           outline=tuple(list(accent) + [200]), width=2)
    draw.line([(x + 20, y + 3), (x + w - 20, y + 3)],
              fill=tuple(list(accent) + [115]), width=2)


def _progress_bar(img, draw, x, y, w, h, frac, accent):
    """경험치 진행 바 (배경 + 채움 + 은은한 글로우)."""
    r = h // 2
    draw.rounded_rectangle([x, y, x + w, y + h], radius=r, fill=BAR_BG,
                           outline=(120, 95, 190, 150), width=2)
    frac = max(0.0, min(1.0, frac))
    if frac <= 0:
        return
    fill_w = max(h, int(w * frac))
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(glow).rounded_rectangle(
        [x, y, x + fill_w, y + h], radius=r, fill=tuple(list(accent) + [110]))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(9)))
    draw.rounded_rectangle([x, y, x + fill_w, y + h], radius=r, fill=tuple(accent))
    # 상단 하이라이트
    draw.rounded_rectangle([x + 4, y + 3, x + fill_w - 4, y + h // 2],
                           radius=r // 2, fill=(255, 255, 255, 55))


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
    ratio = max(W / bg.width, H / bg.height)
    bg = bg.resize((int(bg.width * ratio) + 1, int(bg.height * ratio) + 1), Image.LANCZOS)
    left, top = (bg.width - W) // 2, (bg.height - H) // 2
    bg = bg.crop((left, top, left + W, top + H))
    bg = Image.alpha_composite(bg, Image.new("RGBA", (W, H), (10, 5, 28, 110)))
    # 아래쪽을 더 어둡게 (패널 가독성)
    grad = Image.new("L", (1, H))
    for yy in range(H):
        grad.putpixel((0, yy), int(max(0, (yy - 210) / (H - 210)) * 135) if yy > 210 else 0)
    dark = Image.new("RGBA", (W, H), (8, 4, 24, 255))
    dark.putalpha(grad.resize((W, H)))
    img = Image.alpha_composite(bg, dark)
    draw = ImageDraw.Draw(img, "RGBA")

    # 외곽 보더
    draw.rounded_rectangle([6, 6, W - 7, H - 7], radius=34,
                           outline=(150, 110, 230, 200), width=3)
    draw.rounded_rectangle([12, 12, W - 13, H - 13], radius=30,
                           outline=(90, 60, 160, 120), width=1)

    # ---------- 아바타 ----------
    AX, AY, AR = 167, 140, 90
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse(
        [AX - AR - 16, AY - AR - 16, AX + AR + 16, AY + AR + 16],
        outline=(160, 110, 255, 165), width=13)
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
    draw.ellipse([AX - AR - 3, AY - AR - 3, AX + AR + 3, AY + AR + 3],
                 outline=(30, 18, 58), width=7)
    draw.ellipse([AX - AR - 8, AY - AR - 8, AX + AR + 8, AY + AR + 8],
                 outline=PURPLE, width=4)
    for dx, dy in [(0, -AR - 8), (0, AR + 8), (-AR - 8, 0), (AR + 8, 0)]:
        _diamond(draw, AX + dx, AY + dy, 13, fill=(40, 24, 74), outline=PURPLE, width=3)
        _diamond(draw, AX + dx, AY + dy, 5, fill=LAVENDER)

    # ---------- 헤더 텍스트 ----------
    TX = 291  # 텍스트 좌측 기준선
    soft = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(soft).rounded_rectangle([TX - 30, 50, 1143, 238], radius=36,
                                           fill=(10, 5, 28, 135))
    img.alpha_composite(soft.filter(ImageFilter.GaussianBlur(24)))

    _spaced_text(draw, TX, 66, "GAME ARENA", _font(UI_FONT, 26), LAVENDER,
                 spacing=10, stroke=1, stroke_fill=BLACK)
    f_name = _fit_font(draw, name, TITLE_FONT, 520, 76, 34)
    draw.text((TX, 106), name, font=f_name, fill=WHITE,
              stroke_width=4, stroke_fill=(50, 25, 95))
    _spaced_text(draw, TX, 193, "PLAY TOGETHER, WIN TOGETHER.", _font(UI_FONT, 20),
                 LAVENDER_DIM, spacing=1.5, stroke=1, stroke_fill=BLACK)

    # 보유 포인트 (헤더 우측 칩)
    PX0, PY0, PX1, PY1 = 841, 80, 1143, 168
    draw.rounded_rectangle([PX0, PY0, PX1, PY1], radius=22, fill=PANEL_BG,
                           outline=(150, 110, 230, 200), width=2)
    gx, gy = PX0 + 44, (PY0 + PY1) // 2
    _diamond(draw, gx, gy, 25, fill=(60, 34, 110), outline=PURPLE, width=3)
    _diamond(draw, gx, gy, 13, fill=(150, 105, 250), outline=LAVENDER, width=2)
    _diamond(draw, gx, gy, 5, fill=WHITE)

    TXT_L, TXT_R = gx + 32, PX1 - 22       # 텍스트 영역 (우측 여백 확보)
    draw.text((TXT_L, PY0 + 10), "보유 포인트", font=_font(UI_FONT, 21),
              fill=LAVENDER_DIM, stroke_width=1, stroke_fill=BLACK)
    f_p = _font(TITLE_FONT, 24)
    p_w = draw.textlength("P", font=f_p)
    pts_txt = f"{points:,}"
    # 숫자가 길어도 'P' 와 우측 여백을 침범하지 않도록 폰트 자동 축소
    f_pts = _fit_font(draw, pts_txt, TITLE_FONT, TXT_R - TXT_L - p_w - 10, 40, 20)
    num_cy = PY0 + 60
    draw.text((TXT_R, num_cy + 5), "P", font=f_p, fill=PURPLE, anchor="rm",
              stroke_width=1, stroke_fill=BLACK)
    draw.text((TXT_R - p_w - 8, num_cy), pts_txt, font=f_pts, fill=WHITE, anchor="rm",
              stroke_width=2, stroke_fill=(50, 25, 95))

    # ---------- 경험치 바 ----------
    # 좌우 끝을 하단 티어 패널(SX0~SX1)과 동일하게 맞춘다.
    SX0, SX1 = 56, 1144
    draw.rounded_rectangle([SX0, 254, SX1, 484], radius=24, fill=(14, 8, 34, 190),
                           outline=(150, 110, 230, 150), width=2)
    # 바/텍스트는 패널 안쪽 여백을 두고 배치
    BX0, BX1 = SX0 + 24, SX1 - 24
    BW = BX1 - BX0
    f_lbl = _font(TITLE_FONT, 29)
    f_lv = _font(TITLE_FONT, 33)
    f_rank = _font(TITLE_FONT, 22)
    f_xp = _font(UI_FONT, 19)

    def xp_row(top, label, lv, into, span, rank, accent):
        draw.text((BX0 + 4, top), label, font=f_lbl, fill=WHITE,
                  stroke_width=2, stroke_fill=BLACK)
        lw = draw.textlength(label, font=f_lbl)
        draw.text((BX0 + 14 + lw, top - 2), f"Lv. {lv}", font=f_lv, fill=accent,
                  stroke_width=2, stroke_fill=BLACK)
        # 순위 — 바 위 오른쪽에 작게
        if rank:
            draw.text((BX1 - 4, top + 6), f"#{rank}위", font=f_rank, fill=GOLD,
                      anchor="ra", stroke_width=1, stroke_fill=BLACK)
        _progress_bar(img, draw, BX0, top + 44, BW, 28, into / span, accent)
        draw.text((BX1 - 4, top + 74), f"{int(into):,} / {int(span):,} XP",
                  font=f_xp, fill=LAVENDER_DIM, anchor="ra",
                  stroke_width=1, stroke_fill=BLACK)

    chat_lv, voice_lv = level_from_xp(chat_xp), level_from_xp(voice_xp)
    vi = voice_xp - xp_for_level(voice_lv)
    vs = max(1, xp_for_level(voice_lv + 1) - xp_for_level(voice_lv))
    ci = chat_xp - xp_for_level(chat_lv)
    cs = max(1, xp_for_level(chat_lv + 1) - xp_for_level(chat_lv))
    xp_row(274, "음성 레벨", voice_lv, vi, vs, voice_rank, VOICE_ACCENT)
    xp_row(382, "채팅 레벨", chat_lv, ci, cs, chat_rank, CHAT_ACCENT)

    # ---------- 티어 패널 (하단) ----------
    TY0, TH = 494, 170
    GAP = 20
    PWID = (SX1 - SX0 - GAP) // 2
    f_tlabel = _font(UI_FONT, 24)
    f_tname = _font(TITLE_FONT, 40)

    def tier_panel(px, label, tier):
        tname, tcolor, icon_path = (tuple(tier) + (None,))[:3]
        _panel(draw, px, TY0, PWID, TH, tcolor)
        icx, icy = px + 92, TY0 + TH // 2
        pasted = False
        if icon_path:
            try:
                icon = Image.open(icon_path).convert("RGBA")
                bbox = icon.getchannel("A").getbbox()
                if bbox:
                    icon = icon.crop(bbox)
                icon.thumbnail((132, 132), Image.LANCZOS)
                halo = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                ImageDraw.Draw(halo).ellipse(
                    [icx - 62, icy - 62, icx + 62, icy + 62],
                    fill=tuple(list(tcolor) + [75]))
                img.alpha_composite(halo.filter(ImageFilter.GaussianBlur(16)))
                img.alpha_composite(icon, (icx - icon.width // 2, icy - icon.height // 2))
                pasted = True
            except Exception:
                pasted = False
        if not pasted:
            _tier_badge(draw, icx, icy, 54, tcolor)
        tx = px + 172
        draw.text((tx, TY0 + 44), label, font=f_tlabel, fill=LAVENDER_DIM,
                  stroke_width=1, stroke_fill=BLACK)
        f_tn = _fit_font(draw, tname, TITLE_FONT, PWID - 190, 40, 22)
        draw.text((tx, TY0 + 80), tname, font=f_tn, fill=tcolor,
                  stroke_width=2, stroke_fill=BLACK)

    tier_panel(SX0, "롤 솔랭 티어", lol_tier)
    tier_panel(SX0 + PWID + GAP, "발로 경쟁 티어", val_tier)

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
