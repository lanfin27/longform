# -*- coding: utf-8 -*-
"""
utils/scene_selector.py
씬 범위 선택 유틸리티

주요 기능:
1. 범위 입력 파싱 (1-10, 1~20)
2. 직접 입력 파싱 (1,3,5,10-20)
3. 프리셋 범위 생성
4. 선택 현황 포맷팅
"""

import re
from typing import List, Set, Tuple, Optional


def parse_scene_range_input(input_str: str, max_scene: int) -> List[int]:
    """
    사용자 입력을 파싱하여 씬 번호 목록 반환

    지원 형식:
    - "1-10" → [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    - "1,3,5" → [1, 3, 5]
    - "1-5,10-15,20" → [1, 2, 3, 4, 5, 10, 11, 12, 13, 14, 15, 20]
    - "1~10" → [1, 2, 3, 4, 5, 6, 7, 8, 9, 10] (한국어 물결표 지원)

    Args:
        input_str: 사용자 입력 문자열
        max_scene: 최대 씬 번호

    Returns:
        정렬된 씬 번호 목록
    """

    if not input_str or not input_str.strip():
        return []

    scenes = set()

    # 공백 제거, 물결표를 하이픈으로 변환
    input_str = input_str.strip()
    input_str = input_str.replace("~", "-")
    input_str = input_str.replace("～", "-")  # 전각 물결표
    input_str = input_str.replace(" ", "")

    # 콤마로 분리
    parts = input_str.split(",")

    for part in parts:
        part = part.strip()

        if not part:
            continue

        # 범위 형식 (예: "1-10")
        if "-" in part:
            range_match = re.match(r'^(\d+)-(\d+)$', part)
            if range_match:
                start = int(range_match.group(1))
                end = int(range_match.group(2))

                # 유효 범위로 제한
                start = max(1, start)
                end = min(max_scene, end)

                if start <= end:
                    scenes.update(range(start, end + 1))

        # 단일 숫자 (예: "5")
        elif part.isdigit():
            num = int(part)
            if 1 <= num <= max_scene:
                scenes.add(num)

    return sorted(list(scenes))


def format_selected_scenes(scene_nums: List[int]) -> str:
    """
    선택된 씬 번호를 사람이 읽기 쉬운 형식으로 변환

    예:
    - [1, 2, 3, 4, 5] → "1~5"
    - [1, 2, 3, 7, 8, 9] → "1~3, 7~9"
    - [1, 3, 5, 7] → "1, 3, 5, 7"
    """

    if not scene_nums:
        return "없음"

    scene_nums = sorted(scene_nums)

    ranges = []
    start = scene_nums[0]
    end = scene_nums[0]

    for num in scene_nums[1:]:
        if num == end + 1:
            end = num
        else:
            # 현재 범위 저장
            if start == end:
                ranges.append(str(start))
            else:
                ranges.append(f"{start}~{end}")

            start = num
            end = num

    # 마지막 범위 저장
    if start == end:
        ranges.append(str(start))
    else:
        ranges.append(f"{start}~{end}")

    return ", ".join(ranges)


def generate_preset_ranges(total_scenes: int, chunk_size: int = 10) -> List[Tuple[int, int]]:
    """
    프리셋 범위 생성

    Args:
        total_scenes: 전체 씬 수
        chunk_size: 청크 크기 (기본 10)

    Returns:
        [(1, 10), (11, 20), (21, 30), ...]
    """

    presets = []

    for start in range(1, total_scenes + 1, chunk_size):
        end = min(start + chunk_size - 1, total_scenes)
        presets.append((start, end))

    return presets


def apply_range_to_selection(
    current_selection: Set[int],
    range_start: int,
    range_end: int,
    mode: str = "new"
) -> Set[int]:
    """
    범위를 선택에 적용

    Args:
        current_selection: 현재 선택된 씬들
        range_start: 범위 시작
        range_end: 범위 끝
        mode: "new" (새로 선택), "add" (추가), "remove" (제외)

    Returns:
        업데이트된 선택 세트
    """

    range_scenes = set(range(range_start, range_end + 1))

    if mode == "new":
        return range_scenes
    elif mode == "add":
        return current_selection | range_scenes
    elif mode == "remove":
        return current_selection - range_scenes
    else:
        return range_scenes


def get_selection_stats(
    selected: Set[int],
    total: int,
    completed_scenes: Optional[Set[int]] = None
) -> dict:
    """
    선택 통계 반환

    Args:
        selected: 선택된 씬들
        total: 전체 씬 수
        completed_scenes: 완료된 씬들 (이미지 있는 씬)

    Returns:
        통계 딕셔너리
    """

    completed_scenes = completed_scenes or set()

    selected_completed = selected & completed_scenes
    selected_incomplete = selected - completed_scenes

    return {
        "total": total,
        "selected_count": len(selected),
        "selected_completed": len(selected_completed),
        "selected_incomplete": len(selected_incomplete),
        "percent": round(len(selected) / total * 100, 1) if total > 0 else 0
    }


# ============================================================
# SceneSelector UI 클래스
# ============================================================

import streamlit as st
import os
import uuid


class SceneSelector:
    """
    씬 선택 UI 컴포넌트

    사용법:
        selector = SceneSelector(total_scenes=13, key_prefix="storyboard")
        selected_ids = selector.render(scenes_data)

    Note:
        v2.0: UUID 기반 고유 키 생성으로 중복 key 에러 방지
    """

    def __init__(self, total_scenes: int, key_prefix: str = "scene_select"):
        self.total_scenes = total_scenes
        self.base_prefix = key_prefix

        # UUID 기반 고유 키 생성 (세션 유지)
        session_key = f"_selector_uuid_{key_prefix}"
        if session_key not in st.session_state:
            st.session_state[session_key] = str(uuid.uuid4())[:8]
        self.unique_id = st.session_state[session_key]

        # 고유 key_prefix 생성
        self.key_prefix = f"{key_prefix}_{self.unique_id}"
        self._init_session_state()

    def _init_session_state(self):
        """세션 상태 초기화"""
        key = f"{self.key_prefix}_selected"
        if key not in st.session_state:
            st.session_state[key] = set()

    @property
    def selected_scenes(self) -> Set[int]:
        """선택된 씬 ID 집합"""
        return st.session_state.get(f"{self.key_prefix}_selected", set())

    @selected_scenes.setter
    def selected_scenes(self, value: Set[int]):
        st.session_state[f"{self.key_prefix}_selected"] = value

    def select_all(self):
        """전체 선택"""
        self.selected_scenes = set(range(1, self.total_scenes + 1))

    def deselect_all(self):
        """전체 해제"""
        self.selected_scenes = set()

    def select_range(self, start: int, end: int):
        """구간 선택"""
        start = max(1, start)
        end = min(self.total_scenes, end)
        self.selected_scenes = set(range(start, end + 1))

    def toggle_scene(self, scene_id: int):
        """개별 씬 토글"""
        selected = self.selected_scenes.copy()
        if scene_id in selected:
            selected.remove(scene_id)
        else:
            selected.add(scene_id)
        self.selected_scenes = selected

    def render(self, scenes_data: List[dict] = None) -> Set[int]:
        """
        씬 선택 UI 렌더링

        Args:
            scenes_data: 씬 데이터 리스트 (이미지/비디오 유무 표시용)

        Returns:
            선택된 씬 ID 집합
        """
        st.markdown("### 🎯 씬 선택")

        # 선택 현황 표시
        selected_count = len(self.selected_scenes)
        st.markdown(f"**선택됨: {selected_count} / {self.total_scenes}개 씬**")

        if selected_count > 0:
            formatted = format_selected_scenes(sorted(self.selected_scenes))
            st.caption(f"선택된 씬: {formatted}")

        # 선택 방식 탭
        tab1, tab2, tab3 = st.tabs(["⚡ 빠른 선택", "🔢 범위 선택", "✅ 개별 선택"])

        with tab1:
            self._render_quick_select(scenes_data)

        with tab2:
            self._render_range_select()

        with tab3:
            self._render_individual_select(scenes_data)

        return self.selected_scenes

    def _render_quick_select(self, scenes_data: List[dict] = None):
        """빠른 선택 UI"""

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            if st.button("✅ 전체 선택", use_container_width=True, key=f"{self.key_prefix}_all"):
                self.select_all()
                st.rerun()

        with col2:
            if st.button("❌ 전체 해제", use_container_width=True, key=f"{self.key_prefix}_none"):
                self.deselect_all()
                st.rerun()

        with col3:
            if st.button("🔄 선택 반전", use_container_width=True, key=f"{self.key_prefix}_invert"):
                all_scenes = set(range(1, self.total_scenes + 1))
                self.selected_scenes = all_scenes - self.selected_scenes
                st.rerun()

        with col4:
            if st.button("🖼️ 미생성만", use_container_width=True, key=f"{self.key_prefix}_no_img"):
                if scenes_data:
                    no_image = set()
                    for s in scenes_data:
                        sid = s.get("scene_id", s.get("id", 0))
                        img_path = s.get("image_path", s.get("composite_path", ""))
                        if not img_path or not os.path.exists(str(img_path)):
                            no_image.add(sid)
                    self.selected_scenes = no_image
                    st.rerun()
                else:
                    st.warning("씬 데이터가 없습니다.")

        # 프리셋 버튼
        st.markdown("**프리셋:**")

        presets = generate_preset_ranges(self.total_scenes, chunk_size=5)
        cols = st.columns(min(len(presets) + 2, 6))

        for i, (start, end) in enumerate(presets[:4]):
            with cols[i]:
                label = f"{start}~{end}" if start != end else str(start)
                if st.button(label, key=f"{self.key_prefix}_preset_{i}"):
                    self.select_range(start, end)
                    st.rerun()

        # 전반부/후반부
        with cols[min(4, len(cols) - 2)]:
            if st.button("전반부", key=f"{self.key_prefix}_first_half"):
                mid = self.total_scenes // 2
                self.select_range(1, mid)
                st.rerun()

        with cols[min(5, len(cols) - 1)]:
            if st.button("후반부", key=f"{self.key_prefix}_second_half"):
                mid = self.total_scenes // 2 + 1
                self.select_range(mid, self.total_scenes)
                st.rerun()

    def _render_range_select(self):
        """범위 선택 UI"""

        col1, col2, col3 = st.columns([2, 2, 1])

        with col1:
            start = st.number_input(
                "시작 씬",
                min_value=1,
                max_value=self.total_scenes,
                value=1,
                key=f"{self.key_prefix}_range_start"
            )

        with col2:
            end = st.number_input(
                "끝 씬",
                min_value=1,
                max_value=self.total_scenes,
                value=min(5, self.total_scenes),
                key=f"{self.key_prefix}_range_end"
            )

        with col3:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("범위 선택", key=f"{self.key_prefix}_apply_range"):
                self.select_range(int(start), int(end))
                st.rerun()

        st.markdown("---")

        # 직접 입력
        st.markdown("**직접 입력** (예: `1,3,5-10,15`)")

        range_input = st.text_input(
            "씬 번호",
            placeholder="예: 1,3,5-10,15,20-25",
            key=f"{self.key_prefix}_direct_input",
            label_visibility="collapsed"
        )

        if st.button("입력값 적용", key=f"{self.key_prefix}_apply_direct"):
            parsed = parse_scene_range_input(range_input, self.total_scenes)
            self.selected_scenes = set(parsed)
            st.success(f"✅ {len(parsed)}개 씬 선택됨")
            st.rerun()

    def _render_individual_select(self, scenes_data: List[dict] = None):
        """개별 선택 UI (체크박스 그리드)"""

        # 씬 데이터 매핑
        scene_info_map = {}
        if scenes_data:
            for s in scenes_data:
                sid = s.get("scene_id", s.get("id", 0))
                scene_info_map[sid] = s

        # 5열 그리드
        cols_per_row = 5
        rows = (self.total_scenes + cols_per_row - 1) // cols_per_row

        # 현재 선택 상태 복사 (체크박스 변경 추적용)
        new_selection = self.selected_scenes.copy()

        for row in range(rows):
            cols = st.columns(cols_per_row)

            for col_idx in range(cols_per_row):
                scene_id = row * cols_per_row + col_idx + 1

                if scene_id > self.total_scenes:
                    break

                with cols[col_idx]:
                    # 씬 상태 아이콘
                    status_icons = ""
                    if scene_id in scene_info_map:
                        scene = scene_info_map[scene_id]
                        has_img = bool(scene.get("image_path") or scene.get("composite_path"))
                        has_vid = bool(scene.get("video_path"))
                        status_icons = f"{'🖼️' if has_img else '⬜'}{'🎬' if has_vid else ''}"

                    # 체크박스
                    is_selected = scene_id in self.selected_scenes

                    checked = st.checkbox(
                        f"씬 {scene_id} {status_icons}",
                        value=is_selected,
                        key=f"{self.key_prefix}_cb_{scene_id}"
                    )

                    # 선택 상태 업데이트
                    if checked and scene_id not in new_selection:
                        new_selection.add(scene_id)
                    elif not checked and scene_id in new_selection:
                        new_selection.discard(scene_id)

        # 변경사항 적용
        if new_selection != self.selected_scenes:
            self.selected_scenes = new_selection


def render_scene_selector(total_scenes: int, scenes_data: List[dict] = None, key: str = "default") -> Set[int]:
    """
    씬 선택 UI 렌더링 (단축 함수)

    Args:
        total_scenes: 전체 씬 수
        scenes_data: 씬 데이터 (이미지/비디오 유무 표시용)
        key: 고유 키

    Returns:
        선택된 씬 ID 집합
    """
    selector = SceneSelector(total_scenes, key_prefix=f"scene_sel_{key}")
    return selector.render(scenes_data)
