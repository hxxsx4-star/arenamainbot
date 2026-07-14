import discord
from discord.ext import commands
from discord import app_commands
import random

LOL_LINES = ["탑", "정글", "미드", "원딜", "서폿"]
LOL_CHAMPIONS = sorted(list(set([
    "가렌", "갈리오", "갱플랭크", "그라가스", "그레이브즈", "그웬", "나르", "나미", "나서스", "노틸러스",
    "녹턴", "누누와 윌럼프", "니달리", "니코", "닐라", "다리우스", "다이애나", "드레이븐", "라이즈", "라칸",
    "람머스", "럭스", "럼블", "레나타 글라스크", "레넥톤", "레오나", "렉사이", "렐", "렝가", "루시안",
    "룰루", "르블랑", "리 신", "리븐", "리산드라", "릴리아", "마스터 이", "마오카이", "말자하", "말파이트",
    "모데카이저", "모르가나", "문도 박사", "미스 포츈", "바드", "바루스", "바이", "베이가", "베인", "벡스",
    "벨베스", "벨코즈", "볼리베어", "브라움", "브라이어", "브랜드", "블라디미르", "블리츠크랭크", "비에고", "빅토르",
    "뽀삐", "사미라", "사이온", "사일러스", "샤코", "세나", "세라핀", "세주아니", "세트", "소나",
    "소라카", "솔", "쉔", "쉬바나", "스웨인", "스카너", "시비르", "신 짜오", "신드라", "신지드",
    "쓰레쉬", "아리", "아무무", "아우렐리온 솔", "아이번", "아지르", "아칼리", "아크샨", "아트록스", "아펠리오스",
    "알리스타", "애니", "애니비아", "애쉬", "야스오", "에코", "엘리스", "오공", "오른", "오리아나",
    "올라프", "요네", "요릭", "우디르", "우르곳", "워윅", "유미", "이렐리아", "이블린", "이즈리얼",
    "일라오이", "자르반 4세", "자야", "자이라", "자크", "잔나", "잭스", "제드", "제라스", "제리",
    "제이스", "조이", "직스", "진", "질리언", "징크스", "초가스", "카르마", "카밀", "카사딘",
    "카서스", "카시오페아", "카이사", "카직스", "카타리나", "칼리스타", "케넨", "케이틀린", "케인", "케일",
    "코그모", "코르키", "퀸", "크산테", "클레드", "키아나", "킨드레드", "타릭", "탈론", "탈리야",
    "탐 켄치", "트런들", "트리스타나", "트린다미어", "트위스티드 페이트", "트위치", "티모", "파이크", "판테온", "피들스틱",
    "피오라", "피즈", "하이머딩거", "헤카림", "흐웨이"
])))

class GachaCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    gacha_group = app_commands.Group(name="가챠", description="랜덤으로 무언가를 뽑습니다.")

    @gacha_group.command(name="라인", description="LOL 라인을 무작위로 뽑습니다.")
    async def gacha_line(self, interaction: discord.Interaction):
        selected_line = random.choice(LOL_LINES)
        embed = discord.Embed(
            title="🎲 라인 가챠 결과!",
            description=f"선택된 라인은 {selected_line} 입니다!",
            color=discord.Color.random()
        )
        embed.set_footer(text=f"요청자: {interaction.user.display_name}")
        await interaction.response.send_message(embed=embed)

    @gacha_group.command(name="챔피언", description="LOL 챔피언을 무작위로 뽑습니다.")
    async def gacha_champion(self, interaction: discord.Interaction):
        selected_champion = random.choice(LOL_CHAMPIONS)
        embed = discord.Embed(
            title="🏆 챔피언 가챠 결과!",
            description=f"선택된 챔피언은 {selected_champion} 입니다!",
            color=discord.Color.random()
        )
        embed.set_footer(text=f"요청자: {interaction.user.display_name}")
        await interaction.response.send_message(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(GachaCog(bot))