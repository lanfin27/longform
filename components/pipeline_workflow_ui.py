# -*- coding: utf-8 -*-
"""
components/pipeline_workflow_ui.py
씬 타입 변환 파이프라인 워크플로우 UI

AI 소모량 최소화를 위한 순차적 소거 방식 파이프라인 UI입니다.

작성: 2025-01
"""

import streamlit as st
from pathlib import Path
from typing import List, Dict, Set, Optional, Tuple

from utils.pipeline_state import (
    PipelineState,
    PipelineStep,
    STEP_CONFIG,
    save_pipeline_state,
    load_pipeline_state,
    get_step_config,
    get_all_steps
)
from utils.pipeline_recommender import (
    recommend_real_image_scenes,
    recommend_infographic_scenes,
    recommend_character_scenes,
    recommend_video_scenes,
    get_recommendation_summary,
    filter_by_confidence,
    RecommendResult
)
from components.pipeline_step1_ui import (
    render_step1_real_image_enhanced,
    render_step1_result_summary
)


# ============================================================
# 세션 상태 관리
# ============================================================

def get_pipeline_state(project_path: Path, scenes: List[Dict]) -> PipelineState:
    """파이프라인 상태 가져오기 (없으면 생성)"""
    state_key = f"pipeline_state_{project_path}"

    if state_key not in st.session_state:
        # 저장된 상태 로드 시도
        state = load_pipeline_state(project_path)

        if state is None:
            # 새 상태 생성
            state = PipelineState()
            state.initialize_from_scenes(scenes)

        st.session_state[state_key] = state

    return st.session_state[state_key]


def save_state(project_path: Path):
    """현재 상태 저장"""
    state_key = f"pipeline_state_{project_path}"
    if state_key in st.session_state:
        save_pipeline_state(st.session_state[state_key], project_path)


# ============================================================
# 메인 UI
# ============================================================

def render_pipeline_workflow(
    scenes: List[Dict],
    project_path: Path
) -> Optional[Dict]:
    """
    파이프라인 워크플로우 메인 UI

    Args:
        scenes: 씬 데이터 리스트
        project_path: 프로젝트 경로

    Returns:
        실행할 액션 정보 (있으면)
    """
    st.markdown("## 🎬 씬 타입 변환 파이프라인")
    st.caption("AI 소모량 최소화를 위한 순차적 소거 방식")

    # 파이프라인 상태
    state = get_pipeline_state(project_path, scenes)

    # 씬 데이터 동기화
    if len(state.total_scenes) != len(scenes):
        state.initialize_from_scenes(scenes)
        save_state(project_path)

    # 진행 상황 표시
    render_pipeline_progress(state)

    st.markdown("---")

    # 단계별 탭
    tabs = st.tabs([
        "🔴 Step 1: 실사이미지",
        "🟠 Step 2: 인포그래픽",
        "🟡 Step 3: 캐릭터",
        "🟢 Step 4: 비디오",
        "📊 결과"
    ])

    action = None

    with tabs[0]:
        # 우선 대상 기능 포함된 향상된 Step 1 UI 사용
        action = render_step1_real_image_enhanced(
            state, scenes, project_path,
            save_callback=lambda: save_state(project_path)
        ) or action

    with tabs[1]:
        action = render_step2_infographic(state, scenes, project_path) or action

    with tabs[2]:
        action = render_step3_character(state, scenes, project_path) or action

    with tabs[3]:
        action = render_step4_video(state, scenes, project_path) or action

    with tabs[4]:
        render_final_result(state, project_path)

    return action


def render_pipeline_progress(state: PipelineState):
    """파이프라인 진행 상황 시각화"""

    steps = get_all_steps()
    current_step = state.current_step

    # 현재 단계 인덱스
    try:
        current_idx = steps.index(current_step)
    except ValueError:
        current_idx = -1 if current_step == PipelineStep.INITIAL else len(steps)

    # 단계 표시
    cols = st.columns(len(steps))

    for idx, step in enumerate(steps):
        config = get_step_config(step)

        with cols[idx]:
            if idx < current_idx:
                # 완료
                st.markdown(f"""
                    <div style="
                        background: {config['color']};
                        color: white;
                        padding: 8px;
                        border-radius: 6px;
                        text-align: center;
                        font-size: 12px;
                    ">
                        ✅ {config['emoji']} {config['name'][:4]}
                    </div>
                """, unsafe_allow_html=True)
            elif idx == current_idx:
                # 현재
                st.markdown(f"""
                    <div style="
                        background: {config['color']};
                        color: white;
                        padding: 8px;
                        border-radius: 6px;
                        text-align: center;
                        font-size: 12px;
                        border: 2px solid white;
                        box-shadow: 0 0 8px {config['color']};
                    ">
                        🔄 {config['emoji']} {config['name'][:4]}
                    </div>
                """, unsafe_allow_html=True)
            else:
                # 대기
                st.markdown(f"""
                    <div style="
                        background: #374151;
                        color: #9CA3AF;
                        padding: 8px;
                        border-radius: 6px;
                        text-align: center;
                        font-size: 12px;
                    ">
                        ⏳ {config['emoji']} {config['name'][:4]}
                    </div>
                """, unsafe_allow_html=True)

    # 통계 요약
    stats = state.get_statistics()

    st.markdown("### 📊 현재 상태")

    m_cols = st.columns(6)

    with m_cols[0]:
        st.metric("전체", f"{stats['total']}개")
    with m_cols[1]:
        st.metric("🔤 한글", f"{stats['korean_text']['count']}개")
    with m_cols[2]:
        st.metric("📷 실사", f"{stats['real_image']['count']}개")
    with m_cols[3]:
        st.metric("📊 인포", f"{stats['infographic']['count']}개")
    with m_cols[4]:
        st.metric("🎬 비디오", f"{stats['video']['count']}개")
    with m_cols[5]:
        st.metric("🖼️ 일반", f"{stats['normal']['count']}개")


# ============================================================
# Step 1: 실사이미지
# ============================================================

def render_step1_real_image(
    state: PipelineState,
    scenes: List[Dict],
    project_path: Path
) -> Optional[Dict]:
    """Step 1: 실사이미지 대체"""

    config = get_step_config(PipelineStep.REAL_IMAGE)

    st.markdown(f"### {config['emoji']} Step 1: {config['name']}")
    st.caption(f"AI 소모: {config['ai_cost_label']} | {config['description']}")

    # 처리 가능한 씬 풀
    pool = state.get_remaining_pool(PipelineStep.REAL_IMAGE)

    st.info(f"📦 처리 가능한 씬: **{len(pool)}개** (한글텍스트 {len(state.korean_text_scenes)}개 제외)")

    # 이미 처리된 씬
    if state.real_image_scenes:
        st.success(f"✅ 대체 완료: **{len(state.real_image_scenes)}개**")
        with st.expander("대체된 씬 목록", expanded=False):
            st.write(sorted(state.real_image_scenes))

    st.markdown("---")

    # AI 추천
    col1, col2, col3 = st.columns([2, 1, 1])

    with col1:
        if st.button("🤖 AI 실사이미지 적합 씬 분석", type="primary", key="p1_analyze"):
            with st.spinner("씬 분석 중..."):
                results = recommend_real_image_scenes(pool, scenes)
                st.session_state['p1_results'] = results
                st.success(f"✅ {len(results)}개 씬 추천")

    with col2:
        if st.button("➡️ Step 2로", key="p1_next"):
            state.current_step = PipelineStep.INFOGRAPHIC
            save_state(project_path)
            st.rerun()

    with col3:
        if st.button("🔄 초기화", key="p1_reset"):
            state.real_image_scenes = set()
            save_state(project_path)
            st.rerun()

    # 추천 결과
    if 'p1_results' in st.session_state and st.session_state['p1_results']:
        results = st.session_state['p1_results']
        summary = get_recommendation_summary(results)

        st.markdown(f"#### 🎯 추천 씬 ({summary['count']}개)")
        st.caption(f"높음: {summary['high']} | 중간: {summary['medium']} | 낮음: {summary['low']}")

        # 신뢰도 필터
        confidence_filter = st.radio(
            "신뢰도 필터",
            ["전체", "높음+중간", "높음만"],
            horizontal=True,
            key="p1_conf"
        )

        if confidence_filter == "높음+중간":
            filtered = filter_by_confidence(results, "medium")
        elif confidence_filter == "높음만":
            filtered = filter_by_confidence(results, "high")
        else:
            filtered = results

        # 씬 선택
        default_ids = [r.scene_id for r in filtered[:20]]
        selected = st.multiselect(
            "실사이미지로 대체할 씬",
            options=[r.scene_id for r in filtered],
            default=default_ids,
            key="p1_selected"
        )

        # 상세 보기
        with st.expander("추천 상세", expanded=False):
            for r in filtered[:10]:
                icon = "🟢" if r.confidence == "high" else ("🟡" if r.confidence == "medium" else "🔴")
                st.markdown(f"{icon} **씬 {r.scene_id}** (점수: {r.score:.1f}) - {', '.join(r.reasons[:2])}")

        # 확정 버튼
        if st.button("✅ 선택한 씬 실사이미지로 대체 확정", key="p1_confirm"):
            state.add_to_step(PipelineStep.REAL_IMAGE, set(selected))
            save_state(project_path)
            st.success(f"{len(selected)}개 씬이 실사이미지로 대체되었습니다.")
            st.rerun()

    return None


# ============================================================
# Step 2: 인포그래픽
# ============================================================

def render_step2_infographic(
    state: PipelineState,
    scenes: List[Dict],
    project_path: Path
) -> Optional[Dict]:
    """Step 2: 인포그래픽 대체"""

    config = get_step_config(PipelineStep.INFOGRAPHIC)

    st.markdown(f"### {config['emoji']} Step 2: {config['name']}")
    st.caption(f"AI 소모: {config['ai_cost_label']} | {config['description']}")

    # 처리 가능한 씬 풀 (실사이미지 제외됨!)
    pool = state.get_remaining_pool(PipelineStep.INFOGRAPHIC)
    reduction = state.get_pool_reduction_info(PipelineStep.INFOGRAPHIC)

    # 소거 효과 강조
    if reduction['excluded_count'] > 0:
        st.success(f"""
            📦 처리 가능한 씬: **{len(pool)}개**

            ⚡ **소거 효과**: {', '.join(reduction['excluded_types'])} 제외됨
            → AI 작업량 {reduction['excluded_count']}개 감소! ({reduction['reduction_rate']:.1f}% 절감)
        """)
    else:
        st.info(f"📦 처리 가능한 씬: **{len(pool)}개**")

    # 이미 처리된 씬
    if state.infographic_scenes:
        st.success(f"✅ 대체 완료: **{len(state.infographic_scenes)}개**")

    st.markdown("---")

    # AI 추천
    col1, col2, col3 = st.columns([2, 1, 1])

    with col1:
        if st.button("🤖 AI 인포그래픽 적합 씬 분석", type="primary", key="p2_analyze"):
            with st.spinner("씬 분석 중..."):
                results = recommend_infographic_scenes(pool, scenes)
                st.session_state['p2_results'] = results
                st.success(f"✅ {len(results)}개 씬 추천")

    with col2:
        if st.button("➡️ Step 3로", key="p2_next"):
            state.current_step = PipelineStep.CHARACTER
            save_state(project_path)
            st.rerun()

    with col3:
        if st.button("🔄 초기화", key="p2_reset"):
            state.infographic_scenes = set()
            save_state(project_path)
            st.rerun()

    # 추천 결과
    if 'p2_results' in st.session_state and st.session_state['p2_results']:
        results = st.session_state['p2_results']
        summary = get_recommendation_summary(results)

        st.markdown(f"#### 🎯 추천 씬 ({summary['count']}개)")

        selected = st.multiselect(
            "인포그래픽으로 대체할 씬",
            options=[r.scene_id for r in results],
            default=[r.scene_id for r in results[:15]],
            key="p2_selected"
        )

        if st.button("✅ 선택한 씬 인포그래픽으로 대체 확정", key="p2_confirm"):
            state.add_to_step(PipelineStep.INFOGRAPHIC, set(selected))
            save_state(project_path)
            st.success(f"{len(selected)}개 씬이 인포그래픽으로 대체되었습니다.")
            st.rerun()

    return None


# ============================================================
# Step 3: 캐릭터 합성
# ============================================================

def render_step3_character(
    state: PipelineState,
    scenes: List[Dict],
    project_path: Path
) -> Optional[Dict]:
    """Step 3: 캐릭터 합성"""

    config = get_step_config(PipelineStep.CHARACTER)

    st.markdown(f"### {config['emoji']} Step 3: {config['name']}")
    st.caption(f"AI 소모: {config['ai_cost_label']} | {config['description']}")

    # 캐릭터 합성은 모든 타입 대상 (한글텍스트만 제외)
    pool = state.get_remaining_pool(PipelineStep.CHARACTER)

    st.info(f"""
        📦 처리 가능한 씬: **{len(pool)}개**

        ✅ 포함: 📷 실사이미지 + 📊 인포그래픽 + 🖼️ 일반이미지
        ❌ 제외: 🔤 한글텍스트 (오버레이 충돌 방지)
    """)

    # 이미 처리된 씬
    if state.character_composite_scenes:
        st.success(f"✅ 합성 완료: **{len(state.character_composite_scenes)}개**")

    st.markdown("---")

    # 캐릭터 설정
    st.markdown("#### 🎭 캐릭터 설정")

    char_col1, char_col2 = st.columns(2)

    with char_col1:
        # 캐릭터 이미지 경로
        char_dir = project_path / "characters" / "representative"
        char_images = []
        if char_dir.exists():
            char_images = list(char_dir.glob("*.png")) + list(char_dir.glob("*.jpg"))

        if char_images:
            char_path = st.selectbox(
                "캐릭터 이미지",
                options=char_images,
                format_func=lambda x: x.name,
                key="p3_char"
            )
        else:
            st.warning("캐릭터 이미지 없음")
            char_path = None

    with char_col2:
        position = st.selectbox(
            "합성 위치",
            ["right_bottom", "left_bottom", "center_bottom"],
            format_func=lambda x: {"right_bottom": "↘️ 우하단", "left_bottom": "↙️ 좌하단", "center_bottom": "⬇️ 하단중앙"}.get(x),
            key="p3_pos"
        )
        scale = st.slider("크기", 0.15, 0.45, 0.30, 0.05, key="p3_scale")

    st.markdown("---")

    # AI 추천
    col1, col2, col3 = st.columns([2, 1, 1])

    with col1:
        if st.button("🤖 AI 캐릭터 적합 씬 분석", type="primary", key="p3_analyze"):
            with st.spinner("씬 분석 중..."):
                results = recommend_character_scenes(pool, scenes)
                st.session_state['p3_results'] = results
                st.success(f"✅ {len(results)}개 씬 추천")

    with col2:
        if st.button("➡️ Step 4로", key="p3_next"):
            state.current_step = PipelineStep.VIDEO
            save_state(project_path)
            st.rerun()

    with col3:
        if st.button("🔄 초기화", key="p3_reset"):
            state.character_composite_scenes = set()
            save_state(project_path)
            st.rerun()

    # 추천 결과
    if 'p3_results' in st.session_state and st.session_state['p3_results']:
        results = st.session_state['p3_results']

        st.markdown(f"#### 🎯 추천 씬 ({len(results)}개)")

        selected = st.multiselect(
            "캐릭터 합성할 씬",
            options=[r.scene_id for r in results],
            default=[r.scene_id for r in results[:20]],
            key="p3_selected"
        )

        if st.button("✅ 선택한 씬에 캐릭터 합성 실행", key="p3_confirm"):
            state.add_to_step(PipelineStep.CHARACTER, set(selected))
            save_state(project_path)

            # 캐릭터 합성 액션 반환
            return {
                "action": "character_composite",
                "scene_ids": selected,
                "character_path": str(char_path) if char_path else None,
                "position": position,
                "scale": scale
            }

    return None


# ============================================================
# Step 4: 비디오
# ============================================================

def render_step4_video(
    state: PipelineState,
    scenes: List[Dict],
    project_path: Path
) -> Optional[Dict]:
    """Step 4: 비디오 변환"""

    config = get_step_config(PipelineStep.VIDEO)

    st.markdown(f"### {config['emoji']} Step 4: {config['name']}")
    st.caption(f"AI 소모: {config['ai_cost_label']} | {config['description']}")

    # 비디오 변환은 가장 좁은 풀
    pool = state.get_remaining_pool(PipelineStep.VIDEO)
    reduction = state.get_pool_reduction_info(PipelineStep.VIDEO)

    # 소거 효과 강조 (가장 큰 절감!)
    st.success(f"""
        📦 처리 가능한 씬: **{len(pool)}개**

        ⚡⚡⚡ **대폭 소거 효과**: {', '.join(reduction['excluded_types'])}
        → AI 작업량 **{reduction['excluded_count']}개 감소!** ({reduction['reduction_rate']:.1f}% 절감)
    """)

    st.warning("⚠️ 비디오 변환은 AI 비용이 가장 높습니다. 신중하게 선택하세요.")

    # 이미 처리된 씬
    if state.video_scenes:
        st.success(f"✅ 변환 완료: **{len(state.video_scenes)}개**")

    st.markdown("---")

    # AI 추천
    col1, col2, col3 = st.columns([2, 1, 1])

    with col1:
        if st.button("🤖 AI 비디오 적합 씬 분석", type="primary", key="p4_analyze"):
            with st.spinner("씬 분석 중..."):
                results = recommend_video_scenes(pool, scenes)
                st.session_state['p4_results'] = results
                st.success(f"✅ {len(results)}개 씬 추천")

    with col2:
        if st.button("✅ 파이프라인 완료", key="p4_complete"):
            state.current_step = PipelineStep.COMPLETED
            save_state(project_path)
            st.balloons()
            st.rerun()

    with col3:
        if st.button("🔄 초기화", key="p4_reset"):
            state.video_scenes = set()
            save_state(project_path)
            st.rerun()

    # 추천 결과
    if 'p4_results' in st.session_state and st.session_state['p4_results']:
        results = st.session_state['p4_results']

        st.markdown(f"#### 🎯 추천 씬 ({len(results)}개)")

        # 비디오는 신뢰도 높은 것만 기본 선택
        high_conf = filter_by_confidence(results, "high")

        selected = st.multiselect(
            "비디오로 변환할 씬 (신중하게 선택!)",
            options=[r.scene_id for r in results],
            default=[r.scene_id for r in high_conf[:10]],
            key="p4_selected"
        )

        if st.button("✅ 선택한 씬 비디오로 변환 확정", key="p4_confirm"):
            state.add_to_step(PipelineStep.VIDEO, set(selected))
            save_state(project_path)
            st.success(f"{len(selected)}개 씬이 비디오로 변환 예정입니다.")
            st.rerun()

    return None


# ============================================================
# 최종 결과
# ============================================================

def render_final_result(state: PipelineState, project_path: Path):
    """최종 결과 표시"""

    st.markdown("### 📊 최종 결과")

    # Step 1 결과 요약 카드 (우선 대상 정보 포함)
    if state.real_image_scenes:
        render_step1_result_summary(state)

    stats = state.get_statistics()
    savings = state.get_ai_cost_savings()

    # 분포 차트
    st.markdown("#### 씬 타입 분포")

    types_data = [
        ("🔤 한글텍스트", stats['korean_text']['count'], stats['korean_text']['percentage'], "#3B82F6"),
        ("📷 실사이미지", stats['real_image']['count'], stats['real_image']['percentage'], "#10B981"),
        ("📊 인포그래픽", stats['infographic']['count'], stats['infographic']['percentage'], "#8B5CF6"),
        ("🎬 비디오", stats['video']['count'], stats['video']['percentage'], "#EF4444"),
        ("🖼️ 일반이미지", stats['normal']['count'], stats['normal']['percentage'], "#6B7280"),
    ]

    for label, count, pct, color in types_data:
        bar_width = max(pct, 2)
        st.markdown(f"""
            <div style="display: flex; align-items: center; margin: 6px 0;">
                <span style="width: 100px; font-size: 13px;">{label}</span>
                <div style="flex: 1; background: #374151; border-radius: 4px; height: 22px; margin: 0 8px;">
                    <div style="width: {bar_width}%; background: {color}; height: 100%; border-radius: 4px; display: flex; align-items: center; padding-left: 8px;">
                        <span style="color: white; font-size: 11px;">{count}개</span>
                    </div>
                </div>
                <span style="width: 50px; text-align: right; font-size: 12px;">{pct:.1f}%</span>
            </div>
        """, unsafe_allow_html=True)

    st.markdown("---")

    # 캐릭터 합성 현황
    st.markdown(f"#### 🎭 캐릭터 합성: {stats['character_composite']['count']}개 씬")

    st.markdown("---")

    # AI 비용 절감 요약
    st.markdown("#### 💰 AI 비용 절감 효과")

    st.success(f"""
        **비디오 변환 단계에서 {savings['saved_scenes']}개 씬 소거됨!**

        - 원래 처리 대상: {savings['base_pool']}개
        - 실제 처리 대상: {savings['video_pool']}개
        - 📷 실사이미지로 제외: {savings['excluded_by_real_image']}개
        - 📊 인포그래픽으로 제외: {savings['excluded_by_infographic']}개

        **→ 예상 AI 비용 절감: {savings['savings_rate']:.1f}%**
    """)

    # 파이프라인 리셋
    if st.button("🔄 파이프라인 전체 초기화", key="p_reset_all"):
        state.reset()
        save_state(project_path)
        st.rerun()
