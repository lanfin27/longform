# -*- coding: utf-8 -*-
"""
components/storyboard_workflow/step1_korean_text.py
Step 1: 한글 텍스트 씬 대체 UI (v3.0)

처리 단위: 묶음 (Bundle)
대상: image_prompt_korean_text 필드가 있는 씬

v3.0: 🔧 수동 추가 씬 UI 묶음 단위 표시 통일
      - 수정 전: "수동 추가 씬: 50개" (개별 씬 단위)
      - 수정 후: "수동 추가: 17개 묶음 (50개 씬)" (묶음 단위)
      - 최종 대상도 묶음 수로 표시: "37개 묶음 (AI 27 + 수동 10)"
      - AI 추천과 수동 추가의 UI 표시 형식 통일

v2.9: 🔴 긴급 수정 - 수동 선택 씬 개별 묶음 대신 기존 묶음 재사용
      - 문제: v2.8에서 수동 선택 씬이 기존 묶음의 비대표 멤버일 때 개별 묶음 생성 → API 낭비
      - 예시: 씬 8,9 선택 → 묶음3(씬7-9)에 이미 포함 → 개별 묶음 2개 불필요 생성
      - 수정: 이미 묶음에 포함된 씬은 스킵 (대표 씬에서 복사됨)
      - 결과: 68개 묶음 → 42개 묶음 (26개 API 호출 절약!)

v1.1: 실제 이미지 생성 로직 추가
v1.2: 폴백 제거 - 이미지 생성 탭에서 선택된 씬만 표시
v1.3: Nano Banana / Pro 모델 선택 UI 추가 (나노바나나 합성과 동일)
      - 모델 선택 라디오 버튼 (빠름/고품질)
      - 레퍼런스 강도 슬라이더
      - 워크플로우 정보 expander 기본 펼침
v1.4: 묶음 씬 범위 표시 수정 - 연속된 씬만 범위로 표시
      - 기존: "씬 46-200" (46과 200이 연속이 아닌데 범위로 표시됨)
      - 수정: "씬 44, 46, 90-91, 106" (연속된 씬만 범위로 묶음)
v1.5: 배경/캐릭터 레퍼런스 강도 분리
      - 단일 슬라이더 → 배경/캐릭터 별도 슬라이더
      - 프리셋 버튼 추가 (배경 중심, 캐릭터 중심, 균형, 창의적)
v1.6: 🔴 긴급 수정 - 묶음 로직 오류 수정
      - 기존: 원본 scenes.json의 bundle_id 사용 (비연속 씬이 같은 묶음에!)
      - 수정: 선택된 씬들을 정렬 후 단순 분할하여 새 묶음 생성
      - 핵심: 39개 선택 씬 → 3개씩 나눠서 13개 묶음 생성
v1.7: 🔧 묶음 로직 재수정 - 기존 bundle_id 존중
      - 문제: v1.6에서 씬 [49,50,51,53,54] 선택 시 [49,51,53]만 처리
      - 원인: UI bundle_size로 단순 분할, 기존 묶음 무시
      - 수정: scenes.json의 bundle_id를 참조하여 올바른 묶음 생성
      - 결과: [[49,50], [51], [53,54]] 처럼 기존 묶음 구조 유지
v1.8: 🔴 긴급 수정 - 묶음 내 중복 API 호출 문제
      - 문제: 묶음 [47,48] 선택 시 둘 다 API 호출 (복사 0개!)
      - 원인: on_execute()에서 대표 씬만 전달 → 모든 씬에 API 호출
      - 수정: session_state의 step1_all_selected_scene_ids_v16 사용
      - 결과: 대표 씬만 API 호출, 나머지는 이미지 복사 (API 50% 절약!)
v1.9: 🔴 긴급 수정 - 묶음 멤버 씬 이미지 복사 누락
      - 문제: 대표 씬 45, 47 생성 후 멤버 씬 46, 48에 이미지 복사 안됨
      - 원인: _create_bundles_from_existing_info()가 선택된 대표 씬만 포함
      - 수정: bundle_id로 묶음의 전체 씬 확장 (대표 + 멤버 모두 포함)
      - 결과: 대표 씬 [45] 선택 → 묶음 전체 [45,46] 처리 (복사 정상 작동!)
v2.0: 🔧 레퍼런스 강도 기능 제거
      - 제거: 배경/캐릭터 레퍼런스 강도 슬라이더 UI
      - 제거: 빠른 설정 버튼 (배경 중심, 캐릭터 중심, 균형, 창의적)
      - 제거: "배경 분위기를 적당히(X%)..." 프롬프트 삽입 로직
      - 효과: 원본 프롬프트 그대로 사용하여 이미지 품질 향상
      - 유지: 레퍼런스 이미지 선택 체크박스 (배경/캐릭터)
v2.1: 🚀 배치(병렬) 처리 모드 UI 추가
      - 추가: 처리 모드 선택 (배치/순차)
      - 추가: 동시 처리 수 설정 (2~8, 기본 4)
      - 기본값: 배치 처리 (순차 대비 ~75% 시간 절약)
      - 효과: 여러 이미지를 동시에 생성하여 처리 속도 대폭 향상
v2.2: 🔧 프로젝트-영상별 설정 저장/로드
      - 추가: utils/step1_settings.py 설정 관리자
      - 저장 항목: 생성 모델, 레퍼런스 이미지, 캐릭터 레퍼런스, 처리 모드, 동시 처리 수
      - 저장 경로: {video_path}/settings/step1_settings.json
      - 효과: 다음 접속 시 마지막 사용 설정이 기본값으로 적용
v2.4: 🔴 긴급 수정 - 씬 동기화 누락 문제 해결
      - 문제: 이미지 생성에서 102개 씬 선택 → 스토리보드 Step 1에서 96개만 표시 (6개 누락)
      - 원인: _create_bundles_from_existing_info()가 대표 씬 기준으로만 묶음 확장
      - 수정: 원본 korean_text_scene_ids 참조하여 모든 선택 씬의 묶음 확장
      - 추가: 누락 씬 검사 및 자동 개별 묶음 추가
      - 추가: _find_scene_display_image() 개선 - 씬 데이터 우선 확인, 더 많은 패턴 지원
v2.5: 🔴 긴급 수정 - 페이지네이션으로 인한 씬 67 이후 누락 문제
      - 문제: 101개 씬 → 34개 묶음 생성 → 15개 묶음만 처리 (45개 씬), 56개 씬 누락!
      - 원인: "전체 선택" 체크 시에도 현재 페이지(15개)의 체크박스만 selected에 추가
      - 수정: select_all=True일 때 모든 묶음/씬을 step1_all_selected_scene_ids_v16에 포함
      - 결과: 전체 선택 시 페이지와 무관하게 모든 묶음의 모든 씬 처리
"""

import streamlit as st
import time
import os
import re
from typing import Set, Dict, List, Optional, Tuple
from pathlib import Path
from collections import defaultdict

from .step_ui_base import StepUIBase
from .progress_visualizer import render_step_status_cards

# 이미지 생성 유틸리티
try:
    from utils.gemini_image_generator import GeminiImageGenerator, generate_images_parallel
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    generate_images_parallel = None
    print("[Step1] ⚠️ GeminiImageGenerator를 불러올 수 없습니다.")

# 레퍼런스 이미지 캐시
try:
    from utils.image_cache import preload_references, get_reference_cache_stats
    IMAGE_CACHE_AVAILABLE = True
except ImportError:
    IMAGE_CACHE_AVAILABLE = False
    preload_references = None
    get_reference_cache_stats = None

try:
    from components.nano_banana_composite import (
        get_scene_number,
        get_scene_prompts,
        get_scene_image_paths,
        update_scene_image_path
    )
    COMPOSITE_UTILS_AVAILABLE = True
except ImportError:
    COMPOSITE_UTILS_AVAILABLE = False
    print("[Step1] ⚠️ nano_banana_composite 유틸리티를 불러올 수 없습니다.")

# v2.2: Step1 설정 저장/로드
try:
    from utils.step1_settings import (
        load_step1_settings,
        save_step1_settings,
        set_step1_setting,
        get_step1_setting
    )
    STEP1_SETTINGS_AVAILABLE = True
except ImportError:
    STEP1_SETTINGS_AVAILABLE = False
    print("[Step1] ⚠️ step1_settings 유틸리티를 불러올 수 없습니다.")


class Step1KoreanTextUI(StepUIBase):
    """Step 1: 한글 텍스트 씬 대체"""

    def __init__(self, workflow_manager, project_path: Path):
        super().__init__(
            step_number=1,
            workflow_manager=workflow_manager,
            project_path=project_path
        )

    def get_pool(self) -> Set[int]:
        return self.manager.calculate_step1_pool()

    def get_assigned(self) -> Set[int]:
        return self.manager.state.step1_scenes

    def get_completed(self) -> Set[int]:
        return self.manager.state.completed_step1

    def render_step_content(
        self,
        scenes: List[Dict],
        pool: Set[int],
        assigned: Set[int],
        completed: Set[int]
    ) -> Optional[Dict]:
        """Step 1 콘텐츠 렌더링"""

        # v2.2: 저장된 설정 로드
        saved_settings = {}
        if STEP1_SETTINGS_AVAILABLE:
            saved_settings = load_step1_settings(str(self.project_path))

        # 설명
        st.info("""
            **🔤 Step 1: 한글 텍스트 씬**

            - **대상**: `image_prompt_korean_text` 필드가 있는 씬
            - **처리 단위**: 묶음 (Bundle) - 대표 씬만 생성, 나머지 복사
            - **프롬프트**: 한글 텍스트 전용 프롬프트 사용
        """)

        st.markdown("---")

        # 생성 설정 (v1.3: 나노바나나 합성과 동일한 UI)
        with st.expander("⚙️ 생성 설정", expanded=True):
            col1, col2 = st.columns(2)

            with col1:
                st.markdown("**레퍼런스 이미지**")

                # v2.2: 저장된 레퍼런스 설정 로드
                ref_options = ["기존 이미지 사용", "없음"]
                saved_ref = saved_settings.get("reference_image", "기존 이미지 사용")
                ref_default_idx = ref_options.index(saved_ref) if saved_ref in ref_options else 0

                use_reference = st.radio(
                    "레퍼런스 이미지",
                    ref_options,
                    index=ref_default_idx,
                    key="step1_reference",
                    horizontal=True,
                    label_visibility="collapsed"
                )

                # v2.2: 저장된 캐릭터 레퍼런스 설정 로드
                saved_char_ref = saved_settings.get("include_character_reference", True)
                include_char_ref = st.checkbox(
                    "캐릭터 이미지도 레퍼런스에 추가",
                    value=saved_char_ref,
                    key="step1_char_ref"
                )

            with col2:
                # v1.3: 모델 선택 UI - 나노바나나 합성과 동일
                # v2.2: 저장된 모델 설정 로드
                st.markdown("**생성 모델**")
                model_options = {
                    "gemini_nano_banana": "Nano Banana (빠름, ~15원/장)",
                    "gemini_nano_banana_pro": "Nano Banana Pro (고품질, ~25원/장)"
                }
                model_keys = list(model_options.keys())
                saved_model = saved_settings.get("generation_model", "gemini_nano_banana")
                model_default_idx = model_keys.index(saved_model) if saved_model in model_keys else 0

                selected_model = st.radio(
                    "모델",
                    options=model_keys,
                    index=model_default_idx,
                    format_func=lambda x: model_options[x],
                    key="step1_model",
                    horizontal=True,
                    label_visibility="collapsed"
                )

                prompt_type = st.selectbox(
                    "프롬프트 유형",
                    ["한글 텍스트 프롬프트 (image_prompt_korean_text)"],
                    key="step1_prompt_type"
                )

            # v2.0: 레퍼런스 강도 설정 제거 (원본 프롬프트 그대로 사용)
            # 배경/캐릭터 레퍼런스 이미지만 순서대로 전달 (강도 지시문 없음)

            st.markdown("---")

            # v2.1: 처리 모드 선택 UI
            # v2.2: 저장된 처리 모드 설정 로드
            st.markdown("**⚡ 처리 모드**")
            proc_col1, proc_col2 = st.columns([2, 1])

            proc_options = ["batch", "sequential"]
            saved_proc_mode = saved_settings.get("processing_mode", "batch")
            proc_default_idx = proc_options.index(saved_proc_mode) if saved_proc_mode in proc_options else 0

            with proc_col1:
                processing_mode = st.radio(
                    "처리 모드",
                    options=proc_options,
                    format_func=lambda x: "🚀 배치 처리 (빠름)" if x == "batch" else "📝 순차 처리 (안정)",
                    index=proc_default_idx,
                    horizontal=True,
                    key="step1_processing_mode",
                    help="배치 처리: 여러 이미지를 동시에 생성 (빠름)\n순차 처리: 하나씩 순서대로 생성 (안정)"
                )

            with proc_col2:
                if processing_mode == "batch":
                    saved_max_concurrent = saved_settings.get("max_concurrent", 4)
                    max_concurrent = st.number_input(
                        "동시 처리 수",
                        min_value=2,
                        max_value=8,
                        value=saved_max_concurrent,
                        key="step1_max_concurrent",
                        help="동시에 생성할 이미지 수 (2~8)\n높을수록 빠르지만 API 부하 증가"
                    )
                else:
                    max_concurrent = 1

            # 처리 모드 정보 표시
            if processing_mode == "batch":
                st.info(f"💡 **배치 모드**: {max_concurrent}개 이미지를 동시에 생성합니다. 순차 처리 대비 약 {(1 - 1/max_concurrent) * 100:.0f}% 빠릅니다.")
            else:
                st.info("💡 **순차 모드**: 안정적으로 하나씩 생성합니다. API 오류 시 재시도가 쉽습니다.")

        st.markdown("---")

        # ═══════════════════════════════════════════════════════════════
        # v2.3: 씬 선택 모드 UI (AI 분석 씬 / AI + 수동 추가)
        # ═══════════════════════════════════════════════════════════════
        st.markdown("#### 🔍 씬 선택 모드")

        # AI 선택 씬 수 표시
        ai_scene_count = len(pool)

        mode_col1, mode_col2 = st.columns([2, 3])

        with mode_col1:
            selection_mode = st.radio(
                "선택 모드",
                ["AI 분석 씬만", "AI + 수동 추가"],
                index=0,
                horizontal=True,
                key="step1_selection_mode",
                label_visibility="collapsed"
            )

        with mode_col2:
            st.info(f"🤖 AI 분석 씬: **{ai_scene_count}개**")

        # v2.3: 수동 선택 모드일 때 타임라인 뷰 표시
        manual_selected_scenes = set()
        manual_bundle_count = 0  # v3.0: 수동 선택 묶음 수

        if selection_mode == "AI + 수동 추가":
            manual_selected_scenes = self._render_manual_selection_timeline(scenes, pool)

            # v3.0: 수동 선택 묶음 수 계산 (AI와 겹치지 않는 것만)
            manual_bundle_ids = st.session_state.get('step1_manual_selected_bundles', set())
            # AI 풀의 묶음 ID 계산
            ai_bundle_ids = set()
            for scene in scenes:
                sid = scene.get('scene_id', scene.get('id', 0))
                if sid in pool:
                    ai_bundle_ids.add(scene.get('bundle_id', sid))
            # AI와 겹치지 않는 수동 묶음만 카운트
            manual_only_bundle_ids = manual_bundle_ids - ai_bundle_ids
            manual_bundle_count = len(manual_only_bundle_ids)

            manual_only = manual_selected_scenes - pool
            if manual_only:
                # v3.0: 묶음 단위로 표시 (개별 씬 아닌)
                st.success(f"✋ 수동 추가: **{manual_bundle_count}개 묶음** ({len(manual_only)}개 씬)")

        # v2.3: AI + 수동 선택 합산
        combined_pool = pool | manual_selected_scenes

        st.markdown("---")

        # 대상 씬 목록
        st.markdown("#### 📋 대상 묶음 목록")

        # v3.0: 최종 대상 묶음 단위 표시
        if combined_pool:
            # AI 묶음 수 계산
            ai_bundle_ids_in_pool = set()
            for scene in scenes:
                sid = scene.get('scene_id', scene.get('id', 0))
                if sid in pool:
                    ai_bundle_ids_in_pool.add(scene.get('bundle_id', sid))
            ai_bundle_count = len(ai_bundle_ids_in_pool)

            total_bundle_count = ai_bundle_count + manual_bundle_count  # 중복 제거됨
            final_scene_count = len(combined_pool)

            if manual_selected_scenes - pool:
                st.markdown(f"**최종 대상**: **{total_bundle_count}개 묶음** ({final_scene_count}개 씬) — AI {ai_bundle_count}개 + 수동 {manual_bundle_count}개 묶음")

        # v1.2: 빈 풀 처리 - 적용 상태에 따라 다른 메시지
        if not combined_pool:
            korean_text_applied = st.session_state.get('korean_text_scenes_applied', False)

            if not korean_text_applied:
                # 한글 텍스트 씬이 적용되지 않은 경우 안내
                st.warning("⚠️ 한글 텍스트 씬이 선택되지 않았습니다.")
                st.info("""
                    💡 **한글 텍스트 씬 적용 방법:**

                    **방법 1: AI 분석 씬 적용**
                    1. **[이미지 생성]** 탭으로 이동
                    2. **한글 텍스트 씬** 섹션에서 씬 선택 (AI 추천)
                    3. **"📋 스토리보드에 적용"** 버튼 클릭

                    **방법 2: 수동 추가 선택** (위 선택 모드에서)
                    1. **"AI + 수동 추가"** 선택
                    2. 타임라인 뷰에서 원하는 묶음 직접 선택
                """)
            else:
                # 적용되었지만 모두 처리된 경우
                st.success("✅ 한글 텍스트 씬이 모두 처리되었습니다.")

            return None

        # 씬 선택 (v2.3: combined_pool 사용)
        selected = self._render_bundle_selection(combined_pool, scenes)

        # 영향받는 씬 미리보기
        self.render_affected_scenes_preview(selected)

        # 실행 버튼
        def on_assign(ids):
            self.manager.assign_to_step(1, ids)
            self.manager.save()

        def on_execute(ids):
            # v1.8: 🔧 묶음 내 전체 씬 사용 (핵심 수정!)
            # 기존: get_scenes_affected_by_selection이 대표 씬만 반환 → 모든 씬에 API 호출 (낭비!)
            # 수정: session_state에 저장된 전체 씬 사용 → 대표 씬만 API, 나머지 복사
            all_scene_ids = st.session_state.get("step1_all_selected_scene_ids_v16", set())

            if all_scene_ids:
                scene_ids_to_generate = sorted(all_scene_ids)
                print(f"[Step1] ✅ v1.8: 묶음 전체 씬 사용 - {len(scene_ids_to_generate)}개 씬")
            else:
                # 폴백: 기존 방식 (묶음 정보 없는 경우)
                affected = self.manager.get_scenes_affected_by_selection(ids, 1)
                scene_ids_to_generate = sorted(affected['total'])
                print(f"[Step1] ⚠️ v1.8: 폴백 사용 - {len(scene_ids_to_generate)}개 씬")

            # v2.1: 처리 모드 및 동시 처리 수 추가
            settings = {
                "use_reference": use_reference == "기존 이미지 사용",
                "include_char_ref": include_char_ref,
                "model_key": selected_model,  # v1.3: gemini_nano_banana 또는 gemini_nano_banana_pro
                "prompt_field": "image_prompt_korean_text",
                "processing_mode": processing_mode,  # v2.1: "batch" 또는 "sequential"
                "max_concurrent": max_concurrent  # v2.1: 동시 처리 수 (2~8)
            }

            # v2.2: 설정 저장 (생성 실행 시)
            if STEP1_SETTINGS_AVAILABLE:
                save_settings = {
                    "generation_model": selected_model,
                    "reference_image": use_reference,
                    "include_character_reference": include_char_ref,
                    "processing_mode": processing_mode,
                    "max_concurrent": max_concurrent
                }
                save_step1_settings(str(self.project_path), save_settings)
                print(f"[Step1] ✅ 설정 저장됨: 모델={selected_model}")

            # 실제 이미지 생성 실행
            result = self._execute_korean_text_generation(
                scene_ids=scene_ids_to_generate,
                scenes=scenes,
                settings=settings
            )

            return result

        return self.render_execution_buttons(
            selected,
            on_assign=on_assign,
            on_execute=on_execute,
            execute_label="한글 텍스트 이미지 생성"
        )

    def _execute_korean_text_generation(
        self,
        scene_ids: List[int],
        scenes: List[Dict],
        settings: Dict
    ) -> Dict:
        """
        한글 텍스트 이미지 생성 실행 (v2.0 - 병렬 처리 최적화)

        v2.0 변경사항:
        - 병렬 처리: generate_images_parallel() 사용
        - 레퍼런스 이미지 프리로드 (캐시 활용)
        - 묶음 내 첫 번째 씬만 API 호출, 나머지 씬은 이미지 복사

        Args:
            scene_ids: 생성할 씬 ID 목록
            scenes: 전체 씬 데이터
            settings: 생성 설정

        Returns:
            {'success': [], 'failed': [], 'skipped': [], 'copied': [], 'generated': []}
        """
        import shutil

        results = {
            'success': [],
            'failed': [],
            'skipped': [],
            'copied': [],      # 복사된 씬 (API 절약)
            'generated': []    # API 호출로 생성된 씬
        }

        if not scene_ids:
            st.warning("생성할 씬이 없습니다.")
            return results

        # 유틸리티 확인
        if not GEMINI_AVAILABLE:
            st.error("❌ GeminiImageGenerator를 사용할 수 없습니다.")
            return results

        # 씬 맵 생성
        scene_map = {}
        for s in scenes:
            sid = s.get('scene_id', s.get('id', 0))
            if sid:
                scene_map[sid] = s

        project_path = str(self.project_path)

        # ═══════════════════════════════════════════════════════════════════════
        # v1.7: 🔧 묶음 로직 수정 - bundle_mode에 따라 다른 방식 사용
        # session_state에서 묶음 정보 가져오기
        # ═══════════════════════════════════════════════════════════════════════
        scenes_to_generate = []  # API 호출 대상 (묶음 대표 씬)
        scenes_to_copy = []      # 복사 대상 [{scene_id, source_scene_id}, ...]

        # v1.7: 묶음 정보 가져오기
        selected_bundles = st.session_state.get("step1_selected_bundles_v16", [])

        if not selected_bundles:
            # 묶음 정보 없으면 bundle_mode에 따라 생성
            bundle_mode = st.session_state.get("step1_bundle_mode", "기존 묶음 사용")

            if bundle_mode == "기존 묶음 사용":
                # v1.7: 기존 bundle_id 참조
                selected_bundles = self._create_bundles_from_existing_info(set(scene_ids), scenes)
                print(f"[Step1] ⚠️ session_state에 묶음 정보 없음, 기존 bundle_id 기반 생성: {len(selected_bundles)}개 묶음")
            else:
                # 단순 분할 방식
                bundle_size = st.session_state.get("step1_bundle_size", 3)
                selected_bundles = self._create_simple_bundles(set(scene_ids), bundle_size)
                print(f"[Step1] ⚠️ session_state에 묶음 정보 없음, 새로 생성: {len(selected_bundles)}개 묶음")

        # 묶음 역맵 구축 (scene_id → bundle_info)
        scene_to_bundle = {}
        for bundle in selected_bundles:
            bundle_id = bundle["bundle_id"]
            representative_id = bundle["representative_id"]
            for sid in bundle["scene_ids"]:
                scene_to_bundle[sid] = {
                    "bundle_id": bundle_id,
                    "representative_id": representative_id,
                    "scene_ids": bundle["scene_ids"]
                }

        # 처리된 묶음 추적
        processed_bundles = {}  # bundle_id → representative_scene_id

        for scene_id in scene_ids:
            bundle_info = scene_to_bundle.get(scene_id)

            if bundle_info is None:
                # 묶음에 속하지 않는 단독 씬 → 직접 생성
                scenes_to_generate.append(scene_id)
            else:
                bundle_id = bundle_info["bundle_id"]
                representative_id = bundle_info["representative_id"]

                if bundle_id not in processed_bundles:
                    # 이 묶음의 첫 번째 처리 → 대표 씬(첫 번째 씬) 생성
                    scenes_to_generate.append(representative_id)
                    processed_bundles[bundle_id] = representative_id
                elif scene_id != processed_bundles[bundle_id]:
                    # 이미 처리된 묶음의 다른 씬 → 복사 대상
                    source_scene_id = processed_bundles[bundle_id]
                    scenes_to_copy.append({
                        'scene_id': scene_id,
                        'source_scene_id': source_scene_id,
                        'bundle_id': bundle_id
                    })

        # 총 작업 수
        total_generate = len(scenes_to_generate)
        total_copy = len(scenes_to_copy)
        total = total_generate + total_copy

        print(f"\n[Step1] ═══════════════════════════════════════════════════════")
        print(f"[Step1] 📋 묶음 최적화 분석 완료")
        print(f"[Step1] 선택된 전체 씬: {len(scene_ids)}개")
        print(f"[Step1] API 생성 대상 (묶음 대표): {total_generate}개 → {scenes_to_generate}")
        print(f"[Step1] 복사 대상: {total_copy}개")
        for copy_info in scenes_to_copy:
            print(f"[Step1]    씬 {copy_info['scene_id']} ← 씬 {copy_info['source_scene_id']} (묶음 {copy_info['bundle_id']})")
        print(f"[Step1] 💰 API 절약: {total_copy}회")
        print(f"[Step1] ═══════════════════════════════════════════════════════\n")

        st.markdown("### 🔤 한글 텍스트 이미지 생성")

        # 묶음 최적화 정보 표시
        if total_copy > 0:
            st.info(f"""
                **📦 묶음 최적화 적용**
                - API 생성: **{total_generate}개** 씬 (묶음 대표만)
                - 이미지 복사: **{total_copy}개** 씬 (같은 묶음 내)
                - 💰 API 절약: **{total_copy}회**
            """)

        # UI 요소
        progress_bar = st.progress(0)
        status_text = st.empty()
        workflow_container = st.container()
        current_image_container = st.empty()
        result_container = st.container()

        try:
            # v2.0: 레퍼런스 강도 제거 - 모델 키만 가져오기
            model_key = settings.get('model_key', 'gemini_nano_banana')

            print(f"[Step1] 🎯 선택된 모델: {model_key}")
            print(f"[Step1] 📷 레퍼런스 사용: {settings.get('use_reference', True)}")
            print(f"[Step1] 👤 캐릭터 레퍼런스 포함: {settings.get('include_char_ref', True)}")

            # 출력 폴더 생성
            output_dir = Path(project_path) / "images" / "korean_text"
            output_dir.mkdir(parents=True, exist_ok=True)

            # 생성된 이미지 경로 저장 (복사용)
            generated_images = {}  # scene_id → output_path

            # ═══════════════════════════════════════════════════════════════════
            # v2.0: 병렬 처리를 위한 요청 준비
            # ═══════════════════════════════════════════════════════════════════
            st.markdown("#### 🎨 1단계: API 이미지 생성 (묶음 대표 씬)")

            # 요청 목록 준비
            api_requests = []
            request_meta = {}  # scene_id → {output_path, korean_prompt, ref_bg_path, ref_char_path}

            for scene_id in scenes_to_generate:
                # 씬 데이터 찾기
                scene = scene_map.get(scene_id)
                if not scene:
                    results['skipped'].append({'scene': scene_id, 'reason': '씬 데이터 없음'})
                    print(f"[Step1] ⏭️ 씬 {scene_id} 스킵: 씬 데이터 없음")
                    continue

                # 한글 텍스트 프롬프트 가져오기
                korean_prompt = scene.get('image_prompt_korean_text', '')
                if not korean_prompt:
                    prompts = scene.get('prompts', {})
                    korean_prompt = prompts.get('image_prompt_korean_text', '')

                if not korean_prompt:
                    results['skipped'].append({'scene': scene_id, 'reason': 'image_prompt_korean_text 없음'})
                    print(f"[Step1] ⏭️ 씬 {scene_id} 스킵: 한글 텍스트 프롬프트 없음")
                    continue

                # 레퍼런스 이미지 수집
                reference_images = []
                ref_bg_path = None
                ref_char_path = None

                if settings.get('use_reference', True) and COMPOSITE_UTILS_AVAILABLE:
                    try:
                        paths = get_scene_image_paths(scene, project_path)

                        # 배경 이미지
                        ref_bg_path = paths.get("background")
                        if ref_bg_path and os.path.exists(ref_bg_path):
                            reference_images.append(ref_bg_path)

                        # 캐릭터 이미지 (옵션)
                        if settings.get('include_char_ref', True):
                            ref_char_path = paths.get("character")
                            if ref_char_path and os.path.exists(ref_char_path):
                                reference_images.append(ref_char_path)

                    except Exception as e:
                        print(f"[Step1] ⚠️ 레퍼런스 이미지 로드 실패: {e}")

                # v2.0: 프롬프트 원본 그대로 사용 (강도 지시문 제거)
                # 레퍼런스 이미지만 순서대로 전달 (배경→첫번째, 캐릭터→두번째)

                # 출력 경로 생성
                timestamp = int(time.time() * 1000)
                output_path = str(output_dir / f"korean_text_scene_{scene_id:03d}_{timestamp}.png")

                # 요청 추가 (원본 프롬프트, 레퍼런스 강도 제거)
                api_requests.append({
                    "scene_id": scene_id,
                    "prompt": korean_prompt,  # 원본 프롬프트 그대로 사용
                    "reference_images": reference_images,
                    "reference_type": "style",
                    "aspect_ratio": "16:9"
                })

                # 메타 정보 저장
                request_meta[scene_id] = {
                    "output_path": output_path,
                    "korean_prompt": korean_prompt,
                    "ref_bg_path": ref_bg_path,
                    "ref_char_path": ref_char_path,
                    "scene": scene
                }

            # ═══════════════════════════════════════════════════════════════════
            # v2.0: 레퍼런스 이미지 프리로드 (캐시 최적화)
            # ═══════════════════════════════════════════════════════════════════
            if IMAGE_CACHE_AVAILABLE and api_requests:
                all_refs = []
                for req in api_requests:
                    all_refs.extend(req.get("reference_images", []))
                if all_refs:
                    status_text.markdown(f"**📦 레퍼런스 이미지 프리로드 중... ({len(set(all_refs))}개)**")
                    preload_references(list(set(all_refs)))

            # ═══════════════════════════════════════════════════════════════════
            # v2.1: 배치/순차 처리 선택 (사용자 설정 반영)
            # ═══════════════════════════════════════════════════════════════════
            if api_requests:
                # v2.1: 사용자 설정에서 처리 모드 및 동시 처리 수 가져오기
                processing_mode = settings.get('processing_mode', 'batch')
                max_concurrent = settings.get('max_concurrent', 4)

                # 배치 처리 가능 여부 체크 (병렬 함수 존재 + 배치 모드 선택 + 2개 이상 요청)
                use_parallel = (
                    generate_images_parallel is not None and
                    processing_mode == "batch" and
                    len(api_requests) > 1
                )

                print(f"[Step1] ⚡ 처리 모드: {processing_mode}, 동시 처리: {max_concurrent}개, 병렬 사용: {use_parallel}")

                if use_parallel:
                    # 🚀 병렬 처리
                    status_text.markdown(f"**🚀 병렬 이미지 생성 중... ({len(api_requests)}개 씬, 동시 {max_concurrent}개)**")

                    # 워크플로우 정보 한번에 표시
                    with workflow_container:
                        with st.expander(f"📋 병렬 처리 대상 씬 ({len(api_requests)}개)", expanded=False):
                            for req in api_requests:
                                scene_id = req["scene_id"]
                                meta = request_meta[scene_id]
                                st.caption(f"씬 {scene_id}: {meta['korean_prompt'][:60]}...")

                    # 병렬 생성 실행
                    parallel_results = generate_images_parallel(
                        requests=api_requests,
                        max_concurrent=max_concurrent,
                        model_key=model_key
                    )

                    # 결과 처리
                    for idx, res in enumerate(parallel_results):
                        scene_id = res.get("scene_id", 0)
                        meta = request_meta.get(scene_id, {})
                        output_path = meta.get("output_path", "")

                        progress = (idx + 1) / total
                        progress_bar.progress(progress)

                        if res.get("success") and res.get("image_data"):
                            # 이미지 저장
                            with open(output_path, 'wb') as f:
                                f.write(res["image_data"])

                            # 생성된 이미지 경로 저장 (복사용)
                            generated_images[scene_id] = output_path
                            print(f"[Step1] ✅ 씬 {scene_id} 생성 완료 → generated_images 등록 ({len(generated_images)}개)")

                            # 씬 데이터 업데이트
                            scene = meta.get("scene")
                            if scene and COMPOSITE_UTILS_AVAILABLE:
                                try:
                                    update_scene_image_path(
                                        scene, "composite", output_path, scenes, project_path,
                                        {"type": "korean_text", "prompt": meta.get("korean_prompt", "")[:200]}
                                    )
                                except Exception as e:
                                    print(f"[Step1] ⚠️ 씬 데이터 업데이트 실패: {e}")

                            # 워크플로우 상태 업데이트
                            self.manager.mark_completed(1, {scene_id})

                            results['success'].append(scene_id)
                            results['generated'].append({
                                'scene_id': scene_id,
                                'image_path': output_path,
                                'prompt': meta.get("korean_prompt", ""),
                                'ref_background': meta.get("ref_bg_path"),
                                'ref_character': meta.get("ref_char_path"),
                                'type': 'generated',
                                'elapsed_time': res.get("elapsed_time", 0)
                            })

                            status_text.markdown(f"**✅ 씬 {scene_id} 완료 ({res.get('elapsed_time', 0):.1f}초) [{idx + 1}/{len(api_requests)}]**")
                            current_image_container.image(output_path, caption=f"씬 {scene_id} 생성 완료", width=400)
                        else:
                            error = res.get("error") or "알 수 없는 오류"
                            results['failed'].append({'scene': scene_id, 'reason': error})
                            print(f"[Step1] ❌ 씬 {scene_id} 실패: {error}")

                else:
                    # 🐢 순차 처리 (폴백)
                    generator = GeminiImageGenerator()

                    for idx, req in enumerate(api_requests):
                        scene_id = req["scene_id"]
                        meta = request_meta[scene_id]

                        progress = (idx + 1) / total
                        progress_bar.progress(progress)
                        status_text.markdown(f"**🎨 씬 {scene_id} 생성 중... (순차 처리 {idx + 1}/{len(api_requests)})**")

                        # 워크플로우 정보 표시
                        with workflow_container:
                            self._render_workflow_info(
                                scene_id=scene_id,
                                ref_bg_path=meta.get("ref_bg_path"),
                                ref_char_path=meta.get("ref_char_path"),
                                prompt=meta.get("korean_prompt", "")
                            )

                        try:
                            result = generator.generate_image(
                                prompt=req["prompt"],
                                model_key=model_key,
                                reference_images=req.get("reference_images", []),
                                reference_type=req.get("reference_type", "style"),
                                reference_strength=req.get("reference_strength", 0.7),
                                aspect_ratio=req.get("aspect_ratio", "16:9")
                            )

                            if result.success and result.image_data:
                                output_path = meta["output_path"]

                                with open(output_path, 'wb') as f:
                                    f.write(result.image_data)

                                generated_images[scene_id] = output_path
                                print(f"[Step1] ✅ 씬 {scene_id} 생성 완료 → generated_images 등록 ({len(generated_images)}개)")

                                scene = meta.get("scene")
                                if scene and COMPOSITE_UTILS_AVAILABLE:
                                    try:
                                        update_scene_image_path(
                                            scene, "composite", output_path, scenes, project_path,
                                            {"type": "korean_text", "prompt": meta.get("korean_prompt", "")[:200]}
                                        )
                                    except Exception as e:
                                        print(f"[Step1] ⚠️ 씬 데이터 업데이트 실패: {e}")

                                self.manager.mark_completed(1, {scene_id})

                                results['success'].append(scene_id)
                                results['generated'].append({
                                    'scene_id': scene_id,
                                    'image_path': output_path,
                                    'prompt': meta.get("korean_prompt", ""),
                                    'ref_background': meta.get("ref_bg_path"),
                                    'ref_character': meta.get("ref_char_path"),
                                    'type': 'generated'
                                })

                                current_image_container.image(output_path, caption=f"씬 {scene_id} 생성 완료", width=400)
                            else:
                                error = result.error or "알 수 없는 오류"
                                results['failed'].append({'scene': scene_id, 'reason': error})

                        except Exception as e:
                            results['failed'].append({'scene': scene_id, 'reason': str(e)})
                            print(f"[Step1] ❌ 씬 {scene_id} 에러: {e}")

                        # API 레이트 리밋 방지
                        if idx < len(api_requests) - 1:
                            time.sleep(0.5)

            # ═══════════════════════════════════════════════════════════════════
            # 2단계: 묶음 내 다른 씬에 이미지 복사
            # ═══════════════════════════════════════════════════════════════════
            if scenes_to_copy:
                st.markdown("#### 📋 2단계: 이미지 복사 (같은 묶음 내)")
                print(f"[Step1] 📋 복사 시작: {len(scenes_to_copy)}개, 원본 이미지 보유: {sorted(generated_images.keys())}")

                for idx, copy_info in enumerate(scenes_to_copy):
                    scene_id = copy_info['scene_id']
                    source_scene_id = copy_info['source_scene_id']
                    bundle_id = copy_info['bundle_id']

                    # 진행 상황 업데이트
                    progress = (total_generate + idx + 1) / total
                    progress_bar.progress(progress)
                    status_text.markdown(f"**📋 씬 {scene_id} 복사 중... (씬 {source_scene_id}에서 복사)**")

                    # 원본 이미지 경로
                    source_image_path = generated_images.get(source_scene_id)

                    if source_image_path and os.path.exists(source_image_path):
                        try:
                            # 복사본 생성
                            timestamp = int(time.time() * 1000)
                            output_path = str(output_dir / f"korean_text_scene_{scene_id:03d}_{timestamp}.png")

                            shutil.copy2(source_image_path, output_path)

                            # 씬 데이터 업데이트
                            scene = scene_map.get(scene_id)
                            if scene and COMPOSITE_UTILS_AVAILABLE:
                                try:
                                    update_scene_image_path(
                                        scene, "composite", output_path, scenes, project_path,
                                        {"type": "korean_text_copy", "source_scene": source_scene_id}
                                    )
                                except Exception as e:
                                    print(f"[Step1] ⚠️ 씬 {scene_id} 데이터 업데이트 실패: {e}")

                            # 워크플로우 상태 업데이트
                            self.manager.mark_completed(1, {scene_id})

                            results['success'].append(scene_id)
                            results['copied'].append({
                                'scene_id': scene_id,
                                'source_scene_id': source_scene_id,
                                'image_path': output_path,
                                'source_image_path': source_image_path,
                                'bundle_id': bundle_id,
                                'type': 'copied'
                            })

                            print(f"[Step1] 📋 씬 {scene_id}: 씬 {source_scene_id} 이미지 복사됨")
                            print(f"[Step1]    원본: {source_image_path}")
                            print(f"[Step1]    복사: {output_path}")

                        except Exception as e:
                            results['failed'].append({'scene': scene_id, 'reason': f'복사 실패: {e}'})
                            print(f"[Step1] ❌ 씬 {scene_id} 복사 실패: {e}")
                    else:
                        # ⭐ v2.5: 복사 실패 시 직접 생성으로 fallback
                        print(f"[Step1] ⚠️ 씬 {scene_id} 복사 실패 (원본 씬 {source_scene_id} 이미지 없음) → 직접 생성 시도")
                        fallback_done = False

                        scene = scene_map.get(scene_id)
                        if scene and GEMINI_AVAILABLE:
                            korean_prompt = scene.get('image_prompt_korean_text', '')
                            if korean_prompt:
                                try:
                                    generator = GeminiImageGenerator()
                                    result_single = generator.generate_image(
                                        prompt=korean_prompt,
                                        model_key=model_key,
                                        reference_images=[],
                                        reference_type="style",
                                        aspect_ratio="16:9"
                                    )
                                    if result_single.success and result_single.image_data:
                                        timestamp = int(time.time() * 1000)
                                        fallback_path = str(output_dir / f"korean_text_scene_{scene_id:03d}_{timestamp}.png")
                                        with open(fallback_path, 'wb') as f:
                                            f.write(result_single.image_data)

                                        generated_images[scene_id] = fallback_path

                                        if COMPOSITE_UTILS_AVAILABLE:
                                            try:
                                                update_scene_image_path(
                                                    scene, "composite", fallback_path, scenes, project_path,
                                                    {"type": "korean_text_fallback", "source_scene": source_scene_id}
                                                )
                                            except Exception as e:
                                                print(f"[Step1] ⚠️ 씬 {scene_id} 데이터 업데이트 실패: {e}")

                                        self.manager.mark_completed(1, {scene_id})
                                        results['success'].append(scene_id)
                                        results['generated'].append({
                                            'scene_id': scene_id,
                                            'image_path': fallback_path,
                                            'type': 'fallback_generated'
                                        })
                                        fallback_done = True
                                        print(f"[Step1] ✅ 씬 {scene_id} fallback 생성 완료: {fallback_path}")
                                except Exception as e:
                                    print(f"[Step1] ❌ 씬 {scene_id} fallback 생성 실패: {e}")

                        if not fallback_done:
                            results['failed'].append({
                                'scene': scene_id,
                                'reason': f'원본 이미지 없음 (씬 {source_scene_id}), fallback 생성도 실패'
                            })
                            print(f"[Step1] ❌ 씬 {scene_id} 최종 실패: 복사 불가, fallback 불가")

            # 완료
            progress_bar.progress(1.0)
            status_text.markdown("**✅ 한글 텍스트 이미지 생성 완료!**")
            current_image_container.empty()

            # 워크플로우 상태 저장
            self.manager.save()

            # ═══════════════════════════════════════════════════════════════════
            # 결과 요약 표시
            # ═══════════════════════════════════════════════════════════════════
            with result_container:
                self._render_generation_results(results)

        except Exception as e:
            st.error(f"❌ 이미지 생성 중 오류 발생: {e}")
            import traceback
            st.code(traceback.format_exc())
            print(f"[Step1] ❌ 생성 오류: {e}")

        return results

    def _render_workflow_info(
        self,
        scene_id: int,
        ref_bg_path: Optional[str],
        ref_char_path: Optional[str],
        prompt: str
    ):
        """워크플로우 정보 표시 (레퍼런스 이미지 + 프롬프트) v1.3: 기본 펼침"""
        with st.expander(f"📋 씬 {scene_id} 워크플로우 정보", expanded=True):  # v1.3: expanded=True
            cols = st.columns([1, 1, 2])

            with cols[0]:
                st.markdown("**📷 배경 레퍼런스**")
                if ref_bg_path and os.path.exists(ref_bg_path):
                    st.image(ref_bg_path, width=150)
                    st.caption(os.path.basename(ref_bg_path))
                else:
                    st.info("배경 이미지 없음")

            with cols[1]:
                st.markdown("**👤 캐릭터 레퍼런스**")
                if ref_char_path and os.path.exists(ref_char_path):
                    st.image(ref_char_path, width=150)
                    st.caption(os.path.basename(ref_char_path))
                else:
                    st.info("캐릭터 이미지 없음")

            with cols[2]:
                st.markdown("**📝 한글 텍스트 프롬프트**")
                st.text_area(
                    "프롬프트",
                    prompt,
                    height=120,
                    key=f"workflow_prompt_{scene_id}",
                    disabled=True,
                    label_visibility="collapsed"
                )

    def _build_prompt_with_separate_strengths(
        self,
        base_prompt: str,
        has_bg: bool,
        has_char: bool,
        bg_strength: float,
        char_strength: float
    ) -> str:
        """
        배경/캐릭터 개별 레퍼런스 강도를 반영한 프롬프트 구성 (v1.5)

        Args:
            base_prompt: 기본 프롬프트
            has_bg: 배경 레퍼런스 이미지 유무
            has_char: 캐릭터 레퍼런스 이미지 유무
            bg_strength: 배경 레퍼런스 강도 (0.0~1.0)
            char_strength: 캐릭터 레퍼런스 강도 (0.0~1.0)

        Returns:
            개별 강도 힌트가 포함된 프롬프트
        """
        hints = []

        # 배경 강도 힌트
        if has_bg:
            if bg_strength >= 0.8:
                hints.append(f"배경 스타일(색감, 구도, 분위기)을 매우 강하게({int(bg_strength * 100)}%) 유지하고")
            elif bg_strength >= 0.5:
                hints.append(f"배경 분위기를 적당히({int(bg_strength * 100)}%) 반영하고")
            elif bg_strength > 0:
                hints.append(f"배경 스타일을 약간({int(bg_strength * 100)}%)만 참고하고")
            # 0이면 힌트 없음

        # 캐릭터 강도 힌트
        if has_char:
            if char_strength >= 0.8:
                hints.append(f"캐릭터 외모와 특징을 매우 정확하게({int(char_strength * 100)}%) 재현하세요")
            elif char_strength >= 0.5:
                hints.append(f"캐릭터의 일반적인 특성을 적당히({int(char_strength * 100)}%) 반영하세요")
            elif char_strength > 0:
                hints.append(f"캐릭터를 자유롭게 해석하되 약간({int(char_strength * 100)}%)만 참고하세요")
            # 0이면 힌트 없음

        if hints:
            hint_text = ", ".join(hints)
            return f"{hint_text}. {base_prompt}"

        return base_prompt

    def _render_generation_results(self, results: Dict):
        """생성 결과 상세 표시"""
        st.markdown("### 📊 결과 요약")

        generated = results.get('generated', [])
        copied = results.get('copied', [])
        failed = results.get('failed', [])
        skipped = results.get('skipped', [])

        # 통계 카드
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            st.metric("✅ 성공", len(results['success']))
        with col2:
            st.metric("🎨 API 생성", len(generated))
        with col3:
            st.metric("📋 복사", len(copied))
        with col4:
            st.metric("❌ 실패", len(failed))
        with col5:
            api_saved = len(copied)
            st.metric("💰 API 절약", f"{api_saved}회")

        # 상세 정보 - API 생성된 씬
        if generated:
            with st.expander(f"🎨 API로 생성된 씬 ({len(generated)}개)", expanded=True):
                for item in generated:
                    scene_id = item['scene_id']
                    cols = st.columns([1, 1, 1, 2])

                    with cols[0]:
                        if item.get('ref_background') and os.path.exists(item['ref_background']):
                            st.image(item['ref_background'], caption="배경", width=80)
                        else:
                            st.caption("배경 없음")

                    with cols[1]:
                        if item.get('ref_character') and os.path.exists(item['ref_character']):
                            st.image(item['ref_character'], caption="캐릭터", width=80)
                        else:
                            st.caption("캐릭터 없음")

                    with cols[2]:
                        if item.get('image_path') and os.path.exists(item['image_path']):
                            st.image(item['image_path'], caption=f"씬 {scene_id}", width=100)

                    with cols[3]:
                        prompt = item.get('prompt', '')
                        st.markdown(f"**씬 {scene_id}** (API 생성)")
                        st.caption(prompt[:150] + "..." if len(prompt) > 150 else prompt)

                    st.divider()

        # 상세 정보 - 복사된 씬
        if copied:
            with st.expander(f"📋 복사된 씬 ({len(copied)}개) - 💰 API 절약!", expanded=False):
                for item in copied:
                    scene_id = item['scene_id']
                    source_id = item['source_scene_id']
                    bundle_id = item['bundle_id']

                    cols = st.columns([1, 1, 2])

                    with cols[0]:
                        if item.get('source_image_path') and os.path.exists(item['source_image_path']):
                            st.image(item['source_image_path'], caption=f"원본 (씬 {source_id})", width=120)

                    with cols[1]:
                        if item.get('image_path') and os.path.exists(item['image_path']):
                            st.image(item['image_path'], caption=f"복사본 (씬 {scene_id})", width=120)

                    with cols[2]:
                        st.markdown(f"**씬 {scene_id}** ← 씬 {source_id}")
                        st.caption(f"묶음 {bundle_id} | 이미지 복사로 API 1회 절약")

                    st.divider()

        # 실패/스킵 정보
        if failed:
            with st.expander(f"❌ 실패한 씬 ({len(failed)}개)", expanded=False):
                for item in failed:
                    st.error(f"씬 {item['scene']}: {item.get('reason', '알 수 없는 오류')}")

        if skipped:
            with st.expander(f"⏭️ 스킵된 씬 ({len(skipped)}개)", expanded=False):
                for item in skipped:
                    st.warning(f"씬 {item['scene']}: {item.get('reason', '알 수 없는 이유')}")

    def _get_korean_text_scene_ids_from_session(self, scenes: List[Dict]) -> Set[int]:
        """session_state에서 한글 텍스트 씬 ID 가져오기"""
        korean_scene_ids = set()

        # 가능한 모든 키 확인
        possible_keys = [
            'korean_text_scene_ids',
            'ai_recommended_korean_text_scenes',
            'selected_korean_text_scenes',
            'korean_text_scenes'
        ]

        for key in possible_keys:
            if key in st.session_state:
                value = st.session_state[key]
                if isinstance(value, (list, set, tuple)):
                    korean_scene_ids.update(int(v) if isinstance(v, (int, str)) and str(v).isdigit() else v for v in value)
                elif isinstance(value, dict):
                    korean_scene_ids.update(int(k) for k, v in value.items() if v)

        if korean_scene_ids:
            print(f"[Step1] session_state에서 한글 씬 ID 로드: {sorted(korean_scene_ids)}")

        return korean_scene_ids

    def _create_simple_bundles(self, scene_ids: Set[int], bundle_size: int = 3) -> List[Dict]:
        """
        선택된 씬들을 단순 분할하여 새 묶음 생성 (v1.6 핵심 수정!)

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
        print(f"\n[Step1] ========== 🆕 새 묶음 생성 결과 (v1.6) ==========")
        print(f"[Step1] 선택된 씬: {len(sorted_ids)}개 → {sorted_ids}")
        print(f"[Step1] 묶음 크기: {bundle_size}개/묶음")
        print(f"[Step1] 생성된 묶음: {len(bundles)}개")

        for b in bundles:
            print(f"[Step1] ✅ 묶음 {b['bundle_id']}: {b['scene_range']} ({len(b['scene_ids'])}개)")

        print(f"[Step1] =====================================================\n")

        return bundles

    def _get_bundle_info_from_scenes(self, scenes: List[Dict]) -> Dict[int, Dict]:
        """
        scenes.json에서 기존 묶음 정보 추출 (v1.7)

        Returns:
            scene_id → {"bundle_id": int, "bundle_size": int, "original_index": int}
        """
        scene_to_bundle = {}

        for idx, scene in enumerate(scenes):
            scene_id = scene.get('scene_id', scene.get('id', 0))
            if not scene_id:
                continue

            bundle_id = scene.get('bundle_id')
            bundle_size = scene.get('bundle_size', 2)  # 기본값 2

            if bundle_id is not None:
                scene_to_bundle[scene_id] = {
                    "bundle_id": bundle_id,
                    "bundle_size": bundle_size,
                    "original_index": idx
                }

        if scene_to_bundle:
            unique_bundles = len(set(info["bundle_id"] for info in scene_to_bundle.values()))
            print(f"[Step1] 📋 기존 묶음 정보: {len(scene_to_bundle)}개 씬 → {unique_bundles}개 묶음")

        return scene_to_bundle

    def _create_bundles_from_existing_info(
        self,
        selected_scene_ids: Set[int],
        scenes: List[Dict]
    ) -> List[Dict]:
        """
        기존 bundle_id를 참조하여 선택된 씬들을 묶음으로 그룹화 (v2.4 핵심!)

        Args:
            selected_scene_ids: 선택된 씬 ID 집합 (대표 씬만 포함될 수 있음)
            scenes: 전체 씬 데이터 (bundle_id 포함)

        Returns:
            묶음 리스트 [{"bundle_id": 1, "scene_ids": [49, 50], "representative_id": 49}, ...]

        v2.4 변경사항:
            - 🔧 원본 korean_text_scene_ids 기반으로 묶음 확장
            - 선택된 씬이 속한 묶음의 전체 씬 포함
            - session_state에서 원본 선택 목록 참조하여 누락 방지
        """
        import streamlit as st

        if not selected_scene_ids:
            return []

        # v2.9: session_state 캐싱 (인포그래픽 탭 등 다른 탭 조작 시 불필요한 재계산 방지)
        ai_ids_for_hash = tuple(sorted(st.session_state.get('korean_text_scene_ids', [])))
        input_hash = hash((
            tuple(sorted(selected_scene_ids)),
            ai_ids_for_hash,
            len(scenes)
        ))
        cache_key = f'_step1_bundles_cache_{input_hash}'
        if cache_key in st.session_state:
            return st.session_state[cache_key]

        # v2.7: 🔧 수동 추가 씬 포함 - selected_scene_ids를 기본으로 사용
        # 기존 버그: session_state의 korean_text_scene_ids는 AI 분석 씬만 포함
        # 수정: 전달받은 selected_scene_ids (combined_pool = AI + 수동 추가)를 기본으로 사용
        ai_korean_ids = set(st.session_state.get('korean_text_scene_ids', []))

        # v2.7: selected_scene_ids가 더 크거나 같으면 그것을 사용 (수동 추가 포함)
        if len(selected_scene_ids) >= len(ai_korean_ids):
            original_korean_ids = selected_scene_ids
            manual_count = len(selected_scene_ids) - len(ai_korean_ids & selected_scene_ids)
            if manual_count > 0:
                print(f"[Step1] v2.7: selected_scene_ids 사용 (AI {len(ai_korean_ids)}개 + 수동 ~{manual_count}개 = {len(selected_scene_ids)}개)")
            else:
                print(f"[Step1] v2.7: selected_scene_ids 사용: {len(selected_scene_ids)}개")
        else:
            original_korean_ids = ai_korean_ids | selected_scene_ids
            print(f"[Step1] v2.7: AI + selected 합산: {len(original_korean_ids)}개")

        # 1. 기존 묶음 정보 추출 (scene_id → bundle_info)
        scene_to_bundle = self._get_bundle_info_from_scenes(scenes)

        # v2.4: 🔧 핵심 수정 - bundle_id → [all scene_ids] 맵 생성 (전체 씬 기준)
        # 모든 씬을 순회하여 동일 bundle_id의 전체 씬 목록 구축
        bundle_id_to_all_scenes = {}  # bundle_id → [scene_ids in that bundle]
        scene_id_to_bundle_id = {}    # scene_id → bundle_id (역방향 맵)

        for scene in scenes:
            scene_id = scene.get('scene_id', scene.get('id', 0))
            bundle_id = scene.get('bundle_id')
            if scene_id:
                if bundle_id is not None:
                    if bundle_id not in bundle_id_to_all_scenes:
                        bundle_id_to_all_scenes[bundle_id] = []
                    bundle_id_to_all_scenes[bundle_id].append(scene_id)
                    scene_id_to_bundle_id[scene_id] = bundle_id
                else:
                    # bundle_id가 없는 씬도 추적 (자기 자신이 bundle_id)
                    scene_id_to_bundle_id[scene_id] = scene_id

        # 2. v2.4: 원본 선택 목록의 모든 씬이 속한 묶음 확장
        bundle_groups = {}  # bundle_id → [scene_ids]
        processed_bundle_ids = set()  # 이미 처리된 묶음 ID

        # v2.4: 원본 선택 목록 기준으로 묶음 확장 (대표 씬뿐만 아니라 원본 전체!)
        all_target_scenes = original_korean_ids | selected_scene_ids

        for scene_id in all_target_scenes:
            # 씬의 bundle_id 찾기
            bundle_id = scene_id_to_bundle_id.get(scene_id)

            if bundle_id is not None and bundle_id in bundle_id_to_all_scenes:
                # 이미 처리된 묶음이면 스킵
                if bundle_id in processed_bundle_ids:
                    continue

                # 해당 묶음의 전체 씬 추가
                all_scenes_in_bundle = bundle_id_to_all_scenes[bundle_id]
                bundle_groups[bundle_id] = all_scenes_in_bundle
                processed_bundle_ids.add(bundle_id)
            else:
                # bundle_id가 없거나 매핑되지 않은 씬은 개별 묶음으로 처리
                individual_bundle_id = -scene_id
                if individual_bundle_id not in bundle_groups:
                    bundle_groups[individual_bundle_id] = [scene_id]

        # 3. 묶음 리스트 생성 (bundle_id 순서대로 정렬)
        bundles = []
        new_bundle_id = 1

        for orig_bundle_id in sorted(bundle_groups.keys()):
            scene_ids = sorted(bundle_groups[orig_bundle_id])

            bundles.append({
                "bundle_id": new_bundle_id,
                "original_bundle_id": orig_bundle_id,  # 원본 묶음 ID 보존
                "scene_ids": scene_ids,
                "scene_range": self._format_scene_range(scene_ids),
                "representative_id": scene_ids[0]  # 대표 씬 = 첫 번째 씬
            })

            new_bundle_id += 1

        # 디버그 로그
        total_scenes = sum(len(b["scene_ids"]) for b in bundles)
        print(f"\n[Step1] ========== 🔧 기존 묶음 기반 그룹화 (v2.4) ==========")
        print(f"[Step1] 원본 선택 씬: {len(original_korean_ids)}개")
        print(f"[Step1] 대표 씬 입력: {len(selected_scene_ids)}개")
        print(f"[Step1] 통합 대상 씬: {len(all_target_scenes)}개")
        print(f"[Step1] v2.4 확장 후 전체 씬: {total_scenes}개")
        print(f"[Step1] 생성된 묶음: {len(bundles)}개")

        # v2.4: 누락 검사
        expanded_all = set()
        for b in bundles:
            expanded_all.update(b["scene_ids"])

        missing = original_korean_ids - expanded_all
        if missing:
            print(f"[Step1] ⚠️ 누락된 씬 발견: {sorted(missing)}")
            # 누락된 씬 개별 추가
            for sid in missing:
                bundles.append({
                    "bundle_id": new_bundle_id,
                    "original_bundle_id": -sid,
                    "scene_ids": [sid],
                    "scene_range": f"씬 {sid}",
                    "representative_id": sid
                })
                new_bundle_id += 1
            print(f"[Step1] ✅ 누락 씬 {len(missing)}개 개별 묶음으로 추가됨")
            total_scenes = sum(len(b["scene_ids"]) for b in bundles)

        # ═══════════════════════════════════════════════════════════════════
        # v2.9: 🔴 핵심 수정 - 수동 선택 씬의 기존 묶음 재사용
        # 문제: v2.8에서 수동 선택 씬이 기존 묶음의 비대표 멤버일 때 개별 묶음 생성 → API 낭비
        # 해결: 이미 묶음에 속한 씬은 스킵 (대표 씬에서 복사됨), 진짜 미소속 씬만 개별 생성
        # ═══════════════════════════════════════════════════════════════════

        # 현재 묶음들의 대표 씬 수집
        matched_representative_ids = set()
        for bundle in bundles:
            matched_representative_ids.add(bundle['representative_id'])

        # 현재 묶음들에 포함된 모든 씬 수집 (대표 + 멤버)
        all_bundled_scene_ids = set()
        for bundle in bundles:
            all_bundled_scene_ids.update(bundle.get('scene_ids', []))

        # 미매칭 대표 씬 확인 (selected_scene_ids에 있지만 어떤 묶음의 대표도 아닌 씬)
        unmatched_representative_ids = set(selected_scene_ids) - matched_representative_ids

        if unmatched_representative_ids:
            print(f"[Step1] ⚠️ v2.9: 대표 씬 미매칭 발견: {len(unmatched_representative_ids)}개 → {sorted(unmatched_representative_ids)[:20]}{'...' if len(unmatched_representative_ids) > 20 else ''}")

            added_count = 0
            skipped_count = 0

            for scene_id in sorted(unmatched_representative_ids):
                # ⭐ v2.9 핵심: 이 씬이 이미 묶음의 멤버인지 확인
                if scene_id in all_bundled_scene_ids:
                    # 기존 묶음의 멤버 → 대표 씬에서 복사되므로 스킵 (API 절약!)
                    # 어느 묶음에 속하는지 찾아서 로그
                    parent_bundle = None
                    for bundle in bundles:
                        if scene_id in bundle.get('scene_ids', []):
                            parent_bundle = bundle
                            break
                    if parent_bundle:
                        rep_id = parent_bundle.get('representative_id')
                        bundle_id = parent_bundle.get('bundle_id')
                        print(f"[Step1] ℹ️ v2.9: 씬 {scene_id} → 묶음 {bundle_id}에 이미 포함 (대표: {rep_id}), 복사로 처리됨 → 스킵")
                    skipped_count += 1
                else:
                    # 어떤 묶음에도 속하지 않음 → 새 개별 묶음 생성 (진짜 필요한 경우)
                    bundles.append({
                        "bundle_id": new_bundle_id,
                        "original_bundle_id": -scene_id,
                        "scene_ids": [scene_id],
                        "scene_range": f"씬 {scene_id}",
                        "representative_id": scene_id,
                        "source": "manual_addition_standalone"
                    })
                    new_bundle_id += 1
                    added_count += 1
                    print(f"[Step1] ➕ v2.9: 씬 {scene_id} → 기존 묶음 없음, 개별 묶음 생성")

            print(f"[Step1] ✅ v2.9: 미매칭 처리 완료 (스킵: {skipped_count}개, 개별 추가: {added_count}개)")
            print(f"[Step1] v2.9: 최종 묶음 수: {len(bundles)}개 (기존 매칭: {len(matched_representative_ids)}개)")
            total_scenes = sum(len(b["scene_ids"]) for b in bundles)

        for b in bundles[:10]:  # 처음 10개만 로그
            orig_id = b.get("original_bundle_id", "?")
            print(f"[Step1] ✅ 묶음 {b['bundle_id']} (원본 {orig_id}): {b['scene_range']} ({len(b['scene_ids'])}개)")
        if len(bundles) > 10:
            print(f"[Step1] ... 외 {len(bundles) - 10}개 묶음")

        print(f"[Step1] 최종 씬 수: {total_scenes}개")
        print(f"[Step1] ==========================================================\n")

        # v2.9: 결과 캐싱 (다른 탭 인터랙션 시 재계산 방지)
        st.session_state[cache_key] = bundles

        return bundles

    def _get_bundle_for_scene(self, scene_id: int, bundles: List[Dict]) -> Optional[Dict]:
        """씬 ID가 속한 묶음 찾기 (v1.6)"""
        for bundle in bundles:
            if scene_id in bundle.get("scene_ids", []):
                return bundle
        return None

    def _map_scene_ids_to_bundle_ids(self, scene_ids: Set[int], scenes: List[Dict]) -> Set[int]:
        """씬 ID를 묶음 ID로 매핑

        v1.6: 🔴 이 함수는 더 이상 사용되지 않음! 새 묶음 로직 사용
        (하위 호환성을 위해 유지하지만 실제로는 _create_simple_bundles 사용)
        """
        # v1.6: 새 묶음 생성 후 bundle_id 반환
        bundles = self._create_simple_bundles(scene_ids, bundle_size=3)
        return set(b["bundle_id"] for b in bundles)

    def _render_bundle_selection(self, pool: Set[int], scenes: List[Dict]) -> Set[int]:
        """묶음 선택 UI

        v1.7: 🔧 재수정 - 기존 bundle_id를 참조하여 묶음 생성!
        - scenes.json의 bundle_id 사용
        - 선택된 씬들만 포함된 올바른 묶음 구조 생성
        """
        selected = set()
        scene_map = self.manager.scene_map

        # ═══════════════════════════════════════════════════════════════
        # v1.7: 묶음 모드 선택 UI (기존 묶음 / 새 묶음)
        # ═══════════════════════════════════════════════════════════════
        config_col1, config_col2, config_col3 = st.columns([1, 1, 2])

        with config_col1:
            bundle_mode = st.radio(
                "묶음 모드",
                ["기존 묶음 사용", "새 묶음 생성"],
                key="step1_bundle_mode",
                horizontal=True,
                label_visibility="collapsed",
                help="기존 묶음: scenes.json의 bundle_id 참조 / 새 묶음: 선택 씬을 지정 크기로 분할"
            )

        # ═══════════════════════════════════════════════════════════════
        # v1.7: 묶음 생성 - 모드에 따라 다른 함수 사용
        # ═══════════════════════════════════════════════════════════════
        if bundle_mode == "기존 묶음 사용":
            # 기존 bundle_id 참조
            bundles = self._create_bundles_from_existing_info(pool, scenes)
            with config_col3:
                st.info(f"📦 **{len(pool)}개 씬** → **{len(bundles)}개 묶음** (기존 bundle_id 기준)")
        else:
            # 새 묶음 생성 (단순 분할)
            bundle_size = st.session_state.get("step1_bundle_size", 3)
            with config_col2:
                new_bundle_size = st.number_input(
                    "묶음 크기",
                    min_value=1,
                    max_value=10,
                    value=bundle_size,
                    key="step1_bundle_size_input",
                    help="한 묶음에 포함될 씬 개수"
                )
                if new_bundle_size != bundle_size:
                    st.session_state["step1_bundle_size"] = new_bundle_size
                    st.rerun()
            bundles = self._create_simple_bundles(pool, bundle_size)
            with config_col3:
                st.info(f"📦 **{len(pool)}개 씬** → **{len(bundles)}개 묶음** ({bundle_size}개/묶음)")

        # 전체 선택 (v2.6: 기본값 True - 묶음이 있으면 모두 선택된 상태로 시작)
        col1, col2, col3 = st.columns([1, 1, 2])
        with col1:
            select_all = st.checkbox("전체 선택", value=True, key="step1_select_all_v16")
        with col2:
            st.caption(f"✅ 묶음 수: {len(bundles)}개")
        with col3:
            total_scenes = sum(len(b["scene_ids"]) for b in bundles)
            st.caption(f"총 씬: {total_scenes}개")

        # 페이지네이션 (묶음 기준)
        items_per_page = 15
        total_pages = max(1, (len(bundles) + items_per_page - 1) // items_per_page)

        if total_pages > 1:
            page = st.number_input(
                "페이지",
                min_value=1,
                max_value=total_pages,
                value=1,
                key="step1_page_v16"
            )
        else:
            page = 1

        start_idx = (page - 1) * items_per_page
        end_idx = min(start_idx + items_per_page, len(bundles))
        page_bundles = bundles[start_idx:end_idx]

        # 묶음 카드 렌더링
        for bundle in page_bundles:
            bundle_id = bundle["bundle_id"]
            bundle_scenes = bundle["scene_ids"]
            scene_range = bundle["scene_range"]
            representative_id = bundle["representative_id"]

            # 대표 씬 정보 가져오기
            rep_scene = scene_map.get(representative_id, {})
            script = rep_scene.get('script_text', rep_scene.get('narration', ''))[:60]
            korean_prompt = rep_scene.get('image_prompt_korean_text', '')[:40]

            # 체크박스 키 (v1.6 새 형식)
            checkbox_key = f"step1_new_bundle_{bundle_id}_v16"

            # 초기값 설정
            if checkbox_key not in st.session_state:
                st.session_state[checkbox_key] = select_all

            with st.container():
                cols = st.columns([0.4, 1.5, 1.5, 2.5])

                with cols[0]:
                    is_selected = st.checkbox(
                        f"묶음 {bundle_id} 선택",
                        value=select_all or st.session_state.get(checkbox_key, False),
                        key=checkbox_key,
                        label_visibility="collapsed"
                    )
                    if is_selected:
                        # 묶음의 대표 씬 ID를 선택에 추가
                        selected.add(representative_id)

                with cols[1]:
                    st.markdown(f"**묶음 {bundle_id}**<br><small>{scene_range}</small>", unsafe_allow_html=True)

                with cols[2]:
                    if korean_prompt:
                        st.markdown(f"<small style='color:#60A5FA'>🔤 {korean_prompt}...</small>", unsafe_allow_html=True)
                    else:
                        st.caption(f"({len(bundle_scenes)}개 씬)")

                with cols[3]:
                    st.markdown(f"<small>{script}...</small>", unsafe_allow_html=True)

        # v2.5: 🔧 핵심 수정 - "전체 선택" 시 모든 묶음 포함 (페이지네이션 무관)
        # 기존 버그: select_all=True 여도 현재 페이지의 체크박스만 selected에 추가됨
        # 결과: 34개 묶음 중 15개(1페이지)만 처리, 나머지 누락!
        if select_all:
            # 전체 선택: 모든 묶음의 모든 씬 포함
            selected_bundles = bundles  # 전체 묶음
            all_selected_scene_ids = set()
            for b in bundles:
                all_selected_scene_ids.update(b["scene_ids"])
            print(f"[Step1] v2.5: 전체 선택 - 모든 묶음 포함: {len(bundles)}개 묶음, {len(all_selected_scene_ids)}개 씬")
        else:
            # 개별 선택: 체크된 묶음만
            selected_bundles = [b for b in bundles if b["representative_id"] in selected]
            all_selected_scene_ids = set()
            for b in selected_bundles:
                all_selected_scene_ids.update(b["scene_ids"])

        st.session_state["step1_selected_bundles_v16"] = selected_bundles
        st.session_state["step1_all_selected_scene_ids_v16"] = all_selected_scene_ids

        # v2.4: 묶음 확장 정보 및 동기화 검증
        display_selected_count = len(bundles) if select_all else len(selected)
        if display_selected_count > 0:
            original_count = len(st.session_state.get('korean_text_scene_ids', []))
            st.info(f"📊 **묶음 확장**: {display_selected_count}개 묶음 → {len(all_selected_scene_ids)}개 전체 씬")

            # v2.4: 동기화 상태 표시
            if original_count > 0:
                if len(all_selected_scene_ids) == original_count:
                    st.success(f"✅ 동기화 완료: 원본 {original_count}개 = 확장 {len(all_selected_scene_ids)}개")
                elif len(all_selected_scene_ids) >= original_count:
                    st.success(f"✅ 확장 완료: 원본 {original_count}개 → {len(all_selected_scene_ids)}개")
                else:
                    # 일부만 선택된 경우 (전체 선택이 아님)
                    st.caption(f"ℹ️ 원본 {original_count}개 중 {len(all_selected_scene_ids)}개 선택됨")

        if select_all:
            return pool.copy()

        return selected

    # ═══════════════════════════════════════════════════════════════════
    # v2.3: 수동 선택 타임라인 뷰 (2차 필터)
    # ═══════════════════════════════════════════════════════════════════

    def _render_manual_selection_timeline(
        self,
        scenes: List[Dict],
        ai_pool: Set[int]
    ) -> Set[int]:
        """
        v2.3: 수동 씬 선택 타임라인 뷰

        Args:
            scenes: 전체 씬 데이터
            ai_pool: AI 분석으로 선택된 씬 ID 집합

        Returns:
            수동 선택된 씬 ID 집합 (묶음 확장 적용됨)
        """
        with st.expander("📷 타임라인 뷰 (수동 씬 추가 선택)", expanded=True):
            st.markdown("*이미지를 보고 한글 텍스트 이미지로 생성할 씬을 추가로 선택하세요. 묶음 내 씬 선택 시 전체 묶음이 자동 선택됩니다.*")

            # session_state에서 수동 선택 상태 관리
            if "step1_manual_selected_bundles" not in st.session_state:
                st.session_state.step1_manual_selected_bundles = set()

            # 전체 묶음 목록 생성 (AI 선택 여부 무관)
            all_bundles = self._get_all_bundles_for_timeline(scenes)

            if not all_bundles:
                st.info("표시할 묶음이 없습니다.")
                return set()

            # 필터 옵션
            filter_col1, filter_col2, filter_col3 = st.columns([1, 1, 2])

            with filter_col1:
                if st.button("✅ 전체 선택", key="step1_manual_select_all"):
                    st.session_state.step1_manual_selected_bundles = {b["bundle_id"] for b in all_bundles}
                    st.rerun()

            with filter_col2:
                if st.button("❌ 전체 해제", key="step1_manual_deselect_all"):
                    st.session_state.step1_manual_selected_bundles = set()
                    st.rerun()

            with filter_col3:
                exclude_ai = st.checkbox(
                    "AI 선택 묶음 숨기기",
                    value=False,
                    key="step1_exclude_ai_bundles"
                )

            st.markdown("---")

            # AI 선택 묶음 ID 추출
            ai_bundle_ids = set()
            for bundle in all_bundles:
                if any(sid in ai_pool for sid in bundle["scene_ids"]):
                    ai_bundle_ids.add(bundle["bundle_id"])

            # 필터 적용
            display_bundles = all_bundles
            if exclude_ai:
                display_bundles = [b for b in all_bundles if b["bundle_id"] not in ai_bundle_ids]

            if not display_bundles:
                st.info("표시할 묶음이 없습니다. (AI 선택 묶음 제외됨)")
                return self._expand_manual_selection_to_scenes(all_bundles)

            # 묶음별 카드 렌더링 (4열 그리드)
            cols_per_row = 4

            for i in range(0, len(display_bundles), cols_per_row):
                row_bundles = display_bundles[i:i + cols_per_row]
                cols = st.columns(cols_per_row)

                for j, bundle in enumerate(row_bundles):
                    if j >= len(row_bundles):
                        break

                    bundle_id = bundle["bundle_id"]
                    scene_ids = bundle["scene_ids"]
                    is_ai_selected = bundle_id in ai_bundle_ids
                    is_manually_selected = bundle_id in st.session_state.step1_manual_selected_bundles

                    with cols[j]:
                        # 묶음 헤더
                        header_parts = [f"**묶음 {bundle_id}**"]
                        if is_ai_selected:
                            header_parts.append("🤖")
                        if is_manually_selected:
                            header_parts.append("✅")
                        st.markdown(" ".join(header_parts))

                        # 씬 범위 표시
                        if len(scene_ids) == 1:
                            st.caption(f"씬 {scene_ids[0]}")
                        else:
                            st.caption(f"씬 {scene_ids[0]}-{scene_ids[-1]} ({len(scene_ids)}개)")

                        # 대표 씬 이미지 표시
                        rep_scene_id = scene_ids[0]
                        rep_scene = self.manager.scene_map.get(rep_scene_id, {})
                        image_path = self._find_scene_display_image(rep_scene_id, rep_scene)

                        if image_path and os.path.exists(image_path):
                            st.image(image_path, use_container_width=True)
                        else:
                            st.markdown(
                                "<div style='height:80px;background:#444;display:flex;"
                                "align-items:center;justify-content:center;border-radius:4px;'>"
                                "<span style='color:#999;font-size:12px;'>이미지 없음</span></div>",
                                unsafe_allow_html=True
                            )

                        # 스크립트 미리보기
                        script = rep_scene.get('script_text', rep_scene.get('narration', ''))[:30]
                        if script:
                            st.caption(f"📝 {script}...")

                        # 한글 텍스트 프롬프트 표시
                        korean_prompt = rep_scene.get('image_prompt_korean_text', '')
                        if korean_prompt:
                            st.markdown(f"<small style='color:#60A5FA'>🔤 {korean_prompt[:20]}...</small>", unsafe_allow_html=True)

                        # 선택/해제 버튼
                        if is_manually_selected:
                            if st.button("해제", key=f"step1_manual_deselect_{bundle_id}", use_container_width=True):
                                st.session_state.step1_manual_selected_bundles.discard(bundle_id)
                                st.rerun()
                        else:
                            if st.button("선택", key=f"step1_manual_select_{bundle_id}", use_container_width=True):
                                st.session_state.step1_manual_selected_bundles.add(bundle_id)
                                st.rerun()

            st.markdown("---")

            # 선택 통계
            manual_count = len(st.session_state.step1_manual_selected_bundles)
            st.caption(f"수동 선택된 묶음: {manual_count}개 / 전체: {len(all_bundles)}개")

        # 수동 선택된 묶음의 전체 씬 ID 반환
        return self._expand_manual_selection_to_scenes(all_bundles)

    def _get_all_bundles_for_timeline(self, scenes: List[Dict]) -> List[Dict]:
        """전체 씬에서 묶음 목록 생성 (타임라인 뷰용)"""
        bundle_dict = defaultdict(list)

        for scene in scenes:
            scene_id = scene.get('scene_id', scene.get('id', 0))
            bundle_id = scene.get('bundle_id', scene_id)
            if scene_id:
                bundle_dict[bundle_id].append({
                    'scene_id': scene_id,
                    'scene': scene
                })

        bundles = []
        for bundle_id in sorted(bundle_dict.keys()):
            items = bundle_dict[bundle_id]
            items.sort(key=lambda x: x['scene_id'])
            scene_ids = [item['scene_id'] for item in items]

            bundles.append({
                'bundle_id': bundle_id,
                'scene_ids': scene_ids,
                'scene_count': len(scene_ids),
                'representative_id': scene_ids[0]
            })

        return bundles

    def _expand_manual_selection_to_scenes(self, all_bundles: List[Dict]) -> Set[int]:
        """수동 선택된 묶음을 씬 ID 집합으로 확장"""
        selected_bundle_ids = st.session_state.get('step1_manual_selected_bundles', set())
        expanded_scene_ids = set()

        for bundle in all_bundles:
            if bundle['bundle_id'] in selected_bundle_ids:
                expanded_scene_ids.update(bundle['scene_ids'])

        return expanded_scene_ids

    def _find_scene_display_image(self, scene_id: int, scene: Dict) -> Optional[str]:
        """
        씬의 표시용 이미지 경로 찾기 (v2.5 개선)

        우선순위:
        1. 씬 데이터의 직접 필드 (timeline_composite.get_latest_scene_image와 동일 우선순위)
        2. 씬 데이터의 images 딕셔너리
        3. composited > nano_composite > composite_realshot > backgrounds > scenes > korean_text 디렉토리 탐색
        """
        # v2.5: 1순위 - 씬 데이터에서 이미지 경로 직접 확인
        # (timeline_composite.py의 get_latest_scene_image와 동일 우선순위)
        if scene:
            direct_fields = [
                'real_image_path',          # Step3 실사 대체 이미지 (최우선)
                'composited_image_path',    # Step3 합성 이미지
                'composite_image_path',     # 합성 이미지
                'nano_composite_image',     # Nano Banana 합성 이미지
                'composite_path',           # 합성 경로
                'display_image',            # 표시용 이미지
                'image_path',               # 일반 이미지 경로
                'background_image',         # 배경 이미지
                'background_image_path',    # 배경 이미지 경로
                'composite_image',          # 합성 이미지 (레거시)
                'scene_image',              # 씬 이미지
                'infographic_image_path',   # 인포그래픽 이미지
            ]

            for field in direct_fields:
                img_path = scene.get(field)
                if img_path and os.path.exists(str(img_path)):
                    return str(img_path)

            # images 딕셔너리 확인 (다양한 키)
            images = scene.get('images', {})
            if isinstance(images, dict):
                for key in ['composite', 'composited', 'background', 'scene', 'korean_text', 'nano_composite']:
                    img_path = images.get(key)
                    if img_path and os.path.exists(str(img_path)):
                        return str(img_path)

        # 2순위 - 디렉토리 탐색
        import glob as glob_mod

        search_dirs = [
            self.project_path / "images" / "composited",
            self.project_path / "images" / "nano_composite",
            self.project_path / "images" / "composite_realshot",
            self.project_path / "images" / "backgrounds",
            self.project_path / "images" / "scenes",
            self.project_path / "images" / "korean_text",
            self.project_path / "images" / "generated",
            self.project_path / "images" / "video_thumbnails",
        ]

        extensions = ['.png', '.jpg', '.jpeg', '.webp']

        # v2.5: 타임스탬프 포함 glob 패턴 우선 검색 (가장 최근 파일)
        glob_patterns = [
            ("images/composited", f"composited_{scene_id:03d}_*"),
            ("images/nano_composite", f"composite_scene_{scene_id:03d}_*"),
            ("images/composite_realshot", f"scene_{scene_id:03d}_composite*"),
            ("images/backgrounds", f"bg_scene_{scene_id:03d}_*"),
        ]

        for rel_dir, pattern in glob_patterns:
            dir_path = self.project_path / rel_dir
            if dir_path.exists():
                for ext in extensions:
                    matches = glob_mod.glob(str(dir_path / f"{pattern}{ext}"))
                    if matches:
                        # 가장 최근 파일 반환
                        return max(matches, key=os.path.getmtime)

        # 정확한 파일명 패턴 검색
        name_patterns = [
            f"scene_{scene_id:03d}",
            f"scene_{scene_id:04d}",
            f"scene_{scene_id}",
            f"scene{scene_id:03d}",
            f"{scene_id:03d}",
            f"{scene_id:04d}",
            f"korean_text_scene_{scene_id:03d}",
            f"composite_scene_{scene_id:03d}",
        ]

        for search_dir in search_dirs:
            if search_dir.exists():
                for pattern in name_patterns:
                    for ext in extensions:
                        exact_path = search_dir / f"{pattern}{ext}"
                        if exact_path.exists():
                            return str(exact_path)

                # 와일드카드: 씬 번호 포함 파일 검색
                for ext in extensions:
                    for file in search_dir.glob(f"*_{scene_id:03d}_*{ext}"):
                        return str(file)

        return None


def render_step1_ui(manager, scenes: List[Dict], project_path: Path):
    """Step 1 UI 렌더 함수"""
    ui = Step1KoreanTextUI(manager, project_path)
    return ui.render(scenes)
