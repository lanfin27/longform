# -*- coding: utf-8 -*-
"""
한글 씬 선택 상태 관리 모듈 (v1.0)

자동 선택(랜덤/AI)과 수동 추가/제거를 분리 관리
"""

import streamlit as st
from typing import Set, Dict, Optional


def init_korean_scene_state():
    """한글 씬 선택 상태 초기화"""

    if 'korean_scene_state' not in st.session_state:
        st.session_state.korean_scene_state = {
            'auto_selected': set(),      # 랜덤/AI로 선택된 씬 ID
            'manual_added': set(),        # 사용자가 수동 추가한 씬 ID
            'manual_removed': set(),      # 사용자가 수동 제거한 씬 ID (자동 선택에서)
            'selection_method': 'random', # 'random' | 'ai' | 'manual'
        }


def get_all_selected_korean_scenes() -> Set[int]:
    """모든 선택된 한글 씬 ID 반환 (자동 + 수동)"""

    init_korean_scene_state()
    state = st.session_state.korean_scene_state

    # 자동 선택 - 수동 제거 + 수동 추가
    selected = state['auto_selected'] - state['manual_removed']
    selected = selected | state['manual_added']

    return selected


def get_auto_selected_scenes() -> Set[int]:
    """자동 선택된 씬만 반환 (수동 제거 제외)"""
    init_korean_scene_state()
    state = st.session_state.korean_scene_state
    return state['auto_selected'] - state['manual_removed']


def get_manual_added_scenes() -> Set[int]:
    """수동 추가된 씬만 반환"""
    init_korean_scene_state()
    return st.session_state.korean_scene_state['manual_added'].copy()


def get_auto_selected_raw() -> Set[int]:
    """원본 자동 선택 씬 반환 (수동 제거 포함)"""
    init_korean_scene_state()
    return st.session_state.korean_scene_state['auto_selected'].copy()


def set_auto_selected_scenes(scene_ids: Set[int], method: str = 'random'):
    """자동 선택 씬 설정 (랜덤/AI 결과)"""

    init_korean_scene_state()
    st.session_state.korean_scene_state['auto_selected'] = set(scene_ids)
    st.session_state.korean_scene_state['selection_method'] = method

    # 수동 제거 목록 초기화 (새로 선택했으므로)
    st.session_state.korean_scene_state['manual_removed'] = set()

    print(f"[KoreanScene] 자동 선택 설정: {len(scene_ids)}개 ({method})")


def add_manual_scene(scene_id: int) -> bool:
    """씬 수동 추가

    Returns:
        True: 추가 성공
        False: 이미 선택되어 있음
    """

    init_korean_scene_state()
    state = st.session_state.korean_scene_state

    # 이미 선택되어 있으면 무시
    if scene_id in get_all_selected_korean_scenes():
        return False

    # 만약 자동 선택에서 수동 제거된 것이면, 수동 제거 목록에서 제거
    if scene_id in state['manual_removed']:
        state['manual_removed'].discard(scene_id)
        print(f"[KoreanScene] 씬 {scene_id} 수동 제거 취소 (자동 선택 복원)")
        return True

    # 수동 추가
    state['manual_added'].add(scene_id)

    print(f"[KoreanScene] ➕ 씬 {scene_id} 수동 추가됨")
    return True


def remove_manual_scene(scene_id: int) -> bool:
    """씬 수동 제거

    Returns:
        True: 제거 성공
        False: 선택되어 있지 않음
    """

    init_korean_scene_state()
    state = st.session_state.korean_scene_state

    # 수동 추가된 씬이면 수동 추가 목록에서 제거
    if scene_id in state['manual_added']:
        state['manual_added'].discard(scene_id)
        print(f"[KoreanScene] ➖ 씬 {scene_id} 수동 추가에서 제거됨")
        return True

    # 자동 선택된 씬이면 수동 제거 목록에 추가
    if scene_id in state['auto_selected'] and scene_id not in state['manual_removed']:
        state['manual_removed'].add(scene_id)
        print(f"[KoreanScene] ➖ 씬 {scene_id} 자동 선택에서 제거됨")
        return True

    return False


def is_korean_scene_selected(scene_id: int) -> bool:
    """씬이 한글 씬으로 선택되었는지 확인"""
    return scene_id in get_all_selected_korean_scenes()


def get_selection_source(scene_id: int) -> Optional[str]:
    """씬 선택 소스 반환

    Returns:
        'auto': 자동 선택 (랜덤/AI)
        'manual': 수동 추가
        None: 선택되지 않음
    """

    init_korean_scene_state()
    state = st.session_state.korean_scene_state

    if scene_id in state['manual_added']:
        return 'manual'
    elif scene_id in state['auto_selected'] and scene_id not in state['manual_removed']:
        return 'auto'
    else:
        return None


def get_selection_stats() -> Dict:
    """선택 통계 반환"""

    init_korean_scene_state()
    state = st.session_state.korean_scene_state

    auto_effective = state['auto_selected'] - state['manual_removed']
    manual_count = len(state['manual_added'])
    auto_count = len(auto_effective)
    total_selected = len(get_all_selected_korean_scenes())
    removed_count = len(state['manual_removed'])

    return {
        'auto_count': auto_count,
        'manual_count': manual_count,
        'removed_count': removed_count,
        'total_selected': total_selected,
        'method': state['selection_method'],
        'auto_raw': len(state['auto_selected']),  # 제거 전 자동 선택 수
    }


def clear_korean_scene_selection():
    """한글 씬 선택 모두 초기화"""

    init_korean_scene_state()
    st.session_state.korean_scene_state = {
        'auto_selected': set(),
        'manual_added': set(),
        'manual_removed': set(),
        'selection_method': 'random',
    }
    print("[KoreanScene] 선택 초기화됨")


def sync_with_legacy_state():
    """기존 korean_selected_scenes 상태와 동기화

    기존 코드와의 호환성을 위해 korean_selected_scenes 세션 상태를
    새로운 상태 관리 시스템과 동기화
    """

    init_korean_scene_state()

    # 기존 상태가 있고 새 상태가 비어있으면 마이그레이션
    legacy_scenes = st.session_state.get('korean_selected_scenes', set())
    state = st.session_state.korean_scene_state

    if legacy_scenes and not state['auto_selected'] and not state['manual_added']:
        # 기존 상태를 자동 선택으로 마이그레이션
        state['auto_selected'] = set(legacy_scenes)
        print(f"[KoreanScene] 기존 상태 마이그레이션: {len(legacy_scenes)}개")


def update_legacy_state():
    """새 상태를 기존 korean_selected_scenes에 반영

    기존 코드와의 호환성을 위해 호출
    """

    all_selected = get_all_selected_korean_scenes()
    st.session_state['korean_selected_scenes'] = all_selected
    return all_selected
