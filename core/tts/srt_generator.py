"""
텍스트 기반 SRT 생성기

MP3 파일 없이 스크립트 텍스트만으로 SRT 자막을 생성합니다.
음성 인식 대신 평균 읽기 속도를 기준으로 타임스탬프를 추정합니다.
"""
import re
from pathlib import Path
from typing import List, Dict, Optional


class TextBasedSRTGenerator:
    """텍스트 기반 SRT 생성기"""

    # 평균 읽기 속도 (초당 글자 수)
    # 한국어: 분당 약 250자 = 초당 약 4.2자
    # 일본어: 분당 약 300자 = 초당 약 5자
    CHARS_PER_SECOND = {
        "ko": 4.2,
        "ja": 5.0,
        "en": 12.0  # 영어는 단어 기준이지만 글자로 환산
    }

    def __init__(self, language: str = "ko", chars_per_second: float = None):
        """
        Args:
            language: 언어 코드 (ko, ja, en)
            chars_per_second: 초당 글자 수 (None이면 언어별 기본값 사용)
        """
        self.language = language
        self.chars_per_second = chars_per_second or self.CHARS_PER_SECOND.get(language, 4.2)

    def generate_srt_from_text(
        self,
        text: str,
        output_path: str,
        audio_path: str = None,
        min_duration: float = 1.5,
        max_duration: float = 6.0
    ) -> Dict:
        """
        텍스트에서 SRT 파일 생성

        Args:
            text: 스크립트 텍스트
            output_path: SRT 저장 경로
            audio_path: MP3 파일 경로 (있으면 실제 길이 사용)
            min_duration: 최소 자막 표시 시간 (초)
            max_duration: 최대 자막 표시 시간 (초)

        Returns:
            생성 결과 정보
        """
        # 문장 분리
        sentences = self._split_into_sentences(text)

        if not sentences:
            return {"success": False, "error": "문장을 찾을 수 없습니다."}

        # 오디오 길이 확인 (있으면)
        total_duration = None
        if audio_path and Path(audio_path).exists():
            try:
                from pydub import AudioSegment
                audio = AudioSegment.from_file(audio_path)
                total_duration = len(audio) / 1000  # 밀리초 → 초
            except Exception as e:
                print(f"[WARNING] 오디오 로드 실패: {e}")

        # 타임스탬프 계산
        segments = self._calculate_timestamps(
            sentences,
            total_duration=total_duration,
            min_duration=min_duration,
            max_duration=max_duration
        )

        # SRT 파일 생성
        srt_content = self._generate_srt_content(segments)

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(srt_content, encoding="utf-8")

        return {
            "success": True,
            "srt_path": str(output_path),
            "segment_count": len(segments),
            "total_duration": segments[-1]["end_time"] if segments else 0
        }

    def _split_into_sentences(self, text: str) -> List[str]:
        """텍스트를 문장 단위로 분리"""
        # 섹션 마커 제거
        text = re.sub(r'\[(HOOK|INTRO|MAIN|CTA|OUTRO|포인트\s*\d+)\]', '', text, flags=re.IGNORECASE)

        # 줄바꿈으로 먼저 분리
        paragraphs = text.split('\n')

        sentences = []
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            # 문장 부호로 분리
            # 한국어/일본어: 。.!?
            parts = re.split(r'(?<=[.!?。！？])\s*', para)

            for part in parts:
                part = part.strip()
                if part and len(part) > 1:  # 최소 2글자
                    sentences.append(part)

        return sentences

    def _calculate_timestamps(
        self,
        sentences: List[str],
        total_duration: float = None,
        min_duration: float = 1.5,
        max_duration: float = 6.0
    ) -> List[Dict]:
        """각 문장의 타임스탬프 계산"""
        segments = []
        current_time = 0.0

        # 총 글자 수 계산
        total_chars = sum(len(s) for s in sentences)

        # 실제 오디오 길이가 있으면 속도 조정
        effective_cps = self.chars_per_second
        if total_duration and total_chars > 0:
            effective_cps = total_chars / total_duration

        for i, sentence in enumerate(sentences):
            # 문장 길이에 따른 예상 시간
            char_count = len(sentence)
            estimated_duration = char_count / effective_cps

            # 최소/최대 시간 적용
            duration = max(min_duration, min(estimated_duration, max_duration))

            segments.append({
                "index": i + 1,
                "start_time": current_time,
                "end_time": current_time + duration,
                "text": sentence
            })

            current_time += duration

        return segments

    def _generate_srt_content(self, segments: List[Dict]) -> str:
        """SRT 형식 문자열 생성"""
        lines = []

        for seg in segments:
            lines.append(str(seg["index"]))
            lines.append(f"{self._format_time(seg['start_time'])} --> {self._format_time(seg['end_time'])}")
            lines.append(seg["text"])
            lines.append("")  # 빈 줄

        return "\n".join(lines)

    def _format_time(self, seconds: float) -> str:
        """초를 SRT 타임코드 형식으로 변환 (00:00:00,000)"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)

        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def generate_srt_from_script(
    script_path: str,
    audio_path: str,
    output_path: str,
    language: str = "ko"
) -> Dict:
    """
    스크립트 파일에서 SRT 생성 (편의 함수)

    Args:
        script_path: 스크립트 파일 경로
        audio_path: MP3 파일 경로
        output_path: SRT 저장 경로
        language: 언어 코드

    Returns:
        생성 결과
    """
    script_path = Path(script_path)

    if not script_path.exists():
        return {"success": False, "error": f"스크립트 파일이 없습니다: {script_path}"}

    text = script_path.read_text(encoding="utf-8")

    generator = TextBasedSRTGenerator(language=language)
    return generator.generate_srt_from_text(text, output_path, audio_path)
