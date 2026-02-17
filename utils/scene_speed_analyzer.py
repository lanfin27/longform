# -*- coding: utf-8 -*-
"""
씬 분석 속도 개선 모듈 v2.2

멀티 프로바이더 지원 (Anthropic, Google, OpenAI)

기능:
- 배치 처리: 여러 씬을 한 번의 API 호출로 분석
- 병렬 처리: concurrent.futures를 사용한 동시 처리
- 순차 처리: 안정적인 하나씩 처리
- 통합 AI 클라이언트 사용
- 분석 메타데이터 추적

v2.2 변경사항:
- ⭐ 묶음 분석 방식 수정: 묶음 내 모든 씬 포함 및 스크립트 합치기
  - 기존: 대표 씬만 저장하고 분석 (나머지 씬 누락)
  - 수정: 묶음 내 모든 씬 저장, 분석 후 묶음 병합 적용
- ⭐ 분석 완료 후 apply_bundle_analysis_result() 호출로 묶음 병합

v2.1 변경사항:
- ⭐ 긴급 수정: Claude Code 분석 전 scenes.json 항상 업데이트
  - 기존: scenes.json이 존재하면 업데이트 안 함 (이전 데이터 사용)
  - 수정: 항상 선택된 씬으로 scenes.json 업데이트 후 분석
- ⭐ 저장 후 검증 추가 (scene ID 일치 확인)
"""

import json
import time
import concurrent.futures
from datetime import datetime
from typing import List, Dict, Callable, Optional, Any, Tuple

from .ai_client import UnifiedAIClient
from .ai_providers import get_model, AIProvider
from .ai_providers import get_model_rate_info, get_gemini_fallback_models

# ============================================================
# Rate Limit 관리 (v2.3)
# ============================================================

import threading

_rate_limit_lock = threading.Lock()
_last_api_call_time: float = 0.0


def _acquire_rate_limit_slot(model_id: str, verbose: bool = True) -> float:
    """
    RPM 기반 Rate Limit 슬롯 예약 (v2.5)

    Lock 안에서 다음 호출 가능 시각만 계산/예약하고,
    실제 대기(sleep)는 lock 밖에서 수행하도록 대기 시간을 반환합니다.

    이를 통해 여러 스레드가 동시에 슬롯을 예약할 수 있어
    병렬 배치 처리 시 API I/O가 오버랩됩니다.

    Returns:
        대기해야 할 시간(초). 0이면 즉시 호출 가능.
    """
    global _last_api_call_time
    info = get_model_rate_info(model_id)
    delay = info.get("delay_seconds", 0)
    if delay <= 0:
        return 0.0

    with _rate_limit_lock:
        now = time.time()
        earliest_allowed = _last_api_call_time + delay
        if earliest_allowed <= now:
            # 즉시 호출 가능
            _last_api_call_time = now
            return 0.0
        else:
            # 미래 슬롯 예약 (다른 스레드는 이 이후 슬롯 받음)
            _last_api_call_time = earliest_allowed
            wait = earliest_allowed - now
            if verbose:
                print(f"  [Rate limit] {wait:.1f}초 후 슬롯 (RPM={info['rpm']}, 간격={delay}s)")
            return wait


def _wait_for_rate_limit(model_id: str, verbose: bool = True):
    """하위 호환 래퍼: 슬롯 예약 + sleep (순차 처리용)"""
    wait = _acquire_rate_limit_slot(model_id, verbose=verbose)
    if wait > 0:
        time.sleep(wait)


def _call_with_retry(
    client: 'UnifiedAIClient',
    prompt: str,
    model: str,
    max_tokens: int = 8000,
    max_retries: int = 2,
    status_callback=None
) -> str:
    """
    API 호출 + Rate Limit 재시도 + Gemini 모델 폴백

    1. 현재 모델로 호출 (RPM 간격 대기)
    2. 429/ResourceExhausted → 대기 후 재시도
    3. 재시도 실패 → 다음 폴백 모델로 전환
    """
    model_info = get_model(model)
    is_gemini = model_info and model_info.provider == AIProvider.GOOGLE

    fallback_models = get_gemini_fallback_models(exclude=model) if is_gemini else []
    models_to_try = [model] + fallback_models

    last_error = None
    current_client = client

    for model_id in models_to_try:
        # 폴백 모델인 경우 새 클라이언트 생성
        if model_id != model:
            try:
                current_client = UnifiedAIClient(model_id=model_id)
                msg = f"[폴백] {model} → {model_id} 모델 전환"
                print(msg)
                if status_callback:
                    status_callback(msg)
            except Exception as e:
                print(f"[폴백] {model_id} 초기화 실패: {e}")
                continue

        for attempt in range(max_retries + 1):
            try:
                wait = _acquire_rate_limit_slot(model_id)
                if wait > 0:
                    time.sleep(wait)
                response = current_client.generate(prompt=prompt, max_tokens=max_tokens)
                return response
            except Exception as e:
                last_error = e
                error_str = str(e).lower()
                is_rate_limit = any(k in error_str for k in [
                    '429', 'rate_limit', 'rate limit', 'resource exhausted',
                    'quota', 'too many requests'
                ])

                if is_rate_limit and attempt < max_retries:
                    wait = 30 * (attempt + 1)
                    msg = f"[재시도] Rate limit ({model_id}), {wait}초 대기 ({attempt+1}/{max_retries+1})..."
                    print(msg)
                    if status_callback:
                        status_callback(msg)
                    time.sleep(wait)
                    continue

                # 재시도 실패 → 다음 폴백 모델로
                print(f"[실패] {model_id}: {str(e)[:200]}")
                break

    raise Exception(f"모든 모델 호출 실패: {last_error}")


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


def _expand_scenes_with_bundle_members(
    scenes: List[Dict],
    all_scenes_path: str = None
) -> Tuple[List[Dict], Dict[int, Dict]]:
    """
    v2.2: 선택된 씬들을 묶음 내 모든 씬으로 확장

    Args:
        scenes: 선택된 씬 리스트 (대표 씬만 포함될 수 있음)
        all_scenes_path: 전체 scenes.json 경로 (None이면 scenes만 사용)

    Returns:
        (확장된 씬 리스트, 묶음 정보 딕셔너리)
        묶음 정보: {bundle_id: {scene_ids: [], combined_script: str, primary_scene_id: int}}
    """
    from collections import defaultdict

    # 묶음별 씬 그룹핑
    bundle_scenes = defaultdict(list)
    for scene in scenes:
        bundle_id = scene.get('bundle_id')
        if bundle_id is not None:
            bundle_scenes[bundle_id].append(scene)
        else:
            # bundle_id가 없으면 단독 씬
            bundle_scenes[scene.get('scene_id', 0)] = [scene]

    # 묶음 정보 구성
    bundle_info = {}
    for bundle_id, scenes_in_bundle in bundle_scenes.items():
        # 씬 ID 순으로 정렬
        scenes_in_bundle.sort(key=lambda s: s.get('scene_id', 0))

        scene_ids = [s.get('scene_id') for s in scenes_in_bundle]

        # 스크립트 합치기
        combined_script = " ".join([
            s.get('script_ko', s.get('script_text', s.get('text', '')))
            for s in scenes_in_bundle
        ]).strip()

        # 대표 씬 (첫 번째 씬)
        primary_scene_id = scene_ids[0] if scene_ids else None

        bundle_info[bundle_id] = {
            'scene_ids': scene_ids,
            'combined_script': combined_script,
            'primary_scene_id': primary_scene_id,
            'bundle_size': len(scenes_in_bundle)
        }

        print(f"[Bundle 준비] 묶음 {bundle_id}: 씬 {scene_ids}")
        print(f"[Bundle 준비]   스크립트: {combined_script[:60]}...")

    print(f"[Bundle 준비] 📦 {len(bundle_info)}개 묶음 준비 완료")

    return scenes, bundle_info


def _apply_bundle_merge_to_scenes(
    scenes: List[Dict]
) -> List[Dict]:
    """
    v2.2: 분석 완료 후 묶음 병합 적용 (Gemini와 동일한 로직)

    대표 씬의 분석 결과를 묶음 내 모든 씬에 복사
    """
    from collections import defaultdict

    # 묶음별 그룹핑
    bundle_map = defaultdict(list)
    for scene in scenes:
        bundle_id = scene.get('bundle_id')
        if bundle_id is not None:
            bundle_map[bundle_id].append(scene)

    if not bundle_map:
        print(f"[Bundle 병합] 묶음 정보 없음 - 스킵")
        return scenes

    merged_count = 0

    for bundle_id, bundle_scenes in bundle_map.items():
        # 씬 정렬
        bundle_scenes.sort(key=lambda s: s.get('scene_id', 0))

        # 대표 씬 찾기 (분석 결과가 있는 첫 번째 씬)
        primary_scene = None
        for scene in bundle_scenes:
            if scene.get('background_prompt_en'):
                primary_scene = scene
                break

        if not primary_scene:
            # 분석 결과가 없으면 첫 번째 씬을 대표로
            primary_scene = bundle_scenes[0] if bundle_scenes else None

        if not primary_scene:
            continue

        primary_id = primary_scene.get('scene_id', '?')

        print(f"[Bundle 적용] 대표 씬 {primary_id}, bundle_id={bundle_id}")
        print(f"[Bundle 적용] bundle_id={bundle_id}인 씬들: {[s.get('scene_id') for s in bundle_scenes]}")

        # 복사할 필드들
        fields_to_copy = [
            'script_en',
            'background_prompt_en',
            'character_prompt_en',
            'image_prompt_en',
            'image_prompt_korean_text',
            'characters',
            'visual_elements',
            'scene_mood',
            'direction_guide',
            'video_prompt_character',
            'video_prompt_full',
            'location',
            'mood'
        ]

        # 묶음 내 모든 씬에 결과 적용
        for scene in bundle_scenes:
            scene_id = scene.get('scene_id', '?')

            for field in fields_to_copy:
                if primary_scene.get(field):
                    scene[field] = primary_scene[field]

            if scene.get('background_prompt_en'):
                print(f"[Bundle 병합] ✅ 씬 {scene_id}: background_prompt_en 적용됨 (묶음 {bundle_id})")
                merged_count += 1

        print(f"[Bundle 병합] 📦 묶음 {bundle_id} (대표: 씬 {primary_id}) → {len(bundle_scenes)}개 씬에 결과 적용")

    print(f"\n[묶음 병합 완료] {merged_count}개 씬에 분석 결과 적용됨")

    return scenes


def _run_claude_code_batch_analysis(
    scenes: List[Dict],
    progress_callback: Optional[Callable] = None,
    status_callback: Optional[Callable] = None,
    prompt_id: str = None,  # v3.95: 프롬프트 템플릿 ID 추가
    **kwargs
) -> List[Dict]:
    """
    Claude Code를 사용한 배치 분석 (subprocess 실행)

    Args:
        scenes: 분석할 씬 리스트
        progress_callback: 진행률 콜백
        status_callback: 상태 메시지 콜백
        prompt_id: UI에서 선택한 프롬프트 템플릿 ID (v3.95 추가)
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

    # ═══════════════════════════════════════════════════════════════════
    # v2.1 긴급 수정: scenes.json을 항상 선택된 씬으로 업데이트
    # 기존 문제: 파일이 존재하면 업데이트 안 함 → 이전 분석의 씬 데이터 사용
    # 수정: 항상 선택된 씬을 scenes.json에 저장 후 분석
    # ═══════════════════════════════════════════════════════════════════
    if not scenes or len(scenes) == 0:
        print(f"[Claude Code 배치 분석] ❌ 분석할 씬 데이터가 없습니다")
        if status_callback:
            status_callback("❌ 분석할 씬 데이터가 없습니다")
        return scenes

    if not project_path:
        print(f"[Claude Code 배치 분석] ❌ 프로젝트 경로가 없습니다")
        if status_callback:
            status_callback("❌ 프로젝트 경로가 없습니다")
        return scenes

    # analysis 디렉토리 생성
    analysis_dir = os.path.join(project_path, 'analysis')
    os.makedirs(analysis_dir, exist_ok=True)
    scenes_json_path = os.path.join(analysis_dir, 'scenes.json')

    # ⭐ v2.1 핵심 수정: 항상 선택된 씬을 scenes.json에 저장
    print(f"[Claude Code 배치 분석] 🔄 선택된 씬을 scenes.json에 저장 중...")
    if status_callback:
        status_callback("선택된 씬을 scenes.json에 저장 중...")

    # 선택된 씬의 ID 목록 추출
    selected_ids_for_save = []
    scenes_to_save = []

    for i, scene in enumerate(scenes):
        scene_id = scene.get('scene_id', scene.get('id', i + 1))
        selected_ids_for_save.append(scene_id)

        scene_data = {
            'scene_id': scene_id,
            'start_time': scene.get('start_time', ''),
            'end_time': scene.get('end_time', ''),
            'duration': scene.get('duration', scene.get('duration_estimate', 0)),
            'script_ko': scene.get('script_ko', scene.get('script_text', scene.get('text', ''))),
            'script_en': scene.get('script_en', ''),
            'bundle_id': scene.get('bundle_id'),
            'bundle_size': scene.get('bundle_size', 1),
            'is_primary': scene.get('is_primary', False),
            # 분석 결과 필드 (기존 값 유지 또는 빈 문자열)
            'background_prompt_en': scene.get('background_prompt_en', ''),
            'character_prompt_en': scene.get('character_prompt_en', ''),
            'characters': scene.get('characters', []),
            'visual_elements': scene.get('visual_elements', []),
            'scene_mood': scene.get('scene_mood', ''),
        }
        scenes_to_save.append(scene_data)

    # ⭐ v2.1: 저장 전 정보 출력 (디버깅용)
    print(f"[Claude Code 배치 분석] 📋 저장할 씬 ID: {sorted(selected_ids_for_save)}")
    print(f"[Claude Code 배치 분석] 📋 저장할 씬 수: {len(scenes_to_save)}개")

    # 저장
    with open(scenes_json_path, 'w', encoding='utf-8') as f:
        json.dump(scenes_to_save, f, ensure_ascii=False, indent=2)

    print(f"[Claude Code 배치 분석] ✅ scenes.json 저장 완료")
    print(f"[Claude Code 배치 분석] 📁 경로: {scenes_json_path}")

    # ⭐ v2.1: 저장 후 검증
    try:
        with open(scenes_json_path, 'r', encoding='utf-8') as f:
            verified_scenes = json.load(f)

        verified_ids = [s.get('scene_id') for s in verified_scenes]

        # 저장된 씬 ID가 원본과 일치하는지 확인
        missing_ids = set(selected_ids_for_save) - set(verified_ids)
        extra_ids = set(verified_ids) - set(selected_ids_for_save)

        if missing_ids:
            print(f"[Claude Code 배치 분석] ❌ 검증 실패: 누락된 씬 ID: {missing_ids}")
            if status_callback:
                status_callback(f"❌ scenes.json 검증 실패: 누락된 씬 ID: {missing_ids}")
            return scenes

        if extra_ids:
            print(f"[Claude Code 배치 분석] ⚠️ 경고: 예상 외 씬 ID: {extra_ids}")

        print(f"[Claude Code 배치 분석] ✅ 검증 통과: {len(verified_ids)}개 씬 정상 저장됨")
        print(f"[Claude Code 배치 분석] 🎯 저장된 씬 ID: {min(verified_ids)} ~ {max(verified_ids)}")

        if status_callback:
            status_callback(f"scenes.json 저장 완료 ({len(verified_ids)}개 씬)")

    except Exception as e:
        print(f"[Claude Code 배치 분석] ❌ 검증 오류: {e}")
        if status_callback:
            status_callback(f"⚠️ scenes.json 검증 중 오류: {e}")

    print(f"[Claude Code 배치 분석] 📁 scenes.json: {scenes_json_path}")

    if status_callback:
        status_callback("Claude Code로 분석 중...")

    # ═══════════════════════════════════════════════════════════════════
    # v13.7: 선택된 씬 ID 추출 (프롬프트에 정확한 범위 전달)
    # ═══════════════════════════════════════════════════════════════════
    selected_scene_ids = []
    for scene in scenes:
        sid = scene.get('scene_id', scene.get('id'))
        if sid:
            selected_scene_ids.append(sid)

    if selected_scene_ids:
        print(f"[Claude Code 배치 분석] 🎯 선택된 씬 ID: {min(selected_scene_ids)} ~ {max(selected_scene_ids)} ({len(selected_scene_ids)}개)")
    else:
        print(f"[Claude Code 배치 분석] ⚠️ 선택된 씬 ID를 추출할 수 없음")

    # claude_code_runner 사용 시도
    try:
        from .claude_code_runner import run_scene_analysis_agent, SceneAnalysisResult

        def progress_cb(msg):
            if status_callback:
                status_callback(msg)
            print(f"[Claude Code] {msg}")

        # v3.95: prompt_id를 run_scene_analysis_agent에 전달
        print(f"[Claude Code 배치 분석] 📋 프롬프트 템플릿 ID: {prompt_id}")

        result = run_scene_analysis_agent(
            scenes_json_path=scenes_json_path,
            project_path=project_path,
            scene_range=None,  # scene_range 대신 selected_scene_ids 사용
            bundle_mode=bundle_mode,
            custom_instructions=custom_instructions,
            timeout=timeout,
            progress_callback=progress_cb,
            selected_scene_ids=selected_scene_ids if selected_scene_ids else None,  # v13.7: 선택된 씬 ID 전달!
            prompt_id=prompt_id  # v3.95: 프롬프트 템플릿 ID 전달!
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
            # ═══════════════════════════════════════════════════════════════════
            # v3.72: 자동 실행 모드 감지 (새 CMD 창에서 실행 중)
            # ═══════════════════════════════════════════════════════════════════
            fields_info = result.fields_generated or {}

            if fields_info.get('auto_execution') and fields_info.get('status') == 'running':
                print(f"[Claude Code 배치 분석] 🚀 새 CMD 창에서 실행 중...")
                print(f"[Claude Code 배치 분석] 📝 프롬프트 파일: {fields_info.get('prompt_file')}")
                print(f"[Claude Code 배치 분석] 📄 배치 파일: {fields_info.get('batch_file')}")
                print(f"[Claude Code 배치 분석] 💡 완료 후 '결과 확인' 버튼을 클릭하세요")

                # 자동 실행 정보를 session_state에 저장
                st.session_state['claude_code_auto_execution'] = True
                st.session_state['claude_code_prompt_file'] = fields_info.get('prompt_file', '')
                st.session_state['claude_code_batch_file'] = fields_info.get('batch_file', '')
                st.session_state['claude_code_scenes_path'] = scenes_json_path
                st.session_state['claude_code_agent_mode'] = False  # 에이전트 모드가 아님 (자동 실행)

                if status_callback:
                    status_callback("🚀 새 CMD 창에서 실행 중... 완료 후 '결과 확인' 클릭")

                # 현재 씬 반환 (아직 분석 완료 안됨)
                return scenes

            # scenes.json 다시 로드
            with open(scenes_json_path, 'r', encoding='utf-8') as f:
                updated_data = json.load(f)

            updated_scenes = updated_data.get('scenes', updated_data) if isinstance(updated_data, dict) else updated_data

            # ═══════════════════════════════════════════════════════════════════
            # v2.2: 묶음 병합 적용 (Gemini와 동일한 로직)
            # 대표 씬의 분석 결과를 묶음 내 모든 씬에 복사
            # ═══════════════════════════════════════════════════════════════════
            print(f"\n[Claude Code 배치 분석] 📦 묶음 병합 적용 중...")
            updated_scenes = _apply_bundle_merge_to_scenes(updated_scenes)

            # 묶음 병합된 결과를 scenes.json에 저장
            with open(scenes_json_path, 'w', encoding='utf-8') as f:
                json.dump(updated_scenes, f, ensure_ascii=False, indent=2)
            print(f"[Claude Code 배치 분석] ✅ 묶음 병합 결과 scenes.json 저장 완료")

            # ═══════════════════════════════════════════════════════════════════
            # v3.72: 분석 결과 검증 (background_prompt_en 생성 여부)
            # ═══════════════════════════════════════════════════════════════════
            total_scenes = len(updated_scenes)
            scenes_with_bg_prompt = sum(1 for s in updated_scenes if s.get('background_prompt_en'))
            scenes_with_char_prompt = sum(1 for s in updated_scenes if s.get('character_prompt_en'))

            print(f"[Claude Code 배치 분석] ✅ 완료! ({elapsed:.1f}초)")
            print(f"[Claude Code 배치 분석] 📊 분석된 씬: {result.scenes_analyzed}개")
            print(f"[Claude Code 배치 분석] 📊 결과 검증:")
            print(f"    - 배경 프롬프트 생성: {scenes_with_bg_prompt}/{total_scenes}")
            print(f"    - 캐릭터 프롬프트 생성: {scenes_with_char_prompt}/{total_scenes}")

            # 분석 결과 메타데이터 저장
            _update_analysis_metadata('scenes_with_bg_prompt', scenes_with_bg_prompt)
            _update_analysis_metadata('scenes_with_char_prompt', scenes_with_char_prompt)
            _update_analysis_metadata('total_scenes', total_scenes)

            if scenes_with_bg_prompt == 0:
                print(f"[Claude Code 배치 분석] ⚠️ 경고: 배경 프롬프트가 하나도 생성되지 않았습니다!")
                if status_callback:
                    status_callback(f"⚠️ 완료되었으나 프롬프트 0개 생성됨 - 재시도 필요")
            else:
                if status_callback:
                    status_callback(f"✅ 완료! ({scenes_with_bg_prompt}/{total_scenes} 씬 분석)")

            # 에이전트 모드 플래그 해제
            st.session_state['claude_code_agent_mode'] = False
            st.session_state['claude_code_auto_execution'] = False

            if progress_callback:
                progress_callback(1.0)

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

        # Rate limit 스로틀링
        if i > 0:
            _wait_for_rate_limit(model)

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


def _process_single_batch(
    batch: List[Dict],
    batch_index: int,
    total_scenes: int,
    batch_size: int,
    client: 'UnifiedAIClient',
    model: str,
    prompt_id: str,
    verbose: bool = True,
) -> Tuple[int, List[Dict]]:
    """
    단일 배치 처리 (ThreadPoolExecutor 호출용, v2.5)

    Rate limit 슬롯을 lock 밖에서 대기하므로
    여러 배치가 동시에 I/O를 수행할 수 있습니다.

    Returns:
        (batch_index, 처리된 씬 리스트)
    """
    batch_start = batch_index + 1
    batch_end = min(batch_index + batch_size, total_scenes)

    if verbose:
        print(f"[배치 분석] 씬 {batch_start}-{batch_end}/{total_scenes} 처리 중...")

    # Rate limit: 슬롯 예약 (lock) → 대기 (lock 밖)
    wait = _acquire_rate_limit_slot(model, verbose=verbose)
    if wait > 0:
        time.sleep(wait)

    # 프롬프트 생성
    batch_prompt = _create_batch_analysis_prompt(batch, prompt_id=prompt_id)

    try:
        # API 호출
        batch_max_tokens = max(8000, len(batch) * 3000)
        response = client.generate(prompt=batch_prompt, max_tokens=batch_max_tokens)

        # 응답 파싱
        batch_results = _parse_batch_response(response, len(batch))

        # 결과 병합
        for j, scene in enumerate(batch):
            if j < len(batch_results):
                result = batch_results[j]
                scene.update(result)

        bg_count = sum(1 for s in batch_results if s.get('background_prompt_en'))
        if verbose:
            print(f"[배치 분석] ✅ 씬 {batch_start}-{batch_end} 완료 (bg: {bg_count}/{len(batch_results)})")

        return (batch_index, list(batch))

    except Exception as e:
        print(f"[배치 분석] ❌ 배치 {batch_start}-{batch_end} 실패: {e}")
        return (batch_index, list(batch))


def analyze_scenes_batch(
    scenes: List[Dict],
    model: str = "claude-sonnet-4-20250514",
    batch_size: int = 3,
    progress_callback: Optional[Callable] = None,
    status_callback: Optional[Callable] = None,
    prompt_id: str = None,
    verbose: bool = True,
    **kwargs
) -> List[Dict]:
    """
    씬들을 배치로 분석 (v2.5: 동시 배치 처리 지원)

    Args:
        scenes: 분석할 씬 리스트
        model: 사용할 AI 모델
        batch_size: 한 번에 처리할 씬 수
        progress_callback: 진행률 콜백
        status_callback: 상태 메시지 콜백
        prompt_id: UI에서 선택한 프롬프트 ID
        verbose: 상세 로깅 여부
        **kwargs: 추가 파라미터 (Claude Code용)

    Returns:
        분석된 씬 리스트
    """

    # Claude Code 모델 분기 처리
    if _is_claude_code_model(model):
        print(f"[배치 분석] 🤖 Claude Code 감지 - subprocess 실행으로 전환")
        return _run_claude_code_batch_analysis(
            scenes=scenes,
            progress_callback=progress_callback,
            status_callback=status_callback,
            prompt_id=prompt_id,
            **kwargs
        )

    try:
        client = UnifiedAIClient(model_id=model)
    except Exception as e:
        print(f"[배치 분석] ❌ AI 클라이언트 초기화 실패: {e}")
        return scenes

    model_info = get_model(model)
    model_name = model_info.name if model_info else model
    rate_info = get_model_rate_info(model)

    total_scenes = len(scenes)

    # 배치 분할
    batches = []
    for i in range(0, total_scenes, batch_size):
        batches.append((i, scenes[i:i + batch_size]))

    total_batches = len(batches)

    # 동시 워커 수 자동 계산 (RPM 기반)
    import math
    delay = rate_info.get("delay_seconds", 0)
    if delay > 0:
        avg_call_time = 8.0  # 경험적 평균 API 응답 시간
        max_concurrent = max(1, min(3, math.ceil(avg_call_time / delay)))
    else:
        max_concurrent = 3  # rate limit 없으면 3개 동시

    print(f"[배치 분석] 모델: {model_name}, RPM: {rate_info.get('rpm', 'N/A')}")
    print(f"[배치 분석] 배치 수: {total_batches}, 동시 실행: {max_concurrent}, 배치 크기: {batch_size}")

    start_time = time.time()
    completed_count = 0

    # ═══════════════════════════════════════════════════════════
    # 동시 배치 처리 (v2.5: ThreadPoolExecutor)
    # ═══════════════════════════════════════════════════════════
    results_map = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_concurrent) as executor:
        future_to_batch = {}
        for batch_idx, batch in batches:
            future = executor.submit(
                _process_single_batch,
                batch=batch,
                batch_index=batch_idx,
                total_scenes=total_scenes,
                batch_size=batch_size,
                client=client,
                model=model,
                prompt_id=prompt_id,
                verbose=verbose,
            )
            future_to_batch[future] = batch_idx

        for future in concurrent.futures.as_completed(future_to_batch):
            batch_idx = future_to_batch[future]
            completed_count += 1

            try:
                idx, processed = future.result()
                results_map[idx] = processed
            except Exception as e:
                print(f"[배치 분석] ❌ 배치 실패 (idx={batch_idx}): {e}")
                results_map[batch_idx] = list(scenes[batch_idx:batch_idx + batch_size])

            # 진행률 + ETA 계산
            if progress_callback:
                progress_callback(completed_count / total_batches)

            elapsed = time.time() - start_time
            avg_per_batch = elapsed / completed_count
            remaining = (total_batches - completed_count) * avg_per_batch

            if status_callback:
                mins, secs = divmod(int(remaining), 60)
                eta_str = f"{mins}분 {secs}초" if mins > 0 else f"{secs}초"
                status_callback(
                    f"배치 {completed_count}/{total_batches} 완료 "
                    f"(남은 시간: ~{eta_str})"
                )

    # 순서대로 재조립
    analyzed_scenes = []
    for batch_idx, _ in batches:
        analyzed_scenes.extend(results_map.get(batch_idx, []))

    elapsed = time.time() - start_time
    bg_total = sum(1 for s in analyzed_scenes if s.get('background_prompt_en'))
    print(f"[배치 분석] ✅ 전체 완료: {bg_total}/{total_scenes} 씬 분석됨 ({elapsed:.1f}초 소요)")

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

    # RPM 기반 워커 수 조정
    rate_info = get_model_rate_info(model)
    if rate_info["rpm"] > 0:
        safe_workers = max(1, rate_info["rpm"] // 3)
        if safe_workers < max_workers:
            print(f"[병렬 분석] RPM({rate_info['rpm']}) 제한으로 워커 수 조정: {max_workers} → {safe_workers}")
            max_workers = safe_workers

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
        max_tokens=4000
    )

    return _parse_json_response(response)


def _analyze_single_scene_standalone(scene: Dict, model: str) -> Dict:
    """단일 씬 분석 (병렬 처리용 - 독립 클라이언트)"""

    try:
        _wait_for_rate_limit(model)
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


def _recover_truncated_json(text: str) -> List[Dict]:
    """
    잘린 JSON 응답에서 완전한 객체들을 복구

    AI 응답이 max_output_tokens에 의해 잘린 경우,
    완전히 파싱 가능한 JSON 객체들만 추출하여 반환합니다.
    """
    import re

    recovered = []

    # 방법 1: 마지막 완전한 객체 위치까지 잘라서 파싱
    # JSON 배열에서 마지막 완전한 '}' 뒤의 ']'를 붙여 파싱 시도
    if text.startswith('['):
        # 마지막으로 완전한 '},' 또는 '}\n' 패턴 찾기
        last_complete = -1
        brace_depth = 0
        in_string = False
        escape_next = False

        for i, ch in enumerate(text):
            if escape_next:
                escape_next = False
                continue
            if ch == '\\' and in_string:
                escape_next = True
                continue
            if ch == '"' and not escape_next:
                in_string = not in_string
                continue
            if in_string:
                continue

            if ch == '{':
                brace_depth += 1
            elif ch == '}':
                brace_depth -= 1
                if brace_depth == 0:
                    last_complete = i

        if last_complete > 0:
            truncated = text[:last_complete + 1].rstrip().rstrip(',') + ']'
            try:
                results = json.loads(truncated)
                if isinstance(results, list):
                    print(f"[JSON 복구] ✅ 잘린 JSON에서 {len(results)}개 객체 복구 성공")
                    return results
            except json.JSONDecodeError:
                pass

    # 방법 2: 개별 JSON 객체 추출 (정규식 기반)
    # 최상위 {...} 블록을 하나씩 추출 시도
    brace_depth = 0
    obj_start = -1
    in_string = False
    escape_next = False

    for i, ch in enumerate(text):
        if escape_next:
            escape_next = False
            continue
        if ch == '\\' and in_string:
            escape_next = True
            continue
        if ch == '"' and not escape_next:
            in_string = not in_string
            continue
        if in_string:
            continue

        if ch == '{':
            if brace_depth == 0:
                obj_start = i
            brace_depth += 1
        elif ch == '}':
            brace_depth -= 1
            if brace_depth == 0 and obj_start >= 0:
                obj_text = text[obj_start:i + 1]
                try:
                    obj = json.loads(obj_text)
                    recovered.append(obj)
                except json.JSONDecodeError:
                    pass
                obj_start = -1

    if recovered:
        print(f"[JSON 복구] ✅ 개별 객체 추출로 {len(recovered)}개 복구 성공")

    return recovered


def _parse_batch_response(response_text: str, expected_count: int) -> List[Dict]:
    """배치 응답 파싱 (v2.4: 잘린 JSON 복구 + 필드 정규화)"""

    text = response_text.strip()

    # 응답 길이 로깅 (절단 감지용)
    print(f"[배치 파싱] 응답 길이: {len(text)}자 (예상 씬 수: {expected_count})")

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

    # 절단 감지: 괄호 불균형 체크
    open_braces = text.count('{') - text.count('}')
    open_brackets = text.count('[') - text.count(']')
    is_truncated = open_braces != 0 or open_brackets != 0
    if is_truncated:
        print(f"[배치 파싱] ⚠️ 응답 절단 감지! (미닫힌 중괄호: {open_braces}, 대괄호: {open_brackets})")

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
        print(f"[배치 파싱] JSON 파싱 오류: {e}")
        print(f"[배치 파싱] 응답 끝부분: ...{text[-200:]}")

        # v2.4: 잘린 JSON 복구 시도
        recovered = _recover_truncated_json(text)
        if recovered:
            normalized_results = []
            for item in recovered:
                normalized = _normalize_scene_fields(item)
                normalized_results.append(normalized)

            bg_count = sum(1 for s in normalized_results if s.get('background_prompt_en'))
            print(f"[배치 파싱] 🔧 복구된 씬: {len(normalized_results)}개 (background_prompt_en: {bg_count}개)")
            print(f"[배치 파싱] ⚠️ 예상 {expected_count}개 중 {len(normalized_results)}개만 복구됨")

            # 부족한 씬은 빈 딕셔너리로 채움
            while len(normalized_results) < expected_count:
                normalized_results.append({})

            return normalized_results

        print(f"[배치 파싱] ❌ JSON 복구 실패 - 빈 결과 반환")
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
    prompt_id: str = None,
    verbose: bool = True,
    **kwargs
) -> List[Dict]:
    """
    지정된 모드로 씬 분석 (v2.5: verbose 파라미터 추가)

    Args:
        scenes: 분석할 씬 리스트
        mode: 처리 모드 ("sequential", "batch", "parallel")
        model: 사용할 AI 모델
        progress_callback: 진행률 콜백
        status_callback: 상태 메시지 콜백
        prompt_id: UI에서 선택한 프롬프트 ID
        verbose: 상세 로깅 여부
        **kwargs: 추가 파라미터 (Claude Code용)

    Returns:
        분석된 씬 리스트
    """
    global _analysis_metadata

    clear_analysis_metadata()
    _analysis_metadata['timestamp'] = datetime.now().isoformat()
    _analysis_metadata['processing_mode'] = mode
    _analysis_metadata['total_scenes'] = len(scenes)

    start_time = time.time()

    model_info = get_model(model)
    model_name = model_info.name if model_info else model
    provider = model_info.provider.value if model_info else "unknown"

    _analysis_metadata['model_id'] = model
    _analysis_metadata['model_name'] = model_name
    _analysis_metadata['provider'] = provider
    _analysis_metadata['ui_selected_prompt_id'] = prompt_id

    print(f"[분석 시작] 모델: {model_name} ({provider}), 모드: {mode}, prompt_id: {prompt_id}")

    if mode == "parallel":
        result = analyze_scenes_parallel(
            scenes, model,
            progress_callback=progress_callback,
            status_callback=status_callback,
            **kwargs
        )
    elif mode == "batch":
        result = analyze_scenes_batch(
            scenes, model,
            progress_callback=progress_callback,
            status_callback=status_callback,
            prompt_id=prompt_id,
            verbose=verbose,
            **kwargs
        )
    else:  # sequential
        result = analyze_scenes_sequential(
            scenes, model,
            progress_callback=progress_callback,
            status_callback=status_callback,
            **kwargs
        )

    elapsed = time.time() - start_time
    _analysis_metadata['processing_time_seconds'] = round(elapsed, 2)

    print(f"[분석 완료] {len(scenes)}개 씬, {elapsed:.1f}초 소요 (모드: {mode}, 모델: {model_name})")

    return result
