"""롤/발로란트 패치노트 자동 게시.

Riot 공식 뉴스 페이지(Next.js)의 __NEXT_DATA__ 에 기사 목록이 JSON 으로 박혀 있어,
페이지를 받아 그대로 파싱한다. (예전 Gatsby page-data.json 경로는 사이트 개편으로 사라졌고,
_next/data/<buildId>/... 는 배포마다 buildId 가 바뀌어 깨지므로 쓰지 않는다.)

새 패치노트가 올라오면 지정 채널에 임베드로 게시하고, 이미 올린 글은 공유 폴더의
상태 파일에 기록해 재시작/중복 게시를 막는다.
"""
import asyncio
import json
import os
import re
from datetime import datetime, timezone

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks

from utils.logs import is_target_guild

# ───────── 게시 채널 ─────────
LOL_PATCH_CH = 1530711957274103999      # 롤 패치노트
VAL_PATCH_CH = 1530712188111818824      # 발로란트 패치노트

CHECK_INTERVAL_MIN = 30                 # 확인 주기(분)

SHARED_DIR = os.environ.get("ARENA_SHARED_DIR", "/home/hxxsx4/shared_data")
STATE_PATH = os.path.join(SHARED_DIR, "patchnotes_seen.json")

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

_NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S)

# 패치노트만 골라내기 위한 제목 조건 (공지·트레일러 등은 제외)
PATCH_TITLE_HINTS = ("패치 노트", "패치노트", "patch notes")

SOURCES = {
    "lol": {
        "name": "리그 오브 레전드",
        "channel": LOL_PATCH_CH,
        "url": "https://www.leagueoflegends.com/ko-kr/news/game-updates/",
        "base": "https://www.leagueoflegends.com",
        "color": 0xC8AA6E,
    },
    "val": {
        "name": "발로란트",
        "channel": VAL_PATCH_CH,
        "url": "https://playvalorant.com/ko-kr/news/game-updates/",
        "base": "https://playvalorant.com",
        "color": 0xFF4655,
    },
}


def _iter_articles(node):
    """__NEXT_DATA__ 안에서 기사처럼 생긴 노드를 전부 훑는다."""
    if isinstance(node, dict):
        if "title" in node and "publishedAt" in node:
            yield node
        for v in node.values():
            yield from _iter_articles(v)
    elif isinstance(node, list):
        for v in node:
            yield from _iter_articles(v)


def _plain_description(value) -> str:
    """description 은 문자열이 아니라 {'type':'html','body':'...'} 형태로 온다.

    그대로 쓰면 임베드에 JSON 이 그대로 노출되므로 본문만 꺼내고 태그를 제거한다.
    """
    if isinstance(value, dict):
        value = value.get("body") or ""
    text = re.sub(r"<[^>]+>", "", str(value or ""))
    return re.sub(r"\s+", " ", text).strip()[:300]


def _article_url(article: dict, base: str) -> str | None:
    url = ((article.get("action") or {}).get("payload") or {}).get("url")
    if not url:
        return None
    return url if url.startswith("http") else base.rstrip("/") + url


def parse_patch_notes(html: str, base: str) -> list[dict]:
    """페이지 HTML 에서 패치노트 기사만 뽑아 최신순으로 돌려준다."""
    m = _NEXT_DATA_RE.search(html)
    if not m:
        return []
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return []

    out, seen_urls = [], set()
    for a in _iter_articles(data):
        title = str(a.get("title") or "")
        if not any(h in title.lower() for h in
                   (x.lower() for x in PATCH_TITLE_HINTS)):
            continue
        url = _article_url(a, base)
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        out.append({
            "title": title,
            "url": url,
            "published": str(a.get("publishedAt") or ""),
            "description": _plain_description(a.get("description")),
            "image": ((a.get("imageMedia") or a.get("media") or {}) or {}).get("url"),
        })
    out.sort(key=lambda x: x["published"], reverse=True)
    return out


class PatchNotesCog(commands.Cog):
    """새 패치노트가 뜨면 지정 채널에 자동 게시한다."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._seen: dict[str, list[str]] = self._load_state()
        self.check_patches.change_interval(minutes=CHECK_INTERVAL_MIN)
        self.check_patches.start()

    def cog_unload(self):
        self.check_patches.cancel()

    # ----- 게시 이력 (중복 방지) -----
    def _load_state(self) -> dict:
        try:
            with open(STATE_PATH, encoding="utf-8") as f:
                d = json.load(f)
                return {k: list(v) for k, v in d.items()}
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_state(self):
        try:
            os.makedirs(SHARED_DIR, exist_ok=True)
            tmp = STATE_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._seen, f, ensure_ascii=False, indent=2)
            os.replace(tmp, STATE_PATH)
        except OSError as e:
            print(f"🚨 [패치노트] 상태 저장 실패: {e}")

    async def _fetch(self, session: aiohttp.ClientSession, url: str) -> str | None:
        try:
            async with session.get(url, headers={"User-Agent": UA},
                                   timeout=aiohttp.ClientTimeout(total=25)) as r:
                if r.status != 200:
                    print(f"🚨 [패치노트] {url} → HTTP {r.status}")
                    return None
                return await r.text()
        except Exception as e:
            print(f"🚨 [패치노트] {url} 요청 실패: {e}")
            return None

    def _build_embed(self, src: dict, item: dict) -> discord.Embed:
        embed = discord.Embed(
            title=item["title"],
            url=item["url"],
            description=item["description"] or None,
            color=src["color"],
        )
        if item["published"]:
            try:
                embed.timestamp = datetime.fromisoformat(
                    item["published"].replace("Z", "+00:00"))
            except ValueError:
                pass
        if item.get("image"):
            embed.set_image(url=item["image"])
        embed.set_footer(text=f"{src['name']} 공식 패치노트")
        return embed

    async def _check_one(self, session, key: str, src: dict, announce: bool = True) -> int:
        html = await self._fetch(session, src["url"])
        if not html:
            return 0
        items = parse_patch_notes(html, src["base"])
        if not items:
            print(f"🚨 [패치노트] {key}: 기사를 찾지 못했습니다(사이트 구조 변경 가능성)")
            return 0

        seen = self._seen.setdefault(key, [])
        # 첫 실행이면 과거 글을 쏟아내지 않고 현재 목록만 '본 것'으로 기록한다.
        if not seen:
            self._seen[key] = [i["url"] for i in items]
            self._save_state()
            print(f"ℹ️ [패치노트] {key}: 최초 실행 — 기존 {len(items)}건은 게시하지 않고 기록만 함")
            return 0

        new = [i for i in items if i["url"] not in seen]
        if not new:
            return 0

        channel = self.bot.get_channel(src["channel"])
        if channel is None:
            print(f"🚨 [패치노트] {key}: 채널 {src['channel']} 을 찾을 수 없습니다")
            return 0

        posted = 0
        for item in reversed(new):        # 오래된 것부터 순서대로
            try:
                if announce:
                    await channel.send(embed=self._build_embed(src, item))
                seen.append(item["url"])
                posted += 1
                await asyncio.sleep(1)
            except discord.HTTPException as e:
                print(f"🚨 [패치노트] {key} 게시 실패: {e}")
        # 목록이 무한정 커지지 않도록 최근 것만 남긴다.
        self._seen[key] = seen[-100:]
        self._save_state()
        return posted

    @tasks.loop(minutes=CHECK_INTERVAL_MIN)
    async def check_patches(self):
        async with aiohttp.ClientSession() as session:
            for key, src in SOURCES.items():
                try:
                    n = await self._check_one(session, key, src)
                    if n:
                        print(f"📢 [패치노트] {key}: {n}건 게시")
                except Exception as e:
                    print(f"🚨 [패치노트] {key} 처리 중 오류: {e}")

    @check_patches.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

    # ----- 수동 확인 -----
    @app_commands.command(name="패치노트확인",
                          description="[관리자] 지금 즉시 패치노트를 확인해 새 글이 있으면 게시합니다.")
    @app_commands.default_permissions(manage_guild=True)
    async def force_check(self, interaction: discord.Interaction):
        if interaction.guild is None or not is_target_guild(interaction.guild):
            return await interaction.response.send_message(
                "이 명령어는 지정된 서버에서만 사용할 수 있습니다.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        lines = []
        async with aiohttp.ClientSession() as session:
            for key, src in SOURCES.items():
                n = await self._check_one(session, key, src)
                lines.append(f"{src['name']}: {'새 글 ' + str(n) + '건 게시' if n else '새 글 없음'}")
        await interaction.followup.send("✅ 확인 완료\n" + "\n".join(lines), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(PatchNotesCog(bot))
