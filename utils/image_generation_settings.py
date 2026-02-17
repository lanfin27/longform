# -*- coding: utf-8 -*-
"""
utils/image_generation_settings.py

프로젝트별 이미지 생성 설정 관리 (v1.1)

v1.1 변경사항:
- ⭐ 싱글톤 패턴 적용 (중복 로드 방지)
- ⭐ session_state 캐싱으로 성능 최적화
- ⭐ 로깅 중복 제거

채널/영상별로 마지막 사용한 설정을 저장하고 로드
- 배경 스타일
- 프롬프트 유형
- 캐릭터 합성 옵션
- 스타일 모드
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

try:
    import streamlit as st
    _HAS_STREAMLIT = True
except ImportError:
    _HAS_STREAMLIT = False


# ⭐ v1.1: 싱글톤 캐시 키
_SETTINGS_CACHE_PREFIX = "_image_settings_cache_"


def _get_settings_cache_key(video_path: str) -> str:
    """설정 캐시 키 생성"""
    path_hash = hash(str(video_path)) & 0xFFFFFFFF
    return f"{_SETTINGS_CACHE_PREFIX}{path_hash:08x}"


class ImageGenerationSettings:
    """
    이미지 생성 설정 관리 클래스

    채널/영상별로 마지막 사용한 설정을 저장하고 로드
    """

    SETTINGS_FILENAME = "image_generation_settings.json"

    def __init__(self, video_path: str):
        """
        Args:
            video_path: 영상 프로젝트 경로
                예: C:\\Users\\...\\data\\projects\\시니어\\videos\\test5
        """
        self.video_path = Path(video_path) if video_path else None
        if self.video_path:
            self.settings_dir = self.video_path / "settings"
            self.settings_file = self.settings_dir / self.SETTINGS_FILENAME
        else:
            self.settings_dir = None
            self.settings_file = None

    def load(self) -> Dict[str, Any]:
        """
        저장된 설정 로드 (⭐ v1.1: 싱글톤 캐싱)

        session_state에 캐싱하여 중복 로드 방지

        Returns:
            설정 딕셔너리 또는 빈 딕셔너리
        """
        if not self.settings_file:
            return {}

        # ⭐ v1.1: 싱글톤 캐시 확인
        if _HAS_STREAMLIT:
            cache_key = _get_settings_cache_key(str(self.video_path))
            if cache_key in st.session_state:
                # 캐시에서 반환 (로그 출력 안함)
                return st.session_state[cache_key]

        # 캐시 미스: 파일에서 로드
        if self.settings_file.exists():
            try:
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                print(f"[ImageSettings] 설정 로드됨 (1회): {self.settings_file.name}")

                # ⭐ v1.1: 캐시 저장
                if _HAS_STREAMLIT:
                    st.session_state[cache_key] = settings

                return settings
            except Exception as e:
                print(f"[ImageSettings] 설정 로드 실패: {e}")
                return {}

        return {}

    def save(self, settings: Dict[str, Any]) -> bool:
        """
        설정 저장 (⭐ v1.1: 캐시 동기화)

        Args:
            settings: 저장할 설정 딕셔너리

        Returns:
            성공 여부
        """
        if not self.settings_dir:
            return False

        try:
            # 설정 디렉토리 생성
            self.settings_dir.mkdir(parents=True, exist_ok=True)

            # 타임스탬프 추가
            settings["last_updated"] = datetime.now().isoformat()

            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)

            # ⭐ v1.1: 캐시 업데이트
            if _HAS_STREAMLIT:
                cache_key = _get_settings_cache_key(str(self.video_path))
                st.session_state[cache_key] = settings

            print(f"[ImageSettings] 설정 저장됨")
            return True

        except Exception as e:
            print(f"[ImageSettings] 설정 저장 실패: {e}")
            return False

    def get(self, key: str, default: Any = None) -> Any:
        """특정 설정값 가져오기"""
        settings = self.load()
        return settings.get(key, default)

    def set(self, key: str, value: Any) -> bool:
        """특정 설정값 저장"""
        settings = self.load()
        settings[key] = value
        return self.save(settings)

    # ========== 배경 스타일 전용 메서드 ==========

    def get_background_style(self, default: str = None) -> Optional[str]:
        """
        마지막 사용한 배경 스타일 가져오기

        Returns:
            배경 스타일 ID 또는 None
        """
        return self.get("background_style", default)

    def set_background_style(self, style_id: str) -> bool:
        """
        배경 스타일 저장

        Args:
            style_id: 스타일 ID (예: "jazz_video_tone")
        """
        print(f"[ImageSettings] 배경 스타일 저장: {style_id}")
        return self.set("background_style", style_id)

    # ========== 씬 합성 스타일 전용 메서드 ==========

    def get_composite_style(self, default: str = None) -> Optional[str]:
        """마지막 사용한 씬 합성 스타일 가져오기"""
        return self.get("composite_style", default)

    def set_composite_style(self, style_name: str) -> bool:
        """씬 합성 스타일 저장"""
        print(f"[ImageSettings] 씬 합성 스타일 저장: {style_name}")
        return self.set("composite_style", style_name)

    # ========== 기타 설정 메서드 ==========

    def get_prompt_type(self, default: str = "full_prompt") -> str:
        """프롬프트 유형 가져오기"""
        return self.get("prompt_type", default)

    def set_prompt_type(self, prompt_type: str) -> bool:
        """프롬프트 유형 저장"""
        return self.set("prompt_type", prompt_type)

    def get_character_composite(self, default: str = "none") -> str:
        """캐릭터 합성 옵션 가져오기"""
        return self.get("character_composite", default)

    def set_character_composite(self, option: str) -> bool:
        """캐릭터 합성 옵션 저장"""
        return self.set("character_composite", option)

    def get_style_mode(self, default: str = None) -> str:
        """스타일 모드 가져오기"""
        return self.get("style_mode", default)

    def set_style_mode(self, mode: str) -> bool:
        """스타일 모드 저장"""
        return self.set("style_mode", mode)


# ========== 헬퍼 함수 ==========

def get_image_settings(video_path: str) -> ImageGenerationSettings:
    """이미지 생성 설정 인스턴스 가져오기"""
    return ImageGenerationSettings(video_path)


def clear_image_settings_cache(video_path: str):
    """
    이미지 설정 캐시 클리어 (v1.1)

    프로젝트 변경 시 호출
    """
    if _HAS_STREAMLIT:
        cache_key = _get_settings_cache_key(str(video_path))
        if cache_key in st.session_state:
            del st.session_state[cache_key]
            print(f"[ImageSettings] 캐시 클리어됨")


def load_last_background_style(video_path: str, default: str = None) -> Optional[str]:
    """마지막 사용한 배경 스타일 로드 (간편 함수)"""
    settings = ImageGenerationSettings(video_path)
    return settings.get_background_style(default)


def save_background_style(video_path: str, style_id: str) -> bool:
    """배경 스타일 저장 (간편 함수)"""
    settings = ImageGenerationSettings(video_path)
    return settings.set_background_style(style_id)


def load_last_composite_style(video_path: str, default: str = None) -> Optional[str]:
    """마지막 사용한 씬 합성 스타일 로드 (간편 함수)"""
    settings = ImageGenerationSettings(video_path)
    return settings.get_composite_style(default)


def save_composite_style(video_path: str, style_name: str) -> bool:
    """씬 합성 스타일 저장 (간편 함수)"""
    settings = ImageGenerationSettings(video_path)
    return settings.set_composite_style(style_name)


# ========== Streamlit 위젯 래퍼 (프로젝트별) ==========

def project_persistent_selectbox(
    label: str,
    options: List,
    video_path: str,
    setting_key: str,
    default_index: int = 0,
    format_func=None,
    **kwargs
) -> Any:
    """
    프로젝트별 설정이 자동 저장되는 selectbox (⭐ v1.1: 로깅 최적화)

    사용 예:
        style = project_persistent_selectbox(
            "배경 스타일",
            style_ids,
            video_path=str(project_path),
            setting_key="background_style"
        )
    """
    if not _HAS_STREAMLIT:
        return options[default_index] if options else None

    settings = ImageGenerationSettings(video_path)

    # 저장된 값 로드 (캐싱된 값 사용, 로그 없음)
    saved_value = settings.get(setting_key)

    # 저장된 값이 옵션에 있으면 해당 인덱스 사용
    if saved_value in options:
        default_index = options.index(saved_value)
        # ⭐ v1.1: 중복 로그 제거 (필요시 활성화)
        # print(f"[ImageSettings] '{setting_key}' 로드됨: {saved_value}")
    elif default_index >= len(options):
        default_index = 0

    # selectbox 렌더링
    if format_func:
        selected = st.selectbox(label, options, index=default_index, format_func=format_func, **kwargs)
    else:
        selected = st.selectbox(label, options, index=default_index, **kwargs)

    # 값 변경 시 자동 저장 (실제 변경 시에만 로그)
    if selected != saved_value:
        settings.set(setting_key, selected)
        # 변경 시에만 로그 출력
        print(f"[ImageSettings] '{setting_key}' 변경: {saved_value} → {selected}")

    return selected
