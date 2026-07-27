"""봇공지 채널 관리 — 사용법 임베드 자동 갱신 + 봇 패치 내역 공개.

1) 사용법: 각 봇이 시작할 때 자기 슬래시 명령어를 공유 폴더에 내보낸다
   (utils/cmdexport.py). 여기서 그 파일들을 모아 하나의 임베드로 만들고,
   이미 올려둔 메시지를 '수정'한다. 명령어가 추가/삭제되면 안내도 따라 바뀐다.

2) 패치 내역: CHANGELOG.md 에 새 항목이 생기면 봇공지 채널에 게시한다.
   컨테이너에는 .git 이 없어서(도커 이미지에서 제외) git log 를 못 읽기 때문에,
   저장소에 두는 CHANGELOG.md 를 기준으로 삼는다.
"""
import json
import os
import re

import discord
from discord import app_commands
from discord.ext import commands, tasks

from utils.cmdexport import CMD_DIR
from utils.logs import is_target_guild

GUIDE_CH = 1530927403575279657          # 봇공지 채널 (일반 유저용 사용법 + 패치 내역)
ADMIN_THREAD = 1530947637627322449      # 관리자용 사용법 스레드

# 함수 본문에서 권한을 검사하는 명령어들. 데코레이터가 없어 자동 수집으로는
# 관리자 전용인지 알 수 없으므로 여기에 직접 적어둔다.
ROLE_GATED = {
    "내전 진행": "누구나 (실행한 사람이 방장이 됩니다)",
    "닉네임등록": "🔪 롤 티어조정관 / 🔪 발로 티어조정관 (또는 관리자 권한)",
    "음성세팅": "관리자 권한",
    "음성세팅목록": "관리자 권한",
    "음성세팅제거": "관리자 권한",
}

# 위 중에서 '일반 유저 안내'에는 빼야 하는 것들 (실제로 관리자만 쓸 수 있음)
ADMIN_ONLY_EXTRA = {"닉네임등록", "음성세팅", "음성세팅목록", "음성세팅제거"}

# 명령어가 아닌, 버튼/역할로 동작하는 관리 기능 안내
EXTRA_ADMIN_NOTES = [
    ("⚔️ 내전 결과 확정",
     "내전 결과 화면의 **1팀/2팀 승리** 버튼은 **💎 내전매니저** 역할 또는 "
     "**서버 관리 권한**이 있어야 누를 수 있습니다.\n"
     "방장이라도 결과는 확정할 수 없습니다 — 승리 +140P·패배 +60P·MVP +2,000P 가 "
     "지급되기 때문에 아무나 판을 만들어 포인트를 찍어내지 못하도록 막아둔 것입니다."),
    ("🎛️ 음성방 관리",
     "임시 음성방의 관리 패널(이름/인원/잠금/공개/내보내기/방장위임/삭제)은 "
     "**그 방의 방장**이나 **관리자 권한** 보유자만 조작할 수 있습니다.\n"
     "방장이 나가면 남아 있는 사람에게 자동으로 승계됩니다."),
    ("🏆 e스포츠 예측",
     "LCK·MSI·월드 챔피언십 경기는 시작 24시간 전에 자동으로 올라가고, "
     "경기 시작 시각에 자동 마감된 뒤 공식 결과로 자동 정산됩니다.\n"
     "손댈 일은 없지만 `/e스포츠확인` 으로 즉시 점검할 수 있습니다."),
    ("📢 패치노트 · 봇공지",
     "롤·발로란트 패치노트는 30분마다 확인해 각 채널에 자동 게시됩니다.\n"
     "봇공지의 사용법 안내는 각 봇이 내보낸 명령어 목록으로 1시간마다 자동 갱신됩니다."),
]

SHARED_DIR = os.environ.get("ARENA_SHARED_DIR", "/home/hxxsx4/shared_data")
STATE_PATH = os.path.join(SHARED_DIR, "botguide_state.json")
CHANGELOG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "CHANGELOG.md")

REFRESH_MIN = 60        # 사용법 임베드 갱신 주기(분)

# 봇별 표시 순서와 아이콘
BOT_ORDER = [
    ("mainbot", "🪙"),
    ("matchbot", "⚔️"),
    ("petbot", "🎮"),
    ("voicebot", "🔊"),
    ("logbot", "📋"),
]


def _parse_changelog(text: str) -> list[dict]:
    """`## 버전 — 제목` 단위로 잘라 최신순 리스트로."""
    out = []
    for m in re.finditer(r'^##\s+(\S+)\s*(?:[—-]\s*(.*))?$', text, re.M):
        version, title = m.group(1), (m.group(2) or "").strip()
        start = m.end()
        nxt = re.search(r'^##\s+', text[start:], re.M)
        body = text[start:start + nxt.start()] if nxt else text[start:]
        out.append({"version": version, "title": title, "body": body.strip()})
    return out


class BotGuideCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.state = self._load_state()
        self.refresh_guide.change_interval(minutes=REFRESH_MIN)
        self.refresh_guide.start()

    def cog_unload(self):
        self.refresh_guide.cancel()

    # ----- 상태 -----
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
            print(f"🚨 [봇공지] 상태 저장 실패: {e}")

    # ----- 사용법 임베드 -----
    def _load_commands(self) -> dict:
        data = {}
        try:
            files = os.listdir(CMD_DIR)
        except OSError:
            return data
        for fn in files:
            if not fn.endswith(".json"):
                continue
            try:
                with open(os.path.join(CMD_DIR, fn), encoding="utf-8") as f:
                    data[fn[:-5]] = json.load(f)
            except (OSError, json.JSONDecodeError):
                continue
        return data

    def _ordered_keys(self, data: dict) -> list[str]:
        keys = [k for k, _ in BOT_ORDER if k in data]
        return keys + [k for k in sorted(data) if k not in keys]

    def _build_embeds(self) -> list[discord.Embed]:
        """일반 유저용 — 관리자 전용 명령어는 뺀다."""
        data = self._load_commands()
        head = discord.Embed(
            title="🤖 아레나 봇 사용법",
            description=("서버에서 자유롭게 쓸 수 있는 명령어입니다.\n"
                         "채팅창에 `/` 를 입력하면 목록이 뜹니다.\n"
                         "명령어가 추가되거나 바뀌면 이 안내도 **자동으로 갱신**됩니다."),
            color=discord.Color.blurple())

        total = 0
        embeds = [head]
        for key in self._ordered_keys(data):
            info = data[key]
            cmds = [c for c in info.get("commands", [])
                    if not c.get("admin") and c["name"] not in ADMIN_ONLY_EXTRA]
            if not cmds:
                continue
            icon = dict(BOT_ORDER).get(key, "•")
            e = discord.Embed(title=f"{icon} {info.get('label', key)}",
                              color=discord.Color.blurple())
            e.add_field(name="명령어",
                        value=_chunk([f"`/{c['name']}` — {c['description']}" for c in cmds]),
                        inline=False)
            total += len(cmds)
            embeds.append(e)

        head.set_footer(text=f"총 {total}개 명령어 · 마지막 갱신")
        head.timestamp = discord.utils.utcnow()
        return embeds[:10]      # 한 메시지당 임베드 최대 10개

    def _build_admin_embeds(self) -> list[discord.Embed]:
        """관리자용 — 필요한 권한/역할까지 함께 표기한다."""
        data = self._load_commands()
        head = discord.Embed(
            title="🛠️ 관리자용 봇 사용법",
            description=(
                "관리자·스태프 전용 기능 정리입니다. 명령어마다 **필요한 권한**을 함께 적었습니다.\n\n"
                "**권한 등급**\n"
                "• `관리자 권한` — 서버 관리자(Administrator)\n"
                "• `서버 관리 권한` — 서버 관리하기(Manage Server)\n"
                "• `💎 내전매니저` — 내전 운영 역할\n"
                "• `🔪 롤/발로 티어조정관` — 티어 인증·닉네임 등록 담당\n\n"
                "권한이 없으면 명령어가 아예 목록에 보이지 않거나, 실행 시 거부됩니다."),
            color=discord.Color.orange())

        embeds = [head]
        total = 0
        for key in self._ordered_keys(data):
            info = data[key]
            admin = [c for c in info.get("commands", []) if c.get("admin")]
            # 역할로 막힌 명령어는 admin 플래그가 없어도 여기에 같이 싣는다
            extra = [c for c in info.get("commands", [])
                     if not c.get("admin") and c["name"] in ADMIN_ONLY_EXTRA]
            rows = admin + extra
            if not rows:
                continue
            icon = dict(BOT_ORDER).get(key, "•")
            e = discord.Embed(title=f"{icon} {info.get('label', key)}",
                              color=discord.Color.orange())
            lines = []
            for c in sorted(rows, key=lambda x: x["name"]):
                need = ROLE_GATED.get(c["name"]) or c.get("requires") or "관리자 권한"
                lines.append(f"`/{c['name']}` — {c['description']}\n　└ 필요: **{need}**")
            e.add_field(name="명령어", value=_chunk(lines), inline=False)
            total += len(rows)
            embeds.append(e)

        for title, body in EXTRA_ADMIN_NOTES:
            embeds.append(discord.Embed(title=title, description=body,
                                        color=discord.Color.dark_orange()))

        head.set_footer(text=f"관리 기능 {total}개 · 마지막 갱신")
        head.timestamp = discord.utils.utcnow()
        return embeds[:10]

    async def _upsert(self, channel: discord.abc.Messageable, embeds: list[discord.Embed],
                      state_key: str, pin: bool = True) -> str:
        """같은 메시지를 계속 수정한다. 지워졌으면 새로 올린다."""
        msg_id = self.state.get(state_key)
        if msg_id:
            try:
                msg = await channel.fetch_message(int(msg_id))
                await msg.edit(embeds=embeds)
                return "갱신"
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass    # 메시지가 지워졌으면 새로 올린다
        msg = await channel.send(embeds=embeds)
        self.state[state_key] = msg.id
        self._save_state()
        if pin:
            try:
                await msg.pin()
            except discord.HTTPException:
                pass
        return "신규 게시"

    # ----- 패치 내역 -----
    async def _post_changelog(self, channel: discord.abc.Messageable) -> int:
        try:
            with open(CHANGELOG_PATH, encoding="utf-8") as f:
                entries = _parse_changelog(f.read())
        except OSError as e:
            print(f"🚨 [봇공지] CHANGELOG 읽기 실패: {e}")
            return 0
        if not entries:
            return 0

        posted = self.state.setdefault("posted_versions", [])
        # 최초 실행이면 과거 내역을 쏟아내지 않고 최신 1건만 올린다.
        if not posted:
            new = entries[:1]
            posted.extend(e["version"] for e in entries)
        else:
            new = [e for e in entries if e["version"] not in posted]

        count = 0
        for entry in reversed(new):     # 오래된 것부터
            embed = discord.Embed(
                title=f"🔔 봇 업데이트 — {entry['title'] or entry['version']}",
                description=entry["body"][:4000] or "변경 내역 없음",
                color=discord.Color.green())
            embed.set_footer(text=f"버전 {entry['version']}")
            embed.timestamp = discord.utils.utcnow()
            try:
                await channel.send(embed=embed)
                if entry["version"] not in posted:
                    posted.append(entry["version"])
                count += 1
            except discord.HTTPException as e:
                print(f"🚨 [봇공지] 패치 내역 게시 실패: {e}")
        self.state["posted_versions"] = posted[-50:]
        self._save_state()
        return count

    # ----- 루프 -----
    @tasks.loop(minutes=REFRESH_MIN)
    async def refresh_guide(self):
        channel = self.bot.get_channel(GUIDE_CH)
        if channel is None:
            print(f"🚨 [봇공지] 채널 {GUIDE_CH} 을 찾을 수 없습니다")
            return
        try:
            n = await self._post_changelog(channel)
            if n:
                print(f"🔔 [봇공지] 패치 내역 {n}건 게시")
            how = await self._upsert(channel, self._build_embeds(), "guide_message_id")
            print(f"📖 [봇공지] 일반 사용법 {how}")
        except Exception as e:
            print(f"🚨 [봇공지] 일반 사용법 처리 오류: {e}")

        # 관리자용은 별도 스레드에
        try:
            thread = self.bot.get_channel(ADMIN_THREAD) \
                or await self.bot.fetch_channel(ADMIN_THREAD)
            how = await self._upsert(thread, self._build_admin_embeds(),
                                     "admin_message_id", pin=False)
            print(f"🛠️ [봇공지] 관리자 사용법 {how}")
        except Exception as e:
            print(f"🚨 [봇공지] 관리자 사용법 처리 오류: {e}")

    @refresh_guide.before_loop
    async def before_refresh(self):
        await self.bot.wait_until_ready()
        # 다른 봇들이 명령어를 내보낼 시간을 조금 준다.
        import asyncio
        await asyncio.sleep(20)

    # ----- 수동 -----
    @app_commands.command(name="봇공지갱신",
                          description="[관리자] 봇공지 채널의 사용법/패치 내역을 지금 갱신합니다.")
    @app_commands.default_permissions(manage_guild=True)
    async def force_refresh(self, interaction: discord.Interaction):
        if interaction.guild is None or not is_target_guild(interaction.guild):
            return await interaction.response.send_message(
                "이 명령어는 지정된 서버에서만 사용할 수 있습니다.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        channel = self.bot.get_channel(GUIDE_CH)
        if channel is None:
            return await interaction.followup.send("❌ 봇공지 채널을 찾을 수 없습니다.", ephemeral=True)
        n = await self._post_changelog(channel)
        how = await self._upsert(channel, self._build_embeds(), "guide_message_id")
        try:
            thread = self.bot.get_channel(ADMIN_THREAD) \
                or await self.bot.fetch_channel(ADMIN_THREAD)
            how_admin = await self._upsert(thread, self._build_admin_embeds(),
                                           "admin_message_id", pin=False)
        except Exception as e:
            how_admin = f"실패({e})"
        found = ", ".join(sorted(self._load_commands()))
        await interaction.followup.send(
            f"✅ 일반 사용법 {how} · 관리자 사용법 {how_admin} · 패치 내역 {n}건\n"
            f"수집된 봇: {found or '없음'}", ephemeral=True)


def _chunk(lines: list[str], limit: int = 1024) -> str:
    """임베드 필드 1024자 제한에 맞춰 자른다."""
    out, size = [], 0
    for ln in lines:
        if size + len(ln) + 1 > limit - 20:
            out.append("…")
            break
        out.append(ln)
        size += len(ln) + 1
    return "\n".join(out)


async def setup(bot: commands.Bot):
    await bot.add_cog(BotGuideCog(bot))
