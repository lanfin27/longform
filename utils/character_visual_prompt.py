# -*- coding: utf-8 -*-
"""
캐릭터 Visual Prompt 생성 모듈 v2.0

멀티 프로바이더 지원 (Anthropic, Google, OpenAI)

기능:
- 캐릭터 이름에서 visual_prompt 자동 생성
- 배치 처리로 여러 캐릭터 한 번에 처리
- 씬 분석 결과 후처리
"""

import json
from typing import List, Dict

from .ai_client import UnifiedAIClient
from .ai_providers import get_model, get_available_models


def generate_character_visual_prompts(
    characters: List[Dict],
    context: str = "",
    model: str = "claude-3-5-haiku-20241022"
) -> List[Dict]:
    """
    캐릭터들의 visual_prompt 생성

    Args:
        characters: 캐릭터 리스트 [{"name": "...", ...}, ...]
        context: 추가 컨텍스트 (스크립트 등)
        model: 사용할 AI 모델

    Returns:
        visual_prompt가 추가된 캐릭터 리스트
    """

    # visual_prompt가 없는 캐릭터 필터링
    chars_without_prompt = [
        c for c in characters
        if not c.get('visual_prompt') or c.get('visual_prompt', '').strip() == ''
    ]

    if not chars_without_prompt:
        print("[캐릭터] 모든 캐릭터에 visual_prompt가 있습니다")
        return characters

    print(f"[캐릭터] {len(chars_without_prompt)}명의 visual_prompt 생성 중...")

    # 사용 가능한 모델 확인
    available = get_available_models()
    if not available:
        print("[캐릭터] ❌ 사용 가능한 AI 모델이 없습니다. API 키를 설정해주세요.")
        return characters

    # 지정된 모델이 없으면 사용 가능한 첫 번째 모델 사용
    if model not in available:
        model = list(available.keys())[0]
        print(f"[캐릭터] 지정된 모델 사용 불가, {model} 사용")

    try:
        client = UnifiedAIClient(model_id=model)
    except Exception as e:
        print(f"[캐릭터] ❌ AI 클라이언트 초기화 실패: {e}")
        return characters

    model_info = get_model(model)
    model_name = model_info.name if model_info else model
    print(f"[캐릭터] 모델: {model_name}")

    # 캐릭터 정보 수집
    char_info_list = []
    for c in chars_without_prompt:
        char_info = {
            'name': c.get('name', '알 수 없음'),
            'role': c.get('role', ''),
            'description': c.get('description', ''),
            'name_ko': c.get('name_ko', c.get('name', ''))
        }
        char_info_list.append(char_info)

    prompt = f"""다음 캐릭터들의 외모를 이미지 생성에 적합한 영문 프롬프트로 작성해주세요.

## 캐릭터 목록
{json.dumps(char_info_list, ensure_ascii=False, indent=2)}

## 컨텍스트 (스크립트/설명)
{context[:2000] if context else '없음'}

## 작성 지침
각 캐릭터에 대해 다음을 포함한 외모 설명을 영문으로 작성해주세요:
- 성별, 나이대 (예: middle-aged man, young woman)
- 인종/민족 (추정, 예: Middle Eastern, Korean, Caucasian)
- 체형, 헤어스타일 (예: slim build, short black hair)
- 특징적인 외모 요소 (예: wearing glasses, beard)
- 의상 스타일 (예: professional suit, casual wear)
- 표정/분위기 (예: serious expression, friendly smile)

## 응답 형식
JSON 배열로 응답해주세요:
```json
[
  {{
    "name": "캐릭터명 (한국어)",
    "visual_prompt": "Middle-aged Middle Eastern man, journalist, salt-and-pepper beard, wearing glasses, serious expression, professional attire, dark suit, authoritative presence..."
  }},
  ...
]
```

⚠️ visual_prompt는 반드시 영문으로, 이미지 생성에 적합한 상세한 설명으로 작성하세요!
⚠️ 캐릭터 이름이 실제 인물인 경우 해당 인물의 알려진 외모를 기반으로 작성하세요.
JSON만 반환하세요."""

    try:
        response = client.generate(
            prompt=prompt,
            max_tokens=4000
        )

        text = response.strip()

        # JSON 파싱
        if '```json' in text:
            text = text.split('```json')[1].split('```')[0]
        elif '```' in text:
            parts = text.split('```')
            for part in parts:
                part = part.strip()
                if part.startswith('['):
                    text = part
                    break

        results = json.loads(text.strip())

        # 결과 병합
        result_map = {r['name']: r.get('visual_prompt', '') for r in results}

        updated_count = 0
        for char in characters:
            name = char.get('name', '')
            if name in result_map and result_map[name]:
                char['visual_prompt'] = result_map[name]
                print(f"[캐릭터] ✅ {name}: visual_prompt 생성됨")
                updated_count += 1

        print(f"[캐릭터] {updated_count}명의 visual_prompt 생성 완료")
        return characters

    except json.JSONDecodeError as e:
        print(f"[캐릭터] ❌ JSON 파싱 실패: {e}")
        return characters
    except Exception as e:
        print(f"[캐릭터] ❌ visual_prompt 생성 실패: {e}")
        return characters


def ensure_character_visual_prompts(scene_data: Dict, model: str = "claude-3-5-haiku-20241022") -> Dict:
    """
    씬 데이터의 캐릭터들에 visual_prompt가 있는지 확인하고 없으면 생성

    Args:
        scene_data: 씬 데이터 딕셔너리
        model: 사용할 AI 모델

    Returns:
        visual_prompt가 보장된 씬 데이터
    """

    characters = scene_data.get('characters', [])

    if not characters:
        return scene_data

    # 문자열 캐릭터를 딕셔너리로 변환
    processed_chars = []
    for char in characters:
        if isinstance(char, str):
            processed_chars.append({
                'name': char,
                'visual_prompt': ''
            })
        elif isinstance(char, dict):
            processed_chars.append(char)

    # visual_prompt 생성
    narration = scene_data.get('narration', '')
    processed_chars = generate_character_visual_prompts(
        processed_chars,
        context=narration,
        model=model
    )

    scene_data['characters'] = processed_chars

    return scene_data


def post_process_analysis_characters(
    scenes: List[Dict],
    model: str = "claude-3-5-haiku-20241022"
) -> tuple:
    """
    분석 결과 후처리 - 캐릭터 visual_prompt 확인 및 생성

    Args:
        scenes: 씬 리스트
        model: 사용할 AI 모델

    Returns:
        (업데이트된 씬 리스트, 캐릭터 리스트)
    """

    # 모든 씬에서 캐릭터 수집
    all_characters = []
    for scene in scenes:
        chars = scene.get('characters', [])
        for char in chars:
            if isinstance(char, str):
                all_characters.append({'name': char, 'visual_prompt': ''})
            elif isinstance(char, dict):
                all_characters.append(char.copy())

    # 중복 제거 (이름 기준)
    unique_chars = {}
    for char in all_characters:
        name = char.get('name', '')
        if name and name not in unique_chars:
            unique_chars[name] = char
        elif name and name in unique_chars:
            # 기존 항목에 visual_prompt가 없고 현재 항목에 있으면 업데이트
            if not unique_chars[name].get('visual_prompt') and char.get('visual_prompt'):
                unique_chars[name]['visual_prompt'] = char['visual_prompt']

    # visual_prompt가 없는 캐릭터 확인
    chars_without_prompt = [
        c for c in unique_chars.values()
        if not c.get('visual_prompt')
    ]

    if chars_without_prompt:
        print(f"[후처리] {len(chars_without_prompt)}명의 캐릭터에 visual_prompt 없음")

        # 컨텍스트 생성 (전체 나레이션의 일부)
        context = "\n".join([s.get('narration', '') for s in scenes[:5]])

        # visual_prompt 생성
        updated_chars = generate_character_visual_prompts(
            list(unique_chars.values()),
            context=context,
            model=model
        )

        # 결과 반영 - unique_chars 업데이트
        for c in updated_chars:
            name = c.get('name', '')
            if name in unique_chars:
                unique_chars[name] = c

    # 씬에 업데이트된 캐릭터 정보 반영
    char_map = {c['name']: c for c in unique_chars.values()}

    for scene in scenes:
        chars = scene.get('characters', [])
        updated = []
        for char in chars:
            name = char.get('name', char) if isinstance(char, dict) else char
            if name in char_map:
                updated.append(char_map[name].copy())
            elif isinstance(char, dict):
                updated.append(char)
            else:
                updated.append({'name': char, 'visual_prompt': ''})
        scene['characters'] = updated

    # 최종 캐릭터 리스트 생성
    final_characters = []
    for name, char in unique_chars.items():
        final_char = {
            'name': name,
            'name_ko': char.get('name_ko', name),
            'role': char.get('role', '등장인물'),
            'visual_prompt': char.get('visual_prompt', ''),
            'description': char.get('description', '')
        }
        final_characters.append(final_char)

    return scenes, final_characters


def count_characters_without_visual_prompt(characters: List[Dict]) -> int:
    """visual_prompt가 없는 캐릭터 수 반환"""
    count = 0
    for char in characters:
        if isinstance(char, dict):
            if not char.get('visual_prompt') or char.get('visual_prompt', '').strip() == '':
                count += 1
        elif isinstance(char, str):
            count += 1  # 문자열은 visual_prompt가 없는 것으로 간주
    return count


def get_characters_without_visual_prompt(characters: List[Dict]) -> List[Dict]:
    """visual_prompt가 없는 캐릭터 리스트 반환"""
    result = []
    for char in characters:
        if isinstance(char, dict):
            if not char.get('visual_prompt') or char.get('visual_prompt', '').strip() == '':
                result.append(char)
        elif isinstance(char, str):
            result.append({'name': char, 'visual_prompt': ''})
    return result
