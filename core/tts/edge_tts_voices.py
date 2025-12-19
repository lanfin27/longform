"""
Edge TTS 음성 데이터베이스

모든 지원 음성 정보 관리
- 한국어 9개
- 영어 12개
- 일본어 8개
- 중국어 8개
"""
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from enum import Enum


class VoiceGender(Enum):
    MALE = "남성"
    FEMALE = "여성"


class VoiceStyle(Enum):
    """음성 스타일 (일부 음성만 지원)"""
    DEFAULT = "default"
    CHEERFUL = "cheerful"
    SAD = "sad"
    ANGRY = "angry"
    FEARFUL = "fearful"
    DISGRUNTLED = "disgruntled"
    SERIOUS = "serious"
    DEPRESSED = "depressed"
    EMBARRASSED = "embarrassed"
    AFFECTIONATE = "affectionate"
    GENTLE = "gentle"
    CALM = "calm"
    ENVIOUS = "envious"
    HOPEFUL = "hopeful"
    NEWSCAST = "newscast"
    CUSTOMERSERVICE = "customerservice"
    NARRATION = "narration-professional"
    CHAT = "chat"
    ASSISTANT = "assistant"


@dataclass
class VoiceInfo:
    """음성 정보"""
    id: str  # ko-KR-SunHiNeural
    name: str  # 선희
    language: str  # ko-KR
    language_name: str  # 한국어
    gender: VoiceGender
    description: str
    styles: List[str] = field(default_factory=list)
    sample_text: str = ""

    def to_dict(self) -> Dict:
        """딕셔너리 변환"""
        return {
            "id": self.id,
            "name": self.name,
            "language": self.language,
            "language_name": self.language_name,
            "gender": self.gender.value,
            "description": self.description,
            "styles": self.styles,
            "sample_text": self.sample_text,
            "has_styles": len(self.styles) > 0
        }


# ===================================================================
# 한국어 음성 (전체 9개)
# ===================================================================

KOREAN_VOICES = [
    VoiceInfo(
        id="ko-KR-SunHiNeural",
        name="선희",
        language="ko-KR",
        language_name="한국어",
        gender=VoiceGender.FEMALE,
        description="밝고 친근한 여성 음성. 일반적인 나레이션에 적합",
        styles=["cheerful", "sad", "angry", "fearful", "disgruntled", "serious", "depressed", "embarrassed"],
        sample_text="안녕하세요, 선희입니다. 밝고 친근한 목소리로 이야기해 드릴게요."
    ),
    VoiceInfo(
        id="ko-KR-InJoonNeural",
        name="인준",
        language="ko-KR",
        language_name="한국어",
        gender=VoiceGender.MALE,
        description="차분하고 신뢰감 있는 남성 음성. 뉴스, 다큐멘터리에 적합",
        styles=["cheerful", "sad", "angry", "fearful", "disgruntled", "serious", "depressed", "embarrassed"],
        sample_text="안녕하세요, 인준입니다. 차분하고 신뢰감 있는 목소리입니다."
    ),
    VoiceInfo(
        id="ko-KR-HyunsuNeural",
        name="현수",
        language="ko-KR",
        language_name="한국어",
        gender=VoiceGender.MALE,
        description="젊고 활기찬 남성 음성. 유튜브, 팟캐스트에 적합",
        styles=[],
        sample_text="안녕하세요, 현수입니다. 젊고 활기찬 목소리로 전달해 드릴게요."
    ),
    VoiceInfo(
        id="ko-KR-BongJinNeural",
        name="봉진",
        language="ko-KR",
        language_name="한국어",
        gender=VoiceGender.MALE,
        description="성숙하고 무게감 있는 남성 음성. 공식적인 발표에 적합",
        styles=[],
        sample_text="안녕하세요, 봉진입니다. 성숙하고 무게감 있는 목소리입니다."
    ),
    VoiceInfo(
        id="ko-KR-GookMinNeural",
        name="국민",
        language="ko-KR",
        language_name="한국어",
        gender=VoiceGender.MALE,
        description="표준적인 남성 음성. 일반 안내, 교육 콘텐츠에 적합",
        styles=[],
        sample_text="안녕하세요, 국민입니다. 표준적이고 깔끔한 목소리입니다."
    ),
    VoiceInfo(
        id="ko-KR-JiMinNeural",
        name="지민",
        language="ko-KR",
        language_name="한국어",
        gender=VoiceGender.FEMALE,
        description="젊고 상큼한 여성 음성. SNS, 광고에 적합",
        styles=[],
        sample_text="안녕하세요, 지민이에요! 상큼하고 밝은 목소리로 전할게요."
    ),
    VoiceInfo(
        id="ko-KR-SeoHyeonNeural",
        name="서현",
        language="ko-KR",
        language_name="한국어",
        gender=VoiceGender.FEMALE,
        description="부드럽고 우아한 여성 음성. 명상, ASMR에 적합",
        styles=[],
        sample_text="안녕하세요, 서현입니다. 부드럽고 편안한 목소리예요."
    ),
    VoiceInfo(
        id="ko-KR-SoonBokNeural",
        name="순복",
        language="ko-KR",
        language_name="한국어",
        gender=VoiceGender.FEMALE,
        description="성숙하고 따뜻한 여성 음성. 오디오북, 동화에 적합",
        styles=[],
        sample_text="안녕하세요, 순복이에요. 따뜻하고 포근한 이야기를 들려드릴게요."
    ),
    VoiceInfo(
        id="ko-KR-YuJinNeural",
        name="유진",
        language="ko-KR",
        language_name="한국어",
        gender=VoiceGender.FEMALE,
        description="활발하고 에너지 넘치는 여성 음성. 엔터테인먼트에 적합",
        styles=[],
        sample_text="안녕하세요! 유진이에요~ 활기차게 전해드릴게요!"
    ),
]


# ===================================================================
# 영어 음성 (주요 12개)
# ===================================================================

ENGLISH_VOICES = [
    VoiceInfo(
        id="en-US-JennyNeural",
        name="Jenny",
        language="en-US",
        language_name="영어 (미국)",
        gender=VoiceGender.FEMALE,
        description="친근하고 자연스러운 여성 음성",
        styles=["assistant", "chat", "customerservice", "newscast", "angry", "cheerful", "sad", "excited", "friendly", "terrified", "shouting", "unfriendly", "whispering", "hopeful"],
        sample_text="Hello, I'm Jenny. I have a friendly and natural voice."
    ),
    VoiceInfo(
        id="en-US-GuyNeural",
        name="Guy",
        language="en-US",
        language_name="영어 (미국)",
        gender=VoiceGender.MALE,
        description="전문적이고 신뢰감 있는 남성 음성",
        styles=["newscast", "angry", "cheerful", "sad", "excited", "friendly", "terrified", "shouting", "unfriendly", "whispering", "hopeful"],
        sample_text="Hello, I'm Guy. I have a professional and trustworthy voice."
    ),
    VoiceInfo(
        id="en-US-AriaNeural",
        name="Aria",
        language="en-US",
        language_name="영어 (미국)",
        gender=VoiceGender.FEMALE,
        description="명확하고 표현력 있는 여성 음성",
        styles=["chat", "customerservice", "narration-professional", "newscast-casual", "newscast-formal", "cheerful", "empathetic", "angry", "sad", "excited", "friendly", "terrified", "shouting", "unfriendly", "whispering", "hopeful"],
        sample_text="Hi, I'm Aria. My voice is clear and expressive."
    ),
    VoiceInfo(
        id="en-US-DavisNeural",
        name="Davis",
        language="en-US",
        language_name="영어 (미국)",
        gender=VoiceGender.MALE,
        description="깊고 풍부한 남성 음성",
        styles=["chat", "angry", "cheerful", "excited", "friendly", "hopeful", "sad", "shouting", "terrified", "unfriendly", "whispering"],
        sample_text="Hello, I'm Davis. I have a deep and rich voice."
    ),
    VoiceInfo(
        id="en-US-TonyNeural",
        name="Tony",
        language="en-US",
        language_name="영어 (미국)",
        gender=VoiceGender.MALE,
        description="젊고 역동적인 남성 음성",
        styles=["angry", "cheerful", "excited", "friendly", "hopeful", "sad", "shouting", "terrified", "unfriendly", "whispering"],
        sample_text="Hey, I'm Tony! I have a young and dynamic voice."
    ),
    VoiceInfo(
        id="en-US-NancyNeural",
        name="Nancy",
        language="en-US",
        language_name="영어 (미국)",
        gender=VoiceGender.FEMALE,
        description="따뜻하고 친절한 여성 음성",
        styles=["angry", "cheerful", "excited", "friendly", "hopeful", "sad", "shouting", "terrified", "unfriendly", "whispering"],
        sample_text="Hello, I'm Nancy. My voice is warm and kind."
    ),
    VoiceInfo(
        id="en-GB-SoniaNeural",
        name="Sonia",
        language="en-GB",
        language_name="영어 (영국)",
        gender=VoiceGender.FEMALE,
        description="우아한 영국 억양의 여성 음성",
        styles=["cheerful", "sad"],
        sample_text="Hello, I'm Sonia. I speak with a lovely British accent."
    ),
    VoiceInfo(
        id="en-GB-RyanNeural",
        name="Ryan",
        language="en-GB",
        language_name="영어 (영국)",
        gender=VoiceGender.MALE,
        description="품격 있는 영국 억양의 남성 음성",
        styles=["cheerful", "chat"],
        sample_text="Hello, I'm Ryan. I have a distinguished British voice."
    ),
    VoiceInfo(
        id="en-AU-NatashaNeural",
        name="Natasha",
        language="en-AU",
        language_name="영어 (호주)",
        gender=VoiceGender.FEMALE,
        description="생기 있는 호주 억양의 여성 음성",
        styles=[],
        sample_text="G'day, I'm Natasha. I have a lively Australian accent."
    ),
    VoiceInfo(
        id="en-AU-WilliamNeural",
        name="William",
        language="en-AU",
        language_name="영어 (호주)",
        gender=VoiceGender.MALE,
        description="친근한 호주 억양의 남성 음성",
        styles=[],
        sample_text="G'day, I'm William. I speak with an Aussie accent."
    ),
    VoiceInfo(
        id="en-IN-NeerjaNeural",
        name="Neerja",
        language="en-IN",
        language_name="영어 (인도)",
        gender=VoiceGender.FEMALE,
        description="인도 억양의 여성 음성",
        styles=["cheerful", "empathetic", "newscast"],
        sample_text="Hello, I'm Neerja. I speak English with an Indian accent."
    ),
    VoiceInfo(
        id="en-IN-PrabhatNeural",
        name="Prabhat",
        language="en-IN",
        language_name="영어 (인도)",
        gender=VoiceGender.MALE,
        description="인도 억양의 남성 음성",
        styles=[],
        sample_text="Hello, I'm Prabhat. I speak English with an Indian accent."
    ),
]


# ===================================================================
# 일본어 음성 (주요 8개)
# ===================================================================

JAPANESE_VOICES = [
    VoiceInfo(
        id="ja-JP-NanamiNeural",
        name="ナナミ (나나미)",
        language="ja-JP",
        language_name="일본어",
        gender=VoiceGender.FEMALE,
        description="밝고 자연스러운 여성 음성",
        styles=["chat", "cheerful", "customerservice"],
        sample_text="こんにちは、ナナミです。明るく自然な声でお届けします。"
    ),
    VoiceInfo(
        id="ja-JP-KeitaNeural",
        name="ケイタ (케이타)",
        language="ja-JP",
        language_name="일본어",
        gender=VoiceGender.MALE,
        description="차분하고 신뢰감 있는 남성 음성",
        styles=[],
        sample_text="こんにちは、ケイタです。落ち着いた声でお伝えします。"
    ),
    VoiceInfo(
        id="ja-JP-AoiNeural",
        name="アオイ (아오이)",
        language="ja-JP",
        language_name="일본어",
        gender=VoiceGender.FEMALE,
        description="젊고 상쾌한 여성 음성",
        styles=[],
        sample_text="こんにちは、アオイです！さわやかにお届けしますね。"
    ),
    VoiceInfo(
        id="ja-JP-DaichiNeural",
        name="ダイチ (다이치)",
        language="ja-JP",
        language_name="일본어",
        gender=VoiceGender.MALE,
        description="깊고 안정적인 남성 음성",
        styles=[],
        sample_text="こんにちは、ダイチです。安定感のある声でお届けします。"
    ),
    VoiceInfo(
        id="ja-JP-MayuNeural",
        name="マユ (마유)",
        language="ja-JP",
        language_name="일본어",
        gender=VoiceGender.FEMALE,
        description="부드럽고 친절한 여성 음성",
        styles=[],
        sample_text="こんにちは、マユです。やさしい声でお話しします。"
    ),
    VoiceInfo(
        id="ja-JP-NaokiNeural",
        name="ナオキ (나오키)",
        language="ja-JP",
        language_name="일본어",
        gender=VoiceGender.MALE,
        description="명확하고 전문적인 남성 음성",
        styles=[],
        sample_text="こんにちは、ナオキです。はっきりとお伝えします。"
    ),
    VoiceInfo(
        id="ja-JP-ShioriNeural",
        name="シオリ (시오리)",
        language="ja-JP",
        language_name="일본어",
        gender=VoiceGender.FEMALE,
        description="따뜻하고 편안한 여성 음성",
        styles=[],
        sample_text="こんにちは、シオリです。温かみのある声です。"
    ),
    VoiceInfo(
        id="ja-JP-TakumiNeural",
        name="タクミ (타쿠미)",
        language="ja-JP",
        language_name="일본어",
        gender=VoiceGender.MALE,
        description="젊고 활기찬 남성 음성",
        styles=[],
        sample_text="こんにちは、タクミです！元気にお届けします！"
    ),
]


# ===================================================================
# 중국어 음성 (주요 8개)
# ===================================================================

CHINESE_VOICES = [
    VoiceInfo(
        id="zh-CN-XiaoxiaoNeural",
        name="晓晓 (샤오샤오)",
        language="zh-CN",
        language_name="중국어 (간체)",
        gender=VoiceGender.FEMALE,
        description="밝고 친근한 여성 음성",
        styles=["assistant", "chat", "customerservice", "newscast", "affectionate", "angry", "calm", "cheerful", "disgruntled", "fearful", "gentle", "lyrical", "sad", "serious", "poetry-reading"],
        sample_text="你好，我是晓晓。我的声音明亮又亲切。"
    ),
    VoiceInfo(
        id="zh-CN-YunxiNeural",
        name="云希 (윈시)",
        language="zh-CN",
        language_name="중국어 (간체)",
        gender=VoiceGender.MALE,
        description="젊고 활기찬 남성 음성",
        styles=["narration-relaxed", "embarrassed", "fearful", "cheerful", "disgruntled", "serious", "angry", "sad", "depressed", "chat", "assistant", "newscast"],
        sample_text="你好，我是云希。我的声音年轻有活力。"
    ),
    VoiceInfo(
        id="zh-CN-YunjianNeural",
        name="云健 (윈젠)",
        language="zh-CN",
        language_name="중국어 (간체)",
        gender=VoiceGender.MALE,
        description="강하고 힘 있는 남성 음성",
        styles=["narration-relaxed", "sports-commentary", "sports-commentary-excited"],
        sample_text="你好，我是云健。我的声音有力量。"
    ),
    VoiceInfo(
        id="zh-CN-XiaoyiNeural",
        name="晓伊 (샤오이)",
        language="zh-CN",
        language_name="중국어 (간체)",
        gender=VoiceGender.FEMALE,
        description="부드럽고 세련된 여성 음성",
        styles=["affectionate", "angry", "cheerful", "disgruntled", "embarrassed", "fearful", "gentle", "sad", "serious"],
        sample_text="你好，我是晓伊。我的声音温柔优雅。"
    ),
    VoiceInfo(
        id="zh-CN-YunyangNeural",
        name="云扬 (윈양)",
        language="zh-CN",
        language_name="중국어 (간체)",
        gender=VoiceGender.MALE,
        description="전문적인 뉴스 캐스터 음성",
        styles=["customerservice", "narration-professional", "newscast-casual"],
        sample_text="你好，我是云扬。我的声音专业可靠。"
    ),
    VoiceInfo(
        id="zh-TW-HsiaoChenNeural",
        name="曉臻 (샤오첸)",
        language="zh-TW",
        language_name="중국어 (번체/대만)",
        gender=VoiceGender.FEMALE,
        description="친절한 대만 억양 여성 음성",
        styles=[],
        sample_text="你好，我是曉臻。我說話帶有台灣口音。"
    ),
    VoiceInfo(
        id="zh-TW-YunJheNeural",
        name="雲哲 (윈저)",
        language="zh-TW",
        language_name="중국어 (번체/대만)",
        gender=VoiceGender.MALE,
        description="안정적인 대만 억양 남성 음성",
        styles=[],
        sample_text="你好，我是雲哲。我的聲音穩重可靠。"
    ),
    VoiceInfo(
        id="zh-HK-HiuGaaiNeural",
        name="曉佳 (히우가이)",
        language="zh-HK",
        language_name="중국어 (광둥어)",
        gender=VoiceGender.FEMALE,
        description="광둥어 여성 음성",
        styles=[],
        sample_text="你好，我係曉佳。我講廣東話。"
    ),
]


# ===================================================================
# 스타일 이름 매핑 (한국어)
# ===================================================================

STYLE_NAMES_KO = {
    "cheerful": "밝음",
    "sad": "슬픔",
    "angry": "화남",
    "fearful": "두려움",
    "disgruntled": "불만",
    "serious": "진지함",
    "depressed": "우울함",
    "embarrassed": "당황",
    "affectionate": "애정",
    "gentle": "부드러움",
    "calm": "차분함",
    "envious": "질투",
    "hopeful": "희망",
    "newscast": "뉴스",
    "customerservice": "고객서비스",
    "narration-professional": "전문 나레이션",
    "narration-relaxed": "편안한 나레이션",
    "chat": "대화",
    "assistant": "어시스턴트",
    "newscast-casual": "캐주얼 뉴스",
    "newscast-formal": "공식 뉴스",
    "empathetic": "공감",
    "excited": "흥분",
    "friendly": "친근함",
    "terrified": "공포",
    "shouting": "외침",
    "unfriendly": "불친절",
    "whispering": "속삭임",
    "lyrical": "서정적",
    "poetry-reading": "시 낭송",
    "sports-commentary": "스포츠 중계",
    "sports-commentary-excited": "흥분된 스포츠 중계",
}


# ===================================================================
# 음성 관리 클래스
# ===================================================================

class VoiceDatabase:
    """음성 데이터베이스 관리"""

    def __init__(self):
        self.voices = {
            "ko": KOREAN_VOICES,
            "en": ENGLISH_VOICES,
            "ja": JAPANESE_VOICES,
            "zh": CHINESE_VOICES,
        }

        # ID로 빠른 조회용
        self._voice_by_id: Dict[str, VoiceInfo] = {}
        for voices in self.voices.values():
            for voice in voices:
                self._voice_by_id[voice.id] = voice

    def get_all_voices(self) -> List[VoiceInfo]:
        """모든 음성 반환"""
        all_voices = []
        for voices in self.voices.values():
            all_voices.extend(voices)
        return all_voices

    def get_voices_by_language(self, lang_code: str) -> List[VoiceInfo]:
        """언어별 음성 반환"""
        return self.voices.get(lang_code, [])

    def get_voice_by_id(self, voice_id: str) -> Optional[VoiceInfo]:
        """ID로 음성 조회"""
        return self._voice_by_id.get(voice_id)

    def get_voices_by_gender(self, gender: VoiceGender, lang_code: str = None) -> List[VoiceInfo]:
        """성별로 음성 필터링"""
        voices = self.get_voices_by_language(lang_code) if lang_code else self.get_all_voices()
        return [v for v in voices if v.gender == gender]

    def get_voices_with_styles(self, lang_code: str = None) -> List[VoiceInfo]:
        """스타일 지원하는 음성만"""
        voices = self.get_voices_by_language(lang_code) if lang_code else self.get_all_voices()
        return [v for v in voices if v.styles]

    def search_voices(self, query: str) -> List[VoiceInfo]:
        """음성 검색"""
        query = query.lower()
        results = []

        for voice in self.get_all_voices():
            if (query in voice.name.lower() or
                query in voice.id.lower() or
                query in voice.description.lower()):
                results.append(voice)

        return results

    def get_language_info(self) -> Dict[str, Dict]:
        """언어 정보 반환"""
        return {
            "ko": {"name": "한국어", "flag": "🇰🇷", "count": len(KOREAN_VOICES)},
            "en": {"name": "영어", "flag": "🇺🇸", "count": len(ENGLISH_VOICES)},
            "ja": {"name": "일본어", "flag": "🇯🇵", "count": len(JAPANESE_VOICES)},
            "zh": {"name": "중국어", "flag": "🇨🇳", "count": len(CHINESE_VOICES)},
        }

    def get_style_name(self, style: str) -> str:
        """스타일 한국어 이름 반환"""
        return STYLE_NAMES_KO.get(style, style)

    def get_voices_dict(self, lang_code: str = None) -> List[Dict]:
        """딕셔너리 형태로 음성 목록 반환 (settings.py 호환)"""
        voices = self.get_voices_by_language(lang_code) if lang_code else self.get_all_voices()
        return [v.to_dict() for v in voices]


# 싱글톤
_db: Optional[VoiceDatabase] = None


def get_voice_database() -> VoiceDatabase:
    """VoiceDatabase 싱글톤 인스턴스"""
    global _db
    if _db is None:
        _db = VoiceDatabase()
    return _db


# settings.py 호환 함수
def get_extended_tts_voices() -> Dict[str, List[Dict]]:
    """
    확장된 TTS 음성 목록 (settings.TTS_VOICES 대체용)

    Returns:
        {"ko": [...], "en": [...], "ja": [...], "zh": [...]}
    """
    db = get_voice_database()
    return {
        "ko": db.get_voices_dict("ko"),
        "en": db.get_voices_dict("en"),
        "ja": db.get_voices_dict("ja"),
        "zh": db.get_voices_dict("zh"),
    }
