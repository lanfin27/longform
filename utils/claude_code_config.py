# -*- coding: utf-8 -*-
"""
Claude Code 실행 설정 관리 v1.0

사용자가 UI에서 선택한 값을 동적으로 읽기
- 하드코딩 금지!
- 모든 설정값은 session_state 또는 settings에서 읽음

동적으로 읽는 설정:
1. 묶음 크기 (bundle_size)
2. 프롬프트 템플릿 (prompt_template_id)
3. 묶음 모드 사용 (use_bundle_mode)
4. 타임아웃 (timeout)
5. 추가 지시사항 (additional_instructions)
"""

import json
from pathlib import Path
from typing import Optional, Dict, Any, List

# Streamlit import (optional - for non-Streamlit contexts)
try:
    import streamlit as st
    HAS_STREAMLIT = True
except ImportError:
    HAS_STREAMLIT = False
    st = None


# ═══════════════════════════════════════════════════════════════════
# 설정 파일 경로
# ═══════════════════════════════════════════════════════════════════

ROOT_DIR = Path(__file__).parent.parent
SETTINGS_FILE = ROOT_DIR / "data" / "claude_code_settings.json"


def _load_settings_file() -> Dict[str, Any]:
    """설정 파일 로드"""
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[Config] 설정 파일 로드 실패: {e}")
    return {}


def _save_settings_file(settings: Dict[str, Any]):
    """설정 파일 저장"""
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)


def _get_session_state(key: str, default: Any = None) -> Any:
    """session_state에서 값 읽기 (Streamlit 환경)"""
    if HAS_STREAMLIT and st is not None:
        try:
            return st.session_state.get(key, default)
        except:
            pass
    return default


def _get_setting(key: str, default: Any = None) -> Any:
    """
    설정값 읽기 (우선순위: session_state > 파일 > 기본값)
    """
    # 1. session_state 확인
    value = _get_session_state(key)
    if value is not None:
        return value

    # 2. 설정 파일 확인
    settings = _load_settings_file()
    if key in settings:
        return settings[key]

    # 3. 기본값 반환
    return default


# ═══════════════════════════════════════════════════════════════════
# 묶음 설정 (Bundle Settings)
# ═══════════════════════════════════════════════════════════════════

def get_bundle_size() -> int:
    """
    사용자가 선택한 묶음 크기 반환

    UI 위치: 묶음 씬분석 옵션 > 묶음 크기
    session_state 키: bundle_size, srt_bundle_size, scene_bundle_size
    """
    # 여러 가능한 키에서 검색
    for key in ["bundle_size", "srt_bundle_size", "scene_bundle_size"]:
        value = _get_setting(key)
        if value is not None:
            bundle_size = int(value)
            print(f"[Config] 묶음 크기: {bundle_size} (사용자 선택, key={key})")
            return bundle_size

    # 기본값
    default_size = 5
    print(f"[Config] 묶음 크기: {default_size} (기본값)")
    return default_size


def get_use_bundle_mode() -> bool:
    """
    묶음 모드 사용 여부

    UI 위치: Claude Code 설정 > 묶음 모드 사용
    session_state 키: use_bundle_mode, bundle_mode_enabled
    """
    for key in ["use_bundle_mode", "bundle_mode_enabled", "enable_bundle_mode"]:
        value = _get_setting(key)
        if value is not None:
            use_bundle = bool(value)
            print(f"[Config] 묶음 모드: {use_bundle} (사용자 선택)")
            return use_bundle

    # 기본값: 활성화
    print(f"[Config] 묶음 모드: True (기본값)")
    return True


# ═══════════════════════════════════════════════════════════════════
# 프롬프트 설정 (Prompt Settings)
# ═══════════════════════════════════════════════════════════════════

def get_selected_prompt_id() -> Optional[str]:
    """
    사용자가 선택한 프롬프트 템플릿 ID

    UI 위치: 분석 프롬프트 설정 > 사용할 프롬프트
    session_state 키: selected_prompt_id, srt_analysis_prompt_id, prompt_template_id
    """
    for key in [
        "selected_prompt_id",
        "srt_analysis_prompt_id",
        "prompt_template_id",
        "scene_analysis_prompt_id",
        "current_prompt_id"
    ]:
        value = _get_setting(key)
        if value:
            print(f"[Config] 프롬프트 ID: {value} (사용자 선택, key={key})")
            return str(value)

    print(f"[Config] 프롬프트 ID: None (기본 사용)")
    return None


def get_prompt_template_path() -> Optional[str]:
    """
    선택된 프롬프트 템플릿의 파일 경로
    """
    prompt_id = get_selected_prompt_id()

    if not prompt_id:
        return None

    # 가능한 템플릿 경로들
    possible_paths = [
        ROOT_DIR / "data" / "prompts" / "templates" / f"{prompt_id}.md",
        ROOT_DIR / "data" / "prompts" / f"{prompt_id}.md",
        ROOT_DIR / "prompts" / f"{prompt_id}.md",
    ]

    for template_path in possible_paths:
        if template_path.exists():
            print(f"[Config] 템플릿 경로: {template_path}")
            return str(template_path)

    print(f"[Config] ⚠️ 템플릿 파일 없음: {prompt_id}")
    return None


def get_prompt_template_content() -> Optional[str]:
    """
    선택된 프롬프트 템플릿의 내용 읽기
    """
    template_path = get_prompt_template_path()

    if not template_path:
        return None

    try:
        with open(template_path, 'r', encoding='utf-8') as f:
            content = f.read()
        print(f"[Config] 템플릿 내용 로드: {len(content)}자")
        return content
    except Exception as e:
        print(f"[Config] ⚠️ 템플릿 읽기 실패: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════
# Claude Code 실행 설정
# ═══════════════════════════════════════════════════════════════════

def get_timeout() -> int:
    """
    Claude Code 타임아웃 (초)

    UI 위치: Claude Code 설정 > 타임아웃
    session_state 키: claude_code_timeout, cc_timeout, timeout
    """
    for key in ["claude_code_timeout", "cc_timeout", "timeout", "batch_timeout"]:
        value = _get_setting(key)
        if value is not None:
            timeout = int(value)
            print(f"[Config] 타임아웃: {timeout}초 (사용자 선택)")
            return timeout

    # 기본값: 600초 (10분)
    default_timeout = 600
    print(f"[Config] 타임아웃: {default_timeout}초 (기본값)")
    return default_timeout


def get_additional_instructions() -> str:
    """
    추가 지시사항

    UI 위치: Claude Code 설정 > 추가 지시사항
    session_state 키: additional_instructions, extra_instructions, custom_instructions
    """
    for key in ["additional_instructions", "extra_instructions", "custom_instructions"]:
        value = _get_setting(key)
        if value:
            print(f"[Config] 추가 지시사항: {len(value)}자")
            return str(value)

    return ""


def get_processing_mode() -> str:
    """
    처리 모드

    UI 위치: AI 분석 설정 > 처리 모드
    session_state 키: processing_mode, analysis_mode, cc_processing_mode
    """
    for key in ["processing_mode", "analysis_mode", "cc_processing_mode"]:
        value = _get_setting(key)
        if value:
            print(f"[Config] 처리 모드: {value}")
            return str(value)

    return "batch"


# ═══════════════════════════════════════════════════════════════════
# 배치 설정 (Batch Settings)
# ═══════════════════════════════════════════════════════════════════

def get_batch_size() -> int:
    """
    배치 크기 (묶음을 몇 개씩 처리할지)

    동적 결정 또는 사용자 설정
    """
    for key in ["batch_size", "cc_batch_size", "bundles_per_batch"]:
        value = _get_setting(key)
        if value is not None:
            batch_size = int(value)
            print(f"[Config] 배치 크기: {batch_size} (사용자 선택)")
            return batch_size

    # 기본값: 동적 결정을 위해 0 반환
    return 0


def calculate_dynamic_batch_size(total_bundles: int) -> int:
    """
    묶음 수에 따른 동적 배치 크기 결정

    Args:
        total_bundles: 총 묶음 수

    Returns:
        적정 배치 크기
    """
    # 사용자 설정이 있으면 우선
    user_batch_size = get_batch_size()
    if user_batch_size > 0:
        return user_batch_size

    # 동적 결정
    if total_bundles < 10:
        batch_size = total_bundles  # 1개 배치
    elif total_bundles <= 30:
        batch_size = 5
    elif total_bundles <= 60:
        batch_size = 8
    elif total_bundles <= 100:
        batch_size = 10
    else:
        batch_size = 15

    print(f"[Config] 배치 크기: {batch_size} (동적 결정, 묶음 수={total_bundles})")
    return batch_size


# ═══════════════════════════════════════════════════════════════════
# 통합 설정 함수
# ═══════════════════════════════════════════════════════════════════

def get_claude_code_config() -> Dict[str, Any]:
    """
    Claude Code 실행에 필요한 모든 사용자 설정값 수집

    Returns:
        설정 딕셔너리
    """
    config = {
        # 묶음 설정 (사용자 선택!)
        "bundle_size": get_bundle_size(),
        "use_bundle_mode": get_use_bundle_mode(),

        # 프롬프트 설정 (사용자 선택!)
        "prompt_template_id": get_selected_prompt_id(),
        "prompt_template_path": get_prompt_template_path(),

        # Claude Code 설정
        "timeout": get_timeout(),
        "additional_instructions": get_additional_instructions(),

        # 처리 모드
        "processing_mode": get_processing_mode(),
    }

    return config


def print_config_summary():
    """설정 요약 출력"""
    config = get_claude_code_config()

    print("\n" + "=" * 50)
    print("  Claude Code 설정 (사용자 선택값)")
    print("=" * 50)
    print(f"  묶음 크기: {config['bundle_size']}")
    print(f"  묶음 모드: {config['use_bundle_mode']}")
    print(f"  프롬프트 ID: {config['prompt_template_id']}")
    print(f"  타임아웃: {config['timeout']}초")
    print(f"  처리 모드: {config['processing_mode']}")
    if config['additional_instructions']:
        print(f"  추가 지시: {len(config['additional_instructions'])}자")
    print("=" * 50 + "\n")


# ═══════════════════════════════════════════════════════════════════
# 설정 저장 함수 (UI에서 호출)
# ═══════════════════════════════════════════════════════════════════

def save_claude_code_settings(
    bundle_size: int = None,
    use_bundle_mode: bool = None,
    prompt_template_id: str = None,
    timeout: int = None,
    additional_instructions: str = None
):
    """
    Claude Code 설정 저장

    UI에서 설정 변경 시 호출하여 영속화
    """
    settings = _load_settings_file()

    if bundle_size is not None:
        settings["bundle_size"] = bundle_size
    if use_bundle_mode is not None:
        settings["use_bundle_mode"] = use_bundle_mode
    if prompt_template_id is not None:
        settings["prompt_template_id"] = prompt_template_id
    if timeout is not None:
        settings["timeout"] = timeout
    if additional_instructions is not None:
        settings["additional_instructions"] = additional_instructions

    _save_settings_file(settings)
    print(f"[Config] 설정 저장 완료: {list(settings.keys())}")


if __name__ == "__main__":
    # 테스트
    print_config_summary()

    config = get_claude_code_config()
    print(f"\nFull config: {json.dumps(config, indent=2, ensure_ascii=False, default=str)}")
