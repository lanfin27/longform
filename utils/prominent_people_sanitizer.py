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
SANITIZE_PROMPT_TEMPLATE = """You are an expert at identifying and replacing problematic names in image generation prompts for Google ImageFX.

TASK: Analyze the following prompt and replace ANY of these with generic descriptions:
1. Celebrity/famous person names
2. Real company names (Samsung, Tesla, Apple, Google, Hyundai, ZF, Bosch, etc.)
3. Corporate titles combined with company names (e.g., "삼성전자 임원", "Tesla CEO")
4. Public figures or recognizable individuals

RULES:
1. Replace celebrity names with detailed physical descriptions (age, gender, ethnicity, hair, etc.)
2. Replace company names with generic industry descriptions:
   - "삼성전자 임원" → "middle-aged Korean man in formal business suit, professional appearance"
   - "Tesla CEO" → "businessman in smart casual attire"
   - "ZF 독일 임원" → "German businessman in formal suit"
3. Keep the original context and action
4. Preserve fictional character names from the story
5. Return ONLY valid JSON, no markdown formatting

IMPORTANT COMPANY PATTERNS TO DETECT (Korean):
- 삼성, 삼성전자, 현대, 현대자동차, LG, SK, 롯데, 카카오, 네이버
- 임원, 대표, 사장, 회장, 부회장, 전무, 상무, 이사, 팀장

IMPORTANT COMPANY PATTERNS TO DETECT (Global):
- Tesla, Apple, Google, Microsoft, Amazon, Meta, NVIDIA, Intel
- Samsung, Hyundai, Sony, Toyota, BMW, Mercedes, Bosch, ZF
- CEO, executive, director, manager

INPUT PROMPT:
{prompt}

OUTPUT FORMAT (strict JSON only):
{{
    "detected_names": ["list of celebrities/companies found"],
    "replacements": {{"original text": "replacement description"}},
    "sanitized_prompt": "the modified prompt with replacements applied",
    "was_modified": true/false
}}

If no problematic content is detected, return:
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


def sanitize_character_for_imagefx(
    character: Dict[str, Any],
    ai_model: str = None
) -> Tuple[Dict[str, Any], CharacterSanitizeResult]:
    """
    캐릭터 데이터 전체를 치환 (이름 + visual_prompt)

    Args:
        character: 캐릭터 딕셔너리 (name, visual_prompt 등 포함)
        ai_model: 사용할 AI 모델 (None이면 자동 선택)

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
        sanitizer = ProminentPeopleSanitizer(ai_model=ai_model)

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

    # 익명화된 캐릭터 데이터 생성 (원본 정보 보존)
    sanitized_character = character.copy()
    sanitized_character["name"] = result.sanitized_name
    sanitized_character["visual_prompt"] = result.sanitized_visual_prompt

    # 원본 정보 보존 (파일 저장/표시용)
    sanitized_character["_original_name"] = original_name
    sanitized_character["_original_visual_prompt"] = original_visual_prompt
    sanitized_character["_name_was_anonymized"] = result.name_was_modified
    sanitized_character["_prompt_was_anonymized"] = result.prompt_was_modified

    return sanitized_character, result


def sanitize_characters_batch(
    characters: List[Dict[str, Any]],
    ai_model: str = None,
    on_progress: callable = None
) -> Tuple[List[Dict[str, Any]], List[CharacterSanitizeResult]]:
    """
    여러 캐릭터를 배치로 익명화

    Args:
        characters: 캐릭터 목록
        ai_model: 사용할 AI 모델
        on_progress: 진행 콜백 (current, total, character_name)

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

        sanitized_char, result = sanitize_character_for_imagefx(char, ai_model)
        sanitized_characters.append(sanitized_char)
        results.append(result)

    # 통계 로깅
    name_modified_count = sum(1 for r in results if r.name_was_modified)
    prompt_modified_count = sum(1 for r in results if r.prompt_was_modified)

    logger.info(f"[캐릭터 익명화] 배치 완료: 이름 {name_modified_count}명, 프롬프트 {prompt_modified_count}명 변환됨")

    return sanitized_characters, results


def preview_character_sanitization(
    characters: List[Dict[str, Any]],
    ai_model: str = None
) -> List[Dict[str, Any]]:
    """
    캐릭터 익명화 미리보기 (이름만, 빠른 확인용)

    Args:
        characters: 캐릭터 목록
        ai_model: 사용할 AI 모델

    Returns:
        미리보기 결과 목록
    """
    if ai_model is None:
        ai_model = get_recommended_model()

    previews = []

    try:
        sanitizer = ProminentPeopleSanitizer(ai_model=ai_model)

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
    API 호출 없이 빠르게 익명화 필요 여부 확인

    Args:
        text: 확인할 텍스트

    Returns:
        bool: 익명화 필요 여부 (True면 API 호출 필요)
    """
    if not text:
        return False

    # 위험 키워드 목록 (기업명, 유명인, 직책 조합 등)
    danger_keywords = [
        # 한국 대기업
        "삼성", "삼성전자", "현대", "현대자동차", "현대차", "LG", "LG전자",
        "SK", "SK하이닉스", "롯데", "카카오", "네이버", "쿠팡",
        "기아", "포스코", "한화", "GS", "CJ", "두산", "신세계",
        # 글로벌 기업
        "Apple", "Google", "Microsoft", "Amazon", "Tesla", "Meta", "Facebook",
        "Samsung", "Hyundai", "Sony", "Toyota", "BMW", "Mercedes", "Bosch", "ZF",
        "NVIDIA", "Intel", "OpenAI", "Anthropic", "SpaceX",
        # 유명인 관련 키워드
        "이재용", "정의선", "최태원", "신동빈", "정몽구",
        "Elon", "Musk", "Tim Cook", "Zuckerberg", "Bezos", "Gates",
        "트럼프", "바이든", "Trump", "Biden",
        # 한국 직책 키워드 (기업명과 조합 시 위험)
        "임원", "대표", "회장", "부회장", "사장", "전무", "상무", "이사", "팀장",
        # 글로벌 직책 키워드
        "CEO", "executive", "director",
        # 추가 기업명
        "테슬라", "애플", "구글", "페이스북", "아마존",
    ]

    text_check = text.lower() if text else ""

    for keyword in danger_keywords:
        if keyword.lower() in text_check:
            return True

    return False


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
