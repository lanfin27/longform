# -*- coding: utf-8 -*-
"""
사용자 설정 영속성 관리 유틸리티 (v1.0)

기능:
- 사용자 설정을 파일에 자동 저장
- 앱 재시작/페이지 로드 시 자동 복원
- 페이지별 독립 설정 관리
- TTS 관련 설정 제외

사용법:
    from utils.user_settings import (
        persistent_selectbox,
        persistent_radio,
        persistent_checkbox,
        init_page_settings
    )

    PAGE_NAME = "scene_analysis"

    # 저장되는 selectbox
    model = persistent_selectbox(
        "AI 모델",
        options=["Gemini", "Claude"],
        page_name=PAGE_NAME,
        setting_key="ai_model"
    )
"""

import os
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, List, Union
import streamlit as st

# 설정 파일 디렉토리
SETTINGS_DIR = Path("data/user_settings")

# TTS 제외 - 저장하지 않을 키 패턴
EXCLUDED_KEY_PATTERNS = [
    "tts_", "audio_", "voice_", "chatterbox_",
    "speech_", "elevenlabs_", "bark_", "coqui_"
]


def is_excluded_key(key: str) -> bool:
    """TTS 관련 키인지 확인"""
    if not key:
        return False
    key_lower = key.lower()
    return any(pattern in key_lower for pattern in EXCLUDED_KEY_PATTERNS)


def get_settings_path(page_name: str) -> Path:
    """페이지별 설정 파일 경로 반환"""
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    # 파일명 안전하게 변환
    safe_name = page_name.replace(" ", "_").replace("/", "_").replace(":", "_")
    return SETTINGS_DIR / f"{safe_name}.json"


def _make_serializable(obj: Any) -> Any:
    """JSON 직렬화 가능하도록 변환"""
    if isinstance(obj, dict):
        return {str(k): _make_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [_make_serializable(item) for item in obj]
    elif isinstance(obj, set):
        return list(obj)
    elif isinstance(obj, (str, int, float, bool, type(None))):
        return obj
    elif isinstance(obj, Path):
        return str(obj)
    elif hasattr(obj, "isoformat"):  # datetime 등
        return obj.isoformat()
    elif hasattr(obj, "__dict__"):
        return str(obj)
    else:
        return str(obj)


def save_page_settings(page_name: str, settings: Dict[str, Any]) -> bool:
    """
    페이지 설정 저장

    Args:
        page_name: 페이지 이름 (예: "scene_analysis", "image_generation")
        settings: 저장할 설정 딕셔너리

    Returns:
        저장 성공 여부
    """
    try:
        # TTS 관련 키 제외
        filtered_settings = {
            k: v for k, v in settings.items()
            if not is_excluded_key(k)
        }

        # 직렬화 불가능한 타입 처리
        serializable_settings = _make_serializable(filtered_settings)

        data = {
            "last_updated": datetime.now().isoformat(),
            "page_name": page_name,
            "version": "1.0",
            "settings": serializable_settings
        }

        filepath = get_settings_path(page_name)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return True

    except Exception as e:
        print(f"[UserSettings] 설정 저장 실패 ({page_name}): {e}")
        return False


def load_page_settings(page_name: str) -> Dict[str, Any]:
    """
    페이지 설정 로드

    Args:
        page_name: 페이지 이름

    Returns:
        저장된 설정 딕셔너리 (없으면 빈 딕셔너리)
    """
    try:
        filepath = get_settings_path(page_name)

        if not filepath.exists():
            return {}

        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        return data.get("settings", {})

    except Exception as e:
        print(f"[UserSettings] 설정 로드 실패 ({page_name}): {e}")
        return {}


def save_setting(page_name: str, key: str, value: Any) -> None:
    """단일 설정 저장"""
    if is_excluded_key(key):
        return

    settings = load_page_settings(page_name)
    settings[key] = _make_serializable(value)
    save_page_settings(page_name, settings)


def load_setting(page_name: str, key: str, default: Any = None) -> Any:
    """단일 설정 로드"""
    settings = load_page_settings(page_name)
    return settings.get(key, default)


def delete_setting(page_name: str, key: str) -> None:
    """단일 설정 삭제"""
    settings = load_page_settings(page_name)
    if key in settings:
        del settings[key]
        save_page_settings(page_name, settings)


def clear_page_settings(page_name: str) -> None:
    """페이지 설정 전체 삭제"""
    filepath = get_settings_path(page_name)
    if filepath.exists():
        filepath.unlink()


# === Streamlit 통합 헬퍼 함수 ===

def init_page_settings(page_name: str, defaults: Dict[str, Any]) -> Dict[str, Any]:
    """
    페이지 초기화 시 저장된 설정 복원

    Args:
        page_name: 페이지 이름
        defaults: 기본값 딕셔너리 {key: default_value}

    Returns:
        복원된 설정 딕셔너리
    """
    saved_settings = load_page_settings(page_name)
    restored = {}

    for key, default_value in defaults.items():
        if is_excluded_key(key):
            continue

        # 저장된 값 또는 기본값 사용
        value = saved_settings.get(key, default_value)
        restored[key] = value

    return restored


def _get_save_callback(page_name: str, setting_key: str, session_key: str):
    """
    위젯 on_change 콜백용 저장 함수 생성
    """
    def callback():
        if session_key in st.session_state:
            value = st.session_state[session_key]
            save_setting(page_name, setting_key, value)

    return callback


def persistent_selectbox(
    label: str,
    options: List[Any],
    page_name: str,
    setting_key: str,
    default_index: int = 0,
    format_func: callable = None,
    help: str = None,
    **kwargs
) -> Any:
    """
    설정이 자동 저장/복원되는 selectbox

    Args:
        label: 라벨
        options: 선택 옵션 리스트
        page_name: 페이지 이름 (설정 파일용)
        setting_key: 설정 키 이름
        default_index: 기본 선택 인덱스
        format_func: 표시 형식 함수
        help: 도움말 텍스트
        **kwargs: st.selectbox에 전달할 추가 인자

    Returns:
        선택된 값
    """
    session_key = f"_ps_{page_name}_{setting_key}"

    # 저장된 값 로드
    saved_value = load_setting(page_name, setting_key)

    # 저장된 값이 options에 있으면 해당 인덱스 사용
    if saved_value is not None and saved_value in options:
        default_index = options.index(saved_value)
    elif saved_value is not None:
        # 옵션에 없으면 저장된 값 무시
        pass

    # key가 kwargs에 있으면 제거 (session_key 사용)
    kwargs.pop('key', None)
    kwargs.pop('on_change', None)

    result = st.selectbox(
        label,
        options=options,
        index=default_index,
        key=session_key,
        format_func=format_func,
        help=help,
        on_change=_get_save_callback(page_name, setting_key, session_key),
        **kwargs
    )

    return result


def persistent_radio(
    label: str,
    options: List[Any],
    page_name: str,
    setting_key: str,
    default_index: int = 0,
    horizontal: bool = False,
    help: str = None,
    **kwargs
) -> Any:
    """
    설정이 자동 저장/복원되는 radio

    Args:
        label: 라벨
        options: 선택 옵션 리스트
        page_name: 페이지 이름
        setting_key: 설정 키 이름
        default_index: 기본 선택 인덱스
        horizontal: 가로 배치 여부
        help: 도움말 텍스트
        **kwargs: st.radio에 전달할 추가 인자
    """
    session_key = f"_ps_{page_name}_{setting_key}"

    saved_value = load_setting(page_name, setting_key)

    if saved_value is not None and saved_value in options:
        default_index = options.index(saved_value)

    kwargs.pop('key', None)
    kwargs.pop('on_change', None)

    result = st.radio(
        label,
        options=options,
        index=default_index,
        key=session_key,
        horizontal=horizontal,
        help=help,
        on_change=_get_save_callback(page_name, setting_key, session_key),
        **kwargs
    )

    return result


def persistent_checkbox(
    label: str,
    page_name: str,
    setting_key: str,
    default: bool = False,
    help: str = None,
    **kwargs
) -> bool:
    """
    설정이 자동 저장/복원되는 checkbox
    """
    session_key = f"_ps_{page_name}_{setting_key}"

    saved_value = load_setting(page_name, setting_key)

    if saved_value is not None and isinstance(saved_value, bool):
        default = saved_value

    kwargs.pop('key', None)
    kwargs.pop('on_change', None)

    result = st.checkbox(
        label,
        value=default,
        key=session_key,
        help=help,
        on_change=_get_save_callback(page_name, setting_key, session_key),
        **kwargs
    )

    return result


def persistent_slider(
    label: str,
    min_value: Union[int, float],
    max_value: Union[int, float],
    page_name: str,
    setting_key: str,
    default: Union[int, float] = None,
    step: Union[int, float] = None,
    help: str = None,
    **kwargs
) -> Union[int, float]:
    """
    설정이 자동 저장/복원되는 slider
    """
    session_key = f"_ps_{page_name}_{setting_key}"

    saved_value = load_setting(page_name, setting_key)

    if saved_value is not None:
        # 범위 내 값인지 확인
        if min_value <= saved_value <= max_value:
            default = saved_value

    if default is None:
        default = min_value

    kwargs.pop('key', None)
    kwargs.pop('on_change', None)

    result = st.slider(
        label,
        min_value=min_value,
        max_value=max_value,
        value=default,
        step=step,
        key=session_key,
        help=help,
        on_change=_get_save_callback(page_name, setting_key, session_key),
        **kwargs
    )

    return result


def persistent_number_input(
    label: str,
    page_name: str,
    setting_key: str,
    default: Union[int, float] = 0,
    min_value: Union[int, float] = None,
    max_value: Union[int, float] = None,
    step: Union[int, float] = None,
    help: str = None,
    **kwargs
) -> Union[int, float]:
    """
    설정이 자동 저장/복원되는 number_input
    """
    session_key = f"_ps_{page_name}_{setting_key}"

    saved_value = load_setting(page_name, setting_key)

    if saved_value is not None:
        # 타입 및 범위 확인
        if isinstance(saved_value, (int, float)):
            if min_value is not None and saved_value < min_value:
                saved_value = min_value
            if max_value is not None and saved_value > max_value:
                saved_value = max_value
            default = saved_value

    kwargs.pop('key', None)
    kwargs.pop('on_change', None)

    result = st.number_input(
        label,
        value=default,
        min_value=min_value,
        max_value=max_value,
        step=step,
        key=session_key,
        help=help,
        on_change=_get_save_callback(page_name, setting_key, session_key),
        **kwargs
    )

    return result


def persistent_text_input(
    label: str,
    page_name: str,
    setting_key: str,
    default: str = "",
    help: str = None,
    **kwargs
) -> str:
    """
    설정이 자동 저장/복원되는 text_input
    """
    session_key = f"_ps_{page_name}_{setting_key}"

    saved_value = load_setting(page_name, setting_key)

    if saved_value is not None and isinstance(saved_value, str):
        default = saved_value

    kwargs.pop('key', None)
    kwargs.pop('on_change', None)

    result = st.text_input(
        label,
        value=default,
        key=session_key,
        help=help,
        on_change=_get_save_callback(page_name, setting_key, session_key),
        **kwargs
    )

    return result


def persistent_multiselect(
    label: str,
    options: List[Any],
    page_name: str,
    setting_key: str,
    default: List[Any] = None,
    help: str = None,
    **kwargs
) -> List[Any]:
    """
    설정이 자동 저장/복원되는 multiselect
    """
    session_key = f"_ps_{page_name}_{setting_key}"

    saved_value = load_setting(page_name, setting_key)

    if saved_value is not None and isinstance(saved_value, list):
        # 유효한 옵션만 필터링
        default = [v for v in saved_value if v in options]
    elif default is None:
        default = []

    kwargs.pop('key', None)
    kwargs.pop('on_change', None)

    result = st.multiselect(
        label,
        options=options,
        default=default,
        key=session_key,
        help=help,
        on_change=_get_save_callback(page_name, setting_key, session_key),
        **kwargs
    )

    return result


def persistent_toggle(
    label: str,
    page_name: str,
    setting_key: str,
    default: bool = False,
    help: str = None,
    **kwargs
) -> bool:
    """
    설정이 자동 저장/복원되는 toggle
    """
    session_key = f"_ps_{page_name}_{setting_key}"

    saved_value = load_setting(page_name, setting_key)

    if saved_value is not None and isinstance(saved_value, bool):
        default = saved_value

    kwargs.pop('key', None)
    kwargs.pop('on_change', None)

    result = st.toggle(
        label,
        value=default,
        key=session_key,
        help=help,
        on_change=_get_save_callback(page_name, setting_key, session_key),
        **kwargs
    )

    return result


# === 편의 함수 ===

def get_all_settings() -> Dict[str, Dict[str, Any]]:
    """모든 페이지의 설정 반환"""
    all_settings = {}

    if SETTINGS_DIR.exists():
        for filepath in SETTINGS_DIR.glob("*.json"):
            page_name = filepath.stem
            all_settings[page_name] = load_page_settings(page_name)

    return all_settings


def export_settings(export_path: str) -> bool:
    """모든 설정을 단일 파일로 내보내기"""
    try:
        all_settings = get_all_settings()
        data = {
            "exported_at": datetime.now().isoformat(),
            "pages": all_settings
        }

        with open(export_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return True
    except Exception as e:
        print(f"[UserSettings] 설정 내보내기 실패: {e}")
        return False


def import_settings(import_path: str) -> bool:
    """설정 파일 가져오기"""
    try:
        with open(import_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        pages = data.get("pages", {})
        for page_name, settings in pages.items():
            save_page_settings(page_name, settings)

        return True
    except Exception as e:
        print(f"[UserSettings] 설정 가져오기 실패: {e}")
        return False
