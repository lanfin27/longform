# -*- coding: utf-8 -*-
"""
components/storyboard_workflow/progress_visualizer.py
워크플로우 진행률 시각화 (v1.0)
"""

import streamlit as st
from typing import Dict

from .scene_status import STEP_CONFIG


def render_workflow_progress(stats: Dict):
    """
    5단계 워크플로우 진행률 시각화

    Args:
        stats: WorkflowManager.get_statistics() 결과
    """
    st.markdown("### 📊 5단계 워크플로우 진행 현황")

    # Step 카드들
    cols = st.columns(5)

    for idx, step in enumerate(range(1, 6)):
        step_config = STEP_CONFIG.get(step, {})
        step_stats = stats.get(f'step{step}', {})

        pool = step_stats.get('pool', 0)
        assigned = step_stats.get('assigned', 0)
        completed = step_stats.get('completed', 0)
        pending = step_stats.get('pending', 0)

        # 상태 아이콘 결정
        if completed > 0 and pending == 0 and assigned > 0:
            status_icon = "✅"
            status_text = "완료"
        elif pending > 0:
            status_icon = "🔄"
            status_text = "진행중"
        elif assigned > 0:
            status_icon = "📋"
            status_text = "할당됨"
        else:
            status_icon = "⏳"
            status_text = "대기"

        # 진행률 계산
        pct = (completed / assigned * 100) if assigned > 0 else 0

        color = step_config.get('color', '#6B7280')
        emoji = step_config.get('emoji', '')
        name = step_config.get('name', f'Step {step}')

        with cols[idx]:
            st.markdown(f"""
                <div style="
                    background: linear-gradient(135deg, {color}15, {color}05);
                    border: 2px solid {color};
                    border-radius: 12px;
                    padding: 16px;
                    text-align: center;
                    min-height: 180px;
                ">
                    <div style="font-size: 28px; margin-bottom: 8px;">
                        {status_icon}
                    </div>
                    <div style="font-weight: 700; color: {color}; margin-bottom: 4px; font-size: 14px;">
                        Step {step}
                    </div>
                    <div style="font-size: 11px; color: #9CA3AF; margin-bottom: 8px;">
                        {emoji} {name}
                    </div>
                    <div style="
                        background: #374151;
                        border-radius: 4px;
                        height: 8px;
                        margin: 12px 0;
                        overflow: hidden;
                    ">
                        <div style="
                            background: {color};
                            height: 100%;
                            width: {pct}%;
                            transition: width 0.3s;
                        "></div>
                    </div>
                    <div style="font-size: 16px; font-weight: 700; color: #E5E7EB;">
                        {completed} / {assigned}
                    </div>
                    <div style="font-size: 10px; color: #6B7280; margin-top: 4px;">
                        대상: {pool}개
                    </div>
                </div>
            """, unsafe_allow_html=True)

    # 요약 통계
    st.markdown("---")

    sum_cols = st.columns(5)

    total = stats.get('total', 0)
    total_assigned = sum(stats.get(f'step{i}', {}).get('assigned', 0) for i in range(1, 6))
    total_completed = sum(stats.get(f'step{i}', {}).get('completed', 0) for i in range(1, 6))
    excluded = stats.get('excluded', 0)
    remaining = total - total_assigned - excluded

    with sum_cols[0]:
        st.metric("전체 씬", f"{total}개")

    with sum_cols[1]:
        st.metric("할당됨", f"{total_assigned}개", delta=None)

    with sum_cols[2]:
        st.metric("완료됨", f"{total_completed}개",
                 delta=f"{total_completed/total*100:.1f}%" if total > 0 else "0%")

    with sum_cols[3]:
        st.metric("남은 씬", f"{remaining}개")

    with sum_cols[4]:
        st.metric("제외됨", f"{excluded}개")


def render_step_progress_bar(step: int, stats: Dict):
    """개별 Step 진행률 바 렌더링"""
    step_stats = stats.get(f'step{step}', {})
    step_config = STEP_CONFIG.get(step, {})

    assigned = step_stats.get('assigned', 0)
    completed = step_stats.get('completed', 0)
    pool = step_stats.get('pool', 0)

    color = step_config.get('color', '#6B7280')

    pct = (completed / assigned * 100) if assigned > 0 else 0

    st.markdown(f"""
        <div style="margin: 8px 0;">
            <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
                <span style="font-size: 12px; color: #9CA3AF;">
                    진행률: {completed}/{assigned} ({pct:.0f}%)
                </span>
                <span style="font-size: 12px; color: #6B7280;">
                    대상 풀: {pool}개
                </span>
            </div>
            <div style="
                background: #374151;
                border-radius: 4px;
                height: 12px;
                overflow: hidden;
            ">
                <div style="
                    background: linear-gradient(90deg, {color}, {color}CC);
                    height: 100%;
                    width: {pct}%;
                    transition: width 0.3s;
                "></div>
            </div>
        </div>
    """, unsafe_allow_html=True)


def render_step_status_cards(manager, step: int):
    """Step 상태 카드들 렌더링 (할당됨, 완료됨 등)"""
    summary = manager.get_step_summary(step)

    cols = st.columns(4)

    with cols[0]:
        st.markdown(f"""
            <div style="
                background: #1F2937;
                border-radius: 8px;
                padding: 12px;
                text-align: center;
            ">
                <div style="font-size: 24px; font-weight: 700; color: #60A5FA;">
                    {summary['pool_count']}
                </div>
                <div style="font-size: 11px; color: #9CA3AF;">대상 풀</div>
            </div>
        """, unsafe_allow_html=True)

    with cols[1]:
        st.markdown(f"""
            <div style="
                background: #1F2937;
                border-radius: 8px;
                padding: 12px;
                text-align: center;
            ">
                <div style="font-size: 24px; font-weight: 700; color: #FBBF24;">
                    {summary['assigned_count']}
                </div>
                <div style="font-size: 11px; color: #9CA3AF;">할당됨</div>
            </div>
        """, unsafe_allow_html=True)

    with cols[2]:
        st.markdown(f"""
            <div style="
                background: #1F2937;
                border-radius: 8px;
                padding: 12px;
                text-align: center;
            ">
                <div style="font-size: 24px; font-weight: 700; color: #34D399;">
                    {summary['completed_count']}
                </div>
                <div style="font-size: 11px; color: #9CA3AF;">완료됨</div>
            </div>
        """, unsafe_allow_html=True)

    with cols[3]:
        st.markdown(f"""
            <div style="
                background: #1F2937;
                border-radius: 8px;
                padding: 12px;
                text-align: center;
            ">
                <div style="font-size: 24px; font-weight: 700; color: #F87171;">
                    {summary['pending_count']}
                </div>
                <div style="font-size: 11px; color: #9CA3AF;">대기중</div>
            </div>
        """, unsafe_allow_html=True)
