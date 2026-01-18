# -*- coding: utf-8 -*-
"""
utils/storyboard_filter.py
스토리보드 필터링 유틸리티 (v2.0)

주요 기능:
1. 묶음 대표 씬 필터링
2. 한글 텍스트 씬 필터링
3. 복합 필터 지원 (합집합/교집합)
4. 씬 태그 생성
5. 빠른 프리셋 필터

v2.0 추가:
- 복합 필터 체크박스 지원
- 필터 조합 방식 (OR/AND)
- 빠른 프리셋 버튼
- 필터 결과 요약 확장
"""

import random
from typing import List, Dict, Set, Tuple, Optional
from collections import defaultdict


# ========================================
# 필터 프리셋 정의
# ========================================

FILTER_PRESETS = {
    "bundle_korean_or": {
        "name": "📦+🔤 묶음대표+한글 (OR)",
        "description": "묶음 대표 씬 또는 한글 텍스트 씬",
        "filters": {"bundle_representative": True, "korean_text": True},
        "mode": "union"
    },
    "bundle_korean_and": {
        "name": "📦∩🔤 묶음대표&한글 (AND)",
        "description": "묶음 대표이면서 한글 텍스트인 씬",
        "filters": {"bundle_representative": True, "korean_text": True},
        "mode": "intersection"
    },
    "korean_only": {
        "name": "🔤 한글 텍스트만",
        "description": "한글 텍스트 씬만",
        "filters": {"korean_text": True},
        "mode": "union"
    },
    "bundle_only": {
        "name": "📦 묶음 대표만",
        "description": "묶음 대표 씬만",
        "filters": {"bundle_representative": True},
        "mode": "union"
    },
    "not_generated": {
        "name": "⬜ 미생성만",
        "description": "이미지, 비디오 모두 없는 씬",
        "filters": {"not_generated": True},
        "mode": "union"
    },
    "clear_all": {
        "name": "📋 전체 보기",
        "description": "모든 필터 해제",
        "filters": {},
        "mode": "union"
    }
}


# 필터별 정보
FILTER_INFO = {
    "bundle_representative": {
        "name": "묶음 대표",
        "icon": "📦",
        "description": "각 묶음의 대표 씬"
    },
    "korean_text": {
        "name": "한글 텍스트",
        "icon": "🔤",
        "description": "한글 텍스트가 필요한 씬"
    },
    "no_image": {
        "name": "이미지 없음",
        "icon": "🖼️",
        "description": "이미지가 생성되지 않은 씬"
    },
    "no_video": {
        "name": "비디오 없음",
        "icon": "🎬",
        "description": "비디오가 생성되지 않은 씬"
    },
    "not_generated": {
        "name": "미생성",
        "icon": "⬜",
        "description": "이미지, 비디오 모두 없는 씬"
    }
}


def get_bundle_map(scenes: List[Dict]) -> Dict[int, List[Dict]]:
    """
    씬 목록에서 묶음 정보 추출

    Args:
        scenes: 씬 데이터 리스트

    Returns:
        {bundle_id: [scene1, scene2, ...], ...}
    """
    bundles = defaultdict(list)

    for scene in scenes:
        # bundle_id가 있으면 사용, 없으면 scene_id 사용 (묶음 없음)
        bid = scene.get('bundle_id', scene.get('scene_id', 0))
        bundles[bid].append(scene)

    # scene_id 순으로 정렬
    for bid in bundles:
        bundles[bid] = sorted(
            bundles[bid],
            key=lambda s: s.get('scene_id', s.get('id', 0))
        )

    return dict(bundles)


def get_bundle_representative_ids(
    scenes: List[Dict],
    mode: str = "first",
    exclude_korean: bool = False
) -> Set[int]:
    """
    묶음 대표 씬 ID 목록 반환

    Args:
        scenes: 전체 씬 목록
        mode: "first" | "last" | "random"
        exclude_korean: 한글 텍스트 씬 제외 여부

    Returns:
        묶음 대표 씬 ID set
    """
    bundles = get_bundle_map(scenes)
    representative_ids = set()

    for bundle_id, bundle_scenes in bundles.items():
        if not bundle_scenes:
            continue

        # 한글 제외 옵션
        if exclude_korean:
            non_korean = [s for s in bundle_scenes if not has_korean_text(s)]
            target_scenes = non_korean if non_korean else bundle_scenes  # 폴백
        else:
            target_scenes = bundle_scenes

        if mode == "first":
            selected = target_scenes[0]
        elif mode == "last":
            selected = target_scenes[-1]
        elif mode == "random":
            selected = random.choice(target_scenes)
        else:
            selected = target_scenes[0]

        scene_id = selected.get("scene_id") or selected.get("id", 0)
        if scene_id:
            representative_ids.add(scene_id)

    return representative_ids


def has_korean_text(scene: Dict) -> bool:
    """씬에 한글 텍스트가 있는지 확인"""
    korean_prompt = scene.get('image_prompt_korean_text', '')
    return bool(korean_prompt and korean_prompt.strip())


def get_korean_text_scene_ids(scenes: List[Dict]) -> Set[int]:
    """한글 텍스트 씬 ID 목록 반환"""
    korean_ids = set()

    for scene in scenes:
        if has_korean_text(scene):
            scene_id = scene.get("scene_id") or scene.get("id", 0)
            if scene_id:
                korean_ids.add(scene_id)

    return korean_ids


def get_scenes_with_image_ids(scenes: List[Dict]) -> Set[int]:
    """이미지가 있는 씬 ID 목록 반환"""
    image_ids = set()

    for scene in scenes:
        has_image = (
            scene.get("image_path") or
            scene.get("composite_path") or
            scene.get("background_image") or
            scene.get("cloudinary_url")
        )

        if has_image:
            scene_id = scene.get("scene_id") or scene.get("id", 0)
            if scene_id:
                image_ids.add(scene_id)

    return image_ids


def get_scenes_with_video_ids(scenes: List[Dict]) -> Set[int]:
    """비디오가 있는 씬 ID 목록 반환"""
    video_ids = set()

    for scene in scenes:
        if scene.get("video_path") or scene.get("background_video"):
            scene_id = scene.get("scene_id") or scene.get("id", 0)
            if scene_id:
                video_ids.add(scene_id)

    return video_ids


def apply_filters(
    scenes: List[Dict],
    filters: Dict,
    filter_mode: str = "union"
) -> Tuple[List[int], Dict[int, List[str]]]:
    """
    필터 적용 및 씬 태그 생성

    Args:
        scenes: 전체 씬 목록
        filters: 필터 설정
            {
                "bundle_representative": {"enabled": bool, "mode": str, "exclude_korean": bool},
                "korean_text": {"enabled": bool, "include": bool},
                "has_image": {"enabled": bool},
                "has_video": {"enabled": bool},
                "not_generated": {"enabled": bool}
            }
        filter_mode: "union" (합집합 OR) | "intersection" (교집합 AND)

    Returns:
        (필터된 씬 ID 목록, {scene_id: [tags], ...})
    """
    all_scene_ids = set(s.get("scene_id") or s.get("id", i + 1) for i, s in enumerate(scenes))
    scene_tags = {sid: [] for sid in all_scene_ids}
    filter_results = {}

    # 1. 묶음 대표 필터
    bundle_config = filters.get("bundle_representative", {})
    if bundle_config.get("enabled"):
        mode = bundle_config.get("mode", "first")
        exclude_korean = bundle_config.get("exclude_korean", False)
        bundle_rep_ids = get_bundle_representative_ids(scenes, mode, exclude_korean)
        filter_results["bundle_rep"] = bundle_rep_ids

        for sid in bundle_rep_ids:
            if sid in scene_tags:
                scene_tags[sid].append("bundle_rep")

    # 2. 한글 텍스트 필터
    korean_config = filters.get("korean_text", {})
    if korean_config.get("enabled"):
        korean_ids = get_korean_text_scene_ids(scenes)
        include = korean_config.get("include", True)

        if include:
            filter_results["korean_text"] = korean_ids
        else:
            filter_results["korean_text"] = all_scene_ids - korean_ids

    # 한글 텍스트 태그는 항상 표시 (필터 여부 무관)
    for scene in scenes:
        if has_korean_text(scene):
            sid = scene.get("scene_id") or scene.get("id", 0)
            if sid in scene_tags and "korean_text" not in scene_tags[sid]:
                scene_tags[sid].append("korean_text")

    # 3. 이미지 있는 씬 필터
    if filters.get("has_image", {}).get("enabled"):
        image_ids = get_scenes_with_image_ids(scenes)
        filter_results["has_image"] = image_ids

    # 4. 비디오 있는 씬 필터
    if filters.get("has_video", {}).get("enabled"):
        video_ids = get_scenes_with_video_ids(scenes)
        filter_results["has_video"] = video_ids

    # 5. 미생성 씬 필터
    if filters.get("not_generated", {}).get("enabled"):
        image_ids = get_scenes_with_image_ids(scenes)
        video_ids = get_scenes_with_video_ids(scenes)
        generated_ids = image_ids.union(video_ids)
        filter_results["not_generated"] = all_scene_ids - generated_ids

    # 필터 조합
    if not filter_results:
        return sorted(list(all_scene_ids)), scene_tags

    if filter_mode == "union":
        final_ids = set()
        for ids in filter_results.values():
            final_ids = final_ids.union(ids)
    else:  # intersection
        final_ids = all_scene_ids.copy()
        for ids in filter_results.values():
            final_ids = final_ids.intersection(ids)

    return sorted(list(final_ids)), scene_tags


def get_filter_summary(scenes: List[Dict], filters: Dict = None) -> Dict:
    """필터 결과 요약 정보 반환"""
    bundle_map = get_bundle_map(scenes)
    bundle_size = scenes[0].get("bundle_size", 1) if scenes else 1
    has_bundles = bundle_size > 1

    bundle_rep_ids = get_bundle_representative_ids(scenes, "first") if has_bundles else set()
    korean_ids = get_korean_text_scene_ids(scenes)
    image_ids = get_scenes_with_image_ids(scenes)
    video_ids = get_scenes_with_video_ids(scenes)

    overlap = bundle_rep_ids.intersection(korean_ids) if has_bundles else set()

    return {
        "total": len(scenes),
        "bundle_count": len(bundle_map) if has_bundles else 0,
        "bundle_size": bundle_size,
        "has_bundles": has_bundles,
        "bundle_rep_count": len(bundle_rep_ids),
        "korean_text_count": len(korean_ids),
        "has_image_count": len(image_ids),
        "has_video_count": len(video_ids),
        "overlap_count": len(overlap),
    }


def get_scene_tags_only(scenes: List[Dict]) -> Dict[int, List[str]]:
    """
    씬 태그만 생성 (필터 적용 없이)

    Returns:
        {scene_id: ["bundle_rep", "korean_text", ...], ...}
    """
    bundle_map = get_bundle_map(scenes)
    bundle_size = scenes[0].get("bundle_size", 1) if scenes else 1
    has_bundles = bundle_size > 1

    # 묶음 대표 씬 (첫 번째 씬)
    bundle_rep_ids = set()
    if has_bundles:
        for bundle_scenes in bundle_map.values():
            if bundle_scenes:
                first_scene_id = bundle_scenes[0].get("scene_id") or bundle_scenes[0].get("id", 0)
                if first_scene_id:
                    bundle_rep_ids.add(first_scene_id)

    # 태그 생성
    scene_tags = {}
    for scene in scenes:
        sid = scene.get("scene_id") or scene.get("id", 0)
        if not sid:
            continue

        tags = []

        # 묶음 대표 태그
        if sid in bundle_rep_ids:
            tags.append("bundle_rep")

        # 한글 텍스트 태그
        if has_korean_text(scene):
            tags.append("korean_text")

        scene_tags[sid] = tags

    return scene_tags


# ========================================
# v2.0: 복합 필터 지원
# ========================================

def get_no_image_scene_ids(scenes: List[Dict]) -> Set[int]:
    """이미지 없는 씬 ID 목록 반환"""
    no_image_ids = set()

    for scene in scenes:
        has_image = (
            scene.get("image_path") or
            scene.get("composite_path") or
            scene.get("background_image") or
            scene.get("cloudinary_url")
        )

        if not has_image:
            scene_id = scene.get("scene_id") or scene.get("id", 0)
            if scene_id:
                no_image_ids.add(scene_id)

    return no_image_ids


def get_no_video_scene_ids(scenes: List[Dict]) -> Set[int]:
    """비디오 없는 씬 ID 목록 반환"""
    no_video_ids = set()

    for scene in scenes:
        has_video = scene.get("video_path") or scene.get("background_video")

        if not has_video:
            scene_id = scene.get("scene_id") or scene.get("id", 0)
            if scene_id:
                no_video_ids.add(scene_id)

    return no_video_ids


def get_not_generated_scene_ids(scenes: List[Dict]) -> Set[int]:
    """미생성 씬 ID 반환 (이미지, 비디오 모두 없는 씬)"""
    image_ids = get_scenes_with_image_ids(scenes)
    video_ids = get_scenes_with_video_ids(scenes)
    generated_ids = image_ids.union(video_ids)

    all_ids = set()
    for scene in scenes:
        scene_id = scene.get("scene_id") or scene.get("id", 0)
        if scene_id:
            all_ids.add(scene_id)

    return all_ids - generated_ids


def apply_complex_filters(
    scenes: List[Dict],
    active_filters: Dict[str, bool],
    combine_mode: str = "union",
    bundle_mode: str = "first"
) -> Tuple[Set[int], Dict[str, Set[int]]]:
    """
    복합 필터 적용 (v2.0)

    Args:
        scenes: 전체 씬 목록
        active_filters: 활성화된 필터
            {
                "bundle_representative": bool,
                "korean_text": bool,
                "no_image": bool,
                "no_video": bool,
                "not_generated": bool
            }
        combine_mode: "union" (합집합 OR) | "intersection" (교집합 AND)
        bundle_mode: 묶음 대표 선택 방식 ("first", "last", "random")

    Returns:
        (최종 필터된 씬 ID set, {필터명: 씬 ID set, ...})
    """
    all_scene_ids = set()
    for scene in scenes:
        scene_id = scene.get("scene_id") or scene.get("id", 0)
        if scene_id:
            all_scene_ids.add(scene_id)

    # 각 필터별 결과 계산
    filter_results = {}

    if active_filters.get("bundle_representative"):
        filter_results["bundle_representative"] = get_bundle_representative_ids(
            scenes, mode=bundle_mode
        )

    if active_filters.get("korean_text"):
        filter_results["korean_text"] = get_korean_text_scene_ids(scenes)

    if active_filters.get("no_image"):
        filter_results["no_image"] = get_no_image_scene_ids(scenes)

    if active_filters.get("no_video"):
        filter_results["no_video"] = get_no_video_scene_ids(scenes)

    if active_filters.get("not_generated"):
        filter_results["not_generated"] = get_not_generated_scene_ids(scenes)

    # 필터가 하나도 선택되지 않은 경우 전체 반환
    if not filter_results:
        return all_scene_ids, {}

    # 필터 조합
    if combine_mode == "union":
        # 합집합 (OR): 하나라도 해당되면 포함
        final_ids = set()
        for ids in filter_results.values():
            final_ids = final_ids.union(ids)
    else:
        # 교집합 (AND): 모두 해당되어야 포함
        final_ids = all_scene_ids.copy()
        for ids in filter_results.values():
            final_ids = final_ids.intersection(ids)

    return final_ids, filter_results


def get_extended_filter_summary(
    scenes: List[Dict],
    active_filters: Dict[str, bool] = None,
    bundle_mode: str = "first"
) -> Dict:
    """
    확장된 필터 결과 요약 (v2.0)

    Returns:
        {
            "total": int,
            "bundle_representative": int,
            "korean_text": int,
            "no_image": int,
            "no_video": int,
            "not_generated": int,
            "bundle_korean_overlap": int,  # 묶음대표 ∩ 한글텍스트
            "union_result": int,            # 합집합 결과
            "intersection_result": int,     # 교집합 결과
            "has_bundles": bool,
            "bundle_size": int
        }
    """
    if active_filters is None:
        active_filters = {
            "bundle_representative": True,
            "korean_text": True,
            "no_image": False,
            "no_video": False,
            "not_generated": False
        }

    bundle_size = scenes[0].get("bundle_size", 1) if scenes else 1
    has_bundles = bundle_size > 1

    # 각 필터별 개수 계산
    bundle_rep_ids = get_bundle_representative_ids(scenes, bundle_mode) if has_bundles else set()
    korean_ids = get_korean_text_scene_ids(scenes)
    no_image_ids = get_no_image_scene_ids(scenes)
    no_video_ids = get_no_video_scene_ids(scenes)
    not_generated_ids = get_not_generated_scene_ids(scenes)

    # 교집합 (묶음대표 ∩ 한글텍스트)
    bundle_korean_overlap = bundle_rep_ids.intersection(korean_ids) if has_bundles else set()

    # 합집합/교집합 결과 계산
    union_ids, _ = apply_complex_filters(scenes, active_filters, "union", bundle_mode)
    intersection_ids, _ = apply_complex_filters(scenes, active_filters, "intersection", bundle_mode)

    return {
        "total": len(scenes),
        "bundle_representative": len(bundle_rep_ids),
        "korean_text": len(korean_ids),
        "no_image": len(no_image_ids),
        "no_video": len(no_video_ids),
        "not_generated": len(not_generated_ids),
        "bundle_korean_overlap": len(bundle_korean_overlap),
        "union_result": len(union_ids),
        "intersection_result": len(intersection_ids),
        "has_bundles": has_bundles,
        "bundle_size": bundle_size,
        # 개별 ID sets (필요시 사용)
        "_bundle_rep_ids": bundle_rep_ids,
        "_korean_ids": korean_ids,
        "_overlap_ids": bundle_korean_overlap
    }


def apply_preset_filter(
    scenes: List[Dict],
    preset_id: str,
    bundle_mode: str = "first"
) -> Tuple[Set[int], str, Dict[str, Set[int]]]:
    """
    프리셋 필터 적용

    Args:
        scenes: 씬 목록
        preset_id: 프리셋 ID
        bundle_mode: 묶음 대표 선택 방식

    Returns:
        (필터된 씬 ID set, 필터 모드, 필터별 결과)
    """
    preset = FILTER_PRESETS.get(preset_id)

    if not preset:
        # 프리셋이 없으면 전체 반환
        all_ids = set()
        for scene in scenes:
            scene_id = scene.get("scene_id") or scene.get("id", 0)
            if scene_id:
                all_ids.add(scene_id)
        return all_ids, "union", {}

    active_filters = preset.get("filters", {})
    combine_mode = preset.get("mode", "union")

    final_ids, filter_results = apply_complex_filters(
        scenes, active_filters, combine_mode, bundle_mode
    )

    return final_ids, combine_mode, filter_results


def get_filter_presets() -> Dict[str, dict]:
    """프리셋 목록 반환"""
    return FILTER_PRESETS.copy()


def get_filter_info() -> Dict[str, dict]:
    """필터 정보 반환"""
    return FILTER_INFO.copy()


def get_active_filter_labels(active_filters: Dict[str, bool], combine_mode: str) -> str:
    """활성화된 필터 라벨 문자열 생성"""
    labels = []

    for filter_key, is_active in active_filters.items():
        if is_active:
            info = FILTER_INFO.get(filter_key, {})
            icon = info.get("icon", "")
            name = info.get("name", filter_key)
            labels.append(f"{icon}{name}")

    if not labels:
        return "전체"

    separator = " + " if combine_mode == "union" else " ∩ "
    return separator.join(labels)
