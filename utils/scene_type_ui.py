# -*- coding: utf-8 -*-
"""
utils/scene_type_ui.py
씬 타입 UI 통합 모듈

스토리보드 페이지에서 사용하는 씬 타입 관련 UI 함수들을 제공합니다.

작성: 2025-01
"""

import streamlit as st
from pathlib import Path
from typing import List, Dict, Set, Optional, Tuple

# 씬 타입 모듈 로드
try:
    from utils.scene_types import (
        SceneType,
        SCENE_TYPE_CONFIG,
        SceneTypeManager,
        get_scene_type_badge_html,
        get_character_badge_html
    )
    from utils.scene_type_state import (
        init_scene_type_state,
        get_scene_type_manager,
        save_scene_types_to_file,
        load_scene_types_from_file,
        sync_scene_types_with_data,
        get_scene_type_for_display,
        get_type_statistics_for_ui
    )
    from utils.scene_replacement_recommender import (
        recommend_real_image_replacement,
        recommend_video_replacement,
        recommend_infographic_replacement,
        recommend_character_composite,
        get_all_recommendations,
        get_recommendation_summary,
        suggest_character_pose,
        suggest_character_expression,
        analyze_character_position
    )
    from utils.image_character_compositor import (
        ImageCharacterCompositor,
        ImageCharacterPosition,
        get_image_position_presets,
        get_scale_presets,
        analyze_image_for_character_placement,
        quick_compose
    )
    SCENE_TYPE_UI_AVAILABLE = True
except ImportError as e:
    SCENE_TYPE_UI_AVAILABLE = False
    print(f"[SceneTypeUI] 씬 타입 모듈 로드 실패: {e}")

# 파이프라인 모듈 로드
try:
    from utils.pipeline_state import (
        PipelineState,
        PipelineStep,
        STEP_CONFIG,
        save_pipeline_state,
        load_pipeline_state,
        get_all_steps
    )
    from components.pipeline_workflow_ui import (
        render_pipeline_workflow,
        get_pipeline_state
    )
    PIPELINE_UI_AVAILABLE = True
except ImportError as e:
    PIPELINE_UI_AVAILABLE = False
    print(f"[SceneTypeUI] 파이프라인 모듈 로드 실패: {e}")


def is_scene_type_available() -> bool:
    """씬 타입 기능 사용 가능 여부"""
    return SCENE_TYPE_UI_AVAILABLE


def init_scene_type_for_project(project_path: Path):
    """프로젝트 씬 타입 초기화"""
    if not SCENE_TYPE_UI_AVAILABLE:
        return

    init_scene_type_state(project_path)


def render_scene_type_expander(
    scenes: List[Dict],
    project_path: Path
) -> Tuple[Set[int], str]:
    """
    씬 타입 필터 Expander 렌더링

    Args:
        scenes: 씬 데이터 리스트
        project_path: 프로젝트 경로

    Returns:
        (필터된 씬 ID 집합, 필터 라벨)
    """
    if not SCENE_TYPE_UI_AVAILABLE:
        all_ids = {s.get("scene_id") or s.get("id", i+1) for i, s in enumerate(scenes)}
        return all_ids, "전체"

    with st.expander("🏷️ 씬 타입 필터 (Flow 1/2/3)", expanded=False):
        return render_scene_type_filter_content(scenes, project_path)


def render_scene_type_filter_content(
    scenes: List[Dict],
    project_path: Path
) -> Tuple[Set[int], str]:
    """
    씬 타입 필터 내용 렌더링

    Returns:
        (필터된 씬 ID 집합, 필터 라벨)
    """
    if not SCENE_TYPE_UI_AVAILABLE:
        all_ids = {s.get("scene_id") or s.get("id", i+1) for i, s in enumerate(scenes)}
        return all_ids, "전체"

    # 탭 구성
    tab1, tab2, tab3 = st.tabs([
        "🔍 대체 대상 소팅",
        "📦 타입별 관리",
        "🎭 캐릭터 합성"
    ])

    filtered_ids = set()
    filter_label = "전체"

    with tab1:
        filtered_ids, filter_label = _render_flow1_ui(scenes, project_path)

    with tab2:
        _render_flow2_ui(scenes, project_path)

    with tab3:
        _render_flow3_ui(scenes, project_path)

    return filtered_ids, filter_label


def _render_flow1_ui(
    scenes: List[Dict],
    project_path: Path
) -> Tuple[Set[int], str]:
    """Flow 1: 대체 대상 씬 소팅"""

    st.markdown("##### 🔍 대체 대상 씬 AI 추천")

    # AI 추천 버튼
    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("📷 실사이미지", key="st_f1_real", use_container_width=True):
            with st.spinner("분석 중..."):
                results = recommend_real_image_replacement(scenes)
                st.session_state.st_f1_results = ("real_image", results)

    with col2:
        if st.button("🎬 비디오", key="st_f1_video", use_container_width=True):
            with st.spinner("분석 중..."):
                results = recommend_video_replacement(scenes)
                st.session_state.st_f1_results = ("video", results)

    with col3:
        if st.button("📊 인포그래픽", key="st_f1_info", use_container_width=True):
            with st.spinner("분석 중..."):
                results = recommend_infographic_replacement(scenes)
                st.session_state.st_f1_results = ("infographic", results)

    # 결과 표시
    filtered_ids = set()
    filter_label = "전체"

    if 'st_f1_results' in st.session_state:
        rec_type, results = st.session_state.st_f1_results

        type_info = {
            "real_image": ("📷 실사이미지", "#10B981"),
            "video": ("🎬 비디오", "#EF4444"),
            "infographic": ("📊 인포그래픽", "#8B5CF6")
        }
        label, color = type_info.get(rec_type, ("추천", "#6B7280"))

        if results:
            st.success(f"{label} 추천: **{len(results)}개** 씬")

            # 추천 씬 ID 목록
            filtered_ids = {r.scene_id for r in results}
            filter_label = f"{label} 추천 ({len(results)}개)"

            # 상위 결과 표시
            with st.container():
                for r in results[:5]:
                    st.caption(f"씬 {r.scene_id}: {', '.join(r.reasons[:2])}")

                if len(results) > 5:
                    st.caption(f"... 외 {len(results) - 5}개")
        else:
            st.info("추천 결과 없음")

    # 필터 결과 없으면 전체
    if not filtered_ids:
        filtered_ids = {s.get("scene_id") or s.get("id", i+1) for i, s in enumerate(scenes)}
        filter_label = "전체"

    return filtered_ids, filter_label


def _render_flow2_ui(
    scenes: List[Dict],
    project_path: Path
):
    """Flow 2: 타입별 관리"""

    st.markdown("##### 📦 씬 타입 분포")

    total = len(scenes)
    stats = get_type_statistics_for_ui(total)

    # 타입별 프로그레스 바
    for scene_type in SceneType:
        # v1.1: KeyError 방지 - .get() 사용
        default_stats = {
            "count": 0,
            "percentage": 0.0,
            "emoji": SCENE_TYPE_CONFIG.get(scene_type, {}).get("emoji", "❓"),
            "label": SCENE_TYPE_CONFIG.get(scene_type, {}).get("label", "Unknown")
        }
        type_stats = stats.get("by_type", {}).get(scene_type, default_stats)
        count = type_stats.get("count", 0)
        percentage = type_stats.get("percentage", 0.0)
        emoji = type_stats.get("emoji", "❓")
        label = type_stats.get("label", "Unknown")

        col1, col2 = st.columns([1, 3])
        with col1:
            st.caption(f"{emoji} {label}")
        with col2:
            st.progress(min(percentage / 100, 1.0), text=f"{count}개 ({percentage:.1f}%)")

    # 캐릭터 합성 현황
    char_stats = stats["character_stats"]
    st.info(f"🎭 캐릭터: 합성 {char_stats['composited']}개 | 대기 {char_stats['pending']}개")


def _render_flow3_ui(
    scenes: List[Dict],
    project_path: Path
):
    """Flow 3: 캐릭터 합성"""

    st.markdown("##### 🎭 캐릭터 합성 설정")

    # 캐릭터 경로
    char_dir = project_path / "characters" / "representative"
    char_images = []
    if char_dir.exists():
        char_images = list(char_dir.glob("*.png")) + list(char_dir.glob("*.jpg"))

    if char_images:
        char_path = st.selectbox(
            "캐릭터 이미지",
            options=char_images,
            format_func=lambda x: x.name,
            key="st_f3_char"
        )
    else:
        st.warning("캐릭터 이미지 없음. `characters/representative/` 폴더에 PNG 파일을 추가하세요.")
        char_path = None

    # 위치/크기
    col1, col2 = st.columns(2)
    with col1:
        position = st.selectbox(
            "합성 위치",
            ["right_bottom", "left_bottom", "center_bottom"],
            format_func=lambda x: {
                "right_bottom": "↘️ 우하단",
                "left_bottom": "↙️ 좌하단",
                "center_bottom": "⬇️ 하단 중앙"
            }.get(x, x),
            key="st_f3_pos"
        )
    with col2:
        scale = st.slider("크기", 0.15, 0.45, 0.30, 0.05, key="st_f3_scale")

    # AI 추천
    if st.button("🤖 캐릭터 합성 적합 씬 분석", key="st_f3_analyze"):
        with st.spinner("분석 중..."):
            results = recommend_character_composite(scenes)
            st.session_state.st_f3_results = results
            st.success(f"**{len(results)}개** 씬 추천")

    # 추천 결과
    if 'st_f3_results' in st.session_state:
        results = st.session_state.st_f3_results
        if results:
            st.caption(f"추천 씬: {', '.join(str(r.scene_id) for r in results[:10])}{'...' if len(results) > 10 else ''}")


def render_scene_card_type_badge(scene_id: int) -> str:
    """
    씬 카드에 표시할 타입 배지 HTML

    Args:
        scene_id: 씬 ID

    Returns:
        HTML 문자열
    """
    if not SCENE_TYPE_UI_AVAILABLE:
        return ""

    display = get_scene_type_for_display(scene_id)

    html = display.get("badge_html", "")
    if display.get("has_character"):
        char_html = display.get("character_badge_html", "")
        if char_html:
            html += f" {char_html}"

    return html


def execute_character_composite(
    scenes: List[Dict],
    scene_ids: List[int],
    character_path: str,
    position: str,
    scale: float,
    project_path: Path,
    progress_callback=None
) -> Dict[int, Tuple[bool, str]]:
    """
    캐릭터 합성 실행

    Args:
        scenes: 씬 데이터 리스트
        scene_ids: 합성할 씬 ID 리스트
        character_path: 캐릭터 이미지 경로
        position: 위치 프리셋
        scale: 크기 비율
        project_path: 프로젝트 경로
        progress_callback: 진행 콜백

    Returns:
        {scene_id: (success, result_path or error), ...}
    """
    if not SCENE_TYPE_UI_AVAILABLE:
        return {}

    # 출력 디렉토리
    output_dir = project_path / "images" / "composited_with_char"

    # 합성기 생성
    compositor = ImageCharacterCompositor(str(output_dir))

    # 씬 ID -> 이미지 경로 매핑
    scene_map = {
        (s.get("scene_id") or s.get("id", i+1)): s
        for i, s in enumerate(scenes)
    }

    results = {}
    total = len(scene_ids)

    for idx, scene_id in enumerate(scene_ids):
        if progress_callback:
            progress_callback(idx + 1, total, f"씬 {scene_id} 합성 중")

        scene = scene_map.get(scene_id)
        if not scene:
            results[scene_id] = (False, "씬 데이터 없음")
            continue

        # 이미지 경로 찾기
        img_path = (
            scene.get("composite_path") or
            scene.get("image_path") or
            scene.get("background_image") or
            scene.get("cloudinary_url")
        )

        if not img_path or not Path(img_path).exists():
            results[scene_id] = (False, "이미지 없음")
            continue

        # 합성 실행
        success, result = compositor.compose_scene_with_character(
            scene_id=scene_id,
            scene_image_path=str(img_path),
            character_image_path=str(character_path),
            position_preset=position,
            scale=scale
        )

        results[scene_id] = (success, result)

        # 성공하면 타입 매니저에 기록
        if success:
            manager = get_scene_type_manager()
            manager.mark_character_composite(
                scene_id,
                position,
                str(character_path),
                result
            )

    # 저장
    save_scene_types_to_file(project_path)

    return results


def sync_scene_types_from_data(
    scenes: List[Dict],
    project_path: Path,
    overwrite: bool = False
) -> int:
    """
    씬 데이터에서 타입 정보 동기화

    Returns:
        동기화된 씬 수
    """
    if not SCENE_TYPE_UI_AVAILABLE:
        return 0

    return sync_scene_types_with_data(project_path, scenes, overwrite)


def is_pipeline_available() -> bool:
    """파이프라인 기능 사용 가능 여부"""
    return PIPELINE_UI_AVAILABLE


def render_pipeline_expander(
    scenes: List[Dict],
    project_path: Path
) -> Optional[Set[int]]:
    """
    파이프라인 워크플로우 Expander 렌더링

    Args:
        scenes: 씬 데이터 리스트
        project_path: 프로젝트 경로

    Returns:
        현재 단계의 필터된 씬 ID 집합 또는 None
    """
    if not PIPELINE_UI_AVAILABLE:
        st.warning("파이프라인 모듈을 사용할 수 없습니다.")
        return None

    with st.expander("🔄 파이프라인 워크플로우 (순차 소거)", expanded=False):
        return render_pipeline_workflow(scenes, project_path)


def render_combined_workflow_expander(
    scenes: List[Dict],
    project_path: Path
) -> Tuple[Set[int], str]:
    """
    씬 타입 필터와 파이프라인을 통합한 워크플로우 Expander

    Args:
        scenes: 씬 데이터 리스트
        project_path: 프로젝트 경로

    Returns:
        (필터된 씬 ID 집합, 필터 라벨)
    """
    if not SCENE_TYPE_UI_AVAILABLE:
        all_ids = {s.get("scene_id") or s.get("id", i+1) for i, s in enumerate(scenes)}
        return all_ids, "전체"

    with st.expander("🎯 씬 워크플로우 (타입 필터 + 파이프라인)", expanded=False):
        # 탭 구성
        if PIPELINE_UI_AVAILABLE:
            tab1, tab2, tab3, tab4 = st.tabs([
                "🔄 파이프라인",
                "🔍 대체 대상 소팅",
                "📦 타입별 관리",
                "🎭 캐릭터 합성"
            ])
        else:
            tab1, tab2, tab3 = st.tabs([
                "🔍 대체 대상 소팅",
                "📦 타입별 관리",
                "🎭 캐릭터 합성"
            ])

        filtered_ids = set()
        filter_label = "전체"

        if PIPELINE_UI_AVAILABLE:
            with tab1:
                st.markdown("##### 🔄 순차 소거 파이프라인")
                st.caption("AI 비용 최적화: 저비용 단계부터 처리하여 고비용 단계의 처리량 최소화")

                pipeline_ids = render_pipeline_workflow(scenes, project_path)
                if pipeline_ids:
                    filtered_ids = pipeline_ids

                    # 파이프라인 상태에서 현재 단계 가져오기
                    pipeline_state = get_pipeline_state(project_path, scenes)
                    if pipeline_state:
                        current_step = pipeline_state.current_step
                        step_cfg = STEP_CONFIG.get(current_step, {})
                        filter_label = f"파이프라인: {step_cfg.get('emoji', '')} {step_cfg.get('label', current_step.value)}"

            with tab2:
                flow1_ids, flow1_label = _render_flow1_ui(scenes, project_path)
                if not filtered_ids:
                    filtered_ids = flow1_ids
                    filter_label = flow1_label

            with tab3:
                _render_flow2_ui(scenes, project_path)

            with tab4:
                _render_flow3_ui(scenes, project_path)
        else:
            with tab1:
                flow1_ids, flow1_label = _render_flow1_ui(scenes, project_path)
                filtered_ids = flow1_ids
                filter_label = flow1_label

            with tab2:
                _render_flow2_ui(scenes, project_path)

            with tab3:
                _render_flow3_ui(scenes, project_path)

        # 필터 결과 없으면 전체
        if not filtered_ids:
            filtered_ids = {s.get("scene_id") or s.get("id", i+1) for i, s in enumerate(scenes)}
            filter_label = "전체"

        return filtered_ids, filter_label


def get_pipeline_summary(scenes: List[Dict], project_path: Path) -> Dict:
    """
    파이프라인 진행 상황 요약

    Returns:
        {
            "available": bool,
            "current_step": str,
            "completed_steps": int,
            "total_steps": int,
            "remaining_pool_size": int,
            "total_processed": int,
            "ai_savings_percent": float
        }
    """
    if not PIPELINE_UI_AVAILABLE:
        return {"available": False}

    pipeline_state = get_pipeline_state(project_path, scenes)
    if not pipeline_state:
        return {"available": False}

    all_steps = get_all_steps()
    completed = sum(1 for s in all_steps if pipeline_state.is_step_completed(s))

    current_pool = pipeline_state.get_remaining_pool(pipeline_state.current_step)
    total_processed = sum(len(pipeline_state.processed_scenes.get(s.value, set())) for s in all_steps)

    # AI 비용 절감 계산 (대략적)
    total_scenes = len(scenes)
    if total_scenes > 0:
        # 파이프라인 없이 모든 씬에 고비용 처리 시
        baseline_cost = total_scenes * 3  # 고비용(video) 기준
        # 순차 소거로 실제 처리량
        actual_cost = 0
        for step in all_steps:
            pool_size = len(pipeline_state.get_remaining_pool(step))
            cost_level = STEP_CONFIG.get(step, {}).get("ai_cost", 1)
            actual_cost += pool_size * cost_level

        savings = max(0, (baseline_cost - actual_cost) / baseline_cost * 100) if baseline_cost > 0 else 0
    else:
        savings = 0

    return {
        "available": True,
        "current_step": pipeline_state.current_step.value,
        "completed_steps": completed,
        "total_steps": len(all_steps),
        "remaining_pool_size": len(current_pool),
        "total_processed": total_processed,
        "ai_savings_percent": savings
    }


# 내보내기
__all__ = [
    # 씬 타입 기능
    'is_scene_type_available',
    'init_scene_type_for_project',
    'render_scene_type_expander',
    'render_scene_type_filter_content',
    'render_scene_card_type_badge',
    'execute_character_composite',
    'sync_scene_types_from_data',
    'SCENE_TYPE_UI_AVAILABLE',
    # 파이프라인 기능
    'is_pipeline_available',
    'render_pipeline_expander',
    'render_combined_workflow_expander',
    'get_pipeline_summary',
    'PIPELINE_UI_AVAILABLE'
]
