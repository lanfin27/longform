# -*- coding: utf-8 -*-
"""
components/storyboard_workflow/step2_character.py
Step 2: 배경+캐릭터 합성 UI (v2.6 - session_state 오류 수정)

처리 단위: 묶음 (Bundle)
대상: characters 필드가 있는 씬 (Step 1 제외)

v2.0 변경사항:
- 나노바나나 배경+캐릭터 합성 기능 완전 통합
- 모델 선택 (Nano Banana / Nano Banana Pro)
- 프롬프트 언어 선택 (영어/한글)
- 레퍼런스 강도 설정
- 묶음 최적화 (대표 씬만 생성, 나머지 복사)
- 워크플로우 정보 표시 (레퍼런스 이미지, 프롬프트)

v2.1 변경사항:
- 씬 범위 표시 수정 - 연속된 씬만 범위로 표시

v2.2 변경사항:
- 배경/캐릭터 레퍼런스 강도 분리 (단일 슬라이더 → 2개 슬라이더)
- 프리셋 버튼 추가 (배경 중심, 캐릭터 중심, 균형, 창의적)

v2.3 변경사항:
- 🔴 긴급 수정: 묶음 로직 오류 수정
- 기존: 원본 scenes.json의 bundle_id 사용 (비연속 씬이 같은 묶음에!)
- 수정: 선택된 씬들을 정렬 후 단순 분할하여 새 묶음 생성

v2.4 변경사항:
- 🔧 긴급 수정: 기존 bundle_id 기반 묶음 최적화 추가!
- 문제: 씬 47,48이 같은 묶음인데 둘 다 별도 API 호출 (낭비!)
- 추가: "기존 묶음 사용" 옵션 (기본값) - scenes.json의 bundle_id 참조
- 효과: 같은 묶음 내 씬들은 대표 씬만 API 호출, 나머지는 복사
- 💰 API 비용 50%+ 절약!

v2.5 변경사항:
- ⚡ 배치/순차 처리 선택 UI 추가 (Step 1과 동일)
- 배치: ThreadPoolExecutor 병렬 처리 (빠름, 에러 시 전체 중단 가능성)
- 순차: 하나씩 처리 (안정적, 진행 상황 실시간 확인)
- 👥 다중 캐릭터 레퍼런스 지원 추가
- get_all_character_images_for_scene() 함수로 씬의 모든 캐릭터 이미지 조회

v2.6 변경사항:
- 🔧 session_state 오류 수정: 위젯 생성 후 session_state 직접 할당 제거
- 문제: st.session_state["step2_processing_mode"] = processing_mode (위젯 생성 후 할당)
- 오류: "st.session_state.xxx cannot be modified after the widget is instantiated"
- 수정: 위젯이 자동으로 session_state와 동기화하므로 직접 할당 불필요
"""

import streamlit as st
import json
import os
import time
import shutil
from typing import Set, Dict, List, Optional, Tuple
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from .step_ui_base import StepUIBase
from .progress_visualizer import render_step_status_cards

# 나노바나나 합성 모듈 import
try:
    from components.nano_banana_composite import (
        get_scene_number,
        get_scene_prompts,
        get_scene_image_paths,
        generate_composite_image,
        update_scene_image_path,
        has_character_prompt,
        # v2.5: 다중 캐릭터 레퍼런스 지원
        get_all_character_images_for_scene,
        get_primary_character_image,
    )
    from utils.gemini_image_generator import (
        GeminiImageGenerator,
        GEMINI_IMAGE_MODELS,
        check_gemini_api_key
    )
    NANO_BANANA_AVAILABLE = True
except ImportError as e:
    NANO_BANANA_AVAILABLE = False
    print(f"[Step2] ⚠️ 나노바나나 합성 모듈 로드 실패: {e}")

# 레이어 합성용 PIL
try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


# 모델 정보
COMPOSITE_MODELS = {
    "gemini_nano_banana": {
        "display_name": "Nano Banana (빠름, ~15원/장)",
        "cost": "~15원",
        "speed": "빠름"
    },
    "gemini_nano_banana_pro": {
        "display_name": "Nano Banana Pro (고품질, ~25원/장)",
        "cost": "~25원",
        "speed": "보통"
    }
}


class Step2CharacterUI(StepUIBase):
    """Step 2: 배경+캐릭터 합성 (v2.0)"""

    def __init__(self, workflow_manager, project_path: Path):
        super().__init__(
            step_number=2,
            workflow_manager=workflow_manager,
            project_path=project_path
        )

    def get_pool(self) -> Set[int]:
        return self.manager.calculate_step2_pool()

    def get_assigned(self) -> Set[int]:
        return self.manager.state.step2_scenes

    def get_completed(self) -> Set[int]:
        return self.manager.state.completed_step2

    def render_step_content(
        self,
        scenes: List[Dict],
        pool: Set[int],
        assigned: Set[int],
        completed: Set[int]
    ) -> Optional[Dict]:
        """Step 2 콘텐츠 렌더링 (v2.0)"""

        # Step 1 완료 확인
        step1_completed = len(self.manager.state.completed_step1)
        step1_assigned = len(self.manager.state.step1_scenes)

        if step1_assigned > 0 and step1_completed < step1_assigned:
            st.warning(f"⚠️ Step 1이 진행 중입니다. (완료: {step1_completed}/{step1_assigned})")

        # 설명
        st.info("""
            **🎭 Step 2: 배경+캐릭터 합성**

            - **대상**: `characters` 필드가 있는 씬 (Step 1 처리 씬 제외)
            - **처리 단위**: 묶음 (Bundle) - 대표 씬만 생성, 나머지 복사
            - **합성 방식**: 나노바나나 AI 합성 (배경+캐릭터 레퍼런스)
        """)

        st.markdown("---")

        # API 확인
        if not NANO_BANANA_AVAILABLE:
            st.error("❌ 나노바나나 합성 모듈이 설치되지 않았습니다.")
            return None

        if not check_gemini_api_key():
            st.error("❌ Gemini API 키가 설정되지 않았습니다. `.env` 파일에 `GEMINI_API_KEY`를 추가하세요.")
            return None

        # ═══════════════════════════════════════════════════════════════════
        # 합성 설정 (나노바나나 페이지와 동일)
        # ═══════════════════════════════════════════════════════════════════
        with st.expander("⚙️ 합성 설정", expanded=True):
            self._render_composite_settings()

        st.markdown("---")

        # 대상 씬 목록
        st.markdown("#### 📋 대상 묶음 목록 (캐릭터 있는 씬)")

        if not pool:
            st.success("✅ 캐릭터 합성 대상 씬이 없거나 모두 처리되었습니다.")
            return None

        # 씬 선택
        selected = self._render_bundle_selection_v2(pool, scenes)

        # 영향받는 씬 미리보기
        self.render_affected_scenes_preview(selected)

        # 실행 버튼
        def on_assign(ids):
            self.manager.assign_to_step(2, ids)
            self.manager.save()

        def on_execute(ids):
            """v2.0: 나노바나나 합성 실행"""
            affected = self.manager.get_scenes_affected_by_selection(ids, 2)
            scene_ids = sorted(affected['total'])

            if not scene_ids:
                st.warning("⚠️ 합성할 씬이 없습니다.")
                return None

            # v2.2: 세션 상태에서 설정 가져오기 (배경/캐릭터 강도 분리)
            composite_method = st.session_state.get("step2_method", "Nano Banana 합성")
            model_key = st.session_state.get("step2_model_key", "gemini_nano_banana")
            prompt_type = st.session_state.get("step2_prompt_type", "english")
            bg_ref_strength = st.session_state.get("step2_bg_ref_strength", 0.7)
            char_ref_strength = st.session_state.get("step2_char_ref_strength", 0.6)

            result = self._execute_nano_banana_composite(
                scenes=scenes,
                scene_ids=scene_ids,
                composite_method=composite_method,
                model_key=model_key,
                prompt_type=prompt_type,
                bg_ref_strength=bg_ref_strength,
                char_ref_strength=char_ref_strength,
            )

            return result

        return self.render_execution_buttons(
            selected,
            on_assign=on_assign,
            on_execute=on_execute,
            execute_label="캐릭터 합성 실행"
        )

    def _render_composite_settings(self):
        """합성 설정 UI (나노바나나 페이지와 동일) v2.5: 배치/순차 처리 선택 추가"""

        # v2.5: 처리 모드 선택 (배치/순차)
        st.markdown("##### ⚡ 처리 모드")
        mode_col1, mode_col2 = st.columns([1, 3])

        with mode_col1:
            processing_mode = st.radio(
                "처리 방식",
                ["순차 처리", "배치 처리"],
                index=0,  # 순차 처리 기본값 (안정적)
                key="step2_processing_mode",
                horizontal=True,
                label_visibility="collapsed",
                help="순차: 하나씩 처리 (안정적) / 배치: 병렬 처리 (빠름)"
            )
            # v2.6: session_state 직접 할당 제거 (위젯이 자동 동기화)

        with mode_col2:
            if processing_mode == "배치 처리":
                max_workers = st.slider(
                    "동시 처리 수",
                    min_value=2,
                    max_value=8,
                    value=4,
                    key="step2_max_workers",
                    help="병렬로 처리할 최대 작업 수 (API 레이트 리밋 주의)"
                )
                st.caption(f"⚠️ 배치 처리: {max_workers}개 동시 처리 (빠르지만 에러 시 전체 중단 가능)")
            else:
                st.caption("✅ 순차 처리: 안정적이며 진행 상황 실시간 확인 가능")

        st.markdown("---")

        col1, col2 = st.columns(2)

        with col1:
            # 합성 방식
            composite_method = st.radio(
                "합성 방식",
                ["Nano Banana 합성", "레이어 합성 (기존 배경 + 캐릭터)"],
                key="step2_method"
            )

            # 나노바나나 선택 시 추가 설정
            if "Nano Banana" in composite_method:
                # 모델 선택
                model_options = list(COMPOSITE_MODELS.keys())
                model_display_names = [COMPOSITE_MODELS[k]["display_name"] for k in model_options]

                model_display = st.selectbox(
                    "🍌 모델 선택",
                    model_display_names,
                    index=0,
                    key="step2_model_display"
                )

                model_key = model_options[model_display_names.index(model_display)]
                st.session_state["step2_model_key"] = model_key

        with col2:
            if "Nano Banana" in composite_method:
                # 프롬프트 언어
                prompt_type_display = st.radio(
                    "📝 프롬프트 언어",
                    ["🇺🇸 영어 (권장)", "🇰🇷 한글"],
                    horizontal=True,
                    key="step2_prompt_lang"
                )
                prompt_type = "english" if "영어" in prompt_type_display else "korean"
                st.session_state["step2_prompt_type"] = prompt_type

                # v2.2: 배경/캐릭터 레퍼런스 강도 분리
                st.markdown("**🎨 레퍼런스 강도 설정**")

                ref_col1, ref_col2 = st.columns(2)

                with ref_col1:
                    bg_ref_strength = st.slider(
                        "🖼️ 배경 강도",
                        min_value=0.0,
                        max_value=1.0,
                        value=st.session_state.get("step2_bg_ref_strength", 0.7),
                        step=0.1,
                        key="step2_bg_ref_strength",
                        help="배경 이미지가 결과에 반영되는 정도"
                    )

                with ref_col2:
                    char_ref_strength = st.slider(
                        "👤 캐릭터 강도",
                        min_value=0.0,
                        max_value=1.0,
                        value=st.session_state.get("step2_char_ref_strength", 0.6),
                        step=0.1,
                        key="step2_char_ref_strength",
                        help="캐릭터 이미지가 결과에 반영되는 정도"
                    )

                # 프리셋 버튼
                preset_col1, preset_col2, preset_col3, preset_col4 = st.columns(4)

                with preset_col1:
                    if st.button("🖼️ 배경", key="step2_preset_bg", use_container_width=True, help="배경 90% / 캐릭터 30%"):
                        st.session_state["step2_bg_ref_strength"] = 0.9
                        st.session_state["step2_char_ref_strength"] = 0.3
                        st.rerun()

                with preset_col2:
                    if st.button("👤 캐릭터", key="step2_preset_char", use_container_width=True, help="배경 30% / 캐릭터 90%"):
                        st.session_state["step2_bg_ref_strength"] = 0.3
                        st.session_state["step2_char_ref_strength"] = 0.9
                        st.rerun()

                with preset_col3:
                    if st.button("⚖️ 균형", key="step2_preset_balanced", use_container_width=True, help="배경 60% / 캐릭터 60%"):
                        st.session_state["step2_bg_ref_strength"] = 0.6
                        st.session_state["step2_char_ref_strength"] = 0.6
                        st.rerun()

                with preset_col4:
                    if st.button("🎨 창의", key="step2_preset_creative", use_container_width=True, help="배경 40% / 캐릭터 40%"):
                        st.session_state["step2_bg_ref_strength"] = 0.4
                        st.session_state["step2_char_ref_strength"] = 0.4
                        st.rerun()

                st.caption(f"📊 현재: 배경 {int(bg_ref_strength * 100)}% / 캐릭터 {int(char_ref_strength * 100)}%")
            else:
                # 레이어 합성 설정
                char_position = st.selectbox(
                    "캐릭터 위치",
                    ["자동 (AI 추천)", "왼쪽 하단", "오른쪽 하단", "중앙 하단"],
                    key="step2_char_pos"
                )
                st.session_state["step2_char_position"] = char_position

                char_scale = st.slider(
                    "캐릭터 크기 (%)",
                    min_value=30,
                    max_value=100,
                    value=60,
                    key="step2_char_scale"
                )
                st.session_state["step2_char_scale"] = char_scale / 100.0

        # 비용 정보
        if "Nano Banana" in composite_method:
            model_key = st.session_state.get("step2_model_key", "gemini_nano_banana")
            model_info = COMPOSITE_MODELS.get(model_key, {})
            st.info(f"💰 예상 비용: {model_info.get('cost', '~15원')}/장 | ⚡ 속도: {model_info.get('speed', '빠름')}")

    def _render_bundle_selection_v2(self, pool: Set[int], scenes: List[Dict]) -> Set[int]:
        """묶음 선택 UI (v2.4 - 기존 묶음 사용 옵션 추가!)

        v2.4: 🔧 핵심 수정 - 기존 bundle_id 사용 옵션 추가!
        - "기존 묶음 사용": scenes.json의 bundle_id 참조 (API 절약!)
        - "새 묶음 생성": 선택된 씬들을 단순 분할
        """
        selected = set()
        scene_map = self.manager.scene_map

        # ═══════════════════════════════════════════════════════════════
        # v2.4: 묶음 모드 선택 UI (기존 묶음 / 새 묶음)
        # ═══════════════════════════════════════════════════════════════
        config_col1, config_col2, config_col3 = st.columns([1, 1, 2])

        with config_col1:
            bundle_mode = st.radio(
                "묶음 모드",
                ["기존 묶음 사용", "새 묶음 생성"],
                index=0,  # v2.4: 기본값을 "기존 묶음 사용"으로!
                key="step2_bundle_mode",
                horizontal=True,
                label_visibility="collapsed",
                help="기존 묶음: scenes.json의 bundle_id 참조 (API 절약!) / 새 묶음: 선택 씬을 지정 크기로 분할"
            )

        # ═══════════════════════════════════════════════════════════════
        # v2.4: 묶음 생성 - 모드에 따라 다른 함수 사용
        # ═══════════════════════════════════════════════════════════════
        if bundle_mode == "기존 묶음 사용":
            # 기존 bundle_id 참조 (API 절약!)
            bundles = self._create_bundles_from_existing_info(pool, scenes)
            with config_col3:
                st.info(f"📦 **{len(pool)}개 씬** → **{len(bundles)}개 묶음** (기존 bundle_id 기준) 💰 API 절약!")
        else:
            # 새 묶음 생성 (단순 분할)
            bundle_size = st.session_state.get("step2_bundle_size", 3)
            with config_col2:
                new_bundle_size = st.number_input(
                    "묶음 크기",
                    min_value=1,
                    max_value=10,
                    value=bundle_size,
                    key="step2_bundle_size_input",
                    help="한 묶음에 포함될 씬 개수"
                )
                if new_bundle_size != bundle_size:
                    st.session_state["step2_bundle_size"] = new_bundle_size
                    st.rerun()
            bundles = self._create_simple_bundles(pool, bundle_size)
            with config_col3:
                st.info(f"📦 **{len(pool)}개 씬** → **{len(bundles)}개 묶음** ({bundle_size}개/묶음)")

        # 상태 요약 계산
        bg_ready_count = 0
        char_ready_count = 0
        composite_ready_count = 0

        for sid in pool:
            scene = scene_map.get(sid, {})
            paths = get_scene_image_paths(scene, str(self.project_path))
            if paths.get("background"):
                bg_ready_count += 1
            if paths.get("character"):
                char_ready_count += 1
            if paths.get("composite"):
                composite_ready_count += 1

        # 상태 요약 표시
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("대상 묶음", len(bundles))
        with col2:
            st.metric("🏞️ 배경", f"{bg_ready_count}/{len(pool)}")
        with col3:
            st.metric("👤 캐릭터", f"{char_ready_count}/{len(pool)}")
        with col4:
            st.metric("✨ 합성 완료", f"{composite_ready_count}/{len(pool)}")

        # 경고 메시지
        if char_ready_count == 0:
            st.warning("⚠️ 캐릭터 이미지가 없습니다. 합성하려면 먼저 **캐릭터 이미지를 생성**해야 합니다.")
        elif bg_ready_count == 0:
            st.warning("⚠️ 배경 이미지가 없습니다. 합성하려면 **배경 이미지와 캐릭터 이미지 모두** 필요합니다.")

        st.markdown("---")

        # 전체 선택
        col1, col2 = st.columns([1, 3])
        with col1:
            select_all = st.checkbox("전체 선택", key="step2_select_all_v23")
        with col2:
            # 합성 가능한 씬 수
            composable_count = min(bg_ready_count, char_ready_count)
            st.caption(f"합성 가능: {composable_count}개")

        # 페이지네이션 (묶음 기준)
        items_per_page = 12
        total_pages = max(1, (len(bundles) + items_per_page - 1) // items_per_page)

        if total_pages > 1:
            page = st.number_input(
                "페이지",
                min_value=1,
                max_value=total_pages,
                value=1,
                key="step2_page_v23"
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
            scene = scene_map.get(representative_id, {})

            script = scene.get('script_text', scene.get('narration', ''))[:40]

            # 이미지 상태 확인
            paths = get_scene_image_paths(scene, str(self.project_path))
            has_bg = bool(paths.get("background"))
            has_char = bool(paths.get("character"))
            has_composite = bool(paths.get("composite"))

            # 캐릭터 이름
            characters = scene.get('characters', [])
            char_names = []
            for char in characters:
                if isinstance(char, dict):
                    char_names.append(char.get('name', ''))
                elif isinstance(char, str):
                    char_names.append(char)
            char_display = ", ".join(char_names[:2]) if char_names else "캐릭터"

            with st.container():
                cols = st.columns([0.4, 1.0, 1.2, 0.8, 0.8, 1.8])

                with cols[0]:
                    # v2.3: 새 묶음 키 사용
                    checkbox_key = f"step2_new_bundle_{bundle_id}_v23"
                    is_selected = st.checkbox(
                        f"묶음 {bundle_id} 선택",
                        value=select_all,
                        key=checkbox_key,
                        label_visibility="collapsed"
                    )
                    if is_selected:
                        # v2.3: 대표 씬 ID를 선택에 추가
                        selected.add(representative_id)

                with cols[1]:
                    # v2.3: 이미 bundle에서 scene_range 가져옴
                    st.markdown(f"**묶음 {bundle_id}**<br><small>{scene_range}</small>", unsafe_allow_html=True)

                with cols[2]:
                    st.markdown(f"<small style='color:#FBBF24'>🎭 {char_display}</small>", unsafe_allow_html=True)

                with cols[3]:
                    # 배경/캐릭터 상태
                    bg_icon = "✅" if has_bg else "❌"
                    char_icon = "✅" if has_char else "❌"
                    st.markdown(f"<small>{bg_icon}배경 {char_icon}캐릭</small>", unsafe_allow_html=True)

                with cols[4]:
                    # 합성 상태
                    if has_composite:
                        st.markdown("<small style='color:#22C55E'>✨완료</small>", unsafe_allow_html=True)
                    elif has_bg and has_char:
                        st.markdown("<small style='color:#60A5FA'>⏳대기</small>", unsafe_allow_html=True)
                    else:
                        st.markdown("<small style='color:#EF4444'>⚠️부족</small>", unsafe_allow_html=True)

                with cols[5]:
                    st.markdown(f"<small>{script}...</small>", unsafe_allow_html=True)

        # v2.3: 선택된 묶음의 전체 씬 저장 (합성 시 사용)
        selected_bundles = [b for b in bundles if b["representative_id"] in selected]
        all_selected_scene_ids = set()
        for b in selected_bundles:
            all_selected_scene_ids.update(b["scene_ids"])

        st.session_state["step2_selected_bundles_v23"] = selected_bundles
        st.session_state["step2_all_selected_scene_ids_v23"] = all_selected_scene_ids

        # 묶음 확장 정보
        if selected:
            st.info(f"📊 **묶음 확장**: {len(selected)}개 대표 씬 → {len(all_selected_scene_ids)}개 전체 씬")

        if select_all:
            return pool.copy()

        return selected

    # ═══════════════════════════════════════════════════════════════
    # v2.5: 배치/순차 처리 헬퍼 메서드
    # ═══════════════════════════════════════════════════════════════

    def _composite_single_scene(
        self,
        scene_id: int,
        scene_map: Dict,
        project_path: str,
        generator,
        use_nano_banana: bool,
        model_key: str,
        prompt_type: str,
        bg_ref_strength: float,
        char_ref_strength: float,
        output_dir: Path
    ) -> Dict:
        """
        단일 씬 합성 처리 (v2.5 - 배치/순차 공통 로직)

        Returns:
            {
                'scene_id': int,
                'success': bool,
                'output_path': str or None,
                'error': str or None,
                'type': 'generated' | 'layer_composite'
            }
        """
        result = {
            'scene_id': scene_id,
            'success': False,
            'output_path': None,
            'error': None,
            'type': None
        }

        scene = scene_map.get(scene_id)
        if not scene:
            result['error'] = '씬 데이터 없음'
            return result

        # 이미지 경로 확인
        paths = get_scene_image_paths(scene, project_path)
        bg_path = paths.get("background")
        char_path = paths.get("character")

        if not bg_path or not os.path.exists(bg_path):
            result['error'] = '배경 이미지 없음'
            return result

        if not char_path or not os.path.exists(char_path):
            result['error'] = '캐릭터 이미지 없음'
            return result

        # 프롬프트 가져오기
        prompts = get_scene_prompts(scene)
        prompt = prompts["full_en"] if prompt_type == "english" else prompts["full_ko"]

        try:
            if use_nano_banana:
                # 배경/캐릭터 강도를 반영한 프롬프트 구성
                enhanced_prompt = self._build_prompt_with_separate_strengths(
                    prompt,
                    has_bg=bg_path is not None,
                    has_char=char_path is not None,
                    bg_strength=bg_ref_strength,
                    char_strength=char_ref_strength
                )

                # 평균 강도를 API에 전달
                avg_ref_strength = (bg_ref_strength + char_ref_strength) / 2

                # 나노바나나 합성
                success, output_path, error, composite_info = generate_composite_image(
                    scene=scene,
                    project_path=project_path,
                    generator=generator,
                    background_path=bg_path,
                    character_path=char_path,
                    model_key=model_key,
                    prompt_type=prompt_type,
                    reference_strength=avg_ref_strength,
                    custom_prompt=enhanced_prompt
                )

                if success and output_path:
                    result['success'] = True
                    result['output_path'] = output_path
                    result['type'] = 'generated'
                    result['composite_info'] = composite_info
                    result['prompt'] = prompt
                else:
                    result['error'] = error or '합성 실패'
            else:
                # 레이어 합성 (PIL)
                char_position = st.session_state.get("step2_char_position", "자동 (AI 추천)")
                char_scale = st.session_state.get("step2_char_scale", 0.6)

                pil_result = self._composite_with_pil(
                    bg_path=bg_path,
                    char_path=char_path,
                    output_dir=output_dir,
                    scene_id=scene_id,
                    position=char_position,
                    scale=char_scale
                )

                if pil_result.get('success'):
                    result['success'] = True
                    result['output_path'] = pil_result['output_path']
                    result['type'] = 'layer_composite'
                else:
                    result['error'] = pil_result.get('error', '합성 실패')

        except Exception as e:
            result['error'] = str(e)

        return result

    def _process_composites_sequential(
        self,
        scenes_to_composite: List[int],
        scene_map: Dict,
        scenes: List[Dict],
        project_path: str,
        generator,
        use_nano_banana: bool,
        model_key: str,
        prompt_type: str,
        bg_ref_strength: float,
        char_ref_strength: float,
        output_dir: Path,
        progress_bar,
        status_text,
        workflow_container,
        current_image_container
    ) -> Tuple[Dict, Dict]:
        """
        순차 처리 (v2.5) - 하나씩 처리하며 실시간 진행 상황 표시

        Returns:
            (results dict, generated_images dict)
        """
        results = {
            'success': [],
            'failed': [],
            'skipped': [],
            'generated': [],
            'total_cost': 0.0
        }
        generated_images = {}

        total = len(scenes_to_composite)

        for idx, scene_id in enumerate(scenes_to_composite):
            progress = (idx + 1) / total if total > 0 else 1.0
            progress_bar.progress(progress)
            status_text.markdown(f"**🎨 씬 {scene_id} 합성 중... ({idx + 1}/{total})**")

            # 워크플로우 정보 표시 (v2.5: 다중 캐릭터 지원)
            scene = scene_map.get(scene_id)
            if scene:
                paths = get_scene_image_paths(scene, project_path)
                prompts = get_scene_prompts(scene)
                prompt = prompts["full_en"] if prompt_type == "english" else prompts["full_ko"]

                # v2.5: 다중 캐릭터 이미지 조회
                all_char_images = get_all_character_images_for_scene(scene, project_path)

                with workflow_container:
                    self._render_workflow_info(
                        scene_id=scene_id,
                        bg_path=paths.get("background"),
                        char_path=paths.get("character"),
                        prompt=prompt,
                        model_key=model_key,
                        bg_ref_strength=bg_ref_strength,
                        char_ref_strength=char_ref_strength,
                        all_char_images=all_char_images
                    )

            # 단일 씬 합성
            result = self._composite_single_scene(
                scene_id=scene_id,
                scene_map=scene_map,
                project_path=project_path,
                generator=generator,
                use_nano_banana=use_nano_banana,
                model_key=model_key,
                prompt_type=prompt_type,
                bg_ref_strength=bg_ref_strength,
                char_ref_strength=char_ref_strength,
                output_dir=output_dir
            )

            if result['success']:
                output_path = result['output_path']
                generated_images[scene_id] = output_path

                # 씬 데이터 업데이트
                scene = scene_map.get(scene_id)
                if scene:
                    update_scene_image_path(
                        scene, "composite", output_path, scenes, project_path,
                        result.get('composite_info')
                    )

                # 워크플로우 상태 업데이트
                self.manager.mark_completed(2, {scene_id})

                results['success'].append(scene_id)
                results['generated'].append({
                    'scene_id': scene_id,
                    'output_path': output_path,
                    'prompt': result.get('prompt', ''),
                    'type': result.get('type', 'generated')
                })

                # 비용 추산
                cost = 0.012 if model_key == "gemini_nano_banana" else 0.020
                results['total_cost'] += cost

                print(f"[Step2] ✅ 씬 {scene_id} 합성 완료: {output_path}")
                current_image_container.image(output_path, caption=f"씬 {scene_id} 합성 완료", width=400)
            elif result.get('error') in ['배경 이미지 없음', '캐릭터 이미지 없음', '씬 데이터 없음']:
                results['skipped'].append({'scene': scene_id, 'reason': result['error']})
                print(f"[Step2] ⏭️ 씬 {scene_id} 스킵: {result['error']}")
            else:
                results['failed'].append({'scene': scene_id, 'reason': result.get('error', '합성 실패')})
                print(f"[Step2] ❌ 씬 {scene_id} 실패: {result.get('error')}")

            # API 레이트 리밋 방지
            if idx < total - 1 and use_nano_banana:
                time.sleep(1.5)

        return results, generated_images

    def _process_composites_batch(
        self,
        scenes_to_composite: List[int],
        scene_map: Dict,
        scenes: List[Dict],
        project_path: str,
        generator,
        use_nano_banana: bool,
        model_key: str,
        prompt_type: str,
        bg_ref_strength: float,
        char_ref_strength: float,
        output_dir: Path,
        max_workers: int,
        progress_bar,
        status_text
    ) -> Tuple[Dict, Dict]:
        """
        배치 처리 (v2.5) - ThreadPoolExecutor로 병렬 처리

        Returns:
            (results dict, generated_images dict)
        """
        results = {
            'success': [],
            'failed': [],
            'skipped': [],
            'generated': [],
            'total_cost': 0.0
        }
        generated_images = {}

        total = len(scenes_to_composite)
        completed = 0

        print(f"[Step2 Batch] 🚀 배치 처리 시작: {total}개 씬, {max_workers} 워커")
        status_text.markdown(f"**⚡ 배치 처리 중... (0/{total})**")

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 모든 작업 제출
            future_to_scene = {}
            for scene_id in scenes_to_composite:
                future = executor.submit(
                    self._composite_single_scene,
                    scene_id=scene_id,
                    scene_map=scene_map,
                    project_path=project_path,
                    generator=generator,
                    use_nano_banana=use_nano_banana,
                    model_key=model_key,
                    prompt_type=prompt_type,
                    bg_ref_strength=bg_ref_strength,
                    char_ref_strength=char_ref_strength,
                    output_dir=output_dir
                )
                future_to_scene[future] = scene_id

            # 완료된 작업 처리
            for future in as_completed(future_to_scene):
                scene_id = future_to_scene[future]
                completed += 1

                try:
                    result = future.result()

                    if result['success']:
                        output_path = result['output_path']
                        generated_images[scene_id] = output_path

                        # 씬 데이터 업데이트
                        scene = scene_map.get(scene_id)
                        if scene:
                            update_scene_image_path(
                                scene, "composite", output_path, scenes, project_path,
                                result.get('composite_info')
                            )

                        # 워크플로우 상태 업데이트
                        self.manager.mark_completed(2, {scene_id})

                        results['success'].append(scene_id)
                        results['generated'].append({
                            'scene_id': scene_id,
                            'output_path': output_path,
                            'prompt': result.get('prompt', ''),
                            'type': result.get('type', 'generated')
                        })

                        # 비용 추산
                        cost = 0.012 if model_key == "gemini_nano_banana" else 0.020
                        results['total_cost'] += cost

                        print(f"[Step2 Batch] ✅ 씬 {scene_id} 완료")
                    elif result.get('error') in ['배경 이미지 없음', '캐릭터 이미지 없음', '씬 데이터 없음']:
                        results['skipped'].append({'scene': scene_id, 'reason': result['error']})
                        print(f"[Step2 Batch] ⏭️ 씬 {scene_id} 스킵: {result['error']}")
                    else:
                        results['failed'].append({'scene': scene_id, 'reason': result.get('error', '합성 실패')})
                        print(f"[Step2 Batch] ❌ 씬 {scene_id} 실패: {result.get('error')}")

                except Exception as e:
                    results['failed'].append({'scene': scene_id, 'reason': str(e)})
                    print(f"[Step2 Batch] ❌ 씬 {scene_id} 예외: {e}")

                # 진행률 업데이트
                progress = completed / total
                progress_bar.progress(progress)
                status_text.markdown(f"**⚡ 배치 처리 중... ({completed}/{total})**")

        print(f"[Step2 Batch] ✅ 배치 처리 완료: 성공 {len(results['success'])}, 실패 {len(results['failed'])}, 스킵 {len(results['skipped'])}")

        return results, generated_images

    # ═══════════════════════════════════════════════════════════════
    # v2.0: 나노바나나 캐릭터 합성 실행 로직
    # ═══════════════════════════════════════════════════════════════

    def _execute_nano_banana_composite(
        self,
        scenes: List[Dict],
        scene_ids: List[int],
        composite_method: str,
        model_key: str,
        prompt_type: str,
        bg_ref_strength: float,
        char_ref_strength: float,
    ) -> Dict:
        """
        나노바나나 캐릭터 합성 실행 (v2.2 - 배경/캐릭터 강도 분리)

        묶음 내 첫 번째 씬(대표 씬)만 합성, 나머지 씬은 이미지 복사

        Args:
            scenes: 씬 데이터 리스트
            scene_ids: 합성할 씬 ID 리스트
            composite_method: 합성 방식
            model_key: 모델 키
            prompt_type: 프롬프트 언어 (english/korean)
            bg_ref_strength: 배경 레퍼런스 강도
            char_ref_strength: 캐릭터 레퍼런스 강도
        """
        results = {
            'success': [],
            'failed': [],
            'skipped': [],
            'generated': [],  # API 호출로 생성
            'copied': [],     # 복사된 씬
            'total_cost': 0.0,
        }

        if not scene_ids:
            st.warning("⚠️ 합성할 씬이 없습니다.")
            return results

        # 씬 맵 생성
        scene_map = {}
        for s in scenes:
            sid = s.get('scene_id', s.get('id', 0))
            if sid:
                scene_map[sid] = s

        project_path = str(self.project_path)

        # ═══════════════════════════════════════════════════════════════════
        # v2.4: 🔧 핵심 수정 - 묶음 모드에 따라 다른 방식 사용!
        # session_state에서 묶음 정보 가져오기 (기존 묶음 / 새 묶음)
        # ═══════════════════════════════════════════════════════════════════
        scenes_to_composite = []  # API 호출 대상 (묶음 대표 씬)
        scenes_to_copy = []       # 복사 대상 [{scene_id, source_scene_id}, ...]

        # v2.4: 묶음 모드 확인
        bundle_mode = st.session_state.get("step2_bundle_mode", "기존 묶음 사용")

        # v2.7: 항상 scene_ids에서 묶음 정보 재구축 (session state 의존 제거!)
        # scene_ids는 get_scenes_affected_by_selection()으로 확장된 전체 씬 목록이므로
        # 여기서 직접 묶음을 구축해야 정확한 대표/복사 분류가 됨
        if bundle_mode == "기존 묶음 사용":
            selected_bundles = self._create_bundles_from_existing_info(set(scene_ids), scenes)
            print(f"[Step2 Composite] ✅ 기존 bundle_id 기반 묶음 생성: {len(selected_bundles)}개 묶음")
        else:
            bundle_size = st.session_state.get("step2_bundle_size", 3)
            selected_bundles = self._create_simple_bundles(set(scene_ids), bundle_size)
            print(f"[Step2 Composite] 📦 새 묶음 생성: {len(selected_bundles)}개 묶음 ({bundle_size}개/묶음)")

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
                # 묶음에 속하지 않는 단독 씬 → 직접 합성
                scenes_to_composite.append(scene_id)
            else:
                bundle_id = bundle_info["bundle_id"]
                representative_id = bundle_info["representative_id"]

                if bundle_id not in processed_bundles:
                    # 이 묶음의 첫 번째 처리 → 대표 씬(첫 번째 씬) 합성
                    scenes_to_composite.append(representative_id)
                    processed_bundles[bundle_id] = representative_id
                elif scene_id != processed_bundles[bundle_id]:
                    # 이미 처리된 묶음의 다른 씬 → 복사 대상
                    source_scene_id = processed_bundles[bundle_id]
                    scenes_to_copy.append({
                        'scene_id': scene_id,
                        'source_scene_id': source_scene_id,
                        'bundle_id': bundle_id
                    })

        total_composite = len(scenes_to_composite)
        total_copy = len(scenes_to_copy)
        total = total_composite + total_copy

        print(f"\n[Step2 Composite] ═══════════════════════════════════════════════════════")
        print(f"[Step2 Composite] 📋 묶음 최적화 분석 완료")
        print(f"[Step2 Composite] 선택된 전체 씬: {len(scene_ids)}개")
        print(f"[Step2 Composite] API 합성 대상 (묶음 대표): {total_composite}개 → {scenes_to_composite}")
        print(f"[Step2 Composite] 복사 대상: {total_copy}개")
        print(f"[Step2 Composite] 💰 API 절약: {total_copy}회")
        print(f"[Step2 Composite] ═══════════════════════════════════════════════════════\n")

        st.markdown("### 🎨 배경+캐릭터 합성")

        # 묶음 최적화 정보 표시
        if total_copy > 0:
            st.info(f"""
                **📦 묶음 최적화 적용**
                - API 합성: **{total_composite}개** 씬 (묶음 대표만)
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
            # 출력 폴더 생성
            output_dir = Path(project_path) / "images" / "nano_composite"
            output_dir.mkdir(parents=True, exist_ok=True)

            # 생성된 이미지 경로 저장 (복사용)
            generated_images = {}  # scene_id → output_path

            # 레이어 합성 또는 나노바나나 합성
            use_nano_banana = "Nano Banana" in composite_method

            if use_nano_banana:
                generator = GeminiImageGenerator()
            else:
                generator = None

            # ═══════════════════════════════════════════════════════════════════
            # 1단계: 묶음 대표 씬 합성 (API 호출) - v2.5: 배치/순차 처리 지원
            # ═══════════════════════════════════════════════════════════════════
            processing_mode = st.session_state.get("step2_processing_mode", "순차 처리")

            if processing_mode == "배치 처리":
                max_workers = st.session_state.get("step2_max_workers", 4)
                st.markdown(f"#### ⚡ 1단계: API 합성 (배치 모드, {max_workers} 워커)")

                api_results, generated_images = self._process_composites_batch(
                    scenes_to_composite=scenes_to_composite,
                    scene_map=scene_map,
                    scenes=scenes,
                    project_path=project_path,
                    generator=generator,
                    use_nano_banana=use_nano_banana,
                    model_key=model_key,
                    prompt_type=prompt_type,
                    bg_ref_strength=bg_ref_strength,
                    char_ref_strength=char_ref_strength,
                    output_dir=output_dir,
                    max_workers=max_workers,
                    progress_bar=progress_bar,
                    status_text=status_text
                )
            else:
                st.markdown("#### 🎨 1단계: API 합성 (순차 모드)")

                api_results, generated_images = self._process_composites_sequential(
                    scenes_to_composite=scenes_to_composite,
                    scene_map=scene_map,
                    scenes=scenes,
                    project_path=project_path,
                    generator=generator,
                    use_nano_banana=use_nano_banana,
                    model_key=model_key,
                    prompt_type=prompt_type,
                    bg_ref_strength=bg_ref_strength,
                    char_ref_strength=char_ref_strength,
                    output_dir=output_dir,
                    progress_bar=progress_bar,
                    status_text=status_text,
                    workflow_container=workflow_container,
                    current_image_container=current_image_container
                )

            # 결과 병합
            results['success'].extend(api_results['success'])
            results['failed'].extend(api_results['failed'])
            results['skipped'].extend(api_results['skipped'])
            results['generated'].extend(api_results['generated'])
            results['total_cost'] += api_results['total_cost']

            # ═══════════════════════════════════════════════════════════════════
            # 2단계: 묶음 내 다른 씬에 이미지 복사
            # ═══════════════════════════════════════════════════════════════════
            if scenes_to_copy:
                st.markdown("#### 📋 2단계: 이미지 복사 (같은 묶음 내)")

                for copy_info in scenes_to_copy:
                    scene_id = copy_info['scene_id']
                    source_scene_id = copy_info['source_scene_id']
                    bundle_id = copy_info['bundle_id']

                    source_image_path = generated_images.get(source_scene_id)

                    if source_image_path and os.path.exists(source_image_path):
                        try:
                            # 복사본 생성
                            timestamp = int(time.time() * 1000)
                            output_path = str(output_dir / f"composite_scene_{scene_id:03d}_{timestamp}.png")

                            shutil.copy2(source_image_path, output_path)

                            # 씬 데이터 업데이트
                            scene = scene_map.get(scene_id)
                            if scene:
                                scene['nano_composite_image'] = output_path

                            # 워크플로우 상태 업데이트
                            self.manager.mark_completed(2, {scene_id})

                            results['success'].append(scene_id)
                            results['copied'].append({
                                'scene_id': scene_id,
                                'source_scene_id': source_scene_id,
                                'output_path': output_path,
                                'bundle_id': bundle_id,
                                'type': 'copied'
                            })

                            print(f"[Step2] 📋 씬 {scene_id}: 씬 {source_scene_id} 이미지 복사됨")

                        except Exception as e:
                            results['failed'].append({'scene': scene_id, 'reason': f'복사 실패: {e}'})
                    else:
                        results['failed'].append({
                            'scene': scene_id,
                            'reason': f'원본 이미지 없음 (씬 {source_scene_id})'
                        })

                # v2.7: 복사된 경로를 scenes.json에 저장 (디스크 영속화)
                try:
                    scenes_path = Path(project_path) / "analysis" / "scenes.json"
                    if scenes_path.exists():
                        with open(scenes_path, 'w', encoding='utf-8') as f:
                            json.dump(scenes, f, ensure_ascii=False, indent=2)
                        print(f"[Step2] 📋 복사된 {len(results['copied'])}개 씬 경로 scenes.json 저장 완료")
                except Exception as e:
                    print(f"[Step2] ⚠️ scenes.json 저장 실패: {e}")

            # 완료
            progress_bar.progress(1.0)
            status_text.markdown("**✅ 캐릭터 합성 완료!**")
            current_image_container.empty()

            # 워크플로우 상태 저장
            self.manager.save()

            # 결과 요약 표시
            with result_container:
                self._render_composite_results(results)

        except Exception as e:
            st.error(f"❌ 합성 중 오류 발생: {e}")
            import traceback
            st.code(traceback.format_exc())
            print(f"[Step2] ❌ 합성 오류: {e}")

        return results

    def _render_workflow_info(
        self,
        scene_id: int,
        bg_path: str,
        char_path: str,
        prompt: str,
        model_key: str,
        bg_ref_strength: float,
        char_ref_strength: float,
        all_char_images: List[Dict] = None
    ):
        """워크플로우 정보 표시 (레퍼런스 이미지 + 프롬프트) v2.5: 다중 캐릭터 지원"""
        with st.expander(f"📋 씬 {scene_id} 합성 정보", expanded=False):
            # v2.5: 다중 캐릭터가 있으면 열 수 조정
            has_multi_char = all_char_images and len([c for c in all_char_images if c.get('exists')]) > 1

            if has_multi_char:
                # 다중 캐릭터: 배경 + 캐릭터들 + 프롬프트
                char_count = len([c for c in all_char_images if c.get('exists')])
                cols = st.columns([1] + [1] * min(char_count, 3) + [2])
            else:
                cols = st.columns([1, 1, 2])

            with cols[0]:
                st.markdown(f"**🏞️ 배경 ({int(bg_ref_strength*100)}%)**")
                if bg_path and os.path.exists(bg_path):
                    st.image(bg_path, width=150)
                else:
                    st.warning("배경 이미지 없음")

            if has_multi_char:
                # v2.5: 다중 캐릭터 표시
                char_idx = 1
                for char_info in all_char_images[:3]:  # 최대 3개까지 표시
                    if char_info.get('exists') and char_info.get('path'):
                        with cols[char_idx]:
                            char_name = char_info.get('name', f'캐릭터 {char_idx}')
                            st.markdown(f"**👤 {char_name} ({int(char_ref_strength*100)}%)**")
                            st.image(char_info['path'], width=120)
                        char_idx += 1

                # 프롬프트는 마지막 열에
                prompt_col_idx = min(char_count, 3) + 1
            else:
                with cols[1]:
                    st.markdown(f"**👤 캐릭터 ({int(char_ref_strength*100)}%)**")
                    if char_path and os.path.exists(char_path):
                        st.image(char_path, width=150)
                    else:
                        st.warning("캐릭터 이미지 없음")
                prompt_col_idx = 2

            with cols[prompt_col_idx] if has_multi_char else cols[2]:
                st.markdown("**📝 합성 프롬프트**")
                st.text_area(
                    "프롬프트",
                    prompt,
                    height=100,
                    key=f"workflow_composite_prompt_{scene_id}",
                    disabled=True,
                    label_visibility="collapsed"
                )
                char_info_text = f"배경 {int(bg_ref_strength*100)}% / 캐릭터 {int(char_ref_strength*100)}%"
                if has_multi_char:
                    char_info_text += f" (👥 {char_count}명)"
                st.caption(f"모델: {model_key} | {char_info_text}")

    def _build_prompt_with_separate_strengths(
        self,
        base_prompt: str,
        has_bg: bool,
        has_char: bool,
        bg_strength: float,
        char_strength: float
    ) -> str:
        """
        배경/캐릭터 개별 레퍼런스 강도를 반영한 프롬프트 구성 (v2.2)

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
                hints.append(f"Keep the background style, colors and composition very closely ({int(bg_strength * 100)}%)")
            elif bg_strength >= 0.5:
                hints.append(f"Maintain the general background atmosphere ({int(bg_strength * 100)}%)")
            elif bg_strength > 0:
                hints.append(f"Use the background as a loose reference ({int(bg_strength * 100)}%)")

        # 캐릭터 강도 힌트
        if has_char:
            if char_strength >= 0.8:
                hints.append(f"Accurately reproduce the character's appearance and pose ({int(char_strength * 100)}%)")
            elif char_strength >= 0.5:
                hints.append(f"Maintain the character's general features ({int(char_strength * 100)}%)")
            elif char_strength > 0:
                hints.append(f"Freely interpret the character with minimal reference ({int(char_strength * 100)}%)")

        if hints:
            hint_text = ". ".join(hints)
            return f"{hint_text}. {base_prompt}"

        return base_prompt

    def _render_composite_results(self, results: Dict):
        """합성 결과 상세 표시"""
        st.markdown("### 📊 결과 요약")

        generated = results.get('generated', [])
        copied = results.get('copied', [])
        failed = results.get('failed', [])
        skipped = results.get('skipped', [])
        total_cost = results.get('total_cost', 0)

        # 통계 카드
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            st.metric("✅ 성공", len(results['success']))
        with col2:
            st.metric("🎨 API 합성", len(generated))
        with col3:
            st.metric("📋 복사", len(copied))
        with col4:
            st.metric("❌ 실패", len(failed))
        with col5:
            st.metric("💰 예상 비용", f"${total_cost:.3f}")

        # 상세 정보 - API 합성된 씬
        if generated:
            with st.expander(f"🎨 API로 합성된 씬 ({len(generated)}개)", expanded=True):
                cols = st.columns(min(3, len(generated)))
                for i, item in enumerate(generated[:6]):
                    with cols[i % 3]:
                        if item.get('output_path') and os.path.exists(item['output_path']):
                            st.image(item['output_path'], caption=f"씬 {item['scene_id']}", use_container_width=True)

        # 상세 정보 - 복사된 씬
        if copied:
            with st.expander(f"📋 복사된 씬 ({len(copied)}개) - 💰 API 절약!", expanded=False):
                for item in copied:
                    st.markdown(f"**씬 {item['scene_id']}** ← 씬 {item['source_scene_id']} (묶음 {item['bundle_id']})")

        # 실패/스킵 정보
        if failed:
            with st.expander(f"❌ 실패한 씬 ({len(failed)}개)", expanded=False):
                for item in failed:
                    st.error(f"씬 {item['scene']}: {item.get('reason', '알 수 없는 오류')}")

        if skipped:
            with st.expander(f"⏭️ 스킵된 씬 ({len(skipped)}개)", expanded=False):
                for item in skipped:
                    st.warning(f"씬 {item['scene']}: {item.get('reason', '알 수 없는 이유')}")

    def _composite_with_pil(
        self,
        bg_path: str,
        char_path: str,
        output_dir: Path,
        scene_id: int,
        position: str,
        scale: float
    ) -> Dict:
        """PIL을 사용한 레이어 합성"""
        if not PIL_AVAILABLE:
            return {'success': False, 'error': 'PIL 라이브러리 없음'}

        try:
            # 이미지 로드
            background = Image.open(bg_path).convert('RGBA')
            character = Image.open(char_path).convert('RGBA')

            bg_width, bg_height = background.size

            # 캐릭터 크기 조정
            char_width, char_height = character.size
            target_height = int(bg_height * scale)
            ratio = target_height / char_height
            target_width = int(char_width * ratio)

            character_resized = character.resize(
                (target_width, target_height),
                Image.Resampling.LANCZOS
            )

            # 위치 매핑
            position_map = {
                "자동 (AI 추천)": "center",
                "왼쪽 하단": "left",
                "오른쪽 하단": "right",
                "중앙 하단": "center"
            }
            pos = position_map.get(position, "center")

            # 위치 계산
            if pos == 'center':
                x = (bg_width - target_width) // 2
            elif pos == 'left':
                x = int(bg_width * 0.1)
            elif pos == 'right':
                x = bg_width - target_width - int(bg_width * 0.1)
            else:
                x = (bg_width - target_width) // 2

            y = bg_height - target_height  # 하단 정렬

            # 합성
            result = background.copy()
            result.paste(character_resized, (x, y), character_resized)

            # 저장
            timestamp = int(time.time() * 1000)
            output_path = str(output_dir / f"composite_scene_{scene_id:03d}_{timestamp}.png")
            result.save(output_path, 'PNG')

            print(f"[Step2] ✅ PIL 합성 완료: {output_path}")

            return {'success': True, 'output_path': output_path}

        except Exception as e:
            print(f"[Step2] ❌ PIL 합성 실패: {e}")
            return {'success': False, 'error': str(e)}


    # ═══════════════════════════════════════════════════════════════
    # v2.4: 기존 bundle_id 기반 묶음 최적화 (Step1과 동일)
    # ═══════════════════════════════════════════════════════════════

    def _get_bundle_info_from_scenes(self, scenes: List[Dict]) -> Dict[int, Dict]:
        """
        scenes.json에서 기존 묶음 정보 추출 (v2.4)

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
            print(f"[Step2] 📋 기존 묶음 정보: {len(scene_to_bundle)}개 씬 → {unique_bundles}개 묶음")

        return scene_to_bundle

    def _create_bundles_from_existing_info(
        self,
        selected_scene_ids: Set[int],
        scenes: List[Dict]
    ) -> List[Dict]:
        """
        기존 bundle_id를 참조하여 선택된 씬들을 묶음으로 그룹화 (v2.4)

        Args:
            selected_scene_ids: 선택된 씬 ID 집합
            scenes: 전체 씬 데이터 (bundle_id 포함)

        Returns:
            묶음 리스트 [{"bundle_id": 1, "scene_ids": [47, 48], "representative_id": 47}, ...]

        예시:
            selected_scene_ids: {47, 48} (같은 묶음)
            scenes.json bundle_id: 씬 47,48 → 묶음2

            결과:
            - 묶음 1: [47, 48] (둘 다 포함, API는 47만!)
        """
        if not selected_scene_ids:
            return []

        # 1. 기존 묶음 정보 추출 (scene_id → bundle_info)
        scene_to_bundle = self._get_bundle_info_from_scenes(scenes)

        # bundle_id → [all scene_ids] 맵 생성
        bundle_id_to_all_scenes = {}
        for scene in scenes:
            scene_id = scene.get('scene_id', scene.get('id', 0))
            bundle_id = scene.get('bundle_id')
            if scene_id and bundle_id is not None:
                if bundle_id not in bundle_id_to_all_scenes:
                    bundle_id_to_all_scenes[bundle_id] = []
                bundle_id_to_all_scenes[bundle_id].append(scene_id)

        # 2. 선택된 씬이 속한 묶음의 전체 씬 포함
        bundle_groups = {}  # bundle_id → [scene_ids]
        processed_bundle_ids = set()

        for scene_id in selected_scene_ids:
            bundle_info = scene_to_bundle.get(scene_id)

            if bundle_info:
                orig_bundle_id = bundle_info["bundle_id"]

                # 이미 처리된 묶음이면 스킵
                if orig_bundle_id in processed_bundle_ids:
                    continue

                # v2.7: 해당 묶음의 전체 씬 추가 (selected_scene_ids 필터 제거!)
                # pool에는 대표 씬만 포함되므로, 여기서 필터링하면 묶음이 1개 씬만 갖게 됨
                # 묶음 내 모든 씬을 포함해야 대표 씬만 API 호출하고 나머지는 복사 가능
                all_scenes_in_bundle = bundle_id_to_all_scenes.get(orig_bundle_id, [scene_id])
                bundle_groups[orig_bundle_id] = all_scenes_in_bundle
                processed_bundle_ids.add(orig_bundle_id)

                print(f"[Step2] v2.7: 묶음 {orig_bundle_id} - 전체 씬 {all_scenes_in_bundle}")
            else:
                # bundle_id가 없는 씬은 개별 묶음으로 처리
                individual_bundle_id = -scene_id
                bundle_groups[individual_bundle_id] = [scene_id]

        # 3. 묶음 리스트 생성
        bundles = []
        new_bundle_id = 1

        for orig_bundle_id in sorted(bundle_groups.keys()):
            scene_ids = sorted(bundle_groups[orig_bundle_id])

            bundles.append({
                "bundle_id": new_bundle_id,
                "original_bundle_id": orig_bundle_id,
                "scene_ids": scene_ids,
                "scene_range": self._format_scene_range(scene_ids),
                "representative_id": scene_ids[0]  # 대표 씬 = 첫 번째 씬
            })

            new_bundle_id += 1

        # 디버그 로그
        total_scenes = sum(len(b["scene_ids"]) for b in bundles)
        print(f"\n[Step2] ========== 🔧 기존 묶음 기반 그룹화 (v2.7) ==========")
        print(f"[Step2] 선택된 씬: {len(selected_scene_ids)}개 → {sorted(selected_scene_ids)}")
        print(f"[Step2] 생성된 묶음: {len(bundles)}개")

        for b in bundles:
            orig_id = b.get("original_bundle_id", "?")
            print(f"[Step2] ✅ 묶음 {b['bundle_id']} (원본 {orig_id}): {b['scene_range']} ({len(b['scene_ids'])}개)")

        print(f"[Step2] ==========================================================\n")

        return bundles


def render_step2_ui(manager, scenes: List[Dict], project_path: Path):
    """Step 2 UI 렌더 함수"""
    ui = Step2CharacterUI(manager, project_path)
    return ui.render(scenes)
