# -*- coding: utf-8 -*-
"""
ImageFX 프롬프트 안전성 전처리 모듈 (v2.0 - AI 기반)

Google ImageFX/Imagen API의 유명인 필터(Prominent People Filter) 회피를 위한
프롬프트 전처리 모듈

v2.0 (2026-02):
- 하드코딩 완전 제거: 유명인/기업 이름 목록, regex 패턴 전부 삭제
- AI 기반 동적 정제: ProminentPeopleSanitizer로 위임
- aggressive_sanitize() → ai_aggressive_sanitize() 위임
- get_safe_character_name() → AI 위임
- is_prominent_people_error() 유지 (에러 탐지용)

사용법:
    from utils.imagefx_prompt_sanitizer import sanitize_prompt_for_imagefx, aggressive_sanitize

    # 기본 정제
    sanitized, changes = sanitize_prompt_for_imagefx(prompt)

    # 점진적 정제 (재시도용)
    sanitized = aggressive_sanitize(prompt, level=1)
"""

import logging
from typing import Tuple, List

logger = logging.getLogger(__name__)


def sanitize_prompt_for_imagefx(prompt: str) -> Tuple[str, List[str]]:
    """
    ImageFX용 프롬프트 안전성 전처리 (AI 기반)

    Args:
        prompt: 원본 프롬프트

    Returns:
        (정제된 프롬프트, 적용된 변환 목록)
    """
    if not prompt or not prompt.strip():
        return prompt, []

    try:
        from utils.prominent_people_sanitizer import (
            ProminentPeopleSanitizer,
            get_recommended_model
        )

        ai_model = get_recommended_model()
        sanitizer = ProminentPeopleSanitizer(ai_model=ai_model)
        result = sanitizer.sanitize(prompt)

        if result.was_modified:
            changes = [
                f"{k} → {v}" for k, v in result.replacements.items()
            ]
            logger.info(f"[PromptSanitizer] AI 정제 완료: {len(changes)}건 변경")
            return result.sanitized_prompt, changes
        else:
            return prompt, []

    except Exception as e:
        logger.warning(f"[PromptSanitizer] AI 정제 실패 (원본 반환): {e}")
        return prompt, []


def aggressive_sanitize(prompt: str, level: int = 0) -> str:
    """
    점진적으로 강력한 정제 적용 (AI 기반)

    Args:
        prompt: 원본 프롬프트
        level: 정제 강도
            0: 기본 정제 (유명인 이름/직함 제거)
            1: 강화 (유명인 암시 표현 + 기업명 제거)
            2: 완전 일반화 (모든 고유명사/특정 조직/문화적 특징 제거)

    Returns:
        정제된 프롬프트
    """
    if not prompt or not prompt.strip():
        return prompt

    logger.info(f"[PromptSanitizer] 정제 레벨 {level} 적용 중...")

    try:
        from utils.prominent_people_sanitizer import ai_aggressive_sanitize
        return ai_aggressive_sanitize(prompt, level=level)
    except Exception as e:
        logger.warning(f"[PromptSanitizer] AI 정제 실패 (원본 반환): {e}")
        return prompt


def get_safe_character_name(character_name: str) -> str:
    """
    캐릭터 이름을 ImageFX 안전한 형태로 변환 (AI 기반)

    Args:
        character_name: 원본 캐릭터 이름

    Returns:
        안전한 캐릭터 설명
    """
    if not character_name or not character_name.strip():
        return character_name

    try:
        from utils.prominent_people_sanitizer import (
            ProminentPeopleSanitizer,
            get_recommended_model
        )

        ai_model = get_recommended_model()
        sanitizer = ProminentPeopleSanitizer(ai_model=ai_model)
        result = sanitizer.sanitize(character_name)

        if result.was_modified:
            logger.info(f"[PromptSanitizer] 캐릭터명 변환: '{character_name}' → '{result.sanitized_prompt}'")
            return result.sanitized_prompt

    except Exception as e:
        logger.warning(f"[PromptSanitizer] 캐릭터명 AI 변환 실패: {e}")

    return character_name


def is_prominent_people_error(error_message: str) -> bool:
    """
    유명인 필터 오류인지 확인

    Args:
        error_message: 오류 메시지

    Returns:
        유명인 필터 오류 여부
    """
    prominent_patterns = [
        "PROMINENT_PEOPLE_FILTER_FAILED",
        "prominent people",
        "celebrity",
        "public figure",
        "famous person",
    ]

    error_lower = error_message.lower()

    for pattern in prominent_patterns:
        if pattern.lower() in error_lower:
            return True

    return False
