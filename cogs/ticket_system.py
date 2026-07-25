import discord
from discord.ext import commands
from discord import app_commands
import asyncio

TICKET_CREATOR_ID = "ticket_creator_id"

# 서버 커스텀 이모지
EMOJI_LOL = "<:Arena_GAME_Kind_0:1529940671836983517>"   # 리그오브레전드
EMOJI_VAL = "<:Arena_GAME_Kind_1:1529940981246332990>"   # 발로란트

# ───────────────── 티켓 카테고리 ─────────────────
# key: (버튼 라벨, 이모지, 채널 접두어, 버튼 스타일, 안내 문구)
TICKET_CATEGORIES = {
    "server": {
        "label": "서버 문의", "emoji": "📩", "prefix": "서버문의",
        "style": discord.ButtonStyle.primary,
        "desc": ("서버 이용 중 궁금한 점이나 건의사항을 남겨주세요.\n"
                 "관리자가 확인 후 순차적으로 답변해 드립니다."),
    },
    "report": {
        "label": "유저 신고 및 분쟁", "emoji": "🚨", "prefix": "신고",
        "style": discord.ButtonStyle.danger,
        "desc": ("아래 양식으로 남겨주시면 처리가 빨라집니다.\n\n"
                 "**신고 대상:** (닉네임/멘션)\n"
                 "**사유:** (무슨 일이 있었는지)\n"
                 "**증거:** (스크린샷/링크 첨부)\n\n"
                 "신고 내용은 관리자만 볼 수 있습니다."),
    },
    "match": {
        "label": "내전 문의", "emoji": "⚔️", "prefix": "내전문의",
        "style": discord.ButtonStyle.primary,
        "desc": ("내전 참여/진행 관련 문의를 남겨주세요.\n"
                 "내전 관리자가 확인 후 답변해 드립니다."),
    },
    "tier_lol": {
        "label": "롤 티어 인증", "emoji": EMOJI_LOL, "prefix": "롤티어인증",
        "style": discord.ButtonStyle.secondary,
        "manager_role": 1526678260182683668,   # 롤 티어 조정관
        "desc": ("**리그오브레전드** 티어 역할 신청입니다. 아래 정보를 남겨주세요.\n\n"
                 "**라이엇 ID:** 닉네임#태그\n"
                 "**현재 티어:** (예: 다이아몬드 IV)\n"
                 "**인증 사진:** 게임 내 프로필/랭크가 보이는 스크린샷 첨부\n\n"
                 "롤 티어 조정관이 확인 후 역할을 지급해 드립니다."),
    },
    "tier_val": {
        "label": "발로 티어 인증", "emoji": EMOJI_VAL, "prefix": "발로티어인증",
        "style": discord.ButtonStyle.secondary,
        "manager_role": 1527320282824441856,   # 발로란트 티어 조정관
        "desc": ("**발로란트** 티어 역할 신청입니다. 아래 정보를 남겨주세요.\n\n"
                 "**라이엇 ID:** 닉네임#태그\n"
                 "**현재 티어:** (예: 다이아몬드 2)\n"
                 "**인증 사진:** 경쟁전 프로필/랭크가 보이는 스크린샷 첨부\n\n"
                 "발로란트 티어 조정관이 확인 후 역할을 지급해 드립니다."),
    },
    "donate": {
        "label": "후원", "emoji": "💝", "prefix": "후원",
        "style": discord.ButtonStyle.success,
        "desc": ("서버 후원에 관심 가져주셔서 감사합니다! 🙏\n"
                 "후원 방법과 혜택을 안내해 드릴게요. 잠시만 기다려주세요."),
    },
    "etc": {
        "label": "기타 문의", "emoji": "💬", "prefix": "기타문의",
        "style": discord.ButtonStyle.success,
        "desc": ("위 항목에 해당하지 않는 문의를 자유롭게 남겨주세요.\n"
                 "관리자가 확인 후 답변해 드립니다."),
    },
}

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

async def _open_ticket(interaction: discord.Interaction, cat_key: str):
    """카테고리별 비공개 티켓 채널을 생성합니다."""
    cat = TICKET_CATEGORIES[cat_key]
    await interaction.response.defer(ephemeral=True)

    guild = interaction.guild
    user = interaction.user
    channel_name = f"{cat['prefix']}-{user.name}"

    existing_channel = discord.utils.get(guild.text_channels, name=channel_name.lower())
    if existing_channel:
        await interaction.followup.send(
            f"이미 본인의 **{cat['label']}** 채널({existing_channel.mention})이 존재합니다.", ephemeral=True)
        return

    # 기본 권한 설정
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True)
    }

    # 서포트 역할에게 채널 보기 및 메시지 보내기 권한 부여
    support_role = guild.get_role(1522224219138691184)
    if support_role:
        overwrites[support_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

    # 카테고리 담당 역할(티어 조정관 등)에게도 권한 부여
    manager_role = guild.get_role(cat["manager_role"]) if cat.get("manager_role") else None
    if manager_role:
        overwrites[manager_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

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
            reason=f"{user.name}님의 {cat['label']} 티켓 생성"
        )

        embed = discord.Embed(
            title=f"{cat['emoji']} {cat['label']}",
            description=(f"안녕하세요, {user.mention}님!\n\n"
                         f"{cat['desc']}\n\n"
                         "문의가 해결되면 아래 **티켓 닫기** 버튼을 눌러주세요."),
            color=discord.Color.green())
        # 담당 역할이 있으면 알림이 가도록 멘션
        content = manager_role.mention if manager_role else None
        await new_channel.send(content=content, embed=embed, view=OpenTicketView())

        await interaction.followup.send(f"✅ {new_channel.mention} 채널이 생성되었습니다.", ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send("⚠️ 채널 생성에 실패했습니다. 봇이 '채널 관리' 권한을 가지고 있는지 확인해주세요.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"⚠️ 알 수 없는 오류로 채널 생성에 실패했습니다: {e}", ephemeral=True)


class TicketSystemView(discord.ui.View):
    """카테고리별 티켓 생성 버튼 패널 View"""
    def __init__(self):
        super().__init__(timeout=None)

    # --- 1행 (파랑) ---
    # 서버 문의 — 기존 패널 버튼(custom_id 유지)도 이 카테고리로 동작
    @discord.ui.button(label="서버 문의", emoji="📩", style=discord.ButtonStyle.primary,
                       custom_id="create_ticket_button", row=0)
    async def server_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _open_ticket(interaction, "server")

    @discord.ui.button(label="내전 문의", emoji="⚔️", style=discord.ButtonStyle.primary,
                       custom_id="ticket_match", row=0)
    async def match_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _open_ticket(interaction, "match")

    # --- 2행 (회색) ---
    @discord.ui.button(label="롤 티어 인증", emoji=EMOJI_LOL, style=discord.ButtonStyle.secondary,
                       custom_id="ticket_tier_lol", row=1)
    async def tier_lol_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _open_ticket(interaction, "tier_lol")

    @discord.ui.button(label="발로 티어 인증", emoji=EMOJI_VAL, style=discord.ButtonStyle.secondary,
                       custom_id="ticket_tier_val", row=1)
    async def tier_val_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _open_ticket(interaction, "tier_val")

    # --- 3행 (초록) ---
    @discord.ui.button(label="후원", emoji="💝", style=discord.ButtonStyle.success,
                       custom_id="ticket_donate", row=2)
    async def donate_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _open_ticket(interaction, "donate")

    @discord.ui.button(label="기타 문의", emoji="💬", style=discord.ButtonStyle.success,
                       custom_id="ticket_etc", row=2)
    async def etc_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _open_ticket(interaction, "etc")

    # --- 4행 (빨강) ---
    @discord.ui.button(label="유저 신고 및 분쟁", emoji="🚨", style=discord.ButtonStyle.danger,
                       custom_id="ticket_report", row=3)
    async def report_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _open_ticket(interaction, "report")

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
            title="🎫 문의 티켓",
            description=("아래 버튼을 눌러 **비공개 문의 채널**을 생성하세요.\n"
                         "관리자만 볼 수 있으며, 문의 종류에 맞는 버튼을 선택해주세요.\n\n"
                         "📩 **서버 문의** — 서버 이용 관련 일반 문의/건의\n"
                         "⚔️ **내전 문의** — 내전 참여/진행 관련\n"
                         f"{EMOJI_LOL} **롤 티어 인증** — 롤 티어 역할 신청 (스크린샷 첨부)\n"
                         f"{EMOJI_VAL} **발로 티어 인증** — 발로 티어 역할 신청 (스크린샷 첨부)\n"
                         "💝 **후원** — 서버 후원 안내\n"
                         "💬 **기타 문의** — 위에 해당하지 않는 문의\n"
                         "🚨 **유저 신고 및 분쟁** — 신고 대상·사유·증거 첨부"),
            color=discord.Color.blue()
        )
        try:
            await channel.send(embed=embed, view=TicketSystemView())
            await interaction.response.send_message(f"✅ {channel.mention}에 문의 패널을 성공적으로 게시했습니다.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message(f"❌ {channel.mention}에 메시지를 보낼 권한이 없습니다.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(TicketSystemCog(bot))