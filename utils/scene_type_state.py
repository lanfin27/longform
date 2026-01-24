# -*- coding: utf-8 -*-
"""
utils/scene_type_state.py
씬 타입 세션 상태 관리

Streamlit 세션 상태와 파일 저장/로드를 관리합니다.

작성: 2025-01
"""

import streamlit as st
import json
from pathlib import Path
from typing import Dict, List, Optional, Set

from utils.scene_types import (
    SceneType,
    SceneTypeManager,
    SceneTypeInfo,
    SCENE_TYPE_CONFIG,
    get_scene_type_badge_html,
    get_character_badge_html
)


# ============================================================
# 세션 상태 관리
# ============================================================

def init_scene_type_state(project_path: Path = None):
    """
    씬 타입 상태 초기화

    Args:
        project_path: 프로젝트 경로 (있으면 파일에서 로드)
    """
    if 'scene_type_manager' not in st.session_state:
        st.session_state.scene_type_manager = SceneTypeManager()

    # 프로젝트 경로가 주어지면 저장된 데이터 로드
    if project_path:
        load_scene_types_from_file(project_path)


def get_scene_type_manager() -> SceneTypeManager:
    """씬 타입 매니저 반환 (없으면 생성)"""
    if 'scene_type_manager' not in st.session_state:
        st.session_state.scene_type_manager = SceneTypeManager()
    return st.session_state.scene_type_manager


def reset_scene_type_state():
    """씬 타입 상태 초기화"""
    if 'scene_type_manager' in st.session_state:
        st.session_state.scene_type_manager.clear()


# ============================================================
# 파일 저장/로드
# ============================================================

def save_scene_types_to_file(project_path: Path) -> bool:
    """
    씬 타입 정보를 파일로 저장

    Args:
        project_path: 프로젝트 경로

    Returns:
        성공 여부
    """
    try:
        manager = get_scene_type_manager()
        data = manager.to_dict()

        save_path = project_path / "data" / "scene_types.json"
        save_path.parent.mkdir(parents=True, exist_ok=True)

        with open(save_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"[SceneTypeState] 저장 완료: {save_path} ({len(manager.scene_types)}개 씬)")
        return True

    except Exception as e:
        print(f"[SceneTypeState] 저장 실패: {e}")
        return False


def load_scene_types_from_file(project_path: Path) -> bool:
    """
    파일에서 씬 타입 정보 로드

    Args:
        project_path: 프로젝트 경로

    Returns:
        성공 여부
    """
    load_path = project_path / "data" / "scene_types.json"

    if not load_path.exists():
        print(f"[SceneTypeState] 저장된 데이터 없음: {load_path}")
        return False

    try:
        with open(load_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        manager = get_scene_type_manager()
        manager.from_dict(data)

        print(f"[SceneTypeState] 로드 완료: {len(manager.scene_types)}개 씬")
        return True

    except Exception as e:
        print(f"[SceneTypeState] 로드 실패: {e}")
        return False


def auto_save_on_change(project_path: Path):
    """변경 시 자동 저장 (데코레이터용)"""
    save_scene_types_to_file(project_path)


# ============================================================
# 씬 데이터 연동
# ============================================================

def sync_scene_types_with_data(
    project_path: Path,
    scenes: List[Dict],
    overwrite: bool = False
) -> int:
    """
    씬 데이터와 타입 정보 동기화

    Args:
        project_path: 프로젝트 경로
        scenes: 씬 데이터 리스트
        overwrite: 기존 타입 덮어쓰기 여부

    Returns:
        동기화된 씬 수
    """
    manager = get_scene_type_manager()

    # 씬 데이터에서 타입 자동 감지 및 설정
    before_count = len(manager.scene_types)
    manager.sync_from_scenes(scenes, overwrite=overwrite)
    after_count = len(manager.scene_types)

    # 파일 저장
    save_scene_types_to_file(project_path)

    return after_count - before_count


def get_scene_type_for_display(scene_id: int) -> Dict:
    """
    UI 표시용 씬 타입 정보 반환

    Returns:
        {
            "type": SceneType,
            "label": "한글텍스트",
            "emoji": "🔤",
            "color": "#3B82F6",
            "badge_html": "<span>...</span>",
            "has_character": True/False,
            "character_badge_html": "<span>...</span>" or None
        }
    """
    manager = get_scene_type_manager()
    info = manager.get_scene_info(scene_id)

    # v1.1: KeyError 방지를 위한 기본값
    default_config = {"label": "Unknown", "emoji": "❓", "color": "#999999"}

    if info:
        scene_type = info.scene_type
        config = SCENE_TYPE_CONFIG.get(scene_type, default_config)

        result = {
            "type": scene_type,
            "label": config.get("label", "Unknown"),
            "emoji": config.get("emoji", "❓"),
            "color": config.get("color", "#999999"),
            "badge_html": get_scene_type_badge_html(scene_type),
            "has_character": info.character_composite,
            "character_position": info.character_position
        }

        if info.character_composite:
            result["character_badge_html"] = get_character_badge_html(info.character_position)
        else:
            result["character_badge_html"] = None

        return result

    # 기본값 (NORMAL)
    config = SCENE_TYPE_CONFIG.get(SceneType.NORMAL, default_config)
    return {
        "type": SceneType.NORMAL,
        "label": config.get("label", "일반이미지"),
        "emoji": config.get("emoji", "🖼️"),
        "color": config.get("color", "#6B7280"),
        "badge_html": get_scene_type_badge_html(SceneType.NORMAL),
        "has_character": False,
        "character_badge_html": None
    }


# ============================================================
# 필터링 지원
# ============================================================

def get_filtered_scene_ids_by_type(
    selected_types: List[SceneType],
    all_scene_ids: Set[int] = None
) -> Set[int]:
    """
    선택된 타입의 씬 ID 반환

    Args:
        selected_types: 선택된 씬 타입 리스트
        all_scene_ids: 전체 씬 ID (미지정 씬 처리용)

    Returns:
        필터된 씬 ID 집합
    """
    manager = get_scene_type_manager()
    result = set()

    # 선택된 타입의 씬 추가
    for scene_type in selected_types:
        result.update(manager.get_scenes_by_type(scene_type))

    # NORMAL 타입이 선택되었고 all_scene_ids가 주어진 경우
    # 관리되지 않는 씬도 NORMAL로 간주하여 추가
    if SceneType.NORMAL in selected_types and all_scene_ids:
        managed_ids = set(manager.scene_types.keys())
        unmanaged_ids = all_scene_ids - managed_ids
        result.update(unmanaged_ids)

    return result


def get_character_filter_scene_ids(
    filter_type: str,
    all_scene_ids: Set[int] = None
) -> Set[int]:
    """
    캐릭터 합성 상태로 필터링

    Args:
        filter_type: "all" | "with_character" | "without_character"
        all_scene_ids: 전체 씬 ID

    Returns:
        필터된 씬 ID 집합
    """
    manager = get_scene_type_manager()

    if filter_type == "all":
        return all_scene_ids or set(manager.scene_types.keys())

    composited = set(manager.get_character_composited_scenes())

    if filter_type == "with_character":
        return composited
    elif filter_type == "without_character":
        if all_scene_ids:
            return all_scene_ids - composited
        else:
            return set(manager.scene_types.keys()) - composited

    return all_scene_ids or set()


# ============================================================
# 유틸리티 함수
# ============================================================

def get_type_statistics_for_ui(total_scenes: int) -> Dict:
    """
    UI용 통계 정보 반환

    Returns:
        {
            "by_type": {SceneType: {"count": int, "percentage": float, ...}},
            "character_stats": {"total": int, "composited": int, "pending": int},
            "summary": "한글텍스트 45개, 인포그래픽 8개, ..."
        }
    """
    manager = get_scene_type_manager()

    type_stats = manager.get_type_statistics(total_scenes)

    composited = len(manager.get_character_composited_scenes())
    candidates = len(manager.get_character_composite_candidates())

    # 요약 문자열 생성
    summary_parts = []
    for scene_type in SceneType:
        # v1.1: KeyError 방지를 위해 .get() 사용
        config = SCENE_TYPE_CONFIG.get(scene_type, {
            "label": "Unknown", "emoji": "❓", "color": "#999999",
            "bg_color": "#333333", "description": ""
        })
        default_stats = {
            "count": 0,
            "percentage": 0.0,
            "label": config["label"],
            "emoji": config["emoji"],
            "color": config["color"],
            "bg_color": config["bg_color"],
            "description": config.get("description", "")
        }
        stats = type_stats.get(scene_type, default_stats)
        if stats["count"] > 0:
            summary_parts.append(f"{stats['emoji']}{stats['label']} {stats['count']}개")

    return {
        "by_type": type_stats,
        "character_stats": {
            "total": total_scenes,
            "composited": composited,
            "pending": candidates
        },
        "summary": ", ".join(summary_parts) if summary_parts else "타입 미지정"
    }


def export_scene_types_for_report(project_path: Path) -> str:
    """
    리포트용 씬 타입 정보 내보내기 (마크다운)

    Returns:
        마크다운 형식의 리포트 문자열
    """
    manager = get_scene_type_manager()

    lines = ["## 씬 타입 분석 리포트", ""]

    # 타입별 목록
    for scene_type in SceneType:
        # v1.1: KeyError 방지 - .get() 사용
        default_config = {"emoji": "❓", "label": "Unknown"}
        config = SCENE_TYPE_CONFIG.get(scene_type, default_config)
        scene_ids = manager.get_scenes_by_type(scene_type)

        lines.append(f"### {config.get('emoji', '❓')} {config.get('label', 'Unknown')} ({len(scene_ids)}개)")

        if scene_ids:
            lines.append(f"씬 번호: {', '.join(map(str, sorted(scene_ids)))}")
        else:
            lines.append("해당 없음")

        lines.append("")

    # 캐릭터 합성 현황
    composited = manager.get_character_composited_scenes()
    lines.append(f"### 🎭 캐릭터 합성 완료 ({len(composited)}개)")
    if composited:
        lines.append(f"씬 번호: {', '.join(map(str, sorted(composited)))}")
    else:
        lines.append("해당 없음")

    return "\n".join(lines)


def batch_update_scene_types(
    project_path: Path,
    updates: Dict[int, SceneType]
) -> int:
    """
    여러 씬의 타입을 일괄 업데이트

    Args:
        project_path: 프로젝트 경로
        updates: {scene_id: SceneType} 딕셔너리

    Returns:
        업데이트된 씬 수
    """
    manager = get_scene_type_manager()

    for scene_id, scene_type in updates.items():
        manager.set_scene_type(scene_id, scene_type)

    save_scene_types_to_file(project_path)

    return len(updates)
