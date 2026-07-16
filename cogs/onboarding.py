import re

import discord
from discord.ext import commands

from utils.stats import set_nickname
from utils.logs import is_target_guild

# 이 역할을 새로 얻으면 온보딩 DM 을 보냅니다. (서버 기본 권한)
BASE_ROLE_ID = 1526595902788206653
_NICK_RE = re.compile(r"^.+#.+$")
_GAME_NAME = {"lol": "롤", "val": "발로란트"}


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
        await set_nickname(interaction.user.id, self.game, value)
        await interaction.response.send_message(
            f"✅ {_GAME_NAME[self.game]} 닉네임을 `{value}` (으)로 등록했습니다!", ephemeral=True)


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
