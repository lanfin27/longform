"""
문단별 무음 패딩 모듈

⚠️ Critical: 시니어를 위해 문단 사이 1.5초 무음 삽입

시니어 타겟의 경우 말이 빠르면 내용을 놓칠 수 있으므로,
문단이 바뀔 때 충분한 휴식 시간을 제공합니다.
"""
from pydub import AudioSegment
from pathlib import Path
import re
import json
from typing import List, Dict, Optional

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config.settings import TTS_DEFAULT_SILENCE_MS


class SilencePadder:
    """
    문단 사이에 무음 패딩을 추가하는 모듈

    기능:
    - 문단 구분점 자동 감지
    - 오디오에 무음 삽입
    - SRT 타임스탬프 자동 조정
    """

    DEFAULT_SILENCE_MS = TTS_DEFAULT_SILENCE_MS  # 1.5초
    SECTION_SILENCE_MS = 2000  # 섹션 마커에서는 2초

    def __init__(self, silence_duration_ms: int = None):
        """
        Args:
            silence_duration_ms: 기본 무음 길이 (밀리초)
        """
        self.silence_duration = silence_duration_ms or self.DEFAULT_SILENCE_MS

    def detect_paragraph_breaks(self, script: str) -> List[Dict]:
        """
        스크립트에서 문단 구분점 감지

        구분 기준:
        - 빈 줄 (\\n\\n)
        - [HOOK], [INTRO], [MAIN] 등의 섹션 마커
        - 번호 매기기 (1., 2., 첫째, 둘째 등)

        Args:
            script: 스크립트 텍스트

        Returns:
            문단 구분점 리스트
        """
        breaks = []

        # 1. 섹션 마커 감지 (더 긴 무음)
        section_pattern = r'\[(HOOK|INTRO|MAIN|CTA|OUTRO|포인트\s*\d+)\]'
        for match in re.finditer(section_pattern, script, re.IGNORECASE):
            breaks.append({
                "position": match.start(),
                "type": "section",
                "marker": match.group(),
                "silence_ms": self.SECTION_SILENCE_MS
            })

        # 2. 빈 줄 기준 문단 구분
        pos = 0
        paragraphs = script.split("\n\n")

        for i, para in enumerate(paragraphs[:-1]):  # 마지막 문단 제외
            pos += len(para) + 2  # +2 for \n\n

            # 섹션 마커와 겹치지 않는 경우만 추가
            if not any(abs(b["position"] - pos) < 50 for b in breaks):
                breaks.append({
                    "position": pos,
                    "type": "paragraph",
                    "silence_ms": self.silence_duration
                })

        # 위치순 정렬
        return sorted(breaks, key=lambda x: x["position"])

    def add_silence_to_audio(
        self,
        audio_path: str,
        paragraph_timings: List[Dict],
        output_path: str = None
    ) -> str:
        """
        오디오 파일의 문단 구분점에 무음 삽입

        Args:
            audio_path: 원본 오디오 파일 경로
            paragraph_timings: 문단 구분 타이밍 리스트
                [{"time_ms": 5000, "silence_ms": 1500}, ...]
            output_path: 출력 파일 경로 (None이면 원본 덮어쓰기)

        Returns:
            출력 파일 경로
        """
        # 오디오 로드
        audio = AudioSegment.from_file(audio_path)

        # 타이밍 역순 정렬 (뒤에서부터 삽입해야 앞의 타이밍이 밀리지 않음)
        sorted_timings = sorted(
            paragraph_timings,
            key=lambda x: x["time_ms"],
            reverse=True
        )

        # 각 문단 구분점에 무음 삽입
        for timing in sorted_timings:
            insert_point = timing["time_ms"]
            silence_ms = timing.get("silence_ms", self.silence_duration)

            # 무음 생성
            silence = AudioSegment.silent(duration=silence_ms)

            # 오디오 분할 후 무음 삽입
            before = audio[:insert_point]
            after = audio[insert_point:]
            audio = before + silence + after

        # 저장
        output = output_path or audio_path
        audio.export(output, format="mp3")

        return output

    def adjust_srt_for_silence(
        self,
        srt_segments: List[Dict],
        paragraph_timings: List[Dict]
    ) -> List[Dict]:
        """
        무음 삽입에 맞춰 SRT 타임스탬프 조정

        무음이 삽입되면 이후의 모든 자막 시간이 밀려야 함

        Args:
            srt_segments: SRT 세그먼트 리스트
            paragraph_timings: 문단 구분 타이밍 리스트

        Returns:
            조정된 SRT 세그먼트 리스트
        """
        # 타이밍 오름차순 정렬
        sorted_timings = sorted(paragraph_timings, key=lambda x: x["time_ms"])

        adjusted = []

        for seg in srt_segments:
            start_ms = seg["start_ms"]
            end_ms = seg["end_ms"]

            # 이 자막 이전에 삽입된 무음 시간 합계 계산
            offset = sum(
                t.get("silence_ms", self.silence_duration)
                for t in sorted_timings
                if t["time_ms"] < start_ms
            )

            adjusted.append({
                **seg,
                "start_ms": start_ms + offset,
                "end_ms": end_ms + offset
            })

        return adjusted

    def calculate_total_silence(self, paragraph_timings: List[Dict]) -> int:
        """
        삽입될 총 무음 시간 계산

        Args:
            paragraph_timings: 문단 구분 타이밍 리스트

        Returns:
            총 무음 시간 (밀리초)
        """
        return sum(
            t.get("silence_ms", self.silence_duration)
            for t in paragraph_timings
        )


def ms_to_srt_time(ms: int) -> str:
    """
    밀리초를 SRT 시간 형식으로 변환

    Args:
        ms: 밀리초

    Returns:
        "HH:MM:SS,mmm" 형식 문자열
    """
    hours = ms // 3600000
    minutes = (ms % 3600000) // 60000
    seconds = (ms % 60000) // 1000
    milliseconds = ms % 1000

    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


def srt_time_to_ms(time_str: str) -> int:
    """
    SRT 시간 형식을 밀리초로 변환

    Args:
        time_str: "HH:MM:SS,mmm" 형식 문자열

    Returns:
        밀리초
    """
    time_str = time_str.replace(",", ".").strip()
    parts = time_str.split(":")

    hours = int(parts[0])
    minutes = int(parts[1])
    seconds = float(parts[2])

    return int((hours * 3600 + minutes * 60 + seconds) * 1000)
