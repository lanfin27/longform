# -*- coding: utf-8 -*-
"""
components/prompt_default_selector.py
기본 프롬프트 선택 UI 컴포넌트

기능:
1. 단일/배치 분석용 기본 프롬프트 선택 UI
2. 기본 프롬프트 설정/해제 버튼
3. 현재 기본 프롬프트 표시
4. v3.26.1: template_manager와 동기화
"""

import streamlit as st
from typing import List, Dict, Optional
from utils.prompt_defaults import (
    get_default_prompt,
    set_default_prompt,
    clear_default_prompt,
    get_default_prompt_id
)
from core.prompt.prompt_template_manager import get_template_manager


def render_default_prompt_settings(
    all_srt_prompts: Dict[str, List[Dict]],
    key_prefix: str = "default_prompt"
):
    """
    기본 프롬프트 설정 UI 렌더링

    Args:
        all_srt_prompts: 유형별 프롬프트 목록
            {
                "single": [{"id": "...", "name": "...", "is_default": bool}, ...],
                "batch": [...],
                "both": [...]
            }
        key_prefix: Streamlit 위젯 키 접두사
    """

    st.markdown("### ⭐ 기본 프롬프트 설정")
    st.caption("씬 분석 시 기본으로 사용할 프롬프트를 설정합니다. 수동 변경 전까지 자동 적용됩니다.")

    # 단일 분석용 프롬프트 목록 (single + both)
    single_prompts = []
    for t in all_srt_prompts.get("single", []):
        single_prompts.append(t)
    for t in all_srt_prompts.get("both", []):
        if t not in single_prompts:
            single_prompts.append(t)

    # 배치 분석용 프롬프트 목록 (batch + both)
    batch_prompts = []
    for t in all_srt_prompts.get("batch", []):
        batch_prompts.append(t)
    for t in all_srt_prompts.get("both", []):
        if t not in batch_prompts:
            batch_prompts.append(t)

    col1, col2 = st.columns(2)

    # ═══════════════════════════════════════════════════════
    # 단일 씬 분석용 기본 프롬프트
    # ═══════════════════════════════════════════════════════

    with col1:
        st.markdown("**📌 단일 씬 분석용**")

        # 현재 기본 설정 가져오기
        current_single = get_default_prompt("single_scene_analysis")
        current_single_id = current_single.get("prompt_id") if current_single else None
        current_single_name = current_single.get("prompt_name") if current_single else None

        # 프롬프트 선택 드롭다운
        single_options = ["(선택 안 함)"] + [p["name"] for p in single_prompts]
        single_ids = [None] + [p["id"] for p in single_prompts]

        # 현재 설정된 프롬프트의 인덱스 찾기
        try:
            default_idx = single_ids.index(current_single_id) if current_single_id else 0
        except ValueError:
            default_idx = 0

        selected_single = st.selectbox(
            "단일 분석 프롬프트",
            options=single_options,
            index=default_idx,
            key=f"{key_prefix}_single_select",
            label_visibility="collapsed"
        )

        # 선택된 프롬프트 ID
        selected_idx = single_options.index(selected_single)
        selected_single_id = single_ids[selected_idx]

        # 기본 설정 버튼
        if st.button(
            "⭐ 단일 기본 설정",
            key=f"{key_prefix}_set_single",
            use_container_width=True,
            type="primary" if selected_single_id and selected_single_id != current_single_id else "secondary"
        ):
            if selected_single_id:
                success = set_default_prompt(
                    "single_scene_analysis",
                    selected_single_id,
                    selected_single
                )
                if success:
                    # ⭐ v3.26.2: template_manager와 동기화 + selectbox 초기화
                    try:
                        template_manager = get_template_manager()
                        template_manager.set_active_prompt("single", selected_single_id)
                    except Exception as e:
                        print(f"[DefaultPrompt] template_manager 동기화 실패: {e}")

                    # selectbox session_state 초기화 (새 기본값 반영을 위해)
                    if "srt_analysis_prompt_selector" in st.session_state:
                        del st.session_state["srt_analysis_prompt_selector"]
                    # v3.26.2: 모드 추적 키도 초기화 (기본값 재적용 트리거)
                    if "_last_prompt_type" in st.session_state:
                        del st.session_state["_last_prompt_type"]

                    st.success(f"✅ 단일 분석 기본 프롬프트 설정됨")
                    st.rerun()
            else:
                # 설정 해제
                clear_default_prompt("single_scene_analysis")
                # selectbox 초기화
                if "srt_analysis_prompt_selector" in st.session_state:
                    del st.session_state["srt_analysis_prompt_selector"]
                # v3.26.2: 모드 추적 키도 초기화
                if "_last_prompt_type" in st.session_state:
                    del st.session_state["_last_prompt_type"]
                st.info("ℹ️ 단일 분석 기본 프롬프트 해제됨")
                st.rerun()

        # 현재 기본 표시
        if current_single:
            st.success(f"✅ 현재: {current_single_name}")
        else:
            st.info("ℹ️ 미설정")

    # ═══════════════════════════════════════════════════════
    # 배치 분석용 기본 프롬프트
    # ═══════════════════════════════════════════════════════

    with col2:
        st.markdown("**📌 배치 분석용**")

        # 현재 기본 설정 가져오기
        current_batch = get_default_prompt("batch_scene_analysis")
        current_batch_id = current_batch.get("prompt_id") if current_batch else None
        current_batch_name = current_batch.get("prompt_name") if current_batch else None

        # 프롬프트 선택 드롭다운
        batch_options = ["(선택 안 함)"] + [p["name"] for p in batch_prompts]
        batch_ids = [None] + [p["id"] for p in batch_prompts]

        # 현재 설정된 프롬프트의 인덱스 찾기
        try:
            default_idx = batch_ids.index(current_batch_id) if current_batch_id else 0
        except ValueError:
            default_idx = 0

        selected_batch = st.selectbox(
            "배치 분석 프롬프트",
            options=batch_options,
            index=default_idx,
            key=f"{key_prefix}_batch_select",
            label_visibility="collapsed"
        )

        # 선택된 프롬프트 ID
        selected_idx = batch_options.index(selected_batch)
        selected_batch_id = batch_ids[selected_idx]

        # 기본 설정 버튼
        if st.button(
            "⭐ 배치 기본 설정",
            key=f"{key_prefix}_set_batch",
            use_container_width=True,
            type="primary" if selected_batch_id and selected_batch_id != current_batch_id else "secondary"
        ):
            if selected_batch_id:
                success = set_default_prompt(
                    "batch_scene_analysis",
                    selected_batch_id,
                    selected_batch
                )
                if success:
                    # ⭐ v3.26.2: template_manager와 동기화 + selectbox 초기화
                    try:
                        template_manager = get_template_manager()
                        template_manager.set_active_prompt("batch", selected_batch_id)
                    except Exception as e:
                        print(f"[DefaultPrompt] template_manager 동기화 실패: {e}")

                    # selectbox session_state 초기화 (새 기본값 반영을 위해)
                    if "srt_analysis_prompt_selector" in st.session_state:
                        del st.session_state["srt_analysis_prompt_selector"]
                    # v3.26.2: 모드 추적 키도 초기화 (기본값 재적용 트리거)
                    if "_last_prompt_type" in st.session_state:
                        del st.session_state["_last_prompt_type"]

                    st.success(f"✅ 배치 분석 기본 프롬프트 설정됨")
                    st.rerun()
            else:
                # 설정 해제
                clear_default_prompt("batch_scene_analysis")
                # selectbox 초기화
                if "srt_analysis_prompt_selector" in st.session_state:
                    del st.session_state["srt_analysis_prompt_selector"]
                # v3.26.2: 모드 추적 키도 초기화
                if "_last_prompt_type" in st.session_state:
                    del st.session_state["_last_prompt_type"]
                st.info("ℹ️ 배치 분석 기본 프롬프트 해제됨")
                st.rerun()

        # 현재 기본 표시
        if current_batch:
            st.success(f"✅ 현재: {current_batch_name}")
        else:
            st.info("ℹ️ 미설정")

    st.markdown("---")


def get_auto_selected_prompt_id(
    analysis_mode: str,
    all_srt_prompts: Dict[str, List[Dict]]
) -> Optional[str]:
    """
    분석 모드에 따라 기본 프롬프트 ID 자동 선택

    Args:
        analysis_mode: "sequential", "parallel", "batch"
        all_srt_prompts: 유형별 프롬프트 목록

    Returns:
        기본 프롬프트 ID 또는 None
    """
    if analysis_mode in ("sequential", "parallel"):
        # 단일 씬 분석
        default = get_default_prompt("single_scene_analysis")
        if default:
            # 유효성 검증 (존재하는 프롬프트인지)
            all_ids = []
            for ptype in all_srt_prompts.values():
                for p in ptype:
                    all_ids.append(p["id"])

            if default.get("prompt_id") in all_ids:
                return default.get("prompt_id")

    elif analysis_mode == "batch":
        # 배치 분석
        default = get_default_prompt("batch_scene_analysis")
        if default:
            # 유효성 검증
            all_ids = []
            for ptype in all_srt_prompts.values():
                for p in ptype:
                    all_ids.append(p["id"])

            if default.get("prompt_id") in all_ids:
                return default.get("prompt_id")

    return None


def render_default_prompt_indicator(analysis_mode: str) -> bool:
    """
    기본 프롬프트 적용 여부 표시

    Args:
        analysis_mode: "sequential", "parallel", "batch"

    Returns:
        기본 프롬프트가 적용되었는지 여부
    """
    prompt_type = "single_scene_analysis" if analysis_mode in ("sequential", "parallel") else "batch_scene_analysis"
    default = get_default_prompt(prompt_type)

    if default:
        st.info(f"⭐ 기본 프롬프트 적용됨: {default.get('prompt_name')}")
        return True

    return False
