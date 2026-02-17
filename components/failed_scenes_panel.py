# -*- coding: utf-8 -*-
"""
실패 씬 목록 UI 패널 v1.0

이미지 생성 실패 씬 목록 표시 및 재생성 UI

기능:
- 실패 씬 목록 표시 (체크박스, 에러 정보)
- 에러 유형별 필터링
- 선택적/전체 재생성 버튼
- 상세 에러 정보 표시

사용법:
    from components.failed_scenes_panel import render_failed_scenes_panel

    render_failed_scenes_panel(
        failed_scenes=failed_list,
        on_retry_selected=callback_retry_selected,
        on_retry_all=callback_retry_all,
        on_clear=callback_clear
    )
"""

import streamlit as st
from typing import List, Dict, Callable, Optional

from utils.failed_scene_manager import (
    FailedSceneManager,
    ERROR_CATEGORY_INFO,
    get_error_category_info
)


def render_failed_scenes_panel(
    failed_scenes: List[Dict],
    on_retry_selected: Optional[Callable] = None,
    on_retry_all: Optional[Callable] = None,
    on_clear: Optional[Callable] = None,
    on_ai_sanitize: Optional[Callable] = None,
    key_prefix: str = "failed"
):
    """
    실패 씬 목록 패널 UI 렌더링

    Args:
        failed_scenes: 실패 씬 정보 목록
        on_retry_selected: 선택 씬 재시도 콜백
        on_retry_all: 전체 재시도 콜백
        on_clear: 기록 삭제 콜백
        on_ai_sanitize: AI 프롬프트 정제 콜백 (scene_id, prompt)
        key_prefix: 위젯 키 접두사
    """
    if not failed_scenes:
        st.success("모든 씬이 성공적으로 생성되었습니다!")
        return

    # ════════════════════════════════════════════════════════════
    # 헤더
    # ════════════════════════════════════════════════════════════
    st.markdown(f"""
    <div style="background: #FFF3CD; padding: 15px; border-radius: 8px; border-left: 4px solid #FFC107; margin-bottom: 16px;">
        <h4 style="margin: 0; color: #856404;">실패한 씬 목록 ({len(failed_scenes)}개)</h4>
    </div>
    """, unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════════
    # 에러 유형별 요약
    # ════════════════════════════════════════════════════════════
    error_summary = {}
    for fs in failed_scenes:
        cat = fs.get('error_category', 'unknown')
        error_summary[cat] = error_summary.get(cat, 0) + 1

    # 요약 메트릭
    num_cols = min(len(error_summary) + 1, 5)
    cols = st.columns(num_cols)

    with cols[0]:
        st.metric("총 실패", f"{len(failed_scenes)}개")

    for idx, (cat, count) in enumerate(list(error_summary.items())[:4]):
        if idx + 1 < num_cols:
            info = get_error_category_info(cat)
            with cols[idx + 1]:
                st.metric(f"{info['icon']} {info['label']}", f"{count}개")

    st.markdown("---")

    # ════════════════════════════════════════════════════════════
    # 필터링 옵션
    # ════════════════════════════════════════════════════════════
    filter_col1, filter_col2 = st.columns([3, 1])

    with filter_col1:
        filter_options = ["전체"] + [
            f"{get_error_category_info(cat)['icon']} {get_error_category_info(cat)['label']}"
            for cat in error_summary.keys()
        ]
        selected_filter = st.selectbox(
            "에러 유형 필터",
            options=filter_options,
            key=f"{key_prefix}_filter",
            label_visibility="collapsed"
        )

    with filter_col2:
        # 전체 선택 체크박스
        select_all = st.checkbox(
            "전체 선택",
            key=f"{key_prefix}_select_all"
        )

    # 필터링된 씬 목록
    if selected_filter == "전체":
        filtered_scenes = failed_scenes
    else:
        # 필터에서 카테고리 추출
        for cat, info in ERROR_CATEGORY_INFO.items():
            if info['label'] in selected_filter:
                filtered_scenes = [fs for fs in failed_scenes if fs.get('error_category') == cat]
                break
        else:
            filtered_scenes = failed_scenes

    st.markdown("")

    # ════════════════════════════════════════════════════════════
    # 실패 씬 목록
    # ════════════════════════════════════════════════════════════
    selected_scenes = []

    for idx, fs in enumerate(filtered_scenes):
        scene_id = fs.get('scene_id')
        error_type = fs.get('error_type', 'Unknown')
        error_category = fs.get('error_category', 'unknown')
        error_msg = fs.get('error_message', '')[:100]
        retry_count = fs.get('retry_count', 0)
        timestamp = fs.get('timestamp', '')
        prompt_preview = fs.get('prompt', '')[:80]

        cat_info = get_error_category_info(error_category)

        # 행 레이아웃
        col_check, col_scene, col_error, col_info = st.columns([0.5, 1, 2.5, 1])

        with col_check:
            # 체크박스
            is_selected = st.checkbox(
                "선택",
                value=select_all or st.session_state.get(f"{key_prefix}_cb_{scene_id}", False),
                key=f"{key_prefix}_cb_{scene_id}_{idx}",
                label_visibility="collapsed"
            )
            if is_selected:
                selected_scenes.append(fs)

        with col_scene:
            st.markdown(f"**씬 {scene_id}**")
            if retry_count > 0:
                st.caption(f"재시도 {retry_count}회")

        with col_error:
            # 에러 카테고리 배지
            st.markdown(f"{cat_info['icon']} **{cat_info['label']}**")
            st.caption(error_msg + ("..." if len(error_msg) == 100 else ""))

        with col_info:
            st.caption(timestamp.split(" ")[0] if " " in timestamp else timestamp)

            # 상세 보기 버튼
            if st.button("상세", key=f"{key_prefix}_detail_{scene_id}_{idx}"):
                st.session_state[f'{key_prefix}_show_detail_{scene_id}'] = True

        # 상세 정보 표시
        if st.session_state.get(f'{key_prefix}_show_detail_{scene_id}', False):
            with st.expander(f"씬 {scene_id} 에러 상세", expanded=True):
                st.markdown(f"**에러 유형:** `{error_type}`")
                st.markdown(f"**카테고리:** {cat_info['icon']} {cat_info['label']}")
                st.markdown(f"**설명:** {cat_info['description']}")
                st.markdown(f"**해결 방법:** {cat_info['solution']}")

                st.markdown("**전체 에러 메시지:**")
                st.code(fs.get('error_message', ''), language=None)

                # 스택 트레이스
                with st.expander("스택 트레이스"):
                    st.code(fs.get('error_traceback', '상세 정보 없음'), language="python")

                # 프롬프트 편집 및 재생성
                full_prompt = fs.get('prompt', '')
                if full_prompt:
                    st.markdown("---")
                    st.markdown("**원본 프롬프트:**")
                    st.text_area(
                        "원본", value=full_prompt, height=80, disabled=True,
                        key=f"{key_prefix}_orig_{scene_id}",
                        label_visibility="collapsed"
                    )

                    edit_key = f"{key_prefix}_edit_prompt_{scene_id}"
                    edited_prompt = st.text_area(
                        "수정된 프롬프트 (편집 가능)",
                        value=st.session_state.get(edit_key, full_prompt),
                        height=80,
                        key=f"{key_prefix}_edit_{scene_id}"
                    )
                    st.session_state[edit_key] = edited_prompt

                    btn_col1, btn_col2 = st.columns(2)
                    with btn_col1:
                        if st.button("이 씬만 재생성", key=f"{key_prefix}_retry_one_{scene_id}"):
                            retry_scene = fs.copy()
                            retry_scene["prompt"] = edited_prompt
                            if on_retry_selected:
                                on_retry_selected([retry_scene])
                    with btn_col2:
                        if st.button("AI 프롬프트 정제", key=f"{key_prefix}_ai_{scene_id}"):
                            if on_ai_sanitize:
                                on_ai_sanitize(scene_id, edited_prompt)

                if st.button("닫기", key=f"{key_prefix}_close_detail_{scene_id}"):
                    st.session_state[f'{key_prefix}_show_detail_{scene_id}'] = False
                    st.rerun()

        # 구분선
        if idx < len(filtered_scenes) - 1:
            st.markdown("<hr style='margin: 8px 0; opacity: 0.3;'>", unsafe_allow_html=True)

    st.markdown("---")

    # ════════════════════════════════════════════════════════════
    # 액션 버튼
    # ════════════════════════════════════════════════════════════
    col_retry_sel, col_retry_all, col_clear = st.columns([1.5, 1.5, 1])

    with col_retry_sel:
        retry_sel_disabled = len(selected_scenes) == 0
        if st.button(
            f"선택 씬 재생성 ({len(selected_scenes)}개)",
            disabled=retry_sel_disabled,
            type="primary",
            use_container_width=True,
            key=f"{key_prefix}_retry_selected"
        ):
            if on_retry_selected:
                on_retry_selected(selected_scenes)

    with col_retry_all:
        if st.button(
            f"전체 재생성 ({len(failed_scenes)}개)",
            type="secondary",
            use_container_width=True,
            key=f"{key_prefix}_retry_all"
        ):
            if on_retry_all:
                on_retry_all(failed_scenes)

    with col_clear:
        if st.button(
            "기록 삭제",
            use_container_width=True,
            key=f"{key_prefix}_clear"
        ):
            if on_clear:
                on_clear()


def render_generation_progress_with_failures(
    total: int,
    completed: int,
    success: int,
    failed: int,
    key_prefix: str = "progress"
):
    """
    실패 포함 진행률 표시

    Args:
        total: 전체 씬 수
        completed: 완료된 씬 수
        success: 성공 씬 수
        failed: 실패 씬 수
        key_prefix: 위젯 키 접두사
    """
    progress = completed / total if total > 0 else 0

    # 프로그레스 바
    st.progress(progress)

    # 상태 표시
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("진행", f"{completed}/{total}")

    with col2:
        st.metric("성공", f"{success}개")

    with col3:
        st.metric("실패", f"{failed}개")

    with col4:
        success_rate = (success / completed * 100) if completed > 0 else 0
        st.metric("성공률", f"{success_rate:.1f}%")


def render_failed_scenes_summary_card(
    failed_scenes: List[Dict],
    on_click: Optional[Callable] = None,
    key_prefix: str = "summary"
):
    """
    실패 씬 요약 카드 (메인 페이지용)

    Args:
        failed_scenes: 실패 씬 목록
        on_click: 클릭 시 콜백
        key_prefix: 위젯 키 접두사
    """
    if not failed_scenes:
        return

    # 에러 카테고리별 집계
    error_counts = {}
    for fs in failed_scenes:
        cat = fs.get('error_category', 'unknown')
        error_counts[cat] = error_counts.get(cat, 0) + 1

    # 카드 스타일
    st.markdown(f"""
    <div style="
        background: linear-gradient(135deg, #FFF3CD 0%, #FFE8A1 100%);
        padding: 16px;
        border-radius: 12px;
        border: 1px solid #FFC107;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    ">
        <div style="display: flex; align-items: center; margin-bottom: 12px;">
            <span style="font-size: 24px; margin-right: 8px;">&#x26A0;</span>
            <span style="font-size: 18px; font-weight: bold; color: #856404;">
                이전 생성에서 {len(failed_scenes)}개 씬 실패
            </span>
        </div>
        <div style="display: flex; flex-wrap: wrap; gap: 8px;">
            {''.join([
                f'<span style="background: #FFC107; color: #000; padding: 4px 8px; border-radius: 4px; font-size: 12px;">'
                f'{get_error_category_info(cat)["icon"]} {get_error_category_info(cat)["label"]}: {count}개'
                f'</span>'
                for cat, count in list(error_counts.items())[:4]
            ])}
        </div>
    </div>
    """, unsafe_allow_html=True)

    if on_click:
        if st.button(
            "실패 씬 확인 및 재생성",
            type="primary",
            key=f"{key_prefix}_view_failed"
        ):
            on_click()


def render_compact_failed_list(
    failed_scenes: List[Dict],
    max_display: int = 5,
    key_prefix: str = "compact"
):
    """
    컴팩트 실패 씬 목록 (사이드바용)

    Args:
        failed_scenes: 실패 씬 목록
        max_display: 최대 표시 개수
        key_prefix: 위젯 키 접두사
    """
    if not failed_scenes:
        st.caption("실패한 씬 없음")
        return

    st.caption(f"실패 씬: {len(failed_scenes)}개")

    for idx, fs in enumerate(failed_scenes[:max_display]):
        scene_id = fs.get('scene_id')
        cat = fs.get('error_category', 'unknown')
        info = get_error_category_info(cat)

        st.markdown(f"{info['icon']} 씬 {scene_id} - {info['label']}")

    if len(failed_scenes) > max_display:
        st.caption(f"... 외 {len(failed_scenes) - max_display}개")
