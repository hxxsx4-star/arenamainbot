"""웹사이트 소환사 명단(arena_site/summoners.json) 연동.

디스코드에서 롤 닉네임을 등록하면 사이트 명단에도 자동 추가한다.
사이트(arenasite/store.py)와 동일한 파일 포맷/파일락을 사용한다.
"""
import os
import json
import time
import uuid
import asyncio

from filelock import FileLock

SHARED_DIR = os.environ.get("ARENA_SHARED_DIR", "/home/hxxsx4/shared_data")
SITE_DIR = os.path.join(SHARED_DIR, "arena_site")
_PATH = os.path.join(SITE_DIR, "summoners.json")
_LOCK = FileLock(_PATH + ".lock", timeout=5)


def _add_sync(riot_id: str, tier: str, discord_id: str, avatar: str):
    os.makedirs(SITE_DIR, exist_ok=True)
    with _LOCK:
        data = []
        if os.path.exists(_PATH):
            try:
                with open(_PATH, encoding="utf-8") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError):
                data = []
        for s in data:
            if s.get("riot_id", "").lower() == riot_id.lower():
                if tier:
                    s["tier"] = tier
                if discord_id:
                    s["discord_id"] = discord_id
                if avatar:
                    s["avatar"] = avatar
                break
        else:
            data.append({
                "id": uuid.uuid4().hex[:8],
                "riot_id": riot_id,
                "tier": tier,
                "position": "",
                "discord_id": discord_id,
                "avatar": avatar,
                "added_at": time.time(),
            })
        tmp = _PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, _PATH)


async def add_to_roster(riot_id: str, tier: str = "", discord_id: str = "", avatar: str = ""):
    """사이트 소환사 명단에 추가/갱신 (실패해도 조용히 넘어감)."""
    try:
        await asyncio.to_thread(_add_sync, riot_id.strip(), tier, str(discord_id), avatar)
    except Exception as e:
        print(f"[사이트 명단] 등록 실패 ({riot_id}): {e}")
