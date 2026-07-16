import time
import random

import discord
from discord.ext import commands
from discord import app_commands

from utils.stats import spend_points, add_points, get_points, bump_mission, format_num

MIN_BET = 10
MAX_BET = 100_000
COOLDOWN = 3  # 초 (연타 방지)

SLOT_EMOJIS = ["🍒", "🍋", "🔔", "⭐", "💎", "7️⃣"]


class MinigamesCog(commands.Cog):
    """포인트 베팅 미니게임 (주사위/슬롯/가위바위보/동전)."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._cd: dict[int, float] = {}

    async def _take_bet(self, interaction: discord.Interaction, bet: int) -> bool:
        """베팅 유효성 검사 + 포인트 차감 + 쿨다운 + 미션 카운트. 성공 시 True(응답 안 함)."""
        if bet < MIN_BET:
            await interaction.response.send_message(f"최소 베팅은 {MIN_BET}P 입니다.", ephemeral=True)
            return False
        if bet > MAX_BET:
            await interaction.response.send_message(f"최대 베팅은 {format_num(MAX_BET)}P 입니다.", ephemeral=True)
            return False
        now = time.time()
        last = self._cd.get(interaction.user.id, 0)
        if now - last < COOLDOWN:
            await interaction.response.send_message(
                f"잠시 후 다시 시도하세요. ({COOLDOWN - int(now - last)}초)", ephemeral=True)
            return False
        if not await spend_points(interaction.user.id, bet):
            cur = await get_points(interaction.user.id)
            await interaction.response.send_message(
                f"포인트가 부족합니다. (보유: {format_num(cur)}P)", ephemeral=True)
            return False
        self._cd[interaction.user.id] = now
        await bump_mission(interaction.user.id, "game")
        return True

    async def _result(self, interaction: discord.Interaction, title: str, body: str, payout: int, bet: int):
        if payout > 0:
            await add_points(interaction.user.id, payout)
        net = payout - bet
        cur = await get_points(interaction.user.id)
        if net > 0:
            color, tail = discord.Color.green(), f"🎉 **+{format_num(net)}P** 획득!"
        elif net == 0:
            color, tail = discord.Color.greyple(), "➖ 본전 (무승부)"
        else:
            color, tail = discord.Color.red(), f"💸 **{format_num(net)}P**"
        embed = discord.Embed(title=title, description=f"{body}\n\n{tail}", color=color)
        embed.set_footer(text=f"현재 보유: {format_num(cur)}P")
        await interaction.response.send_message(embed=embed)

    # ---------- 주사위 ----------
    @app_commands.command(name="주사위", description="봇과 주사위 대결! 높은 쪽이 승리 (승리 시 2배)")
    @app_commands.describe(베팅="베팅할 포인트")
    async def dice(self, interaction: discord.Interaction, 베팅: int):
        if not await self._take_bet(interaction, 베팅):
            return
        me, bot = random.randint(1, 6), random.randint(1, 6)
        body = f"🎲 나: **{me}**  vs  봇: **{bot}**"
        if me > bot:
            payout = 베팅 * 2
        elif me == bot:
            payout = 베팅  # 환불
        else:
            payout = 0
        await self._result(interaction, "🎲 주사위 대결", body, payout, 베팅)

    # ---------- 동전 ----------
    @app_commands.command(name="동전", description="동전 던지기! 맞히면 2배")
    @app_commands.describe(베팅="베팅할 포인트", 선택="앞 또는 뒤")
    @app_commands.choices(선택=[
        app_commands.Choice(name="앞", value="앞"),
        app_commands.Choice(name="뒤", value="뒤"),
    ])
    async def coin(self, interaction: discord.Interaction, 베팅: int, 선택: app_commands.Choice[str]):
        if not await self._take_bet(interaction, 베팅):
            return
        result = random.choice(["앞", "뒤"])
        body = f"🪙 동전: **{result}** / 내 선택: **{선택.value}**"
        payout = 베팅 * 2 if result == 선택.value else 0
        await self._result(interaction, "🪙 동전 던지기", body, payout, 베팅)

    # ---------- 가위바위보 ----------
    @app_commands.command(name="가위바위보", description="봇과 가위바위보! 이기면 2배")
    @app_commands.describe(베팅="베팅할 포인트", 선택="가위/바위/보")
    @app_commands.choices(선택=[
        app_commands.Choice(name="가위 ✌️", value="가위"),
        app_commands.Choice(name="바위 ✊", value="바위"),
        app_commands.Choice(name="보 ✋", value="보"),
    ])
    async def rps(self, interaction: discord.Interaction, 베팅: int, 선택: app_commands.Choice[str]):
        if not await self._take_bet(interaction, 베팅):
            return
        emoji = {"가위": "✌️", "바위": "✊", "보": "✋"}
        bot = random.choice(["가위", "바위", "보"])
        me = 선택.value
        body = f"나: {emoji[me]} {me}  vs  봇: {emoji[bot]} {bot}"
        wins = {("가위", "보"), ("바위", "가위"), ("보", "바위")}
        if me == bot:
            payout = 베팅
        elif (me, bot) in wins:
            payout = 베팅 * 2
        else:
            payout = 0
        await self._result(interaction, "✊ 가위바위보", body, payout, 베팅)

    # ---------- 슬롯 ----------
    @app_commands.command(name="슬롯", description="슬롯머신! 3개 일치 10배, 2개 일치 2배")
    @app_commands.describe(베팅="베팅할 포인트")
    async def slot(self, interaction: discord.Interaction, 베팅: int):
        if not await self._take_bet(interaction, 베팅):
            return
        reels = [random.choice(SLOT_EMOJIS) for _ in range(3)]
        body = f"[ {' | '.join(reels)} ]"
        uniq = len(set(reels))
        if uniq == 1:
            payout = 베팅 * 10
            body += "\n✨ 잭팟! 3개 일치!"
        elif uniq == 2:
            payout = 베팅 * 2
            body += "\n2개 일치!"
        else:
            payout = 0
        await self._result(interaction, "🎰 슬롯머신", body, payout, 베팅)


async def setup(bot: commands.Bot):
    await bot.add_cog(MinigamesCog(bot))
