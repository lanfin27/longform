# -*- coding: utf-8 -*-
"""
인포그래픽 데이터 모델 v2

인포그래픽 파싱, 시각 자료 선택, 동영상/이미지 관리를 위한 데이터 클래스

핵심 변경:
- UI 표시: 항상 이미지 (첫 프레임/썸네일)
- 내보내기: 인포그래픽/합성은 MP4 동영상
- 캐릭터 합성: 동영상 전체에 오버레이
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime


class VisualType(Enum):
    """시각 자료 타입"""
    AI_IMAGE = "ai_image"           # AI 생성 이미지
    INFOGRAPHIC = "infographic"     # 인포그래픽 (동영상)
    COMPOSITE = "composite"         # 인포그래픽 + 캐릭터 합성 (동영상)


class MediaType(Enum):
    """미디어 파일 타입"""
    IMAGE = "image"     # PNG/JPG (정적)
    VIDEO = "video"     # MP4 (동적, 애니메이션 포함)


@dataclass
class InfographicScene:
    """파싱된 인포그래픽 씬 데이터"""

    scene_id: int                       # 씬 번호 (1부터 시작)
    text: str = ""                      # 메인 텍스트
    sub: str = ""                       # 서브 텍스트
    pattern: int = 1                    # 레이아웃 패턴 (1-12)

    # 형식 A: sceneData 배열 전용 필드
    icon: Optional[str] = None
    icon2: Optional[str] = None
    color: Optional[str] = None
    val1: Optional[str] = None
    val2: Optional[str] = None
    num: Optional[str] = None
    data: Optional[List[int]] = None
    del_items: Optional[List[str]] = None
    ok_item: Optional[str] = None

    # 형식 B: HTML 요소 전용 필드
    html_content: Optional[str] = None      # 원본 HTML (동영상 녹화용)
    has_animation: bool = False             # CSS 애니메이션 포함 여부
    icons: List[str] = field(default_factory=list)  # Font Awesome 아이콘 목록
    comment: Optional[str] = None           # HTML 주석 (씬 설명)

    # === UI 표시용 (즉시 생성) ===
    thumbnail_path: Optional[str] = None      # 320x180 PNG (목록용)
    first_frame_path: Optional[str] = None    # 1280x720 PNG (첫 프레임, 카드용)

    # === 내보내기용 (필요 시 생성) ===
    video_path: Optional[str] = None          # MP4 동영상 (애니메이션)
    video_duration: float = 10.0              # 동영상 길이 (초)

    # === 캐릭터 합성 결과 ===
    composite_video_path: Optional[str] = None    # 합성된 MP4
    composite_thumbnail_path: Optional[str] = None  # 합성 결과 썸네일

    # 메타데이터
    keywords: List[str] = field(default_factory=list)
    chart_type: Optional[str] = None

    # 상태
    is_thumbnail_ready: bool = False
    is_video_ready: bool = False
    is_composite_ready: bool = False
    render_error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            "scene_id": self.scene_id,
            "text": self.text,
            "sub": self.sub,
            "pattern": self.pattern,
            "icon": self.icon,
            "icon2": self.icon2,
            "color": self.color,
            "val1": self.val1,
            "val2": self.val2,
            "num": self.num,
            "data": self.data,
            "del_items": self.del_items,
            "ok_item": self.ok_item,
            "html_content": self.html_content,
            "has_animation": self.has_animation,
            "icons": self.icons,
            "comment": self.comment,
            "thumbnail_path": self.thumbnail_path,
            "first_frame_path": self.first_frame_path,
            "video_path": self.video_path,
            "video_duration": self.video_duration,
            "composite_video_path": self.composite_video_path,
            "composite_thumbnail_path": self.composite_thumbnail_path,
            "keywords": self.keywords,
            "chart_type": self.chart_type,
            "is_thumbnail_ready": self.is_thumbnail_ready,
            "is_video_ready": self.is_video_ready,
            "is_composite_ready": self.is_composite_ready,
            "render_error": self.render_error
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InfographicScene":
        """딕셔너리에서 생성"""
        return cls(
            scene_id=data.get("scene_id", 0),
            text=data.get("text", ""),
            sub=data.get("sub", ""),
            pattern=data.get("pattern", 1),
            icon=data.get("icon"),
            icon2=data.get("icon2"),
            color=data.get("color"),
            val1=data.get("val1"),
            val2=data.get("val2"),
            num=data.get("num"),
            data=data.get("data"),
            del_items=data.get("del_items") or data.get("del"),
            ok_item=data.get("ok_item") or data.get("ok"),
            html_content=data.get("html_content"),
            has_animation=data.get("has_animation", False),
            icons=data.get("icons", []),
            comment=data.get("comment"),
            thumbnail_path=data.get("thumbnail_path"),
            first_frame_path=data.get("first_frame_path"),
            video_path=data.get("video_path"),
            video_duration=data.get("video_duration", 10.0),
            composite_video_path=data.get("composite_video_path"),
            composite_thumbnail_path=data.get("composite_thumbnail_path"),
            keywords=data.get("keywords", []),
            chart_type=data.get("chart_type"),
            is_thumbnail_ready=data.get("is_thumbnail_ready", False),
            is_video_ready=data.get("is_video_ready", False),
            is_composite_ready=data.get("is_composite_ready", False),
            render_error=data.get("render_error")
        )


@dataclass
class InfographicData:
    """인포그래픽 전체 데이터"""

    html_code: str = ""                     # 원본 HTML 코드
    source_path: str = ""                   # 저장된 HTML 파일 경로
    total_scenes: int = 0                   # 총 씬 수
    scenes: List[InfographicScene] = field(default_factory=list)

    # 설정
    default_video_duration: float = 10.0    # 기본 동영상 길이 (초)
    video_fps: int = 30                     # 동영상 FPS
    video_width: int = 1280                 # 동영상 너비
    video_height: int = 720                 # 동영상 높이

    # 메타데이터
    parsed_at: str = ""                     # 파싱 시간
    parse_format: str = ""                  # 파싱 형식 (format_a_scenedata / format_b_html_elements)
    version: str = "2.0"

    def __post_init__(self):
        if not self.parsed_at:
            self.parsed_at = datetime.now().isoformat()
        if self.scenes:
            self.total_scenes = len(self.scenes)

    def get_scene(self, scene_id: int) -> Optional[InfographicScene]:
        """씬 번호로 씬 조회"""
        for scene in self.scenes:
            if scene.scene_id == scene_id:
                return scene
        return None

    def get_scenes_with_thumbnails(self) -> List[InfographicScene]:
        """썸네일이 있는 씬만 반환"""
        return [s for s in self.scenes if s.is_thumbnail_ready]

    def get_scenes_with_videos(self) -> List[InfographicScene]:
        """동영상이 있는 씬만 반환"""
        return [s for s in self.scenes if s.is_video_ready]

    def get_scenes_needing_video(self) -> List[InfographicScene]:
        """동영상 생성이 필요한 씬"""
        return [s for s in self.scenes if not s.is_video_ready]

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            "html_code": self.html_code,
            "source_path": self.source_path,
            "total_scenes": self.total_scenes,
            "scenes": [s.to_dict() for s in self.scenes],
            "default_video_duration": self.default_video_duration,
            "video_fps": self.video_fps,
            "video_width": self.video_width,
            "video_height": self.video_height,
            "parsed_at": self.parsed_at,
            "parse_format": self.parse_format,
            "version": self.version
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InfographicData":
        """딕셔너리에서 생성"""
        scenes = [InfographicScene.from_dict(s) for s in data.get("scenes", [])]
        return cls(
            html_code=data.get("html_code", ""),
            source_path=data.get("source_path", ""),
            total_scenes=data.get("total_scenes", len(scenes)),
            scenes=scenes,
            default_video_duration=data.get("default_video_duration", 10.0),
            video_fps=data.get("video_fps", 30),
            video_width=data.get("video_width", 1280),
            video_height=data.get("video_height", 720),
            parsed_at=data.get("parsed_at", ""),
            parse_format=data.get("parse_format", ""),
            version=data.get("version", "2.0")
        )


@dataclass
class SceneVisualSelection:
    """각 씬의 비주얼 선택 상태"""

    scene_number: int                           # 씬 번호
    selected_type: VisualType = VisualType.AI_IMAGE

    # 각 타입별 미디어 경로
    # AI 이미지
    ai_image_path: Optional[str] = None
    ai_prompt: Optional[str] = None

    # 인포그래픽 (UI: 썸네일, Export: 동영상)
    infographic_thumbnail: Optional[str] = None   # UI 표시용
    infographic_video: Optional[str] = None       # 내보내기용

    # 캐릭터 합성 (UI: 썸네일, Export: 동영상)
    composite_thumbnail: Optional[str] = None     # UI 표시용
    composite_video: Optional[str] = None         # 내보내기용

    # 캐릭터 합성 설정
    character_id: Optional[str] = None
    character_position: str = "오른쪽"
    character_scale: float = 0.7

    # AI 추천
    ai_recommendation: Optional[VisualType] = None
    recommendation_reason: Optional[str] = None
    recommendation_score: float = 0.0

    # 상태
    is_finalized: bool = False

    def get_display_image(self) -> Optional[str]:
        """UI에 표시할 이미지 경로 반환 (항상 이미지)"""
        if self.selected_type == VisualType.AI_IMAGE:
            return self.ai_image_path
        elif self.selected_type == VisualType.INFOGRAPHIC:
            return self.infographic_thumbnail
        elif self.selected_type == VisualType.COMPOSITE:
            return self.composite_thumbnail
        return None

    def get_export_media(self) -> Tuple[Optional[str], MediaType]:
        """내보내기용 미디어 (경로, 타입) 반환"""
        if self.selected_type == VisualType.AI_IMAGE:
            return (self.ai_image_path, MediaType.IMAGE)
        elif self.selected_type == VisualType.INFOGRAPHIC:
            return (self.infographic_video, MediaType.VIDEO)
        elif self.selected_type == VisualType.COMPOSITE:
            return (self.composite_video, MediaType.VIDEO)
        return (None, MediaType.IMAGE)

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            "scene_number": self.scene_number,
            "selected_type": self.selected_type.value,
            "ai_image_path": self.ai_image_path,
            "ai_prompt": self.ai_prompt,
            "infographic_thumbnail": self.infographic_thumbnail,
            "infographic_video": self.infographic_video,
            "composite_thumbnail": self.composite_thumbnail,
            "composite_video": self.composite_video,
            "character_id": self.character_id,
            "character_position": self.character_position,
            "character_scale": self.character_scale,
            "ai_recommendation": self.ai_recommendation.value if self.ai_recommendation else None,
            "recommendation_reason": self.recommendation_reason,
            "recommendation_score": self.recommendation_score,
            "is_finalized": self.is_finalized
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SceneVisualSelection":
        """딕셔너리에서 생성"""
        selected_type = VisualType(data.get("selected_type", "ai_image"))
        ai_rec = data.get("ai_recommendation")

        return cls(
            scene_number=data.get("scene_number", 0),
            selected_type=selected_type,
            ai_image_path=data.get("ai_image_path"),
            ai_prompt=data.get("ai_prompt"),
            infographic_thumbnail=data.get("infographic_thumbnail"),
            infographic_video=data.get("infographic_video"),
            composite_thumbnail=data.get("composite_thumbnail"),
            composite_video=data.get("composite_video"),
            character_id=data.get("character_id"),
            character_position=data.get("character_position", "오른쪽"),
            character_scale=data.get("character_scale", 0.7),
            ai_recommendation=VisualType(ai_rec) if ai_rec else None,
            recommendation_reason=data.get("recommendation_reason"),
            recommendation_score=data.get("recommendation_score", 0.0),
            is_finalized=data.get("is_finalized", False)
        )


@dataclass
class VisualSelectionState:
    """시각 자료 선택 전체 상태"""

    project_id: str
    selections: Dict[int, SceneVisualSelection] = field(default_factory=dict)

    # 인포그래픽 데이터
    infographic_data: Optional[InfographicData] = None

    # 상태
    last_updated: str = ""
    is_dirty: bool = False

    def __post_init__(self):
        if not self.last_updated:
            self.last_updated = datetime.now().isoformat()

    def get_selection(self, scene_number: int) -> Optional[SceneVisualSelection]:
        """씬 선택 정보 조회"""
        return self.selections.get(scene_number)

    def set_selection(self, selection: SceneVisualSelection):
        """씬 선택 정보 설정"""
        self.selections[selection.scene_number] = selection
        self.is_dirty = True
        self.last_updated = datetime.now().isoformat()

    def get_all_export_media(self, scene_numbers: List[int] = None) -> List[Dict]:
        """
        모든 씬의 내보내기 미디어 목록

        Returns:
            [{"scene_number": 1, "path": "...", "media_type": MediaType, "visual_type": VisualType}, ...]
        """
        target_nums = scene_numbers or sorted(self.selections.keys())
        result = []

        for num in target_nums:
            sel = self.selections.get(num)
            if sel:
                path, media_type = sel.get_export_media()
                if path:
                    result.append({
                        "scene_number": num,
                        "path": path,
                        "media_type": media_type,
                        "visual_type": sel.selected_type
                    })

        return result

    def get_statistics(self) -> Dict[str, Any]:
        """선택 통계 반환"""
        total = len(self.selections)

        type_counts = {t.value: 0 for t in VisualType}
        videos_needed = 0
        finalized_count = 0

        for sel in self.selections.values():
            type_counts[sel.selected_type.value] += 1
            if sel.is_finalized:
                finalized_count += 1

            # 동영상 필요 여부 확인
            if sel.selected_type == VisualType.INFOGRAPHIC and not sel.infographic_video:
                videos_needed += 1
            elif sel.selected_type == VisualType.COMPOSITE and not sel.composite_video:
                videos_needed += 1

        return {
            "total_scenes": total,
            "type_counts": type_counts,
            "finalized_count": finalized_count,
            "pending_count": total - finalized_count,
            "videos_needed": videos_needed,
            "completion_rate": finalized_count / max(total, 1) * 100
        }

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            "project_id": self.project_id,
            "selections": {
                str(k): v.to_dict() for k, v in self.selections.items()
            },
            "infographic_data": self.infographic_data.to_dict() if self.infographic_data else None,
            "last_updated": self.last_updated,
            "is_dirty": self.is_dirty
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VisualSelectionState":
        """딕셔너리에서 생성"""
        selections = {}
        for k, v in data.get("selections", {}).items():
            selections[int(k)] = SceneVisualSelection.from_dict(v)

        infographic_data = None
        if data.get("infographic_data"):
            infographic_data = InfographicData.from_dict(data["infographic_data"])

        return cls(
            project_id=data.get("project_id", ""),
            selections=selections,
            infographic_data=infographic_data,
            last_updated=data.get("last_updated", ""),
            is_dirty=data.get("is_dirty", False)
        )

    def save_to_file(self, file_path: str):
        """파일로 저장"""
        import json
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
        self.is_dirty = False

    @classmethod
    def load_from_file(cls, file_path: str) -> Optional["VisualSelectionState"]:
        """파일에서 로드"""
        import json
        import os

        if not os.path.exists(file_path):
            return None

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return cls.from_dict(data)
        except Exception as e:
            print(f"[VisualSelectionState] 로드 실패: {e}")
            return None
