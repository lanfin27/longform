# -*- coding: utf-8 -*-
"""
utils/bundle_utils.py
묶음(Bundle) 씬 대표 선택 유틸리티 (v1.0)

묶음 씬분석 기능으로 생성된 bundle_id를 기반으로
각 묶음에서 대표 씬을 선택하는 기능 제공

주요 기능:
1. 묶음별 씬 그룹화
2. 대표 씬 선택 (첫번째/마지막/랜덤)
3. 한글 텍스트 씬 제외 옵션
"""

import random
from typing import List, Dict, Set, Tuple, Optional
from collections import defaultdict


def get_bundle_map(scenes: List[Dict]) -> Dict[int, List[Dict]]:
    """
    씬 리스트를 bundle_id 기준으로 그룹화

    Args:
        scenes: 씬 데이터 리스트 (bundle_id 포함)

    Returns:
        {bundle_id: [scene1, scene2, ...]} 형태의 딕셔너리
    """
    bundle_map = defaultdict(list)

    for scene in scenes:
        bid = scene.get('bundle_id', scene.get('scene_id', 0))
        bundle_map[bid].append(scene)

    # scene_id 순으로 정렬
    for bid in bundle_map:
        bundle_map[bid] = sorted(
            bundle_map[bid],
            key=lambda s: s.get('scene_id', s.get('id', 0))
        )

    return dict(bundle_map)


def has_korean_text(scene: Dict) -> bool:
    """
    씬에 한글 텍스트가 있는지 확인

    Args:
        scene: 씬 데이터

    Returns:
        한글 텍스트 유무
    """
    korean_prompt = scene.get('image_prompt_korean_text', '')
    return bool(korean_prompt and korean_prompt.strip())


def get_scene_id(scene: Dict) -> int:
    """씬에서 scene_id 추출"""
    return scene.get('scene_id', scene.get('id', 0))


def select_bundle_representatives(
    scenes: List[Dict],
    mode: str = "first",
    exclude_korean: bool = False,
    random_count: int = 1
) -> Tuple[List[int], Dict[int, Dict]]:
    """
    각 묶음에서 대표 씬 선택

    Args:
        scenes: 전체 씬 리스트 (bundle_id 포함)
        mode: 선택 모드
            - "first": 묶음의 첫번째 씬
            - "last": 묶음의 마지막 씬
            - "random": 묶음에서 랜덤 N개
        exclude_korean: True면 한글 텍스트 씬 제외 (가능한 경우)
        random_count: random 모드일 때 묶음당 선택할 씬 수

    Returns:
        (selected_scene_ids, bundle_info)
        - selected_scene_ids: 선택된 씬 ID 리스트
        - bundle_info: 묶음별 선택 정보
          {bundle_id: {
              "total_scenes": int,
              "korean_scenes": int,
              "selected_scenes": [scene_id, ...],
              "fallback_used": bool  # 모든 씬이 한글이라 폴백 적용됨
          }}
    """
    if not scenes:
        return [], {}

    bundle_map = get_bundle_map(scenes)
    selected_ids = []
    bundle_info = {}

    for bid in sorted(bundle_map.keys()):
        bundle_scenes = bundle_map[bid]
        total_count = len(bundle_scenes)

        # 한글 텍스트 씬 분류
        korean_scenes = [s for s in bundle_scenes if has_korean_text(s)]
        non_korean_scenes = [s for s in bundle_scenes if not has_korean_text(s)]
        korean_count = len(korean_scenes)

        # 선택 대상 씬 결정
        fallback_used = False
        if exclude_korean and non_korean_scenes:
            # 한글 제외 가능
            target_scenes = non_korean_scenes
        elif exclude_korean and not non_korean_scenes:
            # 모든 씬이 한글 - 폴백으로 전체 씬 사용
            target_scenes = bundle_scenes
            fallback_used = True
        else:
            # 한글 제외 안함
            target_scenes = bundle_scenes

        # 모드별 선택
        selected = []

        if mode == "first":
            if target_scenes:
                selected = [get_scene_id(target_scenes[0])]

        elif mode == "last":
            if target_scenes:
                selected = [get_scene_id(target_scenes[-1])]

        elif mode == "random":
            if target_scenes:
                count = min(random_count, len(target_scenes))
                sampled = random.sample(target_scenes, count)
                selected = sorted([get_scene_id(s) for s in sampled])

        selected_ids.extend(selected)
        bundle_info[bid] = {
            "total_scenes": total_count,
            "korean_scenes": korean_count,
            "non_korean_scenes": total_count - korean_count,
            "selected_scenes": selected,
            "fallback_used": fallback_used,
            "scene_range": f"{get_scene_id(bundle_scenes[0])}-{get_scene_id(bundle_scenes[-1])}" if bundle_scenes else "N/A"
        }

    return sorted(selected_ids), bundle_info


def get_bundle_selection_preview(
    scenes: List[Dict],
    mode: str = "first",
    exclude_korean: bool = False,
    random_count: int = 1
) -> str:
    """
    묶음 대표 선택 미리보기 텍스트 생성

    Args:
        scenes: 씬 리스트
        mode: 선택 모드
        exclude_korean: 한글 제외 여부
        random_count: random 모드 시 선택 수

    Returns:
        미리보기 텍스트 (마크다운)
    """
    selected_ids, bundle_info = select_bundle_representatives(
        scenes, mode, exclude_korean, random_count
    )

    if not bundle_info:
        return "묶음 정보가 없습니다."

    lines = []
    lines.append(f"**선택 결과**: {len(selected_ids)}개 씬 / {len(bundle_info)}개 묶음")
    lines.append("")

    # 묶음별 상세
    fallback_count = sum(1 for info in bundle_info.values() if info.get("fallback_used"))
    if fallback_count > 0:
        lines.append(f"⚠️ {fallback_count}개 묶음에서 모든 씬이 한글이라 폴백 적용됨")
        lines.append("")

    lines.append("| 묶음 | 씬 범위 | 한글 | 선택 |")
    lines.append("|------|---------|------|------|")

    for bid in sorted(bundle_info.keys())[:10]:  # 최대 10개만 표시
        info = bundle_info[bid]
        range_str = info["scene_range"]
        korean_str = f"{info['korean_scenes']}/{info['total_scenes']}"
        selected_str = ", ".join(map(str, info["selected_scenes"]))
        fallback_mark = " ⚠️" if info.get("fallback_used") else ""
        lines.append(f"| {bid} | {range_str} | {korean_str} | {selected_str}{fallback_mark} |")

    if len(bundle_info) > 10:
        lines.append(f"| ... | (외 {len(bundle_info) - 10}개 묶음) | | |")

    return "\n".join(lines)


def get_bundle_stats(scenes: List[Dict]) -> Dict:
    """
    묶음 통계 정보 반환

    Args:
        scenes: 씬 리스트

    Returns:
        통계 딕셔너리
    """
    if not scenes:
        return {
            "total_scenes": 0,
            "total_bundles": 0,
            "korean_scenes": 0,
            "avg_scenes_per_bundle": 0,
            "has_bundles": False
        }

    bundle_map = get_bundle_map(scenes)
    korean_count = sum(1 for s in scenes if has_korean_text(s))

    # bundle_size가 1인 경우 묶음이 없는 것
    bundle_size = scenes[0].get('bundle_size', 1) if scenes else 1
    has_bundles = bundle_size > 1

    return {
        "total_scenes": len(scenes),
        "total_bundles": len(bundle_map),
        "korean_scenes": korean_count,
        "avg_scenes_per_bundle": len(scenes) / len(bundle_map) if bundle_map else 0,
        "bundle_size": bundle_size,
        "has_bundles": has_bundles
    }


# ============================================================
# Streamlit UI 컴포넌트
# ============================================================

def render_bundle_selection_ui(
    scenes: List[Dict],
    key_prefix: str = "bundle_select"
) -> Tuple[Optional[List[int]], str]:
    """
    묶음 대표 선택 UI 렌더링

    Args:
        scenes: 씬 리스트
        key_prefix: 위젯 키 프리픽스

    Returns:
        (selected_ids, mode_description)
        - selected_ids: 선택된 씬 ID 리스트 (None이면 적용 안함)
        - mode_description: 선택 모드 설명
    """
    import streamlit as st

    # 묶음 통계
    stats = get_bundle_stats(scenes)

    if not stats["has_bundles"]:
        st.info("ℹ️ 묶음 분석이 적용되지 않은 프로젝트입니다. (묶음 크기: 1)")
        return None, "묶음 없음"

    st.markdown(f"""
    **📊 묶음 현황**
    - 전체: {stats['total_scenes']}개 씬 / {stats['total_bundles']}개 묶음
    - 묶음당 평균: {stats['avg_scenes_per_bundle']:.1f}개 씬
    - 한글 텍스트 씬: {stats['korean_scenes']}개
    """)

    col1, col2 = st.columns(2)

    with col1:
        mode = st.selectbox(
            "선택 모드",
            options=["first", "last", "random"],
            format_func=lambda x: {
                "first": "🔢 첫번째 씬",
                "last": "🔢 마지막 씬",
                "random": "🎲 랜덤 선택"
            }.get(x, x),
            key=f"{key_prefix}_mode"
        )

    with col2:
        exclude_korean = st.checkbox(
            "🔤 한글 텍스트 씬 제외",
            value=False,
            help="한글 텍스트가 있는 씬을 제외하고 선택합니다. 묶음 내 모든 씬이 한글인 경우 첫번째/마지막 씬 선택으로 폴백됩니다.",
            key=f"{key_prefix}_exclude_korean"
        )

    # random 모드일 때 개수 선택
    random_count = 1
    if mode == "random":
        random_count = st.slider(
            "묶음당 선택 수",
            min_value=1,
            max_value=min(5, stats["bundle_size"]),
            value=1,
            key=f"{key_prefix}_random_count"
        )

    # 미리보기
    with st.expander("📋 선택 미리보기", expanded=False):
        preview = get_bundle_selection_preview(scenes, mode, exclude_korean, random_count)
        st.markdown(preview)

    # 적용 버튼
    selected_ids = None
    mode_desc = ""

    col1, col2 = st.columns([1, 2])
    with col1:
        if st.button("✅ 묶음 대표 선택 적용", key=f"{key_prefix}_apply", use_container_width=True):
            selected_ids, _ = select_bundle_representatives(
                scenes, mode, exclude_korean, random_count
            )
            mode_desc = {
                "first": "첫번째 씬",
                "last": "마지막 씬",
                "random": f"랜덤 {random_count}개"
            }.get(mode, mode)
            if exclude_korean:
                mode_desc += " (한글 제외)"
            st.success(f"✅ {len(selected_ids)}개 씬 선택됨")

    return selected_ids, mode_desc
