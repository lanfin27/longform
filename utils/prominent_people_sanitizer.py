# -*- coding: utf-8 -*-
"""
AI 기반 유명인 치환 모듈 v3.0

ImageFX의 PROMINENT_PEOPLE_FILTER 에러를 방지하기 위해
AI를 사용하여 프롬프트에서 유명인 이름을 일반적인 설명으로 치환

지원 프로바이더:
- Google (Gemini)
- Anthropic (Claude)
- OpenAI (GPT)

v3.0 (2026-02):
- 하드코딩 완전 제거: 모든 유명인/기업 이름 목록, regex 패턴 제거
- AI 기반 동적 정제: AI 자체 지식으로 유명인/기업 탐지 및 치환
- _secondary_prompt_cleanup → _ai_secondary_prompt_cleanup: AI 기반 보조 정제
- ai_aggressive_sanitize(): Level 0/1/2 AI 기반 점진적 정제
- needs_sanitization_quick_check(): 구조적 직함 표지만 유지 (이름 목록 제거)
- 정치인 포함 모든 유명인 동적 탐지 가능

v2.0 (2026-01):
- 프롬프트 간소화: AI 응답에 sanitized_prompt 불필요 (대체 매핑만 요청)
- 로컬 치환: replacements dict를 사용하여 로컬에서 str.replace() 적용
- 재시도 로직: max_tokens 점진적 증가 (2048 → 3072 → 4096)
- JSON 완전성 검증: 괄호 균형 검사로 잘림 감지
- 상세 로깅: 입력/응답/검증 단계별 디버그 로그
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


# AI 프롬프트 템플릿 (v3.0: 하드코딩 제거 - AI 자체 지식 활용)
SANITIZE_PROMPT_TEMPLATE = """You are an expert at identifying real people's names, real company/organization names, and public figures in image generation prompts.

TASK: Analyze the prompt and provide REPLACEMENT MAPPINGS for any problematic names.

Use your own knowledge to detect ANY real-world names including but not limited to:
- Business executives, CEOs, founders of ANY company worldwide
- Politicians (presidents, prime ministers, senators, 국회의원, 장관, 대통령, etc.)
- Entertainers, athletes, journalists, professors, authors, YouTubers
- Economists, financial commentators, media personalities
- ANY Korean name (한글 2-4자) that refers to a real person, especially when paired with a title/role
- ANY real company or organization name (Korean or global)

RULES:
1. Replace real person names with physical descriptions (age, gender, ethnicity, hair, build, attire)
2. Replace real company/organization names with generic industry terms
3. The "replacements" keys must be EXACT substrings found in the input prompt
4. Keep fictional character names unchanged
5. Return ONLY valid JSON, no markdown

INPUT PROMPT:
{prompt}

OUTPUT (JSON only, NO markdown code blocks):
{{
    "detected_names": ["list of detected names/companies"],
    "replacements": {{"exact text in prompt": "replacement text"}},
    "was_modified": true
}}

If nothing problematic:
{{"detected_names": [], "replacements": {{}}, "was_modified": false}}

CRITICAL: The "replacements" keys must exactly match substrings in the input prompt. Return ONLY the JSON object."""


# v3.0: 보조 정제용 AI 프롬프트 (이름 없이도 유명인 암시 표현 탐지)
SECONDARY_CLEANUP_PROMPT_TEMPLATE = """You are an expert at detecting descriptions that implicitly identify real people in image generation prompts, even without explicit names.

TASK: The following prompt may contain descriptive phrases that strongly hint at a specific real person (e.g., "visionary Asian businessman" could imply a specific tech CEO). Replace such phrases with generic descriptions.

RULES:
1. Replace descriptions that uniquely identify a specific real person with generic alternatives
2. Replace real company/organization names with generic industry terms
3. Replace nationality + role combinations that narrow down to a specific person
4. The "replacements" keys must be EXACT substrings found in the input prompt
5. If a description could apply to many people (e.g., "a man in a suit"), leave it unchanged
6. Return ONLY valid JSON, no markdown

INPUT PROMPT:
{prompt}

OUTPUT (JSON only, NO markdown code blocks):
{{
    "detected_phrases": ["list of problematic phrases"],
    "replacements": {{"exact text in prompt": "generic replacement"}},
    "was_modified": true
}}

If nothing problematic:
{{"detected_phrases": [], "replacements": {{}}, "was_modified": false}}

CRITICAL: The "replacements" keys must exactly match substrings in the input prompt. Return ONLY the JSON object."""


# v3.0: 점진적 정제용 AI 프롬프트 (Level 0/1/2)
_AGGRESSIVE_LEVEL_PROMPTS = {
    0: """You are an expert at sanitizing image generation prompts. Remove ALL real person names and public figure references.

TASK: Replace any real person names, celebrity names, politician names, or public figure references with generic physical descriptions.

RULES:
1. Replace ALL real person names with physical descriptions
2. Replace company name + title combinations (e.g., "Samsung CEO") with generic descriptions
3. The "replacements" keys must be EXACT substrings found in the input prompt
4. Keep fictional character names unchanged
5. Return ONLY valid JSON

INPUT PROMPT:
{prompt}

OUTPUT (JSON only):
{{"replacements": {{"exact text": "replacement"}}, "was_modified": true}}
If nothing found: {{"replacements": {{}}, "was_modified": false}}""",

    1: """You are an expert at deeply sanitizing image generation prompts. Remove ALL references to real people, real companies, and identifying descriptions.

TASK: Aggressively replace any real person names, company names, organization names, and descriptions that hint at specific real people.

RULES:
1. Replace ALL real person names with generic physical descriptions
2. Replace ALL real company/organization names with generic industry terms (e.g., "Samsung" → "corporation", "Tesla" → "company")
3. Replace descriptions that hint at specific people (e.g., "visionary tech billionaire" → "business executive")
4. Replace title keywords (CEO, 회장, 부회장, chairman, etc.) with "professional" or "executive"
5. The "replacements" keys must be EXACT substrings found in the input prompt
6. Return ONLY valid JSON

INPUT PROMPT:
{prompt}

OUTPUT (JSON only):
{{"replacements": {{"exact text": "replacement"}}, "was_modified": true}}
If nothing found: {{"replacements": {{}}, "was_modified": false}}""",

    2: """You are an expert at completely sanitizing image generation prompts. Remove ALL proper nouns, specific organizations, cultural identifiers, and any detail that could identify a specific real person.

TASK: Completely generalize the prompt - remove all proper nouns, organization names, nationality-specific identifiers, and role-specific descriptions that could narrow down to real individuals.

RULES:
1. Replace ALL real person names with generic physical descriptions
2. Replace ALL company/organization names with generic terms like "corporation" or "company"
3. Replace ALL nationality + role combinations (e.g., "Korean CEO") with just the role ("executive")
4. Replace ALL specific titles (CEO, 회장, chairman, director, etc.) with "professional"
5. Replace ALL proper nouns referring to real entities
6. Remove cultural/ethnic identifiers when combined with professional roles
7. The "replacements" keys must be EXACT substrings found in the input prompt
8. Return ONLY valid JSON

INPUT PROMPT:
{prompt}

OUTPUT (JSON only):
{{"replacements": {{"exact text": "replacement"}}, "was_modified": true}}
If nothing found: {{"replacements": {{}}, "was_modified": false}}"""
}


class ProminentPeopleSanitizer:
    """유명인 이름 치환기"""

    def __init__(self, ai_model: str = "gemini-2.5-flash", prompt_template: str = None):
        """
        Args:
            ai_model: 사용할 AI 모델 ID
            prompt_template: 사용자 정의 프롬프트 템플릿 (None이면 기본 템플릿)
        """
        self.model_id = ai_model
        self.prompt_template = prompt_template or SANITIZE_PROMPT_TEMPLATE
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

    # 재시도 설정
    MAX_RETRIES = 3
    BASE_MAX_TOKENS = 2048
    TOKENS_INCREMENT = 1024  # 재시도마다 증가

    def sanitize(self, prompt: str) -> SanitizeResult:
        """
        프롬프트에서 유명인 이름을 치환 (재시도 + 점진적 max_tokens 증가)

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

        last_error = None

        for attempt in range(self.MAX_RETRIES):
            current_max_tokens = self.BASE_MAX_TOKENS + (attempt * self.TOKENS_INCREMENT)
            logger.info(f"[일반화] 시도 {attempt + 1}/{self.MAX_RETRIES}, "
                        f"max_tokens={current_max_tokens}, 모델={self.model_id}")
            logger.info(f"[일반화] 입력 프롬프트 길이: {len(prompt)}자")

            try:
                # AI 호출 (max_tokens 점진적 증가)
                ai_response = self._call_ai(prompt, max_tokens=current_max_tokens)

                # 응답 로깅
                logger.info(f"[일반화] 응답 길이: {len(ai_response)}자")
                logger.debug(f"[일반화] 응답 처음 300자: {ai_response[:300]}")
                if len(ai_response) > 300:
                    logger.debug(f"[일반화] 응답 마지막 200자: ...{ai_response[-200:]}")

                # JSON 파싱 + 검증
                result = self._parse_response(ai_response, prompt)
                result.model_used = self.model_id

                if result.error is None:
                    logger.info(f"[일반화] 시도 {attempt + 1} 성공! "
                                f"수정됨={result.was_modified}, "
                                f"감지={len(result.detected_names)}개, "
                                f"치환={len(result.replacements)}개")
                    return result

                # 파싱 에러 → 재시도
                last_error = result.error
                logger.warning(f"[일반화] 시도 {attempt + 1} 파싱 실패: {last_error}")

            except Exception as e:
                last_error = str(e)
                logger.warning(f"[일반화] 시도 {attempt + 1} 예외: {last_error}")

        # 모든 재시도 실패
        logger.error(f"[일반화] {self.MAX_RETRIES}번 시도 모두 실패. 마지막 오류: {last_error}")
        return SanitizeResult(
            original_prompt=prompt,
            sanitized_prompt=prompt,
            was_modified=False,
            detected_names=[],
            replacements={},
            model_used=self.model_id,
            error=f"[{self.MAX_RETRIES}회 재시도 실패] {last_error}"
        )

    def _call_ai(self, prompt: str, max_tokens: int = 2048) -> str:
        """AI API 호출"""
        provider = self.model_info.provider

        if provider == AIProvider.GOOGLE:
            return self._call_gemini(prompt, max_tokens=max_tokens)
        elif provider == AIProvider.ANTHROPIC:
            return self._call_claude(prompt, max_tokens=max_tokens)
        elif provider == AIProvider.OPENAI:
            return self._call_openai(prompt, max_tokens=max_tokens)
        else:
            raise ValueError(f"지원하지 않는 프로바이더: {provider}")

    def _call_gemini(self, prompt: str, max_tokens: int = 4096) -> str:
        """Gemini API 호출"""
        import google.generativeai as genai

        api_key = os.getenv("GOOGLE_API_KEY", "")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY가 설정되지 않았습니다.")

        genai.configure(api_key=api_key)

        model = genai.GenerativeModel(self.model_id)
        full_prompt = self.prompt_template.format(prompt=prompt)

        response = model.generate_content(
            full_prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.1,
                max_output_tokens=max_tokens,
            )
        )

        return response.text

    def _call_claude(self, prompt: str, max_tokens: int = 4096) -> str:
        """Claude API 호출"""
        import anthropic

        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY가 설정되지 않았습니다.")

        client = anthropic.Anthropic(api_key=api_key)
        full_prompt = self.prompt_template.format(prompt=prompt)

        response = client.messages.create(
            model=self.model_id,
            max_tokens=max_tokens,
            temperature=0.1,
            messages=[
                {"role": "user", "content": full_prompt}
            ]
        )

        return response.content[0].text

    def _call_openai(self, prompt: str, max_tokens: int = 4096) -> str:
        """OpenAI API 호출"""
        from openai import OpenAI

        api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            raise ValueError("OPENAI_API_KEY가 설정되지 않았습니다.")

        client = OpenAI(api_key=api_key)
        full_prompt = self.prompt_template.format(prompt=prompt)

        response = client.chat.completions.create(
            model=self.model_id,
            messages=[
                {"role": "user", "content": full_prompt}
            ],
            temperature=0.1,
            max_tokens=max_tokens,
        )

        return response.choices[0].message.content

    @staticmethod
    def _extract_json_text(ai_response: str) -> str:
        """AI 응답에서 JSON 텍스트 추출 (마크다운 블록 제거)"""
        cleaned = ai_response.strip()

        # ```json ... ``` 블록 추출
        if "```json" in cleaned:
            match = re.search(r'```json\s*(.*?)\s*```', cleaned, re.DOTALL)
            if match:
                return match.group(1).strip()
        # ``` ... ``` 블록 추출
        if "```" in cleaned:
            match = re.search(r'```\s*(.*?)\s*```', cleaned, re.DOTALL)
            if match:
                return match.group(1).strip()

        # JSON 객체 추출
        json_match = re.search(r'\{.*\}', cleaned, re.DOTALL)
        if json_match:
            return json_match.group()

        return cleaned

    @staticmethod
    def _check_brackets_balanced(text: str) -> bool:
        """괄호 균형 검사 (응답 잘림 감지)"""
        open_braces = text.count('{')
        close_braces = text.count('}')
        open_brackets = text.count('[')
        close_brackets = text.count(']')

        balanced = (open_braces == close_braces) and (open_brackets == close_brackets)

        if not balanced:
            logger.warning(
                f"[일반화] 괄호 불균형 감지 (응답 잘림 가능성): "
                f"{{ {open_braces}/{close_braces}, [ {open_brackets}/{close_brackets}"
            )

        return balanced

    @staticmethod
    def _apply_replacements_locally(original_prompt: str, replacements: Dict[str, str]) -> str:
        """replacements dict를 사용하여 로컬에서 프롬프트 치환"""
        result = original_prompt
        for original_text, replacement_text in replacements.items():
            if original_text in result:
                result = result.replace(original_text, replacement_text)
                logger.info(f"[일반화] 치환 적용: '{original_text}' → '{replacement_text}'")
            else:
                logger.warning(f"[일반화] 치환 키를 원본에서 찾을 수 없음: '{original_text}'")
        return result

    def _parse_response(self, ai_response: str, original_prompt: str) -> SanitizeResult:
        """AI 응답 파싱 (v2.0: 괄호 검증 + 로컬 치환 폴백)"""
        try:
            # 1. JSON 텍스트 추출
            cleaned = self._extract_json_text(ai_response)

            # 2. 괄호 균형 검사 (잘림 감지)
            if not self._check_brackets_balanced(cleaned):
                logger.warning(f"[일반화] 응답 잘림 감지. 응답 전체 길이: {len(ai_response)}자")
                logger.warning(f"[일반화] 응답 마지막 100자: ...{ai_response[-100:]}")
                return SanitizeResult(
                    original_prompt=original_prompt,
                    sanitized_prompt=original_prompt,
                    was_modified=False,
                    detected_names=[],
                    replacements={},
                    model_used=self.model_id,
                    error=f"응답 잘림 감지 (괄호 불균형, 응답 길이: {len(ai_response)}자)"
                )

            # 3. JSON 파싱
            data = json.loads(cleaned)

            # 4. 결과 추출
            detected_names = data.get("detected_names", [])
            replacements = data.get("replacements", {})
            was_modified = data.get("was_modified", bool(replacements))

            # 5. sanitized_prompt 결정 (로컬 치환 우선)
            if replacements:
                # replacements dict를 사용하여 로컬에서 치환 (잘림 위험 없음)
                sanitized_prompt = self._apply_replacements_locally(original_prompt, replacements)
                # 실제로 변경되었는지 재확인
                was_modified = (sanitized_prompt != original_prompt)
            elif "sanitized_prompt" in data and data["sanitized_prompt"]:
                # replacements가 비어있고 sanitized_prompt가 있으면 사용
                sanitized_prompt = data["sanitized_prompt"]
            else:
                sanitized_prompt = original_prompt

            logger.info(f"[일반화] 파싱 성공: 감지={len(detected_names)}개, "
                        f"치환={len(replacements)}개, 수정됨={was_modified}")

            return SanitizeResult(
                original_prompt=original_prompt,
                sanitized_prompt=sanitized_prompt,
                was_modified=was_modified,
                detected_names=detected_names,
                replacements=replacements,
                model_used=self.model_id
            )

        except json.JSONDecodeError as e:
            logger.warning(f"[일반화] JSON 파싱 실패: {e}")
            logger.warning(f"[일반화] 응답 전체 길이: {len(ai_response)}자")
            logger.warning(f"[일반화] 응답 처음 300자: {ai_response[:300]}")
            if len(ai_response) > 300:
                logger.warning(f"[일반화] 응답 마지막 200자: ...{ai_response[-200:]}")
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
    ai_model: str = "gemini-2.5-flash"
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
        "gemini-2.5-flash",
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

    return "gemini-2.5-flash"  # 기본값


def check_prominent_people_error(error_message: str, include_rate_limit: bool = True) -> bool:
    """
    에러 메시지가 PROMINENT_PEOPLE_FILTER인지 확인

    v1.1: Rate limit 에러도 유명인 필터 가능성으로 포함 (옵션)
    - ImageFX에서 유명인 감지 시 Rate limit으로 표시되는 경우가 있음

    Args:
        error_message: 에러 메시지
        include_rate_limit: Rate limit 에러도 유명인 필터 가능성으로 포함할지 여부

    Returns:
        bool: PROMINENT_PEOPLE_FILTER 에러 여부 (또는 가능성)
    """
    if not error_message:
        return False

    error_lower = error_message.lower()

    # 확실한 유명인 필터 에러 패턴
    certain_patterns = [
        "prominent_people",
        "prominent people",
        "celebrity",
        "public figure",
        "famous person",
        "known individual",
        "recognizable person",
        "must_pass_prominent",  # v1.1: ImageFX 정책 에러
        "content policy",       # v1.1: 콘텐츠 정책 위반
    ]

    # 확실한 패턴이 있으면 True
    if any(pattern in error_lower for pattern in certain_patterns):
        return True

    # Rate limit 에러도 유명인 필터 가능성으로 처리 (옵션)
    if include_rate_limit:
        rate_limit_patterns = [
            "rate limit",
            "rate_limit",
            "ratelimit",
            "too many requests",
            "quota exceeded",
        ]
        if any(pattern in error_lower for pattern in rate_limit_patterns):
            return True

    return False


def classify_imagefx_error(error_message: str) -> str:
    """
    ImageFX 에러 유형 분류 (v1.1)

    Args:
        error_message: 에러 메시지

    Returns:
        str: 에러 유형
            - "celebrity_filter": 확실한 유명인 필터 에러
            - "rate_limit_maybe_celebrity": Rate limit (유명인 필터 가능성)
            - "content_policy": 콘텐츠 정책 위반
            - "timeout": 타임아웃
            - "network": 네트워크 오류
            - "unknown": 알 수 없음
    """
    if not error_message:
        return "unknown"

    error_lower = error_message.lower()

    # 확실한 유명인 필터
    celebrity_patterns = [
        "prominent_people", "prominent people", "celebrity",
        "public figure", "famous person", "must_pass_prominent"
    ]
    if any(p in error_lower for p in celebrity_patterns):
        return "celebrity_filter"

    # 콘텐츠 정책
    if "content policy" in error_lower or "policy violation" in error_lower:
        return "content_policy"

    # Rate limit (유명인 필터 가능성)
    rate_limit_patterns = ["rate limit", "rate_limit", "ratelimit", "too many requests"]
    if any(p in error_lower for p in rate_limit_patterns):
        return "rate_limit_maybe_celebrity"

    # 타임아웃
    if "timeout" in error_lower or "timed out" in error_lower:
        return "timeout"

    # 네트워크
    if "network" in error_lower or "connection" in error_lower:
        return "network"

    return "unknown"


# ============================================================
# 캐릭터 데이터 처리 헬퍼 함수 (v3.31)
# ============================================================

@dataclass
class CharacterSanitizeResult:
    """캐릭터 치환 결과"""
    original_name: str
    sanitized_name: str
    original_visual_prompt: str
    sanitized_visual_prompt: str
    name_was_modified: bool
    prompt_was_modified: bool
    name_detected_names: List[str]
    prompt_detected_names: List[str]
    model_used: str
    error: Optional[str] = None


def _ai_secondary_prompt_cleanup(prompt: str, ai_model: str = None) -> str:
    """
    AI 기반 보조 프롬프트 정제 (v3.0)

    AI 치환기가 명시적 이름을 못 찾았지만, 이름이 유명인으로 판정된 경우
    visual_prompt에 남아있는 유명인 암시 표현을 AI로 탐지하여 일반화한다.

    Args:
        prompt: 정제할 프롬프트
        ai_model: 사용할 AI 모델 (None이면 자동 선택)

    Returns:
        정제된 프롬프트 (변경 없으면 원본 그대로)
    """
    if not prompt:
        return prompt

    if ai_model is None:
        ai_model = get_recommended_model()

    try:
        sanitizer = ProminentPeopleSanitizer(
            ai_model=ai_model,
            prompt_template=SECONDARY_CLEANUP_PROMPT_TEMPLATE
        )
        result = sanitizer.sanitize(prompt)

        if result.was_modified and result.sanitized_prompt != prompt:
            logger.info(f"[AI 보조 프롬프트 정제] 변경 적용됨: {len(result.replacements)}건")
            logger.info(f"  변경 전 (100자): {prompt[:100]}...")
            logger.info(f"  변경 후 (100자): {result.sanitized_prompt[:100]}...")
            return result.sanitized_prompt

    except Exception as e:
        logger.warning(f"[AI 보조 프롬프트 정제] AI 호출 실패 (원본 유지): {e}")

    return prompt


# ============================================================
# v3.1: 프롬프트 파트 분리 및 아트스타일 보존 (2026-02)
# ============================================================

# 아트스타일 판별 키워드 (소문자 매칭)
_ART_STYLE_MARKERS = [
    'style', 'aesthetic', 'outline', 'coloring', 'shading', 'lineart',
    'line art', 'cel-shaded', 'cel shaded', 'gradient', 'vector',
    'proportions', 'head shape', 'face style', 'body proportions',
    'color blocking', 'palette', 'desaturated', 'skin tone',
    'shadow', 'highlight', 'texture', 'animated', 'animation',
    'western 2d', 'commercial', 'bold black', 'crisp', 'flat',
    'solid color', 'no shading', 'no wrinkle', 'dot eyes', 'pupils',
    'eyebrow', 'nose', 'mouth', 'chin', 'jawline', 'ears', 'skull',
    'elongated', 'simplified hands', 'finger', 'feet', 'rounded shapes',
    'slim athletic', 'long proportional', 'muted', 'warm beige',
    'no shadows no highlights', 'environmental details', 'high quality',
    'detailed', 'clean lines', 'vibrant colors', 'cinematic',
]

# 구도·배경 판별 키워드 (소문자 매칭)
_COMPOSITION_MARKERS = [
    'pose', 'view', 'background', 'centered', 'frame', 'compositing',
    'standing', 'front view', 'side view', 'full body', 'half body',
    'single character', 'no shadows on background', 'light gray',
    'light neutral', 'plain white', 'solid gray', 'clean edges',
    'centered in frame', 'single character only', 'neutral expression',
]


def _split_prompt_into_parts(full_prompt: str) -> Dict[str, str]:
    """
    결합된 프롬프트를 3개 파트로 분리.

    Returns:
        {
            'art_style': str,      # 원본 그대로 보존할 아트스타일 파트
            'character': str,      # 변환 대상인 캐릭터 설명 파트
            'composition': str,    # 원본 그대로 보존할 구도·배경 파트
        }
    """
    clauses = [c.strip() for c in full_prompt.split(',')]

    art_parts = []
    char_parts = []
    comp_parts = []

    for clause in clauses:
        if not clause:
            continue
        cl = clause.lower()

        # 아트스타일 판별
        if any(marker in cl for marker in _ART_STYLE_MARKERS):
            art_parts.append(clause)
        # 구도·배경 판별
        elif any(marker in cl for marker in _COMPOSITION_MARKERS):
            comp_parts.append(clause)
        # 나머지는 캐릭터 설명
        else:
            char_parts.append(clause)

    return {
        'art_style': ', '.join(art_parts),
        'character': ', '.join(char_parts),
        'composition': ', '.join(comp_parts),
    }


def _reassemble_prompt(art_style: str, character: str, composition: str) -> str:
    """분리된 파트를 다시 결합. 빈 파트는 건너뜀."""
    parts = [p for p in [art_style, character, composition] if p.strip()]
    return ', '.join(parts)


def _refine_character_level_0(character_part: str) -> str:
    """
    레벨 0: 캐릭터 설명에서 시대 수식어와 역할 수행 동사구만 제거.
    복장, 성별, 표정 등 시각 요소는 그대로 유지.
    """
    refined = character_part

    # 1) 시대 수식어 제거: "retro 1970s", "classic 1960s", "vintage 1980s" 등
    refined = re.sub(
        r'(?:retro|classic|vintage|old[\s-]?school|iconic)\s+\d{4}s?\s*',
        '', refined, flags=re.IGNORECASE
    )
    # 단독 연대 제거: "1970s", "1960s" 등
    refined = re.sub(r'\b\d{4}s?\b', '', refined)

    # 2) 역할 수행 동사구 제거: "delivering news", "reading news", "broadcasting live" 등
    refined = re.sub(
        r',?\s*(?:delivering|reading|broadcasting|reporting|presenting|hosting|anchoring)\s+[\w\s]+(?=,|$)',
        '', refined, flags=re.IGNORECASE
    )

    # 3) 정리
    refined = re.sub(r',\s*,', ',', refined)
    refined = re.sub(r'\s{2,}', ' ', refined)
    refined = refined.strip().strip(',').strip()

    return refined


def _refine_character_level_1(character_part: str) -> str:
    """
    레벨 1: 레벨 0의 변환 + 직업명·역할명을 시각적 외형 설명으로 치환.
    """
    # 먼저 레벨 0 변환 적용
    refined = _refine_character_level_0(character_part)

    # 직업/역할 관련 표현 패턴 제거
    role_patterns = [
        r'\b(?:news\s*)?anchor\b',
        r'\bnewscaster\b',
        r'\bnews\s+presenter\b',
        r'\bjournalist\b',
        r'\breporter\b',
        r'\bbroadcaster\b',
        r'\btalk\s+show\s+host\b',
        r'\bTV\s+host\b',
        r'\bhost\b',
        r'\bpolitician\b',
        r'\bpresident\b',
        r'\bsenator\b',
        r'\bcelebrity\b',
        r'\bCEO\b',
        r'\bchairman\b',
        r'\bdirector\b',
        r'\bexecutive\b',
        r'\b회장\b',
        r'\b대표\b',
    ]
    for pattern in role_patterns:
        refined = re.sub(pattern, '', refined, flags=re.IGNORECASE)

    # 정리
    refined = re.sub(r',\s*,', ',', refined)
    refined = re.sub(r'\s{2,}', ' ', refined)
    refined = refined.strip().strip(',').strip()

    # 성별 감지
    gender = 'male' if re.search(r'\bmale\b', refined, re.IGNORECASE) else \
             'female' if re.search(r'\bfemale\b', refined, re.IGNORECASE) else 'male'

    # "A" 만 남았거나 비어있으면 기본 캐릭터 설명 추가
    if not refined or refined.lower() in ['a', 'a male', 'a female', 'male', 'female']:
        refined = f'A fictional {gender} character, {refined}'
    elif not re.search(r'\bcharacter\b', refined, re.IGNORECASE):
        # "A male," 같은 시작을 "A fictional [gender] character," 으로 교체
        refined = re.sub(
            r'^A\s+',
            f'A fictional {gender} character, ',
            refined, flags=re.IGNORECASE
        )
        if not refined.lower().startswith('a '):
            refined = f'A fictional {gender} character, {refined}'

    return refined


def _refine_character_level_2(character_part: str) -> str:
    """
    레벨 2: 캐릭터 설명 파트를 완전히 새로 작성.
    원본에서 시각 속성(성별, 복장 유형, 표정, 연령대)만 추출.
    """
    text = character_part.lower()

    # === 시각 속성 추출 ===

    # 성별
    if 'female' in text or 'woman' in text:
        gender = 'female'
    elif 'male' in text or 'man' in text:
        gender = 'male'
    else:
        gender = 'male'

    # 표정
    expression_match = re.search(
        r'(serious|cheerful|smiling|angry|calm|neutral|confident|stern|friendly|warm|gentle|intense)\s*(?:expression|face|look)?',
        text, re.IGNORECASE
    )
    expression = expression_match.group(1) if expression_match else 'neutral'

    # 복장
    clothing_match = re.search(
        r'wearing\s+(.*?)(?:,|$)',
        text, re.IGNORECASE
    )
    if clothing_match:
        clothing = clothing_match.group(1).strip()
        # 복장에서 직업 힌트 제거
        clothing = re.sub(r'(?:news|anchor|reporter|journalist|broadcaster|formal|business)\s*', '', clothing, flags=re.IGNORECASE).strip()
        if not clothing or len(clothing) < 3:
            clothing = 'a dark professional suit with tie'
    else:
        clothing = 'a dark professional suit with tie'

    # 연령대
    if any(w in text for w in ['young', 'youthful']):
        age = 'young adult'
    elif any(w in text for w in ['elderly', 'old', 'aged', 'senior']):
        age = 'elderly'
    else:
        age = 'middle-aged'

    # === 완전 새 캐릭터 설명 조합 ===
    rewritten = (
        f"A unique fictional {gender} character, "
        f"{age}, "
        f"{expression} expression, "
        f"wearing {clothing}, "
        f"neat combed dark hair, "
        f"clean-shaven, average build"
    )

    return rewritten


def ai_aggressive_sanitize(prompt: str, level: int = 0, ai_model: str = None) -> str:
    """
    AI 기반 점진적 프롬프트 정제 (v3.1)

    imagefx_client.py의 재시도 루프에서 호출됨.

    ⭐ v3.1 핵심 변경:
    - 아트스타일·구도 파트는 100% 원본 보존
    - 캐릭터 설명 파트만 레벨별 변환
    - Level 0: 시대 수식어 + 역할 동사구 제거 (변경률 ~15%)
    - Level 1: 직업명 제거, "fictional character" 추가 (변경률 ~30%)
    - Level 2: 캐릭터 설명 완전 재작성 (변경률 ~60%)

    Args:
        prompt: 원본 프롬프트 (항상 최초 원본에서 시작)
        level: 정제 강도 (0=기본, 1=강화, 2=완전 일반화)
        ai_model: 사용할 AI 모델 (None이면 자동 선택) - v3.1에서는 사용 안 함

    Returns:
        정제된 프롬프트
    """
    if not prompt or not prompt.strip():
        return prompt

    # 레벨 범위 제한
    level = max(0, min(2, level))

    logger.info(f"[AI 정제 v3.1] Level {level} 적용 중...")

    try:
        # ⭐ v3.1: 프롬프트를 3파트로 분리
        parts = _split_prompt_into_parts(prompt)

        art_style = parts['art_style']      # 절대 변경하지 않음
        character = parts['character']       # 이것만 변환
        composition = parts['composition']   # 절대 변경하지 않음

        original_character = character

        # ⭐ 캐릭터 파트만 레벨별 변환
        if level == 0:
            refined_character = _refine_character_level_0(character)
        elif level == 1:
            refined_character = _refine_character_level_1(character)
        elif level >= 2:
            refined_character = _refine_character_level_2(character)
        else:
            refined_character = character

        # ⭐ 원본 아트스타일 + 변환된 캐릭터 + 원본 구도로 재결합
        result = _reassemble_prompt(art_style, refined_character, composition)

        # 로깅
        from difflib import SequenceMatcher
        char_sim = SequenceMatcher(None, original_character, refined_character).ratio()
        char_change = (1 - char_sim) * 100
        full_sim = SequenceMatcher(None, prompt, result).ratio()
        full_change = (1 - full_sim) * 100

        logger.info(f"[AI 정제 v3.1] Level {level} 완료:")
        logger.info(f"  캐릭터 파트 변경률: {char_change:.1f}%")
        logger.info(f"  전체 프롬프트 변경률: {full_change:.1f}%")
        logger.info(f"  아트스타일 보존: {'✅' if art_style == parts['art_style'] else '❌'}")
        logger.info(f"  구도·배경 보존: {'✅' if composition == parts['composition'] else '❌'}")

        print(f"[AI 정제 v3.1] Level {level}:")
        print(f"  캐릭터 원본: {original_character[:80]}...")
        print(f"  캐릭터 정제: {refined_character[:80]}...")
        print(f"  캐릭터 변경률: {char_change:.1f}%, 전체 변경률: {full_change:.1f}%")

        if full_change < 5 and level > 0:
            print(f"  ⚠️ 경고: 전체 변경률이 {full_change:.1f}%로 너무 낮음!")

        return result

    except Exception as e:
        logger.warning(f"[AI 정제 v3.1] Level {level} 실패 (원본 반환): {e}")
        print(f"[AI 정제 v3.1] Level {level} 실패: {e}")
        return prompt


def sanitize_character_for_imagefx(
    character: Dict[str, Any],
    ai_model: str = None,
    prompt_template: str = None
) -> Tuple[Dict[str, Any], CharacterSanitizeResult]:
    """
    캐릭터 데이터 전체를 치환 (이름 + visual_prompt)

    Args:
        character: 캐릭터 딕셔너리 (name, visual_prompt 등 포함)
        ai_model: 사용할 AI 모델 (None이면 자동 선택)
        prompt_template: 사용자 정의 프롬프트 템플릿 (None이면 기본)

    Returns:
        Tuple[Dict, CharacterSanitizeResult]: (익명화된 캐릭터, 상세 결과)
    """
    if ai_model is None:
        ai_model = get_recommended_model()

    original_name = character.get("name", "")
    original_visual_prompt = character.get("visual_prompt", "")

    # 결과 초기화
    result = CharacterSanitizeResult(
        original_name=original_name,
        sanitized_name=original_name,
        original_visual_prompt=original_visual_prompt,
        sanitized_visual_prompt=original_visual_prompt,
        name_was_modified=False,
        prompt_was_modified=False,
        name_detected_names=[],
        prompt_detected_names=[],
        model_used=ai_model
    )

    try:
        sanitizer = ProminentPeopleSanitizer(ai_model=ai_model, prompt_template=prompt_template)

        # 1. 이름 치환
        if original_name:
            name_result = sanitizer.sanitize(original_name)
            result.sanitized_name = name_result.sanitized_prompt
            result.name_was_modified = name_result.was_modified
            result.name_detected_names = name_result.detected_names

            if name_result.was_modified:
                logger.info(f"[캐릭터 익명화] 이름 변환: '{original_name}' → '{result.sanitized_name}'")

        # 2. visual_prompt 치환
        if original_visual_prompt:
            prompt_result = sanitizer.sanitize(original_visual_prompt)
            result.sanitized_visual_prompt = prompt_result.sanitized_prompt
            result.prompt_was_modified = prompt_result.was_modified
            result.prompt_detected_names = prompt_result.detected_names

            if prompt_result.was_modified:
                logger.info(f"[캐릭터 익명화] 프롬프트 변환: {len(prompt_result.detected_names)}명 감지")

    except Exception as e:
        logger.error(f"[캐릭터 익명화] 오류: {e}")
        result.error = str(e)

    # v3.0: AI 기반 보조 프롬프트 정제 - 이름은 유명인으로 판정되었지만 프롬프트에서
    # 명시적 이름이 없어 AI가 놓친 경우, AI로 유명인 암시 표현 탐지·정제
    if result.name_was_modified and not result.prompt_was_modified and original_visual_prompt:
        cleaned = _ai_secondary_prompt_cleanup(result.sanitized_visual_prompt, ai_model=ai_model)
        if cleaned != result.sanitized_visual_prompt:
            result.sanitized_visual_prompt = cleaned
            result.prompt_was_modified = True
            logger.info(f"[캐릭터 익명화] AI 보조 프롬프트 정제 적용 (이름 유명인 → 프롬프트도 정제)")

    # 익명화된 캐릭터 데이터 생성 (원본 정보 보존)
    sanitized_character = character.copy()
    sanitized_character["name"] = result.sanitized_name
    sanitized_character["visual_prompt"] = result.sanitized_visual_prompt

    # v2.0: character_prompt, prompt 등 모든 프롬프트 필드도 동기화
    # generate_character_image()의 fallback 체인: visual_prompt → character_prompt → prompt
    # 모두 일관되게 치환된 값을 사용해야 함
    if "character_prompt" in sanitized_character:
        sanitized_character["character_prompt"] = result.sanitized_visual_prompt
    if "prompt" in sanitized_character:
        sanitized_character["prompt"] = result.sanitized_visual_prompt

    # v2.0: name_en도 치환 (영문 이름에 유명인 이름 포함될 수 있음)
    original_name_en = character.get("name_en", "")
    if original_name_en and result.name_was_modified:
        # 이름이 변경되었으면 name_en도 AI로 치환
        try:
            sanitizer = ProminentPeopleSanitizer(ai_model=ai_model, prompt_template=prompt_template)
            name_en_result = sanitizer.sanitize(original_name_en)
            if name_en_result.was_modified:
                sanitized_character["name_en"] = name_en_result.sanitized_prompt
                sanitized_character["_original_name_en"] = original_name_en
                logger.info(f"[캐릭터 익명화] 영문 이름 변환: '{original_name_en}' → '{name_en_result.sanitized_prompt}'")
        except Exception as e:
            logger.warning(f"[캐릭터 익명화] name_en 치환 실패 (무시): {e}")

    # 원본 정보 보존 (파일 저장/표시용)
    sanitized_character["_original_name"] = original_name
    sanitized_character["_original_visual_prompt"] = original_visual_prompt
    sanitized_character["_name_was_anonymized"] = result.name_was_modified
    sanitized_character["_prompt_was_anonymized"] = result.prompt_was_modified

    logger.info(f"[캐릭터 익명화] 최종 결과: name={result.name_was_modified}, "
                f"prompt={result.prompt_was_modified}, "
                f"visual_prompt 길이={len(result.sanitized_visual_prompt)}자")

    return sanitized_character, result


def sanitize_characters_batch(
    characters: List[Dict[str, Any]],
    ai_model: str = None,
    on_progress: callable = None,
    prompt_template: str = None
) -> Tuple[List[Dict[str, Any]], List[CharacterSanitizeResult]]:
    """
    여러 캐릭터를 배치로 익명화

    Args:
        characters: 캐릭터 목록
        ai_model: 사용할 AI 모델
        on_progress: 진행 콜백 (current, total, character_name)
        prompt_template: 사용자 정의 프롬프트 템플릿 (None이면 기본)

    Returns:
        Tuple[List[Dict], List[CharacterSanitizeResult]]: (익명화된 캐릭터 목록, 결과 목록)
    """
    sanitized_characters = []
    results = []
    total = len(characters)

    logger.info(f"[캐릭터 익명화] 배치 시작: {total}명")

    for i, char in enumerate(characters):
        char_name = char.get("name", f"캐릭터 {i+1}")

        if on_progress:
            on_progress(i + 1, total, char_name)

        sanitized_char, result = sanitize_character_for_imagefx(char, ai_model, prompt_template=prompt_template)
        sanitized_characters.append(sanitized_char)
        results.append(result)

    # 통계 로깅
    name_modified_count = sum(1 for r in results if r.name_was_modified)
    prompt_modified_count = sum(1 for r in results if r.prompt_was_modified)

    logger.info(f"[캐릭터 익명화] 배치 완료: 이름 {name_modified_count}명, 프롬프트 {prompt_modified_count}명 변환됨")

    return sanitized_characters, results


def preview_character_sanitization(
    characters: List[Dict[str, Any]],
    ai_model: str = None,
    prompt_template: str = None
) -> List[Dict[str, Any]]:
    """
    캐릭터 익명화 미리보기 (이름만, 빠른 확인용)

    Args:
        characters: 캐릭터 목록
        ai_model: 사용할 AI 모델
        prompt_template: 사용자 정의 프롬프트 템플릿 (None이면 기본)

    Returns:
        미리보기 결과 목록
    """
    if ai_model is None:
        ai_model = get_recommended_model()

    previews = []

    try:
        sanitizer = ProminentPeopleSanitizer(ai_model=ai_model, prompt_template=prompt_template)

        for char in characters:
            original_name = char.get("name", "")

            if original_name:
                result = sanitizer.sanitize(original_name)
                preview = {
                    "original_name": original_name,
                    "sanitized_name": result.sanitized_prompt,
                    "changed": result.was_modified,
                    "detected_names": result.detected_names,
                    "visual_prompt_preview": (char.get("visual_prompt", "")[:50] + "...")
                        if char.get("visual_prompt") else ""
                }
            else:
                preview = {
                    "original_name": "(이름 없음)",
                    "sanitized_name": "(이름 없음)",
                    "changed": False,
                    "detected_names": [],
                    "visual_prompt_preview": ""
                }

            previews.append(preview)

    except Exception as e:
        logger.error(f"[캐릭터 익명화 미리보기] 오류: {e}")
        # 오류 시 빈 결과 반환
        for char in characters:
            previews.append({
                "original_name": char.get("name", ""),
                "sanitized_name": char.get("name", ""),
                "changed": False,
                "detected_names": [],
                "visual_prompt_preview": "",
                "error": str(e)
            })

    return previews


# 빠른 체크: 변환 필요 여부 판단 (API 호출 없이)
def needs_sanitization_quick_check(text: str) -> bool:
    """
    API 호출 없이 빠르게 익명화 필요 여부 확인 (v3.0: 구조적 표지만 사용)

    하드코딩된 이름/기업 목록 대신, 직함/역할 패턴으로 판단.
    한글 이름 + 직함 조합이 있으면 유명인 가능성 높음.

    Args:
        text: 확인할 텍스트

    Returns:
        bool: 익명화 필요 여부 (True면 API 호출 필요)
    """
    if not text:
        return False

    # 구조적 직함 표지 (이름 없이도 유명인 암시 가능)
    title_keywords = [
        # 한국 직책
        "회장", "부회장", "사장", "부사장", "대표", "임원", "총수",
        "대통령", "국회의원", "장관", "총리", "의원", "위원장", "총장",
        # 글로벌 직책
        "CEO", "Chairman", "President", "executive", "director", "founder",
    ]

    text_lower = text.lower()

    for keyword in title_keywords:
        if keyword.lower() in text_lower:
            return True

    # 한글 이름 패턴 (2-4글자) + 직함/호칭 조합
    if re.search(r'[가-힣]{2,4}\s*(씨|님|회장|부회장|사장|대표|임원|교수|박사|위원|장관|의원|대통령|총리|CEO)', text):
        return True

    return False


# ============================================================
# v1.1: UI 헬퍼 함수
# ============================================================

def get_sanitizer_models_for_ui() -> List[Dict[str, str]]:
    """
    Streamlit UI용 모델 목록 반환 (v1.1)

    Returns:
        List[Dict]: [{"id": "...", "name": "...", "provider": "...", "recommended": bool}, ...]
    """
    available = get_available_models()
    recommended = get_recommended_model()

    result = []
    for model_id, model_info in available.items():
        result.append({
            "id": model_id,
            "name": model_info.name,
            "provider": model_info.provider.value if hasattr(model_info.provider, 'value') else str(model_info.provider),
            "recommended": model_id == recommended
        })

    return result


def preview_prompt_generalization(prompts: List[str], ai_model: str = None) -> List[Dict]:
    """
    프롬프트 일반화 미리보기 (v1.1)

    Args:
        prompts: 프롬프트 목록
        ai_model: 사용할 AI 모델 (None이면 자동 선택)

    Returns:
        [{"original": str, "generalized": str, "changes": list, "has_changes": bool}, ...]
    """
    if ai_model is None:
        ai_model = get_recommended_model()

    results = []

    try:
        sanitizer = ProminentPeopleSanitizer(ai_model=ai_model)

        for prompt in prompts:
            result = sanitizer.sanitize(prompt)
            results.append({
                "original": prompt,
                "generalized": result.sanitized_prompt,
                "changes": [
                    {"from": k, "to": v}
                    for k, v in result.replacements.items()
                ],
                "detected_names": result.detected_names,
                "has_changes": result.was_modified,
                "error": result.error
            })

    except Exception as e:
        # 오류 시 원본 그대로 반환
        for prompt in prompts:
            results.append({
                "original": prompt,
                "generalized": prompt,
                "changes": [],
                "detected_names": [],
                "has_changes": False,
                "error": str(e)
            })

    return results


def batch_sanitize_prompts(
    prompts: List[str],
    ai_model: str = None,
    on_progress: callable = None
) -> List[Dict]:
    """
    여러 프롬프트 일괄 일반화 (v1.1)

    Args:
        prompts: 프롬프트 목록
        ai_model: 사용할 AI 모델
        on_progress: 진행 콜백 (current, total)

    Returns:
        [{"original": str, "generalized": str, "was_modified": bool}, ...]
    """
    if ai_model is None:
        ai_model = get_recommended_model()

    results = []
    total = len(prompts)

    try:
        sanitizer = ProminentPeopleSanitizer(ai_model=ai_model)

        for i, prompt in enumerate(prompts):
            if on_progress:
                on_progress(i + 1, total)

            result = sanitizer.sanitize(prompt)
            results.append({
                "original": prompt,
                "generalized": result.sanitized_prompt,
                "was_modified": result.was_modified,
                "detected_names": result.detected_names,
                "replacements": result.replacements,
                "error": result.error
            })

    except Exception as e:
        logger.error(f"배치 일반화 오류: {e}")
        for prompt in prompts:
            results.append({
                "original": prompt,
                "generalized": prompt,
                "was_modified": False,
                "detected_names": [],
                "replacements": {},
                "error": str(e)
            })

    return results


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
