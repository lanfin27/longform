# -*- coding: utf-8 -*-
"""
Claude Code Streamlit UI 헬퍼 (v1.3)

Streamlit에서 Claude Code 진행률 모니터링 + 자동 완료 처리

v1.3: 캐시 무효화 추가
  - 분석 완료 후 씬 캐시 자동 삭제
  - clear_scene_cache() 호출로 stale 데이터 방지

v1.2: UTF-8 BOM 인코딩 오류 수정
  - 모든 JSON/텍스트 파일 읽기에 'utf-8-sig' 인코딩 사용
  - load_json_safe_st() 헬퍼 함수 추가

사용법:
    from utils.claude_code_ui_helpers import (
        render_claude_code_progress_ui,
        handle_claude_code_completion,
        sync_scenes_to_streamlit
    )
"""

import streamlit as st
import time
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List


def load_json_safe_st(file_path) -> Optional[Dict[str, Any]]:
    """
    JSON 파일 안전하게 로드 (BOM 처리 포함) - v1.2

    Args:
        file_path: JSON 파일 경로 (str 또는 Path)

    Returns:
        파싱된 딕셔너리/리스트 (실패 시 None)
    """
    file_path = Path(file_path) if isinstance(file_path, str) else file_path

    if not file_path.exists():
        return None

    # 여러 인코딩 시도 (BOM 처리용 utf-8-sig 우선)
    encodings = ['utf-8-sig', 'utf-8', 'cp949']

    for encoding in encodings:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                content = f.read()

            # BOM 수동 제거 (혹시 모를 경우 대비)
            if content.startswith('\ufeff'):
                content = content[1:]

            return json.loads(content)

        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        except Exception:
            continue

    return None


def read_text_safe_st(file_path) -> Optional[str]:
    """
    텍스트 파일 안전하게 읽기 (BOM 처리 포함) - v1.2

    Args:
        file_path: 파일 경로

    Returns:
        파일 내용 문자열 (실패 시 None)
    """
    file_path = Path(file_path) if isinstance(file_path, str) else file_path

    if not file_path.exists():
        return None

    encodings = ['utf-8-sig', 'utf-8', 'cp949']

    for encoding in encodings:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                content = f.read()

            if content.startswith('\ufeff'):
                content = content[1:]

            return content

        except (UnicodeDecodeError, Exception):
            continue

    return None


def get_claude_code_progress_st(project_path: str) -> dict:
    """
    Claude Code 진행률 읽기 (Streamlit용) - v1.2 BOM 처리

    Args:
        project_path: 프로젝트 경로

    Returns:
        진행률 딕셔너리 또는 None
    """
    progress_file = Path(project_path) / "logs" / "claude_code" / "_progress.json"

    # v1.2: BOM 안전 로드 사용
    return load_json_safe_st(progress_file)


def is_claude_code_complete_st(project_path: str) -> bool:
    """
    Claude Code 완료 여부 확인 (Streamlit용) - v1.2 BOM 처리

    v1.1: 플래그 파일 존재만 확인하지 않고 내용도 검증
      - "COMPLETE" → True (성공 완료)
      - "ERROR", "FAIL", "NO_SCENES" 포함 → False (오류)
      - 파일 없음 → False

    v1.2: UTF-8 BOM 인코딩 오류 수정

    Args:
        project_path: 프로젝트 경로

    Returns:
        완료 여부 (True=성공 완료, False=미완료 또는 오류)
    """
    complete_flag = Path(project_path) / "logs" / "claude_code" / "_analysis_complete.flag"

    if not complete_flag.exists():
        return False

    # v1.2: BOM 안전 읽기 사용
    content = read_text_safe_st(complete_flag)

    if content is None:
        print(f"[is_claude_code_complete_st] 플래그 파일 읽기 실패")
        return complete_flag.exists()  # fallback: 존재 여부만 확인

    content = content.strip().upper()

    # 성공 완료
    if content == "COMPLETE":
        return True

    # 오류 케이스
    if "ERROR" in content or "FAIL" in content or "NO_SCENES" in content:
        print(f"[is_claude_code_complete_st] 오류 감지됨: {content[:100]}")
        return False

    # 알 수 없는 내용이면 완료로 간주 (호환성)
    return True


def get_analysis_status_st(project_path: str) -> dict:
    """
    분석 상태 상세 확인 (Streamlit용) - v1.2 BOM 처리

    플래그 파일과 progress.json 모두 확인하여 정확한 상태 반환

    v1.2: UTF-8 BOM 인코딩 오류 수정

    Args:
        project_path: 프로젝트 경로

    Returns:
        상태 딕셔너리:
        - status: 'not_started', 'running', 'complete', 'error', 'no_scenes'
        - message: 상태 메시지
        - is_success: 성공 여부 (True=분석 완료, False=오류 또는 진행 중)
        - analyzed_count: 분석된 씬 수
        - total_count: 전체 씬 수
    """
    logs_dir = Path(project_path) / "logs" / "claude_code"
    complete_flag = logs_dir / "_analysis_complete.flag"
    progress_file = logs_dir / "_progress.json"

    result = {
        'status': 'not_started',
        'message': '분석이 시작되지 않았습니다.',
        'is_success': False,
        'analyzed_count': 0,
        'total_count': 0
    }

    # 1. progress.json 확인 (더 상세한 정보) - v1.2: BOM 안전 로드
    progress = load_json_safe_st(progress_file)
    if progress:
        result['analyzed_count'] = progress.get('current', 0)
        result['total_count'] = progress.get('total', 0)

        status_str = progress.get('status', 'unknown')
        message = progress.get('message', '')

        # 에러 체크
        if progress.get('error'):
            result['status'] = 'error'
            result['message'] = message or '분석 중 오류 발생'
            result['is_success'] = False
            return result

        # NO_SCENES 체크
        if 'NO_SCENES' in message.upper() or 'no_scenes' in str(progress).lower():
            result['status'] = 'no_scenes'
            result['message'] = '요청된 씬 ID가 scenes.json에 존재하지 않습니다.'
            result['is_success'] = False
            return result

        if status_str == 'complete':
            exit_code = progress.get('exit_code', 0)
            if exit_code != 0:
                result['status'] = 'error'
                result['message'] = f'분석 실패 (종료 코드: {exit_code})'
                result['is_success'] = False
            else:
                result['status'] = 'complete'
                result['message'] = f"분석 완료 ({result['analyzed_count']}/{result['total_count']}개 씬)"
                result['is_success'] = True
            return result

        elif status_str == 'running':
            result['status'] = 'running'
            result['message'] = f"분석 중... ({result['analyzed_count']}/{result['total_count']}개)"
            return result

    # 2. 플래그 파일 확인 (fallback) - v1.2: BOM 안전 읽기
    content = read_text_safe_st(complete_flag)
    if content:
        content = content.strip()
        content_upper = content.upper()

        if 'NO_SCENES' in content_upper:
            result['status'] = 'no_scenes'
            result['message'] = content
            result['is_success'] = False
        elif 'ERROR' in content_upper or 'FAIL' in content_upper:
            result['status'] = 'error'
            result['message'] = content
            result['is_success'] = False
        elif content_upper == 'COMPLETE':
            result['status'] = 'complete'
            result['message'] = '분석 완료'
            result['is_success'] = True
        else:
            result['status'] = 'complete'
            result['message'] = content or '분석 완료'
            result['is_success'] = True

    return result


def cleanup_claude_code_files_st(project_path: str):
    """
    Claude Code 임시 파일 정리 (Streamlit용)

    Args:
        project_path: 프로젝트 경로
    """
    logs_dir = Path(project_path) / "logs" / "claude_code"

    files_to_remove = [
        logs_dir / "_progress.json",
        logs_dir / "_analysis_complete.flag"
    ]

    for f in files_to_remove:
        if f.exists():
            try:
                f.unlink()
            except:
                pass


def reload_scenes_and_sync(scenes_json_path: str) -> list:
    """
    scenes.json 로드 + session_state 동기화 - v1.3 캐시 무효화

    v1.3: 분석 완료 후 씬 캐시 자동 삭제
    v1.2: BOM 안전 로드 사용

    Args:
        scenes_json_path: scenes.json 파일 경로

    Returns:
        로드된 씬 목록
    """
    scenes_path = Path(scenes_json_path)

    if not scenes_path.exists():
        print(f"[UI Helper] scenes.json not found: {scenes_json_path}")
        return []

    # v1.3: 캐시 무효화 (stale 데이터 방지)
    try:
        from utils.scene_character_loader import clear_scene_cache
        project_path = str(scenes_path.parent)  # scenes.json의 부모 디렉토리
        clear_scene_cache(project_path)
        print(f"[UI Helper] 씬 캐시 삭제 완료: {project_path}")
    except ImportError:
        print("[UI Helper] scene_character_loader 임포트 실패 - 캐시 삭제 건너뜀")
    except Exception as e:
        print(f"[UI Helper] 캐시 삭제 중 오류: {e}")

    # v1.2: BOM 안전 로드 사용
    scenes = load_json_safe_st(scenes_path)

    if scenes is None:
        print(f"[UI Helper] scenes.json 로드 실패 (BOM 또는 인코딩 문제)")
        return []

    # session_state에 동기화 (모든 관련 키)
    sync_scenes_to_streamlit(scenes, scenes_json_path)

    print(f"[UI Helper] scenes.json 로드 + 동기화 완료: {len(scenes)}개 씬")
    return scenes


def sync_scenes_to_streamlit(scenes: list, scenes_json_path: str = None):
    """
    씬 데이터를 Streamlit session_state의 모든 관련 키에 동기화

    Args:
        scenes: 씬 데이터 리스트
        scenes_json_path: scenes.json 파일 경로 (선택)
    """
    # 분석 완료 여부 확인
    analyzed_count = sum(1 for s in scenes if s.get('background_prompt_en'))

    # 메인 씬 데이터 (여러 키에 동일 데이터)
    st.session_state['scenes'] = scenes
    st.session_state['scenes_data'] = scenes
    st.session_state['analysis_scenes'] = scenes
    st.session_state['loaded_scenes'] = scenes
    st.session_state['current_scenes'] = scenes

    # 분석 상태 플래그
    st.session_state['analysis_complete'] = True
    st.session_state['has_analysis_data'] = analyzed_count > 0
    st.session_state['scenes_analyzed'] = analyzed_count > 0
    st.session_state['scenes_json_loaded'] = True

    # 메타 정보
    st.session_state['scenes_count'] = len(scenes)
    st.session_state['analyzed_scenes_count'] = analyzed_count
    st.session_state['scenes_loaded_at'] = datetime.now().isoformat()
    st.session_state['last_analysis_time'] = datetime.now().isoformat()

    if scenes_json_path:
        st.session_state['scenes_json_path'] = scenes_json_path

    print(f"[UI Helper] session_state 동기화 완료: {len(scenes)}개 씬, {analyzed_count}개 분석됨")


def get_scenes_from_session() -> list:
    """
    session_state에서 씬 데이터 가져오기 (여러 키 시도)

    Returns:
        씬 데이터 리스트 (없으면 빈 리스트)
    """
    possible_keys = [
        'scenes',
        'scenes_data',
        'analysis_scenes',
        'loaded_scenes',
        'current_scenes'
    ]

    for key in possible_keys:
        if key in st.session_state and st.session_state[key]:
            return st.session_state[key]

    return []


def ensure_scenes_loaded_st(scenes_json_path: str) -> list:
    """
    씬 데이터가 로드되어 있는지 확인하고, 없으면 로드

    Args:
        scenes_json_path: scenes.json 파일 경로

    Returns:
        씬 데이터 리스트
    """
    scenes = get_scenes_from_session()

    if scenes:
        return scenes

    # session_state에 없으면 파일에서 로드
    return reload_scenes_and_sync(scenes_json_path)


def render_claude_code_progress_ui(
    project_path: str,
    scenes_json_path: str,
    timeout: int = 600,
    poll_interval: float = 1.0,
    auto_rerun: bool = True
) -> bool:
    """
    Claude Code 진행률 UI 렌더링 + 자동 완료 처리

    Args:
        project_path: 프로젝트 경로
        scenes_json_path: scenes.json 파일 경로
        timeout: 최대 대기 시간 (초)
        poll_interval: 폴링 간격 (초)
        auto_rerun: 완료 시 자동 새로고침 여부

    Returns:
        완료 여부
    """
    start_time = st.session_state.get('claude_code_start_time', time.time())

    # UI 컨테이너
    progress_container = st.container()

    with progress_container:
        progress_bar = st.progress(0)
        status_text = st.empty()
        detail_text = st.empty()
        time_text = st.empty()

    # 메인 폴링 루프
    while True:
        elapsed = time.time() - start_time

        # 타임아웃 체크
        if elapsed > timeout:
            status_text.error(f"❌ 타임아웃 ({timeout}초)")
            return False

        # 완료 체크
        if is_claude_code_complete_st(project_path):
            progress_bar.progress(1.0)
            status_text.success("✅ **분석 완료!**")

            # 파일 정리
            cleanup_claude_code_files_st(project_path)

            # scenes.json 자동 로드 + 동기화
            scenes = reload_scenes_and_sync(scenes_json_path)

            if scenes:
                analyzed = sum(1 for s in scenes if s.get('background_prompt_en'))
                detail_text.success(f"📊 {len(scenes)}개 씬 로드 완료 ({analyzed}개 분석됨)")

            # 자동 새로고침
            if auto_rerun:
                time.sleep(1)
                st.rerun()

            return True

        # 진행률 읽기
        progress = get_claude_code_progress_st(project_path)

        if progress:
            status = progress.get('status', 'unknown')
            current = progress.get('current', 0)
            total = progress.get('total', 1)
            message = progress.get('message', '')

            # 진행률 계산
            if total > 0:
                pct = min(current / total, 0.99)
            else:
                pct = 0

            # UI 업데이트
            progress_bar.progress(pct)

            if status == 'running':
                status_text.info(f"🔄 **분석 중...** ({current}/{total} 씬)")
            elif status == 'starting':
                status_text.info("🚀 **Claude Code 시작 중...**")
            elif status == 'complete':
                # 진행률 파일이 complete 상태면 완료 처리
                progress_bar.progress(1.0)
                status_text.success("✅ **분석 완료!**")

                cleanup_claude_code_files_st(project_path)
                scenes = reload_scenes_and_sync(scenes_json_path)

                if scenes:
                    analyzed = sum(1 for s in scenes if s.get('background_prompt_en'))
                    detail_text.success(f"📊 {len(scenes)}개 씬 로드 완료 ({analyzed}개 분석됨)")

                if auto_rerun:
                    time.sleep(1)
                    st.rerun()

                return True

            if message:
                detail_text.caption(message)
        else:
            status_text.info("⏳ **Claude Code 대기 중...**")

        # 경과 시간 표시
        time_text.caption(f"⏱️ 경과 시간: {int(elapsed)}초")

        # 폴링 대기
        time.sleep(poll_interval)


def handle_claude_code_completion(
    project_path: str,
    scenes_json_path: str,
    show_success: bool = True
) -> bool:
    """
    Claude Code 완료 처리 (수동 확인용)

    Args:
        project_path: 프로젝트 경로
        scenes_json_path: scenes.json 파일 경로
        show_success: 성공 메시지 표시 여부

    Returns:
        완료 처리 성공 여부
    """
    if not is_claude_code_complete_st(project_path):
        st.warning("⏳ 아직 분석이 완료되지 않았습니다.")
        return False

    # 파일 정리
    cleanup_claude_code_files_st(project_path)

    # scenes.json 로드 + 동기화
    scenes = reload_scenes_and_sync(scenes_json_path)

    if not scenes:
        st.error("❌ scenes.json 로드 실패!")
        return False

    if show_success:
        analyzed = sum(1 for s in scenes if s.get('background_prompt_en'))
        st.success(f"✅ {len(scenes)}개 씬 로드 완료! ({analyzed}개 분석됨)")

    return True


def render_sync_button(scenes_json_path: str, button_label: str = "🔄 데이터 동기화"):
    """
    씬 데이터 동기화 버튼 렌더링

    Args:
        scenes_json_path: scenes.json 파일 경로
        button_label: 버튼 라벨
    """
    if st.button(button_label, use_container_width=True):
        scenes = reload_scenes_and_sync(scenes_json_path)

        if scenes:
            analyzed = sum(1 for s in scenes if s.get('background_prompt_en'))

            if analyzed > 0:
                st.success(f"✅ {len(scenes)}개 씬 동기화 완료! ({analyzed}개 분석됨)")
            else:
                st.warning(f"⚠️ {len(scenes)}개 씬 로드됨, 분석 데이터 없음")

            st.rerun()
        else:
            st.error("❌ 씬 데이터 로드 실패!")


def check_analysis_status(scenes: list = None, scenes_json_path: str = None) -> dict:
    """
    씬 분석 상태 확인

    Args:
        scenes: 씬 데이터 (None이면 session_state에서 가져옴)
        scenes_json_path: scenes.json 경로 (scenes가 None일 때 사용)

    Returns:
        상태 딕셔너리:
        - has_scenes: 씬 데이터 존재 여부
        - total_count: 전체 씬 수
        - analyzed_count: 분석된 씬 수
        - has_analysis: 분석 데이터 존재 여부
        - completion_rate: 완료율 (0.0 ~ 1.0)
    """
    if scenes is None:
        scenes = get_scenes_from_session()

        if not scenes and scenes_json_path:
            scenes = reload_scenes_and_sync(scenes_json_path)

    if not scenes:
        return {
            'has_scenes': False,
            'total_count': 0,
            'analyzed_count': 0,
            'has_analysis': False,
            'completion_rate': 0.0
        }

    total = len(scenes)
    analyzed = sum(1 for s in scenes if s.get('background_prompt_en'))

    return {
        'has_scenes': True,
        'total_count': total,
        'analyzed_count': analyzed,
        'has_analysis': analyzed > 0,
        'completion_rate': analyzed / total if total > 0 else 0.0
    }
