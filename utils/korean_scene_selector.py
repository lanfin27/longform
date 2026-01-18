# -*- coding: utf-8 -*-
"""
한글 프롬프트 씬 선택 유틸리티 (v1.5)

한글 텍스트가 포함된 이미지를 생성할 씬을 자동으로 선택
- 랜덤 샘플링 (비율, 구간 텀, 혼합 모드)
- AI 추천 (Gemini, Claude 지원)

v1.5 변경사항:
- ⭐ AIPromptManager 통합 (다중 프롬프트 관리)
- ⭐ 프롬프트 매니저에서 선택된 프롬프트 자동 사용

v1.4 변경사항:
- ⭐ 사용자 정의 프롬프트 지원 (custom_prompt 파라미터 추가)
- ⭐ 프롬프트 저장/로드 기능 추가
- ⭐ 기본 프롬프트 상수 외부 접근 가능

v1.3 변경사항:
- ⭐ SceneAnalyzer의 gemini_model을 직접 사용 (자체 API 초기화 하지 않음)
- API 키 문제 완전 해결: SceneAnalyzer가 이미 검증한 모델 사용

v1.2 변경사항:
- APIManager를 사용하여 동적으로 API 키 로드 (config.settings 정적 import 대신)
- SceneAnalyzer와 동일한 genai 설정 방식 적용

v1.1 변경사항:
- API 키 로드 방식을 씬 분석과 동일하게 변경 (config.settings 사용)
"""

import random
import json
import re
from pathlib import Path
from datetime import datetime
from typing import List, Set, Dict, Any, Optional

# ⭐ v1.5: AIPromptManager 통합
try:
    from utils.ai_prompt_manager import get_prompt_manager, AIPromptManager
    PROMPT_MANAGER_AVAILABLE = True
except ImportError:
    PROMPT_MANAGER_AVAILABLE = False


# ============================================================
# ⭐ v1.4: 기본 프롬프트 템플릿 (외부 접근 가능)
# ============================================================

DEFAULT_KOREAN_PROMPT_TEMPLATE = """당신은 한글 텍스트 오버레이 전문가입니다.

## 작업
아래 씬들의 **한글 프롬프트**를 분석하고, 한글 텍스트 오버레이가 효과적일 씬을 선택하세요.

## 선택 기준 (우선순위)
1. 📊 **숫자/통계**: 금액(원), 퍼센트(%), 순위, 연도 등
2. 🏢 **기업/브랜드명**: 삼성, 현대, 테슬라, 애플 등
3. 📝 **핵심 키워드**: 기술 용어, 중요 개념
4. ⚡ **강조 문구**: 시청자 주의를 끌 내용
5. 🎯 **전환점**: 스토리의 중요한 포인트

## 제외 기준
1. 설명이 길고 복잡한 씬
2. 시각적 묘사만 있는 씬
3. 특별한 강조점이 없는 씬

## 출력 형식 (JSON만 출력, 다른 텍스트 없이)
{
    "selected_scenes": [
        {"scene_number": 1, "reason": "선택 이유", "suggested_korean_text": "추천 한글 문구"}
    ],
    "total_selected": N,
    "selection_summary": "전체 선택 요약 (50자 이내)"
}
"""

DEFAULT_ORIGINAL_PROMPT_TEMPLATE = """You are an expert in video content and Korean text overlay optimization.

## Task
Analyze the following scene prompts (in English) and select scenes where Korean text overlay would be most effective for a Korean audience.

## Selection Criteria (Priority)
1. 📊 **Numbers/Statistics**: amounts, percentages, rankings, years
2. 🏢 **Company/Brand names**: Samsung, Hyundai, Tesla, Apple, etc.
3. 📝 **Key terms**: technical terms, important concepts
4. ⚡ **Emphasis**: content that needs viewer attention
5. 🎯 **Turning points**: important story moments

## Exclusion Criteria
1. Scenes with long, complex descriptions
2. Scenes with only visual descriptions
3. Scenes without special emphasis points

## Output Format (JSON only, no other text)
{
    "selected_scenes": [
        {"scene_number": 1, "reason": "Selection reason", "suggested_korean_text": "추천 한글 문구"}
    ],
    "total_selected": N,
    "selection_summary": "Selection summary in Korean (50 chars max)"
}
"""

# 프롬프트 프리셋
PROMPT_PRESETS = {
    "기본": {
        "korean": DEFAULT_KOREAN_PROMPT_TEMPLATE,
        "original": DEFAULT_ORIGINAL_PROMPT_TEMPLATE
    },
    "엄격한 기준": {
        "korean": """당신은 한글 텍스트 오버레이 전문가입니다.
매우 엄격한 기준으로 한글 텍스트가 **반드시** 필요한 씬만 선택하세요.

## 선택 기준 (엄격 - 최소 2개 이상 충족 필요)
1. 프롬프트에 숫자/금액/퍼센트가 명시적으로 있는 경우
2. 브랜드명/기업명이 핵심인 경우
3. 화면/UI가 프롬프트의 주요 요소인 경우

## 제외 대상 (많이 제외)
1. 숫자가 없는 씬
2. 일반적인 설명 씬
3. 감정/분위기 위주 씬

## 출력 형식 (JSON만)
{"selected_scenes": [{"scene_number": N, "reason": "이유", "suggested_korean_text": "문구"}], "total_selected": N, "selection_summary": "요약"}
""",
        "original": """You are a Korean text overlay expert with STRICT selection criteria.
Only select scenes where Korean text overlay is ABSOLUTELY NECESSARY.

## Selection Criteria (Strict - must meet at least 2)
1. Explicit numbers/amounts/percentages in the prompt
2. Brand/company names as key elements
3. Screen/UI as main elements

## Exclusion (be aggressive)
1. Scenes without numbers
2. General description scenes
3. Emotion/atmosphere focused scenes

## Output Format (JSON only)
{"selected_scenes": [{"scene_number": N, "reason": "reason", "suggested_korean_text": "text"}], "total_selected": N, "selection_summary": "summary"}
"""
    },
    "관대한 기준": {
        "korean": """당신은 한글 텍스트 오버레이 전문가입니다.
한글 텍스트가 있으면 더 좋을 것 같은 씬도 폭넓게 선택하세요.

## 선택 기준 (관대 - 1개만 충족해도 선택)
1. 텍스트가 있으면 더 명확해질 장면
2. 정보 전달이 조금이라도 필요한 장면
3. 사람이 보는 화면/문서가 있는 장면
4. 환경에 간판/표지판이 있을 법한 장면
5. 숫자, 이름, 용어가 언급되는 장면

## 제외 기준 (최소한으로)
1. 순수 자연 풍경만 있는 씬
2. 추상적인 이미지 씬

## 출력 형식 (JSON만)
{"selected_scenes": [{"scene_number": N, "reason": "이유", "suggested_korean_text": "문구"}], "total_selected": N, "selection_summary": "요약"}
""",
        "original": """You are a Korean text overlay expert with LENIENT selection criteria.
Include scenes where Korean text would be beneficial, even if not strictly necessary.

## Selection Criteria (Lenient - include if any apply)
1. Scenes that would be clearer with text
2. Scenes with any information delivery
3. Scenes with screens/documents
4. Scenes where signs/banners could exist
5. Scenes mentioning numbers, names, or terms

## Exclusion (minimal)
1. Pure nature scenery only
2. Abstract imagery

## Output Format (JSON only)
{"selected_scenes": [{"scene_number": N, "reason": "reason", "suggested_korean_text": "text"}], "total_selected": N, "selection_summary": "summary"}
"""
    }
}


# ============================================================
# ⭐ v1.4: 프롬프트 저장/로드 유틸리티
# ============================================================

def get_prompt_config_path() -> Path:
    """프롬프트 설정 파일 경로"""
    return Path(__file__).parent.parent / "data" / "config" / "ai_prompts.json"


def save_custom_prompt(prompt: str, prompt_type: str = "korean") -> bool:
    """
    커스텀 프롬프트 저장

    Args:
        prompt: 저장할 프롬프트 텍스트
        prompt_type: "korean" 또는 "original"

    Returns:
        성공 여부
    """
    config_path = get_prompt_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        # 기존 설정 로드
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
        else:
            config = {}

        # 프롬프트 저장
        if "korean_text_recommendation" not in config:
            config["korean_text_recommendation"] = {}

        config["korean_text_recommendation"][f"{prompt_type}_prompt"] = prompt
        config["korean_text_recommendation"]["updated_at"] = datetime.now().isoformat()

        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

        print(f"[KoreanSceneSelector] ✅ 프롬프트 저장됨: {prompt_type}")
        return True

    except Exception as e:
        print(f"[KoreanSceneSelector] ❌ 프롬프트 저장 실패: {e}")
        return False


def load_custom_prompt(prompt_type: str = "korean") -> Optional[str]:
    """
    저장된 커스텀 프롬프트 로드

    Args:
        prompt_type: "korean" 또는 "original"

    Returns:
        저장된 프롬프트 또는 None
    """
    config_path = get_prompt_config_path()

    if not config_path.exists():
        return None

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        return config.get("korean_text_recommendation", {}).get(f"{prompt_type}_prompt")

    except Exception as e:
        print(f"[KoreanSceneSelector] ❌ 프롬프트 로드 실패: {e}")
        return None


def get_default_prompt(prompt_type: str = "korean") -> str:
    """기본 프롬프트 반환"""
    if prompt_type == "korean":
        return DEFAULT_KOREAN_PROMPT_TEMPLATE
    else:
        return DEFAULT_ORIGINAL_PROMPT_TEMPLATE


def get_effective_prompt(prompt_type: str = "korean") -> str:
    """
    실제 사용할 프롬프트 반환 (저장된 것 우선, 없으면 기본값)

    Args:
        prompt_type: "korean" 또는 "original"

    Returns:
        사용할 프롬프트
    """
    custom = load_custom_prompt(prompt_type)
    if custom:
        return custom
    return get_default_prompt(prompt_type)


# ⭐ v1.3: SceneAnalyzer 캐싱 (재사용으로 API 초기화 오버헤드 방지)
_cached_scene_analyzer = None


def _get_scene_analyzer_gemini_model():
    """
    SceneAnalyzer의 검증된 gemini_model을 가져옴

    ⭐ 핵심: 자체 API 키 로드/설정을 하지 않고,
    SceneAnalyzer가 이미 초기화한 모델을 그대로 사용
    """
    global _cached_scene_analyzer

    try:
        # 캐시된 analyzer가 있고 gemini_model이 유효하면 재사용
        if _cached_scene_analyzer is not None and _cached_scene_analyzer.gemini_model is not None:
            print("[KoreanSceneSelector] ✅ 캐시된 SceneAnalyzer.gemini_model 사용", flush=True)
            return _cached_scene_analyzer.gemini_model

        # SceneAnalyzer import 및 초기화
        from core.script.scene_analyzer import SceneAnalyzer

        print("[KoreanSceneSelector] SceneAnalyzer 초기화 중...", flush=True)

        # SceneAnalyzer 인스턴스 생성 (이미 검증된 API 키 사용)
        analyzer = SceneAnalyzer(
            provider='google',
            model_name='gemini-2.0-flash-exp',
            max_output_tokens=8192
        )

        if analyzer.gemini_model is not None:
            _cached_scene_analyzer = analyzer
            print(f"[KoreanSceneSelector] ✅ SceneAnalyzer.gemini_model 획득 성공 (모델: {analyzer.gemini_model_name})", flush=True)
            return analyzer.gemini_model
        else:
            print("[KoreanSceneSelector] ❌ SceneAnalyzer.gemini_model이 None", flush=True)
            return None

    except Exception as e:
        print(f"[KoreanSceneSelector] ❌ SceneAnalyzer 초기화 실패: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return None


def _get_anthropic_api_key() -> str:
    """Anthropic API 키를 가져오기 (config.settings 사용)"""
    try:
        from config.settings import ANTHROPIC_API_KEY
        return ANTHROPIC_API_KEY or ""
    except Exception as e:
        print(f"[KoreanSceneSelector] Anthropic API 키 로드 실패: {e}")
        return ""


# ============================================================
# 랜덤 샘플링 함수
# ============================================================

def select_korean_scenes_by_ratio(
    total_scenes: int,
    ratio_percent: float,
    seed: int = None
) -> Set[int]:
    """비율 기반 랜덤 씬 선택

    Args:
        total_scenes: 전체 씬 수 (예: 318)
        ratio_percent: 선택 비율 (예: 10.0 = 10%)
        seed: 랜덤 시드 (재현성 위해)

    Returns:
        선택된 씬 번호 집합 {1, 15, 27, 45, ...}
    """

    if seed is not None:
        random.seed(seed)

    count = max(1, int(total_scenes * ratio_percent / 100))
    all_scenes = list(range(1, total_scenes + 1))
    selected = random.sample(all_scenes, min(count, total_scenes))

    return set(sorted(selected))


def select_korean_scenes_by_interval(
    total_scenes: int,
    interval: int,
    offset: int = 0,
    randomize_offset: bool = False
) -> Set[int]:
    """구간 텀 기반 씬 선택

    Args:
        total_scenes: 전체 씬 수
        interval: 선택 간격 (예: 3 = 3씬마다 1개)
        offset: 시작 오프셋 (예: 0이면 1, 4, 7..., 1이면 2, 5, 8...)
        randomize_offset: True면 각 구간에서 랜덤 위치 선택

    Returns:
        선택된 씬 번호 집합

    Examples:
        interval=3, offset=0: {1, 4, 7, 10, 13, ...}
        interval=5, randomize=True: {2, 7, 13, 16, 24, ...}
    """

    selected = set()

    for i in range(0, total_scenes, interval):
        if randomize_offset:
            # 각 구간 내에서 랜덤 위치
            scene_in_interval = i + random.randint(0, min(interval - 1, total_scenes - i - 1))
        else:
            scene_in_interval = i + offset

        scene_num = scene_in_interval + 1  # 1-indexed

        if 1 <= scene_num <= total_scenes:
            selected.add(scene_num)

    return selected


def select_korean_scenes_hybrid(
    total_scenes: int,
    base_interval: int,
    variation: int = 1
) -> Set[int]:
    """혼합 모드: 기본 구간 + 랜덤 변동

    Args:
        total_scenes: 전체 씬 수
        base_interval: 기본 간격 (예: 5)
        variation: 변동 범위 (예: 1이면 ±1씬 변동)

    Returns:
        선택된 씬 번호 집합

    Example:
        base_interval=5, variation=1
        기본: 1, 6, 11, 16...
        실제: 1, 5, 12, 15... (±1 랜덤 적용)
    """

    selected = set()

    for i in range(0, total_scenes, base_interval):
        base_scene = i + 1
        offset = random.randint(-variation, variation)
        actual_scene = base_scene + offset

        if 1 <= actual_scene <= total_scenes:
            selected.add(actual_scene)

    return selected


# ============================================================
# AI 추천 함수
# ============================================================

KOREAN_SCENE_RECOMMENDATION_PROMPT = """
당신은 영상 콘텐츠 전문가입니다. 아래 씬들의 나레이션을 분석하고,
한글 텍스트가 포함된 이미지로 표현하면 효과적인 씬을 선택해주세요.

## 선택 기준
1. **핵심 메시지가 명확한 씬**: 짧고 임팩트 있는 문구로 표현 가능
2. **숫자/통계가 있는 씬**: "2조 원", "15억 유로" 등 강조 효과
3. **감정적 호소가 강한 씬**: 시청자의 관심을 끄는 문장
4. **전환점/결론 씬**: 중요한 포인트를 강조할 때
5. **브랜드/제품명 언급 씬**: 로고나 이름을 텍스트로 표현

## 제외 기준
1. 설명이 길고 복잡한 씬
2. 대화체가 많은 씬
3. 시각적 묘사가 중심인 씬

## 입력 데이터
전체 씬 수: {total_scenes}개
목표 선택 수: 약 {target_count}개 (전체의 {target_ratio}%)

### 씬 목록
{scenes_list}

## 출력 형식 (JSON만 출력, 다른 텍스트 없이)
{{
    "selected_scenes": [
        {{
            "scene_number": 1,
            "reason": "선택 이유 (20자 이내)",
            "suggested_korean_text": "추천 한글 문구"
        }}
    ],
    "total_selected": 32,
    "selection_summary": "전체 선택 요약 (50자 이내)"
}}
"""


def build_scenes_list_text(scenes: List[dict], max_scenes: int = 100) -> str:
    """씬 목록 텍스트 생성 (AI 프롬프트용)"""

    lines = []
    step = max(1, len(scenes) // max_scenes) if len(scenes) > max_scenes else 1

    for i, scene in enumerate(scenes):
        if i % step != 0 and len(scenes) > max_scenes:
            continue

        scene_num = scene.get("scene_id") or scene.get("scene_num") or (i + 1)
        narration = scene.get("narration", scene.get("script_text", ""))[:100]

        lines.append(f"씬 {scene_num}: {narration}")

    return "\n".join(lines)


def parse_ai_response(response: str) -> Dict[str, Any]:
    """AI 응답에서 JSON 추출"""

    # JSON 블록 찾기
    json_match = re.search(r'\{[\s\S]*\}', response)

    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError as e:
            print(f"[KoreanSceneSelector] JSON 파싱 실패: {e}")

    # 파싱 실패 시 빈 결과
    return {
        "selected_scenes": [],
        "total_selected": 0,
        "selection_summary": "AI 응답 파싱 실패"
    }


async def recommend_korean_scenes_with_ai(
    scenes: List[dict],
    model_name: str,
    target_ratio: float = 10.0,
    api_key: str = None,
    analysis_basis: str = "original",
    custom_prompt: str = None,  # ⭐ v1.4: 사용자 정의 프롬프트 파라미터 추가
    selection_mode: str = "ratio_limit"  # ⭐ v1.6: "ratio_limit" 또는 "select_all"
) -> Dict[str, Any]:
    """AI를 사용하여 한글 프롬프트 적합 씬 추천 (통합 인터페이스)

    Args:
        scenes: 씬 데이터 리스트
        model_name: 모델 ID (gemini-2.0-flash, claude-3-5-sonnet-20241022 등)
        target_ratio: 목표 선택 비율 (%) - selection_mode가 "ratio_limit"일 때만 사용
        api_key: API 키 (없으면 설정에서 로드)
        analysis_basis: "original" (원본프롬프트) 또는 "korean" (한글프롬프트)
        custom_prompt: 사용자 정의 프롬프트 (None이면 기본 프롬프트 사용)
        selection_mode: "ratio_limit" (비율 제한) 또는 "select_all" (전체 선택)

    Returns:
        {
            "selected_scenes": [...],
            "total_selected": 32,
            "model_used": "gemini-2.0-flash",
            "selection_summary": "...",
            "prompt_used": "custom" | "default",
            "selection_mode": "ratio_limit" | "select_all"
        }
    """

    # ⭐ v1.5: 프롬프트 매니저에서 프롬프트 가져오기
    prompt_source = "default"
    prompt_name = "기본"

    if custom_prompt:
        # 커스텀 프롬프트가 직접 전달된 경우
        effective_prompt = custom_prompt
        prompt_source = "custom"
        prompt_name = "직접 입력"
    elif PROMPT_MANAGER_AVAILABLE:
        # 프롬프트 매니저에서 선택된 프롬프트 사용
        try:
            pm = get_prompt_manager()
            selected = pm.get_selected_prompt()
            effective_prompt = selected.get("content", "")
            prompt_source = "manager"
            prompt_name = selected.get("name", "선택된 프롬프트")
            print(f"[KoreanSceneSelector] 프롬프트 매니저 사용: '{prompt_name}'", flush=True)
        except Exception as e:
            print(f"[KoreanSceneSelector] 프롬프트 매니저 오류: {e}", flush=True)
            effective_prompt = None
    else:
        effective_prompt = None

    print(f"[KoreanSceneSelector] AI 추천 시작 (분석 기준: {analysis_basis}, 선택 모드: {selection_mode}, 프롬프트 소스: {prompt_source})", flush=True)

    # ⭐ v1.4: 분석 기준에 따른 씬 필터링 및 프롬프트 생성
    if analysis_basis == "korean":
        # 한글프롬프트 기준: 한글 있는 씬만 필터링
        target_scenes = _filter_scenes_with_korean_prompt(scenes)
        print(f"[KoreanSceneSelector] 한글프롬프트 있는 씬: {len(target_scenes)}개 / 전체 {len(scenes)}개", flush=True)

        if not target_scenes:
            return {
                "error": "한글프롬프트가 있는 씬이 없습니다.",
                "selected_scenes": [],
                "model_used": model_name
            }

        # 씬 목록 텍스트 생성
        scenes_text = _build_korean_prompt_scenes_text(target_scenes)

        # ⭐ v1.5/v1.6: 프롬프트 매니저 또는 커스텀 프롬프트 사용 (선택 모드 지원)
        if effective_prompt:
            prompt = _build_prompt_with_custom_template(
                custom_prompt=effective_prompt,
                scenes_text=scenes_text,
                total_scenes=len(target_scenes),
                target_ratio=target_ratio,
                selection_mode=selection_mode
            )
            prompt_type = prompt_source
        else:
            prompt = _build_korean_analysis_prompt(
                scenes_text=scenes_text,
                total_scenes=len(target_scenes),
                target_ratio=target_ratio,
                selection_mode=selection_mode
            )
            prompt_type = "builtin"
    else:
        # 원본프롬프트 기준: 전체 씬 대상
        target_scenes = scenes
        print(f"[KoreanSceneSelector] 전체 씬 대상: {len(target_scenes)}개", flush=True)

        # 씬 목록 텍스트 생성
        scenes_text = _build_original_prompt_scenes_text(target_scenes)

        # ⭐ v1.5/v1.6: 프롬프트 매니저 또는 커스텀 프롬프트 사용 (선택 모드 지원)
        if effective_prompt:
            prompt = _build_prompt_with_custom_template(
                custom_prompt=effective_prompt,
                scenes_text=scenes_text,
                total_scenes=len(target_scenes),
                target_ratio=target_ratio,
                selection_mode=selection_mode
            )
            prompt_type = prompt_source
        else:
            prompt = _build_original_analysis_prompt(
                scenes_text=scenes_text,
                total_scenes=len(target_scenes),
                target_ratio=target_ratio,
                selection_mode=selection_mode
            )
            prompt_type = "builtin"

    if "gemini" in model_name.lower():
        result = await _call_gemini_with_prompt(
            prompt=prompt,
            model=model_name
        )
        result["prompt_used"] = prompt_type
        result["prompt_name"] = prompt_name
        result["selection_mode"] = selection_mode  # ⭐ v1.6
        return result
    elif "claude" in model_name.lower():
        result = await _call_claude_with_prompt(
            prompt=prompt,
            model=model_name,
            api_key=api_key
        )
        result["prompt_used"] = prompt_type
        result["prompt_name"] = prompt_name
        result["selection_mode"] = selection_mode  # ⭐ v1.6
        return result
    else:
        return {
            "error": f"지원하지 않는 모델: {model_name}",
            "selected_scenes": [],
            "prompt_used": prompt_type,
            "prompt_name": prompt_name,
            "model_used": model_name,
            "selection_mode": selection_mode  # ⭐ v1.6
        }


# ============================================================
# v1.4: 분석 기준별 헬퍼 함수들
# ============================================================

def _build_prompt_with_custom_template(
    custom_prompt: str,
    scenes_text: str,
    total_scenes: int,
    target_ratio: float,
    selection_mode: str = "ratio_limit"  # ⭐ v1.6: 선택 모드 추가
) -> str:
    """
    사용자 정의 프롬프트 템플릿으로 최종 프롬프트 생성

    Args:
        custom_prompt: 사용자 정의 프롬프트 템플릿
        scenes_text: 씬 목록 텍스트
        total_scenes: 전체 씬 수
        target_ratio: 목표 선택 비율
        selection_mode: "ratio_limit" (비율 제한) 또는 "select_all" (전체 선택)

    Returns:
        최종 프롬프트
    """
    # ⭐ v1.6: 선택 모드에 따른 씬 정보 생성
    if selection_mode == "select_all":
        # 전체 선택 모드: 비율 제한 없음
        scene_info = f"""
## 입력 데이터
전체 씬 수: {total_scenes}개

## 선택 방식
⚠️ **비율 제한 없음**: 위 기준에 해당하는 **모든 씬**을 선택해주세요.
- 기준에 부합하면 개수에 상관없이 모두 선택하세요.
- 기준에 부합하지 않는 씬은 선택하지 마세요.
- 애매한 경우는 선택하는 쪽으로 판단해주세요.

### 씬 목록
{scenes_text}
"""
    else:
        # 비율 제한 모드
        target_count = max(1, int(total_scenes * target_ratio / 100))
        scene_info = f"""
## 입력 데이터
전체 씬 수: {total_scenes}개
목표 선택 수: {target_count}개 ({target_ratio}%)

## 선택 제한
- 전체 {total_scenes}개 씬 중 약 **{target_ratio}%** (약 {target_count}개)를 선택해주세요.
- 가장 적합한 씬들을 우선 선택하세요.
- 정확히 {target_count}개가 아니어도 괜찮지만, 목표 비율에 가깝게 선택해주세요.

### 씬 목록
{scenes_text}
"""

    return custom_prompt + scene_info


def _filter_scenes_with_korean_prompt(scenes: List[dict]) -> List[dict]:
    """한글프롬프트가 있는 씬만 필터링"""
    filtered = []
    for scene in scenes:
        korean_prompt = _get_korean_prompt(scene)
        if korean_prompt:
            filtered.append(scene)
    return filtered


def _get_korean_prompt(scene: dict) -> str:
    """씬에서 한글프롬프트 추출"""
    keys = ['한글프롬프트', 'korean_prompt', 'image_prompt_ko', 'prompt_ko',
            'image_prompt_korean_text', '한글_프롬프트']

    # prompts 서브딕셔너리도 확인
    prompts = scene.get('prompts', {})

    for key in keys:
        value = scene.get(key) or prompts.get(key)
        if value and str(value).strip():
            return str(value).strip()
    return ''


def _get_original_prompt(scene: dict) -> str:
    """씬에서 원본프롬프트 추출"""
    keys = ['원본프롬프트', 'original_prompt', 'image_prompt', 'prompt',
            'visual_prompt', 'image_prompt_en']

    # prompts 서브딕셔너리도 확인
    prompts = scene.get('prompts', {})

    for key in keys:
        value = scene.get(key) or prompts.get(key)
        if value and str(value).strip():
            return str(value).strip()
    return ''


def _build_korean_prompt_scenes_text(scenes: List[dict], max_scenes: int = 100) -> str:
    """한글프롬프트 기준 씬 목록 텍스트 생성"""
    lines = []
    step = max(1, len(scenes) // max_scenes) if len(scenes) > max_scenes else 1

    for i, scene in enumerate(scenes):
        if i % step != 0 and len(scenes) > max_scenes:
            continue

        scene_num = scene.get("scene_id") or scene.get("scene_num") or (i + 1)
        korean_prompt = _get_korean_prompt(scene)[:200]
        narration = scene.get("narration", scene.get("script_text", ""))[:80]

        lines.append(f"씬 {scene_num}:\n  한글프롬프트: {korean_prompt}\n  나레이션: {narration}")

    return "\n\n".join(lines)


def _build_original_prompt_scenes_text(scenes: List[dict], max_scenes: int = 100) -> str:
    """원본프롬프트 기준 씬 목록 텍스트 생성"""
    lines = []
    step = max(1, len(scenes) // max_scenes) if len(scenes) > max_scenes else 1

    for i, scene in enumerate(scenes):
        if i % step != 0 and len(scenes) > max_scenes:
            continue

        scene_num = scene.get("scene_id") or scene.get("scene_num") or (i + 1)
        original_prompt = _get_original_prompt(scene)[:200]
        narration = scene.get("narration", scene.get("script_text", ""))[:80]

        # 원본프롬프트가 없으면 나레이션 사용
        prompt_text = original_prompt if original_prompt else narration[:150]
        lines.append(f"Scene {scene_num}:\n  Prompt: {prompt_text}\n  Narration: {narration}")

    return "\n\n".join(lines)


def _build_korean_analysis_prompt(
    scenes_text: str,
    total_scenes: int,
    target_ratio: float,
    selection_mode: str = "ratio_limit"  # ⭐ v1.6
) -> str:
    """한글프롬프트 분석용 AI 프롬프트 생성"""

    # ⭐ v1.6: 선택 모드에 따른 분기
    if selection_mode == "select_all":
        # 전체 선택 모드
        return f"""당신은 한글 텍스트 오버레이 전문가입니다.

## 작업
아래 씬들의 **한글 프롬프트**를 분석하고, 한글 텍스트 오버레이가 효과적인 **모든 씬**을 선택하세요.

## 선택 기준 (우선순위)
1. 📊 **숫자/통계**: 금액(원), 퍼센트(%), 순위, 연도 등
2. 🏢 **기업/브랜드명**: 삼성, 현대, 테슬라, 애플 등
3. 📝 **핵심 키워드**: 기술 용어, 중요 개념
4. ⚡ **강조 문구**: 시청자 주의를 끌 내용
5. 🎯 **전환점**: 스토리의 중요한 포인트

## 제외 기준
1. 설명이 길고 복잡한 씬
2. 시각적 묘사만 있는 씬
3. 특별한 강조점이 없는 씬

## 선택 방식
⚠️ **비율 제한 없음**: 위 기준에 해당하는 **모든 씬**을 선택하세요.
- 기준에 부합하면 개수에 상관없이 모두 선택하세요.
- 애매한 경우는 선택하는 쪽으로 판단하세요.

## 입력 데이터
전체 씬 수: {total_scenes}개 (한글프롬프트 있는 씬만)

### 씬 목록 (한글프롬프트)
{scenes_text}

## 출력 형식 (JSON만 출력, 다른 텍스트 없이)
{{
    "selected_scenes": [
        {{"scene_number": 1, "reason": "선택 이유", "suggested_korean_text": "추천 한글 문구"}}
    ],
    "total_selected": N,
    "selection_summary": "전체 선택 요약 (50자 이내)"
}}
"""
    else:
        # 비율 제한 모드 (기존)
        target_count = max(1, int(total_scenes * target_ratio / 100))

        return f"""당신은 한글 텍스트 오버레이 전문가입니다.

## 작업
아래 씬들의 **한글 프롬프트**를 분석하고, 한글 텍스트 오버레이가 효과적일 씬 {target_count}개를 선택하세요.

## 선택 기준 (우선순위)
1. 📊 **숫자/통계**: 금액(원), 퍼센트(%), 순위, 연도 등
2. 🏢 **기업/브랜드명**: 삼성, 현대, 테슬라, 애플 등
3. 📝 **핵심 키워드**: 기술 용어, 중요 개념
4. ⚡ **강조 문구**: 시청자 주의를 끌 내용
5. 🎯 **전환점**: 스토리의 중요한 포인트

## 제외 기준
1. 설명이 길고 복잡한 씬
2. 시각적 묘사만 있는 씬
3. 특별한 강조점이 없는 씬

## 입력 데이터
전체 씬 수: {total_scenes}개 (한글프롬프트 있는 씬만)
목표 선택 수: {target_count}개 ({target_ratio}%)

### 씬 목록 (한글프롬프트)
{scenes_text}

## 출력 형식 (JSON만 출력, 다른 텍스트 없이)
{{
    "selected_scenes": [
        {{"scene_number": 1, "reason": "선택 이유", "suggested_korean_text": "추천 한글 문구"}}
    ],
    "total_selected": {target_count},
    "selection_summary": "전체 선택 요약 (50자 이내)"
}}
"""


def _build_original_analysis_prompt(
    scenes_text: str,
    total_scenes: int,
    target_ratio: float,
    selection_mode: str = "ratio_limit"  # ⭐ v1.6
) -> str:
    """원본프롬프트 분석용 AI 프롬프트 생성 (영어)"""

    # ⭐ v1.6: 선택 모드에 따른 분기
    if selection_mode == "select_all":
        # 전체 선택 모드
        return f"""You are an expert in video content and Korean text overlay optimization.

## Task
Analyze the following scene prompts (in English) and select **ALL scenes** where Korean text overlay would be effective for a Korean audience.

## Selection Criteria (Priority)
1. 📊 **Numbers/Statistics**: amounts, percentages, rankings, years
2. 🏢 **Company/Brand names**: Samsung, Hyundai, Tesla, Apple, etc.
3. 📝 **Key terms**: technical terms, important concepts
4. ⚡ **Emphasis**: content that needs viewer attention
5. 🎯 **Turning points**: important story moments

## Exclusion Criteria
1. Scenes with long, complex descriptions
2. Scenes with only visual descriptions
3. Scenes without special emphasis points

## Selection Method
⚠️ **No ratio limit**: Select **ALL scenes** that match the criteria above.
- Select all scenes that meet the criteria regardless of count.
- When in doubt, include the scene.

## Input Data
Total scenes: {total_scenes}

### Scene List
{scenes_text}

## Output Format (JSON only, no other text)
{{
    "selected_scenes": [
        {{"scene_number": 1, "reason": "Selection reason", "suggested_korean_text": "추천 한글 문구"}}
    ],
    "total_selected": N,
    "selection_summary": "Selection summary in Korean (50 chars max)"
}}
"""
    else:
        # 비율 제한 모드 (기존)
        target_count = max(1, int(total_scenes * target_ratio / 100))

        return f"""You are an expert in video content and Korean text overlay optimization.

## Task
Analyze the following scene prompts (in English) and select {target_count} scenes where Korean text overlay would be most effective for a Korean audience.

## Selection Criteria (Priority)
1. 📊 **Numbers/Statistics**: amounts, percentages, rankings, years
2. 🏢 **Company/Brand names**: Samsung, Hyundai, Tesla, Apple, etc.
3. 📝 **Key terms**: technical terms, important concepts
4. ⚡ **Emphasis**: content that needs viewer attention
5. 🎯 **Turning points**: important story moments

## Exclusion Criteria
1. Scenes with long, complex descriptions
2. Scenes with only visual descriptions
3. Scenes without special emphasis points

## Input Data
Total scenes: {total_scenes}
Target selection: {target_count} scenes ({target_ratio}%)

### Scene List
{scenes_text}

## Output Format (JSON only, no other text)
{{
    "selected_scenes": [
        {{"scene_number": 1, "reason": "Selection reason", "suggested_korean_text": "추천 한글 문구"}}
    ],
    "total_selected": {target_count},
    "selection_summary": "Selection summary in Korean (50 chars max)"
}}
"""


async def _call_gemini_with_prompt(prompt: str, model: str) -> Dict[str, Any]:
    """Gemini API 호출 (SceneAnalyzer의 모델 사용)"""
    try:
        gemini_model = _get_scene_analyzer_gemini_model()

        if gemini_model is None:
            return {
                "error": "Gemini 모델 초기화 실패. SceneAnalyzer가 정상 작동하는지 확인하세요.",
                "selected_scenes": [],
                "model_used": model
            }

        print(f"[KoreanSceneSelector] ✅ SceneAnalyzer.gemini_model로 API 호출", flush=True)
        response = gemini_model.generate_content(prompt)
        print(f"[KoreanSceneSelector] ✅ API 응답 수신 완료", flush=True)

        result = parse_ai_response(response.text)
        result["model_used"] = model
        return result

    except Exception as e:
        print(f"[KoreanSceneSelector] Gemini API 오류: {e}")
        import traceback
        traceback.print_exc()
        return {"error": str(e), "selected_scenes": [], "model_used": model}


async def _call_claude_with_prompt(prompt: str, model: str, api_key: str = None) -> Dict[str, Any]:
    """Claude API 호출"""
    try:
        import anthropic

        if not api_key:
            api_key = _get_anthropic_api_key()

        if not api_key:
            return {
                "error": "Anthropic API 키가 설정되지 않았습니다.",
                "selected_scenes": [],
                "model_used": model
            }

        print(f"[KoreanSceneSelector] ✅ Claude API 호출 (모델: {model})", flush=True)
        client = anthropic.Anthropic(api_key=api_key)

        response = client.messages.create(
            model=model,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}]
        )

        print(f"[KoreanSceneSelector] ✅ Claude API 응답 수신 완료", flush=True)
        result = parse_ai_response(response.content[0].text)
        result["model_used"] = model
        return result

    except Exception as e:
        print(f"[KoreanSceneSelector] Claude API 오류: {e}")
        import traceback
        traceback.print_exc()
        return {"error": str(e), "selected_scenes": [], "model_used": model}


def extract_selected_scene_numbers(ai_result: Dict[str, Any]) -> Set[int]:
    """AI 추천 결과에서 씬 번호 집합 추출"""

    selected = set()

    for item in ai_result.get("selected_scenes", []):
        scene_num = item.get("scene_number")
        if scene_num:
            selected.add(scene_num)

    return selected


# ============================================================
# 통합 함수
# ============================================================

def get_korean_selection_stats(
    selected_scenes: Set[int],
    total_scenes: int
) -> Dict[str, Any]:
    """한글 씬 선택 통계"""

    return {
        "selected_count": len(selected_scenes),
        "total_count": total_scenes,
        "ratio_percent": round(len(selected_scenes) / total_scenes * 100, 1) if total_scenes > 0 else 0,
        "scene_numbers": sorted(list(selected_scenes))
    }
