# -*- coding: utf-8 -*-
"""
utils/prompt_defaults.py
기본 프롬프트 설정 관리 유틸리티

기능:
1. 단일/배치 분석용 기본 프롬프트 설정 저장/로드
2. JSON 파일 기반 영구 저장
3. session_state 연동
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict
import logging

logger = logging.getLogger(__name__)

# 설정 파일 경로 (프로젝트 루트 기준)
_ROOT_DIR = Path(__file__).parent.parent
PROMPT_DEFAULTS_FILE = _ROOT_DIR / "data" / "config" / "prompt_defaults.json"


def get_prompt_defaults_path() -> Path:
    """프롬프트 기본 설정 파일 경로 반환"""
    return PROMPT_DEFAULTS_FILE


def load_prompt_defaults() -> Dict:
    """
    기본 프롬프트 설정 로드

    Returns:
        {
            "default_prompts": {
                "single_scene_analysis": {...} or None,
                "batch_scene_analysis": {...} or None
            },
            "last_updated": "..."
        }
    """
    config_path = get_prompt_defaults_path()

    if config_path.exists():
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                logger.debug(f"[PromptDefaults] 설정 로드됨: {config_path}")
                return config
        except Exception as e:
            logger.warning(f"[PromptDefaults] 설정 로드 실패: {e}")

    # 기본값 반환
    return {
        "default_prompts": {
            "single_scene_analysis": None,
            "batch_scene_analysis": None
        },
        "last_updated": None
    }


def save_prompt_defaults(config: Dict) -> bool:
    """
    기본 프롬프트 설정 저장

    Args:
        config: 설정 딕셔너리

    Returns:
        성공 여부
    """
    config_path = get_prompt_defaults_path()

    # 디렉토리 생성
    config_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        config["last_updated"] = datetime.now().isoformat()

        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

        logger.info(f"[PromptDefaults] 설정 저장됨: {config_path}")
        return True
    except Exception as e:
        logger.error(f"[PromptDefaults] 설정 저장 실패: {e}")
        return False


def set_default_prompt(
    prompt_type: str,  # "single_scene_analysis" | "batch_scene_analysis"
    prompt_id: str,
    prompt_name: str
) -> bool:
    """
    기본 프롬프트 설정

    Args:
        prompt_type: 프롬프트 유형 ("single_scene_analysis" 또는 "batch_scene_analysis")
        prompt_id: 프롬프트 ID
        prompt_name: 프롬프트 이름

    Returns:
        성공 여부
    """
    config = load_prompt_defaults()

    config["default_prompts"][prompt_type] = {
        "prompt_id": prompt_id,
        "prompt_name": prompt_name,
        "set_at": datetime.now().isoformat()
    }

    success = save_prompt_defaults(config)

    if success:
        print(f"[PromptDefaults] {prompt_type} 기본 프롬프트 설정: {prompt_name}")

    return success


def get_default_prompt(prompt_type: str) -> Optional[Dict]:
    """
    기본 프롬프트 가져오기

    Args:
        prompt_type: "single_scene_analysis" 또는 "batch_scene_analysis"

    Returns:
        {"prompt_id": "...", "prompt_name": "...", "set_at": "..."}
        또는 None (설정 안 됨)
    """
    config = load_prompt_defaults()
    return config.get("default_prompts", {}).get(prompt_type)


def get_default_prompt_id(prompt_type: str) -> Optional[str]:
    """기본 프롬프트 ID만 반환"""
    default = get_default_prompt(prompt_type)
    return default.get("prompt_id") if default else None


def get_default_prompt_name(prompt_type: str) -> Optional[str]:
    """기본 프롬프트 이름만 반환"""
    default = get_default_prompt(prompt_type)
    return default.get("prompt_name") if default else None


def clear_default_prompt(prompt_type: str) -> bool:
    """
    기본 프롬프트 설정 해제

    Args:
        prompt_type: "single_scene_analysis" 또는 "batch_scene_analysis"

    Returns:
        성공 여부
    """
    config = load_prompt_defaults()
    config["default_prompts"][prompt_type] = None
    success = save_prompt_defaults(config)

    if success:
        print(f"[PromptDefaults] {prompt_type} 기본 프롬프트 해제됨")

    return success


def get_all_defaults() -> Dict[str, Optional[Dict]]:
    """
    모든 기본 프롬프트 설정 반환

    Returns:
        {
            "single_scene_analysis": {...} or None,
            "batch_scene_analysis": {...} or None
        }
    """
    config = load_prompt_defaults()
    return config.get("default_prompts", {
        "single_scene_analysis": None,
        "batch_scene_analysis": None
    })


def is_default_prompt_set(prompt_type: str) -> bool:
    """기본 프롬프트가 설정되어 있는지 확인"""
    return get_default_prompt(prompt_type) is not None


def validate_default_prompt(prompt_type: str, available_prompt_ids: list) -> bool:
    """
    기본 프롬프트가 유효한지 검증 (존재하는 프롬프트인지)

    Args:
        prompt_type: 프롬프트 유형
        available_prompt_ids: 사용 가능한 프롬프트 ID 목록

    Returns:
        유효 여부
    """
    default = get_default_prompt(prompt_type)
    if not default:
        return True  # 설정 안 됨 = 유효 (문제없음)

    return default.get("prompt_id") in available_prompt_ids
