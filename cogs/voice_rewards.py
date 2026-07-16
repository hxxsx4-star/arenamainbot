import discord
from discord.ext import commands, tasks

from utils.stats import add_points, get_points, add_voice_xp, format_num
from utils.logs import VOICE_POINT_LOG_CH, enqueue_embed, is_target_guild

POINT_PER_MIN = 1     # 통화방 1분당 지급 포인트
VOICE_XP_PER_MIN = 1  # 통화방 1분당 음성 경험치
LOG_EVERY_MIN = 10    # 몇 분마다 잠수 포인트 로그를 남길지 (스팸 방지)


class VoiceRewardsCog(commands.Cog):
    """통화방에 있으면 1분당 포인트/음성 경험치를 지급하는 Cog.

    (음성 입장/퇴장/이동 '로그'는 로그봇의 voice_logger가 담당.
     여기서는 포인트 지급 + 잠수 포인트 로그만.)
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._accum: dict[int, int] = {}  # 유저별 로그 적립(분)
        self.voice_point_task.start()

    def cog_unload(self):
        self.voice_point_task.cancel()

    @tasks.loop(minutes=1)
    async def voice_point_task(self):
        for guild in self.bot.guilds:
            if not is_target_guild(guild):
                continue
            for vc in guild.voice_channels:
                # AFK(잠수) 채널은 제외
                if guild.afk_channel and vc.id == guild.afk_channel.id:
                    continue
                for member in vc.members:
                    if member.bot:
                        continue
                    # 자리비움(셀프 뮤트+데프)만 있는 경우도 통화방 유지로 인정
                    await add_points(member.id, POINT_PER_MIN)
                    await add_voice_xp(member.id, VOICE_XP_PER_MIN)
                    self._accum[member.id] = self._accum.get(member.id, 0) + POINT_PER_MIN
                    if self._accum[member.id] >= LOG_EVERY_MIN:
                        earned = self._accum.pop(member.id)
                        current = await get_points(member.id)
                        embed = discord.Embed(
                            description=(f"🎙️ {member.mention} 님이 통화방 유지로 "
                                         f"**+{earned}P** 획득! (현재 보유: {format_num(current)}P)"),
                            color=discord.Color.gold(),
                        )
                        embed.set_footer(text=f"유저 ID: {member.id} · 최근 {LOG_EVERY_MIN}분")
                        enqueue_embed(VOICE_POINT_LOG_CH, embed.to_dict(), guild=guild)

    @voice_point_task.before_loop
    async def before_voice_point_task(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(VoiceRewardsCog(bot))
