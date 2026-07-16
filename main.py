# main.py — 종합게임 아레나 메인봇 (경제/상점/일반 서버 기능)
import configparser

import discord
from discord.ext import commands

from utils.logs import init_log_queue

# --- 설정 로드 ---
config = configparser.ConfigParser()
config.read("config.ini", encoding="utf-8")
TOKEN = config.get("Settings", "token", fallback="").strip()
# config.ini 가 없으면 환경변수(DISCORD_TOKEN)에서 토큰을 읽습니다. (도커/CI 배포용)
if not TOKEN:
    import os
    TOKEN = os.environ.get("DISCORD_TOKEN", "").strip()


class MainBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.voice_states = True
        super().__init__(command_prefix=".", intents=intents)

    async def setup_hook(self):
        init_log_queue()
        print("✅ 로그 큐 초기화 완료")

        cogs_to_load = [
            "cogs.economy",        # 포인트/출석/프로필 (지급·회수 로그 → 공유 큐)
            "cogs.shop",           # 상점 (구매 로그 → 공유 큐)
            "cogs.gacha",          # 가챠
            "cogs.minigames",      # 미니게임 (주사위/슬롯/가위바위보/동전 베팅)
            "cogs.leveling",       # 레벨/경험치 (채팅 활동)
            "cogs.missions",       # 일일 미션
            "cogs.moderation",     # 경고/차감 (로그 → 공유 큐)
            "cogs.ticket_system",  # 티켓
            "cogs.help_kor",       # 도움말
            "cogs.voice_rewards",  # 통화방 포인트 지급 (로그는 로그봇이 담당)
        ]
        for cog in cogs_to_load:
            try:
                await self.load_extension(cog)
                print(f"✅ '{cog}' 로드 성공")
            except Exception as e:
                print(f"❌ '{cog}' 로드 중 오류 발생: {e}")

    async def on_ready(self):
        print("=====================================")
        print(f"🤖 메인봇 로그인 완료: {self.user}")
        print("=====================================")
        try:
            synced = await self.tree.sync()
            print(f"✅ {len(synced)}개의 슬래시 커맨드를 동기화했습니다!")
        except Exception as e:
            print(f"❌ 슬래시 커맨드 동기화 실패: {e}")


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("🚨 토큰이 비어 있습니다. config.ini 파일을 확인하세요.")
    bot = MainBot()
    bot.run(TOKEN)
