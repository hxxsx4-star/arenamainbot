from typing import Optional, Dict
import discord
from discord.ext import commands
from discord import app_commands

from utils.stats import get_points, spend_points, add_points, format_num, load_stats, save_stats, ensure_user
from utils.logs import SHOP_LOG_CH, enqueue_embed

# 상점 구매 로그 채널 (공유 utils/logs.py 기준)
SHOP_LOG_CHANNEL_ID = SHOP_LOG_CH

SHOP_DATA = {
    "lck": {
        "title": "🏆 LCK 역할 상점",
        "description": "원하는 LCK 팀 역할을 7,000 Point에 구매하세요!",
        "price": 7000,
        "roles": {
            "T1": 1520979707816841216, "GEN.G": 1520977760699289610, "HLE": 1520980357619646565,
            "DK": 1520981012711215194, "KT": 1520981444497768558, "NS": 1520981862590451834,
            "BFX": 1520984401486282793, "DNS": 1520982382063255592, "KRX": 1520979987417792562,
            "BRO": 1520982168447488000
        }
    },
    "lol_object": {
        "title": "🐉 롤 오브젝트 역할 상점",
        "description": "원하는 롤 오브젝트 역할을 5,000 Point에 구매하세요!",
        "price": 5000,
        "roles": {
            "내셔남작": 1520986184766193705, "장로드래곤": 1520997233804312626, "바위 게": 1520996406322659448,
            "빨간미니언": 1520996956347043943, "파란미니언": 1520986425389088788
        }
    }
}
CUSTOM_ROLE_PRICE = 25000

# ✨ 상점 로그를 전송하는 비동기 헬퍼 함수
async def send_shop_log(interaction: discord.Interaction, item_name: str, price: int):
    if not interaction.guild: return

    embed = discord.Embed(
        title="🛒 상점 구매 로그",
        color=discord.Color.green(),
        timestamp=discord.utils.utcnow()
    )
    embed.add_field(name="구매자", value=interaction.user.mention, inline=True)
    embed.add_field(name="상품명", value=item_name, inline=True)
    embed.add_field(name="결제 금액", value=f"{format_num(price)} P", inline=True)

    # 로그는 직접 올리지 않고 공유 큐에 적재 → 로그봇이 상점 구매 로그 채널에 기록 (대상 서버만)
    enqueue_embed(SHOP_LOG_CHANNEL_ID, embed.to_dict(), guild=interaction.guild)

class PurchaseButton(discord.ui.Button):
    def __init__(self, label: str, role_id: int, price: int, row: int):
        super().__init__(label=label, style=discord.ButtonStyle.secondary, row=row)
        self.role_id, self.price = role_id, price

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        member = interaction.user
        guild = interaction.guild
        if not guild: return
        role = guild.get_role(self.role_id)

        if not role:
            await interaction.followup.send("❌ 선택한 역할을 서버에서 찾을 수 없습니다.", ephemeral=True)
            return
        if role in member.roles:
            await interaction.followup.send("⚠️ 이미 보유하고 있는 역할입니다.", ephemeral=True)
            return

        current_points = await get_points(member.id)
        if current_points < self.price:
            await interaction.followup.send(f"❌ 포인트가 부족합니다. (필요: {format_num(self.price)} P)", ephemeral=True)
            return

        if not await spend_points(member.id, self.price):
            await interaction.followup.send("❌ 포인트 차감에 실패했습니다.", ephemeral=True)
            return

        try:
            await member.add_roles(role, reason="역할 상점 구매")
        except discord.Forbidden:
            await add_points(member.id, self.price)
            await interaction.followup.send("⚠️ 역할 부여에 실패했습니다 (봇의 권한이 해당 역할보다 낮습니다). 포인트가 환불되었습니다.", ephemeral=True)
            return
        except Exception:
            await add_points(member.id, self.price)
            await interaction.followup.send("⚠️ 알 수 없는 오류로 역할 부여에 실패했습니다. 포인트가 환불되었습니다.", ephemeral=True)
            return

        # 역할 부여가 완벽히 성공했을 때만 메시지와 로그 전송
        await interaction.followup.send(f"✅ {role.name} 역할을 성공적으로 구매했습니다!", ephemeral=True)
        await send_shop_log(interaction, f"{role.name} 역할", self.price)

class DynamicShopView(discord.ui.View):
    def __init__(self, cog: "ShopCog", category_key: str):
        super().__init__(timeout=180.0)
        self.cog = cog
        data = SHOP_DATA.get(category_key)
        if data:
            price, roles = data["price"], data["roles"]
            for i, (label, role_id) in enumerate(roles.items()):
                self.add_item(PurchaseButton(label, role_id, price, row=i // 5))
        self.add_item(self.BackButton(row=4))

    class BackButton(discord.ui.Button):
        def __init__(self, row: int = 4): super().__init__(label="뒤로", style=discord.ButtonStyle.grey, row=row)
        async def callback(self, interaction: discord.Interaction): await interaction.response.edit_message(embed=self.view.cog.build_role_category_embed(), view=RoleCategoryView(self.view.cog))

class CustomRoleConfirmView(discord.ui.View):
    def __init__(self, cog: "ShopCog"):
        super().__init__(timeout=180.0)
        self.cog = cog

    @discord.ui.button(label="예 (구매하기)", style=discord.ButtonStyle.success)
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        member = interaction.user

        current_points = await get_points(member.id)
        if current_points < CUSTOM_ROLE_PRICE:
            await interaction.followup.send(f"❌ 포인트가 부족합니다. (필요: {format_num(CUSTOM_ROLE_PRICE)} P)", ephemeral=True)
            return

        if await spend_points(member.id, CUSTOM_ROLE_PRICE):
            await interaction.followup.send(f"✅ 커스텀 역할 권한을 {format_num(CUSTOM_ROLE_PRICE)} P에 성공적으로 구매했습니다!\n\n1:1 문의(티켓) 채널을 열어 관리자에게 원하는 역할 이름과 색상(Hex 코드)을 요청해 주세요.", ephemeral=True)
            await send_shop_log(interaction, "커스텀 역할", CUSTOM_ROLE_PRICE)

            try:
                admin = interaction.client.get_user(697412465839046747) or await interaction.client.fetch_user(697412465839046747)
                nickname = member.display_name
                await admin.send(f"🔔 커스텀 역할 구매 알림\n서버 닉네임: {nickname}\n유저 멘션: {member.mention}\n\n위 유저가 방금 커스텀 역할을 구매했습니다!")
            except Exception:
                pass

            await interaction.edit_original_response(embed=self.cog.build_role_category_embed(), view=RoleCategoryView(self.cog))
        else:
            await interaction.followup.send("❌ 포인트 차감에 실패했습니다.", ephemeral=True)

    @discord.ui.button(label="아니오 (취소)", style=discord.ButtonStyle.danger)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(embed=self.cog.build_role_category_embed(), view=RoleCategoryView(self.cog))

class RoleCategoryView(discord.ui.View):
    def __init__(self, cog: "ShopCog"):
        super().__init__(timeout=180.0)
        self.cog = cog

    @discord.ui.button(label="LCK 역할", style=discord.ButtonStyle.primary)
    async def lck_role_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = SHOP_DATA["lck"]
        embed = discord.Embed(title=data["title"], description=data["description"], color=discord.Color.blue())
        await interaction.response.edit_message(embed=embed, view=DynamicShopView(self.cog, "lck"))

    @discord.ui.button(label="롤 오브젝트 역할", style=discord.ButtonStyle.success)
    async def lol_object_role_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = SHOP_DATA["lol_object"]
        embed = discord.Embed(title=data["title"], description=data["description"], color=discord.Color.green())
        await interaction.response.edit_message(embed=embed, view=DynamicShopView(self.cog, "lol_object"))

    @discord.ui.button(label="커스텀 역할", style=discord.ButtonStyle.secondary)
    async def custom_role_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(title="✨ 커스텀 역할 상점", description=f"자신만의 커스텀 역할을 {format_num(CUSTOM_ROLE_PRICE)} Point에 구매하시겠습니까?\n구매 후 1:1 문의를 통해 역할을 지급받을 수 있습니다.", color=discord.Color.purple())
        await interaction.response.edit_message(embed=embed, view=CustomRoleConfirmView(self.cog))

    @discord.ui.button(label="뒤로", style=discord.ButtonStyle.grey, row=1)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(embed=self.cog.build_main_embed(), view=MainShopView(self.cog))

class OtherShopView(discord.ui.View):
    def __init__(self, cog: "ShopCog"):
        super().__init__(timeout=180.0)
        self.cog = cog

    @discord.ui.button(label="경고 차감권 구매", style=discord.ButtonStyle.success)
    async def warning_ticket_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        user_id_str = str(interaction.user.id)

        stats = await load_stats()
        rec = ensure_user(stats, user_id_str)
        buy_count = int(rec.get("warning_ticket_count", 0))

        price = 3000 + (2000 * buy_count)

        user_points = await get_points(interaction.user.id)
        if user_points < price:
            await interaction.followup.send(f"❌ 포인트가 부족합니다. (현재 구매 가격: {format_num(price)} P)", ephemeral=True)
            return

        if await spend_points(interaction.user.id, price):
            stats = await load_stats()
            rec = ensure_user(stats, user_id_str)
            rec["warning_ticket_count"] = buy_count + 1
            await save_stats(stats)

            next_price = 3000 + (2000 * (buy_count + 1))
            await interaction.followup.send(f"✅ 경고 차감권을 구매했습니다! ({format_num(price)} P 차감)\n➡️ 다음에 구매하실 때는 {format_num(next_price)} P가 필요합니다.", ephemeral=True)

            await send_shop_log(interaction, "경고 차감권", price)
        else:
            await interaction.followup.send("❌ 포인트 차감에 실패했습니다.", ephemeral=True)

    @discord.ui.button(label="롤 1:1 강의권 구매", style=discord.ButtonStyle.primary)
    async def coaching_ticket_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        price = 5000

        user_points = await get_points(interaction.user.id)
        if user_points < price:
            await interaction.followup.send(f"❌ 포인트가 부족합니다. (필요: {format_num(price)} P)", ephemeral=True)
            return

        if await spend_points(interaction.user.id, price):
            # 성공 시 로그 전송
            await send_shop_log(interaction, "롤 1:1 강의권", price)

            try:
                await add_points(340905894063636481, 2500)

                manager = interaction.client.get_user(340905894063636481) or await interaction.client.fetch_user(340905894063636481)
                await manager.send(f"🔔 강의권 구매 알림 🔔\n{interaction.user.mention} (`{interaction.user.name}`) 님이 상점에서 롤 1:1 강의권을 구매했습니다!\n💰 수익금 2,500 Point가 지급되었습니다.")

                # ✨ 구매한 당사자에게만 보이는(ephemeral) 성공 메시지 전송
                await interaction.followup.send(f"✅ 롤 1:1 강의권을 성공적으로 구매했습니다! 티어매니저에게 실시간으로 알림이 전송되었습니다.", ephemeral=True)
            except Exception:
                await interaction.followup.send(f"✅ 결제는 완료되었으나, 티어매니저님의 DM 설정이 닫혀있어 봇이 알림을 보내지 못했습니다. 매니저님께 직접 문의해주세요.", ephemeral=True)
        else:
            await interaction.followup.send("❌ 포인트 차감에 실패했습니다.", ephemeral=True)

    @discord.ui.button(label="뒤로", style=discord.ButtonStyle.grey, row=1)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(embed=self.cog.build_main_embed(), view=MainShopView(self.cog))

class MainShopView(discord.ui.View):
    def __init__(self, cog: "ShopCog"):
        super().__init__(timeout=180.0)
        self.cog = cog

    @discord.ui.button(label="역할상점", style=discord.ButtonStyle.green)
    async def role_shop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(embed=self.cog.build_role_category_embed(), view=RoleCategoryView(self.cog))

    @discord.ui.button(label="기타상점", style=discord.ButtonStyle.primary, disabled=False)
    async def other_shop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(embed=self.cog.build_other_shop_embed(), view=OtherShopView(self.cog))

class ShopCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def build_main_embed(self) -> discord.Embed:
        return discord.Embed(title="🏪 상점", description="이용하실 상점을 선택해주세요.", color=discord.Color.blue())

    def build_role_category_embed(self) -> discord.Embed:
        return discord.Embed(title="🛎️ 역할상점", description="원하는 역할 카테고리를 선택하세요.", color=discord.Color.gold())

    def build_other_shop_embed(self) -> discord.Embed:
        embed = discord.Embed(title="🛍️ 기타상점", description="원하시는 상품을 구매해주세요.", color=discord.Color.green())
        embed.add_field(name="1. 경고 차감권", value="기본 3,000 P\n(본인이 한 번씩 살 때마다 가격이 2,000 P씩 증가합니다.)", inline=False)
        embed.add_field(name="2. 티어매니저의 롤 1:1 강의권", value="강의당 5,000 P\n구매 시 담당자에게 자동으로 알림이 전송됩니다.", inline=False)
        return embed

    @app_commands.command(name="상점", description="포인트 상점을 엽니다.")
    async def shop(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=self.build_main_embed(), view=MainShopView(self))

    @app_commands.command(name="상점-리로드", description="관리자 전용: 상점 캐시를 리로드합니다.")
    @app_commands.default_permissions(manage_guild=True)
    async def reload_shop_config(self, interaction: discord.Interaction):
        await interaction.response.send_message("✅ 상점 시스템이 최신 하드코딩 데이터로 유지되고 있습니다.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(ShopCog(bot))