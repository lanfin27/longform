# -*- coding: utf-8 -*-
"""
씬 구간 선택 컴포넌트

TTS 생성 페이지에서 씬을 효율적으로 선택할 수 있는 UI 제공

사용법:
    from components.scene_range_selector import render_scene_range_selector

    selected_scene_numbers = render_scene_range_selector(
        total_scenes=len(scenes),
        scenes_data=scenes,
        key_prefix="tts_scene"
    )

    # 선택된 씬만 필터링
    selected_scenes = [scenes[i-1] for i in selected_scene_numbers]
"""

import streamlit as st
from typing import List, Set, Dict, Tuple, Optional
import re

# 기존 유틸리티 함수 재사용
from utils.scene_selector import (
    parse_scene_range_input,
    format_selected_scenes,
    generate_preset_ranges
)


def parse_range_string(range_str: str, max_scene: int) -> Set[int]:
    """
    범위 문자열 파싱 (Set 반환 버전)

    Args:
        range_str: "1-50, 55, 60-70" 형식
        max_scene: 최대 씬 번호

    Returns:
        선택된 씬 번호 집합
    """
    result = parse_scene_range_input(range_str, max_scene)
    return set(result)


def format_selection_summary(selected: Set[int]) -> str:
    """
    선택 요약 문자열 생성

    Args:
        selected: 선택된 씬 번호 집합

    Returns:
        "씬 1~50, 55, 60~70" 형식
    """
    if not selected:
        return "선택 없음"

    formatted = format_selected_scenes(sorted(list(selected)))
    return f"씬 {formatted}"


def render_scene_range_selector(
    total_scenes: int,
    scenes_data: List[Dict] = None,
    key_prefix: str = "scene_select",
    show_header: bool = True,
    default_mode: str = "전체",
    container_height: int = 400
) -> List[int]:
    """
    씬 구간 선택 UI 렌더링

    Args:
        total_scenes: 총 씬 개수
        scenes_data: 씬 데이터 리스트 (미리보기용)
        key_prefix: Streamlit 키 프리픽스
        show_header: 헤더 표시 여부
        default_mode: 기본 선택 모드 ("전체", "구간 선택", "개별 선택")
        container_height: 개별 선택 컨테이너 높이

    Returns:
        선택된 씬 번호 리스트 (1-based, 정렬됨)
    """
    if total_scenes == 0:
        st.warning("선택할 씬이 없습니다.")
        return []

    if show_header:
        st.subheader("생성할 씬 선택")

    # 세션 상태 초기화
    mode_key = f"{key_prefix}_mode"
    if mode_key not in st.session_state:
        st.session_state[mode_key] = default_mode

    # 선택 모드
    mode = st.radio(
        "선택 모드",
        ["전체", "구간 선택", "개별 선택"],
        horizontal=True,
        key=mode_key
    )

    selected_scenes = set()

    # ==========================================
    # 전체 선택 모드
    # ==========================================
    if mode == "전체":
        selected_scenes = set(range(1, total_scenes + 1))
        st.success(f"전체 {total_scenes}개 씬 선택됨")

    # ==========================================
    # 구간 선택 모드
    # ==========================================
    elif mode == "구간 선택":
        st.markdown("---")

        # ⭐ 탭 선택 상태 관리 (슬라이더/직접입력)
        tab_mode_key = f"{key_prefix}_tab_mode"
        if tab_mode_key not in st.session_state:
            st.session_state[tab_mode_key] = "slider"  # 기본값: 슬라이더

        # 탭 선택 라디오 (실제 탭 대신 라디오 사용)
        tab_mode = st.radio(
            "입력 방식",
            ["슬라이더로 선택", "직접 입력"],
            horizontal=True,
            key=f"{key_prefix}_tab_radio"
        )
        st.session_state[tab_mode_key] = "slider" if tab_mode == "슬라이더로 선택" else "text"

        # 세션 상태에서 이전 값 복원
        start_key = f"{key_prefix}_range_start"
        end_key = f"{key_prefix}_range_end"

        if start_key not in st.session_state:
            st.session_state[start_key] = 1
        if end_key not in st.session_state:
            st.session_state[end_key] = min(50, total_scenes)

        # ==========================================
        # 슬라이더 모드
        # ==========================================
        if st.session_state[tab_mode_key] == "slider":
            col1, col2, col3 = st.columns([2, 1, 2])

            with col1:
                start_scene = st.number_input(
                    "시작 씬",
                    min_value=1,
                    max_value=total_scenes,
                    value=st.session_state[start_key],
                    key=f"{key_prefix}_start_input"
                )

            with col2:
                st.markdown("<div style='text-align: center; padding-top: 30px; font-size: 1.5em;'>~</div>",
                           unsafe_allow_html=True)

            with col3:
                end_scene = st.number_input(
                    "끝 씬",
                    min_value=1,
                    max_value=total_scenes,
                    value=st.session_state[end_key],
                    key=f"{key_prefix}_end_input"
                )

            # 범위 슬라이더
            st.markdown("")
            range_values = st.slider(
                "범위 조정",
                min_value=1,
                max_value=total_scenes,
                value=(min(start_scene, end_scene), max(start_scene, end_scene)),
                key=f"{key_prefix}_slider"
            )

            # 슬라이더 값 사용
            final_start = range_values[0]
            final_end = range_values[1]

            # 세션 상태 업데이트
            st.session_state[start_key] = final_start
            st.session_state[end_key] = final_end

            # ⭐ 선택 적용 (슬라이더 모드)
            selected_scenes = set(range(final_start, final_end + 1))

            # 퀵 선택 버튼들
            st.markdown("**퀵 선택:**")

            # 동적으로 버튼 생성
            quick_options = []

            if total_scenes >= 10:
                quick_options.append(("1~10", 1, min(10, total_scenes)))
            if total_scenes >= 50:
                quick_options.append(("1~50", 1, min(50, total_scenes)))
            if total_scenes >= 100:
                quick_options.append(("1~100", 1, min(100, total_scenes)))

            # 후반부 옵션
            if total_scenes > 50:
                half_start = max(1, total_scenes - 49)
                quick_options.append((f"후반 50개", half_start, total_scenes))

            quick_options.append(("전체", 1, total_scenes))

            cols = st.columns(len(quick_options))

            for idx, (label, start, end) in enumerate(quick_options):
                with cols[idx]:
                    if st.button(label, key=f"{key_prefix}_quick_{idx}", use_container_width=True):
                        st.session_state[start_key] = start
                        st.session_state[end_key] = end
                        st.rerun()

        # ==========================================
        # 직접 입력 모드
        # ==========================================
        else:
            st.markdown("""
            **입력 형식:**
            - `1-50` : 씬 1부터 50까지
            - `55` : 씬 55만
            - `1-50, 55, 60-70` : 여러 구간 조합
            - `1~50` : 물결표도 사용 가능
            """)

            # 기본값: 세션 상태에서 슬라이더 값 기반으로 생성
            default_range = f"{st.session_state[start_key]}-{st.session_state[end_key]}"

            range_input = st.text_input(
                "씬 범위 입력",
                value=st.session_state.get(f"{key_prefix}_range_text", default_range),
                placeholder="예: 1-50, 55, 60-70",
                key=f"{key_prefix}_range_input"
            )

            # 세션 상태 저장
            st.session_state[f"{key_prefix}_range_text"] = range_input

            # ⭐ 선택 적용 (직접 입력 모드)
            selected_scenes = parse_range_string(range_input, total_scenes)

            if selected_scenes:
                st.caption(f"파싱 결과: {format_selection_summary(selected_scenes)}")
            else:
                st.warning("입력 형식을 확인해주세요.")

    # ==========================================
    # 개별 선택 모드
    # ==========================================
    elif mode == "개별 선택":
        st.markdown("---")

        # 전체 선택/해제 버튼
        col1, col2, col3 = st.columns([1, 1, 2])
        with col1:
            if st.button("전체 선택", key=f"{key_prefix}_select_all", use_container_width=True):
                for i in range(1, total_scenes + 1):
                    st.session_state[f"{key_prefix}_scene_{i}"] = True
                st.rerun()
        with col2:
            if st.button("전체 해제", key=f"{key_prefix}_deselect_all", use_container_width=True):
                for i in range(1, total_scenes + 1):
                    st.session_state[f"{key_prefix}_scene_{i}"] = False
                st.rerun()
        with col3:
            # 범위 선택 입력
            quick_range = st.text_input(
                "범위 선택",
                placeholder="예: 1-10",
                key=f"{key_prefix}_quick_range",
                label_visibility="collapsed"
            )
            if quick_range:
                quick_set = parse_range_string(quick_range, total_scenes)
                if quick_set:
                    for i in range(1, total_scenes + 1):
                        st.session_state[f"{key_prefix}_scene_{i}"] = i in quick_set
                    st.rerun()

        st.markdown("---")

        # 씬 체크박스 리스트 (스크롤 가능)
        with st.container(height=container_height):
            for i in range(1, total_scenes + 1):
                # 씬 데이터에서 미리보기 텍스트 가져오기
                preview = ""
                char_count = 0
                duration_est = 0

                if scenes_data and i <= len(scenes_data):
                    scene = scenes_data[i - 1]
                    text = scene.get("text", "") or scene.get("script_text", "") or scene.get("narration", "")
                    char_count = len(text)
                    duration_est = scene.get("duration_estimate", max(1, char_count // 10))
                    preview = text[:35] + "..." if len(text) > 35 else text

                # 기본값 설정 (처음에는 전체 선택)
                default_key = f"{key_prefix}_scene_{i}"
                if default_key not in st.session_state:
                    st.session_state[default_key] = True

                # 라벨 생성
                if preview:
                    label = f"씬 {i}  > {preview} ({char_count}자, ~{duration_est}초)"
                else:
                    label = f"씬 {i}"

                checked = st.checkbox(
                    label,
                    value=st.session_state[default_key],
                    key=f"{key_prefix}_scene_cb_{i}"
                )

                # 상태 동기화
                st.session_state[default_key] = checked

                if checked:
                    selected_scenes.add(i)

    # ==========================================
    # 선택 결과 요약
    # ==========================================
    st.markdown("---")

    if selected_scenes:
        summary = format_selection_summary(selected_scenes)

        # 예상 시간 계산
        if scenes_data:
            # 실제 데이터 기반 계산
            estimated_duration = 0
            for i in selected_scenes:
                if i <= len(scenes_data):
                    scene = scenes_data[i - 1]
                    text = scene.get("text", "") or scene.get("script_text", "") or ""
                    char_count = len(text)
                    estimated_duration += scene.get("duration_estimate", max(1, char_count // 10))
        else:
            # 기본값: 씬당 평균 3초
            estimated_duration = len(selected_scenes) * 3

        minutes = estimated_duration // 60
        seconds = estimated_duration % 60

        col1, col2 = st.columns(2)
        with col1:
            st.info(f"**선택된 씬:** {len(selected_scenes)}개")
        with col2:
            if minutes > 0:
                st.info(f"**예상 길이:** {minutes}분 {seconds}초")
            else:
                st.info(f"**예상 길이:** {seconds}초")

        st.caption(f"{summary}")
    else:
        st.warning("선택된 씬이 없습니다.")

    return sorted(list(selected_scenes))


def render_compact_scene_selector(
    total_scenes: int,
    key_prefix: str = "compact_scene"
) -> List[int]:
    """
    컴팩트한 씬 선택기 (구간만)

    Args:
        total_scenes: 총 씬 개수
        key_prefix: Streamlit 키 프리픽스

    Returns:
        선택된 씬 번호 리스트
    """
    col1, col2, col3 = st.columns([2, 1, 2])

    with col1:
        start = st.number_input(
            "시작",
            min_value=1,
            max_value=total_scenes,
            value=1,
            key=f"{key_prefix}_start"
        )

    with col2:
        st.markdown("<div style='text-align: center; padding-top: 30px;'>~</div>",
                   unsafe_allow_html=True)

    with col3:
        end = st.number_input(
            "끝",
            min_value=1,
            max_value=total_scenes,
            value=total_scenes,
            key=f"{key_prefix}_end"
        )

    start, end = min(start, end), max(start, end)
    return list(range(start, end + 1))


# ============================================================
# 세션 상태 관리
# ============================================================

def save_selection_to_session(selected: List[int], key: str = "selected_scenes"):
    """선택 상태를 세션에 저장"""
    st.session_state[key] = selected


def load_selection_from_session(key: str = "selected_scenes") -> List[int]:
    """세션에서 선택 상태 복원"""
    return st.session_state.get(key, [])


def clear_selection_state(key_prefix: str = "scene_select"):
    """선택 상태 초기화"""
    keys_to_remove = [k for k in st.session_state.keys() if k.startswith(key_prefix)]
    for key in keys_to_remove:
        del st.session_state[key]


# ============================================================
# 테스트 함수
# ============================================================

def _test_parse_range_string():
    """범위 파싱 테스트"""
    # 단일 범위
    assert parse_range_string("1-50", 121) == set(range(1, 51))

    # 단일 값
    assert parse_range_string("55", 121) == {55}

    # 복합 범위
    result = parse_range_string("1-50, 55, 60-70", 121)
    expected = set(range(1, 51)) | {55} | set(range(60, 71))
    assert result == expected

    # 범위 초과 처리
    assert parse_range_string("1-200", 121) == set(range(1, 122))

    # 빈 문자열
    assert parse_range_string("", 121) == set()

    # 물결표 지원
    assert parse_range_string("1~50", 121) == set(range(1, 51))

    print("모든 테스트 통과")


def _test_format_selection_summary():
    """요약 포맷 테스트"""
    assert "1~5" in format_selection_summary({1, 2, 3, 4, 5})
    assert "1~3" in format_selection_summary({1, 2, 3, 5, 6, 7})
    assert "5~7" in format_selection_summary({1, 2, 3, 5, 6, 7})
    assert format_selection_summary(set()) == "선택 없음"

    print("모든 테스트 통과")


if __name__ == "__main__":
    _test_parse_range_string()
    _test_format_selection_summary()
