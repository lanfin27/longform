# -*- coding: utf-8 -*-
"""
AI 텍스트 전처리 패널 컴포넌트

TTS 생성 전 영어 단어/약어를 AI로 변환하는 UI 컴포넌트

사용법:
    from components.ai_preprocessing_panel import render_ai_preprocessing_panel

    # TTS 페이지에서 씬 데이터와 함께 호출
    result = render_ai_preprocessing_panel(
        scenes=scenes,
        session_key="tts_preprocess",
        language="ko"
    )

    if result["use_preprocessed"]:
        scenes_to_use = result["preprocessed_scenes"]
    else:
        scenes_to_use = scenes
"""

import streamlit as st
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

from utils.ai_model_selector import render_model_selector, get_selected_model
from utils.ai_providers import get_available_models, get_model
from utils.ai_text_preprocessor import preprocess_scenes_sync, PreprocessResult


@dataclass
class PreprocessPanelResult:
    """전처리 패널 결과"""
    use_preprocessed: bool  # 전처리된 텍스트 사용 여부
    preprocessed_scenes: List[Dict]  # 전처리된 씬 데이터
    original_scenes: List[Dict]  # 원본 씬 데이터
    total_changes: int  # 총 변경 수
    model_used: str  # 사용된 모델


# 언어 옵션
LANGUAGE_OPTIONS = {
    "ko": "한국어",
    "ja": "일본어",
    "zh": "중국어"
}


def render_ai_preprocessing_panel(
    scenes: List[Dict],
    session_key: str = "ai_preprocess",
    default_language: str = "ko",
    show_preview: bool = True,
    expanded: bool = False
) -> Dict:
    """
    AI 텍스트 전처리 패널 렌더링

    Args:
        scenes: 씬 데이터 리스트 [{"scene_id": 1, "text": "..."}, ...]
        session_key: 세션 상태 키 접두사
        default_language: 기본 언어
        show_preview: 미리보기 표시 여부
        expanded: 확장 상태

    Returns:
        {
            "use_preprocessed": bool,
            "preprocessed_scenes": List[Dict],
            "original_scenes": List[Dict],
            "total_changes": int,
            "model_used": str
        }
    """
    # ⭐ 씬 선택이 변경되면 캐시 무효화
    current_scene_ids = tuple(s.get("scene_id", i) for i, s in enumerate(scenes))
    cached_scene_ids = st.session_state.get(f"{session_key}_cached_scene_ids")

    if cached_scene_ids != current_scene_ids:
        # 씬 선택이 변경됨 - 캐시 무효화
        if cached_scene_ids is not None:
            print(f"[AI Preprocess] 씬 선택 변경 감지: {len(cached_scene_ids) if cached_scene_ids else 0}개 → {len(current_scene_ids)}개, 캐시 무효화")
        st.session_state[f"{session_key}_preprocessed_scenes"] = None
        st.session_state[f"{session_key}_use_preprocessed"] = False
        st.session_state[f"{session_key}_total_changes"] = 0
        st.session_state[f"{session_key}_cached_scene_ids"] = current_scene_ids

    # 세션 상태 초기화
    if f"{session_key}_preprocessed_scenes" not in st.session_state:
        st.session_state[f"{session_key}_preprocessed_scenes"] = None
    if f"{session_key}_use_preprocessed" not in st.session_state:
        st.session_state[f"{session_key}_use_preprocessed"] = False
    if f"{session_key}_total_changes" not in st.session_state:
        st.session_state[f"{session_key}_total_changes"] = 0

    result = {
        "use_preprocessed": False,
        "preprocessed_scenes": scenes,
        "original_scenes": scenes,
        "total_changes": 0,
        "model_used": ""
    }

    # AI 모델 사용 가능 여부 확인
    available_models = get_available_models()
    if not available_models:
        st.info("AI 전처리를 사용하려면 API 키를 설정하세요 (ANTHROPIC_API_KEY, GOOGLE_API_KEY, OPENAI_API_KEY)")
        return result

    with st.expander("AI 텍스트 전처리 (영어 → 발음 변환)", expanded=expanded):
        st.caption("영어 단어와 약어를 TTS에 적합한 발음으로 변환합니다.")

        # 설정 영역
        col1, col2 = st.columns([1, 1])

        with col1:
            # 언어 선택
            language = st.selectbox(
                "목표 언어",
                options=list(LANGUAGE_OPTIONS.keys()),
                format_func=lambda x: LANGUAGE_OPTIONS[x],
                index=list(LANGUAGE_OPTIONS.keys()).index(default_language),
                key=f"{session_key}_language"
            )

        with col2:
            # AI 모델 선택 (컴팩트)
            selected_model = render_model_selector(
                key=f"{session_key}_model",
                task="text_preprocessing",
                show_provider_filter=False,
                show_speed_filter=False,
                show_details=False,
                compact=True
            )

        # 전처리 실행 버튼
        col_btn1, col_btn2 = st.columns([1, 1])

        with col_btn1:
            if st.button("AI 전처리 실행", key=f"{session_key}_run", use_container_width=True):
                _run_preprocessing(scenes, language, selected_model, session_key)

        with col_btn2:
            # 전처리 결과가 있으면 초기화 버튼 표시
            if st.session_state.get(f"{session_key}_preprocessed_scenes"):
                if st.button("전처리 초기화", key=f"{session_key}_reset", use_container_width=True):
                    st.session_state[f"{session_key}_preprocessed_scenes"] = None
                    st.session_state[f"{session_key}_use_preprocessed"] = False
                    st.session_state[f"{session_key}_total_changes"] = 0
                    st.rerun()

        # 전처리 결과 표시
        preprocessed_scenes = st.session_state.get(f"{session_key}_preprocessed_scenes")

        if preprocessed_scenes:
            total_changes = st.session_state.get(f"{session_key}_total_changes", 0)
            model_used = st.session_state.get(f"{session_key}_model_used", "")

            st.success(f"전처리 완료: {total_changes}개 항목 변환됨 ({model_used})")

            # 사용 여부 선택
            use_preprocessed = st.checkbox(
                "전처리된 텍스트 사용",
                value=st.session_state.get(f"{session_key}_use_preprocessed", False),
                key=f"{session_key}_use_checkbox"
            )
            st.session_state[f"{session_key}_use_preprocessed"] = use_preprocessed

            # 미리보기
            if show_preview and total_changes > 0:
                _render_preview(scenes, preprocessed_scenes, session_key)

            result["use_preprocessed"] = use_preprocessed
            result["preprocessed_scenes"] = preprocessed_scenes if use_preprocessed else scenes
            result["total_changes"] = total_changes
            result["model_used"] = model_used

    return result


def _run_preprocessing(
    scenes: List[Dict],
    language: str,
    model_id: str,
    session_key: str
):
    """전처리 실행"""
    if not scenes:
        st.warning("전처리할 씬이 없습니다.")
        return

    progress_bar = st.progress(0)
    status_text = st.empty()

    def progress_callback(current: int, total: int, result: PreprocessResult):
        progress = current / total
        progress_bar.progress(progress)
        status_text.text(f"전처리 중... ({current}/{total})")

    try:
        status_text.text("AI 전처리 시작...")

        # 전처리 실행
        preprocessed = preprocess_scenes_sync(
            scenes=scenes,
            language=language,
            model_id=model_id,
            progress_callback=progress_callback
        )

        # 변경 수 계산
        total_changes = sum(
            len(s.get("preprocess_changes", []))
            for s in preprocessed
        )

        # 세션 상태 저장
        st.session_state[f"{session_key}_preprocessed_scenes"] = preprocessed
        st.session_state[f"{session_key}_total_changes"] = total_changes
        st.session_state[f"{session_key}_use_preprocessed"] = True
        st.session_state[f"{session_key}_model_used"] = model_id

        progress_bar.progress(1.0)
        status_text.text("전처리 완료!")

        st.rerun()

    except Exception as e:
        st.error(f"전처리 오류: {e}")
        progress_bar.empty()
        status_text.empty()


def _render_preview(
    original_scenes: List[Dict],
    preprocessed_scenes: List[Dict],
    session_key: str
):
    """변경 사항 미리보기"""
    # 변경 타입 한글 표시
    TYPE_LABELS = {
        "comma_number": "숫자",
        "year": "연도",
        "month": "월",
        "day": "일",
        "percent": "퍼센트",
        "number_unit": "숫자+단위",
        "decimal": "소수",
        "english": "영어"
    }

    with st.expander("변경 사항 미리보기", expanded=False):
        for idx, (orig, prep) in enumerate(zip(original_scenes, preprocessed_scenes)):
            changes = prep.get("preprocess_changes", [])
            if not changes:
                continue

            scene_id = prep.get("scene_id", idx + 1)
            st.markdown(f"**씬 {scene_id}** ({len(changes)}개 변경)")

            # 변경 사항 테이블
            for change in changes:
                change_type = change.get("type", "")
                type_label = TYPE_LABELS.get(change_type, change_type)
                col1, col2, col3, col4 = st.columns([2, 0.5, 2, 1])
                with col1:
                    st.code(change.get("original", ""), language=None)
                with col2:
                    st.markdown("→")
                with col3:
                    st.code(change.get("converted", ""), language=None)
                with col4:
                    st.caption(f"[{type_label}]")

            # 원본 vs 변환 비교
            tabs = st.tabs(["원본", "변환"])
            with tabs[0]:
                st.text(orig.get("text", "")[:500] + "..." if len(orig.get("text", "")) > 500 else orig.get("text", ""))
            with tabs[1]:
                st.text(prep.get("preprocessed_text", "")[:500] + "..." if len(prep.get("preprocessed_text", "")) > 500 else prep.get("preprocessed_text", ""))

            st.divider()


def get_preprocessed_text(scene: Dict) -> str:
    """
    씬에서 전처리된 텍스트 반환

    Args:
        scene: 씬 데이터

    Returns:
        전처리된 텍스트 또는 원본 텍스트
    """
    return scene.get("preprocessed_text") or scene.get("text", "")


def apply_preprocessing_to_scenes(
    scenes: List[Dict],
    session_key: str = "ai_preprocess"
) -> List[Dict]:
    """
    세션 상태의 전처리 결과를 씬에 적용

    Args:
        scenes: 원본 씬 데이터
        session_key: 세션 상태 키 접두사

    Returns:
        전처리 적용된 씬 (또는 원본)
    """
    if not st.session_state.get(f"{session_key}_use_preprocessed"):
        return scenes

    preprocessed = st.session_state.get(f"{session_key}_preprocessed_scenes")
    if not preprocessed:
        return scenes

    # 씬 ID로 매칭
    preprocessed_map = {}
    for ps in preprocessed:
        scene_id = ps.get("scene_id")
        if scene_id:
            preprocessed_map[scene_id] = ps

    result = []
    for scene in scenes:
        scene_id = scene.get("scene_id")
        if scene_id and scene_id in preprocessed_map:
            # 전처리된 텍스트 적용
            scene_copy = dict(scene)
            ps = preprocessed_map[scene_id]
            scene_copy["text"] = ps.get("preprocessed_text") or scene.get("text", "")
            scene_copy["original_text"] = scene.get("text", "")
            result.append(scene_copy)
        else:
            result.append(scene)

    return result


# ============================================================
# 단순화된 인터페이스
# ============================================================

def render_simple_preprocessing_toggle(
    scenes: List[Dict],
    session_key: str = "ai_preprocess"
) -> Tuple[bool, List[Dict]]:
    """
    간단한 전처리 토글 UI

    Returns:
        (사용 여부, 씬 데이터)
    """
    # 이미 전처리가 완료된 경우
    if st.session_state.get(f"{session_key}_preprocessed_scenes"):
        use = st.checkbox(
            "AI 전처리 사용",
            value=st.session_state.get(f"{session_key}_use_preprocessed", False),
            key=f"{session_key}_simple_toggle",
            help="영어 단어를 발음으로 변환합니다"
        )
        st.session_state[f"{session_key}_use_preprocessed"] = use

        if use:
            return True, st.session_state[f"{session_key}_preprocessed_scenes"]
        return False, scenes

    return False, scenes
