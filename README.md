# arenamainbot

종합게임 아레나 **메인봇** (경제/상점/일반 서버 기능).

- `cogs/economy.py`  : 포인트/출석/프로필 (지급·회수 로그 → 공유 큐)
- `cogs/shop.py`     : 상점 (구매 로그 → 공유 큐)
- `cogs/gacha.py`, `cogs/minigames.py` : 가챠/미니게임
- `cogs/moderation.py` : 경고/차감 (로그 → 공유 큐)
- `cogs/ticket_system.py`, `cogs/help_kor.py`, `cogs/admin.py`
- `cogs/voice_rewards.py` : 통화방 1시간 유지 시 포인트 지급 (로그는 로그봇 담당)
- `cogs/nickname_gate.py` : 닉네임 등록 채널 — `나이 닉네임` 형식 자동 인식 + 금지어 필터 + 역할 지급, 안내 임베드 자동 갱신
- `cogs/antispam.py` : 도배(동일 메시지 5회 이상) 자동 타임아웃 1분 (제재 로그 → 공유 큐)
- 모든 로그는 공유 큐(`utils/logs.py`)에 적재 → **로그봇**이 채널에 기록
- `profile_bg.png`, `font.ttf` : 프로필 카드 이미지 생성용

## 실행
```
cp config.ini.example config.ini   # 토큰 입력
pip install -r requirements.txt
python main.py
```
