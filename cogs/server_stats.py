"""서버 통계 음성채널 — 지정 카테고리에 전체인원/음성인원을 보여주는
'표시 전용'(입장 불가) 음성채널 3개를 만들고 주기적으로 이름을 갱신한다.

채널 이름 변경은 디스코드 쪽에서 채널당 10분에 2회로 제한돼 있어서
10분 간격으로만 갱신한다.
"""
import json
import os

import discord
from discord.ext import commands, tasks

from utils.logs import is_target_guild

CATEGORY_ID = 1531544610843656304
TITLE_NAME = "🔥24 HOUR GAME NO.1 ARENA🔥"

SHARED_DIR = os.environ.get("ARENA_SHARED_DIR", "/home/hxxsx4/shared_data")
STATE_PATH = os.path.join(SHARED_DIR, "server_stats_state.json")


class ServerStatsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.state = self._load_state()
        self.refresh_counts.start()

    def cog_unload(self):
        self.refresh_counts.cancel()

    def _load_state(self) -> dict:
        try:
            with open(STATE_PATH, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_state(self):
        try:
            os.makedirs(SHARED_DIR, exist_ok=True)
            tmp = STATE_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.state, f, ensure_ascii=False, indent=2)
            os.replace(tmp, STATE_PATH)
        except OSError as e:
            print(f"🚨 [서버통계] 상태 저장 실패: {e}")

    @commands.Cog.listener()
    async def on_ready(self):
        for guild in self.bot.guilds:
            if not is_target_guild(guild):
                continue
            await self._ensure_channels(guild)
            await self._update_counts(guild)

    # ----- 채널 3개 존재 보장 (없으면 생성) -----
    async def _ensure_channels(self, guild: discord.Guild):
        category = guild.get_channel(CATEGORY_ID)
        if not isinstance(category, discord.CategoryChannel):
            print(f"🚨 [서버통계] 카테고리 {CATEGORY_ID} 를 찾을 수 없습니다.")
            return

        overwrites = {guild.default_role: discord.PermissionOverwrite(connect=False)}

        for key, name in (("title", TITLE_NAME),
                          ("total", "전체인원 : 0"),
                          ("voice", "음성인원 : 0")):
            ch_id = self.state.get(key)
            channel = guild.get_channel(ch_id) if ch_id else None
            if channel is None:
                channel = await guild.create_voice_channel(
                    name, category=category, overwrites=overwrites,
                    reason="서버 통계 채널 생성")
                self.state[key] = channel.id
                self._save_state()

    # ----- 10분마다 인원수 갱신 -----
    @tasks.loop(minutes=10)
    async def refresh_counts(self):
        for guild in self.bot.guilds:
            if not is_target_guild(guild):
                continue
            await self._update_counts(guild)

    @refresh_counts.before_loop
    async def _before_refresh(self):
        await self.bot.wait_until_ready()

    async def _update_counts(self, guild: discord.Guild):
        total_ch = guild.get_channel(self.state.get("total", 0))
        voice_ch = guild.get_channel(self.state.get("voice", 0))
        voice_count = sum(1 for vc in guild.voice_channels for m in vc.members if not m.bot)

        for channel, new_name in (
            (total_ch, f"전체인원 : {guild.member_count}"),
            (voice_ch, f"음성인원 : {voice_count}"),
        ):
            if channel and channel.name != new_name:
                try:
                    await channel.edit(name=new_name, reason="서버 통계 갱신")
                except discord.HTTPException as e:
                    print(f"🚨 [서버통계] 채널 이름 갱신 실패: {e}")


async def setup(bot: commands.Bot):
    await bot.add_cog(ServerStatsCog(bot))
