import random
from typing import Optional

import discord
from discord.ext import commands
from discord import app_commands

from utils.stats import (
    try_chat_xp, bump_mission, get_xp, level_from_xp, xp_for_level,
    get_level_ranking, format_num,
)
from utils.logs import is_target_guild

CHAT_XP_MIN, CHAT_XP_MAX = 5, 15
XP_COOLDOWN = 60  # 초 (스팸 방지)

# 레벨 도달 시 자동 지급할 역할 (원하면 채우세요). 예: {5: 역할ID, 10: 역할ID}
LEVEL_ROLES: dict[int, int] = {}


def _bar(cur: int, total: int, size: int = 12) -> str:
    total = max(1, total)
    filled = int(size * min(1.0, cur / total))
    return "▰" * filled + "▱" * (size - filled)


class LevelingCog(commands.Cog):
    """채팅 활동으로 XP/레벨이 오르는 시스템."""
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
        # XP를 실제로 받은 순간에만 채팅 미션 카운트 (쓰기 부하 완화)
        await bump_mission(message.author.id, "chat")
        if new_lv > old_lv:
            await self._level_up(message, new_lv)

    async def _level_up(self, message: discord.Message, level: int):
        try:
            await message.channel.send(
                f"🎉 {message.author.mention} 님이 **레벨 {level}** 을 달성했어요!",
                delete_after=30,
            )
        except discord.HTTPException:
            pass
        role_id = LEVEL_ROLES.get(level)
        if role_id and message.guild:
            role = message.guild.get_role(role_id)
            if role:
                try:
                    await message.author.add_roles(role, reason=f"레벨 {level} 달성")
                except discord.HTTPException:
                    pass

    @app_commands.command(name="레벨", description="자신 또는 다른 유저의 레벨을 확인합니다.")
    @app_commands.describe(유저="확인할 유저 (생략 시 본인)")
    async def level(self, interaction: discord.Interaction, 유저: Optional[discord.Member] = None):
        target = 유저 or interaction.user
        xp = await get_xp(target.id)
        lv = level_from_xp(xp)
        cur_floor = xp_for_level(lv)
        next_need = xp_for_level(lv + 1)
        into = xp - cur_floor
        span = max(1, next_need - cur_floor)

        embed = discord.Embed(title=f"📊 {target.display_name} 님의 레벨", color=discord.Color.blurple())
        if target.display_avatar:
            embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="레벨", value=f"**Lv. {lv}**", inline=True)
        embed.add_field(name="누적 XP", value=f"{format_num(xp)} XP", inline=True)
        embed.add_field(
            name=f"다음 레벨까지 ({format_num(into)}/{format_num(span)})",
            value=f"{_bar(into, span)}  남은 {format_num(next_need - xp)} XP",
            inline=False,
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="레벨랭킹", description="서버 레벨 랭킹을 확인합니다.")
    async def level_ranking(self, interaction: discord.Interaction):
        if not interaction.guild:
            return
        rows = await get_level_ranking()
        lines = []
        rank = 0
        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        for uid, xp, lv in rows:
            member = interaction.guild.get_member(uid)
            if not member:
                continue
            rank += 1
            tag = medals.get(rank, f"{rank}.")
            lines.append(f"{tag} {member.display_name} — **Lv.{lv}** ({format_num(xp)} XP)")
            if rank >= 10:
                break
        embed = discord.Embed(
            title="🏆 레벨 랭킹 (상위 10명)",
            description="\n".join(lines) if lines else "아직 랭킹 정보가 없습니다.",
            color=discord.Color.gold(),
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(LevelingCog(bot))
