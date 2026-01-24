# -*- coding: utf-8 -*-
"""
utils/scene_types.py
씬 타입 관리 시스템

5가지 씬 타입:
1. KOREAN_TEXT - 한글 텍스트가 포함된 이미지
2. INFOGRAPHIC - 인포그래픽 탭에서 대체된 씬
3. VIDEO - 비디오로 변환/대체된 씬
4. REAL_IMAGE - 실사 이미지로 대체된 씬
5. NORMAL - 기본 AI 생성 이미지 씬

작성: 2025-01
"""

from enum import Enum
from typing import Dict, Set, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime
import json


class SceneType(Enum):
    """씬 타입 정의"""
    KOREAN_TEXT = "korean_text"       # 한글 텍스트 씬
    INFOGRAPHIC = "infographic"       # 인포그래픽 씬
    VIDEO = "video"                   # 비디오 씬
    REAL_IMAGE = "real_image"         # 실사 이미지 씬
    NORMAL = "normal"                 # 일반 이미지 씬


# 씬 타입별 설정
SCENE_TYPE_CONFIG = {
    SceneType.KOREAN_TEXT: {
        "label": "한글텍스트",
        "emoji": "🔤",
        "color": "#3B82F6",  # 파란색
        "bg_color": "#1E3A5F",
        "description": "한글 텍스트 오버레이 포함",
        "priority": 1  # 우선순위 (높을수록 우선)
    },
    SceneType.INFOGRAPHIC: {
        "label": "인포그래픽",
        "emoji": "📊",
        "color": "#8B5CF6",  # 보라색
        "bg_color": "#3D2A6B",
        "description": "인포그래픽으로 대체됨",
        "priority": 2
    },
    SceneType.VIDEO: {
        "label": "비디오",
        "emoji": "🎬",
        "color": "#EF4444",  # 빨간색
        "bg_color": "#5F1E1E",
        "description": "비디오로 변환됨",
        "priority": 3
    },
    SceneType.REAL_IMAGE: {
        "label": "실사이미지",
        "emoji": "📷",
        "color": "#10B981",  # 초록색
        "bg_color": "#1E5F4A",
        "description": "실사 이미지로 대체됨",
        "priority": 4
    },
    SceneType.NORMAL: {
        "label": "일반이미지",
        "emoji": "🖼️",
        "color": "#6B7280",  # 회색
        "bg_color": "#374151",
        "description": "기본 AI 생성 이미지",
        "priority": 5
    }
}


@dataclass
class SceneTypeInfo:
    """씬 타입 정보"""
    scene_id: int
    scene_type: SceneType = SceneType.NORMAL
    replaced_at: Optional[str] = None  # ISO format datetime
    original_type: Optional[str] = None
    character_composite: bool = False
    character_position: Optional[str] = None  # "left_bottom" | "right_bottom"
    character_image_path: Optional[str] = None
    composite_result_path: Optional[str] = None

    def to_dict(self) -> dict:
        """딕셔너리로 변환"""
        return {
            "scene_id": self.scene_id,
            "scene_type": self.scene_type.value,
            "replaced_at": self.replaced_at,
            "original_type": self.original_type,
            "character_composite": self.character_composite,
            "character_position": self.character_position,
            "character_image_path": self.character_image_path,
            "composite_result_path": self.composite_result_path
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'SceneTypeInfo':
        """딕셔너리에서 생성"""
        scene_type = SceneType(data.get("scene_type", "normal"))
        return cls(
            scene_id=data.get("scene_id", 0),
            scene_type=scene_type,
            replaced_at=data.get("replaced_at"),
            original_type=data.get("original_type"),
            character_composite=data.get("character_composite", False),
            character_position=data.get("character_position"),
            character_image_path=data.get("character_image_path"),
            composite_result_path=data.get("composite_result_path")
        )


class SceneTypeManager:
    """씬 타입 관리 클래스"""

    def __init__(self):
        self.scene_types: Dict[int, SceneTypeInfo] = {}
        self._cache_valid = False

    def set_scene_type(
        self,
        scene_id: int,
        scene_type: SceneType,
        preserve_character: bool = True
    ):
        """
        씬 타입 설정

        Args:
            scene_id: 씬 ID
            scene_type: 새 씬 타입
            preserve_character: 기존 캐릭터 합성 정보 유지 여부
        """
        now = datetime.now().isoformat()

        if scene_id in self.scene_types:
            old_info = self.scene_types[scene_id]
            new_info = SceneTypeInfo(
                scene_id=scene_id,
                scene_type=scene_type,
                replaced_at=now,
                original_type=old_info.scene_type.value,
                character_composite=old_info.character_composite if preserve_character else False,
                character_position=old_info.character_position if preserve_character else None,
                character_image_path=old_info.character_image_path if preserve_character else None,
                composite_result_path=old_info.composite_result_path if preserve_character else None
            )
        else:
            new_info = SceneTypeInfo(
                scene_id=scene_id,
                scene_type=scene_type,
                replaced_at=now
            )

        self.scene_types[scene_id] = new_info
        self._cache_valid = False
        print(f"[SceneType] 씬 {scene_id} 타입 설정: {scene_type.value}")

    def get_scene_type(self, scene_id: int) -> SceneType:
        """씬 타입 반환"""
        if scene_id in self.scene_types:
            return self.scene_types[scene_id].scene_type
        return SceneType.NORMAL

    def get_scene_info(self, scene_id: int) -> Optional[SceneTypeInfo]:
        """씬 타입 정보 전체 반환"""
        return self.scene_types.get(scene_id)

    def get_scenes_by_type(self, scene_type: SceneType) -> List[int]:
        """특정 타입의 씬 ID 목록 반환"""
        return [
            info.scene_id
            for info in self.scene_types.values()
            if info.scene_type == scene_type
        ]

    def get_scenes_by_types(self, scene_types: List[SceneType]) -> Set[int]:
        """여러 타입의 씬 ID 집합 반환"""
        result = set()
        for info in self.scene_types.values():
            if info.scene_type in scene_types:
                result.add(info.scene_id)
        return result

    def get_type_statistics(self, total_scenes: int) -> Dict:
        """
        타입별 통계 반환

        Args:
            total_scenes: 전체 씬 수

        Returns:
            {SceneType: {"count": int, "percentage": float, ...}, ...}
        """
        stats = {t: 0 for t in SceneType}

        for info in self.scene_types.values():
            stats[info.scene_type] += 1

        # 명시적으로 타입이 지정되지 않은 씬은 NORMAL로 간주
        assigned = sum(1 for info in self.scene_types.values() if info.scene_type != SceneType.NORMAL)
        # 전체에서 할당된 것을 빼면 미지정 씬
        unassigned = max(0, total_scenes - len(self.scene_types))
        stats[SceneType.NORMAL] += unassigned

        result = {}
        for scene_type, count in stats.items():
            # v1.1: KeyError 방지 - .get() 사용
            config = SCENE_TYPE_CONFIG.get(scene_type, {
                "label": "Unknown",
                "emoji": "❓",
                "color": "#999999",
                "bg_color": "#333333",
                "description": ""
            })
            result[scene_type] = {
                "count": count,
                "percentage": (count / total_scenes * 100) if total_scenes > 0 else 0,
                "label": config.get("label", "Unknown"),
                "emoji": config.get("emoji", "❓"),
                "color": config.get("color", "#999999"),
                "bg_color": config.get("bg_color", "#333333"),
                "description": config.get("description", "")
            }

        return result

    def mark_character_composite(
        self,
        scene_id: int,
        position: str,
        character_image_path: str = None,
        result_path: str = None
    ):
        """캐릭터 합성 완료 표시"""
        if scene_id in self.scene_types:
            info = self.scene_types[scene_id]
            info.character_composite = True
            info.character_position = position
            if character_image_path:
                info.character_image_path = character_image_path
            if result_path:
                info.composite_result_path = result_path
            print(f"[SceneType] 씬 {scene_id} 캐릭터 합성 완료: {position}")
        else:
            # 타입이 없으면 NORMAL로 생성 후 캐릭터 합성 표시
            self.scene_types[scene_id] = SceneTypeInfo(
                scene_id=scene_id,
                scene_type=SceneType.NORMAL,
                character_composite=True,
                character_position=position,
                character_image_path=character_image_path,
                composite_result_path=result_path
            )

    def clear_character_composite(self, scene_id: int):
        """캐릭터 합성 해제"""
        if scene_id in self.scene_types:
            info = self.scene_types[scene_id]
            info.character_composite = False
            info.character_position = None
            info.character_image_path = None
            info.composite_result_path = None

    def get_character_composite_candidates(self, all_scene_ids: Set[int] = None) -> List[int]:
        """
        캐릭터 합성 후보 씬 (타입 2,3,4,5 중 미합성)

        Args:
            all_scene_ids: 전체 씬 ID 집합 (없으면 관리 중인 씬만)
        """
        eligible_types = {
            SceneType.INFOGRAPHIC,
            SceneType.VIDEO,
            SceneType.REAL_IMAGE,
            SceneType.NORMAL
        }

        candidates = []

        # 관리 중인 씬에서 후보 찾기
        for info in self.scene_types.values():
            if info.scene_type in eligible_types and not info.character_composite:
                candidates.append(info.scene_id)

        # all_scene_ids가 주어지면 관리되지 않는 씬도 후보로 추가
        if all_scene_ids:
            managed_ids = set(self.scene_types.keys())
            unmanaged_ids = all_scene_ids - managed_ids
            candidates.extend(list(unmanaged_ids))

        return sorted(candidates)

    def get_character_composited_scenes(self) -> List[int]:
        """캐릭터 합성 완료된 씬 목록"""
        return [
            info.scene_id
            for info in self.scene_types.values()
            if info.character_composite
        ]

    def bulk_set_types(self, scene_ids: List[int], scene_type: SceneType):
        """여러 씬의 타입을 일괄 설정"""
        for scene_id in scene_ids:
            self.set_scene_type(scene_id, scene_type)

    def auto_detect_types(self, scenes: List[Dict]) -> Dict[int, SceneType]:
        """
        씬 데이터에서 타입 자동 감지

        Args:
            scenes: 씬 데이터 리스트

        Returns:
            {scene_id: SceneType, ...}
        """
        detected = {}

        for scene in scenes:
            scene_id = scene.get("scene_id") or scene.get("id", 0)
            if not scene_id:
                continue

            # 우선순위: 비디오 > 인포그래픽 > 실사 > 한글텍스트 > 일반
            if scene.get("video_path") or scene.get("background_video"):
                detected[scene_id] = SceneType.VIDEO
            elif scene.get("infographic_path") or scene.get("visual_type") == "infographic":
                detected[scene_id] = SceneType.INFOGRAPHIC
            elif scene.get("real_image_path") or scene.get("is_real_image"):
                detected[scene_id] = SceneType.REAL_IMAGE
            elif scene.get("image_prompt_korean_text"):
                detected[scene_id] = SceneType.KOREAN_TEXT
            else:
                detected[scene_id] = SceneType.NORMAL

        return detected

    def sync_from_scenes(self, scenes: List[Dict], overwrite: bool = False):
        """
        씬 데이터에서 타입 동기화

        Args:
            scenes: 씬 데이터 리스트
            overwrite: 기존 타입 덮어쓰기 여부
        """
        detected = self.auto_detect_types(scenes)

        for scene_id, scene_type in detected.items():
            if overwrite or scene_id not in self.scene_types:
                self.set_scene_type(scene_id, scene_type)

        print(f"[SceneType] {len(detected)}개 씬 타입 동기화 완료")

    def to_dict(self) -> dict:
        """전체 데이터를 딕셔너리로 변환"""
        return {
            "version": "1.0",
            "scenes": {
                str(scene_id): info.to_dict()
                for scene_id, info in self.scene_types.items()
            }
        }

    def from_dict(self, data: dict):
        """딕셔너리에서 데이터 로드"""
        self.scene_types.clear()

        scenes_data = data.get("scenes", {})
        for scene_id_str, info_data in scenes_data.items():
            try:
                scene_id = int(scene_id_str)
                info = SceneTypeInfo.from_dict(info_data)
                info.scene_id = scene_id  # ID 보장
                self.scene_types[scene_id] = info
            except (ValueError, KeyError) as e:
                print(f"[SceneType] 씬 {scene_id_str} 로드 실패: {e}")

        print(f"[SceneType] {len(self.scene_types)}개 씬 타입 로드 완료")

    def clear(self):
        """모든 데이터 초기화"""
        self.scene_types.clear()
        self._cache_valid = False


def get_scene_type_badge_html(scene_type: SceneType, size: str = "small") -> str:
    """
    씬 타입 배지 HTML 생성

    Args:
        scene_type: 씬 타입
        size: "small" | "medium" | "large"

    Returns:
        HTML 문자열
    """
    # v1.1: KeyError 방지 - .get() 사용
    config = SCENE_TYPE_CONFIG.get(scene_type, {
        "label": "Unknown",
        "emoji": "❓",
        "color": "#999999",
        "bg_color": "#333333"
    })

    sizes = {
        "small": {"padding": "2px 6px", "font_size": "10px"},
        "medium": {"padding": "4px 8px", "font_size": "12px"},
        "large": {"padding": "6px 12px", "font_size": "14px"}
    }

    style = sizes.get(size, sizes["small"])

    return f"""
        <span style="
            background: {config.get('color', '#999999')};
            color: white;
            padding: {style['padding']};
            border-radius: 4px;
            font-size: {style['font_size']};
            font-weight: bold;
            display: inline-block;
        ">
            {config.get('emoji', '❓')} {config.get('label', 'Unknown')}
        </span>
    """


def get_character_badge_html(position: str = None) -> str:
    """캐릭터 합성 배지 HTML 생성"""
    pos_label = "좌" if position == "left_bottom" else "우"
    return f"""
        <span style="
            background: #F59E0B;
            color: white;
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 10px;
            font-weight: bold;
            display: inline-block;
        ">
            🎭 캐릭터({pos_label})
        </span>
    """


# 전역 인스턴스 (모듈 레벨)
_global_manager: Optional[SceneTypeManager] = None


def get_global_manager() -> SceneTypeManager:
    """전역 SceneTypeManager 인스턴스 반환"""
    global _global_manager
    if _global_manager is None:
        _global_manager = SceneTypeManager()
    return _global_manager
