# -*- coding: utf-8 -*-
"""
멀티 AI 프로바이더 지원 모듈 v1.0

Anthropic, Google, OpenAI 통합 관리

기능:
- 모든 프로바이더의 모델 정보 관리
- API 키 상태 확인
- 프로바이더별 모델 필터링
"""

import os
from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum


class AIProvider(Enum):
    """AI 프로바이더"""
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    OPENAI = "openai"


@dataclass
class AIModel:
    """AI 모델 정보"""
    id: str                      # 모델 ID (API 호출용)
    name: str                    # 표시 이름
    provider: AIProvider         # 프로바이더
    speed: str                   # fast, medium, slow
    quality: str                 # standard, high, best
    cost: str                    # low, medium, high
    description: str             # 설명
    max_tokens: int = 4096       # 최대 토큰
    supports_vision: bool = False  # 이미지 입력 지원
    api_key_env: str = ""        # API 키 환경변수 이름


# ============================================================
# 사용 가능한 모든 AI 모델
# ============================================================

ALL_MODELS: Dict[str, AIModel] = {

    # ==================== Anthropic (Claude) ====================
    "claude-3-5-haiku-20241022": AIModel(
        id="claude-3-5-haiku-20241022",
        name="Claude 3.5 Haiku",
        provider=AIProvider.ANTHROPIC,
        speed="fast",
        quality="standard",
        cost="low",
        description="⚡ 가장 빠름, 간단한 작업에 적합",
        max_tokens=4096,
        supports_vision=True,
        api_key_env="ANTHROPIC_API_KEY"
    ),
    "claude-sonnet-4-20250514": AIModel(
        id="claude-sonnet-4-20250514",
        name="Claude Sonnet 4",
        provider=AIProvider.ANTHROPIC,
        speed="medium",
        quality="high",
        cost="medium",
        description="⚖️ 속도와 품질의 균형",
        max_tokens=8192,
        supports_vision=True,
        api_key_env="ANTHROPIC_API_KEY"
    ),
    "claude-opus-4-20250514": AIModel(
        id="claude-opus-4-20250514",
        name="Claude Opus 4",
        provider=AIProvider.ANTHROPIC,
        speed="slow",
        quality="best",
        cost="high",
        description="🎯 최고 품질, 복잡한 분석에 적합",
        max_tokens=8192,
        supports_vision=True,
        api_key_env="ANTHROPIC_API_KEY"
    ),

    # ==================== Google (Gemini) ====================
    "gemini-2.0-flash-exp": AIModel(
        id="gemini-2.0-flash-exp",
        name="Gemini 2.0 Flash",
        provider=AIProvider.GOOGLE,
        speed="fast",
        quality="high",
        cost="low",
        description="⚡ 최신 Gemini, 빠르고 강력함",
        max_tokens=8192,
        supports_vision=True,
        api_key_env="GOOGLE_API_KEY"
    ),
    "gemini-1.5-pro": AIModel(
        id="gemini-1.5-pro",
        name="Gemini 1.5 Pro",
        provider=AIProvider.GOOGLE,
        speed="medium",
        quality="best",
        cost="medium",
        description="🎯 최고 성능 Gemini, 긴 컨텍스트 지원",
        max_tokens=8192,
        supports_vision=True,
        api_key_env="GOOGLE_API_KEY"
    ),
    "gemini-1.5-flash": AIModel(
        id="gemini-1.5-flash",
        name="Gemini 1.5 Flash",
        provider=AIProvider.GOOGLE,
        speed="fast",
        quality="standard",
        cost="low",
        description="⚡ 빠른 Gemini, 비용 효율적",
        max_tokens=8192,
        supports_vision=True,
        api_key_env="GOOGLE_API_KEY"
    ),

    # ==================== OpenAI (GPT) ====================
    "gpt-4o": AIModel(
        id="gpt-4o",
        name="GPT-4o",
        provider=AIProvider.OPENAI,
        speed="medium",
        quality="best",
        cost="high",
        description="🎯 최신 GPT-4, 멀티모달 지원",
        max_tokens=4096,
        supports_vision=True,
        api_key_env="OPENAI_API_KEY"
    ),
    "gpt-4o-mini": AIModel(
        id="gpt-4o-mini",
        name="GPT-4o Mini",
        provider=AIProvider.OPENAI,
        speed="fast",
        quality="high",
        cost="low",
        description="⚡ 빠른 GPT-4, 비용 효율적",
        max_tokens=4096,
        supports_vision=True,
        api_key_env="OPENAI_API_KEY"
    ),
    "gpt-4-turbo": AIModel(
        id="gpt-4-turbo",
        name="GPT-4 Turbo",
        provider=AIProvider.OPENAI,
        speed="medium",
        quality="best",
        cost="high",
        description="⚖️ 강력한 GPT-4 Turbo",
        max_tokens=4096,
        supports_vision=True,
        api_key_env="OPENAI_API_KEY"
    ),
}


# ============================================================
# 프로바이더 표시 정보
# ============================================================

PROVIDER_INFO = {
    AIProvider.ANTHROPIC: {
        "name": "Anthropic",
        "icon": "🟠",
        "display": "🟠 Anthropic (Claude)",
        "env_var": "ANTHROPIC_API_KEY"
    },
    AIProvider.GOOGLE: {
        "name": "Google",
        "icon": "🔵",
        "display": "🔵 Google (Gemini)",
        "env_var": "GOOGLE_API_KEY"
    },
    AIProvider.OPENAI: {
        "name": "OpenAI",
        "icon": "🟢",
        "display": "🟢 OpenAI (GPT)",
        "env_var": "OPENAI_API_KEY"
    }
}


# ============================================================
# 유틸리티 함수
# ============================================================

def get_models_by_provider(provider: AIProvider) -> List[AIModel]:
    """프로바이더별 모델 목록"""
    return [m for m in ALL_MODELS.values() if m.provider == provider]


def get_all_providers() -> List[AIProvider]:
    """사용 가능한 모든 프로바이더"""
    return list(AIProvider)


def get_model(model_id: str) -> Optional[AIModel]:
    """모델 ID로 모델 정보 조회"""
    return ALL_MODELS.get(model_id)


def get_provider_display(provider: AIProvider) -> str:
    """프로바이더 표시 이름"""
    return PROVIDER_INFO.get(provider, {}).get("display", provider.value)


def get_provider_icon(provider: AIProvider) -> str:
    """프로바이더 아이콘"""
    return PROVIDER_INFO.get(provider, {}).get("icon", "")


# ============================================================
# API 키 관리
# ============================================================

def check_api_key(provider: AIProvider) -> bool:
    """프로바이더의 API 키 존재 여부 확인"""
    env_var = PROVIDER_INFO.get(provider, {}).get("env_var", "")
    key = os.getenv(env_var, "")
    return bool(key and key.strip())


def get_available_providers() -> List[AIProvider]:
    """API 키가 설정된 프로바이더만 반환"""
    return [p for p in AIProvider if check_api_key(p)]


def get_available_models() -> Dict[str, AIModel]:
    """API 키가 있는 프로바이더의 모델만 반환"""
    available = get_available_providers()
    return {
        k: v for k, v in ALL_MODELS.items()
        if v.provider in available
    }


def get_api_key_status() -> Dict[str, bool]:
    """모든 프로바이더의 API 키 상태"""
    return {
        provider.value: check_api_key(provider)
        for provider in AIProvider
    }


# ============================================================
# 작업별 기본 모델
# ============================================================

DEFAULT_MODELS = {
    "scene_analysis": "claude-sonnet-4-20250514",
    "character_extraction": "claude-3-5-haiku-20241022",
    "image_prompt": "claude-sonnet-4-20250514",
    "script_generation": "claude-sonnet-4-20250514",
    "visual_prompt": "claude-3-5-haiku-20241022",
}


def get_default_model(task: str) -> str:
    """작업별 기본 모델 반환"""
    return DEFAULT_MODELS.get(task, "claude-sonnet-4-20250514")


def get_fallback_model() -> Optional[str]:
    """사용 가능한 첫 번째 모델 반환 (폴백용)"""
    available = get_available_models()
    if available:
        return list(available.keys())[0]
    return None
