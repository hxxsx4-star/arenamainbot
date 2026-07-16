import discord
from discord.ext import commands
from discord import app_commands

from utils.stats import DAILY_MISSIONS, get_missions, claim_missions, format_num


def _bar(cur: int, total: int, size: int = 10) -> str:
    total = max(1, total)
    filled = int(size * min(1.0, cur / total))
    return "▰" * filled + "▱" * (size - filled)


def build_mission_embed(data: dict) -> discord.Embed:
    progress = data["progress"]
    claimed = data["claimed"]
    embed = discord.Embed(
        title="🎯 오늘의 일일 미션",
        description="완료한 미션의 보상을 아래 버튼으로 받으세요! (매일 자정 초기화)",
        color=discord.Color.green(),
    )
    ready = 0
    for mi in DAILY_MISSIONS:
        cur = int(progress.get(mi["key"], 0))
        done = cur >= mi["goal"]
        if mi["key"] in claimed:
            status = "🎁 수령 완료"
        elif done:
            status = "✅ 완료 — 보상 받기 가능!"
            ready += 1
        else:
            status = f"{_bar(cur, mi['goal'])}  {min(cur, mi['goal'])}/{mi['goal']}"
        embed.add_field(
            name=f"{mi['desc']}  (+{mi['reward']}P)",
            value=status,
            inline=False,
        )
    embed.set_footer(text=f"받을 수 있는 보상: {ready}개")
    return embed


class ClaimView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=120)
        self.owner_id = owner_id

    @discord.ui.button(label="보상 받기", style=discord.ButtonStyle.success, emoji="🎁")
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("본인의 미션만 수령할 수 있어요.", ephemeral=True)
        got = await claim_missions(interaction.user.id)
        data = await get_missions(interaction.user.id)
        embed = build_mission_embed(data)
        if got:
            total = sum(r for _, r in got)
            lines = "\n".join(f"• {desc} → +{r}P" for desc, r in got)
            await interaction.response.edit_message(embed=embed, view=self)
            await interaction.followup.send(f"🎉 보상 지급!\n{lines}\n**합계 +{format_num(total)}P**", ephemeral=True)
        else:
            await interaction.response.send_message("받을 수 있는 보상이 없어요. 미션을 더 완료해보세요!", ephemeral=True)


class MissionsCog(commands.Cog):
    """일일 미션 시스템."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="미션", description="오늘의 일일 미션을 확인하고 보상을 받습니다.")
    async def missions_cmd(self, interaction: discord.Interaction):
        data = await get_missions(interaction.user.id)
        embed = build_mission_embed(data)
        await interaction.response.send_message(embed=embed, view=ClaimView(interaction.user.id), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(MissionsCog(bot))
