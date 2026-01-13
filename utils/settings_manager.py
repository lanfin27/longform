# -*- coding: utf-8 -*-
"""
API 설정 영구 저장 관리자
- JSON 파일로 설정 저장/로드
- 페이지별 설정 분리 관리
- 자동 저장 기능
"""

import json
from pathlib import Path
from typing import Any, Optional, List
import streamlit as st

# 설정 파일 경로
SETTINGS_DIR = Path(__file__).parent.parent / "data" / "settings"
API_PREFERENCES_FILE = SETTINGS_DIR / "api_preferences.json"

# 기본 설정값 (초기화용)
DEFAULT_SETTINGS = {
    "image_generation": {
        "api": "Google ImageFX",
        "model": "imagen-4.0-generate-preview-05-20",
        "resolution": "1280x720",
        "style": "animation",
        "api_interval": 1.0,
        "celebrity_replacement": True,
        "celebrity_ai_model": "gemini-2.0-flash-exp",
        "rembg_enabled": False,
        "auto_save_storyboard": False
    },
    "video_generation": {
        "platform": "minimax",
        "model": "video-01",
        "duration": 4,
        "resolution": "720p",
        "camera_motion": False,
        "slow_motion": False,
        "loop": False
    },
    "channel_trend": {
        "max_results": 50,
        "sort_by": "viewCount",
        "date_range": "month"
    },
    "video_research": {
        "max_results": 30,
        "sort_by": "viewCount",
        "video_type": "all",
        "region": "KR"
    },
    "scene_analysis": {
        "ai_provider": "google",
        "ai_model": "gemini-2.0-flash-exp",
        "language": "ko"
    }
}


class SettingsManager:
    """API 설정 영구 저장 관리자"""

    _instance = None
    _settings = None

    def __new__(cls):
        """싱글톤 패턴"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self._load_settings()
            self._initialized = True

    def _ensure_settings_dir(self):
        """설정 디렉토리 생성"""
        SETTINGS_DIR.mkdir(parents=True, exist_ok=True)

    def _load_settings(self):
        """파일에서 설정 로드"""
        self._ensure_settings_dir()

        if API_PREFERENCES_FILE.exists():
            try:
                with open(API_PREFERENCES_FILE, 'r', encoding='utf-8') as f:
                    self._settings = json.load(f)
                print(f"[Settings] 설정 로드됨 (최초 1회)", flush=True)
            except Exception as e:
                print(f"[Settings] 설정 로드 실패, 기본값 사용: {e}", flush=True)
                self._settings = self._deep_copy_defaults()
        else:
            print("[Settings] 설정 파일 없음, 기본값으로 생성", flush=True)
            self._settings = self._deep_copy_defaults()
            self._save_settings()

    def _deep_copy_defaults(self) -> dict:
        """기본 설정의 깊은 복사본 반환"""
        return json.loads(json.dumps(DEFAULT_SETTINGS))

    def _save_settings(self):
        """설정을 파일에 저장"""
        self._ensure_settings_dir()

        try:
            with open(API_PREFERENCES_FILE, 'w', encoding='utf-8') as f:
                json.dump(self._settings, f, ensure_ascii=False, indent=2)
            # print(f"[Settings] 설정 저장됨", flush=True)  # 빈번한 저장은 로그 생략
        except Exception as e:
            print(f"[Settings] 설정 저장 실패: {e}", flush=True)

    def get(self, page: str, key: str, default: Any = None) -> Any:
        """
        특정 페이지의 설정값 가져오기

        Args:
            page: 페이지 식별자 (예: "image_generation")
            key: 설정 키 (예: "api")
            default: 기본값

        Returns:
            저장된 설정값 또는 기본값
        """
        if page not in self._settings:
            self._settings[page] = DEFAULT_SETTINGS.get(page, {}).copy()

        # 기본값이 없으면 DEFAULT_SETTINGS에서 가져오기
        if default is None and page in DEFAULT_SETTINGS:
            default = DEFAULT_SETTINGS[page].get(key)

        return self._settings[page].get(key, default)

    def set(self, page: str, key: str, value: Any, auto_save: bool = True):
        """
        특정 페이지의 설정값 저장

        Args:
            page: 페이지 식별자
            key: 설정 키
            value: 저장할 값
            auto_save: 즉시 파일에 저장할지 여부
        """
        if page not in self._settings:
            self._settings[page] = {}

        # 값이 변경된 경우에만 저장
        if self._settings[page].get(key) != value:
            self._settings[page][key] = value
            # print(f"[Settings] {page}.{key} = {value}", flush=True)  # 빈번한 설정은 로그 생략

            if auto_save:
                self._save_settings()

    def get_page_settings(self, page: str) -> dict:
        """페이지의 모든 설정 가져오기"""
        if page not in self._settings:
            self._settings[page] = DEFAULT_SETTINGS.get(page, {}).copy()
        return self._settings[page].copy()

    def set_page_settings(self, page: str, settings: dict, auto_save: bool = True):
        """페이지의 모든 설정 한 번에 저장"""
        self._settings[page] = settings
        if auto_save:
            self._save_settings()

    def reset_page(self, page: str):
        """페이지 설정을 기본값으로 초기화"""
        if page in DEFAULT_SETTINGS:
            self._settings[page] = DEFAULT_SETTINGS[page].copy()
            self._save_settings()
            print(f"[Settings] {page} 설정 초기화됨", flush=True)

    def reset_all(self):
        """모든 설정을 기본값으로 초기화"""
        self._settings = self._deep_copy_defaults()
        self._save_settings()
        print("[Settings] 모든 설정 초기화됨", flush=True)


# 전역 인스턴스 가져오기 함수
def get_settings_manager() -> SettingsManager:
    """SettingsManager 싱글톤 인스턴스 반환"""
    return SettingsManager()


# ========== 편의 함수 ==========

def get_setting(page: str, key: str, default: Any = None) -> Any:
    """설정값 가져오기 (단축 함수)"""
    return get_settings_manager().get(page, key, default)


def set_setting(page: str, key: str, value: Any):
    """설정값 저장하기 (단축 함수)"""
    get_settings_manager().set(page, key, value)


def get_page_settings(page: str) -> dict:
    """페이지 전체 설정 가져오기"""
    return get_settings_manager().get_page_settings(page)


# ========== Streamlit 위젯 래퍼 ==========

def persistent_selectbox(
    label: str,
    options: List,
    page: str,
    setting_key: str,
    default_index: int = 0,
    format_func=None,
    **kwargs
) -> Any:
    """
    설정이 자동 저장되는 selectbox

    사용 예:
        api = persistent_selectbox(
            "이미지 생성 API",
            ["Google ImageFX", "DALL-E 3", "Midjourney"],
            page="image_generation",
            setting_key="api"
        )
    """
    manager = get_settings_manager()

    # 저장된 값 로드
    saved_value = manager.get(page, setting_key)

    # 저장된 값이 옵션에 있으면 해당 인덱스 사용
    if saved_value in options:
        default_index = options.index(saved_value)
    elif default_index >= len(options):
        default_index = 0

    # selectbox 렌더링
    if format_func:
        selected = st.selectbox(label, options, index=default_index, format_func=format_func, **kwargs)
    else:
        selected = st.selectbox(label, options, index=default_index, **kwargs)

    # 값 변경 시 자동 저장
    if selected != saved_value:
        manager.set(page, setting_key, selected)

    return selected


def persistent_radio(
    label: str,
    options: List,
    page: str,
    setting_key: str,
    default_index: int = 0,
    format_func=None,
    **kwargs
) -> Any:
    """설정이 자동 저장되는 radio"""
    manager = get_settings_manager()

    saved_value = manager.get(page, setting_key)

    if saved_value in options:
        default_index = options.index(saved_value)
    elif default_index >= len(options):
        default_index = 0

    if format_func:
        selected = st.radio(label, options, index=default_index, format_func=format_func, **kwargs)
    else:
        selected = st.radio(label, options, index=default_index, **kwargs)

    if selected != saved_value:
        manager.set(page, setting_key, selected)

    return selected


def persistent_slider(
    label: str,
    min_value: float,
    max_value: float,
    page: str,
    setting_key: str,
    default_value: float = None,
    **kwargs
) -> float:
    """설정이 자동 저장되는 slider"""
    manager = get_settings_manager()
    saved_value = manager.get(page, setting_key, default_value or min_value)

    # 범위 내로 조정
    if isinstance(saved_value, (int, float)):
        saved_value = max(min_value, min(max_value, saved_value))
    else:
        saved_value = default_value or min_value

    value = st.slider(label, min_value, max_value, saved_value, **kwargs)

    if value != saved_value:
        manager.set(page, setting_key, value)

    return value


def persistent_checkbox(
    label: str,
    page: str,
    setting_key: str,
    default_value: bool = False,
    **kwargs
) -> bool:
    """설정이 자동 저장되는 checkbox"""
    manager = get_settings_manager()
    saved_value = manager.get(page, setting_key, default_value)

    # bool 타입 보장
    if not isinstance(saved_value, bool):
        saved_value = default_value

    value = st.checkbox(label, value=saved_value, **kwargs)

    if value != saved_value:
        manager.set(page, setting_key, value)

    return value


def persistent_number_input(
    label: str,
    page: str,
    setting_key: str,
    min_value: float = None,
    max_value: float = None,
    default_value: float = 0,
    **kwargs
) -> float:
    """설정이 자동 저장되는 number_input"""
    manager = get_settings_manager()
    saved_value = manager.get(page, setting_key, default_value)

    # 숫자 타입 보장
    if not isinstance(saved_value, (int, float)):
        saved_value = default_value

    # 범위 내로 조정
    if min_value is not None:
        saved_value = max(min_value, saved_value)
    if max_value is not None:
        saved_value = min(max_value, saved_value)

    value = st.number_input(
        label,
        min_value=min_value,
        max_value=max_value,
        value=saved_value,
        **kwargs
    )

    if value != saved_value:
        manager.set(page, setting_key, value)

    return value


def persistent_text_input(
    label: str,
    page: str,
    setting_key: str,
    default_value: str = "",
    **kwargs
) -> str:
    """설정이 자동 저장되는 text_input"""
    manager = get_settings_manager()
    saved_value = manager.get(page, setting_key, default_value)

    # 문자열 타입 보장
    if not isinstance(saved_value, str):
        saved_value = default_value

    value = st.text_input(label, value=saved_value, **kwargs)

    if value != saved_value:
        manager.set(page, setting_key, value)

    return value


def render_settings_management_ui(page_id: str, page_name: str = "이 페이지"):
    """
    설정 관리 UI 렌더링 (각 페이지 하단에 추가용)

    Args:
        page_id: 페이지 식별자 (예: "image_generation")
        page_name: 표시용 페이지 이름 (예: "이미지 생성")
    """
    with st.expander("⚙️ 설정 관리"):
        col1, col2 = st.columns(2)

        with col1:
            if st.button(f"🔄 {page_name} 설정 초기화", key=f"reset_{page_id}"):
                manager = get_settings_manager()
                manager.reset_page(page_id)
                st.success("설정이 초기화되었습니다.")
                st.rerun()

        with col2:
            if st.button("📋 현재 설정 보기", key=f"show_{page_id}"):
                current = get_page_settings(page_id)
                st.json(current)
