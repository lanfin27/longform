# -*- coding: utf-8 -*-
"""
components/storyboard_workflow/step_ui_base.py
Step UI 기본 클래스 (v1.2)

모든 Step UI의 공통 기능을 제공합니다.

v1.1: _format_scene_range 함수 추가 - 연속된 씬만 범위로 표시
      - 기존: "씬 46-200" (비연속 씬도 범위 표시)
      - 수정: "씬 44, 46, 90-91, 106" (연속 씬만 범위로 묶음)

v1.2: _create_simple_bundles 함수 추가 - 단순 분할 묶음 생성
      - 🔴 긴급 수정: 원본 bundle_id 대신 선택된 씬을 단순 분할하여 새 묶음 생성
      - 핵심: 39개 선택 씬 → 3개씩 나눠서 13개 묶음 생성
"""

import streamlit as st
from abc import ABC, abstractmethod
from typing import Set, Dict, List, Optional, Callable
from pathlib import Path

from .scene_status import STEP_CONFIG, get_status_badge_html, SceneStatus
from .progress_visualizer import render_step_status_cards


class StepUIBase(ABC):
    """
    Step UI 기본 클래스

    각 Step UI는 이 클래스를 상속하여 구현합니다.
    """

    def __init__(
        self,
        step_number: int,
        workflow_manager,
        project_path: Path
    ):
        self.step = step_number
        self.manager = workflow_manager
        self.project_path = project_path

        step_config = STEP_CONFIG.get(step_number, {})
        self.step_name = step_config.get('name', f'Step {step_number}')
        self.step_emoji = step_config.get('emoji', '')
        self.step_color = step_config.get('color', '#6B7280')
        self.step_unit = step_config.get('unit', 'scene')

    def render(self, scenes: List[Dict]) -> Optional[Dict]:
        """메인 렌더 함수"""
        # 상태 카드
        render_step_status_cards(self.manager, self.step)

        st.markdown("---")

        # 대상 풀 계산
        pool = self.get_pool()
        assigned = self.get_assigned()
        completed = self.get_completed()

        # Step별 콘텐츠 렌더링
        return self.render_step_content(scenes, pool, assigned, completed)

    @abstractmethod
    def get_pool(self) -> Set[int]:
        """이 Step의 대상 씬 풀 반환"""
        pass

    @abstractmethod
    def get_assigned(self) -> Set[int]:
        """이 Step에 할당된 씬 반환"""
        pass

    @abstractmethod
    def get_completed(self) -> Set[int]:
        """이 Step에서 완료된 씬 반환"""
        pass

    @abstractmethod
    def render_step_content(
        self,
        scenes: List[Dict],
        pool: Set[int],
        assigned: Set[int],
        completed: Set[int]
    ) -> Optional[Dict]:
        """Step별 콘텐츠 렌더링"""
        pass

    # ========================================
    # 공통 유틸리티 함수
    # ========================================

    def _format_scene_range(self, scene_ids: List[int]) -> str:
        """
        씬 ID 목록을 읽기 좋은 범위 문자열로 변환 (v1.1)

        연속된 씬만 범위로 표시하고, 비연속 씬은 개별 표시.

        예시:
        - [44] → "씬 44"
        - [90, 91] → "씬 90-91"
        - [44, 46, 90, 91, 94] → "씬 44, 46, 90-91, 94"
        - [46, 90, 91, 200] → "씬 46, 90-91, 200"

        Args:
            scene_ids: 씬 ID 목록

        Returns:
            포맷된 문자열 (예: "씬 90-91, 94, 106")
        """
        if not scene_ids:
            return "씬 없음"

        # 정렬 보장
        sorted_ids = sorted(scene_ids)

        if len(sorted_ids) == 1:
            return f"씬 {sorted_ids[0]}"

        # 연속된 씬 그룹 찾기
        groups = []
        current_group = [sorted_ids[0]]

        for i in range(1, len(sorted_ids)):
            if sorted_ids[i] == sorted_ids[i - 1] + 1:
                # 연속됨 - 현재 그룹에 추가
                current_group.append(sorted_ids[i])
            else:
                # 연속 끊김 - 현재 그룹 저장하고 새 그룹 시작
                groups.append(current_group)
                current_group = [sorted_ids[i]]

        # 마지막 그룹 추가
        groups.append(current_group)

        # 그룹을 문자열로 변환
        parts = []
        for group in groups:
            if len(group) == 1:
                parts.append(str(group[0]))
            else:
                # 2개 이상이면 범위로 표시
                parts.append(f"{group[0]}-{group[-1]}")

        return "씬 " + ", ".join(parts)

    def _create_simple_bundles(self, scene_ids: Set[int], bundle_size: int = 3) -> List[Dict]:
        """
        선택된 씬들을 단순 분할하여 새 묶음 생성 (v1.2)

        핵심: 원본 bundle_id를 무시하고, 선택된 씬들을 정렬 후 bundle_size개씩 나눔

        Args:
            scene_ids: 선택된 씬 ID 집합
            bundle_size: 묶음당 씬 개수 (기본값: 3)

        Returns:
            묶음 리스트 [{"bundle_id": 1, "scene_ids": [44, 46, 90], "scene_range": "씬 44, 46, 90"}, ...]

        예시:
            입력: {44, 46, 90, 91, 94, 96, 97, 98, 100} (9개)
            bundle_size: 3
            출력: [
                {"bundle_id": 1, "scene_ids": [44, 46, 90]},
                {"bundle_id": 2, "scene_ids": [91, 94, 96]},
                {"bundle_id": 3, "scene_ids": [97, 98, 100]},
            ]
        """
        if not scene_ids:
            return []

        # ✅ 핵심 1: 씬 ID 정렬
        sorted_ids = sorted(scene_ids)

        bundles = []
        bundle_id = 1

        # ✅ 핵심 2: bundle_size개씩 단순 분할
        for i in range(0, len(sorted_ids), bundle_size):
            bundle_scenes = sorted_ids[i:i + bundle_size]

            bundles.append({
                "bundle_id": bundle_id,
                "scene_ids": bundle_scenes,
                "scene_range": self._format_scene_range(bundle_scenes),
                "representative_id": bundle_scenes[0]  # 대표 씬 = 첫 번째 씬
            })

            bundle_id += 1

        # 디버그 로그
        print(f"\n[{self.step_name}] ========== 🆕 새 묶음 생성 결과 (v1.2) ==========")
        print(f"[{self.step_name}] 선택된 씬: {len(sorted_ids)}개")
        print(f"[{self.step_name}] 묶음 크기: {bundle_size}개/묶음")
        print(f"[{self.step_name}] 생성된 묶음: {len(bundles)}개")

        for b in bundles[:5]:  # 처음 5개만 출력
            print(f"[{self.step_name}] ✅ 묶음 {b['bundle_id']}: {b['scene_range']}")

        if len(bundles) > 5:
            print(f"[{self.step_name}] ... 외 {len(bundles) - 5}개 묶음")

        print(f"[{self.step_name}] =====================================================\n")

        return bundles

    def _get_bundle_for_scene(self, scene_id: int, bundles: List[Dict]) -> Optional[Dict]:
        """씬 ID가 속한 묶음 찾기 (v1.2)"""
        for bundle in bundles:
            if scene_id in bundle.get("scene_ids", []):
                return bundle
        return None

    # ========================================
    # 공통 UI 컴포넌트
    # ========================================

    def render_scene_list(
        self,
        scene_ids: Set[int],
        scenes: List[Dict],
        title: str = "씬 목록",
        show_checkbox: bool = True,
        key_prefix: str = ""
    ) -> Set[int]:
        """
        씬 목록 렌더링 (체크박스 포함)

        v1.1: WorkflowManager의 scene_map 사용 (bundle_id 일관성 보장)

        Returns:
            선택된 씬 ID 집합
        """
        if not scene_ids:
            st.info(f"대상 씬이 없습니다.")
            return set()

        selected = set()
        # v1.1: self.manager.scene_map 사용 (scenes.json의 정확한 bundle_id 참조)
        scene_map = self.manager.scene_map

        # 전체 선택 체크박스
        if show_checkbox:
            col1, col2, col3 = st.columns([1, 1, 2])
            with col1:
                select_all = st.checkbox(
                    "전체 선택",
                    key=f"{key_prefix}_select_all_{self.step}"
                )
            with col2:
                st.write(f"대상: {len(scene_ids)}개")

        st.markdown(f"#### {title}")

        # 씬 카드 렌더링
        sorted_ids = sorted(scene_ids)

        # 페이지네이션
        items_per_page = 20
        total_pages = (len(sorted_ids) + items_per_page - 1) // items_per_page

        if total_pages > 1:
            page = st.selectbox(
                "페이지",
                range(1, total_pages + 1),
                key=f"{key_prefix}_page_{self.step}"
            )
        else:
            page = 1

        start_idx = (page - 1) * items_per_page
        end_idx = min(start_idx + items_per_page, len(sorted_ids))
        page_ids = sorted_ids[start_idx:end_idx]

        # 묶음별 그룹화 옵션
        if self.step_unit == "bundle":
            self._render_bundle_grouped_list(page_ids, scene_map, selected, select_all if show_checkbox else False, key_prefix)
        else:
            self._render_scene_list(page_ids, scene_map, selected, select_all if show_checkbox else False, key_prefix)

        if show_checkbox:
            if select_all:
                return scene_ids.copy()

        return selected

    def _render_scene_list(
        self,
        scene_ids: List[int],
        scene_map: Dict,
        selected: Set[int],
        select_all: bool,
        key_prefix: str
    ):
        """개별 씬 목록 렌더링"""
        for sid in scene_ids:
            scene = scene_map.get(sid, {})
            script = scene.get('script_text', scene.get('narration', ''))[:80]
            status_str = scene.get('scene_status', 'pending')

            col1, col2, col3 = st.columns([0.5, 1, 4])

            with col1:
                if st.checkbox(
                    f"씬 {sid} 선택",
                    value=select_all,
                    key=f"{key_prefix}_scene_{sid}_{self.step}",
                    label_visibility="collapsed"
                ):
                    selected.add(sid)

            with col2:
                st.markdown(f"**씬 {sid}**")

            with col3:
                st.markdown(f"{script}...")

    def _render_bundle_grouped_list(
        self,
        representative_ids: List[int],
        scene_map: Dict,
        selected: Set[int],
        select_all: bool,
        key_prefix: str
    ):
        """묶음별 그룹화 목록 렌더링"""
        for sid in representative_ids:
            scene = scene_map.get(sid, {})
            bundle_id = scene.get('bundle_id', sid)
            bundle_scenes = self.manager.bundle_map.get(bundle_id, [sid])

            script = scene.get('script_text', scene.get('narration', ''))[:60]

            with st.container():
                col1, col2, col3, col4 = st.columns([0.5, 1.5, 1, 3])

                with col1:
                    if st.checkbox(
                        f"묶음 {bundle_id} 선택",
                        value=select_all,
                        key=f"{key_prefix}_bundle_{bundle_id}_{self.step}",
                        label_visibility="collapsed"
                    ):
                        selected.add(sid)

                with col2:
                    st.markdown(f"**묶음 {bundle_id}**")

                with col3:
                    # v1.1: 연속된 씬만 범위로 표시
                    scene_range = self._format_scene_range(bundle_scenes)
                    st.caption(scene_range)

                with col4:
                    st.markdown(f"{script}...")

    def render_execution_buttons(
        self,
        selected: Set[int],
        on_assign: Callable[[Set[int]], None],
        on_execute: Callable[[Set[int]], Optional[Dict]] = None,
        execute_label: str = "실행",
        show_skip: bool = True
    ) -> Optional[Dict]:
        """
        실행 버튼들 렌더링

        Returns:
            실행 결과 (on_execute가 있는 경우)
        """
        st.markdown("---")

        cols = st.columns([2, 2, 1, 1])

        with cols[0]:
            if st.button(
                f"📋 {len(selected)}개 할당",
                type="secondary",
                disabled=len(selected) == 0,
                key=f"step{self.step}_assign",
                use_container_width=True
            ):
                on_assign(selected)
                st.success(f"✅ {len(selected)}개 씬이 Step {self.step}에 할당되었습니다.")
                st.rerun()

        result = None
        with cols[1]:
            if on_execute and st.button(
                f"🚀 {execute_label}",
                type="primary",
                disabled=len(selected) == 0,
                key=f"step{self.step}_execute",
                use_container_width=True
            ):
                result = on_execute(selected)

        with cols[2]:
            assigned = self.get_assigned()
            if assigned and st.button(
                "↩️ 할당 해제",
                key=f"step{self.step}_unassign",
                use_container_width=True
            ):
                self.manager.unassign_from_step(self.step, assigned)
                self.manager.save()
                st.rerun()

        with cols[3]:
            if show_skip and st.button(
                "⏭️ 건너뛰기",
                key=f"step{self.step}_skip",
                use_container_width=True
            ):
                self.manager.state.current_step = self.step + 1
                self.manager.save()
                st.rerun()

        return result

    def render_affected_scenes_preview(self, selected: Set[int]):
        """선택으로 인해 영향받는 씬 미리보기"""
        if not selected:
            return

        affected = self.manager.get_scenes_affected_by_selection(selected, self.step)

        direct = affected.get('direct', set())
        prefix = affected.get('prefix', set())
        bundle = affected.get('bundle', set())
        total = affected.get('total', set())

        if prefix:
            st.warning(f"⚠️ **Prefix 규칙 적용**: {len(prefix)}개 추가 씬 포함")
            with st.expander(f"📋 Prefix 포함 씬 ({len(prefix)}개)", expanded=False):
                st.write(f"추가 씬: {sorted(prefix)}")

        elif bundle:
            extra = len(bundle)
            if extra > 0:
                st.info(f"ℹ️ **묶음 확장**: {len(direct)}개 대표 씬 → {len(total)}개 전체 씬")
