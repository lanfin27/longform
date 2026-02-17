# -*- coding: utf-8 -*-
"""
components/storyboard_workflow/step5_infographic.py
Step 5: 인포그래픽 대체 UI (v2.8)

처리 단위: 씬 (Scene) 또는 AI 추천
대상: Step 1-4 모두 처리/할당되지 않은 나머지 씬

v2.8: 미처리 필터 버그 수정 + 묶음 보존 필터 로직 반전
      - 캐시 키에 manager.state 해시 포함 (상태 변경 시 자동 무효화)
      - 상태 카운트 상호 배타적 계산 (중복 카운트 방지)
      - 'background_only' 상태를 'unprocessed'로 통합 (미처리로 취급)
      - 묶음 필터 로직 반전: 보존할 씬을 제외하고 나머지가 인포그래픽 대상
        (기존: 첫 씬만 남김 → 수정: 첫 씬 보존, 나머지만 인포그래픽)
      - 드롭다운 라벨 명확화: "묶음 첫 씬 보존 (나머지만 인포그래픽)"

v2.7: 씬 상태 표시 수정 + 묶음당 1개 필터 추가
      - 씬 상태 파일 기반 감지 추가 (manager.state가 비어있을 때 fallback)
      - 묶음당 첫 번째/마지막 씬만 선택 필터 추가 (원본 이미지 보존용)
      - 파일 상태 맵 캐싱으로 성능 최적화

v2.6: JSON 수동선택 반영 + 성능 최적화
      - JSON 다운로드에 수동 선택 씬 합산 (남은 씬 + 수동 추가)
      - 씬 상태 session_state 캐싱 (매 rerun마다 재계산 방지)
      - 페이지당 씬 수 20→12개로 축소 (렌더링 부하 감소)
      - "상태 새로고침" 버튼으로 캐시 무효화 지원

v2.5: 기존 JSON 다운로드 형식 복원
      - 기존 형식 (배열: scene_id, start_time, end_time, script_ko, image_prompt_en, visual_elements)
      - 수동 추가 씬도 포함한 최종 JSON 다운로드 버튼
      - 내부 관리용 메타데이터 저장은 별도 접기 섹션으로 분리

v2.4: "미처리 제외" 필터 옵션 추가
      - 이미 처리된 씬(한글텍스트/캐릭터/실사/비디오)만 표시
      - 타임라인뷰에서 덮어쓸 대상을 빠르게 선택 가능
      - 상태 카운트에 "전체/처리됨" 표시 추가

v2.3: 페이지 전환 시 수동 선택 유지 버그 수정
      - 영속적 session_state 세트 (infographic_manual_selected) 사용
      - 체크박스 on_change 콜백으로 선택 상태 동기화
      - 페이지 1 선택 → 페이지 2 이동 → 페이지 1 복귀 시 선택 유지

v2.2: 수동 선택 타임라인뷰 및 JSON 생성 기능
      - 전체 씬 타임라인뷰 (상태 배지 표시: 한글텍스트/캐릭터/실사/비디오/미처리)
      - 상태별 필터링 기능
      - 남은 씬 선택 + 수동 추가 선택 합산
      - 인포그래픽 대상 확정 JSON 생성 (data/infographic_targets.json)

v2.0: AI 모델/프롬프트 선택 및 타임라인 뷰 구현
      - InfographicAnalysisPromptManager 연동
      - InfographicChannelPreferences로 채널별 설정 저장
      - 프롬프트 선택/편집 UI 추가
      - 타임라인 뷰 (4열 그리드) 추가
      - 드래그앤드롭 이미지 대체 기능
      - 마지막 사용 모델/프롬프트 자동 로드

v1.1 변경사항:
- 선택된 씬 JSON 다운로드 기능 추가
- 지정된 6개 필드만 추출 (scene_id, start_time, end_time, script_ko, image_prompt_en, visual_elements)
- 기존 scenes.json 변경 없음 (읽기 전용)
"""

import streamlit as st
import json
import re
import os
import glob as glob_module
from typing import Set, Dict, List, Optional
from pathlib import Path
from PIL import Image
import time
import hashlib

from .step_ui_base import StepUIBase
from .progress_visualizer import render_step_status_cards

# v1.1: 인포그래픽 내보내기 유틸리티
from utils.infographic_export import (
    create_infographic_export_json,
    get_infographic_export_filename,
    INFOGRAPHIC_EXPORT_FIELDS
)

# v2.0: AI 모델 선택 유틸리티
from utils.ai_model_selector import render_model_selector, get_selected_model

# v2.0: 통합 AI 클라이언트
from utils.ai_client import UnifiedAIClient

# v2.0: 인포그래픽 프롬프트 및 채널 설정 관리
from utils.infographic_prompt_manager import (
    InfographicAnalysisPromptManager,
    InfographicChannelPreferences
)


# ═══════════════════════════════════════════════════════════════════
# v2.9: @st.fragment 래퍼 함수 (전체 페이지 rerun 방지 - 성능 최적화)
# fragment 내부의 위젯 인터랙션은 fragment만 재실행함
# ═══════════════════════════════════════════════════════════════════

@st.fragment
def _scene_selection_fragment(step5_ui_ref, display_pool, scenes_data):
    """씬 선택 UI - fragment (체크박스/페이지네이션 조작 시 전체 rerun 방지)"""
    selected = step5_ui_ref._render_scene_selection(display_pool, scenes_data)
    st.session_state['_step5_scene_selected'] = selected


@st.fragment
def _timeline_view_fragment(step5_ui_ref, display_pool, scenes_data):
    """타임라인 뷰 - fragment (체크박스/파일업로드 조작 시 전체 rerun 방지)"""
    step5_ui_ref._render_timeline_view(display_pool, scenes_data)


@st.fragment
def _manual_selection_fragment(step5_ui_ref, scenes_data):
    """수동 선택 타임라인 - fragment (체크박스/페이지네이션 조작 시 전체 rerun 방지)"""
    step5_ui_ref._render_manual_selection_timeline(scenes_data)


class Step5InfographicUI(StepUIBase):
    """Step 5: 인포그래픽 대체 (v2.9 - @st.fragment 성능 최적화)"""

    def __init__(self, workflow_manager, project_path: Path):
        super().__init__(
            step_number=5,
            workflow_manager=workflow_manager,
            project_path=project_path
        )

        # v1.1: 비디오 이름 추출 (다운로드 파일명용)
        self.video_name = self._get_video_name()

        # v2.0: 프롬프트 및 채널 설정 관리자 초기화
        self.prompt_manager = InfographicAnalysisPromptManager(str(project_path))
        self.channel_prefs = InfographicChannelPreferences(str(project_path))

    def _get_video_name(self) -> str:
        """비디오 이름 추출 (프로젝트 경로에서)"""
        try:
            # project_path = .../videos/{video_name}
            return self.project_path.name
        except:
            return "video"

    def get_pool(self) -> Set[int]:
        return self.manager.calculate_step5_pool()

    def get_assigned(self) -> Set[int]:
        return self.manager.state.step5_scenes

    def get_completed(self) -> Set[int]:
        return self.manager.state.completed_step5

    def render_step_content(
        self,
        scenes: List[Dict],
        pool: Set[int],
        assigned: Set[int],
        completed: Set[int]
    ) -> Optional[Dict]:
        """Step 5 콘텐츠 렌더링"""

        # 이전 Step 완료 확인
        prev_pending = sum([
            len(self.manager.state.step1_scenes - self.manager.state.completed_step1),
            len(self.manager.state.step2_scenes - self.manager.state.completed_step2),
            len(self.manager.state.step3_scenes - self.manager.state.completed_step3),
            len(self.manager.state.step4_scenes - self.manager.state.completed_step4),
        ])

        if prev_pending > 0:
            st.warning(f"이전 Step 대기 중: {prev_pending}개 씬")

        # 설명
        st.info("""
            **Step 5: 인포그래픽 대체**

            - **대상**: Step 1-4 모두 처리되지 않은 나머지 씬
            - **처리 단위**: 씬 (Scene) - AI 추천 또는 수동 선택
            - **방식**: 인포그래픽 템플릿으로 대체
        """)

        st.markdown("---")

        # v2.0: 채널 ID 가져오기 (세션에서)
        channel_id = st.session_state.get('selected_channel_id', 'default')

        # v2.0: AI 추천 섹션 (개선됨)
        with st.expander("AI 인포그래픽 분석", expanded=False):
            st.write("AI가 인포그래픽으로 대체하면 좋을 씬을 분석합니다.")

            # v2.0: 채널별 저장된 설정 로드
            saved_settings = self.channel_prefs.get_infographic_analysis_settings(channel_id)
            default_model = saved_settings.get('model', 'gemini-2.5-flash')
            default_prompt_id = saved_settings.get('prompt_id', 'default')

            # AI 모델 선택 드롭다운
            st.markdown("##### AI 모델 선택")
            selected_model = render_model_selector(
                key="step5_infographic_ai",
                task="scene_analysis",
                show_provider_filter=True,
                show_speed_filter=True,
                show_details=True,
                compact=False
            )

            if selected_model:
                st.caption(f"선택된 모델: `{selected_model}`")

            st.markdown("---")

            # v2.0: 프롬프트 선택 UI
            st.markdown("##### 분석 프롬프트 선택")

            # 사용 가능한 프롬프트 목록
            available_prompts = self.prompt_manager.list_prompts()
            prompt_options = {p['id']: f"{p['name']} - {p['description']}" for p in available_prompts}

            # 기본값 인덱스 찾기
            prompt_ids = list(prompt_options.keys())
            default_idx = prompt_ids.index(default_prompt_id) if default_prompt_id in prompt_ids else 0

            selected_prompt_id = st.selectbox(
                "프롬프트 템플릿",
                options=prompt_ids,
                format_func=lambda x: prompt_options.get(x, x),
                index=default_idx,
                key="step5_prompt_selector"
            )

            # 프롬프트 미리보기
            if selected_prompt_id:
                prompt_data = self.prompt_manager.get_prompt(selected_prompt_id)
                if prompt_data:
                    with st.expander("프롬프트 미리보기", expanded=False):
                        st.code(prompt_data.get('content', '')[:1000] + "...", language="markdown")

            # 프롬프트 관리 버튼
            col_pm1, col_pm2 = st.columns(2)
            with col_pm1:
                if st.button("프롬프트 편집/추가", key="step5_edit_prompt"):
                    st.session_state['step5_show_prompt_editor'] = True
            with col_pm2:
                if st.button("현재 설정 저장", key="step5_save_settings"):
                    if selected_model and selected_prompt_id:
                        self.channel_prefs.save_infographic_analysis_settings(
                            channel_id=channel_id,
                            model=selected_model,
                            prompt_id=selected_prompt_id
                        )
                        st.success(f"채널 '{channel_id}' 기본 설정 저장 완료")

            # v2.0: 프롬프트 편집 UI
            if st.session_state.get('step5_show_prompt_editor', False):
                self._render_prompt_editor()

            st.markdown("---")

            # AI 분석 실행 버튼
            if st.button("AI 분석 실행", key="step5_ai_analysis"):
                if not selected_model:
                    st.error("AI 모델을 선택해주세요.")
                elif not pool:
                    st.warning("분석할 대상 씬이 없습니다.")
                else:
                    # v2.0: 선택된 프롬프트로 AI 분석 실행
                    self._run_infographic_detection(scenes, pool, selected_model, selected_prompt_id)

                    # 사용한 설정 자동 저장
                    self.channel_prefs.save_infographic_analysis_settings(
                        channel_id=channel_id,
                        model=selected_model,
                        prompt_id=selected_prompt_id
                    )

        st.markdown("---")

        # 인포그래픽 설정
        with st.expander("인포그래픽 설정", expanded=True):
            col1, col2 = st.columns(2)

            with col1:
                infographic_style = st.selectbox(
                    "스타일",
                    ["모던 다크", "라이트 클린", "컬러풀", "미니멀"],
                    key="step5_style"
                )

                template_type = st.selectbox(
                    "템플릿 유형",
                    ["자동 선택", "데이터 차트", "비교 표", "타임라인", "프로세스"],
                    key="step5_template"
                )

            with col2:
                color_scheme = st.selectbox(
                    "색상 스키마",
                    ["자동", "블루", "그린", "퍼플", "오렌지"],
                    key="step5_color"
                )

                include_script = st.checkbox(
                    "스크립트 텍스트 포함",
                    value=True,
                    key="step5_include_script"
                )

        st.markdown("---")

        # 대상 씬 목록
        st.markdown("#### 대상 씬 목록 (남은 씬)")

        if not pool:
            st.success("모든 씬이 처리되었습니다!")

            # 완료 요약
            stats = self.manager.get_statistics()
            st.markdown("### 워크플로우 완료 요약")

            summary_cols = st.columns(5)
            for i, step in enumerate(range(1, 6)):
                step_stats = stats.get(f'step{step}', {})
                with summary_cols[i]:
                    st.metric(f"Step {step}", f"{step_stats.get('completed', 0)}개")

            return None

        # v2.0: 감지된 씬 필터 적용
        display_pool = pool
        filter_active = st.session_state.get('step5_filter_detected_only', False)

        if filter_active:
            detected_scenes = st.session_state.get('step5_ai_detected_scenes', [])
            if detected_scenes:
                detected_ids = set()
                for item in detected_scenes:
                    sid = item.get('scene_id')
                    if sid is not None:
                        try:
                            detected_ids.add(int(sid))
                        except (ValueError, TypeError):
                            pass

                pool_int = {int(x) for x in pool}
                display_pool = pool_int & detected_ids

                if display_pool:
                    st.info(f"**필터 적용 중**: 감지된 {len(display_pool)}개 씬만 표시 (전체 대상: {len(pool)}개)")
                else:
                    st.warning(f"감지된 씬이 현재 대상 풀과 겹치지 않습니다.")
                    display_pool = pool

                if st.button("필터 해제", key="step5_clear_filter"):
                    st.session_state['step5_filter_detected_only'] = False
                    st.rerun()
            else:
                st.warning("AI 분석을 먼저 실행해주세요. 필터가 해제됩니다.")
                st.session_state['step5_filter_detected_only'] = False

        # ═══════════════════════════════════════════════════════════════════
        # v2.9: @st.fragment로 분리 - 체크박스/페이지 조작 시 전체 페이지 rerun 방지
        # ═══════════════════════════════════════════════════════════════════

        # 씬 선택 (남은 씬 목록) - fragment
        _scene_selection_fragment(self, display_pool, scenes)
        selected = st.session_state.get('_step5_scene_selected', set())

        # v1.1: JSON 다운로드 섹션
        st.markdown("---")
        self._render_json_download_section(scenes, selected)

        # v2.0: 타임라인 뷰 (개별 씬 이미지 대체) - fragment
        st.markdown("---")
        _timeline_view_fragment(self, display_pool, scenes)

        # v2.2: 수동 선택 타임라인뷰 (전체 씬 대상, 상태 배지 표시) - fragment
        st.markdown("---")
        _manual_selection_fragment(self, scenes)
        manual_selected = st.session_state.get('infographic_manual_selected', set())

        # ═══════════════════════════════════════════════════════════════════
        # v2.2: 최종 선택 요약 및 JSON 생성
        # ═══════════════════════════════════════════════════════════════════
        st.markdown("---")
        final_targets = self._render_final_selection_summary(selected, manual_selected, scenes)

        st.markdown("---")

        # 실행 버튼 (final_targets 사용)
        def on_assign(ids):
            self.manager.assign_to_step(5, ids, apply_expansion=False)
            self.manager.save()

        def on_execute(ids):
            return {
                "action": "infographic_replace",
                "step": 5,
                "scene_ids": sorted(ids),
                "settings": {
                    "style": infographic_style,
                    "template": template_type,
                    "color_scheme": color_scheme,
                    "include_script": include_script
                }
            }

        # v2.2: 최종 합산된 대상으로 실행
        execution_targets = final_targets if final_targets else selected

        return self.render_execution_buttons(
            execution_targets,
            on_assign=on_assign,
            on_execute=on_execute,
            execute_label="인포그래픽 생성",
            show_skip=False  # 마지막 Step은 건너뛰기 불필요
        )

    def _render_scene_selection(self, pool: Set[int], scenes: List[Dict]) -> Set[int]:
        """씬 선택 UI (v2.8: 묶음 보존 필터 - 로직 반전)"""
        selected = set()
        scene_map = self.manager.scene_map

        # v2.8: 전체 선택 + 묶음 보존 필터 (라벨 명확화)
        col1, col2, col3 = st.columns([1, 2, 1.5])
        with col1:
            select_all = st.checkbox("전체 선택", key="step5_select_all")
        with col2:
            bundle_filter = st.selectbox(
                "묶음 필터",
                options=[
                    "전체 (모든 씬)",
                    "묶음 첫 씬 보존 (나머지만 인포그래픽)",
                    "묶음 마지막 씬 보존 (나머지만 인포그래픽)"
                ],
                index=0,
                key="step5_bundle_filter",
                help="각 묶음에서 1개 씬의 원본 이미지를 보존(제외)하고, 나머지만 인포그래픽 대상으로 선택합니다.",
                label_visibility="collapsed"
            )
        with col3:
            st.caption(f"남은 씬: {len(pool)}개")

        # v2.8: 묶음 보존 필터 적용 (로직 반전 - 보존할 씬 제외)
        if bundle_filter != "전체 (모든 씬)":
            filtered_pool, preserved_count = self._exclude_preserved_per_bundle(
                pool, scenes,
                preserve='first' if "첫 씬" in bundle_filter else 'last'
            )
            st.info(f"🔒 **{preserved_count}개 씬 원본 보존** → 인포그래픽 대상: {len(filtered_pool)}개")
        else:
            filtered_pool = pool

        # 페이지네이션
        sorted_pool = sorted(filtered_pool)
        items_per_page = 20
        total_pages = max(1, (len(sorted_pool) + items_per_page - 1) // items_per_page)

        if total_pages > 1:
            page = st.number_input(
                "페이지",
                min_value=1,
                max_value=total_pages,
                value=1,
                key="step5_page"
            )
        else:
            page = 1

        start_idx = (page - 1) * items_per_page
        end_idx = min(start_idx + items_per_page, len(sorted_pool))
        page_items = sorted_pool[start_idx:end_idx]

        # 씬 카드 렌더링
        for sid in page_items:
            scene = scene_map.get(sid, {})
            bundle_id = scene.get('bundle_id', sid)

            script = scene.get('script_text', scene.get('narration', ''))[:70]

            with st.container():
                cols = st.columns([0.4, 1, 4])

                with cols[0]:
                    is_selected = st.checkbox(
                        f"씬 {sid} 선택",
                        value=select_all,
                        key=f"step5_scene_{sid}",
                        label_visibility="collapsed"
                    )
                    if is_selected:
                        selected.add(sid)

                with cols[1]:
                    st.markdown(f"**씬 {sid}**")

                with cols[2]:
                    st.markdown(f"<small>{script}...</small>", unsafe_allow_html=True)

        if select_all:
            return filtered_pool.copy()  # v2.7: 필터링된 풀 반환

        return selected

    def _exclude_preserved_per_bundle(
        self, pool: Set[int], scenes: List[Dict], preserve: str = 'first'
    ) -> tuple:
        """
        v2.8: 각 묶음에서 보존할 1개 씬을 제외하고, 나머지를 인포그래픽 대상으로 반환

        목적: 원본 이미지 보존을 위해 각 묶음에서 1개 씬을 인포그래픽 대상에서 제외

        Args:
            pool: 남은 씬 ID 집합
            scenes: 전체 씬 데이터
            preserve: 'first' (첫 번째 씬 보존) 또는 'last' (마지막 씬 보존)

        Returns:
            (인포그래픽 대상 씬 집합, 보존된 씬 수) 튜플
        """
        # bundle_id → scene_ids 맵 구축
        bundle_to_scenes = {}
        scene_to_bundle = {}

        for scene in scenes:
            sid = scene.get('scene_id', scene.get('id', 0))
            bundle_id = scene.get('bundle_id', sid)  # bundle_id 없으면 자기 자신
            if sid:
                if bundle_id not in bundle_to_scenes:
                    bundle_to_scenes[bundle_id] = []
                bundle_to_scenes[bundle_id].append(sid)
                scene_to_bundle[sid] = bundle_id

        to_exclude = set()  # 보존할 씬 (인포그래픽에서 제외)
        processed_bundles = set()

        for sid in sorted(pool):
            bundle_id = scene_to_bundle.get(sid, sid)

            if bundle_id in processed_bundles:
                continue  # 이 묶음은 이미 처리됨

            # 이 묶음에서 pool에 포함된 씬들
            bundle_scenes = sorted(bundle_to_scenes.get(bundle_id, [sid]))
            in_pool = [s for s in bundle_scenes if s in pool]

            if len(in_pool) >= 2:
                # 2개 이상일 때만 1개 보존 (나머지는 인포그래픽 대상)
                preserved = in_pool[0] if preserve == 'first' else in_pool[-1]
                to_exclude.add(preserved)
            # 1개만 있으면 보존하지 않음 (인포그래픽 대상 유지)

            processed_bundles.add(bundle_id)

        # 보존 씬을 제외한 나머지가 인포그래픽 대상
        result = pool - to_exclude
        return result, len(to_exclude)

    def _render_json_download_section(
        self,
        scenes: List[Dict],
        selected: Set[int]
    ):
        """
        v2.6: 선택된 씬 JSON 다운로드 섹션
        ⭐ 수동 선택 씬도 자동 합산하여 다운로드
        """
        # ⭐ v2.6: 수동 선택 씬 합산
        manual_selected = st.session_state.get('infographic_manual_selected', set())
        combined_selected = set(selected) | set(manual_selected)

        st.markdown("#### 선택 씬 JSON 다운로드")

        col1, col2, col3 = st.columns([2, 2, 1])

        with col1:
            if combined_selected:
                st.markdown(f"**선택된 씬**: {len(combined_selected)}개")
                # 구성 표시
                if manual_selected:
                    st.caption(f"(남은 씬 {len(selected)}개 + 수동 추가 {len(manual_selected)}개)")
                sorted_ids = sorted(combined_selected)
                if len(sorted_ids) <= 10:
                    st.caption(f"씬 ID: {sorted_ids}")
                else:
                    st.caption(f"씬 ID: {sorted_ids[:5]} ... {sorted_ids[-3:]} ({len(sorted_ids)}개)")
            else:
                st.markdown("**선택된 씬**: 0개")
                st.caption("다운로드할 씬을 선택하세요")

        with col2:
            with st.expander("추출 필드 정보", expanded=False):
                st.markdown("다음 필드만 추출됩니다:")
                for field in INFOGRAPHIC_EXPORT_FIELDS:
                    st.markdown(f"- `{field}`")
                st.caption("기존 scenes.json은 변경되지 않습니다.")

        with col3:
            if combined_selected:
                # ⭐ v2.6: 합산된 씬 ID로 JSON 생성
                json_str = create_infographic_export_json(
                    scenes=scenes,
                    selected_scene_ids=combined_selected,
                    video_name=self.video_name
                )

                filename = get_infographic_export_filename(
                    video_name=self.video_name,
                    scene_ids=list(combined_selected)
                )

                st.download_button(
                    label=f"JSON ({len(combined_selected)}개)",
                    data=json_str,
                    file_name=filename,
                    mime="application/json",
                    key="step5_json_download",
                    type="primary"
                )
            else:
                st.button(
                    "JSON 다운로드",
                    disabled=True,
                    key="step5_json_download_disabled",
                    help="다운로드할 씬을 먼저 선택하세요"
                )

    def _render_prompt_editor(self):
        """v2.0: 프롬프트 편집/추가 UI"""
        st.markdown("---")
        st.markdown("#### 프롬프트 관리")

        tab_edit, tab_add = st.tabs(["기존 편집", "새로 추가"])

        with tab_edit:
            available = self.prompt_manager.list_prompts()
            editable = [p for p in available if not p.get('is_system', False)]

            if not editable:
                st.info("편집 가능한 사용자 정의 프롬프트가 없습니다. '새로 추가' 탭에서 프롬프트를 만들어보세요.")
                st.caption("시스템 기본 프롬프트(기본 분석, 데이터 중심, 비교 분석, 타임라인 분석)는 편집할 수 없습니다.")
            else:
                edit_prompt_id = st.selectbox(
                    "편집할 프롬프트",
                    options=[p['id'] for p in editable],
                    format_func=lambda x: next((p['name'] for p in editable if p['id'] == x), x),
                    key="step5_edit_prompt_select"
                )

                if edit_prompt_id:
                    prompt_data = self.prompt_manager.get_prompt(edit_prompt_id)
                    if prompt_data:
                        edit_name = st.text_input(
                            "이름",
                            value=prompt_data.get('name', ''),
                            key="step5_edit_name"
                        )
                        edit_desc = st.text_input(
                            "설명",
                            value=prompt_data.get('description', ''),
                            key="step5_edit_desc"
                        )
                        edit_content = st.text_area(
                            "프롬프트 내용",
                            value=prompt_data.get('content', ''),
                            height=300,
                            key="step5_edit_content"
                        )

                        col_save, col_delete, col_cancel = st.columns(3)
                        with col_save:
                            if st.button("저장", key="step5_save_edit"):
                                self.prompt_manager.save_prompt(
                                    prompt_id=edit_prompt_id,
                                    name=edit_name,
                                    description=edit_desc,
                                    content=edit_content,
                                    is_system=False
                                )
                                st.success("프롬프트 저장 완료")
                                st.session_state['step5_show_prompt_editor'] = False
                                st.rerun()
                        with col_delete:
                            if st.button("삭제", key="step5_delete_prompt"):
                                if self.prompt_manager.delete_prompt(edit_prompt_id):
                                    st.success("프롬프트 삭제 완료")
                                    st.session_state['step5_show_prompt_editor'] = False
                                    st.rerun()
                                else:
                                    st.error("삭제 실패")
                        with col_cancel:
                            if st.button("취소", key="step5_cancel_edit"):
                                st.session_state['step5_show_prompt_editor'] = False
                                st.rerun()

        with tab_add:
            new_id = st.text_input(
                "프롬프트 ID (영문, 숫자, 밑줄만)",
                placeholder="my_custom_prompt",
                key="step5_new_id"
            )
            new_name = st.text_input(
                "표시 이름",
                placeholder="내 커스텀 분석",
                key="step5_new_name"
            )
            new_desc = st.text_input(
                "설명",
                placeholder="이 프롬프트의 용도 설명",
                key="step5_new_desc"
            )

            default_template = self.prompt_manager.get_prompt('default')
            template_content = default_template.get('content', '') if default_template else ''

            new_content = st.text_area(
                "프롬프트 내용",
                value=template_content,
                height=300,
                key="step5_new_content",
                help="기본 프롬프트를 템플릿으로 시작합니다. 필요에 맞게 수정하세요."
            )

            col_add, col_cancel_add = st.columns(2)
            with col_add:
                if st.button("추가", key="step5_add_new"):
                    if not new_id or not new_name:
                        st.error("ID와 이름은 필수입니다.")
                    elif not new_id.replace('_', '').isalnum():
                        st.error("ID는 영문, 숫자, 밑줄만 사용 가능합니다.")
                    else:
                        self.prompt_manager.save_prompt(
                            prompt_id=new_id,
                            name=new_name,
                            description=new_desc or new_name,
                            content=new_content,
                            is_system=False
                        )
                        st.success(f"프롬프트 '{new_name}' 추가 완료")
                        st.session_state['step5_show_prompt_editor'] = False
                        st.rerun()
            with col_cancel_add:
                if st.button("취소", key="step5_cancel_add"):
                    st.session_state['step5_show_prompt_editor'] = False
                    st.rerun()

        st.markdown("---")

    def _render_timeline_view(self, pool: Set[int], scenes: List[Dict]):
        """v2.1: 타임라인 뷰 렌더링 - 4열 그리드 + 드래그앤드롭 + 수동 선택"""
        with st.expander("타임라인 뷰 (개별 씬 이미지 대체)", expanded=False):
            completed_step5 = self.manager.state.completed_step5
            all_scenes_for_timeline = pool | completed_step5

            if not all_scenes_for_timeline:
                st.info("표시할 씬이 없습니다.")
                return

            st.markdown("""
            **사용법**: 체크박스로 씬을 선택하거나, 이미지를 드래그앤드롭하면 **즉시 대체**됩니다.
            """)

            # v2.1: 선택 컨트롤
            all_timeline_ids = sorted(all_scenes_for_timeline)

            # 현재 선택된 씬 수 계산
            tl_selected_count = sum(
                1 for sid in all_timeline_ids
                if st.session_state.get(f"step5_tl_select_{sid}", False)
            )

            sel_ctrl_col1, sel_ctrl_col2, sel_ctrl_col3, sel_ctrl_col4 = st.columns([1.5, 1, 1, 1])

            with sel_ctrl_col1:
                st.markdown(f"**선택된 씬: {tl_selected_count}개** / {len(all_timeline_ids)}개")

            with sel_ctrl_col2:
                if st.button("전체 선택", key="step5_tl_select_all", use_container_width=True):
                    for sid in all_timeline_ids:
                        st.session_state[f"step5_tl_select_{sid}"] = True
                    st.rerun()

            with sel_ctrl_col3:
                if st.button("전체 해제", key="step5_tl_deselect_all", use_container_width=True):
                    for sid in all_timeline_ids:
                        st.session_state[f"step5_tl_select_{sid}"] = False
                    st.rerun()

            with sel_ctrl_col4:
                if st.button("선택 반전", key="step5_tl_invert", use_container_width=True):
                    for sid in all_timeline_ids:
                        current = st.session_state.get(f"step5_tl_select_{sid}", False)
                        st.session_state[f"step5_tl_select_{sid}"] = not current
                    st.rerun()

            st.markdown("---")

            # 필터 옵션
            filter_col1, filter_col2, filter_col3 = st.columns(3)
            with filter_col1:
                filter_mode = st.radio(
                    "필터",
                    ["전체", "대체 필요", "대체 완료"],
                    horizontal=True,
                    key="step5_timeline_filter"
                )

            if filter_mode == "전체":
                display_pool = all_scenes_for_timeline
            elif filter_mode == "대체 필요":
                display_pool = pool - completed_step5
            else:
                display_pool = completed_step5

            with filter_col2:
                st.caption(f"대기: {len(pool - completed_step5)}개")
            with filter_col3:
                st.caption(f"완료: {len(completed_step5)}개")

            if not display_pool:
                st.info(f"'{filter_mode}' 조건에 해당하는 씬이 없습니다.")
                return

            # 이미지 경로
            composited_dir = self.project_path / "images" / "composited"
            scene_images_dir = self.project_path / "images" / "scenes"
            backgrounds_dir = self.project_path / "images" / "backgrounds"
            infographic_dir = self.project_path / "images" / "infographic"

            infographic_dir.mkdir(parents=True, exist_ok=True)

            sorted_pool = sorted(display_pool)

            # 4열 그리드
            cols_per_row = 4
            for i in range(0, len(sorted_pool), cols_per_row):
                row_scenes = sorted_pool[i:i + cols_per_row]
                cols = st.columns(cols_per_row)

                for j, sid in enumerate(row_scenes):
                    with cols[j]:
                        scene = self.manager.scene_map.get(sid, {})
                        script = scene.get('script_text', scene.get('narration', ''))[:40]

                        is_replaced = sid in completed_step5

                        # v2.1: 체크박스 + 씬 헤더
                        check_col, label_col = st.columns([0.3, 0.7])
                        with check_col:
                            st.checkbox(
                                f"select_{sid}",
                                key=f"step5_tl_select_{sid}",
                                label_visibility="collapsed"
                            )
                        with label_col:
                            if is_replaced:
                                st.markdown(f"**씬 {sid}** (완료)")
                            else:
                                st.markdown(f"**씬 {sid}**")

                        current_image = self._find_scene_image(
                            sid, composited_dir, scene_images_dir, backgrounds_dir, infographic_dir
                        )

                        if current_image and current_image.exists():
                            st.image(str(current_image), use_container_width=True)
                            if is_replaced:
                                st.caption("인포그래픽 대체됨")
                        else:
                            st.markdown(
                                "<div style='height:100px;background:#333;display:flex;"
                                "align-items:center;justify-content:center;border-radius:4px;'>"
                                "<span style='color:#999;'>이미지 없음</span></div>",
                                unsafe_allow_html=True
                            )

                        st.caption(f"{script}...")

                        # AI 감지 여부 표시
                        detected_scenes = st.session_state.get('step5_ai_detected_scenes', [])
                        detected_info = next(
                            (item for item in detected_scenes if item.get('scene_id') == sid),
                            None
                        )
                        if detected_info and not is_replaced:
                            rec_type = detected_info.get('recommended_type', 'unknown')
                            st.markdown(f"**인포그래픽 적합** ({rec_type})")

                        # 드래그앤드롭
                        uploader_key = f"step5_dnd_upload_{sid}"
                        processed_hash_key = f"step5_processed_hash_{sid}"

                        individual_file = st.file_uploader(
                            f"씬 {sid} - 드래그앤드롭",
                            type=["png", "jpg", "jpeg", "webp"],
                            key=uploader_key,
                            label_visibility="collapsed",
                            help="이미지를 드래그앤드롭하면 즉시 대체됩니다"
                        )

                        if individual_file is not None:
                            file_content = individual_file.getvalue()
                            file_hash = hashlib.md5(file_content).hexdigest()[:16]
                            previous_hash = st.session_state.get(processed_hash_key, "")

                            if file_hash != previous_hash:
                                print(f"[Step5] 씬 {sid}: 새 파일 감지 (hash={file_hash[:8]})")
                                individual_file.seek(0)

                                with st.spinner(f"씬 {sid} 이미지 대체 중..."):
                                    result = self._replace_single_scene_image(
                                        sid, individual_file, scene, infographic_dir
                                    )
                                    if result:
                                        st.session_state[processed_hash_key] = file_hash
                                        st.success(f"씬 {sid} 대체 완료!")
                                    else:
                                        st.error(f"씬 {sid} 대체 실패")

                        if is_replaced:
                            if st.button("다시 대체", key=f"step5_re_replace_{sid}", use_container_width=True):
                                if individual_file:
                                    result = self._replace_single_scene_image(
                                        sid, individual_file, scene, infographic_dir
                                    )
                                    if result:
                                        st.success(f"씬 {sid} 다시 대체 완료!")
                                        st.rerun()
                                else:
                                    st.warning("이미지를 먼저 드래그앤드롭하세요")

            st.markdown("---")

            # v2.1: 선택된 씬 수집 및 JSON 다운로드
            tl_selected = set()
            for sid in all_timeline_ids:
                if st.session_state.get(f"step5_tl_select_{sid}", False):
                    tl_selected.add(sid)

            # 세션에 저장 (다른 기능에서 활용 가능)
            st.session_state["step5_timeline_selected_scenes"] = tl_selected

            dl_col1, dl_col2, dl_col3 = st.columns([2, 1, 1])
            with dl_col1:
                st.caption(f"표시 중: {len(display_pool)}개 / 전체: {len(all_scenes_for_timeline)}개 / 선택: {len(tl_selected)}개")
            with dl_col2:
                if tl_selected:
                    json_str = create_infographic_export_json(
                        scenes=scenes,
                        selected_scene_ids=tl_selected,
                        video_name=self.video_name
                    )
                    filename = get_infographic_export_filename(
                        video_name=self.video_name,
                        scene_ids=list(tl_selected)
                    )
                    st.download_button(
                        label=f"선택 씬 JSON ({len(tl_selected)}개)",
                        data=json_str,
                        file_name=filename,
                        mime="application/json",
                        key="step5_tl_json_download",
                        use_container_width=True
                    )
                else:
                    st.button(
                        "JSON 다운로드",
                        disabled=True,
                        key="step5_tl_json_download_disabled",
                        help="다운로드할 씬을 선택하세요",
                        use_container_width=True
                    )
            with dl_col3:
                if tl_selected:
                    st.caption(f"씬: {sorted(tl_selected)[:8]}{'...' if len(tl_selected) > 8 else ''}")

    def _replace_single_scene_image(
        self,
        scene_id: int,
        uploaded_file,
        scene: Dict,
        infographic_dir: Path
    ) -> bool:
        """개별 씬 인포그래픽 이미지 대체 (기존 파일 덮어쓰기)"""
        try:
            ext = Path(uploaded_file.name).suffix.lower()
            if ext not in ['.png', '.jpg', '.jpeg', '.webp']:
                ext = '.png'

            # 기존 인포그래픽 이미지 삭제 (씬당 1개만 유지)
            import glob as glob_module
            for pattern in [f"infographic_{scene_id:03d}_*.*", f"infographic_scene_{scene_id:03d}_*.*"]:
                for old_file in glob_module.glob(str(infographic_dir / pattern)):
                    try:
                        os.remove(old_file)
                        print(f"[Step5] 기존 파일 삭제: {Path(old_file).name}")
                    except OSError:
                        pass

            timestamp = int(time.time() * 1000)
            output_filename = f"infographic_{scene_id:03d}_{timestamp}{ext}"
            output_path = infographic_dir / output_filename

            image = Image.open(uploaded_file)

            if ext in ['.jpg', '.jpeg']:
                image = image.convert('RGB')
                image.save(output_path, quality=95)
            else:
                image.save(output_path)

            print(f"[Step5] 씬 {scene_id} 인포그래픽 이미지 저장 완료: {output_filename}")

            self._update_scenes_json_image_path(scene_id, str(output_path), timestamp)
            self._invalidate_scene_image_cache(scene_id)

            self.manager.mark_completed(5, {scene_id})
            self.manager.save()

            print(f"[Step5] 씬 {scene_id} 대체 완료 (데이터 동기화됨)")

            return True

        except Exception as e:
            print(f"[Step5] 씬 {scene_id} 이미지 대체 실패: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _update_scenes_json_image_path(self, scene_id: int, new_image_path: str, timestamp: int):
        """scenes.json에 새 이미지 경로 업데이트"""
        scenes_path = self.project_path / "analysis" / "scenes.json"

        if not scenes_path.exists():
            print(f"[Step5] scenes.json 없음: {scenes_path}")
            return

        try:
            encodings = ['utf-8-sig', 'utf-8', 'cp949']
            scenes = None

            for encoding in encodings:
                try:
                    with open(scenes_path, 'r', encoding=encoding) as f:
                        content = f.read()
                    if content.startswith('\ufeff'):
                        content = content[1:]
                    scenes = json.loads(content)
                    break
                except:
                    continue

            if not scenes:
                print(f"[Step5] scenes.json 로드 실패")
                return

            updated = False
            for scene in scenes:
                sid = scene.get('scene_id', scene.get('id', 0))
                if sid == scene_id:
                    scene['infographic_image_path'] = new_image_path
                    scene['composited_image_path'] = new_image_path
                    scene['image_replaced'] = True
                    scene['replaced_at'] = timestamp
                    scene['replacement_type'] = 'infographic'
                    updated = True
                    break

            if updated:
                with open(scenes_path, 'w', encoding='utf-8') as f:
                    json.dump(scenes, f, ensure_ascii=False, indent=2)
                print(f"[Step5] scenes.json 업데이트 완료 (씬 {scene_id})")

        except Exception as e:
            print(f"[Step5] scenes.json 업데이트 실패: {e}")

    def _invalidate_scene_image_cache(self, scene_id: int):
        """session_state에서 씬 이미지 관련 캐시 무효화"""
        keys_to_clear = []

        for key in list(st.session_state.keys()):
            if any([
                f"scene_{scene_id}" in key,
                f"_{scene_id:03d}" in key,
                f"infographic_{scene_id}" in key,
                "image_cache" in key.lower(),
                "scenes_cache" in key.lower(),
                "loaded_scenes" in key,
                key.startswith("_scene_img_cache_"),  # v2.9: _find_scene_image 캐시도 클리어
            ]):
                keys_to_clear.append(key)

        for key in keys_to_clear:
            try:
                del st.session_state[key]
            except:
                pass

        st.session_state['force_reload_scenes'] = True
        st.session_state['image_cache_invalid'] = True
        st.session_state['storyboard_refresh_timestamp'] = time.time()
        st.session_state['storyboard_needs_refresh'] = True

        # ⭐ v2.5: 미디어 내보내기 캐시 무효화 (image_cache_version 증가)
        current_version = st.session_state.get("image_cache_version", 0)
        st.session_state["image_cache_version"] = current_version + 1
        print(f"[Step5] 이미지 캐시 버전 증가: {current_version + 1}")

        try:
            from . import clear_workflow_manager_cache
            clear_workflow_manager_cache(self.project_path)
            print(f"[Step5 Cache] WorkflowManager 캐시 클리어됨")
        except Exception as e:
            print(f"[Step5 Cache] WorkflowManager 캐시 클리어 실패: {e}")

        print(f"[Step5 Cache] 씬 {scene_id} 캐시 무효화: {len(keys_to_clear)}개 키 삭제")

    def _find_scene_image(
        self,
        scene_id: int,
        composited_dir: Path,
        scene_images_dir: Path,
        backgrounds_dir: Path,
        infographic_dir: Path
    ) -> Optional[Path]:
        """씬 이미지 검색 (v2.9: session_state 캐싱 래퍼)"""
        # session_state 기반 캐시 (파일시스템 반복 검색 방지)
        cache_key = f'_scene_img_cache_{self.project_path}'
        if cache_key not in st.session_state:
            st.session_state[cache_key] = {}

        cache = st.session_state[cache_key]
        version = st.session_state.get('image_cache_version', 0)
        entry = f"{scene_id}_v{version}"

        if entry in cache:
            val = cache[entry]
            if val is None:
                return None
            p = Path(val)
            if p.exists():
                return p
            # 파일이 삭제된 경우 캐시 엔트리 무효화
            del cache[entry]

        # 캐시 미스: 파일시스템 검색
        result = self._find_scene_image_uncached(
            scene_id, composited_dir, scene_images_dir, backgrounds_dir, infographic_dir
        )

        # 결과 캐싱
        cache[entry] = str(result) if result else None
        return result

    def _find_scene_image_uncached(
        self,
        scene_id: int,
        composited_dir: Path,
        scene_images_dir: Path,
        backgrounds_dir: Path,
        infographic_dir: Path
    ) -> Optional[Path]:
        """씬 이미지 검색 - 실제 파일시스템 검색 (인포그래픽 우선)"""
        extensions = ['png', 'jpg', 'jpeg', 'webp']

        # 1. infographic
        if infographic_dir.exists():
            for ext in extensions:
                pattern = str(infographic_dir / f"infographic_{scene_id:03d}_*.{ext}")
                matches = glob_module.glob(pattern)
                if matches:
                    latest_file = max(matches, key=lambda x: Path(x).stat().st_mtime)
                    return Path(latest_file)

        # 2. composited (타임스탬프)
        if composited_dir.exists():
            for ext in extensions:
                pattern = str(composited_dir / f"composited_{scene_id:03d}_*.{ext}")
                matches = glob_module.glob(pattern)
                if matches:
                    latest_file = max(matches, key=lambda x: Path(x).stat().st_mtime)
                    return Path(latest_file)

        # 3. composited (기존)
        for ext in extensions:
            comp_path = composited_dir / f"composited_{scene_id:03d}.{ext}"
            if comp_path.exists():
                return comp_path

        # 4. scenes
        for ext in extensions:
            scene_path = scene_images_dir / f"scene_{scene_id:03d}.{ext}"
            if scene_path.exists():
                return scene_path

        # 5. scenes (역순)
        for ext in extensions:
            alt_path = scene_images_dir / f"{scene_id:03d}_scene.{ext}"
            if alt_path.exists():
                return alt_path

        # 6. backgrounds
        if backgrounds_dir.exists():
            for ext in extensions:
                pattern = str(backgrounds_dir / f"bg_scene_{scene_id:03d}_*.{ext}")
                matches = glob_module.glob(pattern)
                if matches:
                    latest_file = max(matches, key=lambda x: Path(x).stat().st_mtime)
                    return Path(latest_file)

        return None

    def _run_infographic_detection(
        self,
        scenes: List[Dict],
        pool: Set[int],
        model_id: str,
        prompt_id: str = "default"
    ):
        """AI 모델로 인포그래픽 대체 적합 씬 감지"""
        from utils.ai_providers import get_model, AIProvider

        target_scenes = [s for s in scenes if s.get('scene_id', s.get('id', 0)) in pool]

        if not target_scenes:
            st.warning("분석할 대상 씬이 없습니다.")
            return

        prompt_data = self.prompt_manager.get_prompt(prompt_id)
        prompt_name = prompt_data.get('name', prompt_id) if prompt_data else prompt_id

        st.info(f"{len(target_scenes)}개 씬 분석 중... (모델: {model_id}, 프롬프트: {prompt_name})")
        progress_bar = st.progress(0)
        status_text = st.empty()

        scripts_for_analysis = []
        for scene in target_scenes:
            scene_id = scene.get('scene_id', scene.get('id', 0))
            script = scene.get('script_text', scene.get('narration', ''))
            scripts_for_analysis.append({
                "scene_id": scene_id,
                "script": script[:500]
            })

        prompt = self._build_infographic_detection_prompt(scripts_for_analysis, prompt_id)

        try:
            model_info = get_model(model_id)

            if not model_info:
                st.error(f"모델 정보를 찾을 수 없습니다: {model_id}")
                return

            status_text.text(f"AI 분석 중... ({model_info.name})")
            progress_bar.progress(30)

            result = self._call_ai_for_detection(model_id, model_info, prompt)

            progress_bar.progress(80)

            if result:
                detected_scenes = self._parse_detection_result(result)
                progress_bar.progress(100)

                if detected_scenes:
                    st.success(f"분석 완료: {len(detected_scenes)}개 씬이 인포그래픽에 적합")

                    st.session_state['step5_ai_detected_scenes'] = detected_scenes

                    with st.expander("감지 결과 상세", expanded=True):
                        for item in detected_scenes:
                            sid = item.get('scene_id', 0)
                            reason = item.get('reason', '')
                            rec_type = item.get('recommended_type', 'unknown')
                            confidence = item.get('confidence', 0)

                            st.markdown(f"""
                            **씬 {sid}** (신뢰도: {confidence:.0%})
                            - 추천 타입: {rec_type}
                            - 이유: {reason}
                            """)

                    st.markdown("---")
                    col_auto1, col_auto2 = st.columns(2)

                    with col_auto1:
                        if st.button("감지된 씬 자동 선택", key="step5_auto_select"):
                            detected_ids = {item.get('scene_id') for item in detected_scenes}
                            for sid in detected_ids:
                                st.session_state[f"step5_scene_{sid}"] = True
                            st.session_state['step5_filter_detected_only'] = True
                            st.success(f"{len(detected_ids)}개 씬 선택 및 필터 적용됨")
                            st.rerun()

                    with col_auto2:
                        filter_detected = st.checkbox(
                            "감지된 씬만 표시",
                            value=st.session_state.get('step5_filter_detected_only', False),
                            key="step5_filter_toggle"
                        )
                        if filter_detected != st.session_state.get('step5_filter_detected_only', False):
                            st.session_state['step5_filter_detected_only'] = filter_detected
                            st.rerun()
                else:
                    st.info("인포그래픽에 적합한 씬이 감지되지 않았습니다.")
            else:
                st.error("AI 분석 결과를 받지 못했습니다.")

        except Exception as e:
            st.error(f"AI 분석 중 오류 발생: {str(e)}")
            print(f"[Step5 AI 분석] 오류: {e}")

        finally:
            progress_bar.empty()
            status_text.empty()

    def _build_infographic_detection_prompt(self, scenes: List[Dict], prompt_id: str = "default") -> str:
        """인포그래픽 감지용 AI 프롬프트 생성"""
        scenes_text = ""
        for s in scenes:
            scenes_text += f"\n[씬 {s['scene_id']}]\n{s['script']}\n"

        prompt_data = self.prompt_manager.get_prompt(prompt_id)

        if prompt_data and prompt_data.get('content'):
            template_content = prompt_data['content']

            prompt = f"""{template_content}

## 분석할 씬 스크립트
{scenes_text}

JSON만 출력하세요."""
        else:
            print(f"[Step5] 프롬프트 '{prompt_id}' 로드 실패, 기본 프롬프트 사용")
            prompt = f"""당신은 인포그래픽으로 대체 가능한 씬을 분석하는 전문가입니다.

## 분석 기준

인포그래픽 대체가 적합한 경우:
1. 숫자, 통계, 비율 등 데이터가 언급되는 씬
2. 여러 항목을 비교/대조하는 내용
3. 단계별 프로세스나 순서를 설명하는 내용
4. 목록이나 체크리스트 형태의 내용

## 씬 스크립트
{scenes_text}

## 출력 형식 (JSON)

```json
[
  {{
    "scene_id": 씬번호,
    "suitable": true,
    "confidence": 0.85,
    "reason": "분석 이유",
    "recommended_type": "chart"
  }}
]
```

인포그래픽에 적합한 씬만 출력하세요. JSON만 출력하세요."""

        return prompt

    def _call_ai_for_detection(self, model_id: str, model_info, prompt: str) -> Optional[str]:
        """AI API 호출"""
        from utils.ai_providers import AIProvider

        try:
            if model_info.provider == AIProvider.LOCAL:
                st.warning("Claude Code는 이 분석에 지원되지 않습니다. 다른 모델을 선택해주세요.")
                return None

            actual_model_id = model_info.id
            print(f"[Step5 AI] 통합 클라이언트로 호출: {actual_model_id}")

            client = UnifiedAIClient(model_id=actual_model_id)
            result = client.generate(
                prompt=prompt,
                max_tokens=4000,
                temperature=0.2
            )

            print(f"[Step5 AI] 응답 수신: {len(result)} 문자")
            return result

        except ValueError as e:
            st.error(f"설정 오류: {str(e)}")
            print(f"[Step5 AI] 설정 오류: {e}")
            return None
        except Exception as e:
            error_msg = str(e)
            print(f"[Step5 AI] API 호출 오류: {error_msg}")

            if "403" in error_msg and "leaked" in error_msg.lower():
                st.error("API 키가 만료되었거나 보안 문제가 있습니다.")
            elif "401" in error_msg or "unauthorized" in error_msg.lower():
                st.error("API 키 인증에 실패했습니다.")
            elif "quota" in error_msg.lower() or "rate" in error_msg.lower():
                st.error("API 할당량 초과 또는 속도 제한입니다.")
            else:
                st.error(f"API 호출 오류: {error_msg[:200]}")

            raise

    def _parse_detection_result(self, result: str) -> List[Dict]:
        """AI 응답에서 감지 결과 파싱"""
        try:
            json_match = re.search(r'\[[\s\S]*\]', result)
            if json_match:
                data = json.loads(json_match.group())
                if isinstance(data, list):
                    valid_results = []
                    for item in data:
                        if item.get('suitable', True) and 'scene_id' in item:
                            valid_results.append({
                                'scene_id': int(item['scene_id']),
                                'reason': item.get('reason', ''),
                                'recommended_type': item.get('recommended_type', 'unknown'),
                                'confidence': item.get('confidence', 0.5),
                                'extracted_data': item.get('extracted_data', {})
                            })
                    return valid_results

            json_match = re.search(r'\{[\s\S]*\}', result)
            if json_match:
                data = json.loads(json_match.group())
                detected = data.get('detected_scenes', data.get('scenes', []))

                valid_results = []
                for item in detected:
                    if item.get('suitable', True) and 'scene_id' in item:
                        valid_results.append({
                            'scene_id': int(item['scene_id']),
                            'reason': item.get('reason', ''),
                            'recommended_type': item.get('recommended_type', 'unknown'),
                            'confidence': item.get('confidence', 0.5),
                            'extracted_data': item.get('extracted_data', {})
                        })
                return valid_results

            print(f"[Step5 AI] JSON 매칭 실패: {result[:200]}")
            return []

        except json.JSONDecodeError as e:
            print(f"[Step5 AI] JSON 파싱 오류: {e}")
            return []
        except Exception as e:
            print(f"[Step5 AI] 결과 파싱 오류: {e}")
            return []

    # ═══════════════════════════════════════════════════════════════════════════
    # v2.2: 수동 선택 타임라인뷰 및 JSON 생성 기능
    # ═══════════════════════════════════════════════════════════════════════════

    def _get_scene_state(self, scene_id: int) -> tuple:
        """
        씬의 현재 처리 상태를 반환 (v2.7 개선)
        ⭐ 파일 기반 감지 추가 (manager.state가 비어있을 때 fallback)

        Returns:
            (state_code, label, color) 튜플
        """
        # 1단계: manager.state에서 완료 상태 확인
        if scene_id in self.manager.state.completed_step1:
            return ('korean_text', '🔤 한글', '#3B82F6')
        if scene_id in self.manager.state.completed_step2:
            return ('character_composite', '👤 캐릭터', '#8B5CF6')
        if scene_id in self.manager.state.completed_step3:
            return ('real_image', '📷 실사', '#10B981')
        if scene_id in self.manager.state.completed_step4:
            return ('video', '🎬 비디오', '#F97316')
        if scene_id in self.manager.state.completed_step5:
            return ('infographic_done', '✅ 인포그래픽', '#22C55E')

        # 할당됨 (대기 중)
        if scene_id in self.manager.state.step1_scenes:
            return ('step1_assigned', '🔤 한글(대기)', '#93C5FD')
        if scene_id in self.manager.state.step2_scenes:
            return ('step2_assigned', '👤 캐릭터(대기)', '#C4B5FD')
        if scene_id in self.manager.state.step3_scenes:
            return ('step3_assigned', '📷 실사(대기)', '#6EE7B7')
        if scene_id in self.manager.state.step4_scenes:
            return ('step4_assigned', '🎬 비디오(대기)', '#FDBA74')

        # 2단계: ⭐ v2.7 파일 기반 감지 (manager.state가 비어있을 때 fallback)
        file_state = self._detect_scene_state_from_files(scene_id)
        if file_state:
            return file_state

        # 미처리 (인포그래픽 대상 후보)
        return ('unprocessed', '⬜ 미처리', '#EF4444')

    def _detect_scene_state_from_files(self, scene_id: int) -> Optional[tuple]:
        """
        v2.7: 파일 존재 여부로 씬 상태 감지 (fallback)
        성능 최적화를 위해 캐싱된 파일 맵 사용
        """
        # 캐시 키 생성 (프로젝트 경로 기반)
        cache_key = f'step5_file_state_map_{self.project_path}'

        if cache_key not in st.session_state:
            # 파일 맵 빌드
            file_state_map = {}
            import re

            # 우선순위 순서 (나중이 높음): 배경 < 한글 < 캐릭터/합성 < 실사 < 비디오 < 인포그래픽
            dirs_config = [
                ('images/backgrounds', 'background_only', '🖼️ 배경', '#9CA3AF'),
                ('images/korean_text', 'korean_text', '🔤 한글', '#3B82F6'),
                ('images/nano_composite', 'character_composite', '👤 캐릭터', '#8B5CF6'),
                ('images/composited', 'character_composite', '👤 캐릭터', '#8B5CF6'),
                ('images/real_images', 'real_image', '📷 실사', '#10B981'),
                ('videos', 'video', '🎬 비디오', '#F97316'),
                ('images/infographic', 'infographic_done', '✅ 인포', '#22C55E'),
            ]

            for rel_dir, state_code, label, color in dirs_config:
                full_dir = self.project_path / rel_dir
                if full_dir.exists() and full_dir.is_dir():
                    try:
                        for f in full_dir.iterdir():
                            if f.is_file():
                                # 파일명에서 씬 번호 추출: scene_001, scene_1, _001_, _1_
                                match = re.search(r'scene[_-]?(\d+)', f.name, re.IGNORECASE)
                                if match:
                                    sid = int(match.group(1))
                                    file_state_map[sid] = (state_code, label, color)
                    except Exception:
                        pass  # 디렉토리 접근 오류 무시

            st.session_state[cache_key] = file_state_map

        return st.session_state[cache_key].get(scene_id)

    def _render_manual_selection_timeline(self, scenes: List[Dict]) -> Set[int]:
        """
        v2.6: 수동 선택 타임라인뷰 렌더링 - 전체 씬 대상, 상태 배지 표시
        ⭐ 페이지 전환 시에도 선택 유지 (persistent session_state set 사용)
        ⭐ v2.6: 성능 최적화 - 씬 상태 캐싱
        """
        # ⭐ v2.3: 영속적 선택 세트 초기화
        if 'infographic_manual_selected' not in st.session_state:
            st.session_state['infographic_manual_selected'] = set()

        with st.expander("🎬 타임라인뷰 (수동 추가 선택)", expanded=False):
            st.markdown("""
            **전체 씬을 보면서 인포그래픽 대상을 추가로 선택**하세요.
            다른 Step에서 처리된 씬도 덮어쓰기 위해 선택할 수 있습니다.
            """)

            # 전체 씬 ID 수집
            all_scene_ids = sorted([
                s.get('scene_id', s.get('id', 0))
                for s in scenes if s.get('scene_id', s.get('id', 0))
            ])

            if not all_scene_ids:
                st.info("표시할 씬이 없습니다.")
                return set()

            # ⭐ v2.8: 씬 상태 캐싱 - manager.state 해시 포함으로 상태 변경 자동 감지
            # manager.state가 변경되면 캐시 자동 무효화
            state_hash = hash((
                tuple(sorted(self.manager.state.completed_step1)),
                tuple(sorted(self.manager.state.completed_step2)),
                tuple(sorted(self.manager.state.completed_step3)),
                tuple(sorted(self.manager.state.completed_step4)),
                tuple(sorted(self.manager.state.completed_step5)),
                tuple(sorted(self.manager.state.step1_scenes)),
                tuple(sorted(self.manager.state.step2_scenes)),
                tuple(sorted(self.manager.state.step3_scenes)),
                tuple(sorted(self.manager.state.step4_scenes)),
            ))
            cache_key = f'infographic_scene_states_{self.video_name}_{len(scenes)}_{state_hash}'

            # 기존 다른 해시의 캐시 삭제 (메모리 정리)
            old_cache_prefix = f'infographic_scene_states_{self.video_name}_{len(scenes)}_'
            old_keys = [k for k in st.session_state.keys()
                        if k.startswith(old_cache_prefix) and k != cache_key]
            for old_key in old_keys:
                del st.session_state[old_key]

            if cache_key not in st.session_state:
                state_counts = {}
                scene_states = {}
                for sid in all_scene_ids:
                    state, label, color = self._get_scene_state(sid)
                    # ⭐ v2.8: background_only는 unprocessed로 통합 (미처리로 취급)
                    if state == 'background_only':
                        state = 'unprocessed'
                        label = '⬜ 미처리'
                        color = '#EF4444'
                    scene_states[sid] = {'state': state, 'label': label, 'color': color}
                    state_counts[state] = state_counts.get(state, 0) + 1
                st.session_state[cache_key] = {'states': scene_states, 'counts': state_counts}

            cached = st.session_state[cache_key]
            scene_states = cached['states']
            state_counts = cached['counts']

            # 캐시 무효화 버튼 (상태 변경 후 새로고침용)
            if st.button("🔄 상태 새로고침", key="step5_refresh_states", help="씬 상태 캐시를 새로고침합니다"):
                # 씬 상태 캐시 삭제
                if cache_key in st.session_state:
                    del st.session_state[cache_key]
                # v2.7: 파일 기반 상태 맵 캐시도 삭제
                file_cache_key = f'step5_file_state_map_{self.project_path}'
                if file_cache_key in st.session_state:
                    del st.session_state[file_cache_key]
                st.rerun()

            # 상태별 필터 (⭐ v2.4: "미처리 제외" 추가)
            filter_options = ["전체", "미처리 제외", "미처리만", "한글텍스트", "캐릭터합성", "실사이미지", "비디오", "인포그래픽완료"]
            state_map = {
                "미처리만": "unprocessed",
                "한글텍스트": "korean_text",
                "캐릭터합성": "character_composite",
                "실사이미지": "real_image",
                "비디오": "video",
                "인포그래픽완료": "infographic_done"
            }

            filter_col1, filter_col2 = st.columns([2, 2])

            with filter_col1:
                selected_filter = st.radio(
                    "상태 필터",
                    filter_options,
                    horizontal=True,
                    key="step5_manual_timeline_filter",
                    label_visibility="collapsed"
                )

            # 필터 적용 (⭐ v2.4: "미처리 제외" 분기 추가)
            if selected_filter == "전체":
                filtered_ids = all_scene_ids
            elif selected_filter == "미처리 제외":
                # 미처리(unprocessed) 상태가 아닌 씬만 표시 (이미 처리된 씬 중 덮어쓸 대상 선택용)
                filtered_ids = [sid for sid in all_scene_ids
                                if scene_states[sid]['state'] != 'unprocessed']
            else:
                target_state = state_map.get(selected_filter, "")
                # 할당된 상태도 포함
                if target_state == "korean_text":
                    filtered_ids = [sid for sid in all_scene_ids
                                    if scene_states[sid]['state'] in ('korean_text', 'step1_assigned')]
                elif target_state == "character_composite":
                    filtered_ids = [sid for sid in all_scene_ids
                                    if scene_states[sid]['state'] in ('character_composite', 'step2_assigned')]
                elif target_state == "real_image":
                    filtered_ids = [sid for sid in all_scene_ids
                                    if scene_states[sid]['state'] in ('real_image', 'step3_assigned')]
                elif target_state == "video":
                    filtered_ids = [sid for sid in all_scene_ids
                                    if scene_states[sid]['state'] in ('video', 'step4_assigned')]
                else:
                    filtered_ids = [sid for sid in all_scene_ids
                                    if scene_states[sid]['state'] == target_state]

            with filter_col2:
                # ⭐ v2.8: 상태별 개수 표시 - 상호 배타적 카운트 (합계 = 전체)
                # state_counts의 각 키는 상호 배타적 (각 씬은 정확히 1개 상태)
                unproc = state_counts.get('unprocessed', 0)
                korean = state_counts.get('korean_text', 0) + state_counts.get('step1_assigned', 0)
                char = state_counts.get('character_composite', 0) + state_counts.get('step2_assigned', 0)
                real = state_counts.get('real_image', 0) + state_counts.get('step3_assigned', 0)
                video = state_counts.get('video', 0) + state_counts.get('step4_assigned', 0)
                infog = state_counts.get('infographic_done', 0)

                # v2.8: 처리됨 = 미처리 제외 (정확한 합산)
                processed = korean + char + real + video + infog

                st.caption(
                    f"전체: {len(all_scene_ids)} | 처리됨: {processed} | 미처리: {unproc} | "
                    f"한글: {korean} | 캐릭터: {char} | 실사: {real} | 비디오: {video}"
                )

                # v2.8: 합계 검증 (디버그용)
                total_counted = unproc + processed
                if total_counted != len(all_scene_ids):
                    st.warning(f"⚠️ 카운트 불일치: {total_counted} ≠ {len(all_scene_ids)} (누락 상태 확인 필요)")

            st.markdown("---")

            # 선택 컨트롤
            ctrl_col1, ctrl_col2, ctrl_col3, ctrl_col4 = st.columns([1.5, 1, 1, 1])

            # ⭐ v2.3: 영속적 세트에서 현재 선택된 수 계산
            persistent_selected = st.session_state['infographic_manual_selected']
            manual_selected_count = len(persistent_selected)

            with ctrl_col1:
                st.markdown(f"**수동 선택: {manual_selected_count}개** / 전체: {len(all_scene_ids)}개")

            with ctrl_col2:
                if st.button("필터 전체선택", key="step5_manual_select_all_filtered", use_container_width=True):
                    # ⭐ v2.3: 영속적 세트에 추가
                    for sid in filtered_ids:
                        st.session_state['infographic_manual_selected'].add(sid)
                    st.rerun()

            with ctrl_col3:
                if st.button("필터 전체해제", key="step5_manual_deselect_all_filtered", use_container_width=True):
                    # ⭐ v2.3: 영속적 세트에서 제거
                    for sid in filtered_ids:
                        st.session_state['infographic_manual_selected'].discard(sid)
                    st.rerun()

            with ctrl_col4:
                if st.button("전체 초기화", key="step5_manual_clear_all", use_container_width=True):
                    # ⭐ v2.3: 영속적 세트 완전 초기화
                    st.session_state['infographic_manual_selected'] = set()
                    st.rerun()

            st.markdown("---")

            if not filtered_ids:
                st.info(f"'{selected_filter}' 조건에 해당하는 씬이 없습니다.")
                return set()

            # 페이지네이션 (⭐ v2.6: 12개로 줄여 성능 향상)
            items_per_page = 12
            total_pages = max(1, (len(filtered_ids) + items_per_page - 1) // items_per_page)

            page_col1, page_col2, page_col3 = st.columns([1, 2, 1])
            with page_col2:
                current_page = st.number_input(
                    "페이지",
                    min_value=1,
                    max_value=total_pages,
                    value=1,
                    key="step5_manual_timeline_page"
                )

            start_idx = (current_page - 1) * items_per_page
            end_idx = min(start_idx + items_per_page, len(filtered_ids))
            page_ids = filtered_ids[start_idx:end_idx]

            st.caption(f"페이지 {current_page}/{total_pages} (표시: {len(page_ids)}개)")

            # 이미지 경로 디렉토리
            composited_dir = self.project_path / "images" / "composited"
            korean_text_dir = self.project_path / "images" / "korean_text"
            backgrounds_dir = self.project_path / "images" / "backgrounds"
            infographic_dir = self.project_path / "images" / "infographic"
            scene_images_dir = self.project_path / "images" / "scenes"

            # ⭐ v2.3: 체크박스 on_change 콜백 (페이지 전환에도 선택 유지)
            def toggle_manual_scene(scene_id: int):
                """체크박스 변경 시 영속적 세트 업데이트"""
                selected_set = st.session_state['infographic_manual_selected']
                key = f"step5_manual_select_{scene_id}"
                if st.session_state.get(key, False):
                    selected_set.add(scene_id)
                else:
                    selected_set.discard(scene_id)

            # 4열 그리드
            cols_per_row = 4
            for i in range(0, len(page_ids), cols_per_row):
                row_ids = page_ids[i:i + cols_per_row]
                cols = st.columns(cols_per_row)

                for j, sid in enumerate(row_ids):
                    with cols[j]:
                        state_info = scene_states.get(sid, {})
                        label = state_info.get('label', '?')
                        color = state_info.get('color', '#666')

                        # 체크박스 + 상태 배지
                        cb_col, badge_col = st.columns([0.3, 0.7])

                        with cb_col:
                            # ⭐ v2.3: 영속적 세트에서 value 읽고, on_change로 업데이트
                            is_selected = st.checkbox(
                                f"m_sel_{sid}",
                                value=sid in st.session_state['infographic_manual_selected'],
                                key=f"step5_manual_select_{sid}",
                                on_change=toggle_manual_scene,
                                args=(sid,),
                                label_visibility="collapsed"
                            )

                        with badge_col:
                            # 상태 배지
                            st.markdown(
                                f"<span style='background-color:{color};color:white;padding:2px 6px;"
                                f"border-radius:4px;font-size:11px;'>{label}</span>",
                                unsafe_allow_html=True
                            )

                        st.markdown(f"**씬 {sid}**")

                        # 썸네일 이미지
                        img_path = self._find_scene_image(
                            sid, composited_dir, scene_images_dir, backgrounds_dir, infographic_dir
                        )

                        # 한글 텍스트 이미지도 검색
                        if not img_path and korean_text_dir.exists():
                            for ext in ['png', 'jpg', 'jpeg', 'webp']:
                                pattern = str(korean_text_dir / f"korean_text_scene_{sid:03d}_*.{ext}")
                                matches = glob_module.glob(pattern)
                                if matches:
                                    img_path = Path(max(matches, key=lambda x: Path(x).stat().st_mtime))
                                    break

                        if img_path and img_path.exists():
                            st.image(str(img_path), use_container_width=True)
                        else:
                            st.markdown(
                                "<div style='height:80px;background:#2a2a2a;display:flex;"
                                "align-items:center;justify-content:center;border-radius:4px;'>"
                                "<span style='color:#666;font-size:11px;'>이미지 없음</span></div>",
                                unsafe_allow_html=True
                            )

                        # 스크립트 미리보기
                        scene = self.manager.scene_map.get(sid, {})
                        script = scene.get('script_text', scene.get('narration', ''))[:30]
                        if script:
                            st.caption(f"{script}...")

            st.markdown("---")

            # ⭐ v2.3: 영속적 세트에서 직접 반환 (페이지 전환 시에도 유지)
            manual_selected = st.session_state['infographic_manual_selected'].copy()
            st.session_state["step5_manual_selected_scenes"] = manual_selected

            if manual_selected:
                st.success(f"✋ 수동 선택: **{len(manual_selected)}개** 씬 → {sorted(manual_selected)[:10]}{'...' if len(manual_selected) > 10 else ''}")

            return manual_selected

    def _render_final_selection_summary(
        self,
        remaining_selected: Set[int],
        manual_selected: Set[int],
        scenes: List[Dict]
    ) -> Set[int]:
        """
        v2.5: 최종 선택 요약 및 JSON 다운로드 버튼 렌더링
        ⭐ 기존 JSON 형식 복원 (scene_id, start_time, end_time, script_ko, image_prompt_en, visual_elements)
        """
        st.markdown("#### 📊 최종 인포그래픽 대상 요약")

        # 중복 제거 합산
        final_targets = remaining_selected | manual_selected
        overlap_count = len(remaining_selected & manual_selected)

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("남은 씬 선택", f"{len(remaining_selected)}개")
        with col2:
            st.metric("수동 추가", f"{len(manual_selected)}개")
        with col3:
            if overlap_count > 0:
                st.metric("중복 제거", f"-{overlap_count}개")
            else:
                st.metric("중복", "0개")
        with col4:
            st.metric("**최종 합계**", f"**{len(final_targets)}개**")

        if final_targets:
            # 씬 ID 목록 표시
            sorted_ids = sorted(final_targets)
            if len(sorted_ids) <= 15:
                st.caption(f"씬 ID: {sorted_ids}")
            else:
                st.caption(f"씬 ID: {sorted_ids[:8]} ... {sorted_ids[-5:]} ({len(sorted_ids)}개)")

            with st.expander(f"최종 대상 씬 목록 ({len(final_targets)}개)", expanded=False):
                # 상태별 분류
                state_groups = {}
                for sid in sorted(final_targets):
                    state, label, _ = self._get_scene_state(sid)
                    if state not in state_groups:
                        state_groups[state] = []
                    state_groups[state].append(sid)

                for state, sids in state_groups.items():
                    _, label, color = self._get_scene_state(sids[0])
                    st.markdown(
                        f"<span style='background-color:{color};color:white;padding:2px 6px;"
                        f"border-radius:4px;font-size:12px;'>{label}</span> "
                        f"({len(sids)}개): {sids[:15]}{'...' if len(sids) > 15 else ''}",
                        unsafe_allow_html=True
                    )

            st.markdown("---")

            # ═══════════════════════════════════════════════════════════════════
            # ⭐ v2.5: 기존 형식 JSON 다운로드 섹션 복원
            # ═══════════════════════════════════════════════════════════════════
            st.markdown("#### 선택 씬 JSON 다운로드")

            dl_col1, dl_col2, dl_col3 = st.columns([2, 2, 1])

            with dl_col1:
                st.markdown(f"**선택된 씬**: {len(final_targets)}개")
                st.caption(f"(남은 씬 {len(remaining_selected)}개 + 수동 추가 {len(manual_selected)}개)")

            with dl_col2:
                with st.expander("추출 필드 정보", expanded=False):
                    st.markdown("다음 필드만 추출됩니다:")
                    for field in INFOGRAPHIC_EXPORT_FIELDS:
                        st.markdown(f"- `{field}`")
                    st.caption("기존 scenes.json은 변경되지 않습니다.")

            with dl_col3:
                # ⭐ 기존 형식 JSON 생성 (배열, 씬별 상세 필드)
                json_str = create_infographic_export_json(
                    scenes=scenes,
                    selected_scene_ids=final_targets,
                    video_name=self.video_name
                )

                filename = get_infographic_export_filename(
                    video_name=self.video_name,
                    scene_ids=list(final_targets)
                )

                st.download_button(
                    label=f"JSON ({len(final_targets)}개)",
                    data=json_str,
                    file_name=filename,
                    mime="application/json",
                    key="step5_final_json_download",
                    type="primary"
                )

            # ═══════════════════════════════════════════════════════════════════
            # 내부 관리용 메타데이터 저장 (선택적)
            # ═══════════════════════════════════════════════════════════════════
            with st.expander("내부 관리용 메타데이터 저장", expanded=False):
                st.caption("인포그래픽 대상 메타데이터를 프로젝트에 저장합니다. (다운로드 JSON과 별도)")
                if st.button(
                    f"메타데이터 저장 ({len(final_targets)}개 → data/infographic_targets.json)",
                    key="step5_save_targets_meta",
                    use_container_width=True
                ):
                    json_path, json_data = self._save_infographic_targets_json(
                        remaining_selected, manual_selected, scenes
                    )
                    if json_path:
                        st.success(f"✅ 메타데이터 저장 완료: `{json_path}`")
                        st.session_state["step5_targets_json_saved"] = True
                        st.session_state["step5_final_targets"] = final_targets

        else:
            st.info("선택된 씬이 없습니다. 위에서 씬을 선택해주세요.")

        return final_targets

    def _save_infographic_targets_json(
        self,
        remaining_selected: Set[int],
        manual_selected: Set[int],
        scenes: List[Dict]
    ) -> tuple:
        """
        v2.2: 인포그래픽 대상 JSON 저장
        """
        import os
        from datetime import datetime

        # 중복 제거 합산
        final_targets = sorted(set(remaining_selected) | set(manual_selected))

        # JSON 데이터 구조
        data = {
            "version": "1.0",
            "created_at": datetime.now().isoformat(),
            "total_scenes": len(final_targets),
            "sources": {
                "remaining_scenes": sorted(remaining_selected),
                "manual_selection": sorted(manual_selected)
            },
            "final_targets": final_targets,
            "scene_details": []
        }

        # 씬 상세 정보 추가
        scene_map = {s.get('scene_id', s.get('id', 0)): s for s in scenes}
        for sid in final_targets:
            scene = scene_map.get(sid, {})
            source = "remaining" if sid in remaining_selected else "manual"
            if sid in remaining_selected and sid in manual_selected:
                source = "both"

            state, label, _ = self._get_scene_state(sid)

            detail = {
                "scene_id": sid,
                "source": source,
                "previous_state": state,
                "previous_state_label": label,
                "script_ko": scene.get('script_text', scene.get('narration', ''))[:200]
            }
            data["scene_details"].append(detail)

        # 저장 경로
        save_dir = self.project_path / "data"
        save_dir.mkdir(parents=True, exist_ok=True)
        save_path = save_dir / "infographic_targets.json"

        try:
            with open(save_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            print(f"[Step5] ✅ 인포그래픽 대상 JSON 저장됨: {save_path}")
            print(f"[Step5]    총 {len(final_targets)}개 씬 (남은씬: {len(remaining_selected)}, 수동: {len(manual_selected)})")

            return str(save_path), data

        except Exception as e:
            print(f"[Step5] ❌ JSON 저장 실패: {e}")
            st.error(f"JSON 저장 실패: {e}")
            return None, None


def render_step5_ui(manager, scenes: List[Dict], project_path: Path):
    """Step 5 UI 렌더 함수"""
    ui = Step5InfographicUI(manager, project_path)
    return ui.render(scenes)
