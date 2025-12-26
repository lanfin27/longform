# -*- coding: utf-8 -*-
"""
통합 AI 클라이언트 v1.0

모든 프로바이더를 동일한 인터페이스로 호출

기능:
- Anthropic (Claude) API 호출
- Google (Gemini) API 호출
- OpenAI (GPT) API 호출
- JSON 응답 파싱
"""

import os
import json
from typing import Dict, Optional, Any
from .ai_providers import AIProvider, AIModel, get_model, ALL_MODELS


class UnifiedAIClient:
    """
    통합 AI 클라이언트
    Anthropic, Google, OpenAI를 동일한 인터페이스로 호출
    """

    def __init__(self, model_id: str = None):
        """
        Args:
            model_id: 사용할 모델 ID (없으면 기본값 사용)
        """
        self.model_id = model_id or "claude-sonnet-4-20250514"
        self.model_info = get_model(self.model_id)

        if not self.model_info:
            raise ValueError(f"알 수 없는 모델: {self.model_id}")

        self.provider = self.model_info.provider
        self._client = None
        self._init_client()

    def _init_client(self):
        """프로바이더별 클라이언트 초기화"""

        if self.provider == AIProvider.ANTHROPIC:
            self._init_anthropic()
        elif self.provider == AIProvider.GOOGLE:
            self._init_google()
        elif self.provider == AIProvider.OPENAI:
            self._init_openai()

    def _init_anthropic(self):
        """Anthropic 클라이언트 초기화"""
        try:
            import anthropic
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                raise ValueError("ANTHROPIC_API_KEY 환경변수가 설정되지 않았습니다")
            self._client = anthropic.Anthropic(api_key=api_key)
        except ImportError:
            raise ImportError("anthropic 패키지가 설치되지 않았습니다. pip install anthropic")

    def _init_google(self):
        """Google Gemini 클라이언트 초기화"""
        try:
            import google.generativeai as genai
            api_key = os.getenv("GOOGLE_API_KEY")
            if not api_key:
                raise ValueError("GOOGLE_API_KEY 환경변수가 설정되지 않았습니다")
            genai.configure(api_key=api_key)
            self._client = genai.GenerativeModel(self.model_id)
        except ImportError:
            raise ImportError("google-generativeai 패키지가 설치되지 않았습니다. pip install google-generativeai")

    def _init_openai(self):
        """OpenAI 클라이언트 초기화"""
        try:
            from openai import OpenAI
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY 환경변수가 설정되지 않았습니다")
            self._client = OpenAI(api_key=api_key)
        except ImportError:
            raise ImportError("openai 패키지가 설치되지 않았습니다. pip install openai")

    def generate(
        self,
        prompt: str,
        system_prompt: str = None,
        max_tokens: int = None,
        temperature: float = 0.7,
        json_mode: bool = False
    ) -> str:
        """
        텍스트 생성 (통합 인터페이스)

        Args:
            prompt: 사용자 프롬프트
            system_prompt: 시스템 프롬프트 (선택)
            max_tokens: 최대 토큰 수
            temperature: 온도 (창의성)
            json_mode: JSON 응답 모드

        Returns:
            생성된 텍스트
        """

        max_tokens = max_tokens or self.model_info.max_tokens

        if self.provider == AIProvider.ANTHROPIC:
            return self._generate_anthropic(prompt, system_prompt, max_tokens, temperature)
        elif self.provider == AIProvider.GOOGLE:
            return self._generate_google(prompt, system_prompt, max_tokens, temperature)
        elif self.provider == AIProvider.OPENAI:
            return self._generate_openai(prompt, system_prompt, max_tokens, temperature, json_mode)
        else:
            raise ValueError(f"지원하지 않는 프로바이더: {self.provider}")

    def _generate_anthropic(self, prompt, system_prompt, max_tokens, temperature) -> str:
        """Anthropic (Claude) 호출"""

        messages = [{"role": "user", "content": prompt}]

        kwargs = {
            "model": self.model_id,
            "max_tokens": max_tokens,
            "messages": messages,
            "temperature": temperature
        }

        if system_prompt:
            kwargs["system"] = system_prompt

        response = self._client.messages.create(**kwargs)
        return response.content[0].text

    def _generate_google(self, prompt, system_prompt, max_tokens, temperature) -> str:
        """Google (Gemini) 호출"""

        # 시스템 프롬프트를 프롬프트 앞에 추가
        full_prompt = prompt
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{prompt}"

        generation_config = {
            "max_output_tokens": max_tokens,
            "temperature": temperature
        }

        response = self._client.generate_content(
            full_prompt,
            generation_config=generation_config
        )

        return response.text

    def _generate_openai(self, prompt, system_prompt, max_tokens, temperature, json_mode) -> str:
        """OpenAI (GPT) 호출"""

        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": prompt})

        kwargs = {
            "model": self.model_id,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature
        }

        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        response = self._client.chat.completions.create(**kwargs)
        return response.choices[0].message.content

    def generate_json(
        self,
        prompt: str,
        system_prompt: str = None,
        max_tokens: int = None
    ) -> Dict:
        """
        JSON 응답 생성

        Returns:
            파싱된 JSON 딕셔너리
        """

        # JSON 요청 프롬프트 추가
        json_prompt = prompt + "\n\nJSON 형식으로만 응답하세요. 다른 텍스트 없이 순수 JSON만 출력하세요."

        response = self.generate(
            prompt=json_prompt,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            json_mode=(self.provider == AIProvider.OPENAI)
        )

        return self._parse_json_response(response)

    def _parse_json_response(self, text: str) -> Dict:
        """JSON 응답 파싱"""

        text = text.strip()

        # ```json ... ``` 형식 처리
        if '```' in text:
            parts = text.split('```')
            for part in parts:
                part = part.strip()
                if part.startswith('json'):
                    text = part[4:].strip()
                    break
                elif part.startswith('{') or part.startswith('['):
                    text = part
                    break

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            print(f"[AI Client] JSON 파싱 오류: {e}")
            print(f"[AI Client] 원본 응답: {text[:500]}...")
            return {}


# ============================================================
# 헬퍼 함수
# ============================================================

def create_ai_client(model_id: str = None) -> UnifiedAIClient:
    """AI 클라이언트 생성 헬퍼"""
    return UnifiedAIClient(model_id=model_id)


def generate_with_model(
    model_id: str,
    prompt: str,
    system_prompt: str = None,
    max_tokens: int = None
) -> str:
    """특정 모델로 텍스트 생성"""
    client = UnifiedAIClient(model_id=model_id)
    return client.generate(prompt, system_prompt, max_tokens)


def generate_json_with_model(
    model_id: str,
    prompt: str,
    system_prompt: str = None,
    max_tokens: int = None
) -> Dict:
    """특정 모델로 JSON 생성"""
    client = UnifiedAIClient(model_id=model_id)
    return client.generate_json(prompt, system_prompt, max_tokens)


def test_model_connection(model_id: str) -> tuple:
    """
    모델 연결 테스트

    Returns:
        (성공 여부, 메시지)
    """
    try:
        client = UnifiedAIClient(model_id=model_id)
        response = client.generate("Say 'Hello' in one word.", max_tokens=10)
        return True, f"연결 성공: {response[:50]}"
    except Exception as e:
        return False, f"연결 실패: {str(e)}"
