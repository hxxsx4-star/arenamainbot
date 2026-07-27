"""닉네임 등록 채널 — `나이(년생) 닉네임` 형식 자동 인식 + 역할 지급.

지정 채널에 그 형식으로 글을 쓰면 서버 닉네임으로 반영하고 정회원 역할을
지급한다. 형식을 안 지키면 이 채널 말고는 아무 채널도 못 보는 격리 역할을 준다.
안내 임베드는 사람들이 올린 메시지들을 지우지 않고(가입 히스토리 확인용) 그
아래에 새로 보내는 방식으로 항상 채널 최신 메시지 자리를 유지한다.
"""
import json
import os
import re

import discord
from discord.ext import commands

from utils.logs import is_target_guild, send_log_embed, ROLE_LOG_CH

ONBOARD_CH_ID = 1526595115232133140      # 닉네임 등록 채널
OK_ROLE_ID = 1526595902788206653         # 형식 통과 → 정회원 역할
FAIL_ROLE_ID = 1529585636095426590       # 형식 불일치 → 안내 채널만 보이는 격리 역할

# 년생(뒤 두 자리) + 닉네임(한글 1~8글자). 대괄호/슬래시/공백 등 구분자는 있어도
# 없어도 인정한다 (예: "03 원샷", "[03] [원샷]", "03/원샷" 전부 통과).
_ENTRY_RE = re.compile(r"^\s*\[?\s*(\d{2})\s*\]?\s*[\/\-]?\s*\[?\s*([가-힣]{1,8})\s*\]?\s*$")

SHARED_DIR = os.environ.get("ARENA_SHARED_DIR", "/home/hxxsx4/shared_data")
STATE_PATH = os.path.join(SHARED_DIR, "nickname_gate_state.json")


def _guide_embed() -> discord.Embed:
    return discord.Embed(
        title="📋 닉네임 등록 안내",
        description=(
            "이 채널에 아래처럼 **나이(년생 뒤 두 자리)** 와 **서버에서 쓸 닉네임**을 적어주세요.\n\n"
            "```\n03 원샷\n```\n"
            "닉네임은 **한글 1~8글자**만 가능합니다.\n"
            "형식에 맞으면 서버 닉네임이 자동으로 바뀌고 정회원 역할이 지급돼요.\n"
            "형식이 틀리면 이 채널 외 다른 채널이 전부 안 보이게 되니 다시 정확히 작성해주세요."
        ),
        color=discord.Color.blurple(),
    )


class NicknameGateCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.state = self._load_state()

    # ----- 상태(안내 메시지 ID) -----
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
            print(f"🚨 [닉네임게이트] 상태 저장 실패: {e}")

    @commands.Cog.listener()
    async def on_ready(self):
        for guild in self.bot.guilds:
            if not is_target_guild(guild):
                continue
            await self._sync_role_overwrites(guild)
            channel = guild.get_channel(ONBOARD_CH_ID)
            if channel:
                await self._ensure_guide(channel)

    # ----- 격리 역할: 안내 채널 제외 전 채널 비공개 -----
    async def _sync_role_overwrites(self, guild: discord.Guild):
        role = guild.get_role(FAIL_ROLE_ID)
        if not role:
            return
        for channel in guild.channels:
            visible = channel.id == ONBOARD_CH_ID
            current = channel.overwrites_for(role)
            if current.view_channel is visible:
                continue
            current.view_channel = visible
            try:
                await channel.set_permissions(
                    role, overwrite=current, reason="닉네임 미등록 격리 역할 채널 접근 제한")
            except discord.Forbidden:
                pass

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        if not is_target_guild(channel.guild):
            return
        role = channel.guild.get_role(FAIL_ROLE_ID)
        if not role:
            return
        try:
            await channel.set_permissions(
                role, view_channel=(channel.id == ONBOARD_CH_ID),
                reason="닉네임 미등록 격리 역할 채널 접근 제한")
        except discord.Forbidden:
            pass

    # ----- 안내 메시지: 항상 채널의 최신 메시지로 유지 -----
    async def _ensure_guide(self, channel: discord.TextChannel):
        old_id = self.state.get("guide_msg_id")
        if old_id:
            try:
                await channel.fetch_message(old_id)
                return  # 아직 살아있으면 그대로 둔다 (재시작마다 새로 보낼 필요 없음)
            except discord.NotFound:
                pass
            except discord.Forbidden:
                return
        else:
            # 이 기능 도입 전에 봇이 올려뒀을 수 있는 예전 안내 메시지를 정리
            try:
                async for msg in channel.history(limit=50):
                    if msg.author.id == self.bot.user.id:
                        await msg.delete()
            except discord.Forbidden:
                pass
        await self._repost_guide(channel)

    async def _repost_guide(self, channel: discord.TextChannel):
        old_id = self.state.get("guide_msg_id")
        if old_id:
            try:
                old = await channel.fetch_message(old_id)
                await old.delete()
            except (discord.NotFound, discord.Forbidden):
                pass
        try:
            msg = await channel.send(embed=_guide_embed())
        except discord.Forbidden:
            return
        self.state["guide_msg_id"] = msg.id
        self._save_state()

    # ----- 메시지 처리 -----
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return
        if not is_target_guild(message.guild):
            return
        if message.channel.id != ONBOARD_CH_ID:
            return

        match = _ENTRY_RE.match(message.content)
        if match:
            await self._handle_pass(message.author, match.group(2))
        else:
            await self._handle_fail(message.author)

        await self._repost_guide(message.channel)

    async def _handle_pass(self, member: discord.Member, nick: str):
        guild = member.guild
        try:
            await member.edit(nick=nick, reason="닉네임 등록 형식 확인")
        except discord.Forbidden:
            pass

        ok_role = guild.get_role(OK_ROLE_ID)
        fail_role = guild.get_role(FAIL_ROLE_ID)
        try:
            if ok_role and ok_role not in member.roles:
                await member.add_roles(ok_role, reason="닉네임 등록 형식 확인")
            if fail_role and fail_role in member.roles:
                await member.remove_roles(fail_role, reason="닉네임 등록 형식 확인 완료")
        except discord.Forbidden:
            pass

        await send_log_embed(
            self.bot, ROLE_LOG_CH,
            "✅ 닉네임 등록 완료", f"{member.mention} → 닉네임 `{nick}`",
            member, discord.Color.green(), guild=guild)

    async def _handle_fail(self, member: discord.Member):
        guild = member.guild
        role = guild.get_role(FAIL_ROLE_ID)
        if not role or role in member.roles:
            return
        try:
            await member.add_roles(role, reason="닉네임 등록 형식 불일치")
        except discord.Forbidden:
            return
        await send_log_embed(
            self.bot, ROLE_LOG_CH,
            "⚠️ 닉네임 형식 불일치", f"{member.mention} 님이 형식에 맞지 않는 메시지를 보냈습니다.",
            member, discord.Color.orange(), guild=guild)


async def setup(bot: commands.Bot):
    await bot.add_cog(NicknameGateCog(bot))
