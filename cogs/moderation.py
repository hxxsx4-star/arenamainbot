from typing import Optional
import discord
from discord.ext import commands
from discord import app_commands

from utils.stats import add_warning, reduce_warning
from utils.logs import enqueue_embed, WARN_LOG_CH, WARN_REDUCE_LOG_CH

# 경고/차감 로그 채널 (공유 utils/logs.py 기준). 로그봇이 최종 기록합니다.
WARN_LOG_CHANNEL_ID = WARN_LOG_CH
REDUCE_LOG_CHANNEL_ID = WARN_REDUCE_LOG_CH

class ModerationCog(commands.Cog):
    """경고 / 차감 등 제재 기록 관리용 Cog"""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _get_log_channel(self, guild: Optional[discord.Guild], channel_id: int) -> Optional[discord.TextChannel]:
        if guild is None or not channel_id or channel_id == 123456789012345678:
            return None

        ch = guild.get_channel(channel_id)
        if isinstance(ch, discord.TextChannel) and ch.permissions_for(guild.me).send_messages:
            return ch
        return None

    @app_commands.command(name="경고", description="[관리자] 특정 유저에게 경고를 부여합니다. (3회 누적 시 차단)")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(member="경고를 받을 유저", count="부여할 경고 개수", reason="경고 사유")
    async def give_warning(self, interaction: discord.Interaction, member: discord.Member, count: int, reason: str = "사유 미기재"):
        if count < 1:
            await interaction.response.send_message("경고 개수는 1 이상이어야 합니다.", ephemeral=True)
            return

        old_warn, new_warn = await add_warning(member.id, count)

        extra_line = ""
        # ✨ 경고 차단 기준을 4회에서 3회로 변경
        if new_warn >= 3 and old_warn < 3 and interaction.guild and interaction.guild.me.guild_permissions.ban_members:
            try:
                await member.ban(reason=f"경고 {new_warn}회 누적(자동 차단): {reason}")
                extra_line = "\n⚠️ 경고 3회 누적으로 자동 서버 차단이 수행되었습니다."
            except discord.Forbidden:
                extra_line = "\n⚠️ 경고 3회지만, 봇에 차단 권한이 없어 자동 차단에 실패했습니다."

        embed = discord.Embed(
            title="⚠️ 경고 부여",
            description=f"{member.mention} 님에게 경고 {count}회를 부여했습니다.\n누적 경고: {old_warn}회 → {new_warn}회\n경고 3회 누적 시 서버 차단입니다.{extra_line}",
            color=discord.Color.orange()
        )
        embed.add_field(name="사유", value=reason, inline=False)
        embed.set_footer(text=f"처리자: {interaction.user.display_name}")
        await interaction.response.send_message(embed=embed)

        log_embed = discord.Embed(title="🚫 경고 기록", color=discord.Color.dark_orange())
        log_embed.add_field(name="대상", value=member.mention, inline=False)
        log_embed.add_field(name="처리자", value=interaction.user.mention, inline=False)
        log_embed.add_field(name="변동", value=f"+{count}회", inline=False)
        log_embed.add_field(name="누적 경고", value=f"{old_warn}회 → {new_warn}회", inline=False)
        log_embed.add_field(name="채널", value=interaction.channel.mention, inline=False)
        if extra_line:
            log_embed.add_field(name="조치", value="경고 3회 누적으로 자동 서버 차단", inline=False)
        log_embed.add_field(name="사유", value=reason, inline=False)
        enqueue_embed(WARN_LOG_CHANNEL_ID, log_embed.to_dict(), guild=interaction.guild)

    @app_commands.command(name="차감", description="[관리자] 특정 유저의 경고를 차감합니다.")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(member="경고를 차감할 유저", count="차감할 경고 개수", reason="차감 사유")
    async def reduce_warning(self, interaction: discord.Interaction, member: discord.Member, count: int, reason: str = "사유 미기재"):
        if count < 1:
            await interaction.response.send_message("차감할 경고 개수는 1 이상이어야 합니다.", ephemeral=True)
            return

        old_warn, new_warn = await reduce_warning(member.id, count)
        diff = old_warn - new_warn

        note = "⚠️ 차감할 경고가 없어 실제로 차감된 횟수는 0회입니다." if diff <= 0 else ""
        embed = discord.Embed(
            title="✅ 경고 차감",
            description=f"{member.mention} 님의 경고를 {diff}회 차감했습니다.\n누적 경고: {old_warn}회 → {new_warn}회\n{note}".strip(),
            color=discord.Color.green()
        )
        embed.add_field(name="사유", value=reason, inline=False)
        embed.set_footer(text=f"처리자: {interaction.user.display_name}")
        await interaction.response.send_message(embed=embed)

        log_embed = discord.Embed(title="📘 경고 차감 기록", color=discord.Color.blue())
        log_embed.add_field(name="대상", value=member.mention, inline=False)
        log_embed.add_field(name="처리자", value=interaction.user.mention, inline=False)
        log_embed.add_field(name="변동", value=f"-{diff}회 (요청: {count}회)", inline=False)
        log_embed.add_field(name="누적 경고", value=f"{old_warn}회 → {new_warn}회", inline=False)
        log_embed.add_field(name="채널", value=interaction.channel.mention, inline=False)
        log_embed.add_field(name="사유", value=reason, inline=False)
        enqueue_embed(REDUCE_LOG_CHANNEL_ID, log_embed.to_dict(), guild=interaction.guild)

async def setup(bot: commands.Bot):
    await bot.add_cog(ModerationCog(bot))