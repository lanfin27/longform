# -*- coding: utf-8 -*-
"""
components/storyboard_workflow/step4_video.py
Step 4: 비디오 대체 UI (v2.5 - 필터 설정 UI 추가)

처리 단위: 묶음 (Bundle)
대상: 사용자 설정 가능한 duration 필터 (기본 5초, 슬라이더/전체 표시 옵션)

v2.5 변경사항 (필터 설정 UI 추가):
- ⚙️ 필터 설정 섹션 추가: 최대 묶음 길이 슬라이더 (5~120초)
- 🔓 "모든 묶음 표시" 체크박스: duration 필터 비활성화 옵션
- 📊 제외된 묶음 수 경고 표시
- 🔄 필터 초기화 버튼

v2.4 변경사항 (타임라인 이미지 뷰 추가):
- 🖼️ 타임라인 뷰 추가: 각 묶음의 씬 이미지를 그리드로 표시
- 🔄 뷰 모드 전환: 리스트 ↔ 타임라인 선택 가능
- 📷 이미지 경로 자동 탐색: composited > korean_text > background 우선순위
- ✅ Step 3 실사이미지 대체와 동일한 UX 제공

v2.3 변경사항 (4초→5초 변경)

v2.2 변경사항 (🔴 긴급 수정 - 스토리보드 동기화 문제 해결):
- 🔴 scenes.json 경로 수정: project_path/scenes.json → project_path/analysis/scenes.json
- 🔴 session_state 동기화 추가: 비디오 생성 후 즉시 UI 반영
- 🔴 캐시 무효화 플래그 설정: storyboard_needs_refresh, force_reload_scenes
- 🔴 WorkflowManager.scene_map 동기화 추가

v2.1 변경사항 (비디오 길이 최적화):
- ⭐ 비디오 길이 = 묶음 SRT 총 길이 + 0.5초 버퍼
- ⭐ 기존 5초 고정 대비 API 비용 절감
- ⭐ 스토리보드 연동용 video_offset 정보 추가
- ⭐ 묶음 내 각 씬에 video_offset, video_scene_duration 저장
- ⭐ 예: 묶음 6 (씬 54-55, 3.3초 SRT) → 3.8초 비디오 생성

v2.0 변경사항:
- 실제 Video API 플랫폼 연동 (fal.ai, Replicate, PixVerse)
- 모델별 속도/품질/비용 표시
- 묶음 단위 비디오 일괄 생성
- 결과 미리보기 및 저장
"""

import streamlit as st
import time
import os
import glob as glob_module
from typing import Set, Dict, List, Optional, Any
from pathlib import Path

from .step_ui_base import StepUIBase
from .progress_visualizer import render_step_status_cards

# Video API imports
try:
    from utils.scene_video_generator import (
        get_available_video_platforms,
        get_i2v_models_for_platform,
        estimate_video_cost,
        get_video_prompt_for_scene,
        get_scene_image_path,
        generate_scene_video,
        batch_generate_scene_videos,
        get_recommended_video_duration,
        # ⭐ v2.1: 묶음 기반 최적화 비디오 길이 함수
        get_optimal_bundle_video_duration,
        calculate_bundle_srt_duration,
        get_bundle_scenes_by_id,
        VIDEO_API_AVAILABLE,
    )
    from utils.video_api.config import (
        PLATFORM_CONFIGS,
        ALL_MODELS,
        VideoType,
        SpeedTier,
        QualityTier,
    )
    VIDEO_INTEGRATION_AVAILABLE = True
except ImportError as e:
    VIDEO_INTEGRATION_AVAILABLE = False
    VIDEO_API_AVAILABLE = False
    print(f"[Step4 Video] ⚠️ Video API 모듈 로드 실패: {e}")


# 플랫폼 표시명 매핑
PLATFORM_DISPLAY_NAMES = {
    "fal_ai": "fal.ai (Wan, Kling, Hailuo 등)",
    "replicate": "Replicate (Wan, MiniMax, Luma 등)",
    "pixverse": "PixVerse (무료 크레딧 제공)",
}

# 플랫폼별 정보
PLATFORM_INFO = {
    "fal_ai": "💡 신규 가입 시 $10 무료 크레딧 제공. Wan I2V 추천 (가장 저렴)",
    "replicate": "💡 다양한 오픈소스 모델 지원. 크레딧 선불 결제",
    "pixverse": "💡 매일 60 무료 크레딧 제공. 워터마크 있음",
}


class Step4VideoUI(StepUIBase):
    """Step 4: 비디오 대체 (v2.5 - 필터 설정 UI 추가)"""

    def __init__(self, workflow_manager, project_path: Path):
        super().__init__(
            step_number=4,
            workflow_manager=workflow_manager,
            project_path=project_path
        )

    def get_pool(self) -> Set[int]:
        return self.manager.calculate_step4_pool()

    def get_assigned(self) -> Set[int]:
        return self.manager.state.step4_scenes

    def get_completed(self) -> Set[int]:
        return self.manager.state.completed_step4

    def render_step_content(
        self,
        scenes: List[Dict],
        pool: Set[int],
        assigned: Set[int],
        completed: Set[int]
    ) -> Optional[Dict]:
        """Step 4 콘텐츠 렌더링 (v2.0)"""

        # 이전 Step 완료 확인
        prev_pending = sum([
            len(self.manager.state.step1_scenes - self.manager.state.completed_step1),
            len(self.manager.state.step2_scenes - self.manager.state.completed_step2),
            len(self.manager.state.step3_scenes - self.manager.state.completed_step3),
        ])

        if prev_pending > 0:
            st.warning(f"⚠️ 이전 Step 대기 중: {prev_pending}개 씬")

        # 설명
        st.info("""
            **🎬 Step 4: 비디오 대체**

            - **대상**: 묶음 duration 필터 적용 (Step 1-3 처리 씬 제외)
            - **처리 단위**: 묶음 (Bundle) - 대표 씬만 비디오 생성
            - **비디오 길이**: SRT/TTS 기반 자동 추천 (5초 또는 10초)
        """)

        st.markdown("---")

        # ═══════════════════════════════════════════════════════════════════
        # v2.5: 필터 설정 섹션
        # ═══════════════════════════════════════════════════════════════════
        with st.expander("⚙️ 묶음 필터 설정", expanded=False):
            filter_col1, filter_col2, filter_col3 = st.columns(3)

            with filter_col1:
                max_duration = st.slider(
                    "최대 묶음 길이 (초)",
                    min_value=5,
                    max_value=120,
                    value=st.session_state.get("step4_max_duration", 5),
                    step=5,
                    key="step4_max_duration_slider",
                    help="이 길이 이하의 묶음만 표시됩니다"
                )
                st.session_state["step4_max_duration"] = max_duration

            with filter_col2:
                show_all = st.checkbox(
                    "모든 묶음 표시 (필터 해제)",
                    value=st.session_state.get("step4_show_all_bundles", True),
                    key="step4_show_all_checkbox",
                    help="체크하면 duration 필터 없이 모든 묶음을 표시합니다"
                )
                st.session_state["step4_show_all_bundles"] = show_all

            with filter_col3:
                if st.button("필터 초기화", key="step4_filter_reset"):
                    st.session_state["step4_max_duration"] = 5
                    st.session_state["step4_show_all_bundles"] = True
                    self.manager._pool_cache_valid = False
                    st.rerun()

            # 필터 변경 시 캐시 무효화
            self.manager._pool_cache_valid = False

        # pool 재계산 (필터 설정 반영)
        pool = self.manager.calculate_step4_pool()

        # 필터 상태 표시
        if show_all:
            st.success(f"📋 필터 해제 - 전체 묶음 표시: {len(pool)}개 대표 씬")
        else:
            # 전체 묶음 수 대비 표시
            all_pool = self.manager.calculate_step4_pool(disable_filter=True)
            excluded_count = len(all_pool) - len(pool)
            if excluded_count > 0:
                st.warning(f"⚠️ {excluded_count}개 묶음 제외됨 (>{max_duration}초) | 표시: {len(pool)}개 대표 씬")

        st.markdown("---")

        # Video API 확인
        if not VIDEO_INTEGRATION_AVAILABLE:
            st.error("❌ Video API 모듈이 설치되지 않았습니다.")
            return None

        # 사용 가능한 플랫폼 확인
        available_platforms = get_available_video_platforms()
        if not available_platforms:
            st.error("""
                ❌ 사용 가능한 Video API가 없습니다.

                다음 중 하나 이상의 API 키를 설정해주세요:
                - `FAL_KEY` (fal.ai)
                - `REPLICATE_API_TOKEN` (Replicate)
                - `PIXVERSE_API_KEY` (PixVerse)
            """)
            return None

        # ═══════════════════════════════════════════════════════════════════
        # 비디오 생성 설정 (자동조합과 동일한 UI)
        # ═══════════════════════════════════════════════════════════════════
        with st.expander("⚙️ 비디오 생성 설정", expanded=True):
            self._render_video_settings(available_platforms)

        st.markdown("---")

        # 대상 묶음 목록
        filter_label = "전체" if show_all else f"{max_duration}초 이하"
        st.markdown(f"#### 📋 대상 묶음 목록 ({filter_label})")

        if not pool:
            st.success("✅ 비디오 대체 대상 묶음이 없거나 모두 처리되었습니다.")
            return None

        # v2.4: 뷰 모드 선택
        col_view1, col_view2 = st.columns([1, 3])
        with col_view1:
            view_mode = st.radio(
                "뷰 모드",
                ["📋 리스트", "🖼️ 타임라인"],
                index=1,  # 타임라인이 기본값
                horizontal=True,
                key="step4_view_mode"
            )

        # 묶음 선택 (뷰 모드에 따라 다르게 렌더링)
        if "타임라인" in view_mode:
            selected = self._render_timeline_view(pool, scenes)
        else:
            selected = self._render_bundle_selection_v2(pool, scenes)

        # 영향받는 씬 미리보기
        self.render_affected_scenes_preview(selected)

        # 실행 버튼
        def on_assign(ids):
            self.manager.assign_to_step(4, ids)
            self.manager.save()

        def on_execute(ids):
            # v2.0: 실제 비디오 생성 실행
            affected = self.manager.get_scenes_affected_by_selection(ids, 4)
            scene_ids_to_generate = sorted(affected['total'])

            # 세션 상태에서 설정 가져오기
            platform = st.session_state.get("step4_platform", available_platforms[0])
            model_key = st.session_state.get("step4_model_key", "wan_i2v")
            prompt_type = st.session_state.get("step4_prompt_type", "full")
            auto_duration = st.session_state.get("step4_auto_duration", True)

            result = self._execute_video_generation(
                scene_ids=scene_ids_to_generate,
                scenes=scenes,
                platform=platform,
                model_key=model_key,
                prompt_type=prompt_type,
                auto_duration=auto_duration,
            )

            return result

        return self.render_execution_buttons(
            selected,
            on_assign=on_assign,
            on_execute=on_execute,
            execute_label="비디오 생성"
        )

    def _render_video_settings(self, available_platforms: List[str]):
        """비디오 생성 설정 UI (자동조합과 동일)"""

        col1, col2, col3 = st.columns(3)

        with col1:
            # 플랫폼 선택
            platform_options = [
                PLATFORM_DISPLAY_NAMES.get(p, p) for p in available_platforms
            ]
            platform_display = st.selectbox(
                "🏢 플랫폼",
                platform_options,
                key="step4_platform_display"
            )

            # 플랫폼 키 역매핑
            platform = available_platforms[platform_options.index(platform_display)]
            st.session_state["step4_platform"] = platform

        with col2:
            # 모델 선택
            i2v_models = get_i2v_models_for_platform(platform)

            if i2v_models:
                model_options = list(i2v_models.keys())
                model_display_names = [
                    i2v_models[k].display_name for k in model_options
                ]

                model_display = st.selectbox(
                    "🤖 모델",
                    model_display_names,
                    key="step4_model_display"
                )

                model_key = model_options[model_display_names.index(model_display)]
                st.session_state["step4_model_key"] = model_key

                # 모델 설정
                model_config = i2v_models[model_key]
            else:
                st.warning("이 플랫폼에 I2V 모델이 없습니다.")
                model_config = None
                model_key = None

        with col3:
            # 프롬프트 유형
            prompt_type_display = st.radio(
                "📝 프롬프트 유형",
                ["🎬 전체 (video_prompt_full)", "🎭 캐릭터 (video_prompt_character)"],
                horizontal=True,
                key="step4_prompt_type_display"
            )

            prompt_type = "full" if "전체" in prompt_type_display else "character"
            st.session_state["step4_prompt_type"] = prompt_type

        # 속도/품질/비용 표시
        if model_config:
            col1, col2, col3, col4 = st.columns(4)

            with col1:
                # 속도
                speed = model_config.speed
                if speed == SpeedTier.FAST:
                    speed_display = "⚡ FAST (< 1분)"
                elif speed == SpeedTier.MEDIUM:
                    speed_display = "🚀 MEDIUM (1-3분)"
                else:
                    speed_display = "🐢 SLOW (> 3분)"
                st.metric("속도", speed_display)

            with col2:
                # 품질
                quality = model_config.quality
                stars = "★" * quality.value + "☆" * (5 - quality.value)
                st.metric("품질", stars)

            with col3:
                # 비용
                if model_config.price_per_video:
                    cost_display = f"${model_config.price_per_video:.2f}/영상"
                elif model_config.price_per_second:
                    cost_display = f"${model_config.price_per_second:.3f}/초"
                elif model_config.credits_per_video:
                    cost_display = f"{model_config.credits_per_video} 크레딧/영상"
                else:
                    cost_display = "가격 정보 없음"
                st.metric("비용", cost_display)

            with col4:
                # 지원 길이
                durations = model_config.durations
                st.metric("지원 길이", f"{durations} 초")

            # 법적 경고
            if model_config.legal_warning:
                st.warning(f"⚠️ {model_config.legal_warning}")

        # 플랫폼 정보
        st.info(PLATFORM_INFO.get(platform, ""))

        # 자동 비디오 길이 추천
        st.markdown("---")
        col1, col2 = st.columns(2)

        with col1:
            auto_duration = st.checkbox(
                "🎯 SRT/TTS 기반 자동 비디오 길이 추천",
                value=True,
                key="step4_auto_duration",
                help="씬의 실제 오디오 길이에 따라 5초 또는 10초 비디오를 자동 선택합니다."
            )

        with col2:
            if not auto_duration:
                manual_duration = st.selectbox(
                    "비디오 길이",
                    model_config.durations if model_config else [5],
                    key="step4_manual_duration"
                )
                st.session_state["step4_duration"] = manual_duration

    def _render_bundle_selection_v2(
        self,
        pool: Set[int],
        scenes: List[Dict],
    ) -> Set[int]:
        """묶음 선택 UI (v2.1 - 최적화된 비디오 길이 표시)

        v2.2: WorkflowManager의 scene_map 사용 (bundle_id 일관성 보장)
        """
        selected = set()
        # v2.2: self.manager.scene_map 사용 (scenes.json의 정확한 bundle_id 참조)
        scene_map = self.manager.scene_map

        # 전체 선택
        col1, col2, col3 = st.columns([1, 1, 2])
        with col1:
            select_all = st.checkbox("전체 선택", key="step4_select_all")
        with col2:
            st.caption(f"대상 묶음: {len(pool)}개")
        with col3:
            # ⭐ v2.1: 최적화된 비디오 길이 요약 표시
            total_srt_duration = 0.0
            total_video_duration = 0.0
            for sid in pool:
                scene = scene_map.get(sid, {})
                bundle_id = scene.get('bundle_id', sid)
                bundle_scenes = [s for s in scenes if s.get('bundle_id', s.get('scene_id', s.get('id', 0))) == bundle_id]
                video_dur, srt_dur, _ = get_optimal_bundle_video_duration(bundle_scenes)
                total_srt_duration += srt_dur
                total_video_duration += video_dur
            # 기존 5초 고정 대비 절약량
            fixed_5s_total = len(pool) * 5.0
            saved_duration = fixed_5s_total - total_video_duration
            st.caption(f"📊 SRT: {total_srt_duration:.1f}초 → 비디오: {total_video_duration:.1f}초 | 💰 절약: {saved_duration:.1f}초")

        # 페이지네이션
        sorted_pool = sorted(pool)
        items_per_page = 12
        total_pages = max(1, (len(sorted_pool) + items_per_page - 1) // items_per_page)

        if total_pages > 1:
            page = st.number_input(
                "페이지",
                min_value=1,
                max_value=total_pages,
                value=1,
                key="step4_page"
            )
        else:
            page = 1

        start_idx = (page - 1) * items_per_page
        end_idx = min(start_idx + items_per_page, len(sorted_pool))
        page_items = sorted_pool[start_idx:end_idx]

        # 묶음 카드 렌더링
        for sid in page_items:
            scene = scene_map.get(sid, {})
            bundle_id = scene.get('bundle_id', sid)
            bundle_scene_ids = self.manager.bundle_map.get(bundle_id, [sid])

            # ⭐ v2.1: 묶음의 씬 데이터 가져오기
            bundle_scenes_data = [scene_map.get(s, {}) for s in bundle_scene_ids if scene_map.get(s)]

            # ⭐ v2.1: 최적화된 비디오 길이 계산 (SRT + 0.5초)
            opt_video_dur, srt_dur, duration_reason = get_optimal_bundle_video_duration(bundle_scenes_data)

            # 묶음 duration (참고용)
            bundle_duration = self.manager._get_bundle_duration(bundle_id)

            # 스크립트
            script = scene.get('script_text', scene.get('narration', ''))[:40]

            # 이미지 존재 여부
            image_path = get_scene_image_path(scene, str(self.project_path))
            has_image = image_path and os.path.exists(image_path)

            with st.container():
                cols = st.columns([0.4, 1.0, 0.8, 0.8, 0.8, 2.0])

                with cols[0]:
                    is_selected = st.checkbox(
                        f"묶음 {bundle_id} 선택",
                        value=select_all,
                        key=f"step4_bundle_{bundle_id}",
                        label_visibility="collapsed"
                    )
                    if is_selected:
                        selected.add(sid)

                with cols[1]:
                    scene_range = f"씬 {bundle_scene_ids[0]}-{bundle_scene_ids[-1]}" if len(bundle_scene_ids) > 1 else f"씬 {bundle_scene_ids[0]}"
                    st.markdown(f"**묶음 {bundle_id}**<br><small>{scene_range}</small>", unsafe_allow_html=True)

                with cols[2]:
                    # ⭐ v2.1: SRT 길이 표시
                    st.markdown(f"<small>📏 SRT {srt_dur:.1f}초</small>", unsafe_allow_html=True)

                with cols[3]:
                    # ⭐ v2.1: 최적화된 비디오 길이 (SRT + 0.5초)
                    color = "#22C55E"  # 최적화된 길이는 항상 녹색
                    st.markdown(f"<small style='color:{color}'>🎬 {opt_video_dur:.1f}초</small>", unsafe_allow_html=True)

                with cols[4]:
                    # 이미지 상태
                    if has_image:
                        st.markdown("<small style='color:#22C55E'>✅ 이미지</small>", unsafe_allow_html=True)
                    else:
                        st.markdown("<small style='color:#EF4444'>❌ 이미지 없음</small>", unsafe_allow_html=True)

                with cols[5]:
                    st.markdown(f"<small>{script}...</small>", unsafe_allow_html=True)

        if select_all:
            return pool.copy()

        return selected

    def _render_timeline_view(
        self,
        pool: Set[int],
        scenes: List[Dict],
    ) -> Set[int]:
        """
        v2.4: 타임라인 이미지 뷰 - 묶음별 씬 이미지 그리드 표시

        Step 3 실사이미지 대체와 동일한 UX 제공
        각 묶음의 씬 이미지를 시각적으로 표시하여 비디오 대체 대상 선택 용이

        Args:
            pool: 대상 씬 ID 집합
            scenes: 전체 씬 데이터

        Returns:
            선택된 씬 ID 집합
        """
        selected = set()
        scene_map = self.manager.scene_map

        # 전체 선택 및 통계
        col1, col2, col3 = st.columns([1, 1, 2])
        with col1:
            select_all = st.checkbox("전체 선택", key="step4_timeline_select_all")
        with col2:
            st.caption(f"대상 묶음: {len(pool)}개")
        with col3:
            # 최적화된 비디오 길이 요약 표시
            total_srt_duration = 0.0
            total_video_duration = 0.0
            for sid in pool:
                scene = scene_map.get(sid, {})
                bundle_id = scene.get('bundle_id', sid)
                bundle_scenes = [s for s in scenes if s.get('bundle_id', s.get('scene_id', s.get('id', 0))) == bundle_id]
                video_dur, srt_dur, _ = get_optimal_bundle_video_duration(bundle_scenes)
                total_srt_duration += srt_dur
                total_video_duration += video_dur
            fixed_5s_total = len(pool) * 5.0
            saved_duration = fixed_5s_total - total_video_duration
            st.caption(f"📊 SRT: {total_srt_duration:.1f}초 → 비디오: {total_video_duration:.1f}초 | 💰 절약: {saved_duration:.1f}초")

        st.markdown("---")

        # 페이지네이션
        sorted_pool = sorted(pool)
        items_per_page = 6  # 타임라인 뷰는 더 적게 표시 (이미지가 크므로)
        total_pages = max(1, (len(sorted_pool) + items_per_page - 1) // items_per_page)

        if total_pages > 1:
            page = st.number_input(
                "페이지",
                min_value=1,
                max_value=total_pages,
                value=1,
                key="step4_timeline_page"
            )
        else:
            page = 1

        start_idx = (page - 1) * items_per_page
        end_idx = min(start_idx + items_per_page, len(sorted_pool))
        page_items = sorted_pool[start_idx:end_idx]

        # 이미지 디렉토리 경로
        composited_dir = self.project_path / "images" / "composited"
        scene_images_dir = self.project_path / "images" / "scenes"
        backgrounds_dir = self.project_path / "images" / "backgrounds"

        # 묶음별 타임라인 카드 렌더링
        for sid in page_items:
            scene = scene_map.get(sid, {})
            bundle_id = scene.get('bundle_id', sid)
            bundle_scene_ids = self.manager.bundle_map.get(bundle_id, [sid])

            # 묶음의 씬 데이터 가져오기
            bundle_scenes_data = [scene_map.get(s, {}) for s in bundle_scene_ids if scene_map.get(s)]

            # 최적화된 비디오 길이 계산
            opt_video_dur, srt_dur, duration_reason = get_optimal_bundle_video_duration(bundle_scenes_data)

            # 묶음 컨테이너
            with st.container():
                # 묶음 헤더
                header_cols = st.columns([0.5, 2, 1.5, 1.5, 1])

                with header_cols[0]:
                    is_selected = st.checkbox(
                        f"묶음 {bundle_id}",
                        value=select_all,
                        key=f"step4_timeline_bundle_{bundle_id}",
                        label_visibility="collapsed"
                    )
                    if is_selected:
                        selected.add(sid)

                with header_cols[1]:
                    scene_range = f"씬 {bundle_scene_ids[0]}-{bundle_scene_ids[-1]}" if len(bundle_scene_ids) > 1 else f"씬 {bundle_scene_ids[0]}"
                    st.markdown(f"**묶음 {bundle_id}** ({scene_range})")

                with header_cols[2]:
                    st.markdown(f"🎤 SRT **{srt_dur:.1f}**초")

                with header_cols[3]:
                    st.markdown(f"🎬 비디오 **{opt_video_dur:.1f}**초")

                with header_cols[4]:
                    # 이미지 존재 여부 체크
                    has_all_images = all(
                        self._find_scene_image(s, composited_dir, scene_images_dir, backgrounds_dir)
                        for s in bundle_scene_ids
                    )
                    if has_all_images:
                        st.markdown("✅ 이미지 준비됨")
                    else:
                        st.markdown("⚠️ 일부 이미지 없음")

                # 씬 이미지 그리드
                num_scenes = len(bundle_scene_ids)
                cols_per_row = min(num_scenes, 4)  # 최대 4열
                img_cols = st.columns(cols_per_row)

                for i, scene_id in enumerate(bundle_scene_ids):
                    with img_cols[i % cols_per_row]:
                        scene_data = scene_map.get(scene_id, {})
                        script = scene_data.get('script_text', scene_data.get('narration', ''))[:30]

                        # 씬 번호
                        st.markdown(f"**씬 {scene_id}**")

                        # 이미지 찾기 및 표시
                        image_path = self._find_scene_image(
                            scene_id, composited_dir, scene_images_dir, backgrounds_dir
                        )

                        if image_path and image_path.exists():
                            # 타임스탬프로 캐시 우회
                            timestamp = int(image_path.stat().st_mtime * 1000)
                            st.image(
                                str(image_path),
                                use_container_width=True,
                                caption=None
                            )
                        else:
                            # 이미지 없음 플레이스홀더
                            st.markdown(
                                """<div style="
                                    background-color: #333;
                                    height: 100px;
                                    display: flex;
                                    align-items: center;
                                    justify-content: center;
                                    border-radius: 4px;
                                    color: #999;
                                ">이미지 없음</div>""",
                                unsafe_allow_html=True
                            )

                        # 스크립트 미리보기
                        if script:
                            st.caption(f"📝 {script}...")

                st.markdown("---")

        # 페이지 정보
        st.caption(f"표시 중: {len(page_items)}개 / 전체: {len(pool)}개 묶음")

        if select_all:
            return pool.copy()

        return selected

    def _find_scene_image(
        self,
        scene_id: int,
        composited_dir: Path,
        scene_images_dir: Path,
        backgrounds_dir: Path
    ) -> Optional[Path]:
        """
        v2.4: 씬 이미지 경로 찾기 (우선순위 적용)

        우선순위:
        1. composited/composited_XXX_*.ext (타임스탬프 포함, 가장 최근)
        2. composited/composited_XXX.ext (기존 형식)
        3. scenes/scene_XXX.ext
        4. backgrounds/bg_scene_XXX_*.ext (가장 최근)

        Args:
            scene_id: 씬 ID
            composited_dir: composited 이미지 폴더
            scene_images_dir: scenes 이미지 폴더
            backgrounds_dir: backgrounds 이미지 폴더

        Returns:
            찾은 이미지 경로 또는 None
        """
        extensions = ['png', 'jpg', 'jpeg', 'webp']

        # 1. composited/composited_XXX_*.ext (타임스탬프 포함)
        if composited_dir.exists():
            for ext in extensions:
                pattern = str(composited_dir / f"composited_{scene_id:03d}_*.{ext}")
                matches = glob_module.glob(pattern)
                if matches:
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

        # 5. backgrounds/bg_scene_XXX_*.ext (glob 패턴)
        if backgrounds_dir.exists():
            for ext in extensions:
                pattern = str(backgrounds_dir / f"bg_scene_{scene_id:03d}_*.{ext}")
                matches = glob_module.glob(pattern)
                if matches:
                    latest_file = max(matches, key=lambda x: Path(x).stat().st_mtime)
                    return Path(latest_file)

        # 6. backgrounds/background_XXX.ext (대체 형식)
        for ext in extensions:
            bg_path = backgrounds_dir / f"background_{scene_id:03d}.{ext}"
            if bg_path.exists():
                return bg_path

        return None

    def _execute_video_generation(
        self,
        scene_ids: List[int],
        scenes: List[Dict],
        platform: str,
        model_key: str,
        prompt_type: str,
        auto_duration: bool,
    ) -> Dict:
        """
        비디오 생성 실행 (v2.1 - 묶음 최적화 + SRT 기반 길이)

        묶음 내 첫 번째 씬(대표 씬)만 비디오 생성, 나머지 씬은 동일 비디오 참조
        ⭐ v2.1: 비디오 길이 = 묶음 SRT 총 길이 + 0.5초 버퍼

        Args:
            scene_ids: 생성할 씬 ID 목록
            scenes: 전체 씬 데이터
            platform: API 플랫폼
            model_key: 모델 키
            prompt_type: 프롬프트 유형 (full/character)
            auto_duration: SRT 기반 자동 길이 사용 여부 (⭐ v2.1: 항상 최적화 적용)

        Returns:
            생성 결과 딕셔너리
        """
        results = {
            'success': [],
            'failed': [],
            'skipped': [],
            'generated': [],  # API 호출로 생성된 씬
            'referenced': [],  # 같은 묶음 내 다른 씬 (참조만)
            'total_cost': 0.0,
            'total_srt_duration': 0.0,  # ⭐ v2.1: SRT 총 길이
            'total_video_duration': 0.0,  # ⭐ v2.1: 비디오 총 길이
            'saved_duration': 0.0,  # ⭐ v2.1: 절약된 시간
        }

        if not scene_ids:
            st.warning("생성할 씬이 없습니다.")
            return results

        # 씬 맵 생성
        scene_map = {}
        for s in scenes:
            sid = s.get('scene_id', s.get('id', 0))
            if sid:
                scene_map[sid] = s

        project_path = str(self.project_path)

        # ═══════════════════════════════════════════════════════════════════
        # 묶음별로 씬 분류 - 대표 씬만 비디오 생성
        # ═══════════════════════════════════════════════════════════════════
        scenes_to_generate = []  # API 호출 대상 (묶음 대표 씬)
        scenes_to_reference = []  # 참조 대상 [{scene_id, source_scene_id}, ...]

        # ⭐ v2.1: 묶음별 최적화 비디오 길이 계산
        bundle_video_durations = {}  # bundle_id → {video_duration, srt_duration, reason}

        # 묶음 역맵 구축
        scene_to_bundle = {}
        for bid, sids in self.manager.bundle_map.items():
            for sid in sids:
                scene_to_bundle[sid] = bid

        # 처리된 묶음 추적
        processed_bundles = {}  # bundle_id → representative_scene_id

        for scene_id in scene_ids:
            bundle_id = scene_to_bundle.get(scene_id)

            if bundle_id is None:
                # 묶음에 속하지 않는 단독 씬
                scenes_to_generate.append(scene_id)

                # ⭐ v2.1: 단독 씬도 최적화 길이 계산
                single_scene = scene_map.get(scene_id, {})
                video_dur, srt_dur, reason = get_optimal_bundle_video_duration([single_scene])
                bundle_video_durations[scene_id] = {
                    'video_duration': video_dur,
                    'srt_duration': srt_dur,
                    'reason': reason
                }
            elif bundle_id not in processed_bundles:
                # 이 묶음의 첫 번째 처리 → 대표 씬으로 지정
                bundle_scene_ids = self.manager.bundle_map.get(bundle_id, [scene_id])
                representative_id = bundle_scene_ids[0]

                if representative_id in scene_ids:
                    scenes_to_generate.append(representative_id)
                    processed_bundles[bundle_id] = representative_id
                else:
                    scenes_to_generate.append(scene_id)
                    processed_bundles[bundle_id] = scene_id

                # ⭐ v2.1: 묶음 전체 씬으로 최적화 비디오 길이 계산
                bundle_scenes_data = [scene_map.get(s, {}) for s in bundle_scene_ids if scene_map.get(s)]
                video_dur, srt_dur, reason = get_optimal_bundle_video_duration(bundle_scenes_data)
                bundle_video_durations[bundle_id] = {
                    'video_duration': video_dur,
                    'srt_duration': srt_dur,
                    'reason': reason,
                    'bundle_scenes': bundle_scene_ids
                }
            else:
                # 이미 처리된 묶음의 다른 씬
                source_scene_id = processed_bundles[bundle_id]
                if scene_id != source_scene_id:
                    scenes_to_reference.append({
                        'scene_id': scene_id,
                        'source_scene_id': source_scene_id,
                        'bundle_id': bundle_id
                    })

        total_generate = len(scenes_to_generate)
        total_reference = len(scenes_to_reference)
        total = total_generate + total_reference

        # ⭐ v2.1: 총 SRT/비디오 길이 계산
        total_srt = sum(d['srt_duration'] for d in bundle_video_durations.values())
        total_video = sum(d['video_duration'] for d in bundle_video_durations.values())
        fixed_5s_total = total_generate * 5.0
        saved_duration = fixed_5s_total - total_video

        print(f"\n[Step4 Video] ═══════════════════════════════════════════════════════")
        print(f"[Step4 Video] 📋 묶음 최적화 분석 완료 (v2.1)")
        print(f"[Step4 Video] 선택된 전체 씬: {len(scene_ids)}개")
        print(f"[Step4 Video] API 생성 대상 (묶음 대표): {total_generate}개 → {scenes_to_generate}")
        print(f"[Step4 Video] 참조 대상: {total_reference}개")
        print(f"[Step4 Video] ⏱️ SRT 총 길이: {total_srt:.1f}초")
        print(f"[Step4 Video] 🎬 비디오 총 길이: {total_video:.1f}초 (기존 5초 고정: {fixed_5s_total}초)")
        print(f"[Step4 Video] 💰 시간 절약: {saved_duration:.1f}초 ({(saved_duration/fixed_5s_total*100):.0f}% 절약)" if fixed_5s_total > 0 else "")
        print(f"[Step4 Video] ═══════════════════════════════════════════════════════\n")

        st.markdown("### 🎬 비디오 생성")

        # ⭐ v2.1: 최적화 정보 표시
        st.info(f"""
            **📦 묶음 최적화 적용 (v2.1)**
            - API 생성: **{total_generate}개** 씬 (묶음 대표만)
            - 참조 설정: **{total_reference}개** 씬 (같은 묶음 내)
            - ⏱️ SRT 총 길이: **{total_srt:.1f}초** → 비디오: **{total_video:.1f}초** (+0.5초 버퍼)
            - 💰 기존 5초 고정 대비 **{saved_duration:.1f}초 절약** ({(saved_duration/fixed_5s_total*100):.0f}%)
        """ if fixed_5s_total > 0 else f"""
            **📦 묶음 최적화 적용 (v2.1)**
            - API 생성: **{total_generate}개** 씬 (묶음 대표만)
            - 참조 설정: **{total_reference}개** 씬 (같은 묶음 내)
        """)

        # UI 요소
        progress_bar = st.progress(0)
        status_text = st.empty()
        workflow_container = st.container()
        current_video_container = st.empty()
        result_container = st.container()

        try:
            # 출력 폴더 생성
            output_dir = Path(project_path) / "videos" / "ai_generated"
            output_dir.mkdir(parents=True, exist_ok=True)

            # 생성된 비디오 경로 저장
            generated_videos = {}  # scene_id → video_path

            # ═══════════════════════════════════════════════════════════════════
            # 1단계: 묶음 대표 씬 비디오 생성 (API 호출)
            # ═══════════════════════════════════════════════════════════════════
            st.markdown("#### 🎬 1단계: API 비디오 생성 (묶음 대표 씬)")

            for idx, scene_id in enumerate(scenes_to_generate):
                progress = (idx + 1) / total
                progress_bar.progress(progress)

                scene = scene_map.get(scene_id)
                if not scene:
                    results['skipped'].append({'scene': scene_id, 'reason': '씬 데이터 없음'})
                    continue

                # ⭐ v2.1: 묶음 기반 최적화 비디오 길이 사용
                bundle_id = scene_to_bundle.get(scene_id, scene_id)
                duration_info = bundle_video_durations.get(bundle_id) or bundle_video_durations.get(scene_id)

                if duration_info:
                    video_duration = duration_info['video_duration']
                    srt_duration = duration_info['srt_duration']
                    duration_reason = duration_info['reason']
                else:
                    # 폴백: 단일 씬 기준 계산
                    video_duration, srt_duration, duration_reason = get_optimal_bundle_video_duration([scene])

                status_text.markdown(f"**🎬 씬 {scene_id} 비디오 생성 중... ({idx + 1}/{total_generate}) - {duration_reason}**")

                # 이미지 경로
                image_path = get_scene_image_path(scene, project_path)
                if not image_path:
                    results['skipped'].append({'scene': scene_id, 'reason': '이미지 없음'})
                    print(f"[Step4 Video] ⏭️ 씬 {scene_id} 스킵: 이미지 없음")
                    continue

                # 프롬프트 추출
                prompt = get_video_prompt_for_scene(scene, prompt_type)
                if not prompt:
                    results['skipped'].append({'scene': scene_id, 'reason': '프롬프트 없음'})
                    print(f"[Step4 Video] ⏭️ 씬 {scene_id} 스킵: 프롬프트 없음")
                    continue

                # 워크플로우 정보 표시
                with workflow_container:
                    self._render_workflow_info(
                        scene_id=scene_id,
                        image_path=image_path,
                        prompt=prompt,
                        video_duration=video_duration,
                        duration_reason=duration_reason,
                        platform=platform,
                        model_key=model_key
                    )

                # 비디오 생성
                try:
                    print(f"[Step4 Video] 🎬 씬 {scene_id} API 호출 시작...")

                    result = generate_scene_video(
                        image_path=image_path,
                        prompt=prompt,
                        platform=platform,
                        model_key=model_key,
                        duration=video_duration,
                        resolution="720p",
                        output_dir=str(output_dir),
                        scene_id=scene_id,
                    )

                    if result.get('success'):
                        video_path = result.get('video_path')
                        generated_videos[scene_id] = {
                            'path': video_path,
                            'bundle_id': bundle_id,
                            'video_duration': video_duration,
                            'srt_duration': srt_duration
                        }

                        # ⭐ v2.1: 씬 데이터에 비디오 경로 + 오프셋 저장
                        scene['video_path'] = video_path
                        scene['bundle_video_path'] = video_path
                        scene['video_generated_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
                        scene['video_duration_generated'] = video_duration

                        # ⭐ v2.1: 묶음 내 각 씬에 video_offset 설정
                        bundle_scene_ids = self.manager.bundle_map.get(bundle_id, [scene_id])
                        current_offset = 0.0

                        for bsid in bundle_scene_ids:
                            bs = scene_map.get(bsid)
                            if bs:
                                # 해당 씬의 SRT duration
                                from utils.scene_video_generator import get_scene_srt_duration
                                bs_duration = get_scene_srt_duration(bs) or bs.get('duration', bs.get('duration_estimate', 0)) or 0

                                # 비디오 오프셋 설정
                                bs['video_path'] = video_path
                                bs['bundle_video_path'] = video_path
                                bs['video_offset'] = round(current_offset, 2)
                                bs['video_scene_duration'] = round(float(bs_duration), 2)
                                bs['video_bundle_id'] = bundle_id

                                print(f"[Step4 Video]   씬 {bsid}: offset={current_offset:.2f}초, duration={bs_duration:.2f}초")

                                current_offset += float(bs_duration)

                        # 워크플로우 상태 업데이트
                        self.manager.mark_completed(4, {scene_id})

                        results['success'].append(scene_id)
                        results['generated'].append({
                            'scene_id': scene_id,
                            'bundle_id': bundle_id,
                            'video_path': video_path,
                            'video_url': result.get('video_url'),
                            'prompt': prompt,
                            'video_duration': video_duration,
                            'srt_duration': srt_duration,
                            'duration_reason': duration_reason,
                            'cost_usd': result.get('cost_usd', 0),
                            'generation_time': result.get('generation_time', 0),
                            'type': 'generated'
                        })

                        results['total_cost'] += result.get('cost_usd', 0)
                        results['total_srt_duration'] += srt_duration
                        results['total_video_duration'] += video_duration

                        print(f"[Step4 Video] ✅ 씬 {scene_id} (묶음 {bundle_id}) 비디오 생성 완료: {video_path}")

                        # 비디오 미리보기
                        if video_path and os.path.exists(video_path):
                            current_video_container.video(video_path)
                    else:
                        error = result.get('error', '알 수 없는 오류')
                        results['failed'].append({'scene': scene_id, 'reason': error})
                        print(f"[Step4 Video] ❌ 씬 {scene_id} 실패: {error}")

                except Exception as e:
                    results['failed'].append({'scene': scene_id, 'reason': str(e)})
                    print(f"[Step4 Video] ❌ 씬 {scene_id} 에러: {e}")

                # API 레이트 리밋 방지
                if idx < total_generate - 1:
                    time.sleep(2.0)

            # ═══════════════════════════════════════════════════════════════════
            # 2단계: 묶음 내 다른 씬에 비디오 참조 설정
            # ⭐ v2.1: video_offset도 이미 1단계에서 설정됨 (위에서 묶음 전체 처리)
            # ═══════════════════════════════════════════════════════════════════
            if scenes_to_reference:
                st.markdown("#### 📋 2단계: 비디오 참조 확인 (같은 묶음 내)")

                for ref_info in scenes_to_reference:
                    scene_id = ref_info['scene_id']
                    source_scene_id = ref_info['source_scene_id']
                    bundle_id = ref_info['bundle_id']

                    source_video_info = generated_videos.get(source_scene_id)

                    if source_video_info:
                        video_path = source_video_info['path']
                        scene = scene_map.get(scene_id)
                        if scene:
                            # ⭐ v2.1: video_offset은 이미 1단계에서 설정됨
                            # 추가 메타데이터만 설정
                            scene['video_reference_from'] = source_scene_id
                            scene['video_bundle_id'] = bundle_id

                            # video_path와 video_offset이 없으면 설정
                            if not scene.get('video_path'):
                                scene['video_path'] = video_path
                                scene['bundle_video_path'] = video_path

                            # 워크플로우 상태 업데이트
                            self.manager.mark_completed(4, {scene_id})

                            # 오프셋 정보 가져오기
                            video_offset = scene.get('video_offset', 0)
                            video_scene_dur = scene.get('video_scene_duration', 0)

                            results['success'].append(scene_id)
                            results['referenced'].append({
                                'scene_id': scene_id,
                                'source_scene_id': source_scene_id,
                                'video_path': video_path,
                                'bundle_id': bundle_id,
                                'video_offset': video_offset,
                                'video_scene_duration': video_scene_dur,
                                'type': 'referenced'
                            })

                            print(f"[Step4 Video] 📋 씬 {scene_id}: 묶음 {bundle_id} 비디오 참조 (offset={video_offset:.2f}초)")
                    else:
                        results['failed'].append({
                            'scene': scene_id,
                            'reason': f'원본 비디오 없음 (씬 {source_scene_id})'
                        })

            # 완료
            progress_bar.progress(1.0)
            status_text.markdown("**✅ 비디오 생성 완료!**")
            current_video_container.empty()

            # 워크플로우 상태 저장
            self.manager.save()

            # scenes.json 업데이트
            self._save_scenes_json(scenes, project_path)

            # 결과 요약 표시
            with result_container:
                self._render_generation_results(results)

        except Exception as e:
            st.error(f"❌ 비디오 생성 중 오류 발생: {e}")
            import traceback
            st.code(traceback.format_exc())
            print(f"[Step4 Video] ❌ 생성 오류: {e}")

        return results

    def _render_workflow_info(
        self,
        scene_id: int,
        image_path: str,
        prompt: str,
        video_duration: int,
        duration_reason: str,
        platform: str,
        model_key: str
    ):
        """워크플로우 정보 표시"""
        with st.expander(f"📋 씬 {scene_id} 생성 정보", expanded=False):
            cols = st.columns([1, 2, 1])

            with cols[0]:
                st.markdown("**📷 소스 이미지**")
                if image_path and os.path.exists(image_path):
                    st.image(image_path, width=150)
                else:
                    st.warning("이미지 없음")

            with cols[1]:
                st.markdown("**📝 비디오 프롬프트**")
                st.text_area(
                    "프롬프트",
                    prompt,
                    height=100,
                    key=f"workflow_video_prompt_{scene_id}",
                    disabled=True,
                    label_visibility="collapsed"
                )

            with cols[2]:
                st.markdown("**⚙️ 생성 설정**")
                st.write(f"- 플랫폼: {platform}")
                st.write(f"- 모델: {model_key}")
                st.write(f"- 길이: {video_duration}초")
                st.caption(duration_reason)

    def _render_generation_results(self, results: Dict):
        """생성 결과 상세 표시 (v2.1)"""
        st.markdown("### 📊 결과 요약")

        generated = results.get('generated', [])
        referenced = results.get('referenced', [])
        failed = results.get('failed', [])
        skipped = results.get('skipped', [])
        total_cost = results.get('total_cost', 0)
        total_srt = results.get('total_srt_duration', 0)
        total_video = results.get('total_video_duration', 0)

        # ⭐ v2.1: 절약량 계산
        fixed_5s_total = len(generated) * 5.0
        saved_duration = fixed_5s_total - total_video if fixed_5s_total > 0 else 0

        # 통계 카드
        col1, col2, col3, col4, col5, col6 = st.columns(6)
        with col1:
            st.metric("✅ 성공", len(results['success']))
        with col2:
            st.metric("🎬 API 생성", len(generated))
        with col3:
            st.metric("📋 참조", len(referenced))
        with col4:
            st.metric("❌ 실패", len(failed))
        with col5:
            st.metric("💰 총 비용", f"${total_cost:.2f}")
        with col6:
            # ⭐ v2.1: 시간 절약 표시
            st.metric("⏱️ 절약", f"{saved_duration:.1f}초")

        # ⭐ v2.1: 비디오 길이 최적화 요약
        if total_video > 0:
            st.success(f"""
                **⏱️ 비디오 길이 최적화 완료**
                - SRT 총 길이: **{total_srt:.1f}초**
                - 비디오 총 길이: **{total_video:.1f}초** (SRT + 0.5초 버퍼)
                - 기존 5초 고정 대비: **{saved_duration:.1f}초 절약** ({(saved_duration/fixed_5s_total*100):.0f}%)
            """ if fixed_5s_total > 0 else f"""
                **⏱️ 비디오 길이 최적화 완료**
                - SRT 총 길이: **{total_srt:.1f}초**
                - 비디오 총 길이: **{total_video:.1f}초** (SRT + 0.5초 버퍼)
            """)

        # 상세 정보 - API 생성된 씬
        if generated:
            with st.expander(f"🎬 API로 생성된 비디오 ({len(generated)}개)", expanded=True):
                for item in generated:
                    scene_id = item['scene_id']
                    bundle_id = item.get('bundle_id', scene_id)
                    cols = st.columns([1, 2, 1])

                    with cols[0]:
                        if item.get('video_path') and os.path.exists(item['video_path']):
                            st.video(item['video_path'])
                        elif item.get('video_url'):
                            st.video(item['video_url'])

                    with cols[1]:
                        st.markdown(f"**씬 {scene_id}** (묶음 {bundle_id}) - API 생성")
                        prompt = item.get('prompt', '')
                        st.caption(prompt[:200] + "..." if len(prompt) > 200 else prompt)

                    with cols[2]:
                        # ⭐ v2.1: SRT + 비디오 길이 표시
                        srt_dur = item.get('srt_duration', 0)
                        video_dur = item.get('video_duration', 5)
                        st.write(f"📏 SRT: {srt_dur:.1f}초")
                        st.write(f"🎬 비디오: {video_dur:.1f}초")
                        st.caption(item.get('duration_reason', ''))
                        st.write(f"💰 비용: ${item.get('cost_usd', 0):.3f}")
                        st.write(f"⏰ 생성: {item.get('generation_time', 0):.1f}초")

                    st.divider()

        # 상세 정보 - 참조된 씬
        if referenced:
            with st.expander(f"📋 참조 설정된 씬 ({len(referenced)}개) - 💰 API 절약!", expanded=False):
                for item in referenced:
                    scene_id = item['scene_id']
                    source_id = item['source_scene_id']
                    bundle_id = item['bundle_id']
                    video_offset = item.get('video_offset', 0)
                    video_scene_dur = item.get('video_scene_duration', 0)

                    # ⭐ v2.1: 오프셋 정보 표시
                    st.markdown(f"**씬 {scene_id}** → 묶음 {bundle_id} 비디오 (offset: {video_offset:.2f}초 ~ {video_offset + video_scene_dur:.2f}초)")
                    st.caption(f"스토리보드에서 {video_offset:.2f}초 지점부터 재생됩니다.")

        # 실패/스킵 정보
        if failed:
            with st.expander(f"❌ 실패한 씬 ({len(failed)}개)", expanded=False):
                for item in failed:
                    st.error(f"씬 {item['scene']}: {item.get('reason', '알 수 없는 오류')}")

        if skipped:
            with st.expander(f"⏭️ 스킵된 씬 ({len(skipped)}개)", expanded=False):
                for item in skipped:
                    st.warning(f"씬 {item['scene']}: {item.get('reason', '알 수 없는 이유')}")

    def _save_scenes_json(self, scenes: List[Dict], project_path: str):
        """
        scenes.json 업데이트 (v2.2 - 경로 수정 및 동기화 강화)

        v2.2 수정사항:
        - 경로 수정: project_path/scenes.json → project_path/analysis/scenes.json
        - session_state 동기화 추가
        - 캐시 무효화 플래그 설정
        """
        import json

        # ✅ v2.2: 올바른 경로 사용 (analysis/scenes.json)
        scenes_path = Path(project_path) / "analysis" / "scenes.json"

        print(f"[Step4 Video] 📁 scenes.json 저장 경로: {scenes_path}")

        try:
            # 기존 데이터 로드 및 병합
            if scenes_path.exists():
                # BOM 안전 로드
                encodings = ['utf-8-sig', 'utf-8', 'cp949']
                existing_data = None

                for encoding in encodings:
                    try:
                        with open(scenes_path, 'r', encoding=encoding) as f:
                            content = f.read()
                        if content.startswith('\ufeff'):
                            content = content[1:]
                        existing_data = json.loads(content)
                        break
                    except:
                        continue

                if existing_data is None:
                    print(f"[Step4 Video] ⚠️ 기존 scenes.json 로드 실패, 새로 생성")
                    existing_data = scenes
                elif isinstance(existing_data, list):
                    # 리스트 형식 - scene_id로 매칭하여 업데이트
                    existing_map = {s.get('scene_id', s.get('id', i)): s for i, s in enumerate(existing_data)}

                    for scene in scenes:
                        sid = scene.get('scene_id', scene.get('id', 0))
                        if sid and sid in existing_map:
                            # 비디오 관련 필드만 업데이트
                            video_fields = [
                                'video_path', 'bundle_video_path', 'video_generated_at',
                                'video_duration_generated', 'video_offset', 'video_scene_duration',
                                'video_bundle_id', 'video_reference_from'
                            ]
                            for field in video_fields:
                                if field in scene:
                                    existing_map[sid][field] = scene[field]
                            print(f"[Step4 Video] ✅ 씬 {sid} 비디오 정보 업데이트")

                    existing_data = list(existing_map.values())

                elif isinstance(existing_data, dict) and 'scenes' in existing_data:
                    # dict 내부에 scenes 리스트가 있는 경우
                    existing_map = {s.get('scene_id', s.get('id', i)): s for i, s in enumerate(existing_data['scenes'])}

                    for scene in scenes:
                        sid = scene.get('scene_id', scene.get('id', 0))
                        if sid and sid in existing_map:
                            video_fields = [
                                'video_path', 'bundle_video_path', 'video_generated_at',
                                'video_duration_generated', 'video_offset', 'video_scene_duration',
                                'video_bundle_id', 'video_reference_from'
                            ]
                            for field in video_fields:
                                if field in scene:
                                    existing_map[sid][field] = scene[field]

                    existing_data['scenes'] = list(existing_map.values())
            else:
                existing_data = scenes
                print(f"[Step4 Video] 📁 새 scenes.json 생성")

            # 저장
            with open(scenes_path, 'w', encoding='utf-8') as f:
                json.dump(existing_data, f, ensure_ascii=False, indent=2)

            print(f"[Step4 Video] ✅ scenes.json 저장 완료: {scenes_path}")

            # ✅ v2.2: session_state 동기화
            self._sync_session_state_scenes(scenes, existing_data)

            # ✅ v2.2: 캐시 무효화 플래그 설정
            st.session_state['storyboard_needs_refresh'] = True
            st.session_state['force_reload_scenes'] = True
            st.session_state['video_status_cache_invalid'] = True

            # ✅ v2.2: WorkflowManager 캐시 클리어
            from . import clear_workflow_manager_cache
            clear_workflow_manager_cache(Path(project_path))
            print(f"[Step4 Video] ✅ WorkflowManager 캐시 클리어됨")

            print(f"[Step4 Video] ✅ 동기화 플래그 설정됨")

        except Exception as e:
            print(f"[Step4 Video] ❌ scenes.json 업데이트 실패: {e}")
            import traceback
            traceback.print_exc()

    def _sync_session_state_scenes(self, updated_scenes: List[Dict], full_scenes_data):
        """
        v2.2: session_state의 씬 데이터 동기화

        비디오 생성 후 즉시 UI에 반영되도록 session_state 업데이트
        """
        try:
            # session_state의 씬 데이터 업데이트
            if 'scenes' in st.session_state:
                existing_scenes = st.session_state.scenes
                existing_map = {s.get('scene_id', s.get('id', i)): s for i, s in enumerate(existing_scenes)}

                for scene in updated_scenes:
                    sid = scene.get('scene_id', scene.get('id', 0))
                    if sid and sid in existing_map:
                        # 비디오 관련 필드 업데이트
                        video_fields = [
                            'video_path', 'bundle_video_path', 'video_generated_at',
                            'video_duration_generated', 'video_offset', 'video_scene_duration',
                            'video_bundle_id', 'video_reference_from'
                        ]
                        for field in video_fields:
                            if field in scene:
                                existing_map[sid][field] = scene[field]

                st.session_state.scenes = list(existing_map.values())
                print(f"[Step4 Video] ✅ session_state.scenes 동기화 완료")

            # workflow manager의 scene_map도 업데이트
            if hasattr(self, 'manager') and hasattr(self.manager, 'scene_map'):
                for scene in updated_scenes:
                    sid = scene.get('scene_id', scene.get('id', 0))
                    if sid and sid in self.manager.scene_map:
                        video_fields = [
                            'video_path', 'bundle_video_path', 'video_generated_at',
                            'video_duration_generated', 'video_offset', 'video_scene_duration',
                            'video_bundle_id', 'video_reference_from'
                        ]
                        for field in video_fields:
                            if field in scene:
                                self.manager.scene_map[sid][field] = scene[field]

                print(f"[Step4 Video] ✅ WorkflowManager.scene_map 동기화 완료")

        except Exception as e:
            print(f"[Step4 Video] ⚠️ session_state 동기화 실패: {e}")


def render_step4_ui(manager, scenes: List[Dict], project_path: Path):
    """Step 4 UI 렌더 함수"""
    ui = Step4VideoUI(manager, project_path)
    return ui.render(scenes)
