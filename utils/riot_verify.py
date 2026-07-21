"""라이엇 계정 본인 인증 (프로필 아이콘 방식) — DM 닉네임 등록용.

RIOT_API_KEY 환경변수(또는 config.ini [Settings] riot_api_key)가 있으면 활성화.
없으면 인증 없이 기존처럼 바로 등록된다.

인증 방식: 롤 클라이언트에서 프로필 아이콘을 지정 아이콘으로 변경 → 봇이 확인.
발로란트도 라이엇 계정이 공용이므로 같은 방식으로 계정 소유를 인증한다.
"""
import os
import random
import configparser

import aiohttp

_config = configparser.ConfigParser()
_config.read("config.ini", encoding="utf-8")
RIOT_API_KEY = (os.environ.get("RIOT_API_KEY", "").strip()
                or _config.get("Settings", "riot_api_key", fallback="").strip())

ACCOUNT_HOST = "https://asia.api.riotgames.com"
PLATFORM_HOST = "https://kr.api.riotgames.com"
# 인증 안내에 보여줄 아이콘 이미지 (누구나 보유한 기본 아이콘 0~27)
ICON_IMG = ("https://raw.communitydragon.org/latest/plugins/"
            "rcp-be-lol-game-data/global/default/v1/profile-icons/{id}.jpg")
VERIFY_TTL = 600  # 10분


def enabled() -> bool:
    return bool(RIOT_API_KEY)


async def get_puuid(riot_id: str):
    """'이름#태그' → puuid. 실패 시 None."""
    if not RIOT_API_KEY or "#" not in riot_id:
        return None
    name, tag = riot_id.split("#", 1)
    try:
        async with aiohttp.ClientSession(
                headers={"X-Riot-Token": RIOT_API_KEY}) as s:
            async with s.get(
                    f"{ACCOUNT_HOST}/riot/account/v1/accounts/by-riot-id/"
                    f"{name.strip()}/{tag.strip()}",
                    timeout=aiohttp.ClientTimeout(total=8)) as r:
                if r.status != 200:
                    return None
                return (await r.json()).get("puuid")
    except Exception:
        return None


async def get_profile_icon(puuid: str):
    """puuid → 현재 프로필 아이콘 ID. 실패 시 None."""
    if not RIOT_API_KEY or not puuid:
        return None
    try:
        async with aiohttp.ClientSession(
                headers={"X-Riot-Token": RIOT_API_KEY}) as s:
            async with s.get(
                    f"{PLATFORM_HOST}/lol/summoner/v4/summoners/by-puuid/{puuid}",
                    timeout=aiohttp.ClientTimeout(total=8)) as r:
                if r.status != 200:
                    return None
                return (await r.json()).get("profileIconId")
    except Exception:
        return None


def pick_icon(current_icon) -> int:
    """현재 아이콘과 다른 기본 아이콘(0~27) 하나를 랜덤 지정."""
    return random.choice([i for i in range(28) if i != current_icon])
