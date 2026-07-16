import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional
from datetime import datetime, timezone, timedelta
from discord.utils import format_dt

import io
import re
import asyncio
import aiohttp
from PIL import Image, ImageDraw, ImageFont, ImageOps

from utils.stats import load_stats, format_num, get_points, add_points, spend_points, process_attendance, record_streak, bump_mission, get_xp, get_voice_xp, level_from_xp
from utils.logs import POINT_GIVE_LOG_CH, POINT_TAKE_LOG_CH, enqueue_embed

GRANT_LOG_CHANNEL_ID = POINT_GIVE_LOG_CH
REVOKE_LOG_CHANNEL_ID = POINT_TAKE_LOG_CH

CURRENCY, DAILY_REWARD, ATTEND_KEY = "P", 50, "출석_최근"
try: KST = timezone(timedelta(hours=9), 'KST')
except: KST = timezone(timedelta(hours=9))

# 프로필 카드 배경/투명도 설정 (배경에 UI가 안 어울리면 이 값들을 조절하세요)
PROFILE_BG_DIM = 110       # 배경 전체 어둡게 (0=원본, 255=완전 검정)
PROFILE_PANEL_ALPHA = 180  # 패널 투명도 (0=투명, 255=불투명)
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


def generate_profile_image(avatar_bytes: bytes, name: str, chat_xp: int, voice_xp: int, points: int):
    """프로필 카드: 왼쪽에 아바타+이름, 오른쪽에 채팅/음성 레벨 + 포인트."""
    from utils.stats import level_from_xp, xp_for_level
    W, H = 1000, 520
    try:
        bg = Image.open("profile_bg.png").convert("RGBA").resize((W, H))
    except FileNotFoundError:
        bg = Image.new("RGBA", (W, H), (30, 24, 54, 255))

    bg = Image.alpha_composite(bg, Image.new("RGBA", (W, H), (10, 6, 26, PROFILE_BG_DIM)))

    panel = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    pd = ImageDraw.Draw(panel)
    pd.rounded_rectangle((26, 26, W - 26, H - 26), radius=34, fill=(16, 11, 36, PROFILE_PANEL_ALPHA))
    pd.rounded_rectangle((26, 26, W - 26, H - 26), radius=34, outline=(255, 205, 90, 130), width=3)
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

    # 세로 구분선
    draw.line((404, 78, 404, H - 78), fill=(255, 255, 255, 55), width=2)

    # ===== 오른쪽: 채팅/음성 레벨 + 포인트 =====
    RX0, RX1 = 446, W - 60
    f_label = _font(UI_FONT, 28)
    f_lv = _font(TITLE_FONT, 54)
    f_small = _font(UI_FONT, 20)
    f_pts = _font(TITLE_FONT, 50)

    def stat_row(y, label, lv, into, span):
        draw.text((RX0, y), label, font=f_label, fill=sub, stroke_width=1, stroke_fill=black)
        draw.text((RX1, y - 16), f"Lv. {lv}", font=f_lv, fill=gold, anchor="ra", stroke_width=2, stroke_fill=black)
        _progress_bar(draw, RX0, y + 52, RX1 - RX0, 18, into / span)
        draw.text((RX1, y + 76), f"{into:,} / {span:,} XP", font=f_small, fill=sub, anchor="ra")

    chat_lv, voice_lv = level_from_xp(chat_xp), level_from_xp(voice_xp)
    ci, cs = chat_xp - xp_for_level(chat_lv), max(1, xp_for_level(chat_lv + 1) - xp_for_level(chat_lv))
    vi, vs = voice_xp - xp_for_level(voice_lv), max(1, xp_for_level(voice_lv + 1) - xp_for_level(voice_lv))
    stat_row(96, "채팅 레벨", chat_lv, ci, cs)
    stat_row(228, "음성 레벨", voice_lv, vi, vs)

    draw.text((RX0, 372), "보유 포인트", font=f_label, fill=sub, stroke_width=1, stroke_fill=black)
    draw.text((RX1, 356), f"{points:,} P", font=f_pts, fill=gold, anchor="ra", stroke_width=2, stroke_fill=black)

    out = io.BytesIO()
    img.convert("RGB").save(out, "PNG")
    out.seek(0)
    return out.getvalue()


@app_commands.guild_only()
class EconomyCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _send_log(self, guild: discord.Guild, channel_id: int, embed: discord.Embed):
        # 로그는 직접 올리지 않고 공유 큐에 적재 → 로그봇이 채널에 최종 기록 (대상 서버만)
        enqueue_embed(channel_id, embed.to_dict(), guild=guild)

    @app_commands.command(name="프로필", description="자신 또는 다른 유저의 채팅/음성 레벨과 포인트를 확인합니다.")
    @app_commands.describe(유저="확인할 유저 (선택하지 않으면 본인)")
    async def profile(self, interaction: discord.Interaction, 유저: Optional[discord.Member] = None):
        await interaction.response.defer(ephemeral=False)
        target = 유저 or interaction.user

        chat_xp = await get_xp(target.id)
        voice_xp = await get_voice_xp(target.id)
        points_val = await get_points(target.id)

        avatar_bytes = b""
        if target.display_avatar:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(target.display_avatar.url) as resp:
                        if resp.status == 200:
                            avatar_bytes = await resp.read()
            except Exception:
                pass

        image_data = await asyncio.to_thread(
            generate_profile_image, avatar_bytes, target.display_name, chat_xp, voice_xp, points_val
        )
        if not image_data:
            return await interaction.followup.send("❌ 이미지 생성에 실패했습니다. 서버 관리자에게 문의하세요.")
        file = discord.File(fp=io.BytesIO(image_data), filename="profile_card.png")
        await interaction.followup.send(file=file)

    @app_commands.command(name="지갑", description="포인트 보유량을 확인합니다.")
    @app_commands.describe(유저="확인할 유저 (선택)")
    async def wallet(self, interaction: discord.Interaction, 유저: Optional[discord.Member] = None):
        target = 유저 or interaction.user
        points = await get_points(target.id)
        await interaction.response.send_message(f"{target.mention} 님은 {format_num(points)} {CURRENCY}를 보유하고 있어요!")

    @app_commands.command(name="출석", description="하루에 한 번 출석하여 포인트를 받습니다.")
    async def attendance(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        today_str = datetime.now(tz=KST).date().isoformat()

        success = await process_attendance(user_id, DAILY_REWARD, ATTEND_KEY, today_str)

        if not success:
            await interaction.response.send_message("이미 오늘 출석했습니다.", ephemeral=True)
            return

        # 연속 출석 + 미션 카운트 + 연속 보너스
        streak = await record_streak(user_id)
        await bump_mission(user_id, "attend")
        bonus = 0
        if streak > 0 and streak % 7 == 0:   # 7일마다 보너스
            bonus = 100
            await add_points(user_id, bonus)

        msg = f"✅ 출석 완료! {format_num(DAILY_REWARD)} {CURRENCY} 지급 (🔥 {streak}일 연속)"
        if bonus:
            msg += f"\n🎁 {streak}일 연속 보너스 +{format_num(bonus)} {CURRENCY}!"
        await interaction.response.send_message(msg, ephemeral=True)

    @app_commands.command(name="순위", description="서버 내 포인트 순위를 확인합니다.")
    async def ranking(self, interaction: discord.Interaction):
        if not interaction.guild: return
        stats = await load_stats()
        ranking_list = sorted([(int(uid), rec.get("포인트", 0)) for uid, rec in stats.items() if str(uid).isdigit() and isinstance(rec, dict) and interaction.guild.get_member(int(uid))], key=lambda x: x[1], reverse=True)
        if not ranking_list:
            await interaction.response.send_message("순위 정보가 없습니다.")
            return
        lines = [f"{i}. {interaction.guild.get_member(uid).display_name} — {format_num(point)} {CURRENCY}" for i, (uid, point) in enumerate(ranking_list[:10], 1)]
        embed = discord.Embed(title="🏆 서버 포인트 랭킹 (상위 10명)", description="\n".join(lines), color=discord.Color.blue())
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="포인트지급", description="[관리자] 특정 유저에게 포인트를 지급합니다.")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(유저="포인트를 받을 유저", 금액="지급할 포인트 양")
    async def grant_points(self, interaction: discord.Interaction, 유저: discord.Member, 금액: int):
        if 금액 <= 0:
            await interaction.response.send_message("금액은 1 이상이어야 합니다.", ephemeral=True)
            return
        await add_points(유저.id, 금액)
        await interaction.response.send_message(f"{유저.mention}님에게 {format_num(금액)} {CURRENCY}를 지급했습니다.", ephemeral=True)

        log_embed = discord.Embed(title="💰 포인트 지급 로그", color=discord.Color.gold())
        log_embed.add_field(name="실행자", value=interaction.user.mention, inline=False)
        log_embed.add_field(name="대상", value=유저.mention, inline=False)
        log_embed.add_field(name="금액", value=f"{format_num(금액)} {CURRENCY}", inline=False)
        await self._send_log(interaction.guild, GRANT_LOG_CHANNEL_ID, log_embed)

    @app_commands.command(name="포인트회수", description="[관리자] 특정 유저의 포인트를 회수합니다.")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(유저="포인트를 회수할 유저", 금액="회수할 포인트 양")
    async def revoke_points(self, interaction: discord.Interaction, 유저: discord.Member, 금액: int):
        if 금액 <= 0:
            await interaction.response.send_message("금액은 1 이상이어야 합니다.", ephemeral=True)
            return

        success = await spend_points(유저.id, 금액)
        if not success:
            await interaction.response.send_message("대상의 포인트가 부족합니다.", ephemeral=True)
            return

        await interaction.response.send_message(f"{유저.mention}님에게서 {format_num(금액)} {CURRENCY}를 회수했습니다.", ephemeral=True)

        log_embed = discord.Embed(title="💸 포인트 회수 로그", color=discord.Color.dark_red())
        log_embed.add_field(name="실행자", value=interaction.user.mention, inline=False)
        log_embed.add_field(name="대상", value=유저.mention, inline=False)
        log_embed.add_field(name="금액", value=f"{format_num(금액)} {CURRENCY}", inline=False)
        await self._send_log(interaction.guild, REVOKE_LOG_CHANNEL_ID, log_embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(EconomyCog(bot))