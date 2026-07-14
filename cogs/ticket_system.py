import discord
from discord.ext import commands
from discord import app_commands
import asyncio

TICKET_CREATOR_ID = "ticket_creator_id"

# ───────────────── Views ─────────────────

class ClosedTicketView(discord.ui.View):
    """닫힌 티켓에 표시되는 View (삭제, 다시 열기)"""
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="티켓 삭제", style=discord.ButtonStyle.danger, custom_id="delete_ticket")
    async def delete_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("관리자만 티켓을 삭제할 수 있습니다.", ephemeral=True)
            return

        await interaction.response.send_message("5초 후 채널을 삭제합니다...")
        await asyncio.sleep(5)
        await interaction.channel.delete(reason="관리자에 의해 티켓이 삭제됨")

    @discord.ui.button(label="티켓 다시 열기", style=discord.ButtonStyle.success, custom_id="reopen_ticket")
    async def reopen_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("관리자만 티켓을 다시 열 수 있습니다.", ephemeral=True)
            return

        creator_id_str = interaction.channel.topic
        if not creator_id_str or not creator_id_str.startswith(TICKET_CREATOR_ID):
            await interaction.response.send_message("티켓 생성자 정보를 찾을 수 없습니다.", ephemeral=True)
            return

        creator_id = int(creator_id_str.split(":")[1])
        creator = interaction.guild.get_member(creator_id)

        if creator:
            await interaction.channel.set_permissions(creator, send_messages=True, view_channel=True)

        embed = discord.Embed(title="✉️ 1:1 문의", description=f"관리자가 티켓을 다시 열었습니다. 문의를 계속 진행해주세요.", color=discord.Color.green())
        await interaction.response.edit_message(embed=embed, view=OpenTicketView())

class OpenTicketView(discord.ui.View):
    """열린 티켓에 표시되는 View (닫기)"""
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="티켓 닫기", style=discord.ButtonStyle.secondary, custom_id="close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        creator_id_str = interaction.channel.topic
        if not creator_id_str or not creator_id_str.startswith(TICKET_CREATOR_ID):
            await interaction.response.send_message("티켓 생성자 정보를 찾을 수 없습니다.", ephemeral=True)
            return

        creator_id = int(creator_id_str.split(":")[1])

        if not (interaction.user.guild_permissions.administrator or interaction.user.id == creator_id):
            await interaction.response.send_message("관리자 또는 티켓 생성자만 티켓을 닫을 수 있습니다.", ephemeral=True)
            return

        creator = interaction.guild.get_member(creator_id)
        if creator:
            await interaction.channel.set_permissions(creator, send_messages=False)

        embed = discord.Embed(title="🔒 티켓이 닫혔습니다", description="관리자가 이 티켓을 삭제하거나 다시 열 수 있습니다.", color=discord.Color.orange())
        await interaction.response.edit_message(embed=embed, view=ClosedTicketView())

class TicketSystemView(discord.ui.View):
    """1:1 문의 채널 생성 버튼이 있는 초기 View"""
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="1:1 문의 채널 생성", style=discord.ButtonStyle.success, custom_id="create_ticket_button")
    async def create_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        user = interaction.user
        channel_name = f"문의-{user.name}"

        existing_channel = discord.utils.get(guild.text_channels, name=channel_name)
        if existing_channel:
            await interaction.followup.send(f"이미 본인의 문의 채널({existing_channel.mention})이 존재합니다.", ephemeral=True)
            return

        # 기본 권한 설정
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True)
        }

        # 특정 역할(1522224219138691184)에게 채널 보기 및 메시지 보내기 권한 부여 추가
        support_role = guild.get_role(1522224219138691184)
        if support_role:
            overwrites[support_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

        # 관리자 권한을 가진 모든 역할에게 권한 부여
        for role in guild.roles:
            if role.permissions.administrator:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

        try:
            new_channel = await guild.create_text_channel(
                name=channel_name,
                overwrites=overwrites,
                category=interaction.channel.category,
                topic=f"{TICKET_CREATOR_ID}:{user.id}",
                reason=f"{user.name}님의 1:1 문의 채널 생성"
            )

            embed = discord.Embed(title="✉️ 1:1 문의", description=f"안녕하세요, {user.mention}님! 문의 내용을 남겨주시면 관리자가 확인 후 답변해 드립니다.\n\n문의가 해결되면 아래 '티켓 닫기' 버튼을 눌러주세요.", color=discord.Color.green())
            await new_channel.send(embed=embed, view=OpenTicketView())

            await interaction.followup.send(f"✅ {new_channel.mention} 채널이 생성되었습니다.", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("⚠️ 채널 생성에 실패했습니다. 봇이 '채널 관리' 권한을 가지고 있는지 확인해주세요.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"⚠️ 알 수 없는 오류로 채널 생성에 실패했습니다: {e}", ephemeral=True)

# ───────────────── Cog ─────────────────

class TicketSystemCog(commands.Cog):
    """1:1 문의 채널(티켓) 생성 시스템"""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # 봇 재시작 후에도 버튼이 동작하도록 persistent view 등록
        self.bot.add_view(TicketSystemView())
        self.bot.add_view(OpenTicketView())
        self.bot.add_view(ClosedTicketView())

    @app_commands.command(name="티켓생성", description="관리자 전용: 지정된 채널에 1:1 문의 생성 패널을 게시합니다.")
    @app_commands.describe(channel="문의 패널을 게시할 텍스트 채널")
    @app_commands.default_permissions(manage_guild=True)
    async def create_ticket_panel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        embed = discord.Embed(
            title="✉️ 1:1 문의",
            description="아래 버튼을 눌러 관리자와 대화할 수 있는 비공개 채널을 생성하세요.",
            color=discord.Color.blue()
        )
        try:
            await channel.send(embed=embed, view=TicketSystemView())
            await interaction.response.send_message(f"✅ {channel.mention}에 문의 패널을 성공적으로 게시했습니다.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message(f"❌ {channel.mention}에 메시지를 보낼 권한이 없습니다.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(TicketSystemCog(bot))