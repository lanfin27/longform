# -*- coding: utf-8 -*-
"""
페이지 캐시 최적화 유틸리티 (v1.0)

Streamlit 페이지 로딩 성능 최적화를 위한 헬퍼 함수들

핵심 기능:
1. 안정적인 캐시 키 관리 (mtime 대신 명시적 버전)
2. 페이지 초기화 1회만 실행
3. 탭별 조건부 데이터 로딩
4. 싱글톤 패턴 설정 관리

사용 예:
    # 캐시 버전 가져오기
    cache_version = get_stable_cache_version(project_path)

    # 데이터 로드 (안정적 캐시)
    scenes = load_scenes_with_stable_cache(project_path, cache_version)

    # 캐시 무효화 (데이터 변경 시에만)
    invalidate_project_cache(project_path)
"""

import json
import uuid
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional, Callable

try:
    import streamlit as st
    _HAS_STREAMLIT = True
except ImportError:
    _HAS_STREAMLIT = False


# ============================================================
# 1. 캐시 버전 관리
# ============================================================

_CACHE_VERSION_FILE = ".cache_version"
_DEFAULT_CACHE_VERSION = "v1"


def get_stable_cache_version(project_path: str) -> str:
    """
    안정적인 캐시 버전 키 생성

    mtime 대신 명시적 버전 사용으로 불필요한 캐시 갱신 방지

    Args:
        project_path: 프로젝트 경로

    Returns:
        캐시 버전 문자열 (예: "v1", "v_abc12345")
    """
    try:
        version_file = Path(project_path) / _CACHE_VERSION_FILE

        if version_file.exists():
            return version_file.read_text(encoding='utf-8').strip()

        return _DEFAULT_CACHE_VERSION
    except Exception:
        return _DEFAULT_CACHE_VERSION


def invalidate_project_cache(project_path: str) -> str:
    """
    프로젝트 캐시 명시적 무효화

    데이터 변경 시에만 호출 (이미지 생성, 설정 변경 등)

    Args:
        project_path: 프로젝트 경로

    Returns:
        새 캐시 버전
    """
    try:
        version_file = Path(project_path) / _CACHE_VERSION_FILE
        new_version = f"v_{uuid.uuid4().hex[:8]}"
        version_file.write_text(new_version, encoding='utf-8')
        print(f"[CacheOptimizer] 캐시 무효화: {new_version}")
        return new_version
    except Exception as e:
        print(f"[CacheOptimizer] 캐시 무효화 실패: {e}")
        return _DEFAULT_CACHE_VERSION


def get_session_cache_key(project_path: str, key_name: str) -> str:
    """
    프로젝트별 세션 캐시 키 생성

    Args:
        project_path: 프로젝트 경로
        key_name: 키 이름 (예: "scenes", "gallery", "settings")

    Returns:
        고유 캐시 키
    """
    # 경로를 해시하여 고정된 키 생성
    path_hash = hash(str(project_path)) & 0xFFFFFFFF
    return f"_cache_{key_name}_{path_hash:08x}"


# ============================================================
# 2. 페이지 초기화 관리
# ============================================================

def initialize_page_once(
    page_name: str,
    init_functions: List[Callable] = None,
    force: bool = False
) -> bool:
    """
    페이지 초기화 1회만 실행

    Args:
        page_name: 페이지 고유 이름 (예: "image_generation")
        init_functions: 초기화 함수 목록 (선택)
        force: True면 강제 재초기화

    Returns:
        초기화 수행 여부 (True: 초기화됨, False: 이미 초기화됨)
    """
    if not _HAS_STREAMLIT:
        return False

    init_key = f"_page_initialized_{page_name}"

    # 이미 초기화됐으면 스킵
    if st.session_state.get(init_key, False) and not force:
        return False

    print(f"[PageInit] {page_name} 페이지 초기화 (1회)")

    # 초기화 함수들 실행
    if init_functions:
        for func in init_functions:
            try:
                func()
            except Exception as e:
                print(f"[PageInit] 초기화 함수 오류: {e}")

    # 초기화 완료 플래그
    st.session_state[init_key] = True
    return True


def reset_page_initialization(page_name: str):
    """
    페이지 초기화 리셋

    프로젝트 변경 시 호출

    Args:
        page_name: 페이지 고유 이름
    """
    if not _HAS_STREAMLIT:
        return

    init_key = f"_page_initialized_{page_name}"
    if init_key in st.session_state:
        del st.session_state[init_key]

    print(f"[PageInit] {page_name} 초기화 리셋됨")


def check_project_change(current_project: str, page_name: str = "default") -> bool:
    """
    프로젝트 변경 감지

    Args:
        current_project: 현재 프로젝트 경로
        page_name: 페이지 이름 (초기화 리셋용)

    Returns:
        프로젝트 변경 여부
    """
    if not _HAS_STREAMLIT:
        return False

    last_project_key = f"_last_project_{page_name}"
    last_project = st.session_state.get(last_project_key)

    if str(current_project) != str(last_project):
        print(f"[ProjectChange] 프로젝트 변경: {last_project} → {current_project}")

        st.session_state[last_project_key] = str(current_project)
        reset_page_initialization(page_name)

        return True

    return False


# ============================================================
# 3. 싱글톤 설정 관리
# ============================================================

def get_settings_singleton(
    project_path: str,
    settings_key: str,
    loader_func: Callable[[], Dict]
) -> Dict:
    """
    설정 싱글톤 패턴

    session_state에 캐싱하여 중복 로드 방지

    Args:
        project_path: 프로젝트 경로
        settings_key: 설정 키 (예: "image_generation")
        loader_func: 설정 로드 함수

    Returns:
        설정 딕셔너리
    """
    if not _HAS_STREAMLIT:
        return loader_func()

    cache_key = get_session_cache_key(project_path, f"settings_{settings_key}")

    # 캐시에 있으면 반환
    if cache_key in st.session_state:
        return st.session_state[cache_key]

    # 최초 로드
    print(f"[SettingsSingleton] {settings_key} 설정 로드 (1회)")
    settings = loader_func()

    # 캐시 저장
    st.session_state[cache_key] = settings

    return settings


def update_settings_singleton(
    project_path: str,
    settings_key: str,
    settings: Dict
):
    """
    싱글톤 설정 업데이트

    설정 변경 시 캐시도 동기화

    Args:
        project_path: 프로젝트 경로
        settings_key: 설정 키
        settings: 새 설정 딕셔너리
    """
    if not _HAS_STREAMLIT:
        return

    cache_key = get_session_cache_key(project_path, f"settings_{settings_key}")
    st.session_state[cache_key] = settings


def clear_settings_singleton(project_path: str, settings_key: str):
    """싱글톤 설정 캐시 클리어"""
    if not _HAS_STREAMLIT:
        return

    cache_key = get_session_cache_key(project_path, f"settings_{settings_key}")
    if cache_key in st.session_state:
        del st.session_state[cache_key]


# ============================================================
# 4. 탭별 조건부 로딩
# ============================================================

def get_active_tab(page_name: str) -> Optional[int]:
    """
    현재 활성 탭 가져오기

    Args:
        page_name: 페이지 이름

    Returns:
        활성 탭 인덱스 또는 None
    """
    if not _HAS_STREAMLIT:
        return None

    return st.session_state.get(f"_active_tab_{page_name}")


def set_active_tab(page_name: str, tab_index: int):
    """
    활성 탭 설정

    Args:
        page_name: 페이지 이름
        tab_index: 탭 인덱스
    """
    if not _HAS_STREAMLIT:
        return

    st.session_state[f"_active_tab_{page_name}"] = tab_index


def should_load_tab_data(page_name: str, tab_index: int) -> bool:
    """
    탭 데이터 로드 여부 확인

    현재 탭이 활성화된 경우에만 True 반환

    Args:
        page_name: 페이지 이름
        tab_index: 확인할 탭 인덱스

    Returns:
        데이터 로드 여부
    """
    active = get_active_tab(page_name)

    # 첫 방문 시 (활성 탭 미설정) 기본 탭(0) 데이터 로드
    if active is None:
        return tab_index == 0

    return active == tab_index


# ============================================================
# 5. 스타일 변경 감지 최적화
# ============================================================

def detect_style_change_optimized(page_name: str) -> bool:
    """
    스타일 변경 감지 (최적화 버전)

    실제 변경 시에만 감지 로직 실행

    Args:
        page_name: 페이지 이름

    Returns:
        스타일 변경 여부
    """
    if not _HAS_STREAMLIT:
        return False

    # 현재 스타일 (세션에서)
    current_style = st.session_state.get("selected_style")

    # 마지막 감지된 스타일
    last_key = f"_last_style_{page_name}"
    last_style = st.session_state.get(last_key)

    # 변경 없으면 스킵
    if current_style == last_style:
        return False

    # 변경됐을 때만 처리
    print(f"[StyleOptimizer] 스타일 변경 감지: {last_style} → {current_style}")
    st.session_state[last_key] = current_style

    return True


# ============================================================
# 6. 데이터 캐싱 헬퍼
# ============================================================

def get_cached_data(
    project_path: str,
    data_key: str,
    loader_func: Callable[[], Any],
    cache_version: str = None
) -> Any:
    """
    범용 데이터 캐싱 헬퍼

    세션 상태에 데이터를 캐싱하고, 캐시 버전이 변경되면 갱신

    Args:
        project_path: 프로젝트 경로
        data_key: 데이터 키 (예: "scenes", "gallery")
        loader_func: 데이터 로드 함수
        cache_version: 캐시 버전 (None이면 현재 버전 사용)

    Returns:
        캐싱된 데이터
    """
    if not _HAS_STREAMLIT:
        return loader_func()

    cache_key = get_session_cache_key(project_path, data_key)
    version_key = f"{cache_key}_version"

    if cache_version is None:
        cache_version = get_stable_cache_version(project_path)

    # 캐시 버전 확인
    stored_version = st.session_state.get(version_key)

    # 버전 일치하고 데이터 있으면 캐시 반환
    if stored_version == cache_version and cache_key in st.session_state:
        return st.session_state[cache_key]

    # 캐시 미스: 데이터 로드
    print(f"[CacheHelper] {data_key} 데이터 로드 (버전: {cache_version})")
    data = loader_func()

    # 캐시 저장
    st.session_state[cache_key] = data
    st.session_state[version_key] = cache_version

    return data


def clear_cached_data(project_path: str, data_key: str):
    """캐싱된 데이터 클리어"""
    if not _HAS_STREAMLIT:
        return

    cache_key = get_session_cache_key(project_path, data_key)
    version_key = f"{cache_key}_version"

    if cache_key in st.session_state:
        del st.session_state[cache_key]
    if version_key in st.session_state:
        del st.session_state[version_key]


# ============================================================
# 7. 갤러리 캐시 최적화
# ============================================================

def clear_gallery_cache_optimized(project_path: str):
    """
    갤러리 캐시만 무효화 (전체 캐시 무효화 대신)

    새 이미지 생성 시 호출
    """
    clear_cached_data(project_path, "gallery")
    print(f"[GalleryCache] 갤러리 캐시만 무효화")


# ============================================================
# 8. 통합 초기화 함수
# ============================================================

def optimize_page_load(
    page_name: str,
    project_path: str,
    enable_style_check: bool = True
) -> Dict[str, Any]:
    """
    페이지 로딩 최적화 통합 함수

    모든 최적화 로직을 한 번에 적용

    Args:
        page_name: 페이지 이름
        project_path: 프로젝트 경로
        enable_style_check: 스타일 변경 감지 활성화

    Returns:
        최적화 상태 정보
    """
    result = {
        "project_changed": False,
        "style_changed": False,
        "initialized": False,
        "cache_version": None
    }

    # 1. 프로젝트 변경 감지
    result["project_changed"] = check_project_change(project_path, page_name)

    # 2. 캐시 버전 가져오기
    result["cache_version"] = get_stable_cache_version(project_path)

    # 3. 페이지 초기화 (1회만)
    result["initialized"] = initialize_page_once(page_name)

    # 4. 스타일 변경 감지 (선택적)
    if enable_style_check:
        result["style_changed"] = detect_style_change_optimized(page_name)

    return result
