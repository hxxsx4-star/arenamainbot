from typing import Optional
import json
import os
import time
import asyncio
from filelock import FileLock
from datetime import datetime, timedelta, timezone, date

KST = timezone(timedelta(hours=9))

# 공유 데이터 디렉터리 (모든 봇이 동일하게 사용). ARENA_SHARED_DIR 환경변수로 재정의 가능.
SHARED_DIR = os.environ.get("ARENA_SHARED_DIR", "/home/hxxsx4/shared_data")
SHARED_FILE_PATH = os.path.join(SHARED_DIR, "stats.json")
LOCK_FILE_PATH = SHARED_FILE_PATH + ".lock"

os.makedirs(os.path.dirname(SHARED_FILE_PATH), exist_ok=True)
lock = FileLock(LOCK_FILE_PATH, timeout=5)

def _load_stats_nolock() -> dict:
    if not os.path.exists(SHARED_FILE_PATH): return {}
    try:
        with open(SHARED_FILE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}

def _save_stats_nolock(stats: dict):
    with open(SHARED_FILE_PATH, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=4, ensure_ascii=False)

def ensure_user(stats: dict, user_id: str) -> dict:
    if user_id not in stats:
        stats[user_id] = {"포인트": 0, "경고": 0}
    return stats[user_id]

async def load_stats() -> dict:
    def _task():
        with lock:
            return _load_stats_nolock()
    return await asyncio.to_thread(_task)

async def save_stats(stats: dict):
    def _task():
        with lock:
            _save_stats_nolock(stats)
    await asyncio.to_thread(_task)

async def get_points(user_id: int) -> int:
    def _task():
        with lock:
            stats = _load_stats_nolock()
            return int(ensure_user(stats, str(user_id)).get("포인트", 0))
    return await asyncio.to_thread(_task)

async def add_points(user_id: int, amount: int):
    def _task():
        with lock:
            stats = _load_stats_nolock()
            rec = ensure_user(stats, str(user_id))
            rec["포인트"] = int(rec.get("포인트", 0)) + amount
            _save_stats_nolock(stats)
    await asyncio.to_thread(_task)

async def spend_points(user_id: int, amount: int) -> bool:
    def _task():
        with lock:
            stats = _load_stats_nolock()
            rec = ensure_user(stats, str(user_id))
            current_points = int(rec.get("포인트", 0))
            if current_points < amount:
                return False
            rec["포인트"] = current_points - amount
            _save_stats_nolock(stats)
            return True
    return await asyncio.to_thread(_task)

# ==========================================
# ✨ 아래부터 누락되어 에러를 발생시키던 추가 함수들입니다.
# (기존 FileLock 동기화 방식과 동일하게 작성되었습니다)
# ==========================================

def format_num(num: int) -> str:
    """숫자에 3자리마다 콤마를 찍어주는 유틸 함수입니다."""
    return f"{num:,}"

async def process_attendance(user_id: int, reward: int, attend_key: str, today_str: str) -> bool:
    """출석 체크를 진행하고 포인트를 지급하는 함수입니다."""
    def _task():
        with lock:
            stats = _load_stats_nolock()
            rec = ensure_user(stats, str(user_id))

            # 이미 오늘 출석을 한 경우
            if rec.get(attend_key) == today_str:
                return False

            # 출석 처리 및 포인트 지급
            rec[attend_key] = today_str
            rec["포인트"] = int(rec.get("포인트", 0)) + reward
            _save_stats_nolock(stats)
            return True

    return await asyncio.to_thread(_task)

async def add_warning(user_id: int, count: int) -> tuple[int, int]:
    """유저에게 경고를 부여하는 함수입니다. (기존경고, 바뀐경고) 튜플을 반환합니다."""
    def _task():
        with lock:
            stats = _load_stats_nolock()
            rec = ensure_user(stats, str(user_id))

            old_warn = int(rec.get("경고", 0))
            new_warn = old_warn + count
            rec["경고"] = new_warn

            _save_stats_nolock(stats)
            return old_warn, new_warn

    return await asyncio.to_thread(_task)

async def reduce_warning(user_id: int, count: int) -> tuple[int, int]:
    """유저의 경고를 차감하는 함수입니다. (기존경고, 바뀐경고) 튜플을 반환합니다."""
    def _task():
        with lock:
            stats = _load_stats_nolock()
            rec = ensure_user(stats, str(user_id))

            old_warn = int(rec.get("경고", 0))
            new_warn = max(0, old_warn - count) # 경고가 마이너스가 되지 않도록 0 밑으로는 내리지 않음
            rec["경고"] = new_warn

            _save_stats_nolock(stats)
            return old_warn, new_warn

    return await asyncio.to_thread(_task)

# ==========================================
# 🎮 재미 요소: 레벨/경험치, 미션, 연속 출석
# (모두 stats.json 에 저장 → 자동 백업 대상)
# ==========================================

def level_from_xp(xp: int) -> int:
    """누적 XP → 레벨. (레벨 L 도달 필요 XP = L^2 * 100)"""
    if xp < 0:
        xp = 0
    return int((xp / 100) ** 0.5)


def xp_for_level(level: int) -> int:
    return (level ** 2) * 100


async def get_xp(user_id: int) -> int:
    def _task():
        with lock:
            stats = _load_stats_nolock()
            return int(ensure_user(stats, str(user_id)).get("경험치", 0))
    return await asyncio.to_thread(_task)


async def try_chat_xp(user_id: int, amount: int, cooldown_sec: int = 60):
    """쿨다운(스팸 방지)이 지났으면 XP 지급. (old_level, new_level, total_xp) 또는 None."""
    def _task():
        with lock:
            stats = _load_stats_nolock()
            rec = ensure_user(stats, str(user_id))
            now = time.time()
            if now - float(rec.get("xp_last", 0)) < cooldown_sec:
                return None
            rec["xp_last"] = now
            old_xp = int(rec.get("경험치", 0))
            new_xp = old_xp + amount
            rec["경험치"] = new_xp
            _save_stats_nolock(stats)
            return level_from_xp(old_xp), level_from_xp(new_xp), new_xp
    return await asyncio.to_thread(_task)


async def add_xp(user_id: int, amount: int):
    def _task():
        with lock:
            stats = _load_stats_nolock()
            rec = ensure_user(stats, str(user_id))
            old_xp = int(rec.get("경험치", 0))
            new_xp = max(0, old_xp + amount)
            rec["경험치"] = new_xp
            _save_stats_nolock(stats)
            return level_from_xp(old_xp), level_from_xp(new_xp), new_xp
    return await asyncio.to_thread(_task)


async def get_level_ranking():
    """(user_id, xp, level) 리스트를 XP 내림차순으로. (길드 필터는 호출부에서)"""
    def _task():
        with lock:
            stats = _load_stats_nolock()
        rows = []
        for uid, rec in stats.items():
            if str(uid).isdigit() and isinstance(rec, dict):
                xp = int(rec.get("경험치", 0))
                if xp > 0:
                    rows.append((int(uid), xp, level_from_xp(xp)))
        rows.sort(key=lambda x: x[1], reverse=True)
        return rows
    return await asyncio.to_thread(_task)


# ---------- 일일 미션 ----------
DAILY_MISSIONS = [
    {"key": "chat", "desc": "채팅으로 활동하기 (10회)", "goal": 10, "reward": 50},
    {"key": "game", "desc": "미니게임 3판 플레이", "goal": 3, "reward": 50},
    {"key": "attend", "desc": "출석 체크하기", "goal": 1, "reward": 30},
]


def _today_str() -> str:
    return datetime.now(tz=KST).date().isoformat()


def _ensure_missions(rec: dict) -> dict:
    m = rec.get("미션")
    today = _today_str()
    if not isinstance(m, dict) or m.get("date") != today:
        m = {"date": today, "progress": {}, "claimed": []}
        rec["미션"] = m
    return m


async def bump_mission(user_id: int, key: str, amount: int = 1):
    def _task():
        with lock:
            stats = _load_stats_nolock()
            rec = ensure_user(stats, str(user_id))
            m = _ensure_missions(rec)
            m["progress"][key] = int(m["progress"].get(key, 0)) + amount
            _save_stats_nolock(stats)
    await asyncio.to_thread(_task)


async def get_missions(user_id: int) -> dict:
    def _task():
        with lock:
            stats = _load_stats_nolock()
            rec = ensure_user(stats, str(user_id))
            m = _ensure_missions(rec)
            _save_stats_nolock(stats)  # 날짜 바뀌었으면 초기화 저장
            return {"date": m["date"], "progress": dict(m["progress"]), "claimed": list(m["claimed"])}
    return await asyncio.to_thread(_task)


async def claim_missions(user_id: int):
    """완료했지만 미수령한 미션 보상을 지급. [(desc, reward)] 반환."""
    def _task():
        with lock:
            stats = _load_stats_nolock()
            rec = ensure_user(stats, str(user_id))
            m = _ensure_missions(rec)
            got = []
            total = 0
            for mi in DAILY_MISSIONS:
                k = mi["key"]
                if k in m["claimed"]:
                    continue
                if int(m["progress"].get(k, 0)) >= mi["goal"]:
                    m["claimed"].append(k)
                    total += mi["reward"]
                    got.append((mi["desc"], mi["reward"]))
            if total:
                rec["포인트"] = int(rec.get("포인트", 0)) + total
            _save_stats_nolock(stats)
            return got
    return await asyncio.to_thread(_task)


# ---------- 연속 출석 ----------
async def record_streak(user_id: int) -> int:
    """출석 성공 시 호출. 연속 출석일수를 갱신해 반환."""
    def _task():
        with lock:
            stats = _load_stats_nolock()
            rec = ensure_user(stats, str(user_id))
            today = datetime.now(tz=KST).date()
            last = rec.get("출석_날짜")
            streak = int(rec.get("연속출석", 0))
            if last:
                try:
                    gap = (today - date.fromisoformat(last)).days
                    streak = streak + 1 if gap == 1 else (streak if gap == 0 else 1)
                except ValueError:
                    streak = 1
            else:
                streak = 1
            rec["출석_날짜"] = today.isoformat()
            rec["연속출석"] = streak
            _save_stats_nolock(stats)
            return streak
    return await asyncio.to_thread(_task)
