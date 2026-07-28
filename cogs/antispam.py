"""도배 감지 — 어떤 채널이든 동일 메시지 5회 이상 반복 시 1분 타임아웃.

제재가 발생하면 서버 차단 로그 채널(BAN_LOG_CH)에 내역을 남긴다.
"""
import time
from collections import defaultdict, deque
from datetime import timedelta

import discord
from discord.ext import commands

from utils.logs import is_target_guild, send_log_embed, BAN_LOG_CH

SPAM_THRESHOLD = 5     # 동일 메시지 반복 횟수
SPAM_WINDOW_SEC = 30   # 이 시간 안에서 반복되면 도배로 판단
TIMEOUT_SECONDS = 60


class AntiSpamCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._recent: dict[int, deque] = defaultdict(deque)  # member_id -> deque[(content, ts)]

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return
        if not is_target_guild(message.guild):
            return
        content = message.content.strip()
        if not content:
            return

        now = time.time()
        history = self._recent[message.author.id]
        history.append((content, now))
        while history and now - history[0][1] > SPAM_WINDOW_SEC:
            history.popleft()

        if sum(1 for c, _ in history if c == content) >= SPAM_THRESHOLD:
            history.clear()
            await self._punish(message.author, content)

    async def _punish(self, member: discord.Member, content: str):
        try:
            await member.timeout(
                timedelta(seconds=TIMEOUT_SECONDS),
                reason=f"도배(동일 메시지 {SPAM_THRESHOLD}회 이상) 자동 제재")
        except discord.Forbidden:
            return

        await send_log_embed(
            self.bot, BAN_LOG_CH,
            "⏱️ 도배 자동 제재 (타임아웃 1분)",
            f"{member.mention} 님이 같은 메시지를 {SPAM_THRESHOLD}회 이상 반복해 "
            f"{TIMEOUT_SECONDS}초 타임아웃 처리했습니다.\n메시지: `{content[:200]}`",
            member, discord.Color.red(), guild=member.guild)


async def setup(bot: commands.Bot):
    await bot.add_cog(AntiSpamCog(bot))
