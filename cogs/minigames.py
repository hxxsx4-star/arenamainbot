# cogs/minigames.py
import discord
from discord.ext import commands

class MinigamesCog(commands.Cog):
    """
    미니게임 관련 명령어 (현재 비활성화됨)
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.group(name="미니게임", invoke_without_command=True)
    async def minigame(self, ctx: commands.Context):
        """
        미니게임 명령어를 비활성화하고 안내 메시지를 보냅니다.
        """
        await ctx.reply("관리자에 의해 잠정 중단되었습니다.")

    @minigame.command(name="초기화")
    async def minigame_reset(self, ctx: commands.Context, member: discord.Member):
        """
        미니게임 초기화 명령어 또한 비활성화합니다.
        """
        await ctx.reply("관리자에 의해 잠정 중단되었습니다.")

async def setup(bot: commands.Bot):
    await bot.add_cog(MinigamesCog(bot))
