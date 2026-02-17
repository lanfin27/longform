# -*- coding: utf-8 -*-
"""
Step 1 한글 텍스트 생성 설정 관리자 (v1.0)

프로젝트-영상별로 설정 저장/로드
저장 경로: {video_path}/settings/step1_settings.json
"""

import os
import json
from typing import Dict, Any, Optional
from pathlib import Path


class Step1SettingsManager:
    """
    Step 1 한글 텍스트 생성 설정 관리자
    프로젝트-영상별로 설정 저장/로드
    """

    SETTINGS_FILENAME = "step1_settings.json"

    # 기본값 정의
    DEFAULT_SETTINGS = {
        "generation_model": "gemini_nano_banana",  # gemini_nano_banana 또는 gemini_nano_banana_pro
        "reference_image": "기존 이미지 사용",  # "기존 이미지 사용" 또는 "없음"
        "include_character_reference": True,
        "processing_mode": "batch",  # batch 또는 sequential
        "max_concurrent": 4,
    }

    def __init__(self, video_path: str):
        """
        Args:
            video_path: 영상 폴더 경로
        """
        self.video_path = str(video_path)
        self.settings_dir = os.path.join(self.video_path, "settings")
        self.settings_path = os.path.join(self.settings_dir, self.SETTINGS_FILENAME)

        # 설정 디렉토리 생성
        os.makedirs(self.settings_dir, exist_ok=True)

    def load(self) -> Dict[str, Any]:
        """
        설정 로드 (없으면 기본값 반환)
        """
        if os.path.exists(self.settings_path):
            try:
                with open(self.settings_path, 'r', encoding='utf-8') as f:
                    saved_settings = json.load(f)

                # 기본값과 병합 (새 필드 추가 대응)
                settings = {**self.DEFAULT_SETTINGS, **saved_settings}

                print(f"[Step1Settings] ✅ 설정 로드됨: {Path(self.settings_path).name}")
                print(f"[Step1Settings]    생성 모델: {settings.get('generation_model')}")

                return settings

            except Exception as e:
                print(f"[Step1Settings] ⚠️ 설정 로드 실패, 기본값 사용: {e}")
                return self.DEFAULT_SETTINGS.copy()
        else:
            print(f"[Step1Settings] ℹ️ 설정 파일 없음, 기본값 사용")
            return self.DEFAULT_SETTINGS.copy()

    def save(self, settings: Dict[str, Any]) -> bool:
        """
        설정 저장
        """
        try:
            with open(self.settings_path, 'w', encoding='utf-8') as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)

            print(f"[Step1Settings] ✅ 설정 저장됨: {Path(self.settings_path).name}")
            print(f"[Step1Settings]    생성 모델: {settings.get('generation_model')}")

            return True

        except Exception as e:
            print(f"[Step1Settings] ❌ 설정 저장 실패: {e}")
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

    def update(self, updates: Dict[str, Any]) -> bool:
        """여러 설정값 한번에 업데이트"""
        settings = self.load()
        settings.update(updates)
        return self.save(settings)


# 싱글톤 캐시
_settings_managers: Dict[str, Step1SettingsManager] = {}


def get_step1_settings_manager(video_path: str) -> Step1SettingsManager:
    """Step1 설정 매니저 인스턴스 가져오기"""
    video_path_str = str(video_path)
    if video_path_str not in _settings_managers:
        _settings_managers[video_path_str] = Step1SettingsManager(video_path_str)
    return _settings_managers[video_path_str]


def load_step1_settings(video_path: str) -> Dict[str, Any]:
    """Step1 설정 로드 (간편 함수)"""
    manager = get_step1_settings_manager(video_path)
    return manager.load()


def save_step1_settings(video_path: str, settings: Dict[str, Any]) -> bool:
    """Step1 설정 저장 (간편 함수)"""
    manager = get_step1_settings_manager(video_path)
    return manager.save(settings)


def get_step1_setting(video_path: str, key: str, default: Any = None) -> Any:
    """특정 Step1 설정값 가져오기 (간편 함수)"""
    manager = get_step1_settings_manager(video_path)
    return manager.get(key, default)


def set_step1_setting(video_path: str, key: str, value: Any) -> bool:
    """특정 Step1 설정값 저장 (간편 함수)"""
    manager = get_step1_settings_manager(video_path)
    return manager.set(key, value)
