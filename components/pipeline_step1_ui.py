# -*- coding: utf-8 -*-
"""
components/pipeline_step1_ui.py
Step 1: 실사이미지 대체 - 우선 대상 기능 포함 UI

1차 대상 (자동 선별): 묶음 대표 + 한글 씬
2차 대상 (AI 추천): 1차 제외 풀에서 AI 추가 추천

작성: 2025-01
"""

import streamlit as st
from pathlib import Path
from typing import List, Dict, Set, Optional, Tuple

from utils.pipeline_state import (
    PipelineState,
    PipelineStep,
    STEP_CONFIG,
    get_step_config
)
from utils.pipeline_step1_targets import (
    Step1PriorityTargets,
    recommend_real_image_from_pool,
    get_step1_selection_summary,
    init_step1_state,
    get_step1_state,
    set_step1_priority_targets,
    set_step1_ai_recommended,
    set_step1_final_targets,
    confirm_step1,
    reset_step1_state
)


def render_step1_real_image_enhanced(
    state: PipelineState,
    scenes: List[Dict],
    project_path: Path,
    save_callback=None
) -> Optional[Dict]:
    """
    Step 1: 실사이미지 대체 (우선 대상 기능 포함)

    Args:
        state: 파이프라인 상태
        scenes: 씬 데이터 리스트
        project_path: 프로젝트 경로
        save_callback: 저장 콜백 함수

    Returns:
        실행할 액션 (있으면)
    """
    config = get_step_config(PipelineStep.REAL_IMAGE)

    st.markdown(f"### {config['emoji']} Step 1: {config['name']}")
    st.caption(f"AI 소모: {config['ai_cost_label']} | 묶음 대표 + 한글 씬 우선, AI 추가 추천")

    if not scenes:
        st.warning("씬 데이터가 없습니다. 먼저 프로젝트를 로드하세요.")
        return None

    # Step 1 상태 초기화
    init_step1_state()
    step1_state = get_step1_state()

    # 1차 대상 관리자
    priority_manager = Step1PriorityTargets(scenes)

    # 전체 씬 풀
    total_scenes = len(scenes)
    base_pool = state.get_base_pool()  # 한글텍스트 제외된 기본 풀

    st.info(f"📦 전체 씬 풀: **{total_scenes}개** (한글텍스트 {len(state.korean_text_scenes)}개 포함)")

    # 이미 처리된 씬 표시
    if state.real_image_scenes:
        st.success(f"✅ 기존 대체 완료: **{len(state.real_image_scenes)}개**")
        with st.expander("대체된 씬 목록", expanded=False):
            st.write(sorted(state.real_image_scenes))

    st.markdown("---")

    # ═══════════════════════════════════════════════════════════════
    # 🥇 1차 대상 (우선 선별)
    # ═══════════════════════════════════════════════════════════════

    st.markdown("### 🥇 1차 대상 (우선 선별) - 자동")
    st.caption("실사이미지 대체의 핵심 대상입니다. 기본적으로 선택됩니다.")

    # 우선 대상 계산
    priority_targets, priority_details = priority_manager.get_priority_targets()

    # 1차 대상 옵션
    col1, col2 = st.columns(2)

    with col1:
        bundle_info = priority_details['bundle_representative']
        include_bundle = st.checkbox(
            f"☑️ 묶음별 대표 이미지 ({bundle_info['count']}개)",
            value=step1_state.get('include_bundle', True),
            key="step1_include_bundle",
            help="묶음(번들)의 첫 번째 이미지들. 실사로 대체하면 묶음 전체 품질 향상"
        )
        step1_state['include_bundle'] = include_bundle

        if include_bundle and bundle_info['count'] > 0:
            with st.expander(f"묶음 대표 씬 목록 ({bundle_info['count']}개)", expanded=False):
                st.write(sorted(bundle_info['scenes']))

    with col2:
        korean_info = priority_details['korean_text']
        include_korean = st.checkbox(
            f"☑️ 한글 텍스트 씬 ({korean_info['count']}개)",
            value=step1_state.get('include_korean', True),
            key="step1_include_korean",
            help="한글 오버레이가 들어갈 씬들. 실사 배경 위에 텍스트가 더 자연스러움"
        )
        step1_state['include_korean'] = include_korean

        if include_korean and korean_info['count'] > 0:
            with st.expander(f"한글 텍스트 씬 목록 ({korean_info['count']}개)", expanded=False):
                st.write(sorted(korean_info['scenes']))

    # 1차 대상 계산
    selected_priority = set()

    if include_bundle:
        selected_priority |= bundle_info['scenes']

    if include_korean:
        selected_priority |= korean_info['scenes']

    # 중복 정보
    overlap_info = priority_details['overlap']

    # 1차 대상 요약 박스
    st.markdown(f"""
        <div style="
            background: linear-gradient(135deg, #1E3A5F 0%, #2D4A6F 100%);
            padding: 16px;
            border-radius: 10px;
            margin: 12px 0;
            border-left: 4px solid #3B82F6;
        ">
            <div style="font-size: 15px; font-weight: bold; margin-bottom: 8px;">
                📊 1차 대상 합계: <span style="color: #60A5FA;">{len(selected_priority)}개</span>
            </div>
            <div style="font-size: 13px; color: #9CA3AF;">
                묶음대표 {bundle_info['count'] if include_bundle else 0}개 +
                한글씬 {korean_info['count'] if include_korean else 0}개
                {f"(중복 {overlap_info['count']}개 제거)" if overlap_info['count'] > 0 and include_bundle and include_korean else ""}
            </div>
        </div>
    """, unsafe_allow_html=True)

    # 세션에 저장
    set_step1_priority_targets(selected_priority, priority_details)

    st.markdown("---")

    # ═══════════════════════════════════════════════════════════════
    # 🥈 2차 대상 (AI 추천)
    # ═══════════════════════════════════════════════════════════════

    st.markdown("### 🥈 2차 대상 (AI 추천) - 선택적")
    st.caption("1차 대상 외 씬에서 AI가 추가로 실사이미지 적합 씬을 추천합니다.")

    # AI 추천 대상 풀 (1차 대상 제외)
    ai_target_pool = priority_manager.get_remaining_for_ai(selected_priority)

    # 한글텍스트 씬도 제외 (파이프라인 기본 제외 대상)
    ai_target_pool = ai_target_pool - state.korean_text_scenes

    st.info(f"📦 AI 분석 대상: **{len(ai_target_pool)}개** (1차 대상 {len(selected_priority)}개 + 한글텍스트 {len(state.korean_text_scenes)}개 제외)")

    # AI 추천 실행
    col1, col2 = st.columns([3, 1])

    with col1:
        if st.button("🤖 AI 추가 추천 실행", type="secondary", use_container_width=True, key="step1_ai_analyze"):
            with st.spinner("AI가 씬을 분석 중..."):
                # AI 추천 (1차 대상 제외된 풀에서만)
                ai_results = recommend_real_image_from_pool(ai_target_pool, scenes, threshold=3.0)
                ai_recommended = set(r[0] for r in ai_results)

                set_step1_ai_recommended(ai_recommended)
                st.session_state['step1_ai_results'] = ai_results
                st.success(f"✅ AI 추천 완료: **{len(ai_recommended)}개** 씬 추가 추천")

    with col2:
        skip_ai = st.checkbox("AI 추천 건너뛰기", key="step1_skip_ai")

    # AI 추천 결과
    ai_analyzed = step1_state.get('ai_analyzed', False)
    ai_recommended = step1_state.get('ai_recommended', set())
    ai_results = st.session_state.get('step1_ai_results', [])

    selected_ai = set()

    if ai_analyzed and ai_recommended and not skip_ai:
        st.markdown(f"**✅ AI 추천 결과: {len(ai_recommended)}개 씬**")

        # AI 추천 씬 선택
        default_ai_ids = sorted(ai_recommended)
        selected_ai_list = st.multiselect(
            "AI 추천 씬 선택 (수정 가능)",
            options=default_ai_ids,
            default=default_ai_ids[:min(30, len(default_ai_ids))],  # 기본 최대 30개
            key="step1_ai_selected"
        )
        selected_ai = set(selected_ai_list)

        # AI 추천 상세
        if ai_results:
            with st.expander(f"AI 추천 상세 (상위 15개)", expanded=False):
                for scene_id, score, reasons in ai_results[:15]:
                    scene = next((s for s in scenes if (s.get('scene_id') or s.get('id')) == scene_id), None)
                    if scene:
                        script = scene.get('script', '')[:80]
                        st.caption(f"**씬 {scene_id}** (점수: {score:.1f}) - {', '.join(reasons)}")
                        st.caption(f"   └ {script}...")

    elif skip_ai:
        st.info("AI 추천을 건너뜁니다. 1차 대상만 사용합니다.")

    st.markdown("---")

    # ═══════════════════════════════════════════════════════════════
    # 📊 최종 대상 통합
    # ═══════════════════════════════════════════════════════════════

    st.markdown("### 📊 최종 실사이미지 대체 대상")

    # 최종 통합
    final_targets = selected_priority | selected_ai

    # 메트릭 표시
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "🥇 1차 대상",
            f"{len(selected_priority)}개",
            help="묶음 대표 + 한글 씬"
        )

    with col2:
        st.metric(
            "🥈 2차 대상 (AI)",
            f"{len(selected_ai)}개",
            help="AI가 추가 추천한 씬"
        )

    with col3:
        percentage = len(final_targets) / total_scenes * 100 if total_scenes > 0 else 0
        st.metric(
            "📌 총 대상",
            f"{len(final_targets)}개",
            f"{percentage:.1f}%"
        )

    # 최종 대상 요약 박스
    st.markdown(f"""
        <div style="
            background: linear-gradient(135deg, #10B981 0%, #059669 100%);
            padding: 16px;
            border-radius: 10px;
            margin: 12px 0;
            color: white;
        ">
            <div style="font-size: 16px; font-weight: bold; margin-bottom: 8px;">
                📷 실사이미지 대체 대상: {len(final_targets)}개 ({percentage:.1f}%)
            </div>
            <div style="font-size: 13px; opacity: 0.9;">
                🥇 1차(자동): {len(selected_priority)}개 | 🥈 2차(AI): {len(selected_ai)}개
            </div>
        </div>
    """, unsafe_allow_html=True)

    # 대상 씬 목록
    with st.expander(f"📋 최종 대상 씬 목록 ({len(final_targets)}개)", expanded=False):
        # 분류별 표시
        if selected_priority:
            st.markdown("**🥇 1차 대상 (묶음대표 + 한글):**")
            st.write(sorted(selected_priority))

        if selected_ai:
            st.markdown("**🥈 2차 대상 (AI 추천):**")
            st.write(sorted(selected_ai))

    st.markdown("---")

    # 확정 버튼
    col1, col2, col3 = st.columns([2, 1, 1])

    with col1:
        if st.button("✅ 대상 확정 및 저장", type="primary", use_container_width=True, key="step1_confirm"):
            # 파이프라인 상태에 저장
            state.real_image_scenes = final_targets

            # Step 1 상세 정보도 저장
            if hasattr(state, 'step1_details'):
                state.step1_details = {
                    'priority_bundle': bundle_info['scenes'] if include_bundle else set(),
                    'priority_korean': korean_info['scenes'] if include_korean else set(),
                    'priority_total': selected_priority,
                    'ai_recommended': selected_ai,
                    'final_targets': final_targets
                }

            # 상태 저장
            set_step1_final_targets(final_targets)
            confirm_step1()

            if save_callback:
                save_callback()

            st.success(f"✅ **{len(final_targets)}개** 씬이 실사이미지 대체 대상으로 확정되었습니다!")
            st.balloons()

    with col2:
        if st.button("➡️ Step 2로", key="step1_next"):
            if not state.real_image_scenes:
                st.warning("먼저 대상을 확정해주세요.")
            else:
                state.current_step = PipelineStep.INFOGRAPHIC
                if save_callback:
                    save_callback()
                st.rerun()

    with col3:
        if st.button("🔄 초기화", key="step1_reset"):
            state.real_image_scenes = set()
            reset_step1_state()
            if 'step1_ai_results' in st.session_state:
                del st.session_state['step1_ai_results']
            if save_callback:
                save_callback()
            st.rerun()

    return None


def render_step1_result_summary(state: PipelineState) -> None:
    """Step 1 결과 요약 카드"""

    if not state.real_image_scenes:
        return

    step1_state = get_step1_state()
    priority_details = step1_state.get('priority_details', {})

    bundle_count = len(priority_details.get('bundle_representative', {}).get('scenes', set()))
    korean_count = len(priority_details.get('korean_text', {}).get('scenes', set()))
    ai_count = len(step1_state.get('ai_recommended', set()))
    final_count = len(state.real_image_scenes)

    st.markdown(f"""
        <div style="
            background: linear-gradient(135deg, #10B981 0%, #059669 100%);
            padding: 16px;
            border-radius: 12px;
            color: white;
            margin-bottom: 16px;
        ">
            <h4 style="margin: 0 0 12px 0;">📷 Step 1 완료: 실사이미지 대체</h4>

            <div style="display: flex; gap: 20px; flex-wrap: wrap;">
                <div>
                    <div style="font-size: 28px; font-weight: bold;">{final_count}개</div>
                    <div style="font-size: 12px; opacity: 0.8;">총 대상</div>
                </div>
                <div style="border-left: 1px solid rgba(255,255,255,0.3); padding-left: 20px;">
                    <div style="font-size: 14px;">🥇 1차: {bundle_count + korean_count}개</div>
                    <div style="font-size: 12px; opacity: 0.8;">
                        묶음대표 {bundle_count} + 한글 {korean_count}
                    </div>
                </div>
                <div style="border-left: 1px solid rgba(255,255,255,0.3); padding-left: 20px;">
                    <div style="font-size: 14px;">🥈 2차: {ai_count}개</div>
                    <div style="font-size: 12px; opacity: 0.8;">AI 추천</div>
                </div>
            </div>
        </div>
    """, unsafe_allow_html=True)


# ============================================================
# 내보내기
# ============================================================

__all__ = [
    'render_step1_real_image_enhanced',
    'render_step1_result_summary'
]
