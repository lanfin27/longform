# -*- coding: utf-8 -*-
"""
세션 상태 관리자 (v1.0)

기능:
- TTL 기반 캐싱
- 중복 호출 방지
- 페이지/탭 초기화 추적
- 디버그 모드 제어

사용법:
    from utils.state_manager import StateManager, run_once_per_session

    # 캐시된 데이터 가져오기 (5분 TTL)
    data = StateManager.get_cached(
        key="my_data",
        loader_func=load_from_file,
        ttl_seconds=300,
        filepath="data.json"
    )

    # 세션당 1회만 실행
    @run_once_per_session("init_api")
    def init_api_config():
        return load_api_config()
"""

import os
import functools
from datetime import datetime
from typing import Any, Callable, Optional
import streamlit as st


# 디버그 모드 (환경변수 또는 False)
DEBUG_MODE = os.getenv("DEBUG", "false").lower() == "true"


def debug_log(message: str):
    """디버그 모드에서만 출력"""
    if DEBUG_MODE:
        print(message)


class StateManager:
    """세션 상태 관리자 - 캐싱 및 로딩 최적화"""

    # 캐시 프리픽스
    CACHE_PREFIX = "_sm_cache_"
    TIME_PREFIX = "_sm_time_"
    INIT_PREFIX = "_sm_init_"
    CALL_COUNT_PREFIX = "_sm_calls_"

    @staticmethod
    def get_cached(
        key: str,
        loader_func: Callable,
        ttl_seconds: int = 300,
        *args,
        **kwargs
    ) -> Any:
        """
        캐시된 데이터 가져오기 - TTL 지원

        Args:
            key: 캐시 키
            loader_func: 데이터 로드 함수
            ttl_seconds: 캐시 유효 시간 (초, 기본 5분)
            *args, **kwargs: loader_func에 전달할 인자

        Returns:
            캐시된 데이터 또는 새로 로드한 데이터
        """
        cache_key = f"{StateManager.CACHE_PREFIX}{key}"
        time_key = f"{StateManager.TIME_PREFIX}{key}"

        # 캐시 확인
        if cache_key in st.session_state:
            cached_time = st.session_state.get(time_key)
            if cached_time:
                elapsed = (datetime.now() - cached_time).total_seconds()
                if elapsed < ttl_seconds:
                    debug_log(f"[StateManager] Cache hit: {key} ({elapsed:.1f}s ago)")
                    return st.session_state[cache_key]

        # 캐시 미스 - 로드 실행
        debug_log(f"[StateManager] Cache miss: {key} - loading...")
        data = loader_func(*args, **kwargs)

        # 캐시 저장
        st.session_state[cache_key] = data
        st.session_state[time_key] = datetime.now()

        return data

    @staticmethod
    def invalidate_cache(key: str):
        """캐시 무효화"""
        cache_key = f"{StateManager.CACHE_PREFIX}{key}"
        time_key = f"{StateManager.TIME_PREFIX}{key}"

        removed = False
        if cache_key in st.session_state:
            del st.session_state[cache_key]
            removed = True
        if time_key in st.session_state:
            del st.session_state[time_key]
            removed = True

        if removed:
            debug_log(f"[StateManager] Cache invalidated: {key}")

    @staticmethod
    def invalidate_all_caches():
        """모든 캐시 무효화"""
        keys_to_remove = [
            k for k in st.session_state.keys()
            if k.startswith(StateManager.CACHE_PREFIX) or
               k.startswith(StateManager.TIME_PREFIX)
        ]
        for k in keys_to_remove:
            del st.session_state[k]

        if keys_to_remove:
            debug_log(f"[StateManager] All caches invalidated ({len(keys_to_remove)//2} items)")

    @staticmethod
    def is_initialized(key: str) -> bool:
        """초기화 여부 확인"""
        return st.session_state.get(f"{StateManager.INIT_PREFIX}{key}", False)

    @staticmethod
    def mark_initialized(key: str):
        """초기화 완료 표시"""
        st.session_state[f"{StateManager.INIT_PREFIX}{key}"] = True
        debug_log(f"[StateManager] Marked initialized: {key}")

    @staticmethod
    def reset_initialized(key: str):
        """초기화 상태 리셋"""
        init_key = f"{StateManager.INIT_PREFIX}{key}"
        if init_key in st.session_state:
            del st.session_state[init_key]
            debug_log(f"[StateManager] Reset initialized: {key}")

    @staticmethod
    def get_call_count(key: str) -> int:
        """함수 호출 횟수 조회"""
        return st.session_state.get(f"{StateManager.CALL_COUNT_PREFIX}{key}", 0)

    @staticmethod
    def increment_call_count(key: str) -> int:
        """함수 호출 횟수 증가"""
        count_key = f"{StateManager.CALL_COUNT_PREFIX}{key}"
        count = st.session_state.get(count_key, 0) + 1
        st.session_state[count_key] = count
        return count

    @staticmethod
    def should_skip_call(key: str, max_calls_per_session: int = 1) -> bool:
        """
        호출 스킵 여부 확인 (중복 호출 방지)

        Args:
            key: 호출 키
            max_calls_per_session: 세션당 최대 호출 횟수

        Returns:
            True면 스킵해야 함
        """
        count = StateManager.get_call_count(key)
        if count >= max_calls_per_session:
            debug_log(f"[StateManager] Skipping call: {key} (already called {count} times)")
            return True
        return False


def run_once_per_session(key: str):
    """
    세션당 1회만 실행되는 데코레이터

    Args:
        key: 고유 식별 키

    Usage:
        @run_once_per_session("load_api_configs")
        def load_api_configurations():
            print("[Config] API 설정 로드...")
            return load_from_file("api_preferences.json")
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            cache_key = f"_run_once_{key}"

            if cache_key not in st.session_state:
                debug_log(f"[RunOnce] Executing: {key}")
                result = func(*args, **kwargs)
                st.session_state[cache_key] = result
                return result

            debug_log(f"[RunOnce] Skipped (cached): {key}")
            return st.session_state[cache_key]
        return wrapper
    return decorator


def run_once_per_page(key: str):
    """
    페이지 렌더링당 1회만 실행되는 데코레이터

    Streamlit은 페이지마다 rerun되므로, 페이지 전환 시에는 다시 실행됨
    같은 페이지 내 여러 번 호출 방지용

    Args:
        key: 고유 식별 키
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # 현재 페이지 식별 (script_run_ctx 또는 페이지 경로)
            page_key = f"_page_run_{key}"

            # 이미 이번 렌더링에서 실행됨
            if st.session_state.get(page_key):
                debug_log(f"[PageOnce] Skipped: {key}")
                return st.session_state.get(f"_page_result_{key}")

            # 실행
            debug_log(f"[PageOnce] Executing: {key}")
            result = func(*args, **kwargs)

            # 결과 저장 (다음 rerun 전까지 유지)
            st.session_state[page_key] = True
            st.session_state[f"_page_result_{key}"] = result

            return result
        return wrapper
    return decorator


# ============================================================
# 편의 함수
# ============================================================

def get_cached_scenes(project_path: str, force: bool = False):
    """
    씬 데이터 캐시 로드 (편의 함수)

    Args:
        project_path: 프로젝트 경로
        force: True면 캐시 무시

    Returns:
        씬 데이터 리스트
    """
    from utils.scene_character_loader import load_scenes_data

    if force:
        StateManager.invalidate_cache(f"scenes_{project_path}")

    return StateManager.get_cached(
        key=f"scenes_{project_path}",
        loader_func=load_scenes_data,
        ttl_seconds=300,  # 5분
        project_path=project_path
    )


def get_cached_settings(settings_path: str = None):
    """
    설정 데이터 캐시 로드 (편의 함수)

    Args:
        settings_path: 설정 파일 경로

    Returns:
        설정 딕셔너리
    """
    import json
    from pathlib import Path

    if settings_path is None:
        settings_path = "config/settings.json"

    def load_settings():
        path = Path(settings_path)
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    return StateManager.get_cached(
        key="app_settings",
        loader_func=load_settings,
        ttl_seconds=600  # 10분
    )


def invalidate_project_caches(project_path: str = None):
    """
    프로젝트 관련 모든 캐시 무효화

    Args:
        project_path: 프로젝트 경로 (None이면 모든 프로젝트 캐시 무효화)
    """
    if project_path:
        StateManager.invalidate_cache(f"scenes_{project_path}")
        StateManager.invalidate_cache(f"characters_{project_path}")
        StateManager.invalidate_cache(f"images_{project_path}")
        debug_log(f"[StateManager] Project caches invalidated: {project_path}")
    else:
        # 모든 프로젝트 캐시 무효화
        keys_to_remove = [
            k for k in st.session_state.keys()
            if k.startswith(StateManager.CACHE_PREFIX) and
               ("scenes_" in k or "characters_" in k or "images_" in k)
        ]
        for k in keys_to_remove:
            del st.session_state[k]
        debug_log(f"[StateManager] All project caches invalidated")
