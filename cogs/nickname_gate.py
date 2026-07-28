"""닉네임 등록 채널 — `나이(년생) 닉네임` 형식 자동 인식 + 역할 지급.

지정 채널에 그 형식으로 글을 쓰면 서버 닉네임으로 반영하고 정회원 역할을
지급한다. 형식을 안 지키거나 닉네임에 금지어가 있으면 이 채널 말고는
아무 채널도 못 보는 격리 역할을 준다.
안내 임베드는 사람들이 올린 메시지들을 지우지 않고(가입 히스토리 확인용) 그
아래에 새로 보내는 방식으로 항상 채널 최신 메시지 자리를 유지한다.
"""
import json
import os
import re
from datetime import time as dtime, timedelta, timezone

import discord
from discord.ext import commands, tasks

from utils.logs import is_target_guild, send_log_embed, ROLE_LOG_CH

ONBOARD_CH_ID = 1526595115232133140      # 닉네임 등록 채널
OK_ROLE_ID = 1526595902788206653         # 형식 통과 → 정회원 역할
FAIL_ROLE_ID = 1529585636095426590       # 형식 불일치 → 안내 채널만 보이는 격리 역할

KST = timezone(timedelta(hours=9))
REMINDER_TIMES = [dtime(hour=10, tzinfo=KST), dtime(hour=14, tzinfo=KST), dtime(hour=18, tzinfo=KST)]

# 년생(뒤 두 자리) + 닉네임(한글 1~8글자). 대괄호는 인식하지 않는다 (예: "03 원샷").
_ENTRY_RE = re.compile(r"^\s*(\d{2})\s*[\/\-]?\s*([가-힣]{1,8})\s*$")

# 등록 완료 후 실제로 반영되는 닉네임 형식 ("03 원샷"). 기존 멤버 점검용.
_NICK_OK_RE = re.compile(r"^\d{2} [가-힣]{1,8}$")

# 닉네임에 못 쓰게 막을 단어 (욕설/비하 표현)
_BANNED_WORDS = {
    "씨발", "시발", "씨팔", "쓰발", "ㅅㅂ", "ㅄ", "병신",
    "개새끼", "개새기", "좆", "조까", "지랄",
    "미친놈", "미친년", "걸레", "창녀", "보지", "자지",
}


def _has_banned_word(nick: str) -> bool:
    return any(w in nick for w in _BANNED_WORDS)

SHARED_DIR = os.environ.get("ARENA_SHARED_DIR", "/home/hxxsx4/shared_data")
STATE_PATH = os.path.join(SHARED_DIR, "nickname_gate_state.json")


def _guide_embed() -> discord.Embed:
    return discord.Embed(
        title="📋 닉네임 등록 안내",
        description=(
            "이 채널에 아래처럼 **나이(년생 뒤 두 자리)** 와 **서버에서 쓸 닉네임**을 적어주세요.\n\n"
            "```\n03 원샷\n```\n"
            "닉네임은 **한글 1~8글자**만 가능합니다. (대괄호 등 기호는 넣지 마세요)\n"
            "형식에 맞으면 서버 닉네임이 `03 원샷`처럼 **나이 + 닉네임**으로 자동 반영되고 "
            "정회원 역할이 지급돼요.\n"
            "형식이 틀리면 이 채널 외 다른 채널이 전부 안 보이게 되니 다시 정확히 작성해주세요."
        ),
        color=discord.Color.blurple(),
    )


class NicknameGateCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.state = self._load_state()
        self._backfilled = False
        self.remind_nickname.start()

    def cog_unload(self):
        self.remind_nickname.cancel()

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
            if not self._backfilled:
                await self._backfill_existing_members(guild)
        self._backfilled = True

    # ----- 배포 전부터 있던 기존 멤버 점검 -----
    async def _backfill_existing_members(self, guild: discord.Guild):
        ok_role = guild.get_role(OK_ROLE_ID)
        fail_role = guild.get_role(FAIL_ROLE_ID)
        if not fail_role:
            return
        for member in guild.members:
            if member.bot or member.id == guild.owner_id:
                continue
            if member.guild_permissions.administrator:
                continue  # 관리자/운영진은 락 걸리면 서버 관리 자체가 막히니 제외
            if fail_role in member.roles:
                continue  # 이미 격리 처리됨
            name = member.nick or member.name
            if _NICK_OK_RE.match(name):
                continue  # 이미 형식에 맞음

            try:
                if ok_role and ok_role in member.roles:
                    await member.remove_roles(ok_role, reason="닉네임 형식 미준수 (기존 멤버 점검)")
                await member.add_roles(fail_role, reason="닉네임 형식 미준수 (기존 멤버 점검)")
            except discord.Forbidden:
                continue

            await send_log_embed(
                self.bot, ROLE_LOG_CH,
                "⚠️ 기존 멤버 닉네임 형식 미준수",
                f"{member.mention} 님 닉네임(`{name}`)이 형식에 맞지 않아 격리 처리했습니다.",
                member, discord.Color.orange(), guild=guild)

    # ----- 하루 3번 미등록자 재촉 -----
    @tasks.loop(time=REMINDER_TIMES)
    async def remind_nickname(self):
        for guild in self.bot.guilds:
            if not is_target_guild(guild):
                continue
            role = guild.get_role(FAIL_ROLE_ID)
            channel = guild.get_channel(ONBOARD_CH_ID)
            if not role or not channel or not role.members:
                continue
            try:
                await channel.send(
                    f"⏰ {role.mention} 아직 닉네임을 안 쓰신 분들, 이 채널에 "
                    "`년생 닉네임` 형식으로 적어주세요! (예: `03 원샷`)",
                    allowed_mentions=discord.AllowedMentions(roles=True))
            except discord.Forbidden:
                pass

    @remind_nickname.before_loop
    async def _before_remind(self):
        await self.bot.wait_until_ready()

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
        if match and _has_banned_word(match.group(2)):
            await self._handle_fail(message.author, "부적절한 닉네임")
        elif match:
            await self._handle_pass(message.author, match.group(1), match.group(2))
        else:
            await self._handle_fail(message.author)

        await self._repost_guide(message.channel)

    async def _handle_pass(self, member: discord.Member, age: str, nick: str):
        guild = member.guild
        combined = f"{age} {nick}"
        try:
            await member.edit(nick=combined, reason="닉네임 등록 형식 확인")
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
            "✅ 닉네임 등록 완료", f"{member.mention} → 닉네임 `{combined}`",
            member, discord.Color.green(), guild=guild)

    async def _handle_fail(self, member: discord.Member, reason: str = "형식 불일치"):
        guild = member.guild
        role = guild.get_role(FAIL_ROLE_ID)
        if not role or role in member.roles:
            return
        try:
            await member.add_roles(role, reason=f"닉네임 등록 {reason}")
        except discord.Forbidden:
            return
        await send_log_embed(
            self.bot, ROLE_LOG_CH,
            "⚠️ 닉네임 등록 실패", f"{member.mention} 님이 {reason}(으)로 처리됐습니다.",
            member, discord.Color.orange(), guild=guild)


async def setup(bot: commands.Bot):
    await bot.add_cog(NicknameGateCog(bot))
