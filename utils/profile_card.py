import io
import asyncio

import aiohttp
import discord
from PIL import Image, ImageDraw, ImageFont, ImageOps

from utils.stats import get_xp, get_voice_xp, get_points, get_rank, level_from_xp, xp_for_level

# 배경/투명도 설정 (배경에 UI가 안 어울리면 이 값들을 조절하세요)
PROFILE_BG_DIM = 70        # 배경 전체 어둡게 (0=원본, 255=완전 검정)
PROFILE_PANEL_ALPHA = 120  # 패널 투명도 (0=투명, 255=불투명) — 낮을수록 배경이 잘 보임
PANEL_BORDER = (170, 140, 235, 150)  # 패널 테두리 색 (부드러운 보라)
TITLE_FONT = "font.ttf"    # 이름/레벨/포인트용 (나눔스퀘어라운드 Bold)
UI_FONT = "font_ui.ttf"    # 라벨/작은글씨용 (나눔스퀘어라운드 Regular)


def _font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


def _fit_font(draw, text, path, max_w, start_size, min_size=24):
    size = start_size
    while size > min_size:
        f = _font(path, size)
        if draw.textlength(text, font=f) <= max_w:
            return f
        size -= 2
    return _font(path, min_size)


def _progress_bar(draw, x, y, w, h, frac):
    frac = max(0.0, min(1.0, frac))
    draw.rounded_rectangle((x, y, x + w, y + h), radius=h // 2, fill=(255, 255, 255, 50))
    fw = int(w * frac)
    if fw > h:
        draw.rounded_rectangle((x, y, x + fw, y + h), radius=h // 2, fill=(255, 200, 80, 255))


def generate_profile_image(avatar_bytes, name, chat_xp, voice_xp, points, chat_rank=None, voice_rank=None):
    """프로필 카드: 왼쪽에 아바타+이름, 오른쪽에 채팅/음성 레벨(+순위) + 포인트."""
    W, H = 1000, 520
    try:
        bg = Image.open("profile_bg.png").convert("RGBA").resize((W, H))
    except FileNotFoundError:
        bg = Image.new("RGBA", (W, H), (30, 24, 54, 255))

    bg = Image.alpha_composite(bg, Image.new("RGBA", (W, H), (10, 6, 26, PROFILE_BG_DIM)))

    panel = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    pd = ImageDraw.Draw(panel)
    pd.rounded_rectangle((26, 26, W - 26, H - 26), radius=34, fill=(16, 11, 36, PROFILE_PANEL_ALPHA))
    pd.rounded_rectangle((26, 26, W - 26, H - 26), radius=34, outline=PANEL_BORDER, width=3)
    img = Image.alpha_composite(bg, panel)
    draw = ImageDraw.Draw(img)

    gold, white, sub, black = (255, 205, 90), (245, 242, 255), (196, 190, 222), (0, 0, 0)

    # ===== 왼쪽: 아바타 + 이름 =====
    cx, cy, r = 216, 198, 100
    draw.ellipse((cx - r - 7, cy - r - 7, cx + r + 7, cy + r + 7), fill=(255, 205, 90, 255))
    if avatar_bytes:
        try:
            av = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
            av = ImageOps.fit(av, (r * 2, r * 2), centering=(0.5, 0.5))
            mask = Image.new("L", (r * 2, r * 2), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, r * 2, r * 2), fill=255)
            av.putalpha(mask)
            img.paste(av, (cx - r, cy - r), av)
            draw = ImageDraw.Draw(img)
        except Exception as e:
            print(f"[ERROR] 아바타 합성 오류: {e}")
    else:
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(40, 30, 66, 255))

    f_name = _fit_font(draw, name, TITLE_FONT, 340, 46)
    draw.text((cx, 356), name, font=f_name, fill=white, anchor="mm", stroke_width=3, stroke_fill=black)

    draw.line((404, 78, 404, H - 78), fill=(255, 255, 255, 55), width=2)

    # ===== 오른쪽: 채팅/음성 레벨(+순위) + 포인트 =====
    RX0, RX1 = 446, W - 60
    f_label = _font(UI_FONT, 28)
    f_rank = _font(TITLE_FONT, 24)
    f_lv = _font(TITLE_FONT, 54)
    f_small = _font(UI_FONT, 20)
    f_pts = _font(TITLE_FONT, 50)

    def stat_row(y, label, lv, into, span, rank):
        draw.text((RX0, y), label, font=f_label, fill=sub, stroke_width=1, stroke_fill=black)
        if rank:
            lw = draw.textlength(label, font=f_label)
            draw.text((RX0 + lw + 14, y + 5), f"#{rank}위", font=f_rank, fill=gold, stroke_width=1, stroke_fill=black)
        draw.text((RX1, y - 16), f"Lv. {lv}", font=f_lv, fill=gold, anchor="ra", stroke_width=2, stroke_fill=black)
        _progress_bar(draw, RX0, y + 52, RX1 - RX0, 18, into / span)
        draw.text((RX1, y + 76), f"{into:,} / {span:,} XP", font=f_small, fill=sub, anchor="ra")

    chat_lv, voice_lv = level_from_xp(chat_xp), level_from_xp(voice_xp)
    ci, cs = chat_xp - xp_for_level(chat_lv), max(1, xp_for_level(chat_lv + 1) - xp_for_level(chat_lv))
    vi, vs = voice_xp - xp_for_level(voice_lv), max(1, xp_for_level(voice_lv + 1) - xp_for_level(voice_lv))
    stat_row(96, "채팅 레벨", chat_lv, ci, cs, chat_rank)
    stat_row(228, "음성 레벨", voice_lv, vi, vs, voice_rank)

    draw.text((RX0, 372), "보유 포인트", font=f_label, fill=sub, stroke_width=1, stroke_fill=black)
    draw.text((RX1, 356), f"{points:,} P", font=f_pts, fill=gold, anchor="ra", stroke_width=2, stroke_fill=black)

    out = io.BytesIO()
    img.convert("RGB").save(out, "PNG")
    out.seek(0)
    return out.getvalue()


async def build_profile_card(target) -> discord.File:
    """유저의 채팅/음성 레벨·순위·포인트를 담은 프로필 카드 파일을 만듭니다."""
    chat_xp = await get_xp(target.id)
    voice_xp = await get_voice_xp(target.id)
    points = await get_points(target.id)
    chat_rank = await get_rank(target.id, "경험치")
    voice_rank = await get_rank(target.id, "음성경험치")

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
        chat_xp, voice_xp, points, chat_rank, voice_rank,
    )
    return discord.File(fp=io.BytesIO(data), filename="profile_card.png")
