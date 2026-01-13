# -*- coding: utf-8 -*-
"""
한글 프롬프트 씬 선택 유틸리티 (v1.0)

한글 텍스트가 포함된 이미지를 생성할 씬을 자동으로 선택
- 랜덤 샘플링 (비율, 구간 텀, 혼합 모드)
- AI 추천 (Gemini, Claude 지원)
"""

import random
import json
import re
from typing import List, Set, Dict, Any, Optional


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


async def recommend_korean_scenes_with_gemini(
    scenes: List[dict],
    target_ratio: float = 10.0,
    api_key: str = None,
    model: str = "gemini-2.0-flash"
) -> Dict[str, Any]:
    """Gemini를 사용하여 한글 프롬프트 적합 씬 추천"""

    total_scenes = len(scenes)
    target_count = max(1, int(total_scenes * target_ratio / 100))

    # 씬 목록 텍스트 생성
    scenes_text = build_scenes_list_text(scenes)

    # 프롬프트 생성
    prompt = KOREAN_SCENE_RECOMMENDATION_PROMPT.format(
        total_scenes=total_scenes,
        target_count=target_count,
        target_ratio=target_ratio,
        scenes_list=scenes_text
    )

    try:
        import google.generativeai as genai

        # API 키 설정
        if not api_key:
            from utils.settings_manager import SettingsManager
            settings = SettingsManager()
            # ⭐ 수정: get(page, key, default) 형식 사용 (dict를 key로 사용하면 unhashable 오류)
            api_key = settings.get("api_preferences", "gemini_api_key", "")

        if not api_key:
            return {"error": "Gemini API 키가 설정되지 않았습니다.", "selected_scenes": []}

        genai.configure(api_key=api_key)

        model_instance = genai.GenerativeModel(model)
        response = model_instance.generate_content(prompt)

        result = parse_ai_response(response.text)
        result["model_used"] = model

        return result

    except Exception as e:
        print(f"[KoreanSceneSelector] Gemini API 오류: {e}")
        return {"error": str(e), "selected_scenes": [], "model_used": model}


async def recommend_korean_scenes_with_claude(
    scenes: List[dict],
    target_ratio: float = 10.0,
    api_key: str = None,
    model: str = "claude-3-5-sonnet-20241022"
) -> Dict[str, Any]:
    """Claude를 사용하여 한글 프롬프트 적합 씬 추천"""

    total_scenes = len(scenes)
    target_count = max(1, int(total_scenes * target_ratio / 100))

    # 씬 목록 텍스트 생성
    scenes_text = build_scenes_list_text(scenes)

    # 프롬프트 생성
    prompt = KOREAN_SCENE_RECOMMENDATION_PROMPT.format(
        total_scenes=total_scenes,
        target_count=target_count,
        target_ratio=target_ratio,
        scenes_list=scenes_text
    )

    try:
        import anthropic

        # API 키 설정
        if not api_key:
            from utils.settings_manager import SettingsManager
            settings = SettingsManager()
            # ⭐ 수정: get(page, key, default) 형식 사용 (dict를 key로 사용하면 unhashable 오류)
            api_key = settings.get("api_preferences", "anthropic_api_key", "")

        if not api_key:
            return {"error": "Anthropic API 키가 설정되지 않았습니다.", "selected_scenes": []}

        client = anthropic.Anthropic(api_key=api_key)

        response = client.messages.create(
            model=model,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}]
        )

        result = parse_ai_response(response.content[0].text)
        result["model_used"] = model

        return result

    except Exception as e:
        print(f"[KoreanSceneSelector] Claude API 오류: {e}")
        return {"error": str(e), "selected_scenes": [], "model_used": model}


async def recommend_korean_scenes_with_ai(
    scenes: List[dict],
    model_name: str,
    target_ratio: float = 10.0,
    api_key: str = None
) -> Dict[str, Any]:
    """AI를 사용하여 한글 프롬프트 적합 씬 추천 (통합 인터페이스)

    Args:
        scenes: 씬 데이터 리스트
        model_name: 모델 ID (gemini-2.0-flash, claude-3-5-sonnet-20241022 등)
        target_ratio: 목표 선택 비율 (%)
        api_key: API 키 (없으면 설정에서 로드)

    Returns:
        {
            "selected_scenes": [...],
            "total_selected": 32,
            "model_used": "gemini-2.0-flash",
            "selection_summary": "..."
        }
    """

    if "gemini" in model_name.lower():
        return await recommend_korean_scenes_with_gemini(
            scenes=scenes,
            target_ratio=target_ratio,
            api_key=api_key,
            model=model_name
        )
    elif "claude" in model_name.lower():
        return await recommend_korean_scenes_with_claude(
            scenes=scenes,
            target_ratio=target_ratio,
            api_key=api_key,
            model=model_name
        )
    else:
        return {
            "error": f"지원하지 않는 모델: {model_name}",
            "selected_scenes": [],
            "model_used": model_name
        }


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
