# -*- coding: utf-8 -*-
"""
AI 모델 설정 및 관리 모듈 v1.0

기능:
- AI 모델 정보 관리
- 모델 선택 UI 렌더링
- 작업별 기본/권장 모델 설정
"""

from typing import Dict, Optional
from dataclasses import dataclass
import streamlit as st


@dataclass
class AIModel:
    """AI 모델 정보"""
    id: str
    name: str
    provider: str
    speed: str  # "fast", "medium", "slow"
    quality: str  # "standard", "high", "best"
    cost: str  # "low", "medium", "high"
    description: str
    max_tokens: int = 4096


# 사용 가능한 모델 목록
AVAILABLE_MODELS: Dict[str, AIModel] = {
    # Anthropic 모델
    "claude-3-5-haiku-20241022": AIModel(
        id="claude-3-5-haiku-20241022",
        name="Claude 3.5 Haiku",
        provider="anthropic",
        speed="fast",
        quality="standard",
        cost="low",
        description="⚡ 빠른 속도, 간단한 작업에 적합",
        max_tokens=4096
    ),
    "claude-sonnet-4-20250514": AIModel(
        id="claude-sonnet-4-20250514",
        name="Claude Sonnet 4",
        provider="anthropic",
        speed="medium",
        quality="high",
        cost="medium",
        description="⚖️ 속도와 품질의 균형",
        max_tokens=8192
    ),
    "claude-opus-4-20250514": AIModel(
        id="claude-opus-4-20250514",
        name="Claude Opus 4",
        provider="anthropic",
        speed="slow",
        quality="best",
        cost="high",
        description="🎯 최고 품질, 복잡한 작업에 적합",
        max_tokens=8192
    ),
}

# 작업별 기본 모델
DEFAULT_MODELS = {
    "scene_analysis": "claude-sonnet-4-20250514",
    "character_extraction": "claude-3-5-haiku-20241022",
    "image_prompt": "claude-sonnet-4-20250514",
    "script_generation": "claude-sonnet-4-20250514",
    "visual_prompt": "claude-3-5-haiku-20241022",
}

# 처리 모드
PROCESSING_MODES = {
    "sequential": {
        "name": "🔄 순차 처리",
        "description": "씬을 하나씩 처리 (안정적)",
        "speed": "slow"
    },
    "batch": {
        "name": "📦 배치 처리",
        "description": "여러 씬을 한 번에 처리 (빠름)",
        "speed": "medium"
    },
    "parallel": {
        "name": "⚡ 병렬 처리",
        "description": "동시에 여러 씬 처리 (가장 빠름)",
        "speed": "fast"
    }
}


def get_model_info(model_id: str) -> Optional[AIModel]:
    """모델 정보 반환"""
    return AVAILABLE_MODELS.get(model_id)


def get_default_model(task: str) -> str:
    """작업별 기본 모델 반환"""
    return DEFAULT_MODELS.get(task, "claude-sonnet-4-20250514")


def render_model_selector(
    task: str,
    key: str = None,
    show_info: bool = True,
    compact: bool = False
) -> str:
    """
    AI 모델 선택 UI 렌더링

    Args:
        task: 작업 유형 (scene_analysis, character_extraction 등)
        key: Streamlit 위젯 키
        show_info: 모델 정보 표시 여부
        compact: 컴팩트 모드

    Returns:
        선택된 모델 ID
    """

    # 세션 상태에서 이전 선택 복원
    session_key = f"ai_model_{task}"
    if session_key not in st.session_state:
        st.session_state[session_key] = get_default_model(task)

    # 모델 선택 옵션
    model_options = {
        "⚡ 빠름 (Haiku)": "claude-3-5-haiku-20241022",
        "⚖️ 균형 (Sonnet)": "claude-sonnet-4-20250514",
        "🎯 고품질 (Opus)": "claude-opus-4-20250514"
    }

    # 현재 선택된 모델의 레이블 찾기
    current_label = "⚖️ 균형 (Sonnet)"
    for label, model_id in model_options.items():
        if model_id == st.session_state[session_key]:
            current_label = label
            break

    # UI 렌더링
    if compact:
        selected_label = st.selectbox(
            "🤖 AI 모델",
            options=list(model_options.keys()),
            index=list(model_options.keys()).index(current_label),
            key=key or f"model_select_{task}",
            help="빠른 모델은 속도가 빠르지만 품질이 낮을 수 있습니다"
        )
        selected_model = model_options[selected_label]
        st.session_state[session_key] = selected_model
    else:
        col1, col2 = st.columns([2, 3])

        with col1:
            selected_label = st.selectbox(
                "🤖 AI 모델",
                options=list(model_options.keys()),
                index=list(model_options.keys()).index(current_label),
                key=key or f"model_select_{task}",
                help="빠른 모델은 속도가 빠르지만 품질이 낮을 수 있습니다"
            )

        selected_model = model_options[selected_label]
        st.session_state[session_key] = selected_model

        # 모델 정보 표시
        if show_info:
            with col2:
                model_info = get_model_info(selected_model)
                if model_info:
                    st.caption(f"{model_info.description}")

    return selected_model


def render_processing_mode_selector(key: str = None) -> str:
    """
    처리 모드 선택 UI 렌더링

    Returns:
        선택된 처리 모드 ("sequential", "batch", "parallel")
    """

    session_key = "processing_mode"
    if session_key not in st.session_state:
        st.session_state[session_key] = "batch"

    mode_options = {
        "🔄 순차 처리 (안정)": "sequential",
        "📦 배치 처리 (빠름)": "batch",
        "⚡ 병렬 처리 (가장 빠름)": "parallel"
    }

    # 현재 선택된 모드의 레이블 찾기
    current_label = "📦 배치 처리 (빠름)"
    for label, mode in mode_options.items():
        if mode == st.session_state[session_key]:
            current_label = label
            break

    selected_label = st.radio(
        "처리 모드",
        options=list(mode_options.keys()),
        index=list(mode_options.keys()).index(current_label),
        key=key or "processing_mode_select",
        horizontal=True,
        help="병렬 처리가 가장 빠르지만 API 제한에 걸릴 수 있습니다"
    )

    selected_mode = mode_options[selected_label]
    st.session_state[session_key] = selected_mode

    return selected_mode


def render_model_badge(model_id: str):
    """현재 사용 중인 모델 배지 표시"""

    model_info = get_model_info(model_id)
    if model_info:
        speed_emoji = {"fast": "⚡", "medium": "⚖️", "slow": "🎯"}.get(model_info.speed, "")
        st.caption(f"{speed_emoji} 현재 모델: **{model_info.name}**")


def get_model_max_tokens(model_id: str) -> int:
    """모델의 최대 토큰 수 반환"""
    model_info = get_model_info(model_id)
    return model_info.max_tokens if model_info else 4096
