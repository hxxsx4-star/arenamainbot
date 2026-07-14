import discord
from discord.ext import commands
from discord import app_commands
import traceback

@app_commands.guild_only()
class AdminCog(commands.Cog, name="관리"):
    """관리자용 개별 슬래시 커맨드들을 통합 관리합니다."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # =======================================================
    # Cog 전용 에러 핸들러 (Traceback 출력)
    # =======================================================
    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        original_error = getattr(error, "original", error)

        # 콘솔에 상세 에러 로그(Traceback) 출력
        print(f"\n[오류 발생] /{interaction.command.name} 명령어 실행 중 문제가 발생했습니다.")
        traceback.print_exception(type(original_error), original_error, original_error.__traceback__)
        print("-" * 50)

        error_msg = f"❌ 명령어 실행 중 오류가 발생했습니다.\n```py\n{str(original_error)[:1900]}\n```"

        if interaction.response.is_done():
            await interaction.followup.send(error_msg, ephemeral=True)
        else:
            await interaction.response.send_message(error_msg, ephemeral=True)

    # --- Economy Admin Commands ---
    @app_commands.command(name="지급", description="특정 유저에게 포인트를 지급합니다.")
    @app_commands.describe(유저="포인트를 지급할 유저", 금액="지급할 포인트 양")
    @app_commands.default_permissions(manage_guild=True) # 관리자 권한 제한
    async def grant_points(self, interaction: discord.Interaction, 유저: discord.Member, 금액: int):
        eco_cog = self.bot.get_cog("EconomyCog")
        if eco_cog:
            await eco_cog.grant_points(interaction, 유저, 금액)
        else:
            await interaction.response.send_message("❌ EconomyCog를 찾을 수 없습니다.", ephemeral=True)

    @app_commands.command(name="회수", description="특정 유저의 포인트를 회수합니다.")
    @app_commands.describe(유저="포인트를 회수할 유저", 금액="회수할 포인트 양")
    @app_commands.default_permissions(manage_guild=True)
    async def revoke_points(self, interaction: discord.Interaction, 유저: discord.Member, 금액: int):
        eco_cog = self.bot.get_cog("EconomyCog")
        if eco_cog:
            await eco_cog.revoke_points(interaction, 유저, 금액)
        else:
            await interaction.response.send_message("❌ EconomyCog를 찾을 수 없습니다.", ephemeral=True)

    # --- Match Admin Commands ---
    @app_commands.command(name="내전제외", description="내전에서 특정 유저를 제외합니다.")
    @app_commands.describe(유저="제외할 유저")
    @app_commands.default_permissions(manage_guild=True)
    async def kick_from_match(self, interaction: discord.Interaction, 유저: discord.Member):
        match_cog = self.bot.get_cog("MatchCog")
        if match_cog:
            await match_cog.kick_from_match(interaction, 유저)
        else:
            await interaction.response.send_message("❌ MatchCog를 찾을 수 없습니다.", ephemeral=True)

    @app_commands.command(name="내전정지", description="특정 유저의 내전 참여를 정지시킵니다.")
    @app_commands.describe(일수="정지할 일수 (0일 시 해제)", 유저="정지시킬 유저")
    @app_commands.default_permissions(manage_guild=True)
    async def ban_from_match(self, interaction: discord.Interaction, 일수: int, 유저: discord.Member):
        match_cog = self.bot.get_cog("MatchCog")
        if match_cog:
            await match_cog.ban_from_match(interaction, 일수, 유저)
        else:
            await interaction.response.send_message("❌ MatchCog를 찾을 수 없습니다.", ephemeral=True)

    # --- Shop Admin Commands ---
    @app_commands.command(name="상점리로드", description="상점 설정을 다시 불러옵니다.")
    @app_commands.default_permissions(manage_guild=True)
    async def reload_shop_config(self, interaction: discord.Interaction):
        shop_cog = self.bot.get_cog("ShopCog")
        if shop_cog:
            await shop_cog.reload_shop_config(interaction)
        else:
            await interaction.response.send_message("❌ ShopCog를 찾을 수 없습니다.", ephemeral=True)

    # --- Ticket Admin Commands ---
    @app_commands.command(name="티켓생성", description="지정된 채널에 1:1 문의 생성 패널을 게시합니다.")
    @app_commands.describe(채널="패널을 게시할 텍스트 채널")
    @app_commands.default_permissions(manage_guild=True)
    async def create_ticket_panel(self, interaction: discord.Interaction, 채널: discord.TextChannel):
        ticket_cog = self.bot.get_cog("TicketSystemCog")
        if ticket_cog:
            await ticket_cog.create_ticket_panel(interaction, 채널)
        else:
            await interaction.response.send_message("❌ TicketSystemCog를 찾을 수 없습니다.", ephemeral=True)

    # --- Moderation Admin Commands ---
    @app_commands.command(name="경고", description="특정 유저에게 경고를 부여합니다.")
    @app_commands.describe(유저="경고를 부여할 유저", 횟수="부여할 경고 횟수", 사유="경고 사유")
    @app_commands.default_permissions(manage_guild=True)
    async def give_warning(self, interaction: discord.Interaction, 유저: discord.Member, 횟수: int, 사유: str):
        mod_cog = self.bot.get_cog("ModerationCog")
        if mod_cog:
            await mod_cog.give_warning(interaction, 유저, 횟수, 사유)
        else:
            await interaction.response.send_message("❌ ModerationCog를 찾을 수 없습니다. 봇 관리자에게 문의하세요.", ephemeral=True)

    @app_commands.command(name="차감", description="특정 유저의 경고를 차감합니다.")
    @app_commands.describe(유저="경고를 차감할 유저", 횟수="차감할 경고 횟수", 사유="차감 사유")
    @app_commands.default_permissions(manage_guild=True)
    async def reduce_warning(self, interaction: discord.Interaction, 유저: discord.Member, 횟수: int, 사유: str):
        mod_cog = self.bot.get_cog("ModerationCog")
        if mod_cog:
            await mod_cog.reduce_warning(interaction, 유저, 횟수, 사유)
        else:
            await interaction.response.send_message("❌ ModerationCog를 찾을 수 없습니다. 봇 관리자에게 문의하세요.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))