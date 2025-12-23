# -*- coding: utf-8 -*-
"""
시각 자료 선택 매니저 v2

씬별 시각 자료 선택 상태 관리

기능:
- 씬별 AI 이미지 / 인포그래픽 / 합성 선택
- UI용 이미지 / 내보내기용 미디어 구분
- 상태 저장 및 로드
- 선택 통계
"""

import os
import json
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
from datetime import datetime

from utils.models.infographic import (
    VisualType,
    MediaType,
    InfographicScene,
    InfographicData,
    SceneVisualSelection,
    VisualSelectionState
)


class VisualSelectionManager:
    """시각 자료 선택 매니저"""

    STATE_FILENAME = "visual_selections.json"

    def __init__(self, project_path: str):
        """
        Args:
            project_path: 프로젝트 경로
        """
        self.project_path = Path(project_path)
        self.state_file = self.project_path / self.STATE_FILENAME

        # 상태 로드 또는 생성
        self.state = self._load_or_create_state()

    def _load_or_create_state(self) -> VisualSelectionState:
        """상태 로드 또는 생성"""
        if self.state_file.exists():
            loaded = VisualSelectionState.load_from_file(str(self.state_file))
            if loaded:
                return loaded

        return VisualSelectionState(
            project_id=self.project_path.name,
            selections={}
        )

    def save_state(self):
        """상태 저장"""
        self.state.save_to_file(str(self.state_file))

    def get_selection(self, scene_number: int) -> Optional[SceneVisualSelection]:
        """씬 선택 정보 조회"""
        return self.state.get_selection(scene_number)

    def set_visual_type(
        self,
        scene_number: int,
        visual_type: VisualType,
        auto_save: bool = True
    ):
        """씬의 시각 자료 타입 설정"""
        selection = self.state.selections.get(scene_number)

        if selection:
            selection.selected_type = visual_type
        else:
            selection = SceneVisualSelection(
                scene_number=scene_number,
                selected_type=visual_type
            )

        self.state.set_selection(selection)

        if auto_save:
            self.save_state()

    def set_ai_image(
        self,
        scene_number: int,
        image_path: str,
        prompt: Optional[str] = None,
        auto_save: bool = True
    ):
        """AI 이미지 설정"""
        selection = self.state.selections.get(scene_number)

        if not selection:
            selection = SceneVisualSelection(
                scene_number=scene_number,
                selected_type=VisualType.AI_IMAGE
            )

        selection.ai_image_path = image_path
        selection.ai_prompt = prompt
        selection.selected_type = VisualType.AI_IMAGE

        self.state.set_selection(selection)

        if auto_save:
            self.save_state()

    def set_infographic(
        self,
        scene_number: int,
        infographic_scene: InfographicScene,
        auto_save: bool = True
    ):
        """
        인포그래픽 설정

        Args:
            scene_number: 씬 번호
            infographic_scene: 인포그래픽 씬 데이터 (썸네일, 동영상 경로 포함)
        """
        selection = self.state.selections.get(scene_number)

        if not selection:
            selection = SceneVisualSelection(
                scene_number=scene_number,
                selected_type=VisualType.INFOGRAPHIC
            )

        # UI용 썸네일 (첫 프레임)
        selection.infographic_thumbnail = (
            infographic_scene.first_frame_path or infographic_scene.thumbnail_path
        )
        # 내보내기용 동영상
        selection.infographic_video = infographic_scene.video_path

        selection.selected_type = VisualType.INFOGRAPHIC

        self.state.set_selection(selection)

        if auto_save:
            self.save_state()

    def set_composite(
        self,
        scene_number: int,
        infographic_scene: InfographicScene,
        character_id: str = None,
        position: str = "오른쪽",
        scale: float = 0.7,
        auto_save: bool = True
    ):
        """
        캐릭터 합성 설정

        Args:
            scene_number: 씬 번호
            infographic_scene: 인포그래픽 씬 데이터 (합성 결과 포함)
        """
        selection = self.state.selections.get(scene_number)

        if not selection:
            selection = SceneVisualSelection(
                scene_number=scene_number,
                selected_type=VisualType.COMPOSITE
            )

        # UI용 썸네일
        selection.composite_thumbnail = infographic_scene.composite_thumbnail_path
        # 내보내기용 동영상
        selection.composite_video = infographic_scene.composite_video_path

        selection.character_id = character_id
        selection.character_position = position
        selection.character_scale = scale

        selection.selected_type = VisualType.COMPOSITE

        self.state.set_selection(selection)

        if auto_save:
            self.save_state()

    def set_ai_recommendation(
        self,
        scene_number: int,
        recommended_type: VisualType,
        reason: str,
        score: float = 0.5
    ):
        """AI 추천 설정"""
        selection = self.state.selections.get(scene_number)

        if not selection:
            selection = SceneVisualSelection(
                scene_number=scene_number,
                selected_type=VisualType.AI_IMAGE
            )

        selection.ai_recommendation = recommended_type
        selection.recommendation_reason = reason
        selection.recommendation_score = score

        self.state.set_selection(selection)

    def apply_ai_recommendation(self, scene_number: int, auto_save: bool = True):
        """AI 추천을 해당 씬에 적용"""
        selection = self.state.selections.get(scene_number)
        if selection and selection.ai_recommendation:
            selection.selected_type = selection.ai_recommendation
            if auto_save:
                self.save_state()

    def apply_all_ai_recommendations(self):
        """모든 AI 추천 적용"""
        for selection in self.state.selections.values():
            if selection.ai_recommendation:
                selection.selected_type = selection.ai_recommendation
        self.save_state()

    def get_display_image(self, scene_number: int) -> Optional[str]:
        """
        UI에 표시할 이미지 경로 반환

        항상 이미지를 반환 (동영상이 아님):
        - AI 이미지: 원본 이미지
        - 인포그래픽: 첫 프레임 썸네일
        - 합성: 합성 결과 썸네일
        """
        selection = self.state.selections.get(scene_number)
        if selection:
            return selection.get_display_image()
        return None

    def get_export_media(self, scene_number: int) -> Tuple[Optional[str], MediaType]:
        """
        내보내기용 미디어 경로와 타입 반환

        - AI 이미지: (이미지 경로, IMAGE)
        - 인포그래픽: (동영상 경로, VIDEO)
        - 합성: (합성 동영상 경로, VIDEO)
        """
        selection = self.state.selections.get(scene_number)
        if selection:
            return selection.get_export_media()
        return (None, MediaType.IMAGE)

    def get_all_export_media(self, scene_numbers: List[int] = None) -> List[Dict]:
        """모든 씬의 내보내기 미디어 목록"""
        return self.state.get_all_export_media(scene_numbers)

    def set_infographic_data(self, infographic_data: InfographicData):
        """인포그래픽 데이터 설정"""
        self.state.infographic_data = infographic_data
        self.save_state()

    def get_infographic_data(self) -> Optional[InfographicData]:
        """인포그래픽 데이터 조회"""
        return self.state.infographic_data

    def initialize_selections_from_scenes(
        self,
        scene_numbers: List[int],
        default_type: VisualType = VisualType.AI_IMAGE
    ):
        """씬 목록으로 선택 초기화"""
        for scene_num in scene_numbers:
            if scene_num not in self.state.selections:
                selection = SceneVisualSelection(
                    scene_number=scene_num,
                    selected_type=default_type
                )
                self.state.selections[scene_num] = selection

        self.save_state()

    def apply_bulk_type(
        self,
        scene_numbers: List[int],
        visual_type: VisualType
    ):
        """여러 씬에 타입 일괄 적용"""
        for scene_num in scene_numbers:
            self.set_visual_type(scene_num, visual_type, auto_save=False)
        self.save_state()

    def finalize_selection(self, scene_number: int, auto_save: bool = True):
        """선택 확정"""
        selection = self.state.selections.get(scene_number)
        if selection:
            selection.is_finalized = True
            if auto_save:
                self.save_state()

    def get_statistics(self) -> Dict[str, Any]:
        """선택 통계 반환"""
        return self.state.get_statistics()

    def get_videos_needed_count(self) -> int:
        """동영상 생성이 필요한 씬 수"""
        stats = self.get_statistics()
        return stats.get("videos_needed", 0)

    def export_for_video_pipeline(self) -> List[Dict[str, Any]]:
        """
        비디오 생성 파이프라인용 데이터 내보내기

        Returns:
            [
                {
                    "scene_number": 1,
                    "path": "...",
                    "media_type": "image" or "video",
                    "visual_type": "ai_image" or "infographic" or "composite"
                },
                ...
            ]
        """
        result = []

        for scene_num in sorted(self.state.selections.keys()):
            selection = self.state.selections[scene_num]
            path, media_type = selection.get_export_media()

            if path:
                result.append({
                    "scene_number": scene_num,
                    "path": path,
                    "media_type": media_type.value,
                    "visual_type": selection.selected_type.value,
                    "is_finalized": selection.is_finalized
                })

        return result

    def clear_all(self):
        """모든 선택 초기화"""
        self.state.selections = {}
        self.state.infographic_data = None
        self.save_state()


def get_visual_selection_manager(project_path: str) -> VisualSelectionManager:
    """매니저 인스턴스 생성"""
    return VisualSelectionManager(project_path)


# Streamlit 세션 상태 헬퍼
def get_session_manager(project_path: str) -> VisualSelectionManager:
    """
    Streamlit 세션에서 매니저 가져오기 또는 생성

    Usage:
        import streamlit as st
        manager = get_session_manager(project_path)
    """
    import streamlit as st

    key = f"visual_selection_manager_{project_path}"

    if key not in st.session_state:
        st.session_state[key] = VisualSelectionManager(project_path)

    return st.session_state[key]
