# -*- coding: utf-8 -*-
"""
AI 폴백 관리자 (v1.0)

Claude CLI (Max Plan) 오류 시 자동으로 Gemini로 폴백
"""

import os
from typing import Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum


class AIProvider(Enum):
    """AI 제공자"""
    CLAUDE_CODE = "claude_code_agent"  # Claude CLI (Max Plan)
    GEMINI = "gemini"                  # Gemini 2.0 Flash (폴백)


@dataclass
class AIResponse:
    """AI 응답"""
    success: bool
    output: str
    error: str = ""
    provider_used: str = ""
    was_fallback: bool = False


class AIFallbackManager:
    """
    AI 폴백 관리자

    우선순위:
    1. Claude CLI (Max Plan) - 기본
    2. Gemini 2.0 Flash - 폴백
    """

    def __init__(self):
        self.primary_provider = AIProvider.CLAUDE_CODE
        self.fallback_provider = AIProvider.GEMINI

        self._claude_runner = None
        self._gemini_client = None

        self._fallback_count = 0
        self._total_requests = 0

        print(f"[AIFallbackManager] 초기화")
        print(f"[AIFallbackManager]   기본: Claude CLI (Max Plan)")
        print(f"[AIFallbackManager]   폴백: Gemini 2.0 Flash")

        self._init_providers()

    def _init_providers(self):
        """제공자 초기화"""

        # Claude CLI
        try:
            from utils.claude_code_runner import get_claude_code_runner, is_claude_code_available
            if is_claude_code_available():
                self._claude_runner = get_claude_code_runner()
                print(f"[AIFallbackManager] ✅ Claude CLI 사용 가능")
            else:
                print(f"[AIFallbackManager] ⚠️ Claude CLI 사용 불가")
        except Exception as e:
            print(f"[AIFallbackManager] ⚠️ Claude CLI 초기화 실패: {e}")

        # Gemini (폴백용)
        try:
            import google.generativeai as genai
            api_key = os.getenv("GOOGLE_API_KEY")
            if api_key:
                genai.configure(api_key=api_key)
                self._gemini_client = genai.GenerativeModel("gemini-2.0-flash-exp")
                print(f"[AIFallbackManager] ✅ Gemini 폴백 준비 완료")
            else:
                print(f"[AIFallbackManager] ⚠️ GOOGLE_API_KEY 없음 - Gemini 폴백 불가")
        except Exception as e:
            print(f"[AIFallbackManager] ⚠️ Gemini 초기화 실패: {e}")

    def run(
        self,
        prompt: str,
        timeout: int = 180,
        allow_fallback: bool = True
    ) -> AIResponse:
        """
        AI 실행 (자동 폴백 포함)

        Args:
            prompt: 프롬프트
            timeout: 타임아웃 (초)
            allow_fallback: 폴백 허용 여부

        Returns:
            AIResponse
        """

        self._total_requests += 1
        claude_error = ""

        # 1차: Claude CLI (Max Plan)
        if self._claude_runner and self._claude_runner.available:
            print(f"[AIFallbackManager] 🔵 Claude CLI (Max Plan) 실행 중...")

            result = self._claude_runner.run(prompt, timeout=timeout)

            if result.success:
                return AIResponse(
                    success=True,
                    output=result.output,
                    provider_used="claude_code_agent (Max Plan)"
                )

            claude_error = result.error

            # 폴백 필요?
            if not allow_fallback or not result.should_fallback:
                return AIResponse(
                    success=False,
                    output=result.output,
                    error=result.error,
                    provider_used="claude_code_agent (Max Plan)"
                )

            print(f"[AIFallbackManager] ⚠️ Claude CLI 실패: {result.error}")
            print(f"[AIFallbackManager] 🔄 Gemini 폴백 시도...")

        # 2차: Gemini (폴백)
        if self._gemini_client and allow_fallback:
            try:
                print(f"[AIFallbackManager] 🟡 Gemini 2.0 Flash 실행 중...")

                response = self._gemini_client.generate_content(prompt)

                self._fallback_count += 1

                return AIResponse(
                    success=True,
                    output=response.text,
                    provider_used="gemini-2.0-flash-exp",
                    was_fallback=True
                )

            except Exception as e:
                print(f"[AIFallbackManager] ❌ Gemini 실패: {e}")
                return AIResponse(
                    success=False,
                    output="",
                    error=f"모든 AI 제공자 실패. Claude: {claude_error}, Gemini: {e}",
                    provider_used="none"
                )

        # 모두 실패
        return AIResponse(
            success=False,
            output="",
            error="사용 가능한 AI 제공자가 없습니다",
            provider_used="none"
        )

    def get_stats(self) -> Dict[str, Any]:
        """통계 반환"""
        return {
            "total_requests": self._total_requests,
            "fallback_count": self._fallback_count,
            "fallback_rate": f"{self._fallback_count / max(1, self._total_requests) * 100:.1f}%"
        }


# 싱글톤
_manager: Optional[AIFallbackManager] = None

def get_ai_fallback_manager() -> AIFallbackManager:
    global _manager
    if _manager is None:
        _manager = AIFallbackManager()
    return _manager

def run_ai_with_fallback(prompt: str, timeout: int = 180) -> AIResponse:
    """AI 실행 (자동 폴백)"""
    return get_ai_fallback_manager().run(prompt, timeout=timeout)
