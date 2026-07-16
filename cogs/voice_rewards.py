from datetime import datetime, timedelta, timezone

import discord
from discord.ext import commands, tasks

from utils.stats import add_points, get_points, format_num
from utils.logs import VOICE_POINT_LOG_CH, enqueue_embed, is_target_guild

# 통화방 1시간 유지 시 지급할 포인트
VOICE_REWARD_POINT = 10


class VoiceRewardsCog(commands.Cog):
    """통화방에 1시간 접속을 유지하면 포인트를 지급하는 Cog.

    (음성 입장/퇴장/이동 '로그'는 로그봇의 voice_logger가 담당합니다. 여기서는 포인트 지급.)
    포인트 획득 시 '잠수 포인트 로그' 채널로 기록합니다.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.user_join_times: dict[int, dict] = {}
        self.voice_point_task.start()

    def cog_unload(self):
        self.voice_point_task.cancel()

    @tasks.loop(minutes=1)
    async def voice_point_task(self):
        now = datetime.now(timezone.utc)
        for user_id in list(self.user_join_times.keys()):
            join_info = self.user_join_times.get(user_id)
            if not join_info:
                continue
            join_time, guild_id = join_info["time"], join_info["guild_id"]

            if (now - join_time) >= timedelta(hours=1):
                guild = self.bot.get_guild(guild_id)
                if not guild:
                    continue
                member = guild.get_member(user_id)
                if member and member.voice and member.voice.channel:
                    # AFK 채널은 보상에서 제외
                    if guild.afk_channel and member.voice.channel.id == guild.afk_channel.id:
                        continue
                    # 대상 서버가 아니면 지급/로그 생략
                    if not is_target_guild(guild):
                        self.user_join_times[user_id]["time"] += timedelta(hours=1)
                        continue
                    await add_points(user_id, VOICE_REWARD_POINT)
                    # 다음 보상 기준을 1시간 뒤로 이동
                    self.user_join_times[user_id]["time"] += timedelta(hours=1)
                    # 잠수 포인트 로그
                    current = await get_points(user_id)
                    embed = discord.Embed(
                        description=(f"🎙️ {member.mention} 님이 통화방 1시간 유지로 "
                                     f"{VOICE_REWARD_POINT} P 를 획득했습니다! "
                                     f"(현재 보유: {format_num(current)} P)"),
                        color=discord.Color.gold(),
                    )
                    embed.set_footer(text=f"유저 ID: {user_id}")
                    enqueue_embed(VOICE_POINT_LOG_CH, embed.to_dict(), guild=guild)
                else:
                    self.user_join_times.pop(user_id, None)

    @voice_point_task.before_loop
    async def before_voice_point_task(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.bot:
            return
        now = datetime.now(timezone.utc)

        # 입장: 접속 시각 기록 시작
        if not before.channel and after.channel:
            self.user_join_times[member.id] = {"time": now, "guild_id": member.guild.id}
        # 퇴장: 기록 제거
        elif before.channel and not after.channel:
            self.user_join_times.pop(member.id, None)
        # 이동: 기록이 없으면 새로 시작
        elif before.channel and after.channel and before.channel != after.channel:
            if member.id not in self.user_join_times:
                self.user_join_times[member.id] = {"time": now, "guild_id": member.guild.id}


async def setup(bot: commands.Bot):
    await bot.add_cog(VoiceRewardsCog(bot))
