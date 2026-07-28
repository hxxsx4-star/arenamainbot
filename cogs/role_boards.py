"""역할지급 채널 — 이모지 반응으로 역할을 선택/해제하는 "보드"들을 관리한다.

반응을 추가하면 역할 지급, 반응을 취소하면 역할 회수. 배타 처리(다른 반응을
자동으로 지워주는 것)는 하지 않는다 — 안내 문구에 "기존 이모지를 다시 눌러
취소한 뒤 새로 선택하라"고 적어뒀기 때문에, 취소는 유저가 직접 한다.

새 보드를 추가하려면 BOARDS 리스트에 항목만 추가하면 된다.
"""
import json
import os
import re

import discord
from discord.ext import commands

from utils.logs import is_target_guild, send_log_embed, ROLE_LOG_CH

ROLE_CH_ID = 1526595102263480484

_EMOJI_ID_RE = re.compile(r"<a?:[^:]+:(\d+)>")


def _emoji_id(tag: str) -> int:
    return int(_EMOJI_ID_RE.match(tag).group(1))


BOARDS = [
    {
        "key": "lol_tier",
        "title": "🎮 롤 티어 역할",
        "description": "15-3 시즌 이후 최고 티어를 골라주세요. 티어 변경 시 눌렀던 이모지를 "
                       "다시 눌러 취소한 후 다른 티어를 선택하시면 됩니다!",
        "roles": [
            (1527394221827297401, "챌린저", "<:Arena_LOL_Tier_90:1529181678856175737>"),
            (1527394318677966958, "그랜드마스터", "<:Arena_LOL_Tier_9:1529181657553174749>"),
            (1527394271475269652, "마스터", "<:Arena_LOL_Tier_8:1529181633444319385>"),
            (1527391586684637184, "다이아몬드", "<:Arena_LOL_Tier_7:1529181595418890371>"),
            (1527394844992081971, "에메랄드", "<:Arena_LOL_Tier_6:1529181571016429628>"),
            (1527394879553142975, "플레티넘", "<:Arena_LOL_Tier_5:1529181498526400674>"),
            (1527394917079584879, "골드", "<:Arena_LOL_Tier_4:1529181529824297081>"),
            (1527394952588296383, "실버", "<:Arena_LOL_Tier_3:1529181456923099256>"),
            (1527395006430843070, "브론즈", "<:Arena_LOL_Tier_2:1529181418700275860>"),
            (1527395039423107122, "아이언", "<:Arena_LOL_Tier_1:1529181373083029755>"),
            (1527395147732746372, "언랭", "<:Arena_LOL_Tier_0:1529181316719841330>"),
        ],
    },
    {
        "key": "val_tier",
        "title": "🔫 발로란트 티어 역할",
        "description": "2025년부터 현재까지 가장 높은 티어를 선택해주세요. 티어 변경 시 눌렀던 이모지를 "
                       "다시 눌러 취소한 후 다른 티어를 선택하시면 됩니다!",
        "roles": [
            (1527395330876899378, "레디언트", "<:Arena_VAL_Tier_9:1529587139543830608>"),
            (1527395506832019636, "불멸", "<:Arena_VAL_Tier_8:1529587093645426810>"),
            (1527395558019432589, "초월자", "<:Arena_VAL_Tier_7:1529587039505354976>"),
            (1527395603963969779, "다이아몬드", "<:Arena_VAL_Tier_6:1529586988951539824>"),
            (1527395666060378174, "플레티넘", "<:Arena_VAL_Tier_5:1529586943120113694>"),
            (1527395694023807026, "골드", "<:Arena_VAL_Tier_4:1529586894608793882>"),
            (1527395724202086500, "실버", "<:Arena_VAL_Tier_3:1529586849872478510>"),
            (1527395741641867364, "브론즈", "<:Arena_VAL_Tier_2:1529586800459518036>"),
            (1527395761887903794, "아이언", "<:Arena_VAL_Tier_1:1529586338989346877>"),
            (1527397286982848622, "언랭", "<:Arena_VAL_Tier_0:1529588677829988464>"),
        ],
    },
]

SHARED_DIR = os.environ.get("ARENA_SHARED_DIR", "/home/hxxsx4/shared_data")
STATE_PATH = os.path.join(SHARED_DIR, "role_boards_state.json")


def _board_embed(board: dict) -> discord.Embed:
    e = discord.Embed(title=board["title"], description=board["description"],
                      color=discord.Color.blurple())
    lines = [f"{tag}  {name}" for _, name, tag in board["roles"]]
    e.add_field(name="티어 목록", value="\n".join(lines), inline=False)
    return e


class RoleBoardsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.state = self._load_state()

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
            print(f"🚨 [역할보드] 상태 저장 실패: {e}")

    @commands.Cog.listener()
    async def on_ready(self):
        for guild in self.bot.guilds:
            if not is_target_guild(guild):
                continue
            channel = guild.get_channel(ROLE_CH_ID)
            if not channel:
                print(f"🚨 [역할보드] 채널 {ROLE_CH_ID} 를 찾을 수 없습니다.")
                continue
            for board in BOARDS:
                await self._ensure_board(channel, board)

    async def _ensure_board(self, channel: discord.TextChannel, board: dict):
        key = board["key"]
        msg_id = self.state.get(key)
        message = None
        if msg_id:
            try:
                message = await channel.fetch_message(msg_id)
            except (discord.NotFound, discord.Forbidden):
                message = None

        if message is None:
            try:
                message = await channel.send(embed=_board_embed(board))
            except discord.Forbidden:
                return
            self.state[key] = message.id
            self._save_state()
        else:
            # 코드에서 문구/목록이 바뀌었을 수 있으니 재시작마다 최신으로 맞춘다.
            try:
                await message.edit(embed=_board_embed(board))
            except discord.Forbidden:
                pass

        for role_id, name, tag in board["roles"]:
            try:
                await message.add_reaction(discord.PartialEmoji.from_str(tag))
            except discord.HTTPException as e:
                print(f"🚨 [역할보드] 반응 추가 실패 ({name}): {e}")

    def _find_role(self, message_id: int, emoji_id: int):
        for board in BOARDS:
            if self.state.get(board["key"]) != message_id:
                continue
            for role_id, name, tag in board["roles"]:
                if _emoji_id(tag) == emoji_id:
                    return role_id, name
        return None, None

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.emoji.id is None:
            return
        role_id, name = self._find_role(payload.message_id, payload.emoji.id)
        if role_id is None:
            return

        member = payload.member
        if member is None or member.bot:
            return
        if not is_target_guild(member.guild):
            return

        role = member.guild.get_role(role_id)
        if not role or role in member.roles:
            return
        try:
            await member.add_roles(role, reason=f"티어 역할 선택 ({name})")
        except discord.Forbidden:
            return

        await send_log_embed(
            self.bot, ROLE_LOG_CH,
            "🎖️ 티어 역할 지급", f"{member.mention} 님이 **{name}** 역할을 선택했습니다.",
            member, discord.Color.green(), guild=member.guild)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        if payload.emoji.id is None:
            return
        role_id, name = self._find_role(payload.message_id, payload.emoji.id)
        if role_id is None:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if guild is None or not is_target_guild(guild):
            return
        member = guild.get_member(payload.user_id)
        if member is None or member.bot:
            return

        role = guild.get_role(role_id)
        if not role or role not in member.roles:
            return
        try:
            await member.remove_roles(role, reason=f"티어 역할 반응 취소 ({name})")
        except discord.Forbidden:
            return

        await send_log_embed(
            self.bot, ROLE_LOG_CH,
            "🎖️ 티어 역할 회수", f"{member.mention} 님이 **{name}** 반응을 취소해 역할을 회수했습니다.",
            member, discord.Color.orange(), guild=guild)


async def setup(bot: commands.Bot):
    await bot.add_cog(RoleBoardsCog(bot))
