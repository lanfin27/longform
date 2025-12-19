"""
캔버스 상태 관리자

Streamlit 세션 상태를 통한 캔버스 배치 정보 관리

사용법:
    from components.canvas_state_manager import CanvasStateManager

    # 씬에 대한 캐릭터 배치 초기화
    CanvasStateManager.init_placements_for_scene(scene_id, characters, bg_size)

    # 배치 정보 가져오기/설정
    placements = CanvasStateManager.get_placements(scene_id)
    CanvasStateManager.set_placements(scene_id, placements)
"""

import streamlit as st
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict


@dataclass
class CharacterPlacement:
    """캐릭터 배치 정보"""
    id: str                 # 고유 ID
    name: str               # 캐릭터 이름
    image_path: str         # 이미지 경로
    x: float                # X 위치 (비율 0-1)
    y: float                # Y 위치 (비율 0-1)
    scale: float            # 크기 비율 (0.1-2.0)
    z_index: int            # 레이어 순서 (높을수록 위)
    visible: bool = True    # 표시 여부

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> "CharacterPlacement":
        return cls(**data)


class CanvasStateManager:
    """
    캔버스 상태 관리자

    Streamlit 세션 상태를 통해 각 씬별 캐릭터 배치 정보를 관리합니다.
    """

    SESSION_KEY = "_canvas_character_placements"
    BACKGROUND_KEY = "_canvas_background_info"

    # ============================================================
    # 기본 상태 관리
    # ============================================================

    @classmethod
    def _ensure_session_state(cls):
        """세션 상태 초기화"""
        if cls.SESSION_KEY not in st.session_state:
            st.session_state[cls.SESSION_KEY] = {}
        if cls.BACKGROUND_KEY not in st.session_state:
            st.session_state[cls.BACKGROUND_KEY] = {}

    @classmethod
    def get_placements(cls, scene_id: int) -> List[Dict]:
        """
        특정 씬의 캐릭터 배치 정보 가져오기

        Args:
            scene_id: 씬 ID

        Returns:
            배치 정보 리스트 (딕셔너리)
        """
        cls._ensure_session_state()
        placements = st.session_state[cls.SESSION_KEY].get(str(scene_id), [])
        return placements

    @classmethod
    def set_placements(cls, scene_id: int, placements: List[Dict]):
        """
        특정 씬의 캐릭터 배치 정보 설정

        Args:
            scene_id: 씬 ID
            placements: 배치 정보 리스트
        """
        cls._ensure_session_state()
        st.session_state[cls.SESSION_KEY][str(scene_id)] = placements

    @classmethod
    def clear_placements(cls, scene_id: int):
        """특정 씬의 배치 정보 삭제"""
        cls._ensure_session_state()
        if str(scene_id) in st.session_state[cls.SESSION_KEY]:
            del st.session_state[cls.SESSION_KEY][str(scene_id)]

    @classmethod
    def clear_all(cls):
        """모든 배치 정보 삭제"""
        st.session_state[cls.SESSION_KEY] = {}
        st.session_state[cls.BACKGROUND_KEY] = {}

    # ============================================================
    # 배치 초기화
    # ============================================================

    @classmethod
    def init_placements_for_scene(
        cls,
        scene_id: int,
        characters: List[Dict],
        background_size: Tuple[int, int] = (1920, 1080),
        force_reinit: bool = False
    ) -> List[Dict]:
        """
        씬에 대한 캐릭터 배치 초기화

        Args:
            scene_id: 씬 ID
            characters: 캐릭터 정보 리스트
                [{"name": "홍길동", "image_path": "..."}, ...]
            background_size: 배경 크기 (width, height)
            force_reinit: 강제 재초기화 여부

        Returns:
            초기화된 배치 정보 리스트
        """
        cls._ensure_session_state()

        # 이미 존재하고 강제 재초기화가 아니면 기존 값 반환
        existing = cls.get_placements(scene_id)
        if existing and not force_reinit:
            return existing

        # 배경 정보 저장
        st.session_state[cls.BACKGROUND_KEY][str(scene_id)] = {
            "width": background_size[0],
            "height": background_size[1]
        }

        # 초기 배치 생성 (자동 레이아웃)
        placements = cls._create_initial_layout(characters, background_size)
        cls.set_placements(scene_id, placements)

        return placements

    @classmethod
    def _create_initial_layout(
        cls,
        characters: List[Dict],
        background_size: Tuple[int, int]
    ) -> List[Dict]:
        """
        캐릭터들의 초기 레이아웃 생성

        캐릭터 수에 따라 자동 배치:
        - 1명: 중앙
        - 2명: 좌우
        - 3명: 좌중우
        - 4명+: 균등 분배
        """
        if not characters:
            return []

        n = len(characters)
        placements = []

        # 레이아웃 프리셋
        if n == 1:
            positions = [(0.5, 0.6)]  # 중앙 하단
            scales = [0.7]
        elif n == 2:
            positions = [(0.3, 0.6), (0.7, 0.6)]  # 좌우
            scales = [0.6, 0.6]
        elif n == 3:
            positions = [(0.2, 0.6), (0.5, 0.55), (0.8, 0.6)]  # 좌중우
            scales = [0.5, 0.6, 0.5]
        else:
            # n개 균등 분배
            positions = []
            scales = []
            for i in range(n):
                x = 0.15 + (0.7 * i / (n - 1)) if n > 1 else 0.5
                positions.append((x, 0.6))
                scales.append(max(0.3, 0.6 - (n - 3) * 0.05))

        for i, char in enumerate(characters):
            placement = {
                "id": f"char_{i}_{char.get('name', 'unknown')}",
                "name": char.get("name", f"캐릭터 {i+1}"),
                "image_path": char.get("image_path", ""),
                "x": positions[i][0] if i < len(positions) else 0.5,
                "y": positions[i][1] if i < len(positions) else 0.6,
                "scale": scales[i] if i < len(scales) else 0.5,
                "z_index": i,
                "visible": True
            }
            placements.append(placement)

        return placements

    # ============================================================
    # 개별 캐릭터 조작
    # ============================================================

    @classmethod
    def update_character_position(
        cls,
        scene_id: int,
        char_id: str,
        x: float,
        y: float
    ):
        """캐릭터 위치 업데이트"""
        placements = cls.get_placements(scene_id)
        for p in placements:
            if p["id"] == char_id:
                p["x"] = max(0, min(1, x))
                p["y"] = max(0, min(1, y))
                break
        cls.set_placements(scene_id, placements)

    @classmethod
    def update_character_scale(cls, scene_id: int, char_id: str, scale: float):
        """캐릭터 크기 업데이트"""
        placements = cls.get_placements(scene_id)
        for p in placements:
            if p["id"] == char_id:
                p["scale"] = max(0.1, min(2.0, scale))
                break
        cls.set_placements(scene_id, placements)

    @classmethod
    def update_character_z_index(cls, scene_id: int, char_id: str, z_index: int):
        """캐릭터 레이어 순서 업데이트"""
        placements = cls.get_placements(scene_id)
        for p in placements:
            if p["id"] == char_id:
                p["z_index"] = z_index
                break
        cls.set_placements(scene_id, placements)

    @classmethod
    def toggle_character_visibility(cls, scene_id: int, char_id: str):
        """캐릭터 표시 여부 토글"""
        placements = cls.get_placements(scene_id)
        for p in placements:
            if p["id"] == char_id:
                p["visible"] = not p.get("visible", True)
                break
        cls.set_placements(scene_id, placements)

    @classmethod
    def bring_to_front(cls, scene_id: int, char_id: str):
        """캐릭터를 맨 앞으로"""
        placements = cls.get_placements(scene_id)
        max_z = max(p.get("z_index", 0) for p in placements) if placements else 0
        for p in placements:
            if p["id"] == char_id:
                p["z_index"] = max_z + 1
                break
        cls.set_placements(scene_id, placements)

    @classmethod
    def send_to_back(cls, scene_id: int, char_id: str):
        """캐릭터를 맨 뒤로"""
        placements = cls.get_placements(scene_id)
        min_z = min(p.get("z_index", 0) for p in placements) if placements else 0
        for p in placements:
            if p["id"] == char_id:
                p["z_index"] = min_z - 1
                break
        cls.set_placements(scene_id, placements)

    # ============================================================
    # 배경 정보
    # ============================================================

    @classmethod
    def get_background_size(cls, scene_id: int) -> Tuple[int, int]:
        """배경 크기 가져오기"""
        cls._ensure_session_state()
        bg_info = st.session_state[cls.BACKGROUND_KEY].get(str(scene_id), {})
        return (bg_info.get("width", 1920), bg_info.get("height", 1080))

    @classmethod
    def set_background_size(cls, scene_id: int, width: int, height: int):
        """배경 크기 설정"""
        cls._ensure_session_state()
        st.session_state[cls.BACKGROUND_KEY][str(scene_id)] = {
            "width": width,
            "height": height
        }

    # ============================================================
    # 캔버스 결과 처리
    # ============================================================

    @classmethod
    def apply_canvas_result(cls, scene_id: int, canvas_result: Dict):
        """
        캔버스 컴포넌트 결과 적용

        Args:
            scene_id: 씬 ID
            canvas_result: interactive_composite_canvas() 반환값
        """
        if not canvas_result:
            return

        objects = canvas_result.get("objects", [])
        if not objects:
            return

        placements = cls.get_placements(scene_id)
        bg_size = cls.get_background_size(scene_id)

        # 캔버스 좌표를 비율로 변환
        canvas_width = canvas_result.get("canvas_width", 800)
        canvas_height = canvas_result.get("canvas_height", 450)

        for obj in objects:
            char_id = obj.get("id")
            if not char_id:
                continue

            for p in placements:
                if p["id"] == char_id:
                    # 픽셀 좌표를 비율로 변환
                    p["x"] = obj.get("x", 0) / canvas_width
                    p["y"] = obj.get("y", 0) / canvas_height

                    # 크기 비율 계산
                    if "width" in obj and "original_width" in obj:
                        p["scale"] = obj["width"] / obj["original_width"]

                    p["z_index"] = obj.get("z_index", p.get("z_index", 0))
                    break

        cls.set_placements(scene_id, placements)

    # ============================================================
    # 레이아웃 프리셋
    # ============================================================

    @classmethod
    def apply_preset_layout(cls, scene_id: int, preset: str):
        """
        프리셋 레이아웃 적용

        Args:
            scene_id: 씬 ID
            preset: 레이아웃 이름
                - "center": 모두 중앙
                - "spread": 균등 분배
                - "left_focus": 왼쪽 집중
                - "right_focus": 오른쪽 집중
                - "dialogue": 대화 배치 (2인)
                - "group": 그룹 배치
        """
        placements = cls.get_placements(scene_id)
        n = len(placements)

        if n == 0:
            return

        # 프리셋별 위치 계산
        if preset == "center":
            # 모두 중앙에 겹쳐서
            for i, p in enumerate(placements):
                p["x"] = 0.5
                p["y"] = 0.6
                p["z_index"] = i

        elif preset == "spread":
            # 균등 분배
            for i, p in enumerate(placements):
                p["x"] = 0.15 + (0.7 * i / (n - 1)) if n > 1 else 0.5
                p["y"] = 0.6
                p["z_index"] = i

        elif preset == "left_focus":
            # 왼쪽 집중
            for i, p in enumerate(placements):
                if i == 0:
                    p["x"] = 0.35
                    p["scale"] = 0.7
                else:
                    p["x"] = 0.65 + (i - 1) * 0.12
                    p["scale"] = 0.5
                p["y"] = 0.6
                p["z_index"] = n - i  # 첫 번째가 맨 앞

        elif preset == "right_focus":
            # 오른쪽 집중
            for i, p in enumerate(placements):
                if i == n - 1:
                    p["x"] = 0.65
                    p["scale"] = 0.7
                else:
                    p["x"] = 0.15 + i * 0.12
                    p["scale"] = 0.5
                p["y"] = 0.6
                p["z_index"] = i  # 마지막이 맨 앞

        elif preset == "dialogue" and n >= 2:
            # 대화 배치 (마주보는 2인)
            placements[0]["x"] = 0.25
            placements[0]["y"] = 0.6
            placements[0]["scale"] = 0.65
            placements[1]["x"] = 0.75
            placements[1]["y"] = 0.6
            placements[1]["scale"] = 0.65
            # 나머지는 뒤에
            for i in range(2, n):
                placements[i]["x"] = 0.5
                placements[i]["y"] = 0.65
                placements[i]["scale"] = 0.4
                placements[i]["z_index"] = -1

        elif preset == "group":
            # 그룹 배치 (V자 형태)
            if n == 1:
                placements[0]["x"] = 0.5
                placements[0]["y"] = 0.6
            elif n == 2:
                placements[0]["x"] = 0.35
                placements[1]["x"] = 0.65
                for p in placements:
                    p["y"] = 0.6
            else:
                # 중앙이 앞, 양 끝이 뒤
                mid = n // 2
                for i, p in enumerate(placements):
                    offset = abs(i - mid)
                    p["x"] = 0.5 + (i - mid) * 0.15
                    p["y"] = 0.55 + offset * 0.05
                    p["scale"] = 0.6 - offset * 0.08
                    p["z_index"] = n - offset

        cls.set_placements(scene_id, placements)

    # ============================================================
    # 유틸리티
    # ============================================================

    @classmethod
    def get_sorted_placements(cls, scene_id: int) -> List[Dict]:
        """z_index 순으로 정렬된 배치 가져오기 (합성용)"""
        placements = cls.get_placements(scene_id)
        return sorted(placements, key=lambda p: p.get("z_index", 0))

    @classmethod
    def get_visible_placements(cls, scene_id: int) -> List[Dict]:
        """보이는 캐릭터만 z_index 순으로 정렬"""
        placements = cls.get_placements(scene_id)
        visible = [p for p in placements if p.get("visible", True)]
        return sorted(visible, key=lambda p: p.get("z_index", 0))

    @classmethod
    def export_placements(cls, scene_id: int) -> Dict:
        """배치 정보 내보내기 (저장용)"""
        return {
            "scene_id": scene_id,
            "background": st.session_state.get(cls.BACKGROUND_KEY, {}).get(str(scene_id), {}),
            "placements": cls.get_placements(scene_id)
        }

    @classmethod
    def import_placements(cls, data: Dict):
        """배치 정보 가져오기"""
        scene_id = data.get("scene_id")
        if scene_id is None:
            return

        cls._ensure_session_state()

        if "background" in data:
            st.session_state[cls.BACKGROUND_KEY][str(scene_id)] = data["background"]

        if "placements" in data:
            cls.set_placements(scene_id, data["placements"])
