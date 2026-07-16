import random
from typing import Optional

import discord
from discord.ext import commands
from discord import app_commands

from utils.stats import try_chat_xp, bump_mission, bump_activity, get_activity_ranking
from utils.profile_card import build_profile_card
from utils.logs import is_target_guild

CHAT_XP_MIN, CHAT_XP_MAX = 5, 15
XP_COOLDOWN = 60  # 초 (스팸 방지)

PERIOD_CHOICES = [
    app_commands.Choice(name="1일", value="1"),
    app_commands.Choice(name="1주", value="7"),
    app_commands.Choice(name="1달(4주)", value="28"),
]
MODE_CHOICES = [
    app_commands.Choice(name="음성", value="voice"),
    app_commands.Choice(name="채팅", value="chat"),
]
_MEDAL = {1: "🥇", 2: "🥈", 3: "🥉"}


class LevelingCog(commands.Cog):
    """채팅 활동으로 XP/레벨이 오르는 시스템 + 활동 랭킹."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not is_target_guild(message.guild):
            return
        result = await try_chat_xp(message.author.id, random.randint(CHAT_XP_MIN, CHAT_XP_MAX), XP_COOLDOWN)
        if not result:
            return
        old_lv, new_lv, _ = result
        await bump_mission(message.author.id, "chat")
        await bump_activity(message.author.id, "chat")
        if new_lv > old_lv:
            try:
                await message.channel.send(
                    f"🎉 {message.author.mention} 님의 **채팅 레벨 {new_lv}** 달성!", delete_after=30)
            except discord.HTTPException:
                pass

    @app_commands.command(name="레벨", description="채팅/음성 레벨과 순위를 예쁜 카드로 확인합니다.")
    @app_commands.describe(유저="확인할 유저 (생략 시 본인)")
    async def level(self, interaction: discord.Interaction, 유저: Optional[discord.Member] = None):
        await interaction.response.defer()
        target = 유저 or interaction.user
        file = await build_profile_card(target)
        await interaction.followup.send(file=file)

    @app_commands.command(name="top", description="음성/채팅 활동 랭킹을 확인합니다.")
    @app_commands.describe(
        모드="음성 또는 채팅 (선택 안 하면 둘 다 TOP 10)",
        역할="이 역할 보유자만 보기 (선택)",
        기간="집계 기간 (선택 안 하면 전체 기간)",
    )
    @app_commands.choices(모드=MODE_CHOICES, 기간=PERIOD_CHOICES)
    async def top(self, interaction: discord.Interaction,
                  모드: Optional[app_commands.Choice[str]] = None,
                  역할: Optional[discord.Role] = None,
                  기간: Optional[app_commands.Choice[str]] = None):
        await interaction.response.defer()
        guild = interaction.guild
        days = int(기간.value) if 기간 else None
        period_label = 기간.name if 기간 else "전체"
        role_ids = {m.id for m in 역할.members} if 역할 else None

        def build_lines(rows, unit, limit):
            lines, rank = [], 0
            for uid, cnt in rows:
                member = guild.get_member(uid)
                if not member:
                    continue
                if role_ids is not None and uid not in role_ids:
                    continue
                rank += 1
                tag = _MEDAL.get(rank, f"`{rank}.`")
                lines.append(f"{tag} {member.display_name} — **{cnt:,}**{unit}")
                if rank >= limit:
                    break
            return lines or ["기록이 없습니다."]

        color = discord.Color.gold()
        if 모드 is None:
            voice_rows = await get_activity_ranking("voice", days)
            chat_rows = await get_activity_ranking("chat", days)
            embed = discord.Embed(title=f"🏆 활동 랭킹 · {period_label}", color=color)
            embed.add_field(name="🎙️ 음성 TOP 10", value="\n".join(build_lines(voice_rows, "분", 10)), inline=True)
            embed.add_field(name="💬 채팅 TOP 10", value="\n".join(build_lines(chat_rows, "회", 10)), inline=True)
        else:
            kind = 모드.value
            rows = await get_activity_ranking(kind, days)
            unit = "분" if kind == "voice" else "회"
            title = f"🏆 {'🎙️ 음성' if kind == 'voice' else '💬 채팅'} 랭킹 · {period_label}"
            desc = "\n".join(build_lines(rows, unit, 50))
            embed = discord.Embed(title=title, description=desc[:4000], color=color)

        if 역할:
            embed.set_footer(text=f"역할 필터: {역할.name}")
        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(LevelingCog(bot))
