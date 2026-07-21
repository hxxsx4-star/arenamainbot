import re
import time

import discord
from discord.ext import commands

from utils.stats import set_nickname
from utils.logs import is_target_guild
from utils import riot_verify

# 이 역할을 새로 얻으면 온보딩 DM 을 보냅니다. (서버 기본 권한)
BASE_ROLE_ID = 1526595902788206653
_NICK_RE = re.compile(r"^.+#.+$")
_GAME_NAME = {"lol": "롤", "val": "발로란트"}


class IconVerifyView(discord.ui.View):
    """프로필 아이콘 변경으로 라이엇 계정 본인 인증을 진행하는 View."""
    def __init__(self, game: str, nick: str, puuid: str, icon_id: int):
        super().__init__(timeout=riot_verify.VERIFY_TTL)
        self.game, self.nick, self.puuid, self.icon_id = game, nick, puuid, icon_id
        self.expires = time.time() + riot_verify.VERIFY_TTL

    @discord.ui.button(label="아이콘 변경 완료 — 인증 확인", style=discord.ButtonStyle.success, emoji="🔍")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if time.time() > self.expires:
            return await interaction.response.send_message(
                "⏰ 인증 시간이 만료되었습니다. 닉네임 등록을 다시 시작해주세요.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        current = await riot_verify.get_profile_icon(self.puuid)
        if current is None:
            return await interaction.followup.send(
                "⚠️ 라이엇 조회에 실패했습니다. 잠시 후 다시 시도해주세요.", ephemeral=True)
        if current != self.icon_id:
            return await interaction.followup.send(
                "❌ 아이콘이 아직 변경되지 않았어요. 롤 클라이언트에서 지정된 아이콘으로 "
                "변경(저장)한 뒤 잠시 후 다시 눌러주세요.", ephemeral=True)
        await set_nickname(interaction.user.id, self.game, self.nick)
        self.stop()
        await interaction.followup.send(
            f"✅ 본인 인증 완료! {_GAME_NAME[self.game]} 닉네임을 `{self.nick}` (으)로 등록했습니다.\n"
            "프로필 아이콘은 이제 원래대로 되돌리셔도 됩니다.", ephemeral=True)

    @discord.ui.button(label="취소", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.send_message("인증을 취소했습니다.", ephemeral=True)


class NickModal(discord.ui.Modal):
    def __init__(self, game: str):
        super().__init__(title=f"{_GAME_NAME[game]} 닉네임 등록")
        self.game = game
        self.nick = discord.ui.TextInput(
            label=f"{_GAME_NAME[game]} 닉네임 (닉네임#태그)",
            placeholder="예: 홍길동#KR1", min_length=3, max_length=40, required=True)
        self.add_item(self.nick)

    async def on_submit(self, interaction: discord.Interaction):
        value = self.nick.value.strip()
        if not _NICK_RE.match(value):
            return await interaction.response.send_message(
                "❌ `닉네임#태그` 형식으로 입력해주세요. (예: 홍길동#KR1)", ephemeral=True)

        # 라이엇 연동이 없으면 기존처럼 바로 등록
        if not riot_verify.enabled():
            await set_nickname(interaction.user.id, self.game, value)
            return await interaction.response.send_message(
                f"✅ {_GAME_NAME[self.game]} 닉네임을 `{value}` (으)로 등록했습니다!", ephemeral=True)

        # 본인 인증: 계정 존재 확인 → 아이콘 변경 요청
        await interaction.response.defer(ephemeral=True)
        puuid = await riot_verify.get_puuid(value)
        if not puuid:
            return await interaction.followup.send(
                f"❌ `{value}` 라이엇 계정을 찾을 수 없습니다. 닉네임#태그를 확인해주세요.",
                ephemeral=True)
        current = await riot_verify.get_profile_icon(puuid)
        icon_id = riot_verify.pick_icon(current)

        embed = discord.Embed(
            title="🔐 라이엇 계정 본인 인증",
            description=(f"`{value}` 계정이 본인 소유인지 확인할게요.\n\n"
                         "**1.** 롤 클라이언트에 접속해 좌측 상단 **내 프로필 아이콘** 클릭\n"
                         "**2.** 오른쪽에 보이는 **이 아이콘**으로 변경 후 저장\n"
                         "**3.** 아래 **인증 확인** 버튼 클릭\n\n"
                         "⏰ 제한시간 10분 · 인증 후 아이콘은 되돌려도 됩니다."
                         + ("\n\n💡 발로란트도 **같은 라이엇 계정**이라, "
                            "롤 클라이언트 아이콘 변경으로 인증됩니다."
                            if self.game == "val" else "")),
            color=discord.Color.gold())
        embed.set_thumbnail(url=riot_verify.ICON_IMG.format(id=icon_id))
        await interaction.followup.send(
            embed=embed, view=IconVerifyView(self.game, value, puuid, icon_id),
            ephemeral=True)


class GameRegView(discord.ui.View):
    def __init__(self, game: str):
        super().__init__(timeout=1800)
        self.game = game

    @discord.ui.button(label="닉네임 작성", style=discord.ButtonStyle.success, emoji="✏️")
    async def write(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(NickModal(self.game))

    @discord.ui.button(label="게임을 하지 않음", style=discord.ButtonStyle.secondary)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            f"{_GAME_NAME[self.game]}은(는) 건너뛰었습니다. 나중에 하고 싶으면 관리자에게 `/닉네임등록`을 요청하세요.",
            ephemeral=True)


class OnboardingView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # 온보딩은 오래 유지

    @discord.ui.button(label="롤 닉네임 등록", style=discord.ButtonStyle.primary, emoji="🎮", custom_id="onboard_lol")
    async def lol(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("롤 닉네임을 등록할까요?", view=GameRegView("lol"), ephemeral=True)

    @discord.ui.button(label="발로란트 닉네임 등록", style=discord.ButtonStyle.danger, emoji="🔫", custom_id="onboard_val")
    async def val(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("발로란트 닉네임을 등록할까요?", view=GameRegView("val"), ephemeral=True)


class OnboardingCog(commands.Cog):
    """서버 기본 권한 획득 시 닉네임 등록 안내 DM 을 보냅니다."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._registered = False

    @commands.Cog.listener()
    async def on_ready(self):
        # 재시작 후에도 온보딩 버튼이 계속 동작하도록 영속 뷰 등록
        if not self._registered:
            self.bot.add_view(OnboardingView())
            self._registered = True

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if not is_target_guild(after.guild):
            return
        had = any(r.id == BASE_ROLE_ID for r in before.roles)
        has = any(r.id == BASE_ROLE_ID for r in after.roles)
        if has and not had:
            await self._send_dm(after)

    async def _send_dm(self, member: discord.Member):
        embed = discord.Embed(
            title="🏟️ 종합게임 아레나에 오신 걸 환영합니다!",
            description=("내전 참여를 위해 게임 닉네임을 등록해주세요.\n"
                         "아래 버튼을 눌러 **롤** 또는 **발로란트** 닉네임을 등록할 수 있어요.\n"
                         "안 하는 게임은 건너뛰어도 됩니다."),
            color=discord.Color.blurple(),
        )
        try:
            await member.send(embed=embed, view=OnboardingView())
        except discord.Forbidden:
            print(f"[온보딩] {member} 님 DM 이 닫혀있어 안내를 보내지 못했습니다.")
        except Exception as e:
            print(f"[온보딩] DM 전송 실패: {e}")


async def setup(bot: commands.Bot):
    await bot.add_cog(OnboardingCog(bot))
