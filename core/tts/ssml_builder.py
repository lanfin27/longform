"""
SSML (Speech Synthesis Markup Language) 빌더

Edge TTS용 SSML 생성 유틸리티
- 강조, 휴식, 발음 등 지원
- 스타일 적용 (mstts 확장)
- 자동 휴식 삽입
"""
from typing import Optional, List
from dataclasses import dataclass
from enum import Enum
import re


class BreakStrength(Enum):
    """휴식 강도"""
    NONE = "none"
    X_WEAK = "x-weak"
    WEAK = "weak"
    MEDIUM = "medium"
    STRONG = "strong"
    X_STRONG = "x-strong"


class EmphasisLevel(Enum):
    """강조 수준"""
    REDUCED = "reduced"
    NONE = "none"
    MODERATE = "moderate"
    STRONG = "strong"


@dataclass
class SSMLProsody:
    """음성 속성"""
    rate: str = "+0%"  # -50% ~ +100%
    pitch: str = "+0Hz"  # -50Hz ~ +50Hz
    volume: str = "+0%"  # -50% ~ +50%


class SSMLBuilder:
    """SSML 빌더"""

    def __init__(self, voice_id: str = "ko-KR-SunHiNeural"):
        self.voice_id = voice_id
        self.content_parts: List[str] = []
        self.prosody = SSMLProsody()
        self._lang = self._detect_language(voice_id)

    def _detect_language(self, voice_id: str) -> str:
        """음성 ID에서 언어 감지"""
        if voice_id.startswith("ko-"):
            return "ko-KR"
        elif voice_id.startswith("en-"):
            return voice_id.split("-")[0] + "-" + voice_id.split("-")[1]
        elif voice_id.startswith("ja-"):
            return "ja-JP"
        elif voice_id.startswith("zh-"):
            parts = voice_id.split("-")
            return parts[0] + "-" + parts[1]
        return "en-US"

    def set_prosody(
        self,
        rate: str = None,
        pitch: str = None,
        volume: str = None
    ) -> "SSMLBuilder":
        """음성 속성 설정"""
        if rate:
            self.prosody.rate = rate
        if pitch:
            self.prosody.pitch = pitch
        if volume:
            self.prosody.volume = volume
        return self

    def add_text(self, text: str) -> "SSMLBuilder":
        """일반 텍스트 추가"""
        self.content_parts.append(self._escape_xml(text))
        return self

    def add_break(
        self,
        time_ms: int = None,
        strength: BreakStrength = None
    ) -> "SSMLBuilder":
        """휴식 추가"""
        if time_ms:
            self.content_parts.append(f'<break time="{time_ms}ms"/>')
        elif strength:
            self.content_parts.append(f'<break strength="{strength.value}"/>')
        else:
            self.content_parts.append('<break time="500ms"/>')
        return self

    def add_emphasis(
        self,
        text: str,
        level: EmphasisLevel = EmphasisLevel.MODERATE
    ) -> "SSMLBuilder":
        """강조 텍스트 추가"""
        escaped = self._escape_xml(text)
        self.content_parts.append(f'<emphasis level="{level.value}">{escaped}</emphasis>')
        return self

    def add_say_as(
        self,
        text: str,
        interpret_as: str,
        format: str = None
    ) -> "SSMLBuilder":
        """특정 형식으로 읽기

        interpret_as 옵션:
        - "cardinal": 숫자를 숫자로 읽기 (123 -> "일이삼")
        - "ordinal": 서수로 읽기 (1 -> "첫 번째")
        - "characters": 문자 하나씩 (ABC -> "에이 비 씨")
        - "spell-out": 철자로 읽기
        - "date": 날짜로 읽기
        - "time": 시간으로 읽기
        - "telephone": 전화번호로 읽기
        """
        escaped = self._escape_xml(text)
        if format:
            self.content_parts.append(
                f'<say-as interpret-as="{interpret_as}" format="{format}">{escaped}</say-as>'
            )
        else:
            self.content_parts.append(
                f'<say-as interpret-as="{interpret_as}">{escaped}</say-as>'
            )
        return self

    def add_phoneme(
        self,
        text: str,
        phoneme: str,
        alphabet: str = "ipa"
    ) -> "SSMLBuilder":
        """발음 지정"""
        escaped = self._escape_xml(text)
        self.content_parts.append(
            f'<phoneme alphabet="{alphabet}" ph="{phoneme}">{escaped}</phoneme>'
        )
        return self

    def add_sub(self, text: str, alias: str) -> "SSMLBuilder":
        """대체 텍스트 (약어 등)"""
        escaped = self._escape_xml(text)
        alias_escaped = self._escape_xml(alias)
        self.content_parts.append(f'<sub alias="{alias_escaped}">{escaped}</sub>')
        return self

    def add_style(self, text: str, style: str, style_degree: float = 1.0) -> "SSMLBuilder":
        """스타일 적용 (mstts 확장)"""
        escaped = self._escape_xml(text)
        if style_degree != 1.0:
            self.content_parts.append(
                f'<mstts:express-as style="{style}" styledegree="{style_degree}">{escaped}</mstts:express-as>'
            )
        else:
            self.content_parts.append(
                f'<mstts:express-as style="{style}">{escaped}</mstts:express-as>'
            )
        return self

    def add_paragraph(self, text: str) -> "SSMLBuilder":
        """문단 추가"""
        escaped = self._escape_xml(text)
        self.content_parts.append(f'<p>{escaped}</p>')
        return self

    def add_sentence(self, text: str) -> "SSMLBuilder":
        """문장 추가"""
        escaped = self._escape_xml(text)
        self.content_parts.append(f'<s>{escaped}</s>')
        return self

    def build(self) -> str:
        """SSML 문자열 생성"""
        content = "".join(self.content_parts)

        # prosody 래핑
        prosody_attrs = []
        if self.prosody.rate != "+0%":
            prosody_attrs.append(f'rate="{self.prosody.rate}"')
        if self.prosody.pitch != "+0Hz":
            prosody_attrs.append(f'pitch="{self.prosody.pitch}"')
        if self.prosody.volume != "+0%":
            prosody_attrs.append(f'volume="{self.prosody.volume}"')

        if prosody_attrs:
            prosody_str = " ".join(prosody_attrs)
            content = f'<prosody {prosody_str}>{content}</prosody>'

        # 전체 SSML 구조
        ssml = f'''<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis"
    xmlns:mstts="https://www.w3.org/2001/mstts"
    xml:lang="{self._lang}">
    <voice name="{self.voice_id}">
        {content}
    </voice>
</speak>'''

        return ssml

    def _escape_xml(self, text: str) -> str:
        """XML 특수문자 이스케이프"""
        return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;"))

    def reset(self) -> "SSMLBuilder":
        """빌더 초기화"""
        self.content_parts = []
        return self


def create_ssml_with_breaks(
    text: str,
    voice_id: str,
    paragraph_break_ms: int = 800,
    sentence_break_ms: int = 300,
    rate: str = "+0%",
    pitch: str = "+0Hz",
    volume: str = "+0%"
) -> str:
    """
    자동으로 휴식을 삽입한 SSML 생성

    문단(빈 줄)과 문장(. ! ?) 사이에 휴식 삽입
    """
    builder = SSMLBuilder(voice_id)
    builder.set_prosody(rate=rate, pitch=pitch, volume=volume)

    # 문단 분리
    paragraphs = text.split("\n\n")

    for i, para in enumerate(paragraphs):
        if not para.strip():
            continue

        # 문장 분리
        sentences = []
        current = ""
        for char in para:
            current += char
            if char in ".!?。！？":
                sentences.append(current.strip())
                current = ""
        if current.strip():
            sentences.append(current.strip())

        # 문장 추가
        for j, sentence in enumerate(sentences):
            builder.add_text(sentence)
            if j < len(sentences) - 1:
                builder.add_break(time_ms=sentence_break_ms)

        # 문단 간 휴식
        if i < len(paragraphs) - 1:
            builder.add_break(time_ms=paragraph_break_ms)

    return builder.build()


def create_ssml_with_style(
    text: str,
    voice_id: str,
    style: str,
    style_degree: float = 1.0,
    rate: str = "+0%",
    pitch: str = "+0Hz",
    volume: str = "+0%"
) -> str:
    """
    스타일이 적용된 SSML 생성
    """
    builder = SSMLBuilder(voice_id)
    builder.set_prosody(rate=rate, pitch=pitch, volume=volume)
    builder.add_style(text, style, style_degree)
    return builder.build()


def create_simple_ssml(
    text: str,
    voice_id: str,
    rate: str = "+0%",
    pitch: str = "+0Hz",
    volume: str = "+0%"
) -> str:
    """
    기본 SSML 생성 (prosody만 적용)
    """
    builder = SSMLBuilder(voice_id)
    builder.set_prosody(rate=rate, pitch=pitch, volume=volume)
    builder.add_text(text)
    return builder.build()


def format_prosody_value(value: int, unit: str) -> str:
    """
    prosody 값 포맷팅

    Args:
        value: 수치 (-50 ~ 100 등)
        unit: 단위 (%, Hz)

    Returns:
        "+10%" 또는 "-5Hz" 형식 문자열
    """
    sign = "+" if value >= 0 else ""
    return f"{sign}{value}{unit}"


class TextProcessor:
    """텍스트 전처리기"""

    @staticmethod
    def split_sentences(text: str) -> List[str]:
        """문장 분리"""
        # 한국어/일본어/중국어 문장 부호 포함
        pattern = r'(?<=[.!?。！？])\s*'
        sentences = re.split(pattern, text)
        return [s.strip() for s in sentences if s.strip()]

    @staticmethod
    def split_paragraphs(text: str) -> List[str]:
        """문단 분리"""
        paragraphs = re.split(r'\n\s*\n', text)
        return [p.strip() for p in paragraphs if p.strip()]

    @staticmethod
    def estimate_duration(text: str, words_per_minute: int = 150) -> float:
        """예상 음성 길이 계산 (초)"""
        # 한국어: 분당 약 350-400 음절
        # 영어: 분당 약 150 단어
        if re.search(r'[가-힣]', text):
            # 한국어
            syllables = len(re.findall(r'[가-힣]', text))
            return (syllables / 375) * 60
        else:
            # 영어/기타
            words = len(text.split())
            return (words / words_per_minute) * 60

    @staticmethod
    def preprocess_for_tts(text: str) -> str:
        """TTS용 텍스트 전처리"""
        # 연속 공백 제거
        text = re.sub(r'\s+', ' ', text)

        # 특수문자 처리
        text = text.replace('...', '.')
        text = text.replace('..', '.')

        # URL 제거 또는 대체
        text = re.sub(r'https?://\S+', '', text)

        # 이모지 제거
        text = re.sub(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF]', '', text)

        return text.strip()
