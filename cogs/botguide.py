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

GUIDE_CH = 1530927403575279657          # 봇공지 채널

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

    def _build_embeds(self) -> list[discord.Embed]:
        data = self._load_commands()
        head = discord.Embed(
            title="🤖 아레나 봇 사용법",
            description=("서버에서 쓸 수 있는 모든 명령어입니다.\n"
                         "명령어가 추가되거나 바뀌면 이 안내도 **자동으로 갱신**됩니다.\n"
                         "채팅창에 `/` 를 입력하면 목록이 뜹니다."),
            color=discord.Color.blurple())

        total = 0
        embeds = [head]
        ordered = [k for k, _ in BOT_ORDER if k in data]
        ordered += [k for k in sorted(data) if k not in ordered]

        for key in ordered:
            info = data[key]
            cmds = [c for c in info.get("commands", []) if not c.get("admin")]
            admin = [c for c in info.get("commands", []) if c.get("admin")]
            if not cmds and not admin:
                continue
            icon = dict(BOT_ORDER).get(key, "•")
            e = discord.Embed(title=f"{icon} {info.get('label', key)}",
                              color=discord.Color.blurple())
            if cmds:
                lines = [f"`/{c['name']}` — {c['description']}" for c in cmds]
                e.add_field(name="명령어", value=_chunk(lines), inline=False)
            if admin:
                lines = [f"`/{c['name']}`" for c in admin]
                e.add_field(name="관리자 전용", value=" · ".join(lines)[:1024], inline=False)
            total += len(cmds) + len(admin)
            embeds.append(e)

        head.set_footer(text=f"총 {total}개 명령어 · 마지막 갱신")
        head.timestamp = discord.utils.utcnow()
        return embeds[:10]      # 한 메시지당 임베드 최대 10개

    async def _upsert_guide(self, channel: discord.abc.Messageable) -> str:
        embeds = self._build_embeds()
        msg_id = self.state.get("guide_message_id")
        if msg_id:
            try:
                msg = await channel.fetch_message(int(msg_id))
                await msg.edit(embeds=embeds)
                return "갱신"
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass    # 메시지가 지워졌으면 새로 올린다
        msg = await channel.send(embeds=embeds)
        self.state["guide_message_id"] = msg.id
        self._save_state()
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
            how = await self._upsert_guide(channel)
            print(f"📖 [봇공지] 사용법 {how}")
        except Exception as e:
            print(f"🚨 [봇공지] 처리 중 오류: {e}")

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
        how = await self._upsert_guide(channel)
        found = ", ".join(sorted(self._load_commands()))
        await interaction.followup.send(
            f"✅ 사용법 {how} · 패치 내역 {n}건 게시\n수집된 봇: {found or '없음'}", ephemeral=True)


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
