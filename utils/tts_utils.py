# -*- coding: utf-8 -*-
"""
TTS 텍스트 처리 유틸리티

텍스트 분할, 프리뷰 추출, 청크 관리 기능
"""
import re
from typing import List, Dict, Optional


def split_text_for_tts(
    text: str,
    max_chars: int = 80,
    split_on: str = "sentence"
) -> List[Dict]:
    """
    TTS용 텍스트 분할

    Chatterbox의 토큰 반복 감지로 인한 조기 종료 방지를 위해
    긴 텍스트를 적절한 크기로 분할합니다.

    Args:
        text: 원본 텍스트
        max_chars: 청크당 최대 글자 수 (기본 80자)
        split_on: "sentence" (문장 단위) 또는 "char" (글자 단위)

    Returns:
        [{"index": 1, "text": "...", "char_count": 50}, ...]
    """
    if not text or not text.strip():
        return []

    text = text.strip()

    # 텍스트가 max_chars 이하면 분할 불필요
    if len(text) <= max_chars:
        return [{"index": 1, "text": text, "char_count": len(text)}]

    chunks = []

    if split_on == "sentence":
        # 문장 단위 분할 (한국어 + 영어 지원)
        # 마침표, 물음표, 느낌표 뒤에서 분할
        sentences = re.split(r'(?<=[.!?。])\s*', text)

        current_chunk = ""

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            # 현재 청크 + 새 문장이 max_chars 이하면 합침
            if len(current_chunk) + len(sentence) + 1 <= max_chars:
                if current_chunk:
                    current_chunk += " " + sentence
                else:
                    current_chunk = sentence
            else:
                # 현재 청크 저장
                if current_chunk:
                    chunks.append(current_chunk)

                # 새 문장이 max_chars보다 길면 강제 분할
                if len(sentence) > max_chars:
                    sub_chunks = _force_split_long_sentence(sentence, max_chars)
                    chunks.extend(sub_chunks[:-1])
                    current_chunk = sub_chunks[-1] if sub_chunks else ""
                else:
                    current_chunk = sentence

        # 마지막 청크 저장
        if current_chunk:
            chunks.append(current_chunk)

    else:  # char 단위
        for i in range(0, len(text), max_chars):
            chunk = text[i:i + max_chars]
            chunks.append(chunk)

    # 결과 포맷팅
    result = []
    for idx, chunk in enumerate(chunks, 1):
        result.append({
            "index": idx,
            "text": chunk.strip(),
            "char_count": len(chunk.strip())
        })

    return result


def _force_split_long_sentence(sentence: str, max_chars: int) -> List[str]:
    """
    긴 문장을 쉼표나 공백에서 강제 분할

    Args:
        sentence: 분할할 문장
        max_chars: 최대 글자 수

    Returns:
        분할된 문장 리스트
    """
    if len(sentence) <= max_chars:
        return [sentence]

    chunks = []

    # 쉼표 기준 분할 시도
    parts = sentence.split(',')
    current = ""

    for part in parts:
        part = part.strip()
        if not part:
            continue

        if len(current) + len(part) + 2 <= max_chars:
            if current:
                current += ", " + part
            else:
                current = part
        else:
            if current:
                chunks.append(current)
            current = part

    if current:
        chunks.append(current)

    # 여전히 긴 청크가 있으면 공백에서 분할
    final_chunks = []
    for chunk in chunks:
        if len(chunk) > max_chars:
            words = chunk.split()
            sub_chunk = ""
            for word in words:
                if len(sub_chunk) + len(word) + 1 <= max_chars:
                    sub_chunk += " " + word if sub_chunk else word
                else:
                    if sub_chunk:
                        final_chunks.append(sub_chunk)
                    sub_chunk = word
            if sub_chunk:
                final_chunks.append(sub_chunk)
        else:
            final_chunks.append(chunk)

    return final_chunks if final_chunks else [sentence]


def get_preview_text(text: str, preview_length: int = 50) -> str:
    """
    프리뷰용 텍스트 추출 (문장 경계 고려)

    처음 N자 근처에서 문장 끝을 찾아 자연스럽게 자릅니다.

    Args:
        text: 원본 텍스트
        preview_length: 목표 프리뷰 길이

    Returns:
        프리뷰용 텍스트
    """
    if not text:
        return ""

    if len(text) <= preview_length:
        return text

    # preview_length 근처의 문장 끝 찾기
    preview = text[:preview_length]

    # 마지막 문장 끝 찾기
    last_period = max(
        preview.rfind('.'),
        preview.rfind('!'),
        preview.rfind('?'),
        preview.rfind('。')
    )

    if last_period > preview_length * 0.5:  # 50% 이상 위치에 문장 끝이 있으면
        return text[:last_period + 1]

    # 문장 끝이 없으면 그냥 자름
    return preview + "..."


def estimate_duration(text: str, chars_per_second: float = 5.0) -> float:
    """
    텍스트 길이로 음성 길이 추정

    Args:
        text: 텍스트
        chars_per_second: 초당 글자 수 (기본 5자/초)

    Returns:
        예상 초 단위 길이
    """
    if not text:
        return 0.0
    return len(text.strip()) / chars_per_second


def validate_chunk_duration(
    text_length: int,
    actual_duration: float,
    min_ratio: float = 0.08
) -> Dict:
    """
    청크 생성 결과가 잘렸는지 검증

    Chatterbox가 토큰 반복으로 조기 종료하면 실제 길이가 매우 짧아짐.
    정상 발화 속도는 약 8~10 글자/초 (글자당 0.1~0.125초).
    글자당 최소 0.08초 미만이면 잘린 것으로 판단 (12.5 글자/초 이상은 비정상).

    Args:
        text_length: 입력 텍스트 글자 수
        actual_duration: 실제 생성된 오디오 길이 (초)
        min_ratio: 글자당 최소 초 (기본 0.08초 = 최대 12.5 글자/초)

    Returns:
        {
            "is_valid": bool,
            "expected_min": float,
            "actual": float,
            "ratio": float,
            "chars_per_second": float
        }
    """
    expected_min = text_length * min_ratio
    ratio = actual_duration / text_length if text_length > 0 else 0
    chars_per_sec = text_length / actual_duration if actual_duration > 0 else float('inf')

    # 잘림 판정: 예상 최소 시간 미달 또는 발화 속도 12 글자/초 초과
    is_valid = actual_duration >= expected_min and chars_per_sec <= 12.0

    return {
        "is_valid": is_valid,
        "expected_min": expected_min,
        "actual": actual_duration,
        "ratio": ratio,
        "text_length": text_length,
        "chars_per_second": chars_per_sec
    }


def merge_chunk_results(chunk_results: List[Dict]) -> Dict:
    """
    청크별 생성 결과 통계 계산

    Args:
        chunk_results: 각 청크의 생성 결과 리스트

    Returns:
        {
            "total_chunks": int,
            "success_count": int,
            "failed_count": int,
            "truncated_count": int,
            "total_duration": float,
            "total_chars": int
        }
    """
    total = len(chunk_results)
    success = sum(1 for r in chunk_results if r.get("status") == "success")
    failed = sum(1 for r in chunk_results if r.get("status") == "failed")
    truncated = sum(1 for r in chunk_results if r.get("status") == "truncated")

    total_duration = sum(r.get("duration", 0) for r in chunk_results if r.get("status") == "success")
    total_chars = sum(r.get("char_count", 0) for r in chunk_results)

    return {
        "total_chunks": total,
        "success_count": success,
        "failed_count": failed,
        "truncated_count": truncated,
        "total_duration": total_duration,
        "total_chars": total_chars
    }
