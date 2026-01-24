# -*- coding: utf-8 -*-
"""
components/scene_type_filter.py
씬 타입 필터 UI 컴포넌트

Flow 1: 대체 대상 씬 소팅 (AI 추천 포함)
Flow 2: 대체 완료 씬 타입별 필터
Flow 3: 대표 캐릭터 자동 합성

작성: 2025-01
"""

import streamlit as st
from pathlib import Path
from typing import List, Dict, Set, Optional, Tuple

from utils.scene_types import (
    SceneType,
    SCENE_TYPE_CONFIG,
    get_scene_type_badge_html,
    get_character_badge_html
)
from utils.scene_type_state import (
    get_scene_type_manager,
    save_scene_types_to_file,
    get_type_statistics_for_ui,
    get_filtered_scene_ids_by_type,
    get_character_filter_scene_ids
)
from utils.scene_replacement_recommender import (
    recommend_real_image_replacement,
    recommend_video_replacement,
    recommend_infographic_replacement,
    recommend_character_composite,
    get_all_recommendations,
    get_recommendation_summary,
    RecommendationResult
)


# ============================================================
# Flow 1: 대체 대상 씬 소팅
# ============================================================

def render_flow1_sorting_filter(
    scenes: List[Dict],
    project_path: Path = None
) -> Tuple[Set[int], str]:
    """
    Flow 1: 대체 대상 씬 소팅 UI

    Args:
        scenes: 씬 데이터 리스트
        project_path: 프로젝트 경로

    Returns:
        (필터된 씬 ID 집합, 필터 라벨)
    """
    st.markdown("### 🔍 Flow 1: 대체 대상 씬 소팅")
    st.caption("실사이미지/비디오/인포그래픽으로 대체할 씬을 빠르게 선별합니다.")

    # 캐시된 추천 결과 가져오기
    if 'flow1_recommendations' not in st.session_state:
        st.session_state.flow1_recommendations = None

    # AI 추천 프리셋 버튼
    st.markdown("#### ⭐ AI 추천 프리셋")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        if st.button("📷 실사이미지 추천", use_container_width=True, key="f1_real_btn"):
            with st.spinner("분석 중..."):
                results = recommend_real_image_replacement(scenes)
                st.session_state.flow1_recommendations = ("real_image", results)
                st.session_state.flow1_filter_mode = "ai_recommend"

    with col2:
        if st.button("🎬 비디오 추천", use_container_width=True, key="f1_video_btn"):
            with st.spinner("분석 중..."):
                results = recommend_video_replacement(scenes)
                st.session_state.flow1_recommendations = ("video", results)
                st.session_state.flow1_filter_mode = "ai_recommend"

    with col3:
        if st.button("📊 인포그래픽 추천", use_container_width=True, key="f1_info_btn"):
            with st.spinner("분석 중..."):
                results = recommend_infographic_replacement(scenes)
                st.session_state.flow1_recommendations = ("infographic", results)
                st.session_state.flow1_filter_mode = "ai_recommend"

    with col4:
        if st.button("🔄 전체 분석", use_container_width=True, key="f1_all_btn"):
            with st.spinner("전체 분석 중..."):
                all_results = get_all_recommendations(scenes)
                st.session_state.flow1_all_recommendations = all_results
                st.session_state.flow1_filter_mode = "all"

    # AI 추천 결과 표시
    filtered_ids = set()
    filter_label = "전체"

    if st.session_state.get('flow1_filter_mode') == "ai_recommend":
        rec_type, results = st.session_state.flow1_recommendations or (None, [])

        if results:
            type_labels = {
                "real_image": ("📷 실사이미지", "#10B981"),
                "video": ("🎬 비디오", "#EF4444"),
                "infographic": ("📊 인포그래픽", "#8B5CF6")
            }
            label, color = type_labels.get(rec_type, ("추천", "#6B7280"))

            st.success(f"{label} 대체 추천: **{len(results)}개** 씬 발견")

            # 추천 결과 테이블
            with st.expander(f"📋 추천 상세 ({len(results)}개)", expanded=False):
                for r in results[:20]:  # 최대 20개
                    score_bar = "█" * int(r.score * 10) + "░" * (10 - int(r.score * 10))
                    st.markdown(f"""
                        **씬 {r.scene_id}** | {score_bar} {r.score:.0%}
                        - {', '.join(r.reasons)}
                    """)

                if len(results) > 20:
                    st.info(f"... 외 {len(results) - 20}개 더")

            filtered_ids = {r.scene_id for r in results}
            filter_label = f"{label} 추천 ({len(results)}개)"

    elif st.session_state.get('flow1_filter_mode') == "all":
        all_results = st.session_state.get('flow1_all_recommendations', {})
        summary = get_recommendation_summary(all_results)
        st.info(f"📊 전체 추천: {summary}")

    st.markdown("---")

    # 수동 필터 옵션
    st.markdown("#### 🎛️ 수동 필터")

    filter_cols = st.columns(4)

    with filter_cols[0]:
        f_korean = st.checkbox("🔤 한글 텍스트", key="f1_korean")
    with filter_cols[1]:
        f_no_image = st.checkbox("🖼️ 이미지 없음", key="f1_no_image")
    with filter_cols[2]:
        f_no_video = st.checkbox("🎬 비디오 없음", key="f1_no_video")
    with filter_cols[3]:
        f_bundle = st.checkbox("📦 묶음 대표만", key="f1_bundle")

    # 수동 필터 적용
    if any([f_korean, f_no_image, f_no_video, f_bundle]):
        from utils.storyboard_filter import (
            get_korean_text_scene_ids,
            get_no_image_scene_ids,
            get_no_video_scene_ids,
            get_bundle_representative_ids
        )

        manual_ids = set()
        labels = []

        all_ids = {s.get("scene_id") or s.get("id", i+1) for i, s in enumerate(scenes)}

        if f_korean:
            korean_ids = get_korean_text_scene_ids(scenes)
            manual_ids.update(korean_ids)
            labels.append(f"한글({len(korean_ids)})")

        if f_no_image:
            no_img_ids = get_no_image_scene_ids(scenes)
            manual_ids.update(no_img_ids)
            labels.append(f"이미지없음({len(no_img_ids)})")

        if f_no_video:
            no_vid_ids = get_no_video_scene_ids(scenes)
            manual_ids.update(no_vid_ids)
            labels.append(f"비디오없음({len(no_vid_ids)})")

        if f_bundle:
            bundle_ids = get_bundle_representative_ids(scenes)
            if manual_ids:
                manual_ids = manual_ids.intersection(bundle_ids)
            else:
                manual_ids = bundle_ids
            labels.append(f"묶음대표({len(bundle_ids)})")

        if manual_ids:
            filtered_ids = manual_ids
            filter_label = " + ".join(labels)

    # 필터 결과 없으면 전체
    if not filtered_ids:
        filtered_ids = {s.get("scene_id") or s.get("id", i+1) for i, s in enumerate(scenes)}
        filter_label = "전체"

    return filtered_ids, filter_label


# ============================================================
# Flow 2: 대체 완료 씬 타입별 필터
# ============================================================

def render_flow2_type_filter(
    scenes: List[Dict],
    project_path: Path = None
) -> Tuple[Set[int], str]:
    """
    Flow 2: 대체 완료 씬 타입별 필터 UI

    Args:
        scenes: 씬 데이터 리스트
        project_path: 프로젝트 경로

    Returns:
        (필터된 씬 ID 집합, 필터 라벨)
    """
    st.markdown("### 📦 Flow 2: 씬 타입별 필터")
    st.caption("이미 대체 완료된 씬들을 타입별로 확인합니다.")

    total_scenes = len(scenes)
    stats = get_type_statistics_for_ui(total_scenes)

    # 타입별 통계 차트
    st.markdown("#### 📊 씬 타입 분포")

    for scene_type in SceneType:
        # v1.1: KeyError 방지 - .get() 사용
        default_stats = {
            "count": 0,
            "percentage": 0.0,
            "emoji": SCENE_TYPE_CONFIG.get(scene_type, {}).get("emoji", "❓"),
            "label": SCENE_TYPE_CONFIG.get(scene_type, {}).get("label", "Unknown"),
            "color": SCENE_TYPE_CONFIG.get(scene_type, {}).get("color", "#999999")
        }
        type_stats = stats.get("by_type", {}).get(scene_type, default_stats)
        count = type_stats.get("count", 0)
        percentage = type_stats.get("percentage", 0.0)
        emoji = type_stats.get("emoji", "❓")
        label = type_stats.get("label", "Unknown")
        color = type_stats.get("color", "#999999")

        # 프로그레스 바
        bar_width = max(percentage, 2)  # 최소 2%

        col1, col2 = st.columns([1, 4])
        with col1:
            st.markdown(f"{emoji} {label}")
        with col2:
            st.progress(bar_width / 100, text=f"{count}개 ({percentage:.1f}%)")

    st.markdown("---")

    # 타입 필터 체크박스
    st.markdown("#### 🏷️ 씬 타입 선택")

    type_cols = st.columns(5)
    selected_types = []

    for idx, scene_type in enumerate(SceneType):
        # v1.1: KeyError 방지 - .get() 사용
        default_config = {"emoji": "❓", "label": "Unknown", "description": ""}
        config = SCENE_TYPE_CONFIG.get(scene_type, default_config)
        default_stats = {"count": 0}
        type_stats = stats.get("by_type", {}).get(scene_type, default_stats)

        with type_cols[idx]:
            is_selected = st.checkbox(
                f"{config.get('emoji', '❓')} {config.get('label', 'Unknown')}",
                key=f"f2_type_{scene_type.value}",
                help=f"{config.get('description', '')} ({type_stats.get('count', 0)}개)"
            )

            if is_selected:
                selected_types.append(scene_type)

    # 캐릭터 합성 필터
    st.markdown("#### 🎭 캐릭터 합성 상태")

    char_cols = st.columns(3)
    with char_cols[0]:
        f_char_all = st.radio(
            "캐릭터 필터",
            ["전체", "합성 완료", "미합성"],
            key="f2_char_filter",
            horizontal=True
        )

    # 필터 적용
    all_scene_ids = {s.get("scene_id") or s.get("id", i+1) for i, s in enumerate(scenes)}

    # 타입 필터
    if selected_types:
        filtered_ids = get_filtered_scene_ids_by_type(selected_types, all_scene_ids)
        type_labels = [SCENE_TYPE_CONFIG[t]["emoji"] + SCENE_TYPE_CONFIG[t]["label"] for t in selected_types]
        filter_label = " + ".join(type_labels)
    else:
        filtered_ids = all_scene_ids
        filter_label = "전체"

    # 캐릭터 필터 적용
    if f_char_all == "합성 완료":
        char_ids = get_character_filter_scene_ids("with_character", all_scene_ids)
        filtered_ids = filtered_ids.intersection(char_ids)
        filter_label += " (캐릭터 합성)"
    elif f_char_all == "미합성":
        char_ids = get_character_filter_scene_ids("without_character", all_scene_ids)
        filtered_ids = filtered_ids.intersection(char_ids)
        filter_label += " (캐릭터 미합성)"

    # 통계 요약
    composited = stats["character_stats"]["composited"]
    pending = stats["character_stats"]["pending"]
    st.info(f"🎭 캐릭터 합성: 완료 {composited}개 | 대기 {pending}개")

    return filtered_ids, filter_label


# ============================================================
# Flow 3: 대표 캐릭터 자동 합성
# ============================================================

def render_flow3_character_composite(
    scenes: List[Dict],
    project_path: Path = None
) -> Optional[Dict]:
    """
    Flow 3: 대표 캐릭터 자동 합성 UI

    Args:
        scenes: 씬 데이터 리스트
        project_path: 프로젝트 경로

    Returns:
        합성 설정 (실행 시) 또는 None
    """
    st.markdown("### 🎭 Flow 3: 대표 캐릭터 자동 합성")
    st.caption("완성된 씬에 시그니처 캐릭터를 자동으로 합성합니다.")

    # 대표 캐릭터 정보 확인
    st.markdown("#### 📌 대표 캐릭터 설정")

    char_col1, char_col2 = st.columns([1, 3])

    # 캐릭터 이미지 경로 입력
    with char_col1:
        char_path = project_path / "characters" / "representative" if project_path else None

        if char_path and char_path.exists():
            # 캐릭터 이미지 찾기
            char_images = list(char_path.glob("*.png")) + list(char_path.glob("*.jpg"))
            if char_images:
                st.image(str(char_images[0]), width=150)
            else:
                st.info("캐릭터 이미지 없음")
        else:
            st.warning("캐릭터 폴더 없음")

    with char_col2:
        # 캐릭터 이미지 경로 선택
        char_image_path = st.text_input(
            "캐릭터 이미지 경로",
            value=str(char_path / "default.png") if char_path else "",
            key="f3_char_path"
        )

        # 위치/크기 설정
        pos_col1, pos_col2 = st.columns(2)
        with pos_col1:
            position = st.selectbox(
                "합성 위치",
                ["right_bottom", "left_bottom", "center_bottom"],
                format_func=lambda x: {
                    "right_bottom": "↘️ 우하단",
                    "left_bottom": "↙️ 좌하단",
                    "center_bottom": "⬇️ 하단 중앙"
                }.get(x, x),
                key="f3_position"
            )
        with pos_col2:
            scale = st.slider(
                "캐릭터 크기",
                min_value=0.15,
                max_value=0.45,
                value=0.30,
                step=0.05,
                format="%.0f%%",
                key="f3_scale"
            )

    st.markdown("---")

    # 합성 대상 씬 분석
    st.markdown("#### 🎯 합성 대상 씬")

    manager = get_scene_type_manager()
    all_ids = {s.get("scene_id") or s.get("id", i+1) for i, s in enumerate(scenes)}
    candidates = manager.get_character_composite_candidates(all_ids)

    st.info(f"캐릭터 합성 가능한 씬: **{len(candidates)}개** (인포그래픽, 비디오, 실사, 일반 이미지)")

    # AI 분석 버튼
    if st.button("🤖 AI로 적합한 씬 자동 선별", type="primary", key="f3_analyze"):
        with st.spinner("씬 분석 중..."):
            results = recommend_character_composite(scenes)
            st.session_state.f3_recommendations = results
            st.success(f"**{len(results)}개** 씬이 캐릭터 합성에 적합합니다.")

    # 추천 결과 표시
    if 'f3_recommendations' in st.session_state and st.session_state.f3_recommendations:
        results = st.session_state.f3_recommendations

        with st.expander(f"📋 추천 씬 목록 ({len(results)}개)", expanded=True):
            # 선택 체크박스
            selected_for_composite = st.multiselect(
                "합성할 씬 선택",
                options=[r.scene_id for r in results],
                default=[r.scene_id for r in results[:10]],  # 기본 10개
                key="f3_selected_scenes"
            )

            for r in results[:15]:
                is_selected = r.scene_id in selected_for_composite
                icon = "✅" if is_selected else "⬜"
                st.markdown(f"{icon} **씬 {r.scene_id}** - {', '.join(r.reasons)}")

    # 실행 버튼
    st.markdown("---")

    exec_col1, exec_col2 = st.columns(2)

    with exec_col1:
        if st.button("🎨 선택 씬 배치 합성", use_container_width=True, key="f3_execute"):
            selected = st.session_state.get('f3_selected_scenes', [])
            if not selected:
                st.warning("합성할 씬을 선택해주세요.")
                return None

            if not char_image_path or not Path(char_image_path).exists():
                st.error("캐릭터 이미지 경로를 확인해주세요.")
                return None

            return {
                "action": "compose",
                "scene_ids": selected,
                "character_path": char_image_path,
                "position": position,
                "scale": scale
            }

    with exec_col2:
        if st.button("📋 합성 미리보기", use_container_width=True, key="f3_preview"):
            selected = st.session_state.get('f3_selected_scenes', [])
            if selected:
                return {
                    "action": "preview",
                    "scene_ids": selected[:3],  # 미리보기는 3개만
                    "character_path": char_image_path,
                    "position": position,
                    "scale": scale
                }

    return None


# ============================================================
# 통합 필터 탭
# ============================================================

def render_scene_filter_tabs(
    scenes: List[Dict],
    project_path: Path = None
) -> Tuple[Set[int], str, Optional[Dict]]:
    """
    씬 필터 탭 렌더링 (Flow 1, 2, 3)

    Args:
        scenes: 씬 데이터 리스트
        project_path: 프로젝트 경로

    Returns:
        (필터된 씬 ID 집합, 필터 라벨, 캐릭터 합성 설정)
    """
    tab1, tab2, tab3 = st.tabs([
        "🔍 대체 대상 소팅",
        "📦 타입별 관리",
        "🎭 캐릭터 합성"
    ])

    filtered_ids = set()
    filter_label = "전체"
    composite_config = None

    with tab1:
        filtered_ids, filter_label = render_flow1_sorting_filter(scenes, project_path)

    with tab2:
        filtered_ids_t2, filter_label_t2 = render_flow2_type_filter(scenes, project_path)
        # 탭 2가 활성화되면 해당 필터 적용
        if st.session_state.get('_active_filter_tab') == 'tab2':
            filtered_ids = filtered_ids_t2
            filter_label = filter_label_t2

    with tab3:
        composite_config = render_flow3_character_composite(scenes, project_path)

    return filtered_ids, filter_label, composite_config


# ============================================================
# 씬 카드 배지 렌더링
# ============================================================

def render_scene_type_badges(scene_id: int) -> str:
    """
    씬 카드용 타입 배지 HTML 생성

    Args:
        scene_id: 씬 ID

    Returns:
        HTML 문자열
    """
    from utils.scene_type_state import get_scene_type_for_display

    display_info = get_scene_type_for_display(scene_id)

    badges_html = display_info["badge_html"]

    if display_info["has_character"]:
        badges_html += " " + display_info["character_badge_html"]

    return badges_html


def render_scene_card_overlay(
    scene_id: int,
    position: str = "top-left"
) -> str:
    """
    씬 카드 오버레이 스타일 배지 HTML

    Args:
        scene_id: 씬 ID
        position: "top-left" | "top-right" | "bottom-left" | "bottom-right"

    Returns:
        위치가 지정된 배지 HTML
    """
    badges_html = render_scene_type_badges(scene_id)

    positions = {
        "top-left": "top: 8px; left: 8px;",
        "top-right": "top: 8px; right: 8px;",
        "bottom-left": "bottom: 8px; left: 8px;",
        "bottom-right": "bottom: 8px; right: 8px;"
    }

    pos_style = positions.get(position, positions["top-left"])

    return f"""
        <div style="
            position: absolute;
            {pos_style}
            z-index: 10;
        ">
            {badges_html}
        </div>
    """
