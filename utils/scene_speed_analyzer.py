# -*- coding: utf-8 -*-
"""
씬 분석 속도 개선 모듈 v2.0

멀티 프로바이더 지원 (Anthropic, Google, OpenAI)

기능:
- 배치 처리: 여러 씬을 한 번의 API 호출로 분석
- 병렬 처리: concurrent.futures를 사용한 동시 처리
- 순차 처리: 안정적인 하나씩 처리
- 통합 AI 클라이언트 사용
"""

import json
import time
import concurrent.futures
from typing import List, Dict, Callable, Optional

from .ai_client import UnifiedAIClient
from .ai_providers import get_model, AIProvider


def analyze_scenes_sequential(
    scenes: List[Dict],
    model: str = "claude-sonnet-4-20250514",
    progress_callback: Optional[Callable] = None,
    status_callback: Optional[Callable] = None
) -> List[Dict]:
    """
    씬들을 순차적으로 분석 (안정적)

    Args:
        scenes: 분석할 씬 리스트
        model: 사용할 AI 모델
        progress_callback: 진행률 콜백 (0.0 ~ 1.0)
        status_callback: 상태 메시지 콜백

    Returns:
        분석된 씬 리스트
    """

    try:
        client = UnifiedAIClient(model_id=model)
    except Exception as e:
        print(f"[순차 분석] ❌ AI 클라이언트 초기화 실패: {e}")
        return scenes

    model_info = get_model(model)
    model_name = model_info.name if model_info else model
    print(f"[순차 분석] 모델: {model_name}")

    total = len(scenes)

    for i, scene in enumerate(scenes):
        if progress_callback:
            progress_callback((i + 1) / total)
        if status_callback:
            status_callback(f"씬 {scene.get('scene_id', i+1)}/{total} 분석 중...")

        try:
            result = _analyze_single_scene_with_client(client, scene)
            scene.update(result)
            print(f"[순차 분석] ✅ 씬 {scene.get('scene_id', i+1)} 완료")
        except Exception as e:
            print(f"[순차 분석] ❌ 씬 {scene.get('scene_id', i+1)} 실패: {e}")

    return scenes


def analyze_scenes_batch(
    scenes: List[Dict],
    model: str = "claude-sonnet-4-20250514",
    batch_size: int = 5,
    progress_callback: Optional[Callable] = None,
    status_callback: Optional[Callable] = None
) -> List[Dict]:
    """
    씬들을 배치로 분석 (속도 개선)

    Args:
        scenes: 분석할 씬 리스트
        model: 사용할 AI 모델
        batch_size: 한 번에 처리할 씬 수
        progress_callback: 진행률 콜백
        status_callback: 상태 메시지 콜백

    Returns:
        분석된 씬 리스트
    """

    try:
        client = UnifiedAIClient(model_id=model)
    except Exception as e:
        print(f"[배치 분석] ❌ AI 클라이언트 초기화 실패: {e}")
        return scenes

    model_info = get_model(model)
    model_name = model_info.name if model_info else model
    print(f"[배치 분석] 모델: {model_name}")

    total_scenes = len(scenes)
    analyzed_scenes = []

    # 배치 단위로 처리
    for i in range(0, total_scenes, batch_size):
        batch = scenes[i:i + batch_size]
        batch_start = i + 1
        batch_end = min(i + batch_size, total_scenes)

        if progress_callback:
            progress_callback(batch_end / total_scenes)
        if status_callback:
            status_callback(f"배치 {batch_start}-{batch_end}/{total_scenes} 처리 중...")

        print(f"[배치 분석] 씬 {batch_start}-{batch_end}/{total_scenes} 처리 중...")

        # 배치 프롬프트 생성
        batch_prompt = _create_batch_analysis_prompt(batch)

        try:
            response = client.generate(
                prompt=batch_prompt,
                max_tokens=8000
            )

            # 응답 파싱
            batch_results = _parse_batch_response(response, len(batch))

            # 원본 씬에 결과 병합
            for j, scene in enumerate(batch):
                if j < len(batch_results):
                    scene.update(batch_results[j])
                analyzed_scenes.append(scene)

            print(f"[배치 분석] ✅ 씬 {batch_start}-{batch_end} 완료")

        except Exception as e:
            print(f"[배치 분석] ❌ 배치 처리 실패: {e}")
            # 실패 시 원본 씬 유지
            for scene in batch:
                analyzed_scenes.append(scene)

    return analyzed_scenes


def analyze_scenes_parallel(
    scenes: List[Dict],
    model: str = "claude-sonnet-4-20250514",
    max_workers: int = 5,
    progress_callback: Optional[Callable] = None,
    status_callback: Optional[Callable] = None
) -> List[Dict]:
    """
    씬들을 병렬로 분석 (가장 빠름)

    Args:
        scenes: 분석할 씬 리스트
        model: 사용할 AI 모델
        max_workers: 동시 처리 수
        progress_callback: 진행률 콜백
        status_callback: 상태 메시지 콜백

    Returns:
        분석된 씬 리스트
    """

    model_info = get_model(model)
    model_name = model_info.name if model_info else model
    print(f"[병렬 분석] {len(scenes)}개 씬을 {max_workers}개 워커로 처리 (모델: {model_name})")

    if status_callback:
        status_callback(f"병렬 처리 시작 ({max_workers}개 동시 처리)...")

    # 병렬 처리
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 각 씬에 대해 분석 작업 제출
        future_to_scene = {
            executor.submit(_analyze_single_scene_standalone, scene, model): scene
            for scene in scenes
        }

        results = []
        completed = 0
        total = len(scenes)

        for future in concurrent.futures.as_completed(future_to_scene):
            scene = future_to_scene[future]
            completed += 1

            if progress_callback:
                progress_callback(completed / total)
            if status_callback:
                status_callback(f"씬 완료 ({completed}/{total})...")

            try:
                result = future.result()
                scene.update(result)
                print(f"[병렬 분석] ✅ 씬 {scene.get('scene_id', '?')} 완료 ({completed}/{total})")
            except Exception as e:
                print(f"[병렬 분석] ❌ 씬 {scene.get('scene_id', '?')} 실패: {e}")

            results.append(scene)

    # scene_id 순으로 정렬
    results.sort(key=lambda x: x.get('scene_id', 0))

    return results


def _analyze_single_scene_with_client(client: UnifiedAIClient, scene: Dict) -> Dict:
    """단일 씬 분석 (클라이언트 재사용)"""

    scene_id = scene.get('scene_id', 0)
    narration = scene.get('narration', '')
    start_time = scene.get('start_time', '')
    end_time = scene.get('end_time', '')

    if not narration.strip():
        return {}

    prompt = _create_single_scene_prompt(scene_id, narration, start_time, end_time)

    response = client.generate(
        prompt=prompt,
        max_tokens=2000
    )

    return _parse_json_response(response)


def _analyze_single_scene_standalone(scene: Dict, model: str) -> Dict:
    """단일 씬 분석 (병렬 처리용 - 독립 클라이언트)"""

    try:
        client = UnifiedAIClient(model_id=model)
        return _analyze_single_scene_with_client(client, scene)
    except Exception as e:
        print(f"[병렬 분석] 씬 {scene.get('scene_id', '?')} 클라이언트 오류: {e}")
        return {}


def _create_single_scene_prompt(scene_id: int, narration: str, start_time: str, end_time: str) -> str:
    """단일 씬 분석 프롬프트 생성"""

    return f"""다음 씬을 분석하고 JSON으로 응답해주세요.

## 씬 정보
- 씬 번호: {scene_id}
- 시간: {start_time} - {end_time}
- 나레이션: {narration}

## 출력 형식 (반드시 JSON만 출력)
{{
    "image_prompt": "한국어 이미지 프롬프트 (상세한 시각적 묘사)",
    "image_prompt_en": "English image prompt for FLUX (detailed visual description, cinematic style)",
    "character_prompt": "한국어 캐릭터 프롬프트 (인물이 있다면)",
    "character_prompt_en": "English character prompt (if characters present)",
    "direction_guide": "연출가이드 (카메라 앵글, 조명, 분위기 등)",
    "visual_elements": ["시각요소1", "시각요소2"],
    "mood": "분위기 (예: 밝은, 어두운, 긴장감 등)",
    "characters": [
        {{"name": "캐릭터명", "visual_prompt": "English visual description of character appearance..."}}
    ],
    "location": "배경 장소",
    "video_prompt_character": "영상용 캐릭터 프롬프트 (Kling/Runway용)",
    "video_prompt_full": "전체 영상 프롬프트 (Kling/Runway용)"
}}

⚠️ 중요: characters 배열의 각 캐릭터에는 반드시 visual_prompt를 영문으로 포함해주세요!

JSON으로만 응답해주세요. 추가 설명 없이 JSON만 출력하세요."""


def _create_batch_analysis_prompt(scenes: List[Dict]) -> str:
    """배치 분석용 프롬프트 생성"""

    prompt = """다음 씬들을 분석하고 JSON 배열로 응답해주세요.

각 씬에 대해 다음 필드를 포함해주세요:
- scene_id: 씬 번호
- image_prompt: 한국어 이미지 생성 프롬프트
- image_prompt_en: 영문 이미지 프롬프트 (FLUX용, 상세하게)
- character_prompt: 한국어 캐릭터 프롬프트
- character_prompt_en: 영문 캐릭터 프롬프트
- visual_elements: 시각 요소 리스트
- direction_guide: 연출 가이드
- video_prompt_character: 캐릭터 애니메이션 설명
- video_prompt_full: 전체 씬 영상 설명
- characters: 등장 캐릭터 리스트 (각 캐릭터에 name, visual_prompt 포함!)
- location: 배경 장소
- mood: 분위기

⚠️ 중요: characters 배열의 각 캐릭터에는 반드시 visual_prompt를 영문으로 포함해주세요!
예: {"name": "자말 카슈크지", "visual_prompt": "Middle-aged Middle Eastern man, journalist, salt-and-pepper beard, wearing glasses, serious expression..."}

=== 분석할 씬들 ===

"""

    for scene in scenes:
        scene_id = scene.get('scene_id', 0)
        narration = scene.get('narration', '')
        start_time = scene.get('start_time', '')
        end_time = scene.get('end_time', '')

        prompt += f"""
--- 씬 {scene_id} [{start_time} ~ {end_time}] ---
{narration}

"""

    prompt += """
=== 응답 형식 ===
JSON 배열만 반환하세요. 다른 텍스트 없이 순수 JSON만 출력하세요.
```json
[
  {
    "scene_id": 1,
    "image_prompt": "...",
    "image_prompt_en": "...",
    "characters": [
      {"name": "캐릭터명", "visual_prompt": "영문 외모 설명..."}
    ],
    ...
  },
  ...
]
```
"""

    return prompt


def _parse_batch_response(response_text: str, expected_count: int) -> List[Dict]:
    """배치 응답 파싱"""

    text = response_text.strip()

    # ```json ... ``` 형식 처리
    if '```' in text:
        parts = text.split('```')
        for part in parts:
            part = part.strip()
            if part.startswith('json'):
                text = part[4:].strip()
                break
            elif part.startswith('['):
                text = part
                break

    try:
        results = json.loads(text)
        if isinstance(results, list):
            return results
        elif isinstance(results, dict) and 'scenes' in results:
            return results['scenes']
        else:
            return [results]
    except json.JSONDecodeError as e:
        print(f"[배치 분석] JSON 파싱 오류: {e}")
        return [{} for _ in range(expected_count)]


def _parse_json_response(text: str) -> Dict:
    """JSON 응답 파싱"""

    text = text.strip()

    # ```json ... ``` 형식 처리
    if '```json' in text:
        text = text.split('```json')[1].split('```')[0]
    elif '```' in text:
        parts = text.split('```')
        for part in parts:
            part = part.strip()
            if part.startswith('{'):
                text = part
                break

    try:
        return json.loads(text.strip())
    except json.JSONDecodeError as e:
        print(f"[분석] JSON 파싱 오류: {e}")
        return {}


def analyze_scenes_with_mode(
    scenes: List[Dict],
    mode: str = "batch",
    model: str = "claude-sonnet-4-20250514",
    progress_callback: Optional[Callable] = None,
    status_callback: Optional[Callable] = None
) -> List[Dict]:
    """
    지정된 모드로 씬 분석

    Args:
        scenes: 분석할 씬 리스트
        mode: 처리 모드 ("sequential", "batch", "parallel")
        model: 사용할 AI 모델
        progress_callback: 진행률 콜백
        status_callback: 상태 메시지 콜백

    Returns:
        분석된 씬 리스트
    """

    start_time = time.time()

    model_info = get_model(model)
    model_name = model_info.name if model_info else model
    provider = model_info.provider.value if model_info else "unknown"
    print(f"[분석 시작] 모델: {model_name} ({provider}), 모드: {mode}")

    if mode == "parallel":
        result = analyze_scenes_parallel(
            scenes, model,
            progress_callback=progress_callback,
            status_callback=status_callback
        )
    elif mode == "batch":
        result = analyze_scenes_batch(
            scenes, model,
            progress_callback=progress_callback,
            status_callback=status_callback
        )
    else:  # sequential
        result = analyze_scenes_sequential(
            scenes, model,
            progress_callback=progress_callback,
            status_callback=status_callback
        )

    elapsed = time.time() - start_time
    print(f"[분석 완료] {len(scenes)}개 씬, {elapsed:.1f}초 소요 (모드: {mode}, 모델: {model_name})")

    return result
