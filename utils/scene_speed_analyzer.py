# -*- coding: utf-8 -*-
"""
씬 분석 속도 개선 모듈 v2.0

멀티 프로바이더 지원 (Anthropic, Google, OpenAI)

기능:
- 배치 처리: 여러 씬을 한 번의 API 호출로 분석
- 병렬 처리: concurrent.futures를 사용한 동시 처리
- 순차 처리: 안정적인 하나씩 처리
- 통합 AI 클라이언트 사용
- 분석 메타데이터 추적
"""

import json
import time
import concurrent.futures
from datetime import datetime
from typing import List, Dict, Callable, Optional, Any

from .ai_client import UnifiedAIClient
from .ai_providers import get_model, AIProvider

# Claude Code 지원
def _is_claude_code_model(model: str) -> bool:
    """Claude Code 모델인지 확인"""
    if not model:
        return False
    return (
        model == "claude_code" or
        "claude_code" in model.lower() or
        "Claude Code" in model
    )


def _run_claude_code_batch_analysis(
    scenes: List[Dict],
    progress_callback: Optional[Callable] = None,
    status_callback: Optional[Callable] = None,
    **kwargs
) -> List[Dict]:
    """
    Claude Code를 사용한 배치 분석 (subprocess 실행)

    Args:
        scenes: 분석할 씬 리스트
        progress_callback: 진행률 콜백
        status_callback: 상태 메시지 콜백
        **kwargs: 추가 파라미터 (project_path, scenes_json_path, timeout 등)

    Returns:
        분석된 씬 리스트
    """
    import subprocess
    import os
    import streamlit as st

    print(f"\n{'='*70}")
    print(f"[Claude Code 배치 분석] 🚀 시작")
    print(f"[Claude Code 배치 분석] 씬 수: {len(scenes)}")
    print(f"{'='*70}\n")

    start_time = time.time()

    # 파라미터 추출
    project_path = kwargs.get('project_path', '')
    scenes_json_path = kwargs.get('scenes_json_path', '')
    timeout = kwargs.get('timeout', 600)
    bundle_mode = kwargs.get('bundle_mode', True)
    custom_instructions = kwargs.get('custom_instructions', '')

    # 프로젝트 경로 찾기
    if not project_path:
        project_path = st.session_state.get('current_project_path', '')
        if not project_path:
            project_path = st.session_state.get('project_root', '')

    # scenes.json 경로 찾기
    if not scenes_json_path and project_path:
        possible_paths = [
            os.path.join(project_path, 'analysis', 'scenes.json'),
            os.path.join(project_path, 'data', 'scenes.json'),
            os.path.join(project_path, 'scenes.json'),
        ]
        for path in possible_paths:
            if os.path.exists(path):
                scenes_json_path = path
                break

    if not scenes_json_path or not os.path.exists(scenes_json_path):
        print(f"[Claude Code 배치 분석] ❌ scenes.json 파일을 찾을 수 없습니다")
        if status_callback:
            status_callback("❌ scenes.json 파일을 찾을 수 없습니다")
        return scenes

    print(f"[Claude Code 배치 분석] 📁 scenes.json: {scenes_json_path}")

    if status_callback:
        status_callback("Claude Code로 분석 중...")

    # claude_code_runner 사용 시도
    try:
        from .claude_code_runner import run_scene_analysis_agent, SceneAnalysisResult

        def progress_cb(msg):
            if status_callback:
                status_callback(msg)
            print(f"[Claude Code] {msg}")

        result = run_scene_analysis_agent(
            scenes_json_path=scenes_json_path,
            project_path=project_path,
            scene_range=None,  # 전체 씬
            bundle_mode=bundle_mode,
            custom_instructions=custom_instructions,
            timeout=timeout,
            progress_callback=progress_cb
        )

        elapsed = time.time() - start_time

        # ═══════════════════════════════════════════════════════════════════
        # v3.71: AGENT_MODE_REQUIRED 처리 (에이전트 모드 UI 표시)
        # ═══════════════════════════════════════════════════════════════════
        if result.error == "AGENT_MODE_REQUIRED":
            print(f"[Claude Code 배치 분석] 🤖 에이전트 모드: subprocess 비활성화됨")
            print(f"[Claude Code 배치 분석] 📝 프롬프트 복사 후 수동 실행 필요")

            # 에이전트 모드 정보를 session_state에 저장
            fields_info = result.fields_generated or {}

            st.session_state['claude_code_agent_mode'] = True
            st.session_state['claude_code_prompt'] = result.output  # 프롬프트 텍스트
            st.session_state['claude_code_prompt_file'] = fields_info.get('prompt_file', '')
            st.session_state['claude_code_scenes_path'] = scenes_json_path
            st.session_state['claude_code_agent_ready'] = True

            if status_callback:
                status_callback("🤖 에이전트 모드: 프롬프트 복사 필요")

            # 씬은 변경 없이 반환 (UI에서 에이전트 모드 감지 후 처리)
            return scenes

        elif result.success:
            # scenes.json 다시 로드
            with open(scenes_json_path, 'r', encoding='utf-8') as f:
                updated_data = json.load(f)

            updated_scenes = updated_data.get('scenes', updated_data) if isinstance(updated_data, dict) else updated_data

            print(f"[Claude Code 배치 분석] ✅ 완료! ({elapsed:.1f}초)")
            print(f"[Claude Code 배치 분석] 📊 분석된 씬: {result.scenes_analyzed}개")

            # 에이전트 모드 플래그 해제
            st.session_state['claude_code_agent_mode'] = False

            if progress_callback:
                progress_callback(1.0)
            if status_callback:
                status_callback(f"✅ 완료! ({result.scenes_analyzed}개 씬 분석)")

            return updated_scenes
        else:
            print(f"[Claude Code 배치 분석] ❌ 실패: {result.error}")
            if status_callback:
                status_callback(f"❌ 실패: {result.error}")
            return scenes

    except ImportError as e:
        print(f"[Claude Code 배치 분석] ❌ claude_code_runner 모듈 없음: {e}")
        if status_callback:
            status_callback("❌ claude_code_runner 모듈을 찾을 수 없습니다")
        return scenes
    except Exception as e:
        print(f"[Claude Code 배치 분석] ❌ 오류: {e}")
        if status_callback:
            status_callback(f"❌ 오류: {e}")
        return scenes


# ============================================================
# 분석 메타데이터 추적
# ============================================================
_analysis_metadata: Dict[str, Any] = {}


def get_analysis_metadata() -> Dict[str, Any]:
    """마지막 분석에 사용된 메타데이터 반환"""
    global _analysis_metadata
    return _analysis_metadata.copy()


def clear_analysis_metadata():
    """분석 메타데이터 초기화"""
    global _analysis_metadata
    _analysis_metadata = {}


def _update_analysis_metadata(key: str, value: Any):
    """분석 메타데이터 업데이트"""
    global _analysis_metadata
    _analysis_metadata[key] = value


def _safe_template_format(template: str, **kwargs) -> str:
    """
    JSON 예시가 포함된 템플릿을 안전하게 포맷팅

    Python .format()은 JSON 예시의 {}를 변수로 인식하여 KeyError 발생
    → .replace()를 사용하여 플레이스홀더만 정확히 치환

    Args:
        template: 템플릿 문자열
        **kwargs: 치환할 변수들 (예: scenes_content="...", scene_id=1)

    Returns:
        포맷팅된 문자열
    """
    result = template

    for key, value in kwargs.items():
        placeholder = "{" + key + "}"
        if placeholder in result:
            result = result.replace(placeholder, str(value))
            print(f"[SafeFormat] ✅ '{placeholder}' 치환됨")

    return result


def analyze_scenes_sequential(
    scenes: List[Dict],
    model: str = "claude-sonnet-4-20250514",
    progress_callback: Optional[Callable] = None,
    status_callback: Optional[Callable] = None,
    **kwargs  # v3.60: Claude Code 추가 파라미터 지원
) -> List[Dict]:
    """
    씬들을 순차적으로 분석 (안정적)

    Args:
        scenes: 분석할 씬 리스트
        model: 사용할 AI 모델
        progress_callback: 진행률 콜백 (0.0 ~ 1.0)
        status_callback: 상태 메시지 콜백
        **kwargs: 추가 파라미터 (Claude Code용)

    Returns:
        분석된 씬 리스트
    """

    # v3.60: Claude Code 모델 분기 처리
    if _is_claude_code_model(model):
        print(f"[순차 분석] 🤖 Claude Code 감지 - subprocess 실행으로 전환")
        return _run_claude_code_batch_analysis(
            scenes=scenes,
            progress_callback=progress_callback,
            status_callback=status_callback,
            **kwargs
        )

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
            # v2.3: 병합 전 필드 확인
            has_bg_before = bool(scene.get('background_prompt_en'))
            has_bg_in_result = bool(result.get('background_prompt_en'))
            scene.update(result)
            has_bg_after = bool(scene.get('background_prompt_en'))

            if has_bg_in_result and has_bg_after:
                print(f"[순차 병합] ✅ 씬 {scene.get('scene_id', i+1)}: background_prompt_en 추가됨")
            elif not has_bg_in_result:
                print(f"[순차 병합] ⚠️ 씬 {scene.get('scene_id', i+1)}: 분석 결과에 background_prompt_en 없음")

            print(f"[순차 분석] ✅ 씬 {scene.get('scene_id', i+1)} 완료")
        except Exception as e:
            print(f"[순차 분석] ❌ 씬 {scene.get('scene_id', i+1)} 실패: {e}")

    return scenes


def analyze_scenes_batch(
    scenes: List[Dict],
    model: str = "claude-sonnet-4-20250514",
    batch_size: int = 5,
    progress_callback: Optional[Callable] = None,
    status_callback: Optional[Callable] = None,
    prompt_id: str = None,  # ⭐ v3.27: UI에서 선택한 프롬프트 ID 직접 전달
    **kwargs  # v3.60: Claude Code 추가 파라미터 지원
) -> List[Dict]:
    """
    씬들을 배치로 분석 (속도 개선)

    Args:
        scenes: 분석할 씬 리스트
        model: 사용할 AI 모델
        batch_size: 한 번에 처리할 씬 수
        progress_callback: 진행률 콜백
        status_callback: 상태 메시지 콜백
        prompt_id: UI에서 선택한 프롬프트 ID (직접 전달!)
        **kwargs: 추가 파라미터 (Claude Code용)

    Returns:
        분석된 씬 리스트
    """

    # ═══════════════════════════════════════════════════════════
    # v3.60: Claude Code 모델 분기 처리
    # ═══════════════════════════════════════════════════════════
    if _is_claude_code_model(model):
        print(f"[배치 분석] 🤖 Claude Code 감지 - subprocess 실행으로 전환")
        return _run_claude_code_batch_analysis(
            scenes=scenes,
            progress_callback=progress_callback,
            status_callback=status_callback,
            **kwargs
        )

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

        # 배치 프롬프트 생성 (⭐ v3.27: prompt_id 직접 전달!)
        batch_prompt = _create_batch_analysis_prompt(batch, prompt_id=prompt_id)

        try:
            response = client.generate(
                prompt=batch_prompt,
                max_tokens=8000
            )

            # 응답 파싱 (v2.2: 필드 정규화 포함)
            batch_results = _parse_batch_response(response, len(batch))

            # 원본 씬에 결과 병합 (v2.2: 병합 로깅 강화)
            for j, scene in enumerate(batch):
                if j < len(batch_results):
                    result = batch_results[j]
                    scene_id = scene.get('scene_id', batch_start + j)

                    # 병합 전 필드 확인
                    has_bg_before = bool(scene.get('background_prompt_en'))
                    has_bg_in_result = bool(result.get('background_prompt_en'))

                    scene.update(result)

                    # 병합 후 확인
                    has_bg_after = bool(scene.get('background_prompt_en'))

                    if has_bg_in_result and has_bg_after:
                        print(f"[병합] ✅ 씬 {scene_id}: background_prompt_en 추가됨")
                    elif not has_bg_in_result:
                        print(f"[병합] ⚠️ 씬 {scene_id}: AI 응답에 background_prompt_en 없음")

                analyzed_scenes.append(scene)

            # 배치 결과 요약
            bg_count = sum(1 for s in batch_results if s.get('background_prompt_en'))
            print(f"[배치 분석] ✅ 씬 {batch_start}-{batch_end} 완료 (background_prompt_en: {bg_count}/{len(batch_results)})")

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
    status_callback: Optional[Callable] = None,
    **kwargs  # v3.60: Claude Code 추가 파라미터 지원
) -> List[Dict]:
    """
    씬들을 병렬로 분석 (가장 빠름)

    Args:
        scenes: 분석할 씬 리스트
        model: 사용할 AI 모델
        max_workers: 동시 처리 수
        progress_callback: 진행률 콜백
        status_callback: 상태 메시지 콜백
        **kwargs: 추가 파라미터 (Claude Code용)

    Returns:
        분석된 씬 리스트
    """

    # v3.60: Claude Code 모델 분기 처리
    if _is_claude_code_model(model):
        print(f"[병렬 분석] 🤖 Claude Code 감지 - subprocess 실행으로 전환")
        return _run_claude_code_batch_analysis(
            scenes=scenes,
            progress_callback=progress_callback,
            status_callback=status_callback,
            **kwargs
        )

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
                # v2.3: 병합 전 필드 확인
                has_bg_before = bool(scene.get('background_prompt_en'))
                has_bg_in_result = bool(result.get('background_prompt_en'))
                scene.update(result)
                has_bg_after = bool(scene.get('background_prompt_en'))

                if has_bg_in_result and has_bg_after:
                    print(f"[병렬 병합] ✅ 씬 {scene.get('scene_id', '?')}: background_prompt_en 추가됨")
                elif not has_bg_in_result:
                    print(f"[병렬 병합] ⚠️ 씬 {scene.get('scene_id', '?')}: 분석 결과에 background_prompt_en 없음")

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
    """단일 씬 분석 프롬프트 생성 (템플릿 시스템 사용)"""
    global _analysis_metadata

    # 템플릿 매니저에서 프롬프트 로드
    try:
        from core.prompt.prompt_template_manager import get_template_manager
        template_manager = get_template_manager()
        template = template_manager.get_srt_single_template()
        template_prompt = template.prompt if template else None

        if template_prompt:
            # 템플릿에 변수 치환 (v2.1: .replace() 방식으로 JSON 예시와 충돌 방지)
            prompt = _safe_template_format(
                template_prompt,
                scene_id=scene_id,
                start_time=start_time,
                end_time=end_time,
                narration=narration
            )

            # ⭐ 메타데이터 저장 (첫 번째 호출에서만)
            template_id = template.id if template else 'srt_scene_single'
            template_name = template.name if template else 'v1.0'
            is_default = getattr(template, 'is_default', True) if template else True

            if 'prompt_template' not in _analysis_metadata:
                _analysis_metadata['mode'] = 'single'
                _analysis_metadata['template_name'] = template_id
                _analysis_metadata['template_version'] = template_name
                _analysis_metadata['prompt_template'] = template_prompt
                _analysis_metadata['prompt_char_count'] = len(template_prompt)
                _analysis_metadata['prompt_example'] = prompt  # 첫 씬에 적용된 예시
                _analysis_metadata['is_default_template'] = is_default

            # v1.1: 실제 사용된 템플릿 ID 출력 (하드코딩 제거)
            print(f"[SRT 분석] 템플릿 프롬프트 사용 ({template_id}: {template_name})")

            # v1.2: 🔍 프롬프트 핵심 키워드 검증 (단일 씬 분석용)
            keywords_check = {
                "한글텍스트_필드": "image_prompt_korean_text" in template_prompt,
                "카툰_스타일_영문": "cartoon character design" in template_prompt.lower(),
                "인물_스타일_규칙": "stylized Western cartoon" in template_prompt,
            }
            print(f"[SRT 분석] 📊 단일 씬 키워드 검증: {keywords_check}")

            return prompt
    except Exception as e:
        print(f"[SRT 분석] 템플릿 로드 실패, 기본 프롬프트 사용: {e}")
        import traceback
        print(f"[SRT 분석] 상세 오류: {traceback.format_exc()}")

    # 폴백: 기본 하드코딩된 프롬프트
    print(f"[SRT 분석] ⚠️ 기본 하드코딩 프롬프트 사용 (단일 씬)")
    return f"""다음 씬을 분석하고 JSON으로 응답해주세요.

## 씬 정보
- 씬 번호: {scene_id}
- 시간: {start_time} - {end_time}
- 나레이션: {narration}

## 출력 형식 (반드시 JSON만 출력)
{{
    "image_prompt": "한국어 이미지 프롬프트 (상세한 시각적 묘사)",
    "image_prompt_en": "English image prompt for FLUX (detailed visual description, cinematic style). Must include: absolutely no text, no letters, no words, no characters, no writing",
    "image_prompt_korean_text": "영문 이미지 프롬프트 + 한글 텍스트 삽입. image_prompt_en의 시각적 묘사를 사용하되, 나레이션에서 추출한 핵심 메시지를 한글 텍스트로 포함. 형식: [시각적 묘사], headline text in Korean reading \\\"[나레이션 핵심 5-10자]\\\" at the top in handwritten pen script style, subtitle text in Korean reading \\\"[부가 설명 10-20자]\\\" at the bottom in informal handwritten font style, all Korean text in natural hand-drawn pen calligraphy style with slight irregularity",
    "character_prompt": "한국어 캐릭터 프롬프트 (인물이 있다면)",
    "character_prompt_en": "English character prompt (if characters present)",
    "direction_guide": "연출가이드 (카메라 앵글, 조명, 분위기 등)",
    "visual_elements": ["시각요소1", "시각요소2"],
    "mood": "분위기 (예: 밝은, 어두운, 긴장감 등)",
    "characters": [
        {{"name": "캐릭터명", "visual_prompt": "English visual description of character appearance..."}}
    ],
    "location": "배경 장소",
    "video_prompt_character": "Character animation description in ENGLISH for Kling/Runway",
    "video_prompt_full": "Full scene video description in ENGLISH for Kling/Runway"
}}

⚠️ 중요: characters 배열의 각 캐릭터에는 반드시 visual_prompt를 영문으로 포함해주세요!
⚠️ video_prompt_character와 video_prompt_full은 반드시 영어로 작성하세요!
⚠️ image_prompt_korean_text는 나레이션의 핵심 메시지를 한글 텍스트로 포함해야 합니다!

JSON으로만 응답해주세요. 추가 설명 없이 JSON만 출력하세요."""


def _create_batch_analysis_prompt(scenes: List[Dict], prompt_id: str = None) -> str:
    """
    배치 분석용 프롬프트 생성 (템플릿 시스템 사용)

    Args:
        scenes: 분석할 씬 리스트
        prompt_id: 사용할 프롬프트 ID (직접 전달, None이면 fallback)
    """
    global _analysis_metadata

    # 씬 내용 문자열 생성
    scenes_content = ""
    for scene in scenes:
        scene_id = scene.get('scene_id', 0)
        narration = scene.get('narration', '')
        start_time = scene.get('start_time', '')
        end_time = scene.get('end_time', '')

        scenes_content += f"""
--- 씬 {scene_id} [{start_time} ~ {end_time}] ---
{narration}

"""

    # 템플릿 매니저에서 프롬프트 로드
    try:
        from core.prompt.prompt_template_manager import get_template_manager
        template_manager = get_template_manager()

        # v3.27: 상세 로깅 - UI에서 전달된 프롬프트 우선 사용
        print(f"[SRT 배치 분석] ========== 프롬프트 로딩 시작 ==========")
        print(f"[SRT 배치 분석] UI에서 전달된 prompt_id: {prompt_id}")

        # ⭐ v3.27: UI에서 전달된 prompt_id 우선 사용!
        if prompt_id:
            template = template_manager.get_template(prompt_id)
            if template:
                print(f"[SRT 배치 분석] ✅ UI 선택 프롬프트 사용: {prompt_id}")
            else:
                print(f"[SRT 배치 분석] ⚠️ 전달된 ID '{prompt_id}' 없음, fallback 사용")
                template = template_manager.get_srt_batch_template()
        else:
            # fallback: 기존 방식 (get_active_prompt 사용)
            print(f"[SRT 배치 분석] ⚠️ prompt_id 미전달, get_active_prompt 사용 (fallback)")
            active_id = template_manager.get_active_prompt("batch")
            print(f"[SRT 배치 분석] 활성 프롬프트 ID (batch): {active_id}")
            template = template_manager.get_srt_batch_template()

        template_prompt = template.prompt if template else None

        print(f"[SRT 배치 분석] 선택된 템플릿 ID: {template.id if template else 'None'}")
        print(f"[SRT 배치 분석] 선택된 템플릿 이름: {template.name if template else 'None'}")
        print(f"[SRT 배치 분석] 기본 템플릿 여부: {template.is_default if template else 'N/A'}")
        print(f"[SRT 배치 분석] 프롬프트 길이: {len(template_prompt) if template_prompt else 0} 문자")

        # 프롬프트 처음 200자 미리보기
        if template_prompt:
            preview = template_prompt[:200].replace('\n', ' ')
            print(f"[SRT 배치 분석] 프롬프트 미리보기: {preview}...")

        print(f"[SRT 배치 분석] ========== 프롬프트 로딩 완료 ==========")

        if template_prompt:
            # 템플릿에 씬 내용 삽입 (v2.1: .replace() 방식으로 JSON 예시와 충돌 방지)
            prompt = _safe_template_format(template_prompt, scenes_content=scenes_content)

            # ⭐ 메타데이터 저장 (첫 번째 호출에서만)
            template_id = template.id if template else 'srt_scene_batch'
            template_name = template.name if template else 'v1.0'
            is_default = getattr(template, 'is_default', True) if template else True

            if 'prompt_template' not in _analysis_metadata:
                _analysis_metadata['mode'] = 'batch'
                _analysis_metadata['template_name'] = template_id
                _analysis_metadata['template_version'] = template_name
                _analysis_metadata['prompt_template'] = template_prompt
                _analysis_metadata['prompt_char_count'] = len(template_prompt)
                _analysis_metadata['prompt_example'] = prompt  # 첫 배치에 적용된 예시
                _analysis_metadata['is_default_template'] = is_default

            # v1.1: 실제 사용된 템플릿 ID 출력 (하드코딩 제거)
            print(f"[SRT 분석] 템플릿 프롬프트 사용 ({template_id}: {template_name})")

            # v1.2: 🔍 프롬프트 핵심 키워드 검증 (배치 분석용)
            keywords_check = {
                "한글텍스트_필드": "image_prompt_korean_text" in template_prompt,
                "카툰_스타일_영문": "cartoon character design" in template_prompt.lower(),
                "인물_스타일_규칙": "stylized Western cartoon" in template_prompt,
                "텍스트_배치_규칙": "upper 70%" in template_prompt,
                "숫자날짜_변환": "숫자" in template_prompt or "날짜" in template_prompt,
            }
            print(f"[SRT 분석] 📊 핵심 키워드 검증: {keywords_check}")

            # 최종 프롬프트 길이 확인
            print(f"[SRT 분석] 📏 최종 프롬프트 길이: {len(prompt)}자 (씬 데이터 포함)")

            return prompt
    except Exception as e:
        print(f"[SRT 분석] 템플릿 로드 실패, 기본 프롬프트 사용: {e}")
        import traceback
        print(f"[SRT 분석] 상세 오류: {traceback.format_exc()}")

    # 폴백: 기본 하드코딩된 프롬프트
    prompt = """다음 씬들을 분석하고 JSON 배열로 응답해주세요.

각 씬에 대해 다음 필드를 포함해주세요:
- scene_id: 씬 번호
- image_prompt: 한국어 이미지 생성 프롬프트
- image_prompt_en: 영문 이미지 프롬프트 (FLUX용, 상세하게, 텍스트 없이)
- image_prompt_korean_text: 영문 이미지 프롬프트 + 한글 텍스트 (나레이션 핵심 메시지를 한글로 포함)
- character_prompt: 한국어 캐릭터 프롬프트
- character_prompt_en: 영문 캐릭터 프롬프트
- visual_elements: 시각 요소 리스트
- direction_guide: 연출 가이드
- video_prompt_character: Character animation description (ENGLISH)
- video_prompt_full: Full scene video description (ENGLISH)
- characters: 등장 캐릭터 리스트 (각 캐릭터에 name, visual_prompt 포함!)
- location: 배경 장소
- mood: 분위기

⚠️ 중요: characters 배열의 각 캐릭터에는 반드시 visual_prompt를 영문으로 포함해주세요!
예: {"name": "자말 카슈크지", "visual_prompt": "Middle-aged Middle Eastern man, journalist, salt-and-pepper beard, wearing glasses, serious expression..."}

⚠️ video_prompt_character와 video_prompt_full은 반드시 영어로 작성하세요!

⚠️ image_prompt_korean_text 작성법:
- image_prompt_en의 시각적 묘사를 사용
- 나레이션에서 핵심 메시지를 추출하여 한글 텍스트로 포함
- 형식: [시각적 묘사], headline text in Korean reading "[핵심 메시지 5-10자]" at the top in handwritten pen script style, subtitle text in Korean reading "[부가 설명 10-20자]" at the bottom in informal handwritten font style, all Korean text in natural hand-drawn pen calligraphy style

=== 분석할 씬들 ===
"""

    prompt += scenes_content

    prompt += """
=== 응답 형식 ===
JSON 배열만 반환하세요. 다른 텍스트 없이 순수 JSON만 출력하세요.
```json
[
  {
    "scene_id": 1,
    "image_prompt": "...",
    "image_prompt_en": "...",
    "image_prompt_korean_text": "... headline text in Korean reading \"한글 제목\" at the top in handwritten pen script style...",
    "characters": [
      {"name": "캐릭터명", "visual_prompt": "영문 외모 설명..."}
    ],
    "video_prompt_character": "English character animation...",
    "video_prompt_full": "English full scene description...",
    ...
  },
  ...
]
```
"""

    return prompt


def _parse_batch_response(response_text: str, expected_count: int) -> List[Dict]:
    """배치 응답 파싱 (v2.2: 필드 정규화 및 background_prompt_en 보장)"""

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
            raw_results = results
        elif isinstance(results, dict) and 'scenes' in results:
            raw_results = results['scenes']
        else:
            raw_results = [results]

        # v2.2: 필드 정규화 - 다양한 필드명을 표준 이름으로 변환
        normalized_results = []
        for item in raw_results:
            normalized = _normalize_scene_fields(item)
            normalized_results.append(normalized)

        # 필드 통계 로깅
        bg_count = sum(1 for s in normalized_results if s.get('background_prompt_en'))
        char_count = sum(1 for s in normalized_results if s.get('character_prompt_en'))
        print(f"[배치 파싱] 파싱된 씬: {len(normalized_results)}개")
        print(f"[배치 파싱] background_prompt_en 있는 씬: {bg_count}개")
        print(f"[배치 파싱] character_prompt_en 있는 씬: {char_count}개")

        return normalized_results

    except json.JSONDecodeError as e:
        print(f"[배치 분석] JSON 파싱 오류: {e}")
        return [{} for _ in range(expected_count)]


def _normalize_scene_fields(scene_data: Dict) -> Dict:
    """
    씬 필드 정규화 - AI 응답의 다양한 필드명을 표준 이름으로 통일

    다음과 같은 변환을 수행:
    - bg_prompt, background_prompt → background_prompt_en
    - char_prompt, character_prompt → character_prompt_en
    - korean_text, text_overlay, kr_text → korean_text
    """
    if not scene_data:
        return {}

    normalized = {}

    # 기본 필드 복사
    for key, value in scene_data.items():
        normalized[key] = value

    # === background_prompt_en 정규화 ===
    # 가능한 키 이름들 (우선순위순)
    bg_keys = [
        'background_prompt_en',
        'background_prompt',
        'bg_prompt_en',
        'bg_prompt',
        'background_en',
        'scene_background',
        'environment_prompt'
    ]
    for key in bg_keys:
        if scene_data.get(key):
            normalized['background_prompt_en'] = scene_data[key]
            break
    else:
        # 어떤 키도 없으면 빈 문자열 설정
        if 'background_prompt_en' not in normalized:
            normalized['background_prompt_en'] = ''
            scene_id = scene_data.get('scene_id', '?')
            print(f"[필드 정규화] ⚠️ 씬 {scene_id}: background_prompt_en 필드 없음 (빈 문자열 설정)")

    # === character_prompt_en 정규화 ===
    char_keys = [
        'character_prompt_en',
        'character_prompt',
        'char_prompt_en',
        'char_prompt',
        'character_en',
        'person_prompt',
        'figure_prompt'
    ]
    for key in char_keys:
        if scene_data.get(key):
            normalized['character_prompt_en'] = scene_data[key]
            break
    else:
        if 'character_prompt_en' not in normalized:
            normalized['character_prompt_en'] = ''

    # === korean_text 정규화 ===
    kr_keys = [
        'korean_text',
        'image_prompt_korean_text',
        'text_overlay',
        'kr_text',
        'korean_overlay',
        'hangul_text'
    ]
    for key in kr_keys:
        if scene_data.get(key):
            normalized['korean_text'] = scene_data[key]
            # image_prompt_korean_text도 함께 설정
            normalized['image_prompt_korean_text'] = scene_data[key]
            break

    # === image_prompt_en 정규화 ===
    img_keys = [
        'image_prompt_en',
        'full_prompt',
        'image_prompt',
        'prompt_en',
        'visual_prompt'
    ]
    for key in img_keys:
        if scene_data.get(key):
            normalized['image_prompt_en'] = scene_data[key]
            break

    return normalized


def _parse_json_response(text: str) -> Dict:
    """JSON 응답 파싱 (v2.3: 필드 정규화 적용)"""

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
        raw_result = json.loads(text.strip())
        # v2.3: 필드 정규화 적용 (단일 씬 분석에도 동일하게 적용)
        normalized = _normalize_scene_fields(raw_result)
        return normalized
    except json.JSONDecodeError as e:
        print(f"[분석] JSON 파싱 오류: {e}")
        return {}


def analyze_scenes_with_mode(
    scenes: List[Dict],
    mode: str = "batch",
    model: str = "claude-sonnet-4-20250514",
    progress_callback: Optional[Callable] = None,
    status_callback: Optional[Callable] = None,
    prompt_id: str = None,  # ⭐ v3.27: UI에서 선택한 프롬프트 ID 직접 전달
    **kwargs  # v3.60: Claude Code 추가 파라미터 지원
) -> List[Dict]:
    """
    지정된 모드로 씬 분석

    Args:
        scenes: 분석할 씬 리스트
        mode: 처리 모드 ("sequential", "batch", "parallel")
        model: 사용할 AI 모델
        progress_callback: 진행률 콜백
        status_callback: 상태 메시지 콜백
        prompt_id: UI에서 선택한 프롬프트 ID (직접 전달!)
        **kwargs: 추가 파라미터 (Claude Code용: project_path, scenes_json_path, timeout 등)

    Returns:
        분석된 씬 리스트
    """
    global _analysis_metadata

    # ⭐ 메타데이터 초기화 (새 분석 시작)
    clear_analysis_metadata()
    _analysis_metadata['timestamp'] = datetime.now().isoformat()
    _analysis_metadata['processing_mode'] = mode
    _analysis_metadata['total_scenes'] = len(scenes)

    start_time = time.time()

    model_info = get_model(model)
    model_name = model_info.name if model_info else model
    provider = model_info.provider.value if model_info else "unknown"

    # ⭐ 모델 정보 메타데이터에 저장
    _analysis_metadata['model_id'] = model
    _analysis_metadata['model_name'] = model_name
    _analysis_metadata['provider'] = provider
    _analysis_metadata['ui_selected_prompt_id'] = prompt_id  # ⭐ v3.27: UI 선택 프롬프트 추적

    print(f"[분석 시작] 모델: {model_name} ({provider}), 모드: {mode}, prompt_id: {prompt_id}")

    if mode == "parallel":
        result = analyze_scenes_parallel(
            scenes, model,
            progress_callback=progress_callback,
            status_callback=status_callback,
            **kwargs  # v3.60: Claude Code 파라미터 전달
        )
    elif mode == "batch":
        # ⭐ v3.27: prompt_id 직접 전달!
        result = analyze_scenes_batch(
            scenes, model,
            progress_callback=progress_callback,
            status_callback=status_callback,
            prompt_id=prompt_id,
            **kwargs  # v3.60: Claude Code 파라미터 전달
        )
    else:  # sequential
        result = analyze_scenes_sequential(
            scenes, model,
            progress_callback=progress_callback,
            status_callback=status_callback,
            **kwargs  # v3.60: Claude Code 파라미터 전달
        )

    elapsed = time.time() - start_time

    # ⭐ 처리 시간 메타데이터에 저장
    _analysis_metadata['processing_time_seconds'] = round(elapsed, 2)

    print(f"[분석 완료] {len(scenes)}개 씬, {elapsed:.1f}초 소요 (모드: {mode}, 모델: {model_name})")

    return result
