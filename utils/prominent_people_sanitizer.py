# -*- coding: utf-8 -*-
"""
AI 기반 유명인 치환 모듈 v1.0

ImageFX의 PROMINENT_PEOPLE_FILTER 에러를 방지하기 위해
AI를 사용하여 프롬프트에서 유명인 이름을 일반적인 설명으로 치환

지원 프로바이더:
- Google (Gemini)
- Anthropic (Claude)
- OpenAI (GPT)
"""

import os
import json
import re
from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Tuple
import logging

from .ai_providers import (
    AIProvider, AIModel, ALL_MODELS,
    get_available_models, get_model, check_api_key
)

logger = logging.getLogger(__name__)


@dataclass
class SanitizeResult:
    """치환 결과"""
    original_prompt: str          # 원본 프롬프트
    sanitized_prompt: str         # 치환된 프롬프트
    was_modified: bool            # 치환 여부
    detected_names: List[str]     # 감지된 유명인 이름
    replacements: Dict[str, str]  # 원본 -> 치환 매핑
    model_used: str               # 사용된 AI 모델
    error: Optional[str] = None   # 에러 메시지 (있으면)


# AI 프롬프트 템플릿
SANITIZE_PROMPT_TEMPLATE = """You are an expert at identifying and replacing celebrity/famous person names in image generation prompts.

TASK: Analyze the following prompt and replace any celebrity, famous person, or public figure names with generic physical descriptions.

RULES:
1. Replace celebrity names with detailed physical descriptions (age, gender, ethnicity, hair color, body type, etc.)
2. Keep the original context and action
3. Preserve non-celebrity names (fictional characters from the story are OK)
4. Return ONLY valid JSON, no markdown formatting

INPUT PROMPT:
{prompt}

OUTPUT FORMAT (strict JSON only):
{{
    "detected_names": ["list of celebrity names found"],
    "replacements": {{"original name": "replacement description"}},
    "sanitized_prompt": "the modified prompt with replacements applied",
    "was_modified": true/false
}}

If no celebrities are detected, return:
{{
    "detected_names": [],
    "replacements": {{}},
    "sanitized_prompt": "original prompt unchanged",
    "was_modified": false
}}

IMPORTANT: Return ONLY the JSON object, no other text or markdown."""


class ProminentPeopleSanitizer:
    """유명인 이름 치환기"""

    def __init__(self, ai_model: str = "gemini-2.0-flash-exp"):
        """
        Args:
            ai_model: 사용할 AI 모델 ID
        """
        self.model_id = ai_model
        self.model_info = get_model(ai_model)

        if not self.model_info:
            # 폴백: 사용 가능한 첫 번째 모델 사용
            available = get_available_models()
            if available:
                self.model_id = list(available.keys())[0]
                self.model_info = available[self.model_id]
                logger.warning(f"모델 {ai_model}을 찾을 수 없어 {self.model_id}로 폴백합니다.")
            else:
                raise ValueError("사용 가능한 AI 모델이 없습니다. API 키를 확인하세요.")

        logger.info(f"ProminentPeopleSanitizer 초기화: {self.model_info.name}")

    def sanitize(self, prompt: str) -> SanitizeResult:
        """
        프롬프트에서 유명인 이름을 치환

        Args:
            prompt: 원본 프롬프트

        Returns:
            SanitizeResult: 치환 결과
        """
        if not prompt or not prompt.strip():
            return SanitizeResult(
                original_prompt=prompt,
                sanitized_prompt=prompt,
                was_modified=False,
                detected_names=[],
                replacements={},
                model_used=self.model_id
            )

        try:
            # AI 호출
            ai_response = self._call_ai(prompt)

            # JSON 파싱
            result = self._parse_response(ai_response, prompt)
            result.model_used = self.model_id
            return result

        except Exception as e:
            logger.error(f"유명인 치환 실패: {e}")
            return SanitizeResult(
                original_prompt=prompt,
                sanitized_prompt=prompt,
                was_modified=False,
                detected_names=[],
                replacements={},
                model_used=self.model_id,
                error=str(e)
            )

    def _call_ai(self, prompt: str) -> str:
        """AI API 호출"""
        provider = self.model_info.provider

        if provider == AIProvider.GOOGLE:
            return self._call_gemini(prompt)
        elif provider == AIProvider.ANTHROPIC:
            return self._call_claude(prompt)
        elif provider == AIProvider.OPENAI:
            return self._call_openai(prompt)
        else:
            raise ValueError(f"지원하지 않는 프로바이더: {provider}")

    def _call_gemini(self, prompt: str) -> str:
        """Gemini API 호출"""
        import google.generativeai as genai

        api_key = os.getenv("GOOGLE_API_KEY", "")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY가 설정되지 않았습니다.")

        genai.configure(api_key=api_key)

        model = genai.GenerativeModel(self.model_id)
        full_prompt = SANITIZE_PROMPT_TEMPLATE.format(prompt=prompt)

        response = model.generate_content(
            full_prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.1,  # 낮은 온도로 일관된 결과
                max_output_tokens=2048,
            )
        )

        return response.text

    def _call_claude(self, prompt: str) -> str:
        """Claude API 호출"""
        import anthropic

        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY가 설정되지 않았습니다.")

        client = anthropic.Anthropic(api_key=api_key)
        full_prompt = SANITIZE_PROMPT_TEMPLATE.format(prompt=prompt)

        response = client.messages.create(
            model=self.model_id,
            max_tokens=2048,
            temperature=0.1,
            messages=[
                {"role": "user", "content": full_prompt}
            ]
        )

        return response.content[0].text

    def _call_openai(self, prompt: str) -> str:
        """OpenAI API 호출"""
        from openai import OpenAI

        api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            raise ValueError("OPENAI_API_KEY가 설정되지 않았습니다.")

        client = OpenAI(api_key=api_key)
        full_prompt = SANITIZE_PROMPT_TEMPLATE.format(prompt=prompt)

        response = client.chat.completions.create(
            model=self.model_id,
            messages=[
                {"role": "user", "content": full_prompt}
            ],
            temperature=0.1,
            max_tokens=2048,
        )

        return response.choices[0].message.content

    def _parse_response(self, ai_response: str, original_prompt: str) -> SanitizeResult:
        """AI 응답 파싱"""
        try:
            # JSON 추출 (마크다운 블록 제거)
            cleaned = ai_response.strip()

            # ```json ... ``` 블록 제거
            if "```json" in cleaned:
                match = re.search(r'```json\s*(.*?)\s*```', cleaned, re.DOTALL)
                if match:
                    cleaned = match.group(1)
            elif "```" in cleaned:
                match = re.search(r'```\s*(.*?)\s*```', cleaned, re.DOTALL)
                if match:
                    cleaned = match.group(1)

            # JSON 객체 추출
            json_match = re.search(r'\{.*\}', cleaned, re.DOTALL)
            if json_match:
                cleaned = json_match.group()

            data = json.loads(cleaned)

            return SanitizeResult(
                original_prompt=original_prompt,
                sanitized_prompt=data.get("sanitized_prompt", original_prompt),
                was_modified=data.get("was_modified", False),
                detected_names=data.get("detected_names", []),
                replacements=data.get("replacements", {}),
                model_used=self.model_id
            )

        except json.JSONDecodeError as e:
            logger.warning(f"JSON 파싱 실패: {e}, 응답: {ai_response[:200]}")
            # 파싱 실패 시 원본 반환
            return SanitizeResult(
                original_prompt=original_prompt,
                sanitized_prompt=original_prompt,
                was_modified=False,
                detected_names=[],
                replacements={},
                model_used=self.model_id,
                error=f"JSON 파싱 실패: {e}"
            )


# ============================================================
# 헬퍼 함수
# ============================================================

def sanitize_prompt_for_imagefx(
    prompt: str,
    ai_model: str = "gemini-2.0-flash-exp"
) -> Tuple[str, SanitizeResult]:
    """
    ImageFX용 프롬프트 치환

    Args:
        prompt: 원본 프롬프트
        ai_model: 사용할 AI 모델

    Returns:
        Tuple[str, SanitizeResult]: (치환된 프롬프트, 상세 결과)
    """
    sanitizer = ProminentPeopleSanitizer(ai_model=ai_model)
    result = sanitizer.sanitize(prompt)
    return result.sanitized_prompt, result


def get_available_sanitizer_models() -> Dict[str, AIModel]:
    """
    치환에 사용 가능한 AI 모델 목록

    Returns:
        Dict[str, AIModel]: 사용 가능한 모델들
    """
    return get_available_models()


def get_recommended_model() -> str:
    """
    추천 모델 반환 (빠르고 비용 효율적인 모델 우선)

    Returns:
        str: 추천 모델 ID
    """
    # 우선순위: Gemini Flash > Claude Haiku > GPT-4o-mini
    priority_models = [
        "gemini-2.0-flash-exp",
        "gemini-1.5-flash",
        "claude-3-5-haiku-20241022",
        "gpt-4o-mini"
    ]

    available = get_available_models()

    for model_id in priority_models:
        if model_id in available:
            return model_id

    # 우선순위 모델이 없으면 아무거나
    if available:
        return list(available.keys())[0]

    return "gemini-2.0-flash-exp"  # 기본값


def check_prominent_people_error(error_message: str) -> bool:
    """
    에러 메시지가 PROMINENT_PEOPLE_FILTER인지 확인

    Args:
        error_message: 에러 메시지

    Returns:
        bool: PROMINENT_PEOPLE_FILTER 에러 여부
    """
    if not error_message:
        return False

    error_lower = error_message.lower()

    patterns = [
        "prominent_people",
        "prominent people",
        "celebrity",
        "public figure",
        "famous person",
        "known individual",
        "recognizable person"
    ]

    return any(pattern in error_lower for pattern in patterns)


# ============================================================
# 모듈 테스트
# ============================================================

if __name__ == "__main__":
    # 테스트
    test_prompts = [
        "Taylor Swift singing on stage with bright lights",
        "A businessman walking in New York",
        "Elon Musk presenting at a conference",
        "A cat sleeping on a couch"
    ]

    print("=== 유명인 치환 테스트 ===\n")

    # 사용 가능한 모델 확인
    available = get_available_sanitizer_models()
    print(f"사용 가능한 모델: {list(available.keys())}\n")

    if not available:
        print("API 키가 설정되지 않았습니다.")
        exit(1)

    recommended = get_recommended_model()
    print(f"추천 모델: {recommended}\n")

    try:
        sanitizer = ProminentPeopleSanitizer(ai_model=recommended)

        for prompt in test_prompts:
            print(f"원본: {prompt}")
            result = sanitizer.sanitize(prompt)
            print(f"치환: {result.sanitized_prompt}")
            print(f"수정됨: {result.was_modified}")
            if result.detected_names:
                print(f"감지된 이름: {result.detected_names}")
            print("-" * 50)

    except Exception as e:
        print(f"오류: {e}")
