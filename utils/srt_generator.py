# -*- coding: utf-8 -*-
"""
utils/srt_generator.py
SRT 자막 파일 생성 유틸리티 (v1.0)

주요 기능:
1. SRT 형식 자막 파일 생성
2. VTT 형식 지원 (웹 호환)
3. 타임코드 계산 (TTS duration 또는 스크립트 기반 추정)
4. 개별/통합 SRT 파일 생성
"""

from typing import List, Dict, Tuple, Optional
from datetime import timedelta
import re


def format_srt_timestamp(seconds: float) -> str:
    """
    초를 SRT 타임스탬프 형식으로 변환

    Args:
        seconds: 시간 (초)

    Returns:
        "HH:MM:SS,mmm" 형식의 문자열
    """
    if seconds < 0:
        seconds = 0

    total_seconds = int(seconds)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    milliseconds = int((seconds - int(seconds)) * 1000)

    return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"


def format_vtt_timestamp(seconds: float) -> str:
    """
    초를 VTT 타임스탬프 형식으로 변환

    Args:
        seconds: 시간 (초)

    Returns:
        "HH:MM:SS.mmm" 형식의 문자열
    """
    # VTT는 콤마 대신 점 사용
    return format_srt_timestamp(seconds).replace(",", ".")


def estimate_duration_from_script(script: str, chars_per_second: float = 4.0) -> float:
    """
    스크립트 길이 기반 duration 추정

    한국어 평균 읽기 속도: 약 250-300자/분 ≈ 4-5자/초

    Args:
        script: 스크립트 텍스트
        chars_per_second: 초당 글자 수 (기본: 4.0)

    Returns:
        추정 duration (초)
    """
    if not script:
        return 2.0  # 기본값 2초

    # 공백 제거한 글자 수
    char_count = len(script.replace(" ", "").replace("\n", ""))

    # 최소 1초, 최대 30초
    duration = max(1.0, min(30.0, char_count / chars_per_second))

    return round(duration, 2)


def get_scene_duration(scene: Dict) -> float:
    """
    씬의 duration 가져오기

    여러 필드를 확인하여 duration 반환
    TTS duration이 없으면 스크립트로 추정
    """
    # TTS/오디오 duration 확인 (여러 필드명 지원)
    duration = (
        scene.get("tts_duration") or
        scene.get("audio_duration") or
        scene.get("duration") or
        scene.get("scene_duration") or
        scene.get("자막_길이")
    )

    if duration and duration > 0:
        return float(duration)

    # 스크립트 기반 추정
    script = scene.get("script_text") or scene.get("스크립트") or ""
    return estimate_duration_from_script(script)


def calculate_scene_timings(scenes: List[Dict]) -> List[Dict]:
    """
    씬들의 시작/종료 시간 계산

    Args:
        scenes: 씬 목록

    Returns:
        타이밍 정보가 추가된 씬 목록
    """
    result = []
    cumulative_time = 0.0

    for scene in scenes:
        duration = get_scene_duration(scene)

        start_time = cumulative_time
        end_time = cumulative_time + duration

        result.append({
            **scene,
            "srt_start_time": start_time,
            "srt_end_time": end_time,
            "srt_duration": duration,
        })

        cumulative_time = end_time

    return result


def generate_srt_content(
    scenes: List[Dict],
    include_scene_number: bool = False,
    include_timecode: bool = True,
    encoding: str = "utf-8"
) -> str:
    """
    SRT 파일 내용 생성

    Args:
        scenes: 씬 목록
        include_scene_number: 자막에 씬 번호 포함 여부
        include_timecode: 타임코드 포함 여부
        encoding: 인코딩 방식

    Returns:
        SRT 형식의 문자열
    """
    if not scenes:
        return ""

    # 타임코드 계산
    timed_scenes = calculate_scene_timings(scenes)

    srt_lines = []
    subtitle_idx = 0

    for scene in timed_scenes:
        # 스크립트 가져오기
        script = (
            scene.get("script_text") or
            scene.get("스크립트") or
            scene.get("narration") or
            ""
        ).strip()

        if not script:
            continue

        subtitle_idx += 1
        scene_id = scene.get("scene_id") or scene.get("id") or subtitle_idx

        # 자막 인덱스
        srt_lines.append(str(subtitle_idx))

        # 타임코드
        if include_timecode:
            start_ts = format_srt_timestamp(scene["srt_start_time"])
            end_ts = format_srt_timestamp(scene["srt_end_time"])
        else:
            # 기본 2초 간격
            start_ts = format_srt_timestamp((subtitle_idx - 1) * 2)
            end_ts = format_srt_timestamp(subtitle_idx * 2)

        srt_lines.append(f"{start_ts} --> {end_ts}")

        # 자막 텍스트
        if include_scene_number:
            srt_lines.append(f"[씬 {scene_id}] {script}")
        else:
            srt_lines.append(script)

        # 빈 줄 (구분자)
        srt_lines.append("")

    return "\n".join(srt_lines)


def generate_vtt_content(
    scenes: List[Dict],
    include_scene_number: bool = False
) -> str:
    """
    WebVTT 형식 생성 (웹 호환)

    Args:
        scenes: 씬 목록
        include_scene_number: 씬 번호 포함 여부

    Returns:
        VTT 형식의 문자열
    """
    if not scenes:
        return "WEBVTT\n"

    timed_scenes = calculate_scene_timings(scenes)

    vtt_lines = ["WEBVTT", ""]
    subtitle_idx = 0

    for scene in timed_scenes:
        script = (
            scene.get("script_text") or
            scene.get("스크립트") or
            ""
        ).strip()

        if not script:
            continue

        subtitle_idx += 1
        scene_id = scene.get("scene_id") or scene.get("id") or subtitle_idx

        # VTT 타임코드 (점 사용)
        start_ts = format_vtt_timestamp(scene["srt_start_time"])
        end_ts = format_vtt_timestamp(scene["srt_end_time"])

        vtt_lines.append(f"{subtitle_idx}")
        vtt_lines.append(f"{start_ts} --> {end_ts}")

        if include_scene_number:
            vtt_lines.append(f"[씬 {scene_id}] {script}")
        else:
            vtt_lines.append(script)

        vtt_lines.append("")

    return "\n".join(vtt_lines)


def generate_individual_srt_files(
    scenes: List[Dict],
    include_scene_number: bool = False
) -> List[Tuple[str, str]]:
    """
    씬별 개별 SRT 파일 생성

    Args:
        scenes: 씬 목록
        include_scene_number: 씬 번호 포함 여부

    Returns:
        [(파일명, 내용), ...] 형태의 리스트
    """
    result = []

    for scene in scenes:
        scene_id = scene.get("scene_id") or scene.get("id")
        script = (
            scene.get("script_text") or
            scene.get("스크립트") or
            ""
        ).strip()

        if not script:
            continue

        duration = get_scene_duration(scene)

        # 개별 SRT 내용 (해당 씬만, 시작 0초)
        if include_scene_number:
            text = f"[씬 {scene_id}] {script}"
        else:
            text = script

        srt_content = f"""1
00:00:00,000 --> {format_srt_timestamp(duration)}
{text}
"""

        filename = f"scene_{scene_id:03d}.srt"
        result.append((filename, srt_content))

    return result


def get_srt_stats(scenes: List[Dict]) -> Dict:
    """
    SRT 통계 정보 반환

    Args:
        scenes: 씬 목록

    Returns:
        통계 정보 딕셔너리
    """
    timed_scenes = calculate_scene_timings(scenes)

    # 스크립트가 있는 씬만 카운트
    valid_scenes = [
        s for s in timed_scenes
        if (s.get("script_text") or s.get("스크립트") or "").strip()
    ]

    if not valid_scenes:
        return {
            "subtitle_count": 0,
            "total_duration": 0.0,
            "total_duration_formatted": "00:00:00",
            "has_tts_duration": False,
            "estimated_count": 0
        }

    total_duration = valid_scenes[-1].get("srt_end_time", 0) if valid_scenes else 0

    # TTS duration이 있는 씬 수
    tts_count = sum(
        1 for s in scenes
        if s.get("tts_duration") or s.get("audio_duration")
    )

    return {
        "subtitle_count": len(valid_scenes),
        "total_duration": total_duration,
        "total_duration_formatted": format_srt_timestamp(total_duration).split(",")[0],
        "has_tts_duration": tts_count > 0,
        "tts_duration_count": tts_count,
        "estimated_count": len(valid_scenes) - tts_count
    }


def parse_srt_timestamp(timestamp: str) -> float:
    """
    SRT 타임스탬프를 초로 변환

    Args:
        timestamp: "HH:MM:SS,mmm" 형식

    Returns:
        초 (float)
    """
    # 콤마 또는 점 처리
    timestamp = timestamp.replace(".", ",")
    parts = timestamp.replace(",", ":").split(":")

    if len(parts) < 4:
        return 0.0

    hours = int(parts[0])
    minutes = int(parts[1])
    seconds = int(parts[2])
    milliseconds = int(parts[3])

    return hours * 3600 + minutes * 60 + seconds + milliseconds / 1000


def parse_existing_srt(srt_content: str) -> List[Dict]:
    """
    기존 SRT 파일 파싱

    Args:
        srt_content: SRT 파일 내용

    Returns:
        [{"index": 1, "start": 0.0, "end": 2.5, "text": "..."}, ...]
    """
    result = []

    # SRT 블록 패턴
    pattern = r'(\d+)\s*\n(\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*\n([\s\S]*?)(?=\n\n|\n*$)'

    matches = re.findall(pattern, srt_content)

    for match in matches:
        index, start_ts, end_ts, text = match

        result.append({
            "index": int(index),
            "start": parse_srt_timestamp(start_ts),
            "end": parse_srt_timestamp(end_ts),
            "text": text.strip(),
        })

    return result
