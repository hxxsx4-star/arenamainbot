"""실제 티어 엠블럼 이미지 다운로드/캐시.

봇이 도는 서버(VM)에서 최초 1회 다운로드해 assets/tiers/ 에 저장하고,
이후에는 캐시 파일을 그대로 사용한다. 다운로드 실패 시 None 을 반환하며
그 경우 프로필 카드는 직접 그린 엠블럼으로 대체한다.

  롤:   communitydragon (공식 랭크 엠블럼 미러)
  발로: valorant-api.com (공식 경쟁전 티어 아이콘)
"""
import os

import aiohttp

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSET_DIR = os.path.join(BASE_DIR, "assets", "tiers")

_LOL_BASE = ("https://raw.communitydragon.org/latest/plugins/"
             "rcp-fe-lol-static-assets/global/default/images/ranked-emblem")
LOL_URLS = {
    "C":  f"{_LOL_BASE}/emblem-challenger.png",
    "GM": f"{_LOL_BASE}/emblem-grandmaster.png",
    "M":  f"{_LOL_BASE}/emblem-master.png",
    "D":  f"{_LOL_BASE}/emblem-diamond.png",
    "E":  f"{_LOL_BASE}/emblem-emerald.png",
    "P":  f"{_LOL_BASE}/emblem-platinum.png",
    "G":  f"{_LOL_BASE}/emblem-gold.png",
    "S":  f"{_LOL_BASE}/emblem-silver.png",
    "B":  f"{_LOL_BASE}/emblem-bronze.png",
    "I":  f"{_LOL_BASE}/emblem-iron.png",
    # U(언랭)는 공식 엠블럼이 없어 그린 엠블럼 사용
}

_VAL_UUID = "03621f52-342b-cf4e-4f86-9350a49c6d04"
_VAL_BASE = f"https://media.valorant-api.com/competitivetiers/{_VAL_UUID}"
VAL_URLS = {
    "R":  f"{_VAL_BASE}/27/largeicon.png",
    "IM": f"{_VAL_BASE}/25/largeicon.png",
    "A":  f"{_VAL_BASE}/22/largeicon.png",
    "D":  f"{_VAL_BASE}/19/largeicon.png",
    "P":  f"{_VAL_BASE}/16/largeicon.png",
    "G":  f"{_VAL_BASE}/13/largeicon.png",
    "S":  f"{_VAL_BASE}/10/largeicon.png",
    "B":  f"{_VAL_BASE}/7/largeicon.png",
    "I":  f"{_VAL_BASE}/4/largeicon.png",
    "U":  f"{_VAL_BASE}/0/largeicon.png",
}

_URLS = {"lol": LOL_URLS, "val": VAL_URLS}


async def get_tier_icon(game: str, letter: str):
    """티어 아이콘의 로컬 캐시 경로를 반환. 없으면 다운로드, 실패 시 None."""
    url = _URLS.get(game, {}).get(letter)
    if not url:
        return None
    os.makedirs(ASSET_DIR, exist_ok=True)
    path = os.path.join(ASSET_DIR, f"{game}_{letter}.png")
    if os.path.exists(path) and os.path.getsize(path) > 1000:
        return path
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    return None
                data = await resp.read()
        if len(data) < 1000:  # 오류 페이지 등
            return None
        tmp = path + ".tmp"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
        return path
    except Exception as e:
        print(f"[티어 아이콘] {game}/{letter} 다운로드 실패: {e}")
        return None
