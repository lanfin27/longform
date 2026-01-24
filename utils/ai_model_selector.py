# -*- coding: utf-8 -*-
"""
AI 모델 선택 UI 컴포넌트 v1.0

Streamlit용 멀티 프로바이더 모델 선택 위젯

기능:
- 프로바이더 필터 (Anthropic/Google/OpenAI)
- 속도 필터 (빠름/균형/고품질)
- 통합 모델 드롭다운
- API 키 상태 표시
"""

import streamlit as st
from typing import Optional
from .ai_providers import (
    AIProvider, AIModel, ALL_MODELS,
    get_available_models, get_available_providers,
    get_model, get_provider_display, PROVIDER_INFO,
    check_api_key, get_default_model
)


def render_model_selector(
    key: str = "ai_model",
    task: str = "scene_analysis",
    show_provider_filter: bool = True,
    show_speed_filter: bool = True,
    show_details: bool = True,
    compact: bool = False
) -> str:
    """
    AI 모델 선택 UI 렌더링

    Args:
        key: Streamlit 위젯 키
        task: 작업 유형 (기본 모델 결정용)
        show_provider_filter: 프로바이더 필터 표시
        show_speed_filter: 속도 필터 표시
        show_details: 모델 상세 정보 표시
        compact: 컴팩트 모드

    Returns:
        선택된 모델 ID
    """

    # 사용 가능한 모델 (API 키 있는 것만)
    available_models = get_available_models()

    if not available_models:
        st.error("⚠️ 사용 가능한 AI 모델이 없습니다. API 키를 설정해주세요.")
        with st.expander("🔑 API 키 설정 방법"):
            st.markdown("""
            환경 변수에 다음 중 하나 이상을 설정하세요:
            - `ANTHROPIC_API_KEY`: Claude 모델 사용
            - `GOOGLE_API_KEY`: Gemini 모델 사용
            - `OPENAI_API_KEY`: GPT 모델 사용
            """)
        return None

    # 기본 모델 설정
    default_model = get_default_model(task)
    if default_model not in available_models:
        default_model = list(available_models.keys())[0]

    # 세션 상태 초기화
    if f"{key}_model" not in st.session_state:
        st.session_state[f"{key}_model"] = default_model

    # 컴팩트 모드
    if compact:
        return _render_compact_selector(key, available_models)

    # 필터링된 모델
    filtered_models = available_models.copy()

    # 필터 UI
    if show_provider_filter or show_speed_filter:
        filter_cols = st.columns(2)

        # 프로바이더 필터
        if show_provider_filter:
            with filter_cols[0]:
                available_providers = get_available_providers()
                provider_options = ["🌐 전체"]
                for p in available_providers:
                    provider_options.append(get_provider_display(p))

                selected_provider = st.selectbox(
                    "프로바이더",
                    options=provider_options,
                    key=f"{key}_provider_filter",
                    help="API 키가 설정된 프로바이더만 표시됩니다"
                )

                if selected_provider != "🌐 전체":
                    # 선택된 프로바이더의 모델만 필터링
                    for p in AIProvider:
                        if get_provider_display(p) == selected_provider:
                            filtered_models = {
                                k: v for k, v in filtered_models.items()
                                if v.provider == p
                            }
                            break

        # 속도 필터
        if show_speed_filter:
            with filter_cols[1]:
                speed_options = {
                    "🌐 전체": "all",
                    "⚡ 빠름": "fast",
                    "⚖️ 균형": "medium",
                    "🎯 고품질": "slow"
                }

                selected_speed = st.selectbox(
                    "속도/품질",
                    options=list(speed_options.keys()),
                    key=f"{key}_speed_filter",
                    help="빠른 모델은 속도가 빠르지만 품질이 낮을 수 있습니다"
                )

                speed_value = speed_options[selected_speed]
                if speed_value != "all":
                    filtered_models = {
                        k: v for k, v in filtered_models.items()
                        if v.speed == speed_value
                    }

    # 필터 결과 확인
    if not filtered_models:
        st.warning("선택한 필터에 해당하는 모델이 없습니다. 필터를 조정해주세요.")
        return st.session_state.get(f"{key}_model", default_model)

    # 모델 옵션 생성
    model_options = _create_model_options(filtered_models)

    # 현재 선택된 모델이 필터링된 목록에 있는지 확인
    current_model = st.session_state.get(f"{key}_model", default_model)
    if current_model not in filtered_models:
        current_model = list(filtered_models.keys())[0]

    # 현재 모델의 레이블 찾기
    current_label = None
    for label, model_id in model_options.items():
        if model_id == current_model:
            current_label = label
            break

    if not current_label:
        current_label = list(model_options.keys())[0]

    # 모델 선택 드롭다운
    selected_label = st.selectbox(
        "🤖 AI 모델",
        options=list(model_options.keys()),
        index=list(model_options.keys()).index(current_label) if current_label in model_options else 0,
        key=f"{key}_model_select"
    )

    selected_model_id = model_options[selected_label]
    st.session_state[f"{key}_model"] = selected_model_id

    # 모델 상세 정보 표시
    if show_details:
        model_info = get_model(selected_model_id)
        if model_info:
            st.caption(f"{model_info.description}")

    return selected_model_id


def _create_model_options(models: dict) -> dict:
    """모델 드롭다운 옵션 생성"""
    options = {}
    for model_id, model in models.items():
        provider_icon = PROVIDER_INFO.get(model.provider, {}).get("icon", "")
        speed_icon = {"fast": "⚡", "medium": "⚖️", "slow": "🎯"}.get(model.speed, "")

        # Claude Code 특별 처리 (무료 표시)
        if model_id == "claude_code":
            label = f"{provider_icon} {model.name} 🆓"
        else:
            label = f"{provider_icon} {model.name} {speed_icon}"

        options[label] = model_id
    return options


def _render_compact_selector(key: str, models: dict) -> str:
    """컴팩트 모드 선택기"""

    options = _create_model_options(models)

    current = st.session_state.get(f"{key}_model", list(models.keys())[0])
    current_label = None
    for label, mid in options.items():
        if mid == current:
            current_label = label
            break

    if not current_label:
        current_label = list(options.keys())[0]

    selected = st.selectbox(
        "🤖 AI 모델",
        options=list(options.keys()),
        index=list(options.keys()).index(current_label) if current_label in options else 0,
        key=f"{key}_compact"
    )

    selected_model = options[selected]
    st.session_state[f"{key}_model"] = selected_model

    return selected_model


def render_api_key_status():
    """API 키 상태 표시"""

    st.markdown("##### 🔑 API 키 상태")

    cols = st.columns(4)

    providers = [
        (AIProvider.ANTHROPIC, "ANTHROPIC_API_KEY", "Claude"),
        (AIProvider.GOOGLE, "GOOGLE_API_KEY", "Gemini"),
        (AIProvider.OPENAI, "OPENAI_API_KEY", "GPT"),
        (AIProvider.LOCAL, "", "Claude Code")  # CLI 설치 확인
    ]

    for i, (provider, env_var, name) in enumerate(providers):
        with cols[i]:
            has_key = check_api_key(provider)
            icon = PROVIDER_INFO.get(provider, {}).get("icon", "")

            if has_key:
                st.success(f"{icon} {name} ✅")
            else:
                st.error(f"{icon} {name} ❌")
                if provider == AIProvider.LOCAL:
                    st.caption("CLI 설치 필요")
                else:
                    st.caption(f"`{env_var}` 필요")


def render_model_badge(model_id: str):
    """현재 사용 중인 모델 배지 표시"""

    model = get_model(model_id)
    if model:
        icon = PROVIDER_INFO.get(model.provider, {}).get("icon", "")
        speed_icon = {"fast": "⚡", "medium": "⚖️", "slow": "🎯"}.get(model.speed, "")
        st.caption(f"{icon} **{model.name}** {speed_icon}")


def render_processing_mode_selector(key: str = "processing_mode") -> str:
    """
    처리 모드 선택 UI 렌더링

    Returns:
        선택된 처리 모드 ("sequential", "batch", "parallel")
    """

    if f"{key}" not in st.session_state:
        st.session_state[f"{key}"] = "batch"

    mode_options = {
        "🔄 순차 처리 (안정)": "sequential",
        "📦 배치 처리 (빠름)": "batch",
        "⚡ 병렬 처리 (가장 빠름)": "parallel"
    }

    # 현재 선택된 모드의 레이블 찾기
    current_mode = st.session_state.get(f"{key}", "batch")
    current_label = "📦 배치 처리 (빠름)"
    for label, mode in mode_options.items():
        if mode == current_mode:
            current_label = label
            break

    selected_label = st.radio(
        "처리 모드",
        options=list(mode_options.keys()),
        index=list(mode_options.keys()).index(current_label),
        key=f"{key}_select",
        horizontal=True,
        help="병렬 처리가 가장 빠르지만 API 제한에 걸릴 수 있습니다"
    )

    selected_mode = mode_options[selected_label]
    st.session_state[f"{key}"] = selected_mode

    return selected_mode


def get_selected_model(key: str = "ai_model") -> Optional[str]:
    """세션 상태에서 선택된 모델 ID 반환"""
    return st.session_state.get(f"{key}_model")


def set_selected_model(key: str, model_id: str):
    """세션 상태에 모델 ID 설정"""
    st.session_state[f"{key}_model"] = model_id


def render_claude_code_settings(key: str = "claude_code") -> dict:
    """
    Claude Code 설정 UI 렌더링

    Args:
        key: 세션 상태 키 접두사

    Returns:
        설정 딕셔너리 {timeout, bundle_mode, custom_instructions}
    """

    # Claude Code 설치 상태 확인
    try:
        from utils.claude_code_runner import check_claude_code_installation
        status = check_claude_code_installation()
    except ImportError:
        st.error("❌ claude_code_runner 모듈을 불러올 수 없습니다")
        return None

    if status.get('installed'):
        st.success(f"✅ Claude Code 설치됨: {status.get('version', 'unknown')}")
    else:
        st.error(f"❌ Claude Code 미설치: {status.get('error', '')}")
        st.code("npm i -g @anthropic-ai/claude-code", language="bash")
        return None

    # 설정 UI
    with st.expander("⚙️ Claude Code 설정", expanded=True):
        col1, col2 = st.columns(2)

        with col1:
            timeout = st.number_input(
                "타임아웃 (초)",
                min_value=60,
                max_value=1800,
                value=st.session_state.get(f"{key}_timeout", 600),
                step=60,
                key=f"{key}_timeout_input",
                help="분석 작업의 최대 실행 시간"
            )
            st.session_state[f"{key}_timeout"] = timeout

        with col2:
            bundle_mode = st.checkbox(
                "묶음 모드 사용",
                value=st.session_state.get(f"{key}_bundle_mode", True),
                key=f"{key}_bundle_input",
                help="동일한 bundle_id를 가진 씬들은 같은 프롬프트 공유"
            )
            st.session_state[f"{key}_bundle_mode"] = bundle_mode

        custom_instructions = st.text_area(
            "추가 지시사항 (선택)",
            value=st.session_state.get(f"{key}_custom_instructions", ""),
            placeholder="예: 배경 프롬프트에 '네온 조명' 스타일 강조",
            height=60,
            key=f"{key}_instructions_input"
        )
        st.session_state[f"{key}_custom_instructions"] = custom_instructions

        # 장점 안내
        st.info("""
        **✨ Claude Code 장점:**
        - 🆓 **Max Plan 사용 시 API 비용 무료**
        - 🧠 Claude Opus 4 수준의 고품질 분석
        - 📁 파일 직접 수정으로 빠른 처리
        """)

    return {
        "timeout": timeout,
        "bundle_mode": bundle_mode,
        "custom_instructions": custom_instructions
    }


def is_claude_code_selected(key: str = "ai_model") -> bool:
    """현재 Claude Code가 선택되어 있는지 확인"""
    selected = st.session_state.get(f"{key}_model", "")
    return selected == "claude_code"
