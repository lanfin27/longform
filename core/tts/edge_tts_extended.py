"""
Edge TTS 확장 클라이언트

기존 edge_tts_client.py를 확장하여 추가 기능 제공:
- 전체 음성 지원 (37개+)
- 음성 샘플 미리듣기
- TTSSettings / TTSResult 데이터 클래스
- generate_tts() 메서드
"""
import os
import time
import hashlib
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# 기존 클라이언트 임포트
from core.tts.edge_tts_client import EdgeTTSClient as BaseEdgeTTSClient, run_async


@dataclass
class TTSResult:
    """TTS 생성 결과"""
    success: bool
    audio_path: Optional[str] = None
    subtitle_path: Optional[str] = None
    duration_seconds: float = 0.0
    error: Optional[str] = None
    paragraph_count: int = 0
    total_silence_ms: int = 0


@dataclass
class TTSSettings:
    """TTS 설정"""
    voice_id: str = "ko-KR-SunHiNeural"
    rate: int = 0  # -50 ~ +100 (%)
    pitch: int = 0  # -50 ~ +50 (Hz)
    volume: int = 0  # -50 ~ +50 (%)
    style: str = ""  # 감정/스타일 (지원 음성만)
    style_degree: float = 1.0  # 스타일 강도 (0.01 ~ 2.0)

    # 문단/문장 휴식
    paragraph_break_ms: int = 800
    sentence_break_ms: int = 300
    add_breaks: bool = True

    # 시니어 친화 (무음 패딩)
    add_silence: bool = True
    silence_ms: int = 1500

    # 자막
    generate_subtitles: bool = True

    def get_rate_string(self) -> str:
        return f"{'+' if self.rate >= 0 else ''}{self.rate}%"

    def get_pitch_string(self) -> str:
        return f"{'+' if self.pitch >= 0 else ''}{self.pitch}Hz"

    def get_volume_string(self) -> str:
        return f"{'+' if self.volume >= 0 else ''}{self.volume}%"


class ExtendedEdgeTTSClient(BaseEdgeTTSClient):
    """
    확장된 Edge TTS 클라이언트

    특징:
    - 모든 음성 지원 (37개+)
    - 속도/피치/볼륨 조절
    - 감정/스타일 적용
    - 문단별 무음 패딩 자동 삽입
    - SRT 자막 자동 생성
    - 음성 샘플 미리듣기
    """

    def __init__(self, output_dir: str = None):
        super().__init__()
        self.output_dir = output_dir or str(Path(__file__).parent.parent.parent / "data" / "tts")
        self.sample_dir = os.path.join(self.output_dir, "samples")

        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.sample_dir, exist_ok=True)

    # ===================================================================
    # 음성 목록 조회 (확장)
    # ===================================================================

    @classmethod
    def get_all_voices(cls, language: str = None) -> List[Dict]:
        """
        사용 가능한 모든 음성 목록 반환 (확장)

        Args:
            language: 언어 코드 ("ko", "en", "ja", "zh") 또는 None (전체)

        Returns:
            음성 정보 딕셔너리 리스트
        """
        try:
            from core.tts.edge_tts_voices import get_voice_database

            db = get_voice_database()
            if language:
                return db.get_voices_dict(language)
            return [v.to_dict() for v in db.get_all_voices()]
        except ImportError:
            # 폴백: 기존 메서드 사용
            return cls.get_voices(language) if language else []

    @classmethod
    def get_voice_info(cls, voice_id: str) -> Optional[Dict]:
        """
        음성 ID로 정보 조회

        Args:
            voice_id: 음성 ID (예: "ko-KR-SunHiNeural")

        Returns:
            음성 정보 딕셔너리 또는 None
        """
        try:
            from core.tts.edge_tts_voices import get_voice_database

            db = get_voice_database()
            voice = db.get_voice_by_id(voice_id)
            return voice.to_dict() if voice else None
        except ImportError:
            return None

    @classmethod
    def get_voices_with_styles(cls, language: str = None) -> List[Dict]:
        """스타일 지원하는 음성만 반환"""
        try:
            from core.tts.edge_tts_voices import get_voice_database

            db = get_voice_database()
            voices = db.get_voices_with_styles(language)
            return [v.to_dict() for v in voices]
        except ImportError:
            return []

    @classmethod
    def get_language_info(cls) -> Dict[str, Dict]:
        """언어 정보 반환"""
        try:
            from core.tts.edge_tts_voices import get_voice_database

            db = get_voice_database()
            return db.get_language_info()
        except ImportError:
            return {
                "ko": {"name": "한국어", "flag": "🇰🇷", "count": 3},
                "ja": {"name": "일본어", "flag": "🇯🇵", "count": 3},
            }

    # ===================================================================
    # 음성 샘플 생성
    # ===================================================================

    async def generate_sample_async(
        self,
        voice_id: str,
        sample_text: str = None
    ) -> Optional[str]:
        """음성 샘플 생성 (미리듣기용)"""
        import edge_tts

        try:
            from core.tts.edge_tts_voices import get_voice_database

            db = get_voice_database()
            voice = db.get_voice_by_id(voice_id)

            if not sample_text:
                sample_text = voice.sample_text if voice else "안녕하세요, 테스트 음성입니다."
        except ImportError:
            if not sample_text:
                sample_text = "안녕하세요, 테스트 음성입니다."

        # 캐시 확인
        cache_key = hashlib.md5(f"{voice_id}_{sample_text}".encode()).hexdigest()[:12]
        sample_path = os.path.join(self.sample_dir, f"sample_{cache_key}.mp3")

        if os.path.exists(sample_path):
            return sample_path

        try:
            communicate = edge_tts.Communicate(sample_text, voice_id)
            await communicate.save(sample_path)
            return sample_path
        except Exception as e:
            print(f"[EdgeTTS] 샘플 생성 오류: {e}")
            return None

    def generate_sample(self, voice_id: str, sample_text: str = None) -> Optional[str]:
        """음성 샘플 생성 (동기)"""
        return run_async(self.generate_sample_async(voice_id, sample_text))

    # ===================================================================
    # TTS 생성 (확장)
    # ===================================================================

    async def generate_tts_async(
        self,
        text: str,
        settings: TTSSettings = None,
        output_path: str = None
    ) -> TTSResult:
        """
        TTS 생성 (비동기)

        Args:
            text: 스크립트 텍스트
            settings: TTS 설정
            output_path: 출력 파일 경로 (None이면 자동 생성)

        Returns:
            TTSResult
        """
        if settings is None:
            settings = TTSSettings()

        try:
            # 출력 경로 설정
            if output_path is None:
                timestamp = int(time.time() * 1000)
                output_path = os.path.join(self.output_dir, f"tts_{timestamp}.mp3")

            # 기존 메서드 호출
            result = await self.generate_audio_with_silence(
                text=text,
                voice=settings.voice_id,
                output_path=output_path,
                rate=settings.get_rate_string(),
                pitch=settings.get_pitch_string(),
                volume=settings.get_volume_string(),
                add_silence=settings.add_silence,
                silence_ms=settings.silence_ms
            )

            return TTSResult(
                success=True,
                audio_path=result.get("audio_path"),
                subtitle_path=result.get("srt_path"),
                paragraph_count=result.get("paragraph_count", 0),
                total_silence_ms=result.get("total_silence_ms", 0)
            )

        except Exception as e:
            return TTSResult(success=False, error=str(e))

    def generate_tts(
        self,
        text: str,
        settings: TTSSettings = None,
        output_path: str = None
    ) -> TTSResult:
        """TTS 생성 (동기)"""
        return run_async(self.generate_tts_async(text, settings, output_path))


# 싱글톤
_extended_client: Optional[ExtendedEdgeTTSClient] = None


def get_extended_edge_tts_client() -> ExtendedEdgeTTSClient:
    """ExtendedEdgeTTSClient 싱글톤 인스턴스"""
    global _extended_client
    if _extended_client is None:
        _extended_client = ExtendedEdgeTTSClient()
    return _extended_client


# 별칭 (편의성)
def get_edge_tts_client() -> ExtendedEdgeTTSClient:
    """EdgeTTSClient 싱글톤 인스턴스 (확장 버전)"""
    return get_extended_edge_tts_client()
