# -*- coding: utf-8 -*-
"""
components/storyboard_workflow/step3_realshot.py
Step 3: 실사이미지 대체 UI (v1.9)

처리 단위: 씬 (Scene) + Prefix 규칙
대상: Step 1,2 제외된 씬 중 실사이미지 대체 필요한 씬

v1.9: 배경 이미지/비디오 업로드 기능 추가
      - 배경 소스 선택 (기존 이미지, 업로드 이미지, 업로드 비디오)
      - 비디오 배경 자동 트림/루프 (FFmpeg 기반)
      - 비디오 배경 합성 → MP4 출력
      - 타임라인 뷰 비디오 배지 표시
      - scenes.json media_type/background_video 필드 지원
v1.8: 프롬프트 관리 및 채널 기본값 기능 추가
      - RealImageAnalysisPromptManager 연동
      - ChannelPreferencesManager로 채널별 설정 저장
      - 프롬프트 선택/편집 UI 추가
      - 마지막 사용 모델/프롬프트 자동 로드
v1.7: WorkflowManager 캐시 클리어 추가
      - _invalidate_scene_image_cache()에 clear_workflow_manager_cache 호출 추가
      - 스토리보드 페이지와 완전한 동기화 보장
v1.6: 🔴 긴급 수정 - 3가지 문제 해결
      1. 대체 이미지 미반영 수정:
         - scenes.json에 새 이미지 경로 저장
         - session_state 캐시 무효화
         - 타임스탬프 기반 고유 파일명 사용
      2. 드래그앤드롭 즉시 대체:
         - 파일 업로드 감지 시 자동 대체 (버튼 클릭 불필요)
      3. 타임라인 뷰 씬 유지:
         - 대체 완료된 씬도 목록에 유지
         - 필터 옵션 추가 (전체/대체 필요/대체 완료)
v1.5: AI 필터링 및 타임라인 이미지 표시 수정
      - AI 분석 필터 로직 강화 (타입 일관성 보장)
      - 타임라인 뷰 이미지 경로 확장 (backgrounds, composed 등)
      - 필터 상태 디버그 로깅 추가
v1.4: 종합 개선
      - 감지된 씬 자동선택 → 대상 씬 목록 필터링 연동
      - 타임라인 뷰 추가 (시각적 씬 표시)
      - 개별 씬 이미지 대체 버튼 추가
v1.3: ai_client.py 수정으로 403 API leaked 에러 완전 해결
      - config.settings에서 API 키 로드 (scene_analyzer.py와 동일)
v1.2: UnifiedAIClient로 API 호출 일원화
v1.1: AI 모델 선택 및 실사 감지 분석 기능 추가
"""

import streamlit as st
import json
import re
import os
import glob as glob_module
from typing import Set, Dict, List, Optional
from pathlib import Path
from PIL import Image
import io

from .step_ui_base import StepUIBase
from .progress_visualizer import render_step_status_cards

# AI 모델 선택 유틸리티
from utils.ai_model_selector import render_model_selector, get_selected_model

# 통합 AI 클라이언트 (v1.2: API 호출 일원화)
from utils.ai_client import UnifiedAIClient

# v1.8: 프롬프트 및 채널 설정 관리
from utils.realimage_prompt_manager import RealImageAnalysisPromptManager, ChannelPreferencesManager


class Step3RealshotUI(StepUIBase):
    """Step 3: 실사이미지 대체"""

    def __init__(self, workflow_manager, project_path: Path):
        super().__init__(
            step_number=3,
            workflow_manager=workflow_manager,
            project_path=project_path
        )

        # v1.8: 프롬프트 및 채널 설정 관리자 초기화
        self.prompt_manager = RealImageAnalysisPromptManager(str(project_path))
        self.channel_prefs = ChannelPreferencesManager(str(project_path))

    def get_pool(self) -> Set[int]:
        return self.manager.calculate_step3_pool()

    def get_assigned(self) -> Set[int]:
        return self.manager.state.step3_scenes

    def get_completed(self) -> Set[int]:
        return self.manager.state.completed_step3

    def render_step_content(
        self,
        scenes: List[Dict],
        pool: Set[int],
        assigned: Set[int],
        completed: Set[int]
    ) -> Optional[Dict]:
        """Step 3 콘텐츠 렌더링"""

        # Step 1,2 완료 확인
        step1_pending = len(self.manager.state.step1_scenes - self.manager.state.completed_step1)
        step2_pending = len(self.manager.state.step2_scenes - self.manager.state.completed_step2)

        if step1_pending > 0 or step2_pending > 0:
            st.warning(f"⚠️ 이전 Step 진행 중: Step 1 대기 {step1_pending}개, Step 2 대기 {step2_pending}개")

        # 설명
        st.info("""
            **📷 Step 3: 실사이미지 대체**

            - **대상**: Step 1,2 처리된 씬을 제외한 나머지
            - **처리 단위**: 씬 (Scene) + **Prefix 규칙**
            - **Prefix 규칙**: 묶음 중간 씬 선택 시 앞 씬들도 자동 포함

            예) 묶음 [씬1, 씬2, 씬3]에서 씬3 선택 → 씬1, 씬2도 함께 대체됨
        """)

        st.markdown("---")

        # v1.8: 채널 ID 가져오기 (세션에서)
        channel_id = st.session_state.get('selected_channel_id', 'default')

        # AI 분석 섹션
        with st.expander("🔍 AI 분석 (실제 기업/인물/제품 감지)", expanded=False):
            st.write("AI 분석을 통해 실사이미지 대체가 필요한 씬을 자동 감지합니다.")

            # v1.8: 채널별 저장된 설정 로드
            saved_settings = self.channel_prefs.get_realimage_analysis_settings(channel_id)
            default_model = saved_settings.get('model', 'gemini-2.5-flash')
            default_prompt_id = saved_settings.get('prompt_id', 'default')

            # v1.1: AI 모델 선택 드롭다운
            st.markdown("##### 🤖 AI 모델 선택")
            selected_model = render_model_selector(
                key="step3_realshot_ai",
                task="scene_analysis",
                show_provider_filter=True,
                show_speed_filter=True,
                show_details=True,
                compact=False
            )

            if selected_model:
                st.caption(f"선택된 모델: `{selected_model}`")

            st.markdown("---")

            # v1.8: 프롬프트 선택 UI
            st.markdown("##### 📝 분석 프롬프트 선택")

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
                key="step3_prompt_selector"
            )

            # 프롬프트 미리보기
            if selected_prompt_id:
                prompt_data = self.prompt_manager.get_prompt(selected_prompt_id)
                if prompt_data:
                    with st.expander("📋 프롬프트 미리보기", expanded=False):
                        st.code(prompt_data.get('content', '')[:1000] + "...", language="markdown")

            # 프롬프트 관리 버튼
            col_pm1, col_pm2 = st.columns(2)
            with col_pm1:
                if st.button("📝 프롬프트 편집/추가", key="step3_edit_prompt"):
                    st.session_state['step3_show_prompt_editor'] = True
            with col_pm2:
                if st.button("💾 현재 설정 저장", key="step3_save_settings"):
                    if selected_model and selected_prompt_id:
                        self.channel_prefs.save_realimage_analysis_settings(
                            channel_id=channel_id,
                            model=selected_model,
                            prompt_id=selected_prompt_id
                        )
                        st.success(f"✅ 채널 '{channel_id}' 기본 설정 저장 완료")

            # v1.8: 프롬프트 편집 UI (팝업 스타일)
            if st.session_state.get('step3_show_prompt_editor', False):
                self._render_prompt_editor()

            st.markdown("---")

            # AI 분석 실행 버튼
            if st.button("🔍 AI 분석 실행", key="step3_ai_analysis"):
                if not selected_model:
                    st.error("⚠️ AI 모델을 선택해주세요.")
                elif not pool:
                    st.warning("분석할 대상 씬이 없습니다.")
                else:
                    # v1.8: 선택된 프롬프트로 AI 분석 실행
                    self._run_realshot_detection(scenes, pool, selected_model, selected_prompt_id)

                    # 사용한 설정 자동 저장
                    self.channel_prefs.save_realimage_analysis_settings(
                        channel_id=channel_id,
                        model=selected_model,
                        prompt_id=selected_prompt_id
                    )

        st.markdown("---")

        # 실사이미지 업로드 섹션
        with st.expander("📤 실사이미지 업로드", expanded=True):
            uploaded_files = st.file_uploader(
                "실사 이미지 파일들 (파일명에 씬 번호 포함 권장)",
                type=["png", "jpg", "jpeg", "webp"],
                accept_multiple_files=True,
                key="step3_upload"
            )

            if uploaded_files:
                st.success(f"✅ {len(uploaded_files)}개 파일 업로드됨")

            col1, col2 = st.columns(2)
            with col1:
                realshot_width = st.slider(
                    "실사이미지 너비 (%)",
                    min_value=30,
                    max_value=100,
                    value=60,
                    key="step3_width"
                )
            with col2:
                realshot_height = st.slider(
                    "실사이미지 높이 (%)",
                    min_value=30,
                    max_value=100,
                    value=60,
                    key="step3_height"
                )

            position = st.selectbox(
                "위치",
                ["중앙", "상단 중앙", "하단 중앙"],
                key="step3_position"
            )

            bg_opacity = st.slider(
                "배경 투명도 (%)",
                min_value=0,
                max_value=100,
                value=30,
                key="step3_bg_opacity"
            )

            # v1.9: 배경 소스 선택
            st.markdown("---")
            st.markdown("##### 배경 설정")

            bg_source_option = st.radio(
                "배경 소스 선택",
                ["기존 이미지", "업로드 이미지", "업로드 비디오"],
                horizontal=True,
                key="step3_bg_source",
                help="실사이미지 뒤에 표시될 배경을 선택합니다"
            )

            bg_uploaded_image = None
            bg_uploaded_video = None
            bg_video_info = None
            bg_video_loop = False

            if bg_source_option == "업로드 이미지":
                bg_uploaded_image = st.file_uploader(
                    "배경 이미지 업로드",
                    type=["png", "jpg", "jpeg", "webp"],
                    key="step3_bg_image_upload",
                    help="모든 선택된 씬에 동일한 배경 이미지가 적용됩니다"
                )
                if bg_uploaded_image:
                    st.success(f"배경 이미지: {bg_uploaded_image.name}")
                    st.image(bg_uploaded_image, caption="배경 이미지 미리보기", use_container_width=True)

            elif bg_source_option == "업로드 비디오":
                bg_uploaded_video = st.file_uploader(
                    "배경 비디오 업로드",
                    type=["mp4", "mov", "avi", "mkv", "webm"],
                    key="step3_bg_video_upload",
                    help="씬 길이를 초과하는 비디오는 자동으로 트림됩니다"
                )
                if bg_uploaded_video:
                    from utils.timeline_composite import get_video_info_from_file, extract_video_thumbnail
                    bg_video_info = get_video_info_from_file(bg_uploaded_video)

                    if bg_video_info:
                        st.success(f"배경 비디오: {bg_uploaded_video.name}")
                        vi_col1, vi_col2, vi_col3 = st.columns(3)
                        with vi_col1:
                            st.metric("길이", f"{bg_video_info.get('duration', 0):.1f}초")
                        with vi_col2:
                            st.metric("해상도", f"{bg_video_info.get('width', 0)}x{bg_video_info.get('height', 0)}")
                        with vi_col3:
                            st.metric("FPS", f"{bg_video_info.get('fps', 0):.0f}")

                        # v1.10: 비디오 첫 프레임 미리보기 (크기 제한)
                        bg_uploaded_video.seek(0)
                        thumb_path = extract_video_thumbnail(bg_uploaded_video, 0, str(self.project_path))
                        bg_uploaded_video.seek(0)
                        if thumb_path and os.path.exists(thumb_path):
                            st.image(thumb_path, caption="🎬 배경 비디오 미리보기 (첫 프레임)", width=400)

                        # 임시 파일 정리
                        temp_path = bg_video_info.get('temp_path')
                        if temp_path and os.path.exists(temp_path):
                            try:
                                os.unlink(temp_path)
                            except OSError:
                                pass

                    bg_video_loop = st.checkbox(
                        "비디오 루프 (씬보다 짧은 경우 반복)",
                        value=False,
                        key="step3_bg_video_loop"
                    )

                    st.info("비디오 배경 사용 시 출력이 MP4 비디오가 됩니다. "
                            "씬 duration보다 긴 비디오는 자동으로 트림됩니다.")
                    st.info("💡 비디오 배경 모드: 타임라인 드래그앤드롭한 이미지가 비디오 위에 오버레이됩니다.")

        st.markdown("---")

        # 대상 씬 목록
        st.markdown("#### 📋 대상 씬 목록 (씬 단위 선택)")

        if not pool:
            st.success("✅ 실사이미지 대체 대상 씬이 없거나 모두 처리되었습니다.")
            return None

        # v1.5: 감지된 씬 필터 적용 (타입 일관성 보장)
        display_pool = pool
        filter_active = st.session_state.get('step3_filter_detected_only', False)

        if filter_active:
            detected_scenes = st.session_state.get('step3_ai_detected_scenes', [])
            print(f"[Step3 Filter] 필터 활성화됨, 감지된 씬 수: {len(detected_scenes) if detected_scenes else 0}")

            if detected_scenes:
                # v1.5: 타입 일관성 보장 - 모두 int로 변환
                detected_ids = set()
                for item in detected_scenes:
                    sid = item.get('scene_id')
                    if sid is not None:
                        try:
                            detected_ids.add(int(sid))
                        except (ValueError, TypeError):
                            print(f"[Step3 Filter] 잘못된 scene_id 무시: {sid}")

                # pool도 int로 변환 보장
                pool_int = {int(x) for x in pool}

                # 교집합 계산
                display_pool = pool_int & detected_ids

                print(f"[Step3 Filter] pool={len(pool_int)}, detected={len(detected_ids)}, intersection={len(display_pool)}")
                print(f"[Step3 Filter] detected_ids 샘플: {list(detected_ids)[:5]}")
                print(f"[Step3 Filter] pool_int 샘플: {sorted(list(pool_int))[:5]}")

                if display_pool:
                    st.info(f"🔍 **필터 적용 중**: 감지된 {len(display_pool)}개 씬만 표시 (전체 대상: {len(pool)}개)")
                else:
                    # 교집합이 비어있으면 경고 표시
                    st.warning(f"⚠️ 감지된 씬 {len(detected_ids)}개가 현재 대상 풀 {len(pool)}개와 겹치지 않습니다.")
                    display_pool = pool  # 필터 무효화

                # 필터 해제 버튼
                if st.button("❌ 필터 해제", key="step3_clear_filter"):
                    st.session_state['step3_filter_detected_only'] = False
                    print("[Step3 Filter] 필터 해제됨")
                    st.rerun()
            else:
                st.warning("⚠️ AI 분석을 먼저 실행해주세요. 필터가 해제됩니다.")
                st.session_state['step3_filter_detected_only'] = False
                print("[Step3 Filter] 감지된 씬 없음, 필터 비활성화")

        # 씬 선택
        selected = self._render_scene_selection(display_pool, scenes)

        # Prefix 규칙 적용 미리보기
        if selected:
            self._render_prefix_preview(selected)

        # v1.4: 타임라인 뷰 및 개별 대체 기능
        st.markdown("---")
        self._render_timeline_view(display_pool, scenes, uploaded_files if uploaded_files else [])

        # 실행 버튼
        def on_assign(ids):
            expanded = self.manager.expand_with_prefix_scenes(ids)
            self.manager.assign_to_step(3, expanded, apply_expansion=False)
            self.manager.save()

        def on_execute(ids):
            expanded = self.manager.expand_with_prefix_scenes(ids)

            # v1.9: 배경 소스 매핑
            bg_source_map = {
                "기존 이미지": "existing",
                "업로드 이미지": "upload",
                "업로드 비디오": "video"
            }
            bg_source = bg_source_map.get(bg_source_option, "existing")

            settings = {
                "width_pct": realshot_width,
                "height_pct": realshot_height,
                "position": position,
                "bg_opacity": bg_opacity / 100,
                "uploaded_files": len(uploaded_files) if uploaded_files else 0,
                "bg_source": bg_source,
            }

            # v1.9: 비디오 배경인 경우 일괄 처리 실행
            if bg_source == "video" and bg_uploaded_video:
                return self._execute_batch_video_bg_replacement(
                    scene_ids=sorted(expanded),
                    scenes=scenes,
                    uploaded_files=uploaded_files if uploaded_files else [],
                    bg_video_file=bg_uploaded_video,
                    bg_video_loop=bg_video_loop,
                    settings=settings
                )

            # v1.9: 업로드 이미지 배경인 경우 설정에 포함
            if bg_source == "upload" and bg_uploaded_image:
                settings["bg_image_file"] = bg_uploaded_image

            return {
                "action": "realshot_replace",
                "step": 3,
                "scene_ids": sorted(expanded),
                "settings": settings
            }

        return self.render_execution_buttons(
            selected,
            on_assign=on_assign,
            on_execute=on_execute,
            execute_label="실사이미지 적용"
        )

    def _render_scene_selection(self, pool: Set[int], scenes: List[Dict]) -> Set[int]:
        """씬 선택 UI

        v1.1: WorkflowManager의 scene_map 사용 (bundle_id 일관성 보장)
        """
        selected = set()
        # v1.1: self.manager.scene_map 사용 (scenes.json의 정확한 bundle_id 참조)
        scene_map = self.manager.scene_map

        # 전체 선택
        col1, col2 = st.columns([1, 3])
        with col1:
            select_all = st.checkbox("전체 선택", key="step3_select_all")
        with col2:
            st.caption(f"대상 씬: {len(pool)}개")

        # 페이지네이션
        sorted_pool = sorted(pool)
        items_per_page = 20
        total_pages = max(1, (len(sorted_pool) + items_per_page - 1) // items_per_page)

        if total_pages > 1:
            page = st.number_input(
                "페이지",
                min_value=1,
                max_value=total_pages,
                value=1,
                key="step3_page"
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
            bundle_scenes = self.manager.bundle_map.get(bundle_id, [sid])

            script = scene.get('script_text', scene.get('narration', ''))[:60]

            # 묶음 내 위치 표시
            try:
                pos_in_bundle = bundle_scenes.index(sid) + 1
                bundle_pos = f"{pos_in_bundle}/{len(bundle_scenes)}"
            except ValueError:
                bundle_pos = "?"

            with st.container():
                cols = st.columns([0.4, 1, 1, 3])

                with cols[0]:
                    is_selected = st.checkbox(
                        f"씬 {sid} 선택",
                        value=select_all,
                        key=f"step3_scene_{sid}",
                        label_visibility="collapsed"
                    )
                    if is_selected:
                        selected.add(sid)

                with cols[1]:
                    st.markdown(f"**씬 {sid}**")

                with cols[2]:
                    st.markdown(f"<small>묶음{bundle_id} ({bundle_pos})</small>", unsafe_allow_html=True)

                with cols[3]:
                    st.markdown(f"<small>{script}...</small>", unsafe_allow_html=True)

        if select_all:
            return pool.copy()

        return selected

    def _render_prompt_editor(self):
        """v1.8: 프롬프트 편집/추가 UI"""
        st.markdown("---")
        st.markdown("#### 📝 프롬프트 관리")

        # 탭으로 편집/추가 구분
        tab_edit, tab_add = st.tabs(["✏️ 기존 편집", "➕ 새로 추가"])

        with tab_edit:
            # 편집할 프롬프트 선택
            available = self.prompt_manager.list_prompts()
            editable = [p for p in available if not p.get('is_system', False)]

            if not editable:
                st.info("편집 가능한 사용자 정의 프롬프트가 없습니다. '새로 추가' 탭에서 프롬프트를 만들어보세요.")
                st.caption("💡 시스템 기본 프롬프트(기본 분석, 엄격 분석, 관대 분석)는 편집할 수 없습니다.")
            else:
                edit_prompt_id = st.selectbox(
                    "편집할 프롬프트",
                    options=[p['id'] for p in editable],
                    format_func=lambda x: next((p['name'] for p in editable if p['id'] == x), x),
                    key="step3_edit_prompt_select"
                )

                if edit_prompt_id:
                    prompt_data = self.prompt_manager.get_prompt(edit_prompt_id)
                    if prompt_data:
                        edit_name = st.text_input(
                            "이름",
                            value=prompt_data.get('name', ''),
                            key="step3_edit_name"
                        )
                        edit_desc = st.text_input(
                            "설명",
                            value=prompt_data.get('description', ''),
                            key="step3_edit_desc"
                        )
                        edit_content = st.text_area(
                            "프롬프트 내용",
                            value=prompt_data.get('content', ''),
                            height=300,
                            key="step3_edit_content"
                        )

                        col_save, col_delete, col_cancel = st.columns(3)
                        with col_save:
                            if st.button("💾 저장", key="step3_save_edit"):
                                self.prompt_manager.save_prompt(
                                    prompt_id=edit_prompt_id,
                                    name=edit_name,
                                    description=edit_desc,
                                    content=edit_content,
                                    is_system=False
                                )
                                st.success("✅ 프롬프트 저장 완료")
                                st.session_state['step3_show_prompt_editor'] = False
                                st.rerun()
                        with col_delete:
                            if st.button("🗑️ 삭제", key="step3_delete_prompt"):
                                if self.prompt_manager.delete_prompt(edit_prompt_id):
                                    st.success("✅ 프롬프트 삭제 완료")
                                    st.session_state['step3_show_prompt_editor'] = False
                                    st.rerun()
                                else:
                                    st.error("❌ 삭제 실패")
                        with col_cancel:
                            if st.button("❌ 취소", key="step3_cancel_edit"):
                                st.session_state['step3_show_prompt_editor'] = False
                                st.rerun()

        with tab_add:
            new_id = st.text_input(
                "프롬프트 ID (영문, 숫자, 밑줄만)",
                placeholder="my_custom_prompt",
                key="step3_new_id"
            )
            new_name = st.text_input(
                "표시 이름",
                placeholder="내 커스텀 분석",
                key="step3_new_name"
            )
            new_desc = st.text_input(
                "설명",
                placeholder="이 프롬프트의 용도 설명",
                key="step3_new_desc"
            )

            # 기본 템플릿에서 시작
            default_template = self.prompt_manager.get_prompt('default')
            template_content = default_template.get('content', '') if default_template else ''

            new_content = st.text_area(
                "프롬프트 내용",
                value=template_content,
                height=300,
                key="step3_new_content",
                help="기본 프롬프트를 템플릿으로 시작합니다. 필요에 맞게 수정하세요."
            )

            col_add, col_cancel_add = st.columns(2)
            with col_add:
                if st.button("➕ 추가", key="step3_add_new"):
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
                        st.success(f"✅ 프롬프트 '{new_name}' 추가 완료")
                        st.session_state['step3_show_prompt_editor'] = False
                        st.rerun()
            with col_cancel_add:
                if st.button("❌ 취소", key="step3_cancel_add"):
                    st.session_state['step3_show_prompt_editor'] = False
                    st.rerun()

        st.markdown("---")

    def _render_prefix_preview(self, selected: Set[int]):
        """Prefix 규칙 적용 미리보기"""
        expanded = self.manager.expand_with_prefix_scenes(selected)
        prefix_added = expanded - selected

        if prefix_added:
            st.warning(f"""
                ⚠️ **Prefix 규칙 적용됨**

                - 직접 선택: {len(selected)}개 씬
                - Prefix 추가: {len(prefix_added)}개 씬
                - **총 영향 씬: {len(expanded)}개**
            """)

            with st.expander(f"📋 Prefix 포함 씬 상세 ({len(prefix_added)}개)", expanded=False):
                for sid in sorted(prefix_added):
                    scene = self.manager.scene_map.get(sid, {})
                    script = scene.get('script_text', '')[:50]
                    st.markdown(f"- **씬 {sid}** (Prefix 포함): {script}...")

    def _render_timeline_view(
        self,
        pool: Set[int],
        scenes: List[Dict],
        uploaded_files: List
    ):
        """
        v1.6: 타임라인 뷰 렌더링 - 드래그앤드롭 즉시 대체 + 대체된 씬 유지

        변경사항 (v1.6):
        - 드래그앤드롭 시 즉시 대체 (버튼 클릭 불필요)
        - 대체 완료된 씬도 타임라인에 유지
        - 필터 옵션 추가 (전체/대체 필요/대체 완료)
        """
        with st.expander("🎬 타임라인 뷰 (개별 씬 이미지 대체)", expanded=False):
            # v1.6: 대체 완료된 씬도 포함하여 표시
            completed_step3 = self.manager.state.completed_step3
            all_scenes_for_timeline = pool | completed_step3

            if not all_scenes_for_timeline:
                st.info("표시할 씬이 없습니다.")
                return

            st.markdown("""
            **사용법**: 이미지를 드래그앤드롭하면 **즉시 대체**됩니다. (버튼 클릭 불필요)
            """)

            # v1.6: 필터 옵션
            filter_col1, filter_col2, filter_col3 = st.columns(3)
            with filter_col1:
                filter_mode = st.radio(
                    "필터",
                    ["전체", "대체 필요", "대체 완료"],
                    horizontal=True,
                    key="step3_timeline_filter"
                )

            # 필터 적용
            if filter_mode == "전체":
                display_pool = all_scenes_for_timeline
            elif filter_mode == "대체 필요":
                display_pool = pool - completed_step3
            else:  # 대체 완료
                display_pool = completed_step3

            with filter_col2:
                st.caption(f"대기: {len(pool - completed_step3)}개")
            with filter_col3:
                st.caption(f"완료: {len(completed_step3)}개")

            if not display_pool:
                st.info(f"'{filter_mode}' 조건에 해당하는 씬이 없습니다.")
                return

            # 업로드된 파일 매핑 (파일명에서 씬 번호 추출)
            uploaded_map = {}
            for f in uploaded_files:
                # 파일명에서 숫자 추출 시도
                match = re.search(r'(\d+)', f.name)
                if match:
                    file_scene_id = int(match.group(1))
                    uploaded_map[file_scene_id] = f

            # 씬별 현재 이미지 경로 가져오기
            composited_dir = self.project_path / "images" / "composited"
            scene_images_dir = self.project_path / "images" / "scenes"
            backgrounds_dir = self.project_path / "images" / "backgrounds"

            sorted_pool = sorted(display_pool)

            # 4열 그리드로 표시
            cols_per_row = 4
            for i in range(0, len(sorted_pool), cols_per_row):
                row_scenes = sorted_pool[i:i + cols_per_row]
                cols = st.columns(cols_per_row)

                for j, sid in enumerate(row_scenes):
                    with cols[j]:
                        scene = self.manager.scene_map.get(sid, {})
                        script = scene.get('script_text', scene.get('narration', ''))[:40]

                        # v1.6: 대체 완료 여부 표시
                        is_replaced = sid in completed_step3
                        # v1.9: 비디오 배경 여부
                        is_video_bg = scene.get('media_type') == 'video'

                        # 씬 카드 헤더 (대체 완료 표시)
                        if is_replaced and is_video_bg:
                            st.markdown(f"**씬 {sid}** ✅🎬")
                        elif is_replaced:
                            st.markdown(f"**씬 {sid}** ✅")
                        else:
                            st.markdown(f"**씬 {sid}**")

                        # v1.5: 확장된 이미지 경로 검색
                        current_image = self._find_scene_image(sid, composited_dir, scene_images_dir, backgrounds_dir)

                        if current_image and current_image.exists():
                            st.image(str(current_image), use_container_width=True)
                            if is_replaced and is_video_bg:
                                st.caption("✅ 실사 대체됨 (비디오)")
                            elif is_replaced:
                                st.caption("✅ 실사 대체됨")
                        else:
                            st.markdown(
                                "<div style='height:100px;background:#333;display:flex;"
                                "align-items:center;justify-content:center;border-radius:4px;'>"
                                "<span style='color:#999;'>이미지 없음</span></div>",
                                unsafe_allow_html=True
                            )

                        st.caption(f"{script}...")

                        # AI 감지 여부 표시
                        detected_scenes = st.session_state.get('step3_ai_detected_scenes', [])
                        is_detected = any(item.get('scene_id') == sid for item in detected_scenes)
                        if is_detected and not is_replaced:
                            st.markdown("🔴 **실사 대체 필요**")

                        # v1.10: 비디오 배경 모드에서도 드래그앤드롭 허용
                        uploader_key = f"step3_dnd_upload_{sid}"
                        processed_hash_key = f"step3_processed_hash_{sid}"

                        # 파일 업로더 (배경 타입 무관하게 항상 표시)
                        individual_file = st.file_uploader(
                            f"씬 {sid} - 드래그앤드롭",
                            type=["png", "jpg", "jpeg", "webp"],
                            key=uploader_key,
                            label_visibility="collapsed",
                            help="이미지를 드래그앤드롭하면 즉시 대체됩니다"
                        )

                        # v1.8: 파일 업로드 감지 시 즉시 대체 (무한 루프 방지)
                        if individual_file is not None:
                            import hashlib

                            # 파일 해시로 중복 체크 (더 안전함)
                            file_content = individual_file.getvalue()
                            file_hash = hashlib.md5(file_content).hexdigest()[:16]
                            previous_hash = st.session_state.get(processed_hash_key, "")

                            if file_hash != previous_hash:
                                # 새 파일 업로드됨 - 즉시 대체 실행
                                print(f"[Step3] 🔄 씬 {sid}: 새 파일 감지 (hash={file_hash[:8]})")

                                # 파일 포인터 리셋 (getvalue() 후 다시 읽기 위해)
                                individual_file.seek(0)

                                with st.spinner(f"씬 {sid} 이미지 대체 중..."):
                                    result = self._replace_single_scene_image(
                                        sid, individual_file, scene
                                    )
                                    if result:
                                        # v1.10: 해시 저장 후 rerun으로 UI 즉시 갱신
                                        # 해시 체크가 중복 실행을 방지하므로 무한 루프 없음
                                        st.session_state[processed_hash_key] = file_hash
                                        st.success(f"✅ 씬 {sid} 대체 완료!")
                                        st.rerun()
                                    else:
                                        st.error(f"❌ 씬 {sid} 대체 실패")
                            else:
                                # 이미 처리된 파일 - 스킵
                                print(f"[Step3] ⏭️ 씬 {sid}: 이미 처리된 파일, 스킵")

                        # 대체 완료된 씬은 다시 대체 가능하도록 버튼 유지
                        if is_replaced:
                            if st.button("🔄 다시 대체", key=f"step3_re_replace_{sid}", use_container_width=True):
                                file_to_use = individual_file or uploaded_map.get(sid)
                                if file_to_use:
                                    result = self._replace_single_scene_image(sid, file_to_use, scene)
                                    if result:
                                        st.success(f"✅ 씬 {sid} 다시 대체 완료!")
                                        st.rerun()
                                else:
                                    st.warning("이미지를 먼저 드래그앤드롭하세요")

            st.markdown("---")
            st.caption(f"표시 중: {len(display_pool)}개 / 전체: {len(all_scenes_for_timeline)}개")

    def _replace_single_scene_image(
        self,
        scene_id: int,
        uploaded_file,
        scene: Dict
    ) -> bool:
        """
        v1.10: 개별 씬 이미지 대체 - create_composite_realshot()으로 합성

        변경사항 (v1.10):
        - create_composite_realshot() 사용으로 크기/위치/배경 설정 적용
        - UI에서 설정한 너비%, 높이%, 위치, 배경투명도가 반영됨

        Args:
            scene_id: 씬 ID
            uploaded_file: 업로드된 파일 객체
            scene: 씬 정보

        Returns:
            성공 여부
        """
        import time

        try:
            from utils.timeline_composite import create_composite_realshot

            timestamp = int(time.time() * 1000)

            # UI 설정값 읽기
            width_pct = st.session_state.get('step3_width', 60)
            height_pct = st.session_state.get('step3_height', 60)
            position_kr = st.session_state.get('step3_position', '중앙')
            bg_opacity = st.session_state.get('step3_bg_opacity', 30)

            # 위치 매핑 (한국어 → 영어)
            position_map = {"중앙": "center", "상단 중앙": "top", "하단 중앙": "bottom"}
            eng_position = position_map.get(position_kr, 'center')

            # 배경 소스 결정
            bg_source_kr = st.session_state.get('step3_bg_source', '기존 이미지')
            bg_source_map = {"기존 이미지": "existing", "업로드 이미지": "upload", "업로드 비디오": "video"}
            bg_source = bg_source_map.get(bg_source_kr, 'existing')

            # 합성 설정
            composite_settings = {
                'realshot_width_pct': width_pct,
                'realshot_height_pct': height_pct,
                'position': eng_position,
                'bg_source': bg_source,
                'bg_settings': {
                    'opacity': bg_opacity / 100,
                },
                'output_width': 1920,
                'output_height': 1080,
            }

            # 업로드된 배경 이미지가 있으면 설정에 추가
            if bg_source == 'upload':
                bg_image_file = st.session_state.get('step3_bg_image_upload')
                if bg_image_file:
                    composite_settings['bg_settings']['file'] = bg_image_file

            # v1.10: 비디오 배경 → MP4 합성 (첫 프레임 PNG 폴백 아닌 실제 비디오 합성)
            if bg_source == 'video':
                bg_video_file = st.session_state.get('step3_bg_video_upload')
                if bg_video_file:
                    from utils.timeline_composite import (
                        composite_realshot_on_video,
                        prepare_background_video,
                        extract_video_thumbnail
                    )
                    import time as _time

                    # 비디오를 임시 저장
                    bg_video_dir = self.project_path / "videos" / "backgrounds"
                    bg_video_dir.mkdir(parents=True, exist_ok=True)

                    bg_video_file.seek(0)
                    bg_ext = Path(bg_video_file.name).suffix.lower() if hasattr(bg_video_file, 'name') else '.mp4'
                    bg_saved = bg_video_dir / f"bg_single_{scene_id:03d}_{timestamp}{bg_ext}"
                    with open(bg_saved, 'wb') as _f:
                        _f.write(bg_video_file.getbuffer())
                    bg_video_file.seek(0)

                    # 씬 duration 가져오기
                    scene_duration = scene.get('duration', scene.get('duration_estimate', 5.0))
                    if not isinstance(scene_duration, (int, float)) or scene_duration <= 0:
                        scene_duration = 5.0

                    bg_video_loop = st.session_state.get('step3_bg_video_loop', True)

                    # 비디오 트림/루프
                    prepared_path = str(bg_video_dir / f"bg_prepared_{scene_id:03d}_{timestamp}.mp4")
                    prep_result = prepare_background_video(
                        video_path=str(bg_saved),
                        target_duration=float(scene_duration),
                        output_path=prepared_path,
                        loop=bg_video_loop
                    )

                    if prep_result:
                        # FFmpeg로 비디오 합성
                        video_output = composite_realshot_on_video(
                            realshot_source=uploaded_file,
                            bg_video_path=prepared_path,
                            scene_num=scene_id,
                            project_path=str(self.project_path),
                            settings=composite_settings
                        )

                        if video_output:
                            # 썸네일 추출 (타임라인 뷰용)
                            thumb_path = extract_video_thumbnail(video_output, scene_id, str(self.project_path))

                            # scenes.json 업데이트 (비디오 전용)
                            self._update_scenes_json_video_bg(scene_id, video_output, thumb_path, timestamp)

                            # 캐시 무효화 + 완료
                            self._invalidate_scene_image_cache(scene_id)
                            self.manager.mark_completed(3, {scene_id})
                            self.manager.save()

                            # 준비된 비디오 정리
                            if os.path.exists(prepared_path):
                                try:
                                    os.unlink(prepared_path)
                                except OSError:
                                    pass

                            print(f"[Step3] 씬 {scene_id} 비디오 합성 완료: {video_output}")
                            return True
                        else:
                            print(f"[Step3] 씬 {scene_id} 비디오 합성 실패, 이미지 폴백")
                    else:
                        print(f"[Step3] 씬 {scene_id} 비디오 준비 실패, 이미지 폴백")

                    # 준비된 비디오 정리
                    if os.path.exists(prepared_path):
                        try:
                            os.unlink(prepared_path)
                        except OSError:
                            pass

                    # 폴백: 비디오 합성 실패 시 첫 프레임으로 이미지 합성
                    frame_path = extract_video_thumbnail(str(bg_saved), scene_id, str(self.project_path))
                    if frame_path and os.path.exists(frame_path):
                        composite_settings['bg_source'] = 'upload'
                        composite_settings['bg_settings']['file'] = frame_path
                        print(f"[Step3] 비디오 합성 실패 → 첫 프레임 폴백: {frame_path}")
                    else:
                        composite_settings['bg_source'] = 'existing'
                        print(f"[Step3] 프레임 추출도 실패, 기존 이미지로 폴백")
                else:
                    composite_settings['bg_source'] = 'existing'
                    print(f"[Step3] 비디오 파일 없음, 기존 이미지로 폴백")

            print(f"[Step3] 합성 설정: 크기={width_pct}%x{height_pct}%, 위치={eng_position}, "
                  f"배경={bg_source}, 투명도={bg_opacity}%")

            # create_composite_realshot()으로 배경 위에 합성 (이미지 배경 또는 비디오 폴백)
            output_path = create_composite_realshot(
                realshot_source=uploaded_file,
                scene_num=scene_id,
                project_path=str(self.project_path),
                settings=composite_settings
            )

            if not output_path:
                print(f"[Step3] 씬 {scene_id} 합성 실패")
                return False

            # 합성 결과를 composited 폴더에도 복사 (타임라인 뷰 검색용)
            composited_dir = self.project_path / "images" / "composited"
            composited_dir.mkdir(parents=True, exist_ok=True)

            import shutil
            composited_filename = f"composited_{scene_id:03d}_{timestamp}.png"
            composited_path = composited_dir / composited_filename
            shutil.copy2(output_path, str(composited_path))

            print(f"[Step3] 씬 {scene_id} 합성 이미지 저장: {composited_filename}")

            # scenes.json 업데이트
            self._update_scenes_json_image_path(scene_id, str(composited_path), timestamp)

            # session_state 캐시 무효화
            self._invalidate_scene_image_cache(scene_id)

            # 완료 상태 업데이트 (풀에서 제거하지 않음)
            self.manager.mark_completed(3, {scene_id})
            self.manager.save()

            print(f"[Step3] 씬 {scene_id} 대체 완료 (크기={width_pct}%x{height_pct}%, 위치={eng_position})")

            return True

        except Exception as e:
            print(f"[Step3] ❌ 씬 {scene_id} 이미지 대체 실패: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _update_scenes_json_image_path(self, scene_id: int, new_image_path: str, timestamp: int):
        """
        v1.6: scenes.json에 새 이미지 경로 업데이트
        """
        import json

        scenes_path = self.project_path / "analysis" / "scenes.json"

        if not scenes_path.exists():
            print(f"[Step3] ⚠️ scenes.json 없음: {scenes_path}")
            return

        try:
            # BOM 안전 로드
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
                print(f"[Step3] ⚠️ scenes.json 로드 실패")
                return

            # 해당 씬 찾아서 업데이트
            updated = False
            for scene in scenes:
                sid = scene.get('scene_id', scene.get('id', 0))
                if sid == scene_id:
                    # 이미지 경로 업데이트
                    scene['composited_image_path'] = new_image_path
                    scene['real_image_path'] = new_image_path  # 실사 대체이므로
                    scene['image_replaced'] = True
                    scene['replaced_at'] = timestamp
                    scene['replacement_type'] = 'realshot'
                    updated = True
                    break

            if updated:
                with open(scenes_path, 'w', encoding='utf-8') as f:
                    json.dump(scenes, f, ensure_ascii=False, indent=2)
                print(f"[Step3] ✅ scenes.json 업데이트 완료 (씬 {scene_id})")
            else:
                print(f"[Step3] ⚠️ scenes.json에서 씬 {scene_id}를 찾을 수 없음")

        except Exception as e:
            print(f"[Step3] ⚠️ scenes.json 업데이트 실패: {e}")

    def _invalidate_scene_image_cache(self, scene_id: int):
        """
        v1.12: 씬별 캐시 무효화 (선택적 - 전체 클리어 제거)

        st.cache_data.clear() 제거: get_scenes_data_cached()는 mtime 기반으로
        자연 무효화되므로 전체 캐시 클리어 불필요.
        scenes.json 수정 → mtime 변경 → 캐시 자동 갱신.
        """
        # 1. session_state 씬별 캐시 키 삭제 (해당 씬만)
        keys_to_clear = []
        for key in list(st.session_state.keys()):
            if any([
                f"scene_{scene_id}" in key,
                f"_{scene_id:03d}" in key,
                f"composited_{scene_id}" in key,
            ]):
                keys_to_clear.append(key)

        for key in keys_to_clear:
            try:
                del st.session_state[key]
            except:
                pass

        # 2. image_cache_version 증가 (load_image_files_cached 갱신)
        current_version = st.session_state.get("image_cache_version", 0)
        st.session_state["image_cache_version"] = current_version + 1

        # 3. 캐릭터 자동 연동 캐시 무효화
        auto_link_keys = [k for k in st.session_state.keys() if k.startswith("_char_auto_linked_")]
        for key in auto_link_keys:
            try:
                del st.session_state[key]
            except:
                pass

        print(f"[Step3 Cache] 씬 {scene_id} 캐시 무효화 (선택적): "
              f"{len(keys_to_clear)}개 키 삭제, cache_version={current_version + 1}")

    # ========================================
    # v1.9: 비디오 배경 처리
    # ========================================

    def _execute_batch_video_bg_replacement(
        self,
        scene_ids: List[int],
        scenes: List[Dict],
        uploaded_files: List,
        bg_video_file,
        bg_video_loop: bool,
        settings: Dict
    ) -> Dict:
        """
        v1.9: 비디오 배경 + 실사이미지 일괄 합성

        각 씬에 대해:
        1. 실사이미지 소스 찾기
        2. 배경 비디오를 씬 duration에 맞게 트림/루프
        3. FFmpeg로 합성하여 MP4 출력
        4. 썸네일 추출 (타임라인 뷰용)
        5. scenes.json 업데이트
        6. 캐시 무효화 + 완료 처리
        """
        from utils.timeline_composite import (
            composite_realshot_on_video,
            prepare_background_video,
            extract_video_thumbnail
        )
        import time

        results = {'success': [], 'failed': [], 'total': len(scene_ids)}

        if not bg_video_file:
            st.error("배경 비디오가 업로드되지 않았습니다.")
            return {"action": "realshot_replace_video_bg", "step": 3, "results": results}

        # 배경 비디오를 프로젝트 폴더에 저장
        bg_video_dir = self.project_path / "videos" / "backgrounds"
        bg_video_dir.mkdir(parents=True, exist_ok=True)

        timestamp = int(time.time() * 1000)
        bg_video_ext = Path(bg_video_file.name).suffix.lower()
        bg_video_saved_path = bg_video_dir / f"bg_realshot_{timestamp}{bg_video_ext}"

        with open(bg_video_saved_path, 'wb') as f:
            f.write(bg_video_file.getbuffer())
        bg_video_file.seek(0)

        print(f"[Step3 Video BG] 배경 비디오 저장: {bg_video_saved_path.name}")

        # 진행률 표시
        progress_bar = st.progress(0)
        status_text = st.empty()

        scene_map = self.manager.scene_map

        for idx, sid in enumerate(scene_ids):
            try:
                scene = scene_map.get(sid, {})
                scene_duration = scene.get('duration', scene.get('duration_estimate', 5.0))
                if not isinstance(scene_duration, (int, float)) or scene_duration <= 0:
                    scene_duration = 5.0

                status_text.text(f"씬 {sid} 처리 중... ({idx + 1}/{len(scene_ids)})")
                progress_bar.progress((idx + 1) / len(scene_ids))

                # 실사이미지 소스 결정
                realshot_source = self._find_realshot_source(sid, uploaded_files)

                if not realshot_source:
                    print(f"[Step3 Video BG] 씬 {sid}: 실사이미지 없음, 스킵")
                    results['failed'].append({'scene_id': sid, 'reason': '실사이미지 없음'})
                    continue

                # 배경 비디오 준비 (트림/루프)
                prepared_video_path = str(bg_video_dir / f"bg_prepared_{sid:03d}_{timestamp}.mp4")
                prepare_result = prepare_background_video(
                    video_path=str(bg_video_saved_path),
                    target_duration=float(scene_duration),
                    output_path=prepared_video_path,
                    loop=bg_video_loop
                )

                if not prepare_result:
                    print(f"[Step3 Video BG] 씬 {sid}: 비디오 준비 실패")
                    results['failed'].append({'scene_id': sid, 'reason': '비디오 준비 실패'})
                    continue

                # 위치 매핑 (한국어 → 영어)
                position_map = {"중앙": "center", "상단 중앙": "top", "하단 중앙": "bottom"}
                eng_position = position_map.get(settings.get('position', '중앙'), 'center')

                # 합성 실행
                composite_settings = {
                    'realshot_width_pct': settings['width_pct'],
                    'realshot_height_pct': settings['height_pct'],
                    'position': eng_position,
                    'bg_opacity': settings['bg_opacity'],
                    'output_width': 1920,
                    'output_height': 1080,
                }

                output_path = composite_realshot_on_video(
                    realshot_source=realshot_source,
                    bg_video_path=prepared_video_path,
                    scene_num=sid,
                    project_path=str(self.project_path),
                    settings=composite_settings
                )

                if output_path:
                    # 썸네일 추출 (타임라인 뷰용)
                    thumb_path = extract_video_thumbnail(output_path, sid, str(self.project_path))

                    # scenes.json 업데이트
                    self._update_scenes_json_video_bg(sid, output_path, thumb_path, timestamp)

                    # 캐시 무효화 + 완료 처리
                    self._invalidate_scene_image_cache(sid)
                    self.manager.mark_completed(3, {sid})

                    results['success'].append(sid)
                    print(f"[Step3 Video BG] 씬 {sid}: 합성 완료")
                else:
                    results['failed'].append({'scene_id': sid, 'reason': 'FFmpeg 합성 실패'})

                # 준비된 비디오 정리
                if os.path.exists(prepared_video_path):
                    try:
                        os.unlink(prepared_video_path)
                    except OSError:
                        pass

            except Exception as e:
                print(f"[Step3 Video BG] 씬 {sid} 처리 오류: {e}")
                import traceback
                traceback.print_exc()
                results['failed'].append({'scene_id': sid, 'reason': str(e)})

        # 완료
        progress_bar.progress(1.0)
        status_text.empty()
        self.manager.save()

        # 결과 표시
        if results['success']:
            st.success(f"비디오 배경 합성 완료: {len(results['success'])}/{len(scene_ids)}개 씬")
        if results['failed']:
            st.warning(f"실패: {len(results['failed'])}개 씬")
            for fail in results['failed']:
                st.caption(f"  씬 {fail['scene_id']}: {fail['reason']}")

        return {
            "action": "realshot_replace_video_bg",
            "step": 3,
            "results": results
        }

    def _find_realshot_source(self, scene_id: int, uploaded_files: List):
        """
        v1.9: 씬에 대한 실사이미지 소스 찾기

        우선순위:
        1. uploaded_files에서 파일명 매칭
        2. 기존 composited 이미지
        3. None
        """
        # 업로드 파일에서 매칭
        for f in uploaded_files:
            match = re.search(r'(\d+)', f.name)
            if match and int(match.group(1)) == scene_id:
                return f

        # 기존 이미지 검색
        composited_dir = self.project_path / "images" / "composited"
        scene_images_dir = self.project_path / "images" / "scenes"
        backgrounds_dir = self.project_path / "images" / "backgrounds"

        existing = self._find_scene_image(scene_id, composited_dir, scene_images_dir, backgrounds_dir)
        if existing:
            return str(existing)

        return None

    def _update_scenes_json_video_bg(
        self,
        scene_id: int,
        video_path: str,
        thumb_path: str,
        timestamp: int
    ):
        """
        v1.9: scenes.json에 비디오 배경 정보 업데이트
        """
        scenes_path = self.project_path / "analysis" / "scenes.json"

        if not scenes_path.exists():
            print(f"[Step3 Video BG] scenes.json 없음: {scenes_path}")
            return

        try:
            # BOM 안전 로드 (기존 _update_scenes_json_image_path 패턴)
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
                except Exception:
                    continue

            if not scenes:
                print(f"[Step3 Video BG] scenes.json 로드 실패")
                return

            # 해당 씬 찾아서 업데이트
            updated = False
            for scene in scenes:
                sid = scene.get('scene_id', scene.get('id', 0))
                if sid == scene_id:
                    scene['composited_image_path'] = thumb_path or video_path
                    scene['real_image_path'] = thumb_path or video_path
                    scene['background_video'] = video_path
                    scene['media_type'] = 'video'
                    scene['image_replaced'] = True
                    scene['replaced_at'] = timestamp
                    scene['replacement_type'] = 'realshot_video'
                    updated = True
                    break

            if updated:
                with open(scenes_path, 'w', encoding='utf-8') as f:
                    json.dump(scenes, f, ensure_ascii=False, indent=2)
                print(f"[Step3 Video BG] scenes.json 업데이트 완료 (씬 {scene_id})")
            else:
                print(f"[Step3 Video BG] scenes.json에서 씬 {scene_id}를 찾을 수 없음")

        except Exception as e:
            print(f"[Step3 Video BG] scenes.json 업데이트 실패: {e}")

    def _find_scene_image(
        self,
        scene_id: int,
        composited_dir: Path,
        scene_images_dir: Path,
        backgrounds_dir: Path
    ) -> Optional[Path]:
        """
        v1.9: 확장된 씬 이미지 검색 - 타임스탬프 파일명 + 비디오 썸네일 지원

        다양한 경로 패턴을 지원하여 씬 이미지를 찾습니다.

        검색 순서:
        1. composited/composited_XXX_*.ext (타임스탬프 포함, 가장 최근)
        2. composited/composited_XXX.ext (기존 형식)
        3. scenes/scene_XXX.ext
        4. scenes/XXX_scene.ext
        5. scenes/XXX_scene_composed.ext
        6. backgrounds/bg_scene_XXX_*.ext (가장 최근 파일)
        7. video_thumbnails/scene_XXX_video_thumb.ext (비디오 배경 썸네일)

        Args:
            scene_id: 씬 ID
            composited_dir: composited 이미지 폴더
            scene_images_dir: scenes 이미지 폴더
            backgrounds_dir: backgrounds 이미지 폴더

        Returns:
            찾은 이미지 경로 또는 None
        """
        extensions = ['png', 'jpg', 'jpeg', 'webp']

        # v1.6: 1. composited/composited_XXX_*.ext (타임스탬프 포함, 가장 최근)
        if composited_dir.exists():
            for ext in extensions:
                pattern = str(composited_dir / f"composited_{scene_id:03d}_*.{ext}")
                matches = glob_module.glob(pattern)
                if matches:
                    # 가장 최근 파일 선택 (수정 시간 기준)
                    latest_file = max(matches, key=lambda x: Path(x).stat().st_mtime)
                    return Path(latest_file)

        # 2. composited/composited_XXX.ext (기존 형식)
        for ext in extensions:
            comp_path = composited_dir / f"composited_{scene_id:03d}.{ext}"
            if comp_path.exists():
                return comp_path

        # 3. scenes/scene_XXX.ext
        for ext in extensions:
            scene_path = scene_images_dir / f"scene_{scene_id:03d}.{ext}"
            if scene_path.exists():
                return scene_path

        # 4. scenes/XXX_scene.ext (역순 형식)
        for ext in extensions:
            alt_path = scene_images_dir / f"{scene_id:03d}_scene.{ext}"
            if alt_path.exists():
                return alt_path

        # 5. scenes/XXX_scene_composed.ext
        for ext in extensions:
            composed_path = scene_images_dir / f"{scene_id:03d}_scene_composed.{ext}"
            if composed_path.exists():
                return composed_path

        # 6. backgrounds/bg_scene_XXX_*.ext (glob 패턴, 가장 최근 파일)
        if backgrounds_dir.exists():
            for ext in extensions:
                pattern = str(backgrounds_dir / f"bg_scene_{scene_id:03d}_*.{ext}")
                matches = glob_module.glob(pattern)
                if matches:
                    # 가장 최근 파일 선택 (타임스탬프 기준)
                    latest_file = max(matches, key=lambda x: Path(x).stat().st_mtime)
                    return Path(latest_file)

        # v1.9: 7. video_thumbnails/scene_XXX_video_thumb.ext (비디오 배경 썸네일)
        video_thumb_dir = self.project_path / "images" / "video_thumbnails"
        if video_thumb_dir.exists():
            for ext in extensions:
                thumb_path = video_thumb_dir / f"scene_{scene_id:03d}_video_thumb.{ext}"
                if thumb_path.exists():
                    return thumb_path

        return None

    def _run_realshot_detection(
        self,
        scenes: List[Dict],
        pool: Set[int],
        model_id: str,
        prompt_id: str = "default"
    ):
        """
        v1.8: AI 모델로 실사이미지 대체 필요 씬 감지 (프롬프트 선택 지원)

        Args:
            scenes: 전체 씬 목록
            pool: 분석 대상 씬 ID 집합
            model_id: 선택된 AI 모델 ID
            prompt_id: 사용할 프롬프트 템플릿 ID
        """
        from utils.ai_providers import get_model, AIProvider

        # 대상 씬 필터링
        target_scenes = [s for s in scenes if s.get('scene_id', s.get('id', 0)) in pool]

        if not target_scenes:
            st.warning("분석할 대상 씬이 없습니다.")
            return

        # v1.8: 프롬프트 템플릿 정보 표시
        prompt_data = self.prompt_manager.get_prompt(prompt_id)
        prompt_name = prompt_data.get('name', prompt_id) if prompt_data else prompt_id

        st.info(f"🔍 {len(target_scenes)}개 씬 분석 중... (모델: {model_id}, 프롬프트: {prompt_name})")
        progress_bar = st.progress(0)
        status_text = st.empty()

        # 스크립트 텍스트 수집
        scripts_for_analysis = []
        for scene in target_scenes:
            scene_id = scene.get('scene_id', scene.get('id', 0))
            script = scene.get('script_text', scene.get('narration', ''))
            scripts_for_analysis.append({
                "scene_id": scene_id,
                "script": script[:500]  # 500자 제한
            })

        # v1.8: 선택된 프롬프트 템플릿으로 AI 분석 프롬프트 생성
        prompt = self._build_realshot_detection_prompt(scripts_for_analysis, prompt_id)

        try:
            # 모델 정보 가져오기
            model_info = get_model(model_id)

            if not model_info:
                st.error(f"❌ 모델 정보를 찾을 수 없습니다: {model_id}")
                return

            status_text.text(f"AI 분석 중... ({model_info.name})")
            progress_bar.progress(30)

            # API 호출
            result = self._call_ai_for_detection(model_id, model_info, prompt)

            progress_bar.progress(80)

            if result:
                # 결과 파싱 및 표시
                detected_scenes = self._parse_detection_result(result)
                progress_bar.progress(100)

                if detected_scenes:
                    st.success(f"✅ 분석 완료: {len(detected_scenes)}개 씬에서 실사이미지 대체 필요 감지")

                    # 결과 세션 상태에 저장
                    st.session_state['step3_ai_detected_scenes'] = detected_scenes

                    # 결과 표시
                    with st.expander("📋 감지 결과 상세", expanded=True):
                        for item in detected_scenes:
                            sid = item.get('scene_id', 0)
                            reason = item.get('reason', '')
                            entities = item.get('entities', [])

                            entity_str = ", ".join(entities) if entities else "N/A"
                            st.markdown(f"""
                            **씬 {sid}**
                            - 감지 이유: {reason}
                            - 실체: {entity_str}
                            """)

                    # v1.4: 자동 선택 및 필터 옵션
                    st.markdown("---")
                    col_auto1, col_auto2 = st.columns(2)

                    with col_auto1:
                        if st.button("✅ 감지된 씬 자동 선택", key="step3_auto_select"):
                            detected_ids = {item.get('scene_id') for item in detected_scenes}
                            # 체크박스 상태 설정
                            for sid in detected_ids:
                                st.session_state[f"step3_scene_{sid}"] = True
                            # 필터 모드 활성화
                            st.session_state['step3_filter_detected_only'] = True
                            st.success(f"✅ {len(detected_ids)}개 씬 선택 및 필터 적용됨")
                            st.rerun()

                    with col_auto2:
                        # 필터 토글
                        filter_detected = st.checkbox(
                            "🔍 감지된 씬만 표시",
                            value=st.session_state.get('step3_filter_detected_only', False),
                            key="step3_filter_toggle"
                        )
                        if filter_detected != st.session_state.get('step3_filter_detected_only', False):
                            st.session_state['step3_filter_detected_only'] = filter_detected
                            st.rerun()
                else:
                    st.info("📭 실사이미지 대체가 필요한 씬이 감지되지 않았습니다.")
            else:
                st.error("❌ AI 분석 결과를 받지 못했습니다.")

        except Exception as e:
            st.error(f"❌ AI 분석 중 오류 발생: {str(e)}")
            print(f"[Step3 AI 분석] 오류: {e}")

        finally:
            progress_bar.empty()
            status_text.empty()

    def _build_realshot_detection_prompt(self, scenes: List[Dict], prompt_id: str = "default") -> str:
        """
        v1.8: 선택된 템플릿으로 실사이미지 감지용 AI 프롬프트 생성

        Args:
            scenes: 분석할 씬 목록
            prompt_id: 사용할 프롬프트 템플릿 ID

        Returns:
            완성된 프롬프트 문자열
        """
        # 씬 스크립트 텍스트 생성
        scenes_text = ""
        for s in scenes:
            scenes_text += f"\n[씬 {s['scene_id']}]\n{s['script']}\n"

        # v1.8: 선택된 프롬프트 템플릿 로드
        prompt_data = self.prompt_manager.get_prompt(prompt_id)

        if prompt_data and prompt_data.get('content'):
            # 템플릿 기반 프롬프트 생성
            template_content = prompt_data['content']

            # 씬 데이터 삽입
            prompt = f"""{template_content}

## 분석할 씬 스크립트
{scenes_text}

JSON만 출력하세요."""
        else:
            # 폴백: 기본 프롬프트 (템플릿 로드 실패 시)
            print(f"[Step3] ⚠️ 프롬프트 '{prompt_id}' 로드 실패, 기본 프롬프트 사용")
            prompt = f"""당신은 영상 제작 전문가입니다.
아래 씬 스크립트들을 분석하여, **실제 기업/인물/제품/장소**가 언급되어 실사 이미지로 대체해야 하는 씬을 찾아주세요.

## 분석 기준

실사이미지 대체가 필요한 경우:
1. **실제 기업명**: 삼성, 애플, 현대, LG, 네이버, 카카오, 테슬라, 아마존 등
2. **실제 인물명**: 일론 머스크, 제프 베조스, 팀 쿡, 이재용 등 실존 인물
3. **실제 제품명**: 아이폰, 갤럭시, 테슬라 모델Y, ChatGPT 등 실제 제품
4. **실제 장소/건물**: 에펠탑, 남산타워, 삼성전자 본사 등 실존 랜드마크
5. **로고/브랜드 표시**: 특정 브랜드 로고가 화면에 표시되어야 하는 경우

## 씬 스크립트
{scenes_text}

## 출력 형식 (JSON)

```json
{{
  "detected_scenes": [
    {{
      "scene_id": 씬번호,
      "reason": "대체 필요 이유",
      "entities": ["감지된 실체1", "감지된 실체2"]
    }}
  ]
}}
```

실사이미지 대체가 필요한 씬이 없으면 빈 배열을 반환하세요.
JSON만 출력하세요."""

        return prompt

    def _call_ai_for_detection(self, model_id: str, model_info, prompt: str) -> Optional[str]:
        """
        AI API 호출 (v1.2: UnifiedAIClient 사용)

        기존 개별 API 호출 메서드 대신 통합 클라이언트를 사용하여
        일관된 API 호출 및 에러 처리를 제공합니다.
        """
        from utils.ai_providers import AIProvider

        try:
            # LOCAL (Claude Code) 프로바이더는 지원하지 않음
            if model_info.provider == AIProvider.LOCAL:
                st.warning("⚠️ Claude Code는 이 분석에 지원되지 않습니다. 다른 모델을 선택해주세요.")
                return None

            # v1.2: UnifiedAIClient 사용하여 API 호출
            # model_info.id에 실제 모델 ID가 있음
            actual_model_id = model_info.id
            print(f"[Step3 AI] 통합 클라이언트로 호출: {actual_model_id}")

            client = UnifiedAIClient(model_id=actual_model_id)
            result = client.generate(
                prompt=prompt,
                max_tokens=4000,
                temperature=0.2
            )

            print(f"[Step3 AI] 응답 수신: {len(result)} 문자")
            return result

        except ValueError as e:
            # API 키 미설정 등의 에러
            st.error(f"❌ 설정 오류: {str(e)}")
            print(f"[Step3 AI] 설정 오류: {e}")
            return None
        except Exception as e:
            error_msg = str(e)
            print(f"[Step3 AI] API 호출 오류: {error_msg}")

            # 사용자 친화적 에러 메시지
            if "403" in error_msg and "leaked" in error_msg.lower():
                st.error("❌ API 키가 만료되었거나 보안 문제가 있습니다. API 관리 페이지에서 새 키를 설정해주세요.")
            elif "401" in error_msg or "unauthorized" in error_msg.lower():
                st.error("❌ API 키 인증에 실패했습니다. API 키를 확인해주세요.")
            elif "quota" in error_msg.lower() or "rate" in error_msg.lower():
                st.error("❌ API 할당량 초과 또는 속도 제한입니다. 잠시 후 다시 시도해주세요.")
            else:
                st.error(f"❌ API 호출 오류: {error_msg[:200]}")

            raise

    def _parse_detection_result(self, result: str) -> List[Dict]:
        """AI 응답에서 감지 결과 파싱"""
        try:
            # JSON 추출
            json_match = re.search(r'\{[\s\S]*\}', result)
            if not json_match:
                print(f"[Step3 AI] JSON 매칭 실패: {result[:200]}")
                return []

            data = json.loads(json_match.group())
            detected = data.get('detected_scenes', [])

            # 유효성 검증
            valid_results = []
            for item in detected:
                if 'scene_id' in item:
                    valid_results.append({
                        'scene_id': int(item['scene_id']),
                        'reason': item.get('reason', ''),
                        'entities': item.get('entities', [])
                    })

            return valid_results

        except json.JSONDecodeError as e:
            print(f"[Step3 AI] JSON 파싱 오류: {e}")
            return []
        except Exception as e:
            print(f"[Step3 AI] 결과 파싱 오류: {e}")
            return []


def render_step3_ui(manager, scenes: List[Dict], project_path: Path):
    """Step 3 UI 렌더 함수"""
    ui = Step3RealshotUI(manager, project_path)
    return ui.render(scenes)
