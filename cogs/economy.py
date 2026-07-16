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

from utils.stats import load_stats, format_num, get_points, add_points, spend_points, process_attendance, record_streak, bump_mission
from utils.logs import POINT_GIVE_LOG_CH, POINT_TAKE_LOG_CH, enqueue_embed

GRANT_LOG_CHANNEL_ID = POINT_GIVE_LOG_CH
REVOKE_LOG_CHANNEL_ID = POINT_TAKE_LOG_CH

CURRENCY, DAILY_REWARD, ATTEND_KEY = "P", 50, "출석_최근"
try: KST = timezone(timedelta(hours=9), 'KST')
except: KST = timezone(timedelta(hours=9))

def parse_user_info(raw_name: str):
    """서버 프로필 닉네임에서 나이, 롤 닉네임, 성별, 티어를 추출합니다."""
    # ✨ 다국어 처리를 위해 정규식 그대로 사용 (.+는 한자, 일어 등 모든 문자 캡처 가능)
    match = re.match(r'^(\d{2})\s+(.+)\s+(남|여)\s*(.*)$', raw_name.strip())
    if match:
        age = match.group(1) + "년생"
        nickname = match.group(2).strip()
        gender = match.group(3)
        tier = match.group(4) if match.group(4) else "티어 없음"
        return age, nickname, gender, tier

    age = raw_name[:2] + "년생" if len(raw_name) >= 2 and raw_name[:2].isdigit() else "??"
    temp = raw_name[2:].lstrip() if len(raw_name) >= 2 else raw_name
    nickname = re.sub(r'\s+(남|여)[^#]*$', '', temp).strip()
    return age, nickname, "-", "-"

def generate_profile_image(avatar_bytes: bytes, raw_nickname: str, join_date: str, points: str, match_count: str, mvp_count: str, warning_count: str) -> Optional[bytes]:
    try:
        bg = Image.open("profile_bg.png")
        bg = bg.resize((1200, 700))
    except FileNotFoundError:
        bg = Image.new('RGB', (1200, 700), color=(25, 28, 35))

    img = bg.copy()
    draw = ImageDraw.Draw(img)

    # ⚠️ 중요: 한자, 일본어 등을 제대로 출력하려면 "font.ttf" 파일이 NotoSansCJK 등 다국어 지원 폰트여야 합니다.
    font_path = "font.ttf"
    try:
        info_font = ImageFont.truetype(font_path, size=42)
        main_font = ImageFont.truetype(font_path, size=42)
        small_font = ImageFont.truetype(font_path, size=26)
    except OSError:
        info_font = ImageFont.load_default()
        main_font = ImageFont.load_default()
        small_font = ImageFont.load_default()

    age, extracted_nickname, gender, tier = parse_user_info(raw_nickname)
    text_color = (255, 255, 255)

    try:
        if avatar_bytes:
            avatar = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
            avatar = avatar.resize((160, 160))

            mask = Image.new("L", avatar.size, 0)
            draw_mask = ImageDraw.Draw(mask)
            draw_mask.ellipse((0, 0) + avatar.size, fill=255)

            avatar_pasted = ImageOps.fit(avatar, mask.size, centering=(0.5, 0.5))
            avatar_pasted.putalpha(mask)

            img.paste(avatar_pasted, (150, 150), avatar_pasted)
    except Exception as e:
        print(f"[ERROR] 아바타 합성 오류: {e}")

    nick_font_size = 65
    try:
        nickname_font = ImageFont.truetype(font_path, size=nick_font_size)
        while True:
            try: text_width = draw.textlength(extracted_nickname, font=nickname_font)
            except AttributeError: text_width = draw.textsize(extracted_nickname, font=nickname_font)[0]

            if text_width <= 700 or nick_font_size <= 30:
                break
            nick_font_size -= 2
            nickname_font = ImageFont.truetype(font_path, size=nick_font_size)
    except OSError:
        nickname_font = ImageFont.load_default()

    draw.text((340, 155), extracted_nickname, fill=text_color, font=nickname_font)
    draw.text((340, 235), f"티어: {tier}", fill=text_color, font=info_font)
    draw.text((340, 285), f"나이/성별 : {age}/{gender}", fill=text_color, font=info_font)

    stat_x1 = 160
    stat_x2 = 620
    stat_y_row1 = 400
    draw.text((stat_x1, stat_y_row1), f"보유 포인트: {points}", fill=text_color, font=main_font)
    draw.text((stat_x2, stat_y_row1), f"누적 경고: {warning_count}", fill=text_color, font=main_font)

    stat_y_row2 = 480
    draw.text((stat_x1, stat_y_row2), f"내전 참여 수: {match_count}", fill=text_color, font=main_font)
    draw.text((stat_x2, stat_y_row2), f"내전 MVP 횟수: {mvp_count}", fill=text_color, font=main_font)

    draw.text((1050, 560), f"서버 가입일: {join_date}", fill=text_color, font=small_font, anchor="rm")

    with io.BytesIO() as image_binary:
        img.save(image_binary, 'PNG')
        image_binary.seek(0)
        return image_binary.getvalue()

@app_commands.guild_only()
class EconomyCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _send_log(self, guild: discord.Guild, channel_id: int, embed: discord.Embed):
        # 로그는 직접 올리지 않고 공유 큐에 적재 → 로그봇이 채널에 최종 기록 (대상 서버만)
        enqueue_embed(channel_id, embed.to_dict(), guild=guild)

    @app_commands.command(name="프로필", description="자신 또는 다른 유저의 전적 및 상태를 예쁜 프로필 카드로 확인합니다.")
    @app_commands.describe(유저="확인할 유저 (선택하지 않으면 본인)")
    async def profile(self, interaction: discord.Interaction, 유저: Optional[discord.Member] = None):
        await interaction.response.defer(ephemeral=False)

        target = 유저 or interaction.user
        stats = await load_stats()

        rec = stats.get(str(target.id), {})
        match_count = f"{rec.get('match_count', 0)}회"
        mvp_count = f"{rec.get('mvp_count', 0)}회"

        warnings = rec.get("경고", rec.get("warning", 0))
        warning_count = f"{warnings}회"

        points_val = await get_points(target.id)
        points = f"{format_num(points_val)}P"

        if target.joined_at:
            join_date = target.joined_at.astimezone(KST).strftime("%Y년 %m월 %d일")
        else:
            join_date = "알 수 없음"

        raw_nickname = target.display_name

        avatar_bytes = b""
        if target.display_avatar:
            async with aiohttp.ClientSession() as session:
                async with session.get(target.display_avatar.url) as resp:
                    if resp.status == 200:
                        avatar_bytes = await resp.read()

        image_data = await asyncio.to_thread(
            generate_profile_image,
            avatar_bytes,
            raw_nickname,
            join_date,
            points,
            match_count,
            mvp_count,
            warning_count
        )

        if not image_data:
            await interaction.followup.send("❌ 이미지 생성에 실패했습니다. 서버 관리자에게 문의하세요.")
            return

        file = discord.File(fp=io.BytesIO(image_data), filename='profile_card.png')
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