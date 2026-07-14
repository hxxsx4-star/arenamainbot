import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional

CURRENCY = "Point"

class HelpKorCog(commands.Cog):
    """
    /도움, /사용법게시 명령어를 총괄하는 Cog
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _build_user_embed(self) -> discord.Embed:
        """일반 사용자용 도움말 임베드를 생성합니다."""
        embed = discord.Embed(
            title="🧭 명령어 안내",
            description="모든 명령어는 슬래시(`/`)를 사용하여 입력합니다.",
            color=discord.Color.blurple(),
        )

        embed.add_field(
            name="💰 경제 및 정보",
            value=(
                f"• `/프로필 [유저]`: 유저의 프로필(전적, 경고, 포인트 순위 등)을 확인합니다.\n"
                f"• `/지갑 [유저]`: 포인트 보유량을 확인합니다.\n"
                f"• `/출석`: 하루 1회 포인트를 받습니다. (보상: 50 {CURRENCY})\n"
                f"• `/순위`: 서버의 전체 포인트 보유량 순위를 확인합니다."
            ),
            inline=False,
        )

        embed.add_field(
            name="🔊 음성 채널",
            value="• 음성 채널에 참여하면 1시간당 10포인트를 자동으로 받습니다.",
            inline=False,
        )

        embed.add_field(
            name="⚔️ 내전 (포럼)",
            value=(
                f"• 참여: 내전 모집 게시글에서 '손' 또는 'ㅅ'을 입력하여 참여합니다.\n"
                f"• 취소: 본인이 작성한 참여 메시지를 삭제하면 참여가 취소됩니다.\n"
                f"• `/내전 진행`: (관리자용) 참여자 명단을 티어순으로 정렬하고 MVP 투표를 시작합니다."
            ),
            inline=False,
        )

        embed.add_field(
            name="🛎️ 역할 상점",
            value=(
                f"• `/상점`: 버튼을 통해 역할 구매 상점을 이용할 수 있습니다."
            ),
            inline=False,
        )

        embed.add_field(
            name="✉️ 1:1 문의",
            value="• 지정된 채널의 '1:1 문의 채널 생성' 버튼을 통해 관리자와의 비공개 대화를 시작할 수 있습니다.",
            inline=False
        )

        embed.set_footer(text="관리자용 명령어는 '/도움 분류:관리자'를 선택하여 확인하세요.")
        return embed

    def _build_admin_embed(self) -> discord.Embed:
        """관리자용 도움말 임베드를 생성합니다."""
        embed = discord.Embed(
            title="🛠️ 관리자 명령어 안내",
            description="모든 명령어는 슬래시(`/`)를 사용하여 입력합니다.",
            color=discord.Color.orange(),
        )

        embed.add_field(
            name="💰 경제 관리",
            value=(
                f"• `/지급 [유저] [금액]`: 특정 유저에게 포인트를 지급합니다.\n"
                f"• `/회수 [유저] [금액]`: 특정 유저의 포인트를 회수합니다."
            ),
            inline=False,
        )

        embed.add_field(
            name="⚔️ 내전 관리",
            value=(
                f"• `/내전 진행 [인원수]`: 현재 스레드의 참여자를 바탕으로 내전을 시작하고 MVP 투표를 게시합니다."
            ),
            inline=False,
        )

        embed.add_field(
            name="🔨 경매 내전 관리",
            value=(
                f"• `/경매 팀장 [유저] [팀]`: 경매 팀장을 설정합니다.\n"
                f"• `/경매 시작 [포인트]`: 모든 팀장에게 포인트를 지급하고 경매를 시작합니다.\n"
                f"• `/경매 대상 [유저] [시작가]`: 특정 유저의 경매를 시작합니다.\n"
                f"• `/경매 낙찰`: 현재 경매를 최고가로 낙찰시킵니다.\n"
                f"• `/경매 종료`: 진행중인 경매를 강제 종료하고 모든 데이터를 초기화합니다."
            ),
            inline=False,
        )

        embed.add_field(
            name="🚫 제재 관리",
            value=(
                f"• `/경고 [유저] [횟수] [사유]`: 유저에게 경고를 부여합니다.\n"
                f"• `/차감 [유저] [횟수] [사유]`: 유저의 경고를 차감합니다."
            ),
            inline=False,
        )

        embed.add_field(
            name="⚙️ 봇 / 상점 / 티켓 관리",
            value=(
                f"• `/동기화`: 봇의 슬래시 커맨드를 디스코드에 수동으로 동기화합니다.\n"
                f"• `/사용법게시 [채널]`: 지정된 채널에 일반 봇 사용법 안내를 게시합니다.\n"
                f"• `/상점-리로드`: 상점 캐시를 리로드합니다.\n"
                f"• `/티켓생성 [채널]`: 지정된 채널에 1:1 문의 생성 패널을 게시합니다."
            ),
            inline=False,
        )
        return embed

    @app_commands.command(name="도움", description="봇 명령어 사용법과 도움말을 확인합니다.")
    @app_commands.describe(분류="확인할 도움말 종류 (기본값: 일반)")
    @app_commands.choices(분류=[
        app_commands.Choice(name="일반", value="user"),
        app_commands.Choice(name="관리자", value="admin")
    ])
    async def help_cmd(self, interaction: discord.Interaction, 분류: Optional[app_commands.Choice[str]] = None):
        choice_val = 분류.value if 분류 else "user"

        if choice_val == "admin":
            if not interaction.user.guild_permissions.manage_guild:
                await interaction.response.send_message("❌ 이 도움말을 볼 수 있는 관리자 권한이 없습니다.", ephemeral=True)
                return
            await interaction.response.send_message(embed=self._build_admin_embed(), ephemeral=True)
        else:
            await interaction.response.send_message(embed=self._build_user_embed(), ephemeral=True)

    @app_commands.command(name="사용법게시", description="관리자 전용: 지정된 채널에 일반 사용법 안내를 게시합니다.")
    @app_commands.describe(channel="사용법을 게시할 텍스트 채널")
    @app_commands.default_permissions(manage_guild=True)
    async def post_guide(self, interaction: discord.Interaction, channel: discord.TextChannel):
        guide_embed = self._build_user_embed()
        try:
            await channel.send(embed=guide_embed)
            await interaction.response.send_message(f"✅ {channel.mention} 채널에 사용법 안내를 성공적으로 게시했습니다.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message(f"❌ {channel.mention} 채널에 메시지를 보낼 권한이 없습니다.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ 알 수 없는 오류로 메시지 전송에 실패했습니다: {e}", ephemeral=True)

    @app_commands.command(name="동기화", description="관리자 전용: 봇의 슬래시 커맨드를 디스코드에 수동으로 동기화합니다.")
    @app_commands.default_permissions(administrator=True)
    async def sync_commands_slash(self, interaction: discord.Interaction):
        await interaction.response.send_message("🔄 슬래시 커맨드 동기화를 시작합니다...", ephemeral=True)
        try:
            synced = await self.bot.tree.sync()
            await interaction.followup.send(f"✅ 슬래시 커맨드 {len(synced)}개가 성공적으로 동기화되었습니다!\n*(명령어가 안 보인다면 디스코드를 선택 후 `Ctrl + R`을 눌러 새로고침 해주세요.)*", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ 동기화 중 오류가 발생했습니다: {e}", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(HelpKorCog(bot))