# -*- coding: utf-8 -*-
"""
사용자 설정 저장/로드 유틸리티 (v1.0)

마지막 선택한 API, 모델 등을 JSON 파일에 저장하여
앱 재시작 후에도 설정 유지

저장 경로: data/user_preferences.json
"""

import json
import os
from pathlib import Path
from typing import Any, Optional, Dict

# 설정 파일 경로
_ROOT_DIR = Path(__file__).parent.parent
PREFERENCES_FILE = _ROOT_DIR / "data" / "user_preferences.json"


def ensure_preferences_file():
    """설정 파일 및 디렉토리 존재 확인"""
    PREFERENCES_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not PREFERENCES_FILE.exists():
        with open(PREFERENCES_FILE, 'w', encoding='utf-8') as f:
            json.dump({}, f, ensure_ascii=False, indent=2)


def load_preferences() -> Dict[str, Any]:
    """전체 설정 로드"""
    ensure_preferences_file()
    try:
        with open(PREFERENCES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {}


def save_preferences(preferences: Dict[str, Any]) -> None:
    """전체 설정 저장"""
    ensure_preferences_file()
    with open(PREFERENCES_FILE, 'w', encoding='utf-8') as f:
        json.dump(preferences, f, ensure_ascii=False, indent=2)


def get_preference(key: str, default: Any = None) -> Any:
    """특정 설정값 가져오기"""
    preferences = load_preferences()
    return preferences.get(key, default)


def set_preference(key: str, value: Any) -> None:
    """특정 설정값 저장"""
    preferences = load_preferences()
    preferences[key] = value
    save_preferences(preferences)


# ═══════════════════════════════════════════════════════════════════
# 캐릭터 관리 페이지 전용 함수
# ═══════════════════════════════════════════════════════════════════

def get_last_image_api() -> Optional[str]:
    """마지막 선택한 이미지 생성 API 가져오기"""
    return get_preference("character_management.last_image_api")


def set_last_image_api(api_name: str) -> None:
    """이미지 생성 API 선택값 저장"""
    set_preference("character_management.last_image_api", api_name)
    print(f"[UserPrefs] 이미지 API 저장: {api_name}")


def get_last_image_model() -> Optional[str]:
    """마지막 선택한 이미지 모델 가져오기"""
    return get_preference("character_management.last_image_model")


def set_last_image_model(model_name: str) -> None:
    """이미지 모델 선택값 저장"""
    set_preference("character_management.last_image_model", model_name)
    print(f"[UserPrefs] 이미지 모델 저장: {model_name}")


def get_last_concurrent_count() -> int:
    """마지막 동시 생성 수 가져오기"""
    return get_preference("character_management.last_concurrent_count", 4)


def set_last_concurrent_count(count: int) -> None:
    """동시 생성 수 저장"""
    set_preference("character_management.last_concurrent_count", count)
    print(f"[UserPrefs] 동시 생성 수 저장: {count}")


# ═══════════════════════════════════════════════════════════════════
# 통합 함수
# ═══════════════════════════════════════════════════════════════════

def get_character_image_settings() -> Dict[str, Any]:
    """캐릭터 이미지 생성 설정 전체 가져오기"""
    return {
        "image_api": get_last_image_api(),
        "image_model": get_last_image_model(),
        "concurrent_count": get_last_concurrent_count()
    }


def save_character_image_settings(
    image_api: str = None,
    image_model: str = None,
    concurrent_count: int = None
) -> None:
    """캐릭터 이미지 생성 설정 저장 (변경된 값만)"""
    if image_api is not None:
        set_last_image_api(image_api)
    if image_model is not None:
        set_last_image_model(image_model)
    if concurrent_count is not None:
        set_last_concurrent_count(concurrent_count)


# ═══════════════════════════════════════════════════════════════════
# 비디오 생성 페이지 전용 함수 (향후 확장용)
# ═══════════════════════════════════════════════════════════════════

def get_last_video_model() -> Optional[str]:
    """마지막 선택한 비디오 모델 가져오기"""
    return get_preference("video_generation.last_model")


def set_last_video_model(model_name: str) -> None:
    """비디오 모델 선택값 저장"""
    set_preference("video_generation.last_model", model_name)


def get_last_video_duration() -> int:
    """마지막 비디오 길이 가져오기"""
    return get_preference("video_generation.last_duration", 5)


def set_last_video_duration(duration: int) -> None:
    """비디오 길이 저장"""
    set_preference("video_generation.last_duration", duration)


# ═══════════════════════════════════════════════════════════════════
# 캐릭터 배치 생성 설정 (채널-영상별) v1.0
# ═══════════════════════════════════════════════════════════════════

def _get_channel_video_key(channel: str, video: str) -> str:
    """채널-영상 키 생성"""
    return f"{channel}/{video}"


def get_character_batch_settings(channel: str, video: str) -> Dict[str, Any]:
    """
    채널-영상별 캐릭터 배치 생성 설정 가져오기

    Args:
        channel: 채널명
        video: 영상명

    Returns:
        설정 딕셔너리 (character_style, pose, width, height, background_type, image_api)
    """
    key = _get_channel_video_key(channel, video)
    all_settings = get_preference("character_batch_settings", {})
    return all_settings.get(key, {})


def save_character_batch_settings(channel: str, video: str, settings: Dict[str, Any]) -> None:
    """
    채널-영상별 캐릭터 배치 생성 설정 저장

    Args:
        channel: 채널명
        video: 영상명
        settings: 저장할 설정 딕셔너리
    """
    key = _get_channel_video_key(channel, video)
    all_settings = get_preference("character_batch_settings", {})
    all_settings[key] = settings
    set_preference("character_batch_settings", all_settings)
    print(f"[UserPrefs] 캐릭터 배치 설정 저장: {key}")


def get_character_batch_setting(channel: str, video: str, setting_key: str, default: Any = None) -> Any:
    """특정 캐릭터 배치 설정값 가져오기"""
    settings = get_character_batch_settings(channel, video)
    return settings.get(setting_key, default)


def update_character_batch_setting(channel: str, video: str, setting_key: str, value: Any) -> None:
    """특정 캐릭터 배치 설정값 업데이트"""
    settings = get_character_batch_settings(channel, video)
    settings[setting_key] = value
    save_character_batch_settings(channel, video, settings)
    print(f"[UserPrefs] 캐릭터 배치 설정 업데이트: {setting_key}={value}")


# ═══════════════════════════════════════════════════════════════════
# 씬 분석 설정 (채널-영상별) v1.0
# ═══════════════════════════════════════════════════════════════════

def get_scene_analysis_settings(channel: str, video: str) -> Dict[str, Any]:
    """
    채널-영상별 씬 분석 설정 가져오기

    Args:
        channel: 채널명
        video: 영상명

    Returns:
        설정 딕셔너리:
        - script_source: 스크립트 소스 ("srt", "whisper", "pdf", "manual")
        - analysis_method: 분석 방식 ("openai", "gemini", "manual")
        - language: 언어 ("ko", "en", "auto")
        - auto_merge_empty_scenes: 빈 씬 자동 병합 여부 (bool)
    """
    key = _get_channel_video_key(channel, video)
    all_settings = get_preference("scene_analysis_settings", {})
    return all_settings.get(key, {})


def save_scene_analysis_settings(channel: str, video: str, settings: Dict[str, Any]) -> None:
    """
    채널-영상별 씬 분석 설정 저장

    Args:
        channel: 채널명
        video: 영상명
        settings: 저장할 설정 딕셔너리
    """
    key = _get_channel_video_key(channel, video)
    all_settings = get_preference("scene_analysis_settings", {})
    all_settings[key] = settings
    set_preference("scene_analysis_settings", all_settings)
    print(f"[UserPrefs] 씬 분석 설정 저장: {key}")


def get_scene_analysis_setting(channel: str, video: str, setting_key: str, default: Any = None) -> Any:
    """특정 씬 분석 설정값 가져오기"""
    settings = get_scene_analysis_settings(channel, video)
    return settings.get(setting_key, default)


def update_scene_analysis_setting(channel: str, video: str, setting_key: str, value: Any) -> None:
    """특정 씬 분석 설정값 업데이트"""
    settings = get_scene_analysis_settings(channel, video)
    settings[setting_key] = value
    save_scene_analysis_settings(channel, video, settings)
    print(f"[UserPrefs] 씬 분석 설정 업데이트: {setting_key}={value}")


# 씬 분석 개별 설정 함수들

def get_script_source(channel: str, video: str) -> str:
    """스크립트 소스 설정 가져오기 (기본값: srt)"""
    return get_scene_analysis_setting(channel, video, "script_source", "srt")


def set_script_source(channel: str, video: str, value: str) -> None:
    """스크립트 소스 설정 저장"""
    update_scene_analysis_setting(channel, video, "script_source", value)


def get_analysis_method(channel: str, video: str) -> str:
    """분석 방식 설정 가져오기 (기본값: gemini)"""
    return get_scene_analysis_setting(channel, video, "analysis_method", "gemini")


def set_analysis_method(channel: str, video: str, value: str) -> None:
    """분석 방식 설정 저장"""
    update_scene_analysis_setting(channel, video, "analysis_method", value)


def get_analysis_language(channel: str, video: str) -> str:
    """분석 언어 설정 가져오기 (기본값: ko)"""
    return get_scene_analysis_setting(channel, video, "language", "ko")


def set_analysis_language(channel: str, video: str, value: str) -> None:
    """분석 언어 설정 저장"""
    update_scene_analysis_setting(channel, video, "language", value)


def get_auto_merge_empty_scenes(channel: str, video: str) -> bool:
    """빈 씬 자동 병합 설정 가져오기 (기본값: True)"""
    return get_scene_analysis_setting(channel, video, "auto_merge_empty_scenes", True)


def set_auto_merge_empty_scenes(channel: str, video: str, value: bool) -> None:
    """빈 씬 자동 병합 설정 저장"""
    update_scene_analysis_setting(channel, video, "auto_merge_empty_scenes", value)
