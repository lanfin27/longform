# -*- coding: utf-8 -*-
"""
components/storyboard_workflow/__init__.py
5단계 스토리보드 워크플로우 모듈

주요 컴포넌트:
1. WorkflowManager - 워크플로우 상태 관리
2. SceneStatus - 씬 상태 열거형
3. 진행률 시각화 UI
4. Step 1-5 개별 UI
"""

from .scene_status import (
    SceneStatus,
    SCENE_STATUS_CONFIG,
    STEP_CONFIG,
    get_status_from_string,
    get_status_config,
    get_step_config,
    get_status_badge_html
)

from .workflow_manager import (
    WorkflowManager,
    WorkflowState,
    get_workflow_manager,
    clear_workflow_manager_cache
)

__all__ = [
    # Scene Status
    'SceneStatus',
    'SCENE_STATUS_CONFIG',
    'STEP_CONFIG',
    'get_status_from_string',
    'get_status_config',
    'get_step_config',
    'get_status_badge_html',

    # Workflow Manager
    'WorkflowManager',
    'WorkflowState',
    'get_workflow_manager',
    'clear_workflow_manager_cache',
]


def render_5step_workflow(scenes: list, project_path):
    """
    5단계 워크플로우 메인 렌더 함수

    Args:
        scenes: 씬 데이터 리스트
        project_path: 프로젝트 경로
    """
    from .progress_visualizer import render_workflow_progress
    from .step1_korean_text import render_step1_ui
    from .step2_character import render_step2_ui
    from .step3_realshot import render_step3_ui
    from .step4_video import render_step4_ui
    from .step5_infographic import render_step5_ui

    import streamlit as st
    from pathlib import Path

    project_path = Path(project_path)

    # 워크플로우 관리자 로드
    manager = get_workflow_manager(project_path, scenes)

    # 진행률 시각화
    stats = manager.get_statistics()
    render_workflow_progress(stats)

    st.markdown("---")

    # Step 탭
    step_tabs = st.tabs([
        "🔤 Step 1: 한글 텍스트",
        "🎭 Step 2: 캐릭터 합성",
        "📷 Step 3: 실사 이미지",
        "🎬 Step 4: 비디오",
        "📊 Step 5: 인포그래픽"
    ])

    with step_tabs[0]:
        render_step1_ui(manager, scenes, project_path)

    with step_tabs[1]:
        render_step2_ui(manager, scenes, project_path)

    with step_tabs[2]:
        render_step3_ui(manager, scenes, project_path)

    with step_tabs[3]:
        render_step4_ui(manager, scenes, project_path)

    with step_tabs[4]:
        render_step5_ui(manager, scenes, project_path)
