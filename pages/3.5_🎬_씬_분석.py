"""
3.5단계: 씬 분석

스크립트를 분석하여:
1. 씬(Scene) 단위로 자동 분할
2. 등장 캐릭터 추출
3. 각 씬의 연출가이드 생성
4. 이미지 프롬프트 자동 생성
"""
import streamlit as st
import json
import time
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from utils.project_manager import (
    ensure_project_selected,
    get_current_project,
    get_current_project_config,
    render_project_sidebar,
    update_project_step
)
from utils.data_loader import load_script
from utils.script_sync_manager import sync_load_script, get_synced_script_info
from utils.scene_character_loader import clear_scene_cache
from utils.api_helper import require_api_key, show_api_status_sidebar
from utils.progress_ui import render_api_selector, StreamlitProgressUI
from core.api.api_manager import get_api_manager
from core.prompt.prompt_template_manager import get_template_manager, reload_template_manager
from components.prompt_viewer import (
    render_prompts_viewer,
    render_bulk_download_section,
    render_enhanced_bulk_download_section,
    render_quick_prompt_downloads,
    get_prompt,
    PROMPT_TYPES
)
from components.prompt_default_selector import (
    render_default_prompt_settings,
    get_auto_selected_prompt_id
)
from utils.prompt_defaults import get_default_prompt_id
import os
import re
from datetime import datetime

# 사용자 설정 영속성 (v1.0) - settings_manager 사용
from utils.settings_manager import (
    get_setting, set_setting,
    persistent_selectbox, persistent_radio, persistent_checkbox
)

# 채널-영상별 씬 분석 설정 (v1.1)
from utils.user_preferences import (
    get_scene_analysis_settings,
    save_scene_analysis_settings,
    get_script_source,
    set_script_source,
    get_analysis_method,
    set_analysis_method,
    get_analysis_language,
    set_analysis_language
)

# 씬 검증 유틸리티 (background_prompt_en 자동 수정)
try:
    from utils.scene_validator import validate_scenes_before_save
    SCENE_VALIDATOR_AVAILABLE = True
except ImportError:
    SCENE_VALIDATOR_AVAILABLE = False
    def validate_scenes_before_save(scenes, verbose=True):
        return scenes

# 페이지 설정 키
PAGE_SETTINGS_NAME = "scene_analysis"


# ============================================================
# ⭐ 성능 최적화: 캐싱 데코레이터 및 초기화 플래그
# ============================================================

@st.cache_data(ttl=60, show_spinner=False)
def _cached_sync_load_script(project_path_str: str):
    """스크립트 동기화 로드 (캐싱 적용)"""
    return sync_load_script(project_path_str)


@st.cache_data(ttl=60, show_spinner=False)
def _cached_load_script(project_path, language: str, script_type: str):
    """스크립트 파일 로드 (캐싱 적용)"""
    return load_script(project_path, language, script_type)


def _get_page_init_key():
    """페이지 초기화 키 생성"""
    return f"scene_analysis_initialized_{st.session_state.get('current_project', '')}"


# ============================================================
# 스크립트 다운로드 헬퍼 함수
# ============================================================

def extract_scripts_from_scenes(scenes: list) -> str:
    """
    씬 목록에서 스크립트만 추출하여 TXT 형식으로 변환

    형식:
        살면서 지갑을 네 번 잃어버렸는데 한 번이 유독 기억에 남아요///
        그날 저는 이제 막 친구들이랑 시내에 딱 도착했는데///
        ...

    Args:
        scenes: 분석된 씬 목록

    Returns:
        str: "///" 구분자로 구분된 스크립트 텍스트
    """
    if not scenes:
        return ""

    script_lines = []

    for scene in scenes:
        # 스크립트 텍스트 추출 (여러 가능한 키 이름 처리)
        script = None
        # v3.36: script_ko 우선 추가 (scenes.json의 기본 필드)
        possible_keys = ["script_ko", "script_text", "text", "narration", "대사", "content", "dialogue", "나레이션"]

        for key in possible_keys:
            if scene.get(key):
                script = scene.get(key)
                break

        # 스크립트가 있는 경우만 추가
        if script and str(script).strip():
            # 문자열로 변환 및 정리
            cleaned_script = str(script).strip()

            # 내부 줄바꿈을 공백으로 변환 (한 줄로 만들기)
            cleaned_script = cleaned_script.replace("\n", " ").replace("\r", "")

            # 연속 공백 제거
            cleaned_script = re.sub(r'\s+', ' ', cleaned_script)

            # "///" 구분자 추가
            script_lines.append(f"{cleaned_script}///")

    # 줄바꿈으로 연결
    return "\n".join(script_lines)


def get_script_download_filename(project_name: str = "") -> str:
    """스크립트 다운로드 파일명 생성"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if project_name:
        # 파일명에 사용할 수 없는 문자 제거
        safe_name = re.sub(r'[<>:"/\\|?*]', '', project_name)
        safe_name = safe_name.strip()[:50]  # 최대 50자
        return f"{safe_name}_script_{timestamp}.txt"

    return f"script_{timestamp}.txt"


def extract_prompts_from_scenes(scenes: list) -> str:
    """씬 목록에서 이미지 프롬프트만 추출"""
    prompt_lines = []

    for scene in scenes:
        scene_id = scene.get("scene_id", scene.get("index", 0))

        # 이미지 프롬프트 추출 (여러 가능한 키)
        prompt = (
            scene.get("image_prompt_en") or
            scene.get("image_prompt") or
            scene.get("prompt") or
            ""
        )

        if prompt and prompt.strip():
            prompt_lines.append(f"[씬 {scene_id}]")
            prompt_lines.append(prompt.strip())
            prompt_lines.append("")  # 빈 줄

    return "\n".join(prompt_lines)


# ============================================================
# 캐릭터 이름 추출 헬퍼 함수 (v3.15)
# ============================================================

def extract_character_names(characters: list) -> list:
    """캐릭터 리스트에서 이름만 추출

    characters가 문자열 리스트 또는 딕셔너리 리스트일 수 있음:
    - ["발표자", "화자"] → 그대로 반환
    - [{"name": "발표자"}, {"name": "화자"}] → ["발표자", "화자"]

    Args:
        characters: 캐릭터 리스트 (문자열 또는 딕셔너리)

    Returns:
        캐릭터 이름 문자열 리스트
    """
    if not characters:
        return []

    names = []
    for c in characters:
        if isinstance(c, dict):
            name = c.get("name", "")
            if name:
                names.append(str(name))
        elif c:
            names.append(str(c))
    return names


def format_character_names(characters: list, max_count: int = None) -> str:
    """캐릭터 리스트를 포맷된 문자열로 변환

    Args:
        characters: 캐릭터 리스트 (문자열 또는 딕셔너리)
        max_count: 최대 표시 개수 (None이면 전체)

    Returns:
        "이름1, 이름2, 이름3..." 형태의 문자열
    """
    names = extract_character_names(characters)
    if not names:
        return ""

    if max_count:
        display_names = names[:max_count]
        result = ", ".join(display_names)
        if len(names) > max_count:
            result += "..."
    else:
        result = ", ".join(names)

    return result


# ============================================================
# ⭐ v3.70: Claude Code 에이전트 수동 실행 헬퍼 함수
# ============================================================

def generate_claude_agent_prompt(scenes_json_path: str, scene_range: str = None) -> str:
    """
    Claude Code 앱에서 직접 실행할 에이전트 프롬프트 생성

    Args:
        scenes_json_path: scenes.json 파일 경로
        scene_range: 분석할 씬 범위 (예: "1-30"), None이면 전체

    Returns:
        복사용 프롬프트 문자열
    """
    range_text = f"씬 {scene_range}" if scene_range else "전체 씬"

    prompt = f'''# 씬 분석 작업

## 파일
`{scenes_json_path}`

## 범위
{range_text}

## 작업
1. 위 파일을 읽으세요
2. 각 씬의 script 필드를 분석하세요
3. 다음 필드를 각 씬에 추가하세요:

| 필드 | 설명 |
|------|------|
| background_prompt_en | 배경 영문 프롬프트 (80-150단어, "2D animation style" 포함, 사람X) |
| character_prompt_en | 캐릭터 영문 프롬프트 (50-100단어, "2D animated style" 포함) |
| characters | 등장인물 리스트 - 한글 (예: ["진행자", "전문가"]) |
| visual_elements | 시각 요소 - 한글 (예: "회의실, 모니터") |
| scene_mood | 분위기 - 영문 (예: "professional, serious") |

4. 수정된 JSON을 같은 파일에 저장하세요

## 규칙
- script 필드 절대 수정 금지!
- 기존 필드 유지, 새 필드만 추가

## 시작
지금 바로 파일을 읽고 분석을 시작하세요.
완료 후 "분석 완료: X개 씬" 형식으로 알려주세요.
'''
    return prompt


def check_scenes_analysis_status(scenes: list) -> dict:
    """
    씬 분석 상태 확인

    Args:
        scenes: 씬 데이터 리스트

    Returns:
        각 필드별 완료 개수를 담은 딕셔너리
    """
    stats = {
        'total': len(scenes),
        'background_prompt_en': 0,
        'character_prompt_en': 0,
        'characters': 0,
        'visual_elements': 0,
        'scene_mood': 0
    }

    for scene in scenes:
        for field in ['background_prompt_en', 'character_prompt_en', 'characters', 'visual_elements', 'scene_mood']:
            value = scene.get(field)

            if value:
                if isinstance(value, list) and len(value) > 0:
                    stats[field] += 1
                elif isinstance(value, str) and len(value) > 10:
                    stats[field] += 1

    return stats


def create_agent_file_for_scene_analysis(project_path: str, scenes_json_path: str, scene_range: str = None) -> str:
    """
    에이전트 파일 생성 (Claude Code에서 직접 실행 가능)

    Args:
        project_path: 프로젝트 경로
        scenes_json_path: scenes.json 파일 경로
        scene_range: 분석할 씬 범위

    Returns:
        생성된 에이전트 파일 경로 또는 None
    """
    agents_dir = os.path.join(project_path, 'agents')
    os.makedirs(agents_dir, exist_ok=True)

    agent_file = os.path.join(agents_dir, 'run_scene_analysis.md')
    prompt = generate_claude_agent_prompt(scenes_json_path, scene_range)

    try:
        with open(agent_file, 'w', encoding='utf-8') as f:
            f.write(prompt)
        return agent_file
    except Exception as e:
        print(f"[에이전트] 파일 생성 실패: {e}")
        return None


def render_claude_code_manual_execution_ui(project_path, scenes_json_path: str):
    """
    Claude Code 수동 실행 UI 렌더링 (Max Plan 무료 활용)

    subprocess 대신 사용자가 Claude Code 앱에서 직접 실행
    """
    st.markdown("---")
    st.markdown("### 🤖 Claude Code 수동 실행 (Max Plan 무료)")

    st.info("""
    **✨ 수동 실행 장점:**
    - 🆓 **완전 무료** (Claude Max Plan 구독자)
    - 🧠 Claude Opus 4.5 수준의 고품질 분석
    - 📁 파일 직접 수정으로 빠른 처리
    - 🔄 API 크레딧 소모 없음
    """)

    # 분석 대상 파일 표시
    st.markdown("**📁 분석 대상 파일:**")
    st.code(scenes_json_path, language="text")

    # 분석 범위 선택
    col1, col2 = st.columns(2)

    with col1:
        analyze_all = st.checkbox("전체 씬 분석", value=True, key="agent_analyze_all")

    with col2:
        if not analyze_all:
            scene_range = st.text_input(
                "씬 범위 (예: 1-30)",
                value="1-30",
                key="agent_scene_range"
            )
        else:
            scene_range = None

    # 프롬프트 생성
    agent_prompt = generate_claude_agent_prompt(scenes_json_path, scene_range)

    # 탭으로 두 가지 방법 제공
    tab1, tab2 = st.tabs(["📋 방법 1: 프롬프트 복사", "📄 방법 2: 에이전트 파일"])

    with tab1:
        st.markdown("""
        **단계:**
        1. 아래 "프롬프트 복사" 버튼 클릭
        2. Claude Code 앱 열기 (longform 폴더에서)
        3. 프롬프트를 붙여넣고 실행
        4. 완료 후 아래 "결과 확인" 버튼 클릭
        """)

        btn_col1, btn_col2 = st.columns([3, 1])

        with btn_col1:
            if st.button("📋 프롬프트 복사", type="primary", use_container_width=True, key="copy_agent_prompt"):
                try:
                    import pyperclip
                    pyperclip.copy(agent_prompt)
                    st.success("✅ 클립보드에 복사되었습니다! Claude Code에서 붙여넣기하세요.")
                except ImportError:
                    st.warning("pyperclip 패키지가 설치되지 않았습니다. 아래 프롬프트를 직접 복사해주세요.")
                    st.code(agent_prompt, language="markdown")
                except Exception as e:
                    st.error(f"복사 실패: {e}")
                    st.code(agent_prompt, language="markdown")

        with btn_col2:
            if st.button("📂 폴더 열기", key="open_folder"):
                try:
                    folder = os.path.dirname(scenes_json_path)
                    os.startfile(folder)
                except Exception as e:
                    st.error(f"폴더 열기 실패: {e}")

        # 프롬프트 미리보기
        with st.expander("📝 프롬프트 미리보기", expanded=False):
            st.code(agent_prompt, language="markdown")

        # Claude Code 실행 명령어
        st.markdown("**💻 Claude Code 실행:**")
        st.code("cd C:\\Users\\KIMJAEHEON\\longform\nclaude", language="bash")

    with tab2:
        st.markdown("""
        **단계:**
        1. "에이전트 파일 생성" 버튼 클릭
        2. Claude Code에서 에이전트 실행
        """)

        if st.button("📄 에이전트 파일 생성", type="primary", use_container_width=True, key="create_agent_file"):
            agent_file = create_agent_file_for_scene_analysis(
                str(project_path), scenes_json_path, scene_range
            )

            if agent_file:
                st.success(f"✅ 에이전트 파일 생성됨!")
                st.code(agent_file, language="text")
                st.markdown("**실행 명령어:**")
                st.code(f'claude "{agent_file} 파일의 지시대로 씬 분석을 수행해줘"', language="bash")
            else:
                st.error("❌ 에이전트 파일 생성 실패")

    # ─────────────────────────────────────────────────────────
    # 분석 상태 모니터링 섹션
    # ─────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 📊 분석 상태")

    # 파일 수정 시간 표시
    if os.path.exists(scenes_json_path):
        mtime = os.path.getmtime(scenes_json_path)
        mtime_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(mtime))
        st.caption(f"📅 마지막 수정: {mtime_str}")

    # 새로고침 버튼
    refresh_col1, refresh_col2 = st.columns(2)

    with refresh_col1:
        if st.button("🔄 결과 확인", use_container_width=True, key="refresh_analysis_result"):
            # scenes.json 다시 로드
            try:
                with open(scenes_json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                scenes = data.get('scenes', data) if isinstance(data, dict) else data

                if scenes:
                    stats = check_scenes_analysis_status(scenes)

                    # 세션에 저장
                    st.session_state['scenes'] = scenes
                    st.session_state['_agent_analysis_stats'] = stats

                    st.success(f"✅ 데이터 새로고침 완료! ({len(scenes)}개 씬)")
                    st.rerun()
                else:
                    st.warning("씬 데이터가 없습니다.")
            except Exception as e:
                st.error(f"파일 로드 실패: {e}")

    with refresh_col2:
        if st.button("📁 JSON 파일 열기", use_container_width=True, key="open_json_file"):
            try:
                os.startfile(scenes_json_path)
            except Exception as e:
                st.error(f"파일 열기 실패: {e}")

    # 현재 분석 상태 표시
    if '_agent_analysis_stats' in st.session_state:
        stats = st.session_state['_agent_analysis_stats']

        col1, col2, col3, col4, col5 = st.columns(5)

        with col1:
            st.metric("총 씬", stats['total'])

        with col2:
            st.metric("배경 프롬프트", f"{stats['background_prompt_en']}/{stats['total']}")

        with col3:
            st.metric("캐릭터 프롬프트", f"{stats['character_prompt_en']}/{stats['total']}")

        with col4:
            st.metric("캐릭터 목록", f"{stats['characters']}/{stats['total']}")

        with col5:
            completion = stats['background_prompt_en'] / stats['total'] * 100 if stats['total'] > 0 else 0
            st.metric("완료율", f"{completion:.0f}%")
    else:
        # 초기 로드 시 상태 계산
        if os.path.exists(scenes_json_path):
            try:
                with open(scenes_json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                scenes = data.get('scenes', data) if isinstance(data, dict) else data

                if scenes:
                    stats = check_scenes_analysis_status(scenes)
                    st.session_state['_agent_analysis_stats'] = stats

                    col1, col2, col3, col4, col5 = st.columns(5)

                    with col1:
                        st.metric("총 씬", stats['total'])

                    with col2:
                        st.metric("배경 프롬프트", f"{stats['background_prompt_en']}/{stats['total']}")

                    with col3:
                        st.metric("캐릭터 프롬프트", f"{stats['character_prompt_en']}/{stats['total']}")

                    with col4:
                        st.metric("캐릭터 목록", f"{stats['characters']}/{stats['total']}")

                    with col5:
                        completion = stats['background_prompt_en'] / stats['total'] * 100 if stats['total'] > 0 else 0
                        st.metric("완료율", f"{completion:.0f}%")
            except Exception:
                st.caption("분석 상태를 확인하려면 '결과 확인' 버튼을 클릭하세요.")
        else:
            st.warning("scenes.json 파일이 없습니다. 먼저 SRT를 파싱하거나 씬 분석을 실행하세요.")


# ═══════════════════════════════════════════════════════════════════════════════
# v3.71: 에이전트 모드 UI (배치 분석에서 사용)
# ═══════════════════════════════════════════════════════════════════════════════

def _render_claude_code_agent_ui():
    """
    Claude Code 에이전트 모드 UI 렌더링 (v3.71)

    배치 분석에서 AGENT_MODE_REQUIRED 반환 시 표시됩니다.
    session_state에서 프롬프트 정보를 가져옵니다.
    """
    st.markdown("---")
    st.markdown("### 🤖 Claude Code 에이전트 모드")

    st.warning("""
    **Claude Code CLI (subprocess)는 API 크레딧을 소모합니다.**

    대신 Claude Code 앱에서 직접 실행하면 **Max Plan이 적용되어 무료**입니다!
    """)

    # session_state에서 프롬프트 정보 가져오기
    prompt_text = st.session_state.get('claude_code_prompt', '')
    prompt_file = st.session_state.get('claude_code_prompt_file', '')
    scenes_path = st.session_state.get('claude_code_scenes_path', '')

    # 실행 방법 안내
    st.markdown("### 📝 실행 방법")
    st.markdown("""
    1. **"프롬프트 복사"** 버튼 클릭
    2. Claude Code 앱 열기 (`cd longform && claude`)
    3. 프롬프트 붙여넣기
    4. 완료 후 **"결과 확인"** 버튼 클릭
    """)

    # 버튼들
    copy_col1, copy_col2, copy_col3 = st.columns([2, 2, 1])

    with copy_col1:
        if st.button("📋 프롬프트 복사", type="primary", use_container_width=True, key="copy_prompt_batch_agent"):
            if prompt_text:
                try:
                    import pyperclip
                    pyperclip.copy(prompt_text)
                    st.success("✅ 클립보드에 복사되었습니다!")
                    st.toast("Claude Code 앱에 붙여넣기하세요!")
                except ImportError:
                    st.warning("pyperclip 패키지가 설치되지 않았습니다.")
                    with st.expander("프롬프트 직접 복사", expanded=True):
                        st.code(prompt_text, language="markdown")
                except Exception as e:
                    st.error(f"복사 실패: {e}")
                    with st.expander("프롬프트 직접 복사", expanded=True):
                        st.code(prompt_text, language="markdown")
            else:
                st.error("프롬프트를 찾을 수 없습니다.")

    with copy_col2:
        if st.button("🔄 결과 확인 + Bundle 병합", use_container_width=True, key="check_result_batch_agent"):
            if scenes_path and os.path.exists(scenes_path):
                try:
                    # v13.13: Bundle 병합 적용
                    from utils.claude_code_runner import sync_claude_code_results_with_bundle_merge
                    video_path = str(Path(scenes_path).parent.parent)

                    with st.spinner("Bundle 병합 적용 중..."):
                        merge_result = sync_claude_code_results_with_bundle_merge(video_path)

                    if merge_result.get('success'):
                        reload_scenes = merge_result.get('scenes', [])
                        merged_count = merge_result.get('merged_count', 0)

                        if reload_scenes:
                            stats = check_scenes_analysis_status(reload_scenes)

                            if stats['background_prompt_en'] > 0:
                                st.success(f"✅ 분석 결과 감지! {stats['background_prompt_en']}/{stats['total']} 씬 완료 (Bundle 병합: {merged_count}개)")

                                # 세션 업데이트 (sync_data 적용)
                                sync_data = merge_result.get('sync_data', {})
                                for key, value in sync_data.items():
                                    st.session_state[key] = value

                                st.session_state['scenes'] = reload_scenes
                                st.session_state['_agent_analysis_stats'] = stats
                                st.session_state['claude_code_agent_mode'] = False  # 에이전트 모드 해제

                                st.info("💡 '페이지 새로고침' 버튼을 클릭하면 분석 결과가 적용됩니다.")

                                if st.button("🔄 페이지 새로고침", key="refresh_page_after_agent"):
                                    st.rerun()
                            else:
                                st.warning("아직 분석 결과가 없습니다. Claude Code에서 실행을 완료해주세요.")

                                # 파일 수정 시간 표시
                                mtime = os.path.getmtime(scenes_path)
                                mtime_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(mtime))
                                st.caption(f"📅 마지막 수정: {mtime_str}")
                        else:
                            st.warning("씬 데이터가 비어있습니다.")
                    else:
                        st.error(f"Bundle 병합 실패: {merge_result.get('error', '알 수 없는 오류')}")
                        # 폴백: 기존 방식
                        with open(scenes_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        reload_scenes = data.get('scenes', data) if isinstance(data, dict) else data
                        if reload_scenes:
                            stats = check_scenes_analysis_status(reload_scenes)
                            st.session_state['scenes'] = reload_scenes
                            st.info(f"폴백: {stats['background_prompt_en']}/{stats['total']} 씬")

                except ImportError:
                    # 폴백: 기존 방식 (bundle merge 없이)
                    try:
                        with open(scenes_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        reload_scenes = data.get('scenes', data) if isinstance(data, dict) else data
                        if reload_scenes:
                            stats = check_scenes_analysis_status(reload_scenes)
                            if stats['background_prompt_en'] > 0:
                                st.success(f"✅ {stats['background_prompt_en']}/{stats['total']} 씬 완료")
                                st.session_state['scenes'] = reload_scenes
                                st.session_state['claude_code_agent_mode'] = False
                            else:
                                st.warning("아직 분석 결과가 없습니다.")
                    except Exception as e:
                        st.error(f"파일 로드 실패: {e}")
                except Exception as e:
                    st.error(f"오류 발생: {e}")
            else:
                st.error("scenes.json 파일을 찾을 수 없습니다.")

    with copy_col3:
        if st.button("📂", help="폴더 열기", key="open_folder_batch_agent"):
            try:
                if prompt_file and os.path.exists(prompt_file):
                    os.startfile(os.path.dirname(prompt_file))
                elif scenes_path and os.path.exists(scenes_path):
                    os.startfile(os.path.dirname(scenes_path))
            except Exception as e:
                st.error(f"폴더 열기 실패: {e}")

    # 프롬프트 미리보기
    if prompt_text:
        with st.expander("📝 프롬프트 미리보기", expanded=False):
            st.code(prompt_text, language="markdown")

    # Claude Code 실행 명령어
    st.markdown("### 💻 Claude Code 실행")
    st.code("cd C:\\Users\\KIMJAEHEON\\longform\nclaude", language="bash")

    # 파일 경로 표시
    if prompt_file:
        st.caption(f"📄 프롬프트 파일: `{prompt_file}`")
    if scenes_path:
        st.caption(f"📁 분석 대상: `{scenes_path}`")

    # 에이전트 모드 닫기 버튼
    st.markdown("---")
    if st.button("❌ 닫기 (에이전트 모드 취소)", key="close_agent_mode"):
        st.session_state['claude_code_agent_mode'] = False
        st.rerun()


def check_api_availability() -> dict:
    """각 AI API의 사용 가능 여부 확인"""
    availability = {}

    # Anthropic
    try:
        import anthropic
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        availability["anthropic"] = {
            "installed": True,
            "api_key": bool(api_key),
            "status": "✅" if api_key else "⚠️ API 키 필요"
        }
    except ImportError:
        availability["anthropic"] = {
            "installed": False,
            "api_key": False,
            "status": "❌ 패키지 없음"
        }

    # Google Gemini
    try:
        import google.generativeai
        api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
        availability["gemini"] = {
            "installed": True,
            "api_key": bool(api_key),
            "status": "✅" if api_key else "⚠️ API 키 필요"
        }
    except ImportError:
        availability["gemini"] = {
            "installed": False,
            "api_key": False,
            "status": "❌ pip install google-generativeai"
        }

    # OpenAI
    try:
        import openai
        api_key = os.environ.get("OPENAI_API_KEY")
        availability["openai"] = {
            "installed": True,
            "api_key": bool(api_key),
            "status": "✅" if api_key else "⚠️ API 키 필요"
        }
    except ImportError:
        availability["openai"] = {
            "installed": False,
            "api_key": False,
            "status": "❌ 패키지 없음"
        }

    return availability

# 페이지 설정
st.set_page_config(
    page_title="씬 분석",
    page_icon="🎬",
    layout="wide"
)

# ============================================================
# ⭐ 사용자 설정 복원 (v1.0 - 영속성)
# ============================================================
def _init_persistent_settings():
    """저장된 설정 복원 (settings_manager 사용)"""
    # 묶음 크기 복원
    saved_bundle_size = get_setting(PAGE_SETTINGS_NAME, "srt_bundle_size")
    if saved_bundle_size is not None and "srt_bundle_size" not in st.session_state:
        st.session_state["srt_bundle_size"] = saved_bundle_size

    # AI 모델 복원 (하이브리드 변환)
    saved_ai_model = get_setting(PAGE_SETTINGS_NAME, "hybrid_ai_model")
    if saved_ai_model is not None and "hybrid_ai_model" not in st.session_state:
        st.session_state["hybrid_ai_model"] = saved_ai_model

    # SRT 분석 모델 복원
    saved_srt_model = get_setting(PAGE_SETTINGS_NAME, "srt_model_model")
    if saved_srt_model is not None and "srt_model_model" not in st.session_state:
        st.session_state["srt_model_model"] = saved_srt_model

    # 프롬프트 생성 옵션 복원
    saved_generate_prompts = get_setting(PAGE_SETTINGS_NAME, "srt_generate_prompts")
    if saved_generate_prompts is not None and "srt_generate_prompts" not in st.session_state:
        st.session_state["srt_generate_prompts"] = saved_generate_prompts

_init_persistent_settings()

render_project_sidebar()
show_api_status_sidebar()

# === 사이드바: 프롬프트 설정 ===
with st.sidebar:
    st.markdown("---")
    st.markdown("### ⚙️ AI 프롬프트 설정")

    template_manager = get_template_manager()

    with st.expander("🔧 프롬프트 템플릿 편집", expanded=False):
        # 템플릿 선택
        scene_templates = template_manager.get_templates_by_category("scene_analysis")
        char_template = template_manager.get_template("character_extraction")
        img_template = template_manager.get_template("image_prompt_generation")

        template_options = {t.name: t.id for t in scene_templates}
        if char_template:
            template_options[char_template.name] = char_template.id
        if img_template:
            template_options[img_template.name] = img_template.id

        selected_name = st.selectbox(
            "템플릿 선택",
            list(template_options.keys()),
            key="template_select_sidebar"
        )

        template_id = template_options[selected_name]
        template = template_manager.get_template(template_id)

        if template:
            # 현재 상태 표시
            if template.is_default:
                st.info("📋 기본 템플릿 사용 중")
            else:
                st.success("✏️ 커스텀 템플릿")
                st.caption(f"수정: {template.updated_at[:10] if template.updated_at else ''}")

            # 프롬프트 편집
            new_prompt = st.text_area(
                "프롬프트",
                value=template.prompt,
                height=300,
                key=f"prompt_edit_{template_id}"
            )

            col1, col2 = st.columns(2)

            with col1:
                if st.button("💾 저장", key=f"save_template_{template_id}", use_container_width=True):
                    if template_manager.update_template(template_id, new_prompt):
                        reload_template_manager()  # 싱글톤 강제 리로드
                        st.success("저장됨! 다음 분석부터 적용됩니다.")
                        st.rerun()

            with col2:
                if st.button("🔄 기본값", key=f"reset_template_{template_id}", use_container_width=True):
                    if template_manager.reset_to_default(template_id):
                        reload_template_manager()  # 싱글톤 강제 리로드
                        st.success("기본값으로 복원됨!")
                        st.rerun()

if not ensure_project_selected():
    st.stop()

project_path = get_current_project()
project_config = get_current_project_config()


# ═══════════════════════════════════════════════════════════════
# v1.1: 채널-영상별 설정 로드
# ═══════════════════════════════════════════════════════════════
def _extract_channel_video_from_path(path: Path) -> tuple:
    """
    프로젝트 경로에서 채널과 영상 이름 추출

    경로 형식: data/projects/{timestamp}_{channel}/videos/{video_name}
    """
    try:
        parts = path.parts
        if 'videos' in parts:
            videos_idx = parts.index('videos')
            # channel: projects 바로 뒤 폴더에서 타임스탬프 제거
            channel = path.name  # 기본값
            if videos_idx >= 2:
                project_folder = parts[videos_idx - 1]
                # 타임스탬프 패턴 제거 (YYYYMMDD_HHMMSS_)
                if len(project_folder) > 16 and project_folder[8] == '_' and project_folder[15] == '_':
                    channel = project_folder[16:]
                else:
                    channel = project_folder
            # video: videos 폴더 바로 뒤
            if videos_idx + 1 < len(parts):
                video = parts[videos_idx + 1]
            else:
                video = path.name
            return channel, video
    except Exception as e:
        print(f"[씬 분석] 경로 파싱 오류: {e}")
    return path.name, path.name

_current_channel, _current_video = _extract_channel_video_from_path(Path(project_path))
_saved_scene_settings = get_scene_analysis_settings(_current_channel, _current_video)
if _saved_scene_settings:
    print(f"[씬 분석] 저장된 설정 로드: {_current_channel}/{_current_video} - {list(_saved_scene_settings.keys())}")


st.title("🎬 3.5단계: 씬 분석")
st.caption("스크립트를 씬 단위로 분할하고 연출가이드 생성")

# API 키 확인
if not require_api_key("ANTHROPIC_API_KEY", "Anthropic API"):
    st.stop()

st.divider()

# ═══════════════════════════════════════════════════════════════
# 동기화된 스크립트 확인 (스크립트 생성 페이지에서 저장한 최신 데이터)
# ⭐ 성능 최적화: 캐싱된 함수 사용
# ═══════════════════════════════════════════════════════════════
synced_script, synced_language = _cached_sync_load_script(str(project_path))
synced_info = get_synced_script_info()

# 동기화된 스크립트가 있으면 언어 기본값을 동기화
if synced_script and synced_info.get("has_content"):
    default_lang_index = 0 if synced_language == "ko" else 1
    st.info(f"📝 스크립트 탭에서 저장된 **{synced_info.get('language_name', synced_language)}** 스크립트가 있습니다 ({synced_info.get('char_count', 0):,}자)")
else:
    default_lang_index = 0 if project_config.get("language") == "ko" else 1

# v1.1: 저장된 언어 설정 우선 적용
_saved_language = _saved_scene_settings.get("language")
if _saved_language:
    default_lang_index = 0 if _saved_language == "ko" else 1

# 언어 선택
_language_options = ["ko", "ja"]
language = st.selectbox(
    "언어",
    _language_options,
    format_func=lambda x: "한국어" if x == "ko" else "일본어",
    index=default_lang_index,
    key="scene_analysis_language"
)

# v1.1: 언어 설정 저장 (변경 시에만)
if language != _saved_scene_settings.get("language"):
    set_analysis_language(_current_channel, _current_video, language)

# 스크립트 로드 (동기화 우선, 없으면 기존 파일)
if synced_script and synced_language == language:
    auto_script = synced_script
elif synced_script:
    # 동기화된 스크립트가 있지만 언어가 다른 경우
    auto_script = synced_script
    if language != synced_language:
        st.warning(f"⚠️ 저장된 스크립트는 **{synced_info.get('language_name')}**입니다. 언어 설정을 확인하세요.")
else:
    # 동기화된 스크립트가 없으면 기존 파일에서 로드 (⭐ 캐싱 적용)
    auto_script = _cached_load_script(project_path, language, "final") or _cached_load_script(project_path, language, "draft")

# 탭 구성 (v2.5: TTS+AI 타임스탬프 탭 추가)
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📝 스크립트 입력",
    "🎬 씬 분석",
    "👤 캐릭터",
    "📋 결과",
    "⚙️ 프롬프트 설정",
    "🎤 TTS+AI 타임스탬프"
])

# 세션에 스크립트 저장용 (동기화된 스크립트가 있으면 항상 최신으로 업데이트)
if synced_script:
    # 동기화된 스크립트가 있으면 항상 사용 (스크립트 생성에서 새로 저장된 것)
    st.session_state["scene_analysis_script"] = auto_script
elif "scene_analysis_script" not in st.session_state:
    st.session_state["scene_analysis_script"] = auto_script

# === 탭 1: 스크립트 입력 ===
with tab1:
    st.subheader("📝 분석할 스크립트")

    st.info("씬 분석에 사용할 스크립트를 선택하세요. 이전 단계에서 가져오거나 직접 입력할 수 있습니다.")

    # 입력 소스 선택 (v3.14: SRT 옵션 추가)
    # v1.1: 저장된 설정 적용
    _script_source_options = [
        "🔄 자동: 스크립트 탭에서 가져오기",
        "✏️ 수동: 직접 입력",
        "📁 수동: 파일 업로드",
        "🎬 SRT: 자막 파일 업로드"
    ]
    _script_source_keys = ["auto", "manual", "file", "srt"]
    _saved_script_source = _saved_scene_settings.get("script_source", "auto")
    _script_source_default_idx = _script_source_keys.index(_saved_script_source) if _saved_script_source in _script_source_keys else 0

    script_source = st.radio(
        "스크립트 소스",
        _script_source_options,
        horizontal=True,
        index=_script_source_default_idx,
        key="scene_script_source"
    )

    # v1.1: 스크립트 소스 설정 저장
    _current_script_source_key = _script_source_keys[_script_source_options.index(script_source)]
    if _current_script_source_key != _saved_script_source:
        set_script_source(_current_channel, _current_video, _current_script_source_key)

    script = None
    srt_scenes = None  # SRT 파싱 결과 저장용

    # === 자동 모드 ===
    if "자동" in script_source:
        if auto_script:
            script = auto_script
            st.success(f"✅ 스크립트 탭에서 가져옴 ({len(auto_script):,}자)")

            with st.expander("📋 스크립트 미리보기", expanded=False):
                st.text_area("내용", auto_script[:3000], height=300, disabled=True, key="auto_script_preview")
                if len(auto_script) > 3000:
                    st.caption(f"... 외 {len(auto_script) - 3000}자 더 있음")
        else:
            st.warning("⚠️ 스크립트 탭에 저장된 스크립트가 없습니다.")
            st.info("3단계에서 스크립트를 생성하거나, 수동 입력을 사용하세요.")

    # === 수동: 직접 입력 ===
    elif "직접 입력" in script_source:
        manual_script = st.text_area(
            "스크립트 직접 입력",
            height=400,
            placeholder="분석할 스크립트를 여기에 입력하세요...\n\n안녕하세요, 오늘은 세금 절세 방법에 대해...",
            key="scene_manual_script"
        )

        if manual_script and manual_script.strip():
            script = manual_script.strip()
            st.success(f"✅ {len(script):,}자 입력됨")

    # === 수동: 파일 업로드 ===
    elif "파일 업로드" in script_source and "SRT" not in script_source:
        uploaded_file = st.file_uploader(
            "스크립트 파일 선택",
            type=["txt", "docx"],
            key="scene_script_file"
        )

        if uploaded_file:
            try:
                if uploaded_file.name.endswith('.txt'):
                    script = uploaded_file.read().decode('utf-8')
                elif uploaded_file.name.endswith('.docx'):
                    from components.input_source_selector import read_docx_file
                    script = read_docx_file(uploaded_file)

                st.success(f"✅ 파일 로드 완료: {uploaded_file.name} ({len(script):,}자)")

                with st.expander("📋 파일 내용 미리보기"):
                    st.text_area("내용", script[:2000], height=200, disabled=True, key="file_script_preview")
            except Exception as e:
                st.error(f"파일 읽기 실패: {e}")

    # === SRT: 자막 파일 업로드 (v3.14 새로 추가) ===
    elif "SRT" in script_source:
        st.markdown("##### 🎬 SRT 자막 파일")
        st.caption("Vrew 등에서 생성된 SRT 파일을 업로드하세요. 시간 코드 기반으로 씬이 자동 구분됩니다.")

        uploaded_srt = st.file_uploader(
            "SRT 파일 선택",
            type=["srt"],
            help="SRT 자막 파일을 업로드하세요 (.srt)",
            key="scene_srt_file"
        )

        if uploaded_srt:
            # SRT 파싱 옵션
            srt_col1, srt_col2 = st.columns(2)

            with srt_col1:
                merge_short = st.checkbox(
                    "짧은 씬 자동 병합",
                    value=False,
                    help="지정한 시간 미만의 짧은 씬을 인접 씬과 병합합니다",
                    key="srt_merge_short"
                )

            with srt_col2:
                if merge_short:
                    min_duration = st.slider(
                        "최소 씬 길이 (초)",
                        min_value=1.0,
                        max_value=10.0,
                        value=3.0,
                        step=0.5,
                        key="srt_min_duration"
                    )
                else:
                    min_duration = 3.0

            # SRT 파싱
            try:
                from utils.srt_parser import (
                    SRTParser,
                    parse_srt_content,
                    convert_srt_to_scene_structure,
                    prepare_srt_for_batch_analysis
                )

                # 파일 내용 읽기 (여러 인코딩 시도)
                srt_content = None
                for enc in ['utf-8-sig', 'utf-8', 'cp949', 'euc-kr']:
                    try:
                        uploaded_srt.seek(0)
                        srt_content = uploaded_srt.read().decode(enc)
                        break
                    except UnicodeDecodeError:
                        continue

                if srt_content is None:
                    st.error("❌ 파일 인코딩을 인식할 수 없습니다.")
                else:
                    # 유효성 검사
                    is_valid, error_msg, scene_count = SRTParser.validate_srt(srt_content)

                    if not is_valid:
                        st.error(f"❌ SRT 파싱 오류: {error_msg}")
                    else:
                        # 파싱
                        srt_scenes = parse_srt_content(srt_content, merge_short=merge_short, min_duration=min_duration)

                        if srt_scenes:
                            # 전체 길이 계산
                            _, total_duration = SRTParser.get_total_duration(srt_scenes)

                            st.success(f"✅ SRT 파싱 완료: **{len(srt_scenes)}개 씬** (총 길이: {total_duration})")

                            # 통계
                            stat_col1, stat_col2, stat_col3, stat_col4 = st.columns(4)
                            with stat_col1:
                                st.metric("씬 수", f"{len(srt_scenes)}개")
                            with stat_col2:
                                total_chars = sum(len(s.get('narration', '')) for s in srt_scenes)
                                st.metric("총 글자수", f"{total_chars:,}자")
                            with stat_col3:
                                avg_duration = sum(s.get('duration', 0) for s in srt_scenes) / len(srt_scenes)
                                st.metric("평균 길이", f"{avg_duration:.1f}초")
                            with stat_col4:
                                st.metric("전체 길이", total_duration)

                            # 파싱 결과 미리보기
                            with st.expander("📋 SRT 파싱 결과 미리보기", expanded=False):
                                for scene in srt_scenes[:10]:  # 처음 10개만 표시
                                    duration_badge = f"({scene['duration']:.1f}초)"
                                    char_warning = " ⚠️" if len(scene['narration']) > 250 else ""
                                    st.markdown(f"""
                                    **씬 {scene['scene_id']}** `{scene['start_time']} → {scene['end_time']}` {duration_badge}{char_warning}
                                    > {scene['narration'][:100]}{'...' if len(scene['narration']) > 100 else ''}
                                    """)

                                if len(srt_scenes) > 10:
                                    st.caption(f"... 외 {len(srt_scenes) - 10}개 씬")

                            # 전체 스크립트 생성 (기존 로직과 호환)
                            script = SRTParser.to_script_format(srt_scenes, include_time=True)

                            # 세션에 SRT 씬 데이터 저장
                            st.session_state["srt_scenes"] = srt_scenes
                            st.session_state["srt_source"] = True

                        else:
                            st.warning("⚠️ 파싱된 씬이 없습니다. SRT 파일 형식을 확인하세요.")

            except Exception as e:
                st.error(f"SRT 파싱 오류: {e}")
                import traceback
                with st.expander("오류 상세"):
                    st.code(traceback.format_exc())

    # 스크립트 통계
    if script:
        st.session_state["scene_analysis_script"] = script

        st.markdown("---")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("글자 수", f"{len(script):,}자")
        with col2:
            st.metric("예상 길이", f"~{len(script) // 250}분")
        with col3:
            st.metric("문단 수", script.count("\n\n") + 1)
    else:
        st.session_state["scene_analysis_script"] = None

# === 탭 2: 씬 분석 ===
with tab2:
    st.subheader("🎬 씬 분석")

    # SRT 데이터가 있는지 확인
    has_srt_data = st.session_state.get("srt_scenes") is not None and st.session_state.get("srt_source", False)

    # ⭐ 분석 방식 선택 (자동/수동/SRT)
    analysis_options = ["auto", "manual"]
    analysis_format_func = {
        "auto": "🤖 AI 자동 분석",
        "manual": "📝 수동 입력 (외부 AI 결과)"
    }

    # SRT 데이터가 있으면 SRT 옵션 추가
    if has_srt_data:
        analysis_options.append("srt_direct")
        analysis_format_func["srt_direct"] = "🎬 SRT 직접 적용"

    # v1.1: 저장된 분석 방식 설정 적용
    _saved_analysis_method = _saved_scene_settings.get("analysis_method", "auto")
    _analysis_default_idx = 0
    if _saved_analysis_method in analysis_options:
        _analysis_default_idx = analysis_options.index(_saved_analysis_method)

    analysis_mode = st.radio(
        "분석 방식",
        options=analysis_options,
        format_func=lambda x: analysis_format_func[x],
        horizontal=True,
        index=_analysis_default_idx,
        help="SRT 파일을 업로드했다면 'SRT 직접 적용'으로 시간 코드 기반 씬 구분을 유지할 수 있습니다.",
        key="scene_analysis_mode"
    )

    # v1.1: 분석 방식 설정 저장
    if analysis_mode != _saved_analysis_method:
        set_analysis_method(_current_channel, _current_video, analysis_mode)

    # SRT 안내 메시지
    if has_srt_data and analysis_mode != "srt_direct":
        srt_scene_count = len(st.session_state.get("srt_scenes", []))
        st.info(f"💡 SRT 파일에서 **{srt_scene_count}개 씬**이 감지되었습니다. 'SRT 직접 적용'을 선택하면 시간 코드가 유지됩니다.")

    st.divider()

    # ═══════════════════════════════════════════════════════════════════
    # 수동 입력 모드
    # ═══════════════════════════════════════════════════════════════════
    if analysis_mode == "manual":
        st.markdown("#### 📝 외부 AI 분석 결과 입력")

        # 사용 방법 안내
        with st.expander("💡 사용 방법", expanded=False):
            st.markdown("""
            **1단계**: 외부 AI (ChatGPT, Claude, Gemini 등)에 아래 프롬프트와 스크립트를 입력하세요.

            **2단계**: AI가 생성한 JSON 결과를 복사하세요.

            **3단계**: 아래 입력창에 붙여넣고 "적용" 버튼을 누르세요.
            """)

            st.markdown("---")
            st.markdown("**📋 외부 AI용 프롬프트 (복사해서 사용)**")

            prompt_template = '''다음 스크립트를 씬 단위로 분석해서 JSON 형식으로 출력해주세요.

각 씬은 다음 정보를 포함해야 합니다:
- scene_id: 씬 번호 (1부터 시작)
- script_text: 해당 씬의 대사/나레이션 텍스트
- duration_estimate: 예상 재생 시간 (초)
- characters: 등장 캐릭터 목록
- visual_elements: 시각적 요소 목록
- mood: 분위기 (exciting, calm, dramatic 등)
- image_prompt: 이미지 생성용 영어 프롬프트

출력 형식:
```json
{
  "scenes": [
    {
      "scene_id": 1,
      "script_text": "...",
      "duration_estimate": 10,
      "characters": ["캐릭터1"],
      "visual_elements": ["요소1", "요소2"],
      "mood": "exciting",
      "image_prompt": "A dramatic scene showing..."
    }
  ],
  "characters": [
    {
      "name": "캐릭터1",
      "description": "캐릭터 설명",
      "visual_prompt": "캐릭터 외모 프롬프트"
    }
  ]
}
```

스크립트:
[여기에 스크립트 붙여넣기]'''

            st.code(prompt_template, language="text")
            st.caption("💡 위 프롬프트를 복사(Ctrl+C)하여 외부 AI에 붙여넣으세요.")

        st.divider()

        # JSON 입력 영역
        st.markdown("#### 📥 JSON 결과 입력")

        json_input = st.text_area(
            label="JSON 입력",
            height=400,
            placeholder='''{
  "scenes": [
    {
      "scene_id": 1,
      "script_text": "씬 1의 텍스트...",
      "duration_estimate": 10,
      "characters": [],
      "visual_elements": ["요소1"],
      "mood": "exciting",
      "image_prompt": "A dramatic scene..."
    }
  ],
  "characters": []
}''',
            help="외부 AI에서 생성한 JSON 결과를 붙여넣으세요.",
            label_visibility="collapsed",
            key="manual_json_input"
        )

        # 검증 및 적용 버튼
        col1, col2, col3 = st.columns([1, 1, 2])

        with col1:
            validate_btn = st.button("✅ JSON 검증", type="secondary", use_container_width=True, key="validate_json_btn")

        with col2:
            apply_btn = st.button("🚀 적용하기", type="primary", use_container_width=True, key="apply_json_btn")

        # JSON 검증 함수
        def validate_scene_json(json_str: str):
            """씬 분석 JSON 검증 및 정규화"""
            import json as json_module

            # 빈 입력 체크
            if not json_str or not json_str.strip():
                return False, {}, "입력이 비어있습니다."

            # ```json ... ``` 블록 추출
            cleaned = json_str.strip()

            if "```json" in cleaned:
                start = cleaned.find("```json") + 7
                end = cleaned.rfind("```")
                if end > start:
                    cleaned = cleaned[start:end].strip()
                else:
                    cleaned = cleaned[start:].strip()
            elif "```" in cleaned:
                start = cleaned.find("```") + 3
                end = cleaned.rfind("```")
                if end > start:
                    cleaned = cleaned[start:end].strip()

            # JSON 파싱 시도
            try:
                result = json_module.loads(cleaned)
            except json_module.JSONDecodeError as e:
                return False, {}, f"JSON 파싱 오류: {e}"

            # 필수 필드 검증
            if not isinstance(result, dict):
                return False, {}, "최상위가 객체({})여야 합니다."

            if "scenes" not in result:
                return False, {}, "'scenes' 필드가 없습니다."

            if not isinstance(result["scenes"], list):
                return False, {}, "'scenes'는 배열이어야 합니다."

            # 각 씬 검증 및 정규화
            normalized_scenes = []

            for i, scene in enumerate(result["scenes"]):
                if not isinstance(scene, dict):
                    return False, {}, f"씬 {i+1}이 객체가 아닙니다."

                # 필수 필드 체크 및 기본값 설정
                # v3.36: script_ko 우선 체크 추가
                script_text = scene.get("script_ko", scene.get("script_text", scene.get("text", scene.get("narration", ""))))

                if not script_text:
                    return False, {}, f"씬 {i+1}에 'script_text'가 없습니다."

                normalized_scene = {
                    "scene_id": scene.get("scene_id", i + 1),
                    "script_text": script_text,
                    "duration_estimate": scene.get("duration_estimate", scene.get("duration", 10)),
                    "characters": scene.get("characters", []),
                    "visual_elements": scene.get("visual_elements", scene.get("visuals", [])),
                    "mood": scene.get("mood", "neutral"),
                    "image_prompt": scene.get("image_prompt", scene.get("image_prompt_en", "")),
                    "direction_guide": scene.get("direction_guide", ""),
                    "camera_suggestion": scene.get("camera_suggestion", ""),
                    "char_count": len(script_text),
                }

                normalized_scenes.append(normalized_scene)

            # 캐릭터 정규화
            characters = result.get("characters", [])
            normalized_characters = []

            for char in characters:
                if isinstance(char, str):
                    normalized_characters.append({
                        "name": char,
                        "name_ko": char,
                        "description": "",
                        "visual_prompt": ""
                    })
                elif isinstance(char, dict):
                    normalized_characters.append({
                        "name": char.get("name", char.get("name_ko", "Unknown")),
                        "name_ko": char.get("name_ko", char.get("name", "")),
                        "name_en": char.get("name_en", ""),
                        "description": char.get("description", ""),
                        "visual_prompt": char.get("visual_prompt", char.get("character_prompt", "")),
                        "role": char.get("role", "등장인물"),
                    })

            normalized_result = {
                "scenes": normalized_scenes,
                "characters": normalized_characters
            }

            return True, normalized_result, ""

        # JSON 검증 버튼 클릭
        if validate_btn and json_input:
            is_valid, result, error = validate_scene_json(json_input)

            if is_valid:
                st.success(f"✅ JSON 유효! 씬 {len(result.get('scenes', []))}개, 캐릭터 {len(result.get('characters', []))}개 발견")

                # 미리보기
                with st.expander("📊 미리보기", expanded=True):
                    for scene in result.get("scenes", [])[:3]:
                        # v3.36: script_ko 우선 체크
                        _script = scene.get('script_ko') or scene.get('script_text', '')
                        st.markdown(f"**씬 {scene.get('scene_id')}**: {_script[:100]}...")

                    if len(result.get("scenes", [])) > 3:
                        st.caption(f"... 외 {len(result.get('scenes', [])) - 3}개 씬")
            else:
                st.error(f"❌ JSON 오류: {error}")
                st.info("💡 JSON 형식을 확인해주세요. 쉼표, 따옴표, 괄호가 올바른지 확인하세요.")

        # 적용 버튼 클릭
        if apply_btn and json_input:
            is_valid, result, error = validate_scene_json(json_input)

            if is_valid:
                # 결과 저장 (파일)
                analysis_dir = project_path / "analysis"
                analysis_dir.mkdir(parents=True, exist_ok=True)

                # 🔴 저장 전 검증 및 자동 수정 (background_prompt_en 불일치 해결)
                scenes_to_save = result.get("scenes", [])
                if scenes_to_save and SCENE_VALIDATOR_AVAILABLE:
                    scenes_to_save = validate_scenes_before_save(scenes_to_save, verbose=True)
                    result["scenes"] = scenes_to_save

                # character_prompt -> characters 후처리 동기화
                try:
                    from utils.character_sync import sync_all_scenes_characters, update_characters_json
                    scenes_to_save, _sync_cnt = sync_all_scenes_characters(scenes_to_save)
                    if _sync_cnt > 0:
                        print(f"[후처리] {_sync_cnt}개 씬 characters 배열 동기화")
                        result["scenes"] = scenes_to_save
                except Exception as _e:
                    print(f"[후처리] 동기화 오류 (무시): {_e}")

                with open(analysis_dir / "scenes.json", "w", encoding="utf-8") as f:
                    json.dump(scenes_to_save, f, ensure_ascii=False, indent=2)

                with open(analysis_dir / "characters.json", "w", encoding="utf-8") as f:
                    json.dump(result.get("characters", []), f, ensure_ascii=False, indent=2)

                # characters.json에 씬 기반 캐릭터 추가
                try:
                    from utils.character_sync import update_characters_json as _update_cj
                    _update_cj(scenes_to_save, analysis_dir / "characters.json")
                except Exception:
                    pass

                with open(analysis_dir / "full_analysis.json", "w", encoding="utf-8") as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)

                # 세션에도 저장
                st.session_state["scene_analysis_result"] = result
                st.session_state["scenes"] = result.get("scenes", [])
                st.session_state["characters"] = result.get("characters", [])
                st.session_state["scene_characters"] = result.get("characters", [])
                st.session_state["extracted_characters"] = result.get("characters", [])
                st.session_state["analysis_source"] = "manual"  # 수동 입력 표시

                # 다른 페이지 캐시 클리어 (Problem 56)
                clear_scene_cache(str(project_path))
                # 캐릭터 관리 페이지 동기화 플래그 리셋 (재방문 시 재동기화)
                st.session_state.pop(f"char_mgmt_initialized_{project_path}", None)

                st.success(f"✅ 적용 완료! 씬 {len(result.get('scenes', []))}개가 로드되었습니다.")
                st.balloons()

                time.sleep(1)
                st.rerun()
            else:
                st.error(f"❌ 적용 실패: {error}")

        # 현재 로드된 씬 표시
        analysis_path = project_path / "analysis" / "full_analysis.json"
        if analysis_path.exists():
            st.divider()
            st.markdown("#### 📊 현재 로드된 씬")

            with open(analysis_path, "r", encoding="utf-8") as f:
                saved_analysis = json.load(f)

            source = st.session_state.get("analysis_source", "auto")
            source_label = "📝 수동 입력" if source == "manual" else "🤖 AI 자동 분석"

            col1, col2, col3 = st.columns(3)
            col1.metric("씬 수", len(saved_analysis.get("scenes", [])))
            col2.metric("캐릭터 수", len(saved_analysis.get("characters", [])))
            col3.metric("소스", source_label)

    # ═══════════════════════════════════════════════════════════════════
    # SRT 직접 적용 모드 (v3.14 새로 추가)
    # ═══════════════════════════════════════════════════════════════════
    elif analysis_mode == "srt_direct":
        st.markdown("#### 🎬 SRT 기반 씬 직접 적용")

        srt_scenes = st.session_state.get("srt_scenes", [])

        if not srt_scenes:
            st.warning("⚠️ SRT 데이터가 없습니다. '스크립트 입력' 탭에서 SRT 파일을 업로드하세요.")
        else:
            from utils.srt_parser import (
                SRTParser, convert_srt_to_scene_structure,
                create_bundles, get_bundle_primary_scenes,
                apply_bundle_analysis_result, get_bundle_summary
            )

            st.info(f"""
            **SRT 직접 적용이란?**
            - SRT 파일의 **시간 코드(타임스탬프)**를 씬 구분으로 사용
            - AI 씬 분할 없이 SRT 자막 단위 그대로 적용
            - 이미지/캐릭터 프롬프트는 별도 AI 분석으로 생성 가능

            **현재 SRT 데이터**: {len(srt_scenes)}개 씬
            """)

            # SRT 씬 미리보기 (묶음 표시 포함)
            with st.expander("📋 적용될 씬 목록", expanded=True):
                # 미리보기용 임시 묶음 계산
                preview_bundle_size = st.session_state.get("srt_bundle_size", 2) or 2
                current_bundle = 1

                for i, scene in enumerate(srt_scenes[:10]):
                    # 묶음 번호 계산
                    if preview_bundle_size > 1:
                        bundle_num = (i // preview_bundle_size) + 1
                        is_bundle_start = (i % preview_bundle_size == 0)
                        bundle_indicator = f"📦{bundle_num}" if is_bundle_start else "  └─"
                    else:
                        bundle_indicator = ""

                    char_count = len(scene.get('narration', ''))
                    char_warning = " ⚠️" if char_count > 250 else ""

                    if preview_bundle_size > 1:
                        st.markdown(f"""
                        {bundle_indicator} **씬 {scene['scene_id']}** `{scene['start_time']} → {scene['end_time']}` ({scene['duration']:.1f}초){char_warning}
                        > {scene['narration'][:80]}{'...' if len(scene['narration']) > 80 else ''}
                        """)
                    else:
                        st.markdown(f"""
                        **씬 {scene['scene_id']}** `{scene['start_time']} → {scene['end_time']}` ({scene['duration']:.1f}초){char_warning}
                        > {scene['narration'][:80]}{'...' if len(scene['narration']) > 80 else ''}
                        """)

                if len(srt_scenes) > 10:
                    st.caption(f"... 외 {len(srt_scenes) - 10}개 씬")

            st.divider()

            # 프롬프트 생성 옵션
            st.markdown("##### ✨ 프롬프트 생성 옵션")

            generate_prompts = st.checkbox(
                "AI로 이미지/캐릭터 프롬프트 자동 생성",
                value=True,
                help="각 씬에 대해 AI가 이미지 프롬프트와 캐릭터 프롬프트를 생성합니다.",
                key="srt_generate_prompts"
            )

            # ═══════════════════════════════════════════════════════════════════
            # SRT 프롬프트 설정 UI (프롬프트 생성 시에만 표시)
            # ═══════════════════════════════════════════════════════════════════
            if generate_prompts:
                from core.prompt.prompt_template_manager import get_template_manager

                with st.expander("📝 SRT 분석 프롬프트 설정", expanded=False):
                    template_manager = get_template_manager()

                    # SRT 템플릿 목록 가져오기
                    srt_templates = template_manager.get_srt_templates()

                    if not srt_templates:
                        st.info("기본 SRT 분석 프롬프트를 사용합니다.")
                    else:
                        # ============================================================
                        # 통합 프롬프트 편집기 (v2.6 업데이트)
                        # ============================================================
                        st.subheader("📝 프롬프트 편집")
                        st.caption("모든 SRT 분석 프롬프트를 확인하고 수정할 수 있습니다.")

                        # 편집할 프롬프트 선택 드롭다운
                        all_srt_prompts = template_manager.get_all_srt_prompts_for_editor()

                        # 드롭다운용 옵션 생성 (유형별 그룹화)
                        prompt_options = []
                        prompt_map = {}  # id -> template info

                        type_labels = {
                            "single": "🔴 단일 씬 분석용",
                            "batch": "🟠 배치 분석용",
                            "both": "🟢 범용"
                        }

                        for ptype in ["single", "batch", "both"]:
                            templates_in_type = all_srt_prompts.get(ptype, [])
                            if templates_in_type:
                                for t in templates_in_type:
                                    default_badge = " [기본]" if t["is_default"] else ""
                                    display_name = f"{type_labels[ptype]} | {t['name']}{default_badge}"
                                    prompt_options.append(display_name)
                                    prompt_map[display_name] = t

                        if prompt_options:
                            # 세션 스테이트 초기화
                            if 'editor_selected_prompt' not in st.session_state:
                                st.session_state['editor_selected_prompt'] = prompt_options[0]

                            selected_prompt_display = st.selectbox(
                                "📋 편집할 프롬프트 선택",
                                options=prompt_options,
                                key="editor_prompt_selector",
                                help="수정할 프롬프트를 선택하세요"
                            )

                            if selected_prompt_display in prompt_map:
                                selected_info = prompt_map[selected_prompt_display]
                                selected_template = template_manager.get_template(selected_info["id"])

                                if selected_template:
                                    is_default = selected_template.is_default

                                    # 기본 프롬프트 안내
                                    if is_default:
                                        st.info("ℹ️ 기본 프롬프트는 이름 변경 및 삭제가 불가능합니다. 복제하여 사용하세요.")

                                    # 프롬프트 이름 편집
                                    edited_name = st.text_input(
                                        "프롬프트 이름",
                                        value=selected_template.name,
                                        key=f"edit_name_{selected_info['id']}",
                                        disabled=is_default,
                                        help="기본 프롬프트는 이름 변경 불가" if is_default else "프롬프트 이름을 수정할 수 있습니다"
                                    )

                                    # 프롬프트 설명 편집
                                    edited_desc = st.text_input(
                                        "설명",
                                        value=selected_template.description,
                                        key=f"edit_desc_{selected_info['id']}",
                                        help="프롬프트에 대한 간단한 설명"
                                    )

                                    # 프롬프트 내용 편집
                                    edited_prompt = st.text_area(
                                        "프롬프트 내용",
                                        value=selected_template.prompt,
                                        height=300,
                                        key=f"edit_content_{selected_info['id']}"
                                    )

                                    # 수정 여부 확인
                                    is_modified = (
                                        edited_name != selected_template.name or
                                        edited_desc != selected_template.description or
                                        edited_prompt != selected_template.prompt
                                    )

                                    # 버튼 영역
                                    btn_col1, btn_col2, btn_col3, btn_col4 = st.columns(4)

                                    with btn_col1:
                                        save_disabled = not is_modified
                                        if st.button("💾 저장", key="unified_save", disabled=save_disabled, type="primary" if is_modified else "secondary"):
                                            # 기본 프롬프트는 이름 변경 불가
                                            final_name = selected_template.name if is_default else edited_name
                                            if template_manager.update_template(
                                                selected_info["id"],
                                                edited_prompt,
                                                name=final_name,
                                                description=edited_desc
                                            ):
                                                st.success("✅ 저장 완료!")
                                                st.rerun()
                                            else:
                                                st.error("저장 실패")

                                    with btn_col2:
                                        if st.button("🔄 되돌리기", key="unified_revert", disabled=not is_modified):
                                            st.rerun()

                                    with btn_col3:
                                        # 삭제 버튼 (기본 프롬프트는 비활성화)
                                        if st.button("🗑️ 삭제", key="unified_delete", disabled=is_default, help="기본 프롬프트는 삭제 불가" if is_default else "이 프롬프트를 삭제합니다"):
                                            st.session_state['confirm_delete_prompt'] = selected_info["id"]

                                    with btn_col4:
                                        if st.button("📋 복제", key="unified_duplicate", help="이 프롬프트를 복사하여 새 프롬프트 생성"):
                                            st.session_state['show_duplicate_dialog'] = selected_info["id"]

                                    # 삭제 확인 다이얼로그
                                    if st.session_state.get('confirm_delete_prompt') == selected_info["id"]:
                                        st.warning(f"⚠️ '{selected_template.name}' 프롬프트를 삭제하시겠습니까?")
                                        del_col1, del_col2 = st.columns(2)
                                        with del_col1:
                                            if st.button("✅ 삭제 확인", key="confirm_del_yes", type="primary"):
                                                if template_manager.delete_template(selected_info["id"]):
                                                    st.success("✅ 삭제 완료!")
                                                    del st.session_state['confirm_delete_prompt']
                                                    st.rerun()
                                                else:
                                                    st.error("삭제 실패")
                                        with del_col2:
                                            if st.button("❌ 취소", key="confirm_del_no"):
                                                del st.session_state['confirm_delete_prompt']
                                                st.rerun()

                                    # 복제 다이얼로그
                                    if st.session_state.get('show_duplicate_dialog') == selected_info["id"]:
                                        st.info("📋 프롬프트 복제")
                                        dup_name = st.text_input(
                                            "새 프롬프트 이름",
                                            value=f"{selected_template.name} (복사본)",
                                            key="duplicate_new_name"
                                        )
                                        dup_col1, dup_col2 = st.columns(2)
                                        with dup_col1:
                                            if st.button("✅ 복제 생성", key="confirm_dup_yes", type="primary"):
                                                if dup_name.strip():
                                                    new_id = template_manager.duplicate_template(selected_info["id"], dup_name.strip())
                                                    if new_id:
                                                        st.success(f"✅ '{dup_name}' 복제 완료!")
                                                        del st.session_state['show_duplicate_dialog']
                                                        st.rerun()
                                                    else:
                                                        st.error("복제 실패")
                                                else:
                                                    st.warning("이름을 입력하세요")
                                        with dup_col2:
                                            if st.button("❌ 취소", key="confirm_dup_no"):
                                                del st.session_state['show_duplicate_dialog']
                                                st.rerun()
                        else:
                            st.warning("편집 가능한 프롬프트가 없습니다.")

                        st.markdown("---")

                        # 새 버전 생성
                        st.markdown("**➕ 새 프롬프트 버전 생성**")
                        new_name = st.text_input(
                            "새 프롬프트 이름",
                            placeholder="예: SRT 분석 프롬프트 (상세 버전)",
                            key="new_srt_template_name"
                        )

                        # ========================================
                        # 프롬프트 유형 선택 (v2.5 추가)
                        # ========================================
                        st.markdown("##### 📋 프롬프트 유형")
                        new_prompt_type = st.radio(
                            "이 프롬프트를 어디에 사용하시겠습니까?",
                            options=["single", "batch", "both"],
                            format_func=lambda x: {
                                "single": "🔴 단일 씬 분석용 - 순차/병렬 처리 시 각 씬에 개별 적용",
                                "batch": "🟠 배치 분석용 - 여러 씬을 한 번에 묶어서 분석",
                                "both": "🟢 둘 다 사용 - 단일/배치 모두 사용 가능"
                            }[x],
                            key="new_srt_template_type",
                            horizontal=False,
                            help="단일: 씬 하나씩 분석 / 배치: 여러 씬을 한 번에 분석"
                        )

                        # 유형별 설명
                        if new_prompt_type == "single":
                            st.info("""
                            **🔴 단일 씬 분석용**
                            - 순차 처리 또는 병렬 처리 시 사용
                            - 각 씬마다 개별적으로 프롬프트가 적용됨
                            - 예: 씬 1 분석 → 씬 2 분석 → 씬 3 분석...
                            """)
                        elif new_prompt_type == "batch":
                            st.info("""
                            **🟠 배치 분석용**
                            - 배치 처리 시 사용
                            - 여러 씬을 한 번에 묶어서 분석
                            - 예: 씬 1~10을 한 번에 분석
                            """)
                        else:
                            st.info("""
                            **🟢 둘 다 사용**
                            - 단일 씬 분석과 배치 분석 모두에 사용 가능
                            - 범용 프롬프트
                            """)

                        new_prompt = st.text_area(
                            "프롬프트 내용",
                            placeholder="새 프롬프트 내용을 입력하세요...",
                            height=150,
                            key="new_srt_template_content"
                        )
                        if st.button("➕ 새 버전 추가", key="add_new_srt_template", type="primary"):
                            if new_name and new_prompt:
                                new_template = template_manager.create_srt_template(
                                    name=new_name,
                                    description="사용자 정의 SRT 분석 프롬프트",
                                    prompt=new_prompt,
                                    prompt_type=new_prompt_type
                                )
                                if new_template:
                                    type_label = {"single": "단일", "batch": "배치", "both": "범용"}[new_prompt_type]
                                    st.success(f"✅ '{new_name}' 생성 완료! (유형: {type_label})")
                                    st.rerun()
                                else:
                                    st.error("생성 실패")
                            else:
                                st.warning("이름과 내용을 모두 입력하세요.")

                        # ========================================
                        # 프롬프트 목록 요약 (유형별 분류)
                        # ========================================
                        st.markdown("---")
                        st.markdown("**📊 프롬프트 현황**")
                        st.caption("위 통합 편집기에서 프롬프트를 선택하여 편집/삭제/복제할 수 있습니다.")

                        # 유형별로 그룹화
                        grouped_templates = template_manager.get_srt_templates_grouped_by_type()

                        # 유형별 개수 표시
                        single_count = len(grouped_templates.get("single", []))
                        batch_count = len(grouped_templates.get("batch", []))
                        both_count = len(grouped_templates.get("both", []))

                        # 사용자 정의 프롬프트 개수
                        user_single = len([t for t in grouped_templates.get("single", []) if not t.is_default])
                        user_batch = len([t for t in grouped_templates.get("batch", []) if not t.is_default])
                        user_both = len([t for t in grouped_templates.get("both", []) if not t.is_default])

                        col_stat1, col_stat2, col_stat3 = st.columns(3)
                        with col_stat1:
                            st.metric("🔴 단일 씬 분석용", f"{single_count}개", f"(사용자: {user_single}개)")
                        with col_stat2:
                            st.metric("🟠 배치 분석용", f"{batch_count}개", f"(사용자: {user_batch}개)")
                        with col_stat3:
                            st.metric("🟢 범용", f"{both_count}개", f"(사용자: {user_both}개)")

                        # ============================================================
                        # ⭐ 기본 프롬프트 설정 (v3.26 추가)
                        # ============================================================
                        st.markdown("---")
                        all_srt_prompts_for_default = template_manager.get_all_srt_prompts_for_editor()
                        render_default_prompt_settings(
                            all_srt_prompts=all_srt_prompts_for_default,
                            key_prefix="srt_default_prompt"
                        )

            # ═══════════════════════════════════════════════════════════════════
            # 🔀 분석 모드 선택 (v3.18 추가)
            # ═══════════════════════════════════════════════════════════════════
            st.markdown("##### 🔀 분석 모드 선택")
            st.caption("기존 분석 데이터 처리 방식을 선택합니다.")

            analysis_mode = st.radio(
                "분석 모드",
                options=["overwrite", "new"],
                format_func=lambda x: {
                    "overwrite": "📝 덮어쓰기 (기존 분석 유지, 선택된 씬만 업데이트)",
                    "new": "🆕 새로운 분석 (기존 분석 삭제 후 새로 시작)"
                }[x],
                horizontal=False,
                key="srt_analysis_mode",
                help="덮어쓰기: 기존 분석 결과 유지하며 선택된 씬만 업데이트 | 새로운 분석: 기존 분석 완전 삭제"
            )

            # 새로운 분석 모드 경고
            new_analysis_confirmed = True  # 기본값: 덮어쓰기 모드면 확인 불필요
            if analysis_mode == "new":
                st.warning("""
                ⚠️ **주의**: '새로운 분석' 모드는 기존 분석 데이터를 **완전히 삭제**합니다.
                - scenes.json, characters.json, full_analysis.json 삭제
                - 되돌릴 수 없습니다!
                """)
                new_analysis_confirmed = st.checkbox(
                    "✅ 기존 분석 데이터 삭제에 동의합니다",
                    key="confirm_new_analysis",
                    value=False
                )
                if not new_analysis_confirmed:
                    st.info("💡 위 체크박스를 선택해야 분석을 실행할 수 있습니다.")

            st.divider()

            # ═══════════════════════════════════════════════════════════════════
            # 🎯 분석 범위 선택 (v3.16 추가)
            # ═══════════════════════════════════════════════════════════════════
            st.markdown("##### 🎯 분석 범위 선택")
            st.caption("전체 씬 또는 특정 범위만 분석할 수 있습니다.")

            # 기존 분석 결과 로드 (미분석/실패 씬 확인용)
            existing_analysis = {}
            analysis_path = project_path / "analysis" / "scenes.json"
            if analysis_path.exists():
                try:
                    with open(analysis_path, "r", encoding="utf-8") as f:
                        existing_scenes = json.load(f)
                        for scene in existing_scenes:
                            sid = scene.get("scene_id") or scene.get("scene_num")
                            if sid:
                                existing_analysis[sid] = scene
                except:
                    pass

            # 선택된 씬 ID 저장용
            selected_scene_ids = []
            total_scenes = len(srt_scenes)

            # ⭐ v3.16: session_state 초기화 (위젯 생성 전!)
            if "srt_range_start" not in st.session_state:
                st.session_state["srt_range_start"] = 1
            if "srt_range_end" not in st.session_state:
                st.session_state["srt_range_end"] = min(10, total_scenes)
            # 범위 검증 (total_scenes가 변경된 경우)
            if st.session_state["srt_range_start"] > total_scenes:
                st.session_state["srt_range_start"] = 1
            if st.session_state["srt_range_end"] > total_scenes:
                st.session_state["srt_range_end"] = total_scenes

            # 분석 범위 선택 라디오
            range_mode = st.radio(
                "범위 선택 모드",
                options=["all", "range", "individual"],
                format_func=lambda x: {"all": "🌐 전체", "range": "📏 구간 지정", "individual": "☑️ 개별 선택"}[x],
                horizontal=True,
                key="srt_range_mode",
                label_visibility="collapsed"
            )

            if range_mode == "all":
                # 전체 선택
                selected_scene_ids = [s.get("scene_id", i+1) for i, s in enumerate(srt_scenes)]
                st.info(f"✅ 전체 {total_scenes}개 씬이 선택되었습니다.")

            elif range_mode == "range":
                # 구간 지정
                # ⭐ v3.16: 콜백 함수 정의 (위젯 전에 정의해야 함)
                def set_range_first_10():
                    st.session_state["srt_range_start"] = 1
                    st.session_state["srt_range_end"] = min(10, st.session_state.get("_total_scenes", 10))

                def set_range_first_50():
                    st.session_state["srt_range_start"] = 1
                    st.session_state["srt_range_end"] = min(50, st.session_state.get("_total_scenes", 50))

                def set_range_last_50():
                    total = st.session_state.get("_total_scenes", 100)
                    st.session_state["srt_range_start"] = max(1, total - 49)
                    st.session_state["srt_range_end"] = total

                def set_range_all():
                    total = st.session_state.get("_total_scenes", 100)
                    st.session_state["srt_range_start"] = 1
                    st.session_state["srt_range_end"] = total

                # total_scenes를 session_state에 임시 저장 (콜백에서 사용)
                st.session_state["_total_scenes"] = total_scenes

                # 빠른 선택 버튼 (on_click 콜백 사용!)
                st.markdown("**⚡ 빠른 선택**")
                quick_col1, quick_col2, quick_col3, quick_col4 = st.columns(4)

                with quick_col1:
                    st.button("처음 10개", key="quick_first_10", use_container_width=True, on_click=set_range_first_10)

                with quick_col2:
                    st.button("처음 50개", key="quick_first_50", use_container_width=True, on_click=set_range_first_50)

                with quick_col3:
                    st.button("마지막 50개", key="quick_last_50", use_container_width=True, on_click=set_range_last_50)

                with quick_col4:
                    st.button("전체 선택", key="quick_all", use_container_width=True, on_click=set_range_all)

                # 수동 범위 입력 (value= 제거, session_state에서 자동 로드)
                range_col1, range_col2 = st.columns(2)

                with range_col1:
                    start_scene = st.number_input(
                        "시작 씬 번호",
                        min_value=1,
                        max_value=total_scenes,
                        key="srt_range_start"
                    )

                with range_col2:
                    end_scene = st.number_input(
                        "종료 씬 번호",
                        min_value=1,
                        max_value=total_scenes,
                        key="srt_range_end"
                    )

                # 구간 유효성 검사
                if start_scene <= end_scene:
                    selected_scene_ids = [
                        s.get("scene_id", i+1)
                        for i, s in enumerate(srt_scenes)
                        if start_scene <= s.get("scene_id", i+1) <= end_scene
                    ]
                    st.success(f"✅ 씬 {start_scene} ~ {end_scene} ({len(selected_scene_ids)}개) 선택됨")
                else:
                    st.error("❌ 시작 씬 번호가 종료 씬 번호보다 큽니다.")
                    selected_scene_ids = []

            else:  # individual
                # 개별 선택
                st.markdown("**⚡ 빠른 선택 버튼**")
                quick_col1, quick_col2, quick_col3, quick_col4 = st.columns(4)

                # 미분석 씬 계산
                unanalyzed_ids = []
                failed_ids = []
                for i, s in enumerate(srt_scenes):
                    sid = s.get("scene_id", i+1)
                    if sid not in existing_analysis:
                        unanalyzed_ids.append(sid)
                    else:
                        # 분석 실패 여부 확인 (프롬프트가 없거나 에러 표시가 있는 경우)
                        existing = existing_analysis[sid]
                        has_prompt = existing.get("image_prompt_en") or existing.get("image_prompt")
                        has_error = existing.get("analysis_error") or existing.get("error")
                        if not has_prompt or has_error:
                            failed_ids.append(sid)

                with quick_col1:
                    if st.button(f"📭 미분석 ({len(unanalyzed_ids)})", key="quick_unanalyzed", use_container_width=True):
                        if unanalyzed_ids:
                            st.session_state["srt_individual_selection"] = unanalyzed_ids
                            st.rerun()
                        else:
                            st.toast("모든 씬이 이미 분석되었습니다.")

                with quick_col2:
                    if st.button(f"❌ 실패 ({len(failed_ids)})", key="quick_failed", use_container_width=True):
                        if failed_ids:
                            st.session_state["srt_individual_selection"] = failed_ids
                            st.rerun()
                        else:
                            st.toast("분석 실패한 씬이 없습니다.")

                with quick_col3:
                    if st.button("✅ 전체 선택", key="quick_select_all", use_container_width=True):
                        all_ids = [s.get("scene_id", i+1) for i, s in enumerate(srt_scenes)]
                        st.session_state["srt_individual_selection"] = all_ids
                        st.rerun()

                with quick_col4:
                    if st.button("🔄 전체 해제", key="quick_deselect_all", use_container_width=True):
                        st.session_state["srt_individual_selection"] = []
                        st.rerun()

                # 개별 씬 체크박스 (페이지네이션)
                st.markdown("---")
                st.markdown("**☑️ 개별 씬 선택**")

                # 페이지네이션 설정
                page_size = 20
                total_pages = (total_scenes + page_size - 1) // page_size

                page_col1, page_col2 = st.columns([3, 1])
                with page_col1:
                    current_page = st.number_input(
                        f"페이지 (1-{total_pages})",
                        min_value=1,
                        max_value=max(1, total_pages),
                        value=1,
                        key="srt_individual_page"
                    )
                with page_col2:
                    st.markdown(f"<br>", unsafe_allow_html=True)
                    st.caption(f"총 {total_scenes}개 씬")

                # 현재 페이지의 씬 표시
                start_idx = (current_page - 1) * page_size
                end_idx = min(start_idx + page_size, total_scenes)
                page_scenes = srt_scenes[start_idx:end_idx]

                # 이전 선택 상태 로드
                prev_selection = st.session_state.get("srt_individual_selection", [])

                # 체크박스 표시 (3열)
                checkbox_cols = st.columns(3)
                new_selection = list(prev_selection)  # 복사본 생성

                for i, scene in enumerate(page_scenes):
                    col_idx = i % 3
                    sid = scene.get("scene_id", start_idx + i + 1)

                    # 분석 상태 아이콘
                    status_icon = ""
                    if sid not in existing_analysis:
                        status_icon = "📭"  # 미분석
                    else:
                        existing = existing_analysis[sid]
                        has_prompt = existing.get("image_prompt_en") or existing.get("image_prompt")
                        has_error = existing.get("analysis_error") or existing.get("error")
                        if has_error or not has_prompt:
                            status_icon = "❌"  # 실패
                        else:
                            status_icon = "✅"  # 성공

                    with checkbox_cols[col_idx]:
                        is_checked = st.checkbox(
                            f"{status_icon} 씬 {sid}",
                            value=sid in prev_selection,
                            key=f"scene_checkbox_{sid}"
                        )

                        if is_checked and sid not in new_selection:
                            new_selection.append(sid)
                        elif not is_checked and sid in new_selection:
                            new_selection.remove(sid)

                # 선택 상태 업데이트
                st.session_state["srt_individual_selection"] = new_selection
                selected_scene_ids = new_selection

                st.info(f"✅ {len(selected_scene_ids)}개 씬 선택됨")

                # 선택된 씬 미리보기
                if selected_scene_ids and len(selected_scene_ids) <= 30:
                    with st.expander("📋 선택된 씬 목록", expanded=False):
                        sorted_ids = sorted(selected_scene_ids)
                        st.write(", ".join([f"씬 {sid}" for sid in sorted_ids]))

            # 선택된 씬 ID를 세션에 저장
            st.session_state["srt_selected_scene_ids"] = selected_scene_ids

            st.divider()

            # 묶음 분석 옵션 (v3.15 추가)
            st.markdown("##### 📦 묶음 씬분석 옵션")

            bundle_col1, bundle_col2 = st.columns([1, 2])

            with bundle_col1:
                # v1.0: 설정 영속성 - persistent_selectbox 사용
                bundle_size = persistent_selectbox(
                    "묶음 크기",
                    options=[1, 2, 3, 4, 5],
                    page=PAGE_SETTINGS_NAME,
                    setting_key="srt_bundle_size",
                    default_index=1,  # 기본값 2
                    help="N개의 씬을 묶어서 하나의 분석 단위로 처리합니다. 안정적인 이미지 전환(5-10초)에 효과적입니다."
                )

            with bundle_col2:
                if bundle_size == 1:
                    st.info("📍 개별 분석: 각 씬을 독립적으로 분석합니다.")
                else:
                    total_bundles = (len(srt_scenes) + bundle_size - 1) // bundle_size
                    st.info(f"""
                    📦 **묶음 분석**: {len(srt_scenes)}개 씬 → {total_bundles}개 묶음
                    - 묶음당 평균 길이: ~{sum(s['duration'] for s in srt_scenes) / total_bundles:.1f}초
                    - AI 호출 횟수 감소 → 비용 절감
                    - 묶음 내 씬들은 동일한 프롬프트 공유
                    """)

            # AI 모델 및 처리 모드 선택 (프롬프트 생성 시에만 표시)
            selected_model = "claude-sonnet-4-20250514"
            processing_mode = "batch"

            if generate_prompts:
                st.markdown("##### ⚙️ AI 분석 설정")

                from utils.ai_model_selector import render_model_selector, render_processing_mode_selector, render_api_key_status, is_claude_code_selected, render_claude_code_settings
                from utils.ai_providers import get_available_models, get_model

                # API 키 상태 확인
                available_models = get_available_models()
                if not available_models:
                    st.error("⚠️ 사용 가능한 AI 모델이 없습니다. API 키를 설정해주세요.")
                    with st.expander("🔑 API 키 상태 확인"):
                        render_api_key_status()
                else:
                    col1, col2 = st.columns(2)

                    with col1:
                        selected_model = render_model_selector(
                            key="srt_model",
                            task="scene_analysis",
                            show_provider_filter=True,
                            show_speed_filter=True,
                            show_details=True
                        )

                    with col2:
                        processing_mode = render_processing_mode_selector(
                            key="srt_processing_mode"
                        )

                    # 현재 선택된 모델 정보 표시
                    model_info = get_model(selected_model) if selected_model else None
                    if model_info:
                        provider_icon = {"anthropic": "🟠", "google": "🔵", "openai": "🟢", "local": "🤖"}.get(model_info.provider.value, "")
                        st.caption(f"{provider_icon} 선택된 모델: **{model_info.name}** - {model_info.description}")

                    # v3.60: Claude Code 선택 시 설정 UI 표시
                    if is_claude_code_selected("srt_model"):
                        cc_settings = render_claude_code_settings(key="srt_claude_code")
                        if cc_settings is None:
                            st.warning("⚠️ Claude Code를 사용하려면 CLI를 먼저 설치하세요.")

                    # 속도 예상 표시 (선택된 씬 수 기반)
                    selected_count = len(st.session_state.get("srt_selected_scene_ids", srt_scenes))
                    speed_info = {
                        "sequential": f"⏱️ 예상 시간: ~{selected_count * 3}초 (순차 처리)",
                        "batch": f"⚡ 예상 시간: ~{(selected_count // 5 + 1) * 5}초 (배치 처리)",
                        "parallel": f"🚀 예상 시간: ~{max(selected_count // 3, 5)}초 (병렬 처리)"
                    }
                    st.caption(speed_info.get(processing_mode, ""))

                    # ========================================
                    # 📋 분석 프롬프트 설정 (v2.7 통합)
                    # ========================================
                    st.markdown("##### 📋 분석 프롬프트 설정")

                    # 현재 처리 모드 표시
                    mode_info = {
                        "sequential": ("🔴 순차 처리", "각 씬을 하나씩 순서대로 분석", "single"),
                        "batch": ("🟠 배치 처리", "여러 씬을 한 번에 묶어서 분석", "batch"),
                        "parallel": ("🔴 병렬 처리", "여러 씬을 동시에 개별 분석", "single")
                    }
                    mode_label, mode_desc, prompt_type = mode_info.get(processing_mode, ("🟠 배치 처리", "기본 모드", "batch"))

                    st.info(f"**현재 처리 모드**: {mode_label}\n\n{mode_desc}")
                    st.caption("※ 처리 모드에 따라 해당 유형의 프롬프트가 자동 필터링됩니다.")

                    # 처리 모드에 따라 사용 가능한 프롬프트 필터링
                    available_prompts = template_manager.get_templates_for_analysis_mode(processing_mode)

                    if available_prompts:
                        # 현재 활성 프롬프트 ID 가져오기
                        active_prompt_id = template_manager.get_active_prompt(prompt_type)

                        # 프롬프트 옵션 생성
                        prompt_options = {}
                        prompt_ids = []
                        for t in available_prompts:
                            # 유형 배지 추가
                            type_badge = {
                                "single": "🔴",
                                "batch": "🟠",
                                "both": "🟢"
                            }.get(getattr(t, 'prompt_type', 'both'), "🟢")

                            # 현재 활성 프롬프트 표시
                            active_mark = " ✓" if t.id == active_prompt_id else ""
                            prompt_options[t.id] = f"{type_badge} {t.name}{active_mark}"
                            prompt_ids.append(t.id)

                        # ⭐ v3.26.2: 기본 프롬프트 적용 버그 수정
                        # 문제: st.selectbox의 key가 있으면 index 파라미터가 무시됨
                        # 해결: selectbox 렌더링 전에 session_state를 미리 설정

                        default_prompt_type = "single_scene_analysis" if prompt_type == "single" else "batch_scene_analysis"
                        user_default_prompt_id = get_default_prompt_id(default_prompt_type)

                        # 🔴 v3.26.2: session_state 기반 기본값 적용
                        # selectbox의 key가 있으면 session_state[key] 값을 우선 사용함
                        # 따라서 session_state가 없거나 처리 모드가 변경되면 기본값으로 초기화
                        selectbox_key = "srt_analysis_prompt_selector"
                        mode_key = "_last_prompt_type"  # 마지막 처리 모드 추적

                        # 처리 모드 변경 감지 (single ↔ batch)
                        last_prompt_type = st.session_state.get(mode_key)
                        mode_changed = last_prompt_type != prompt_type

                        # selectbox가 아직 초기화되지 않았거나, 처리 모드가 변경됨
                        needs_default_init = (
                            selectbox_key not in st.session_state or
                            mode_changed
                        )

                        default_prompt_applied = False

                        if needs_default_init:
                            # 사용자 기본 프롬프트가 있으면 그것을 사용
                            if user_default_prompt_id and user_default_prompt_id in prompt_ids:
                                st.session_state[selectbox_key] = user_default_prompt_id
                                default_prompt_applied = True
                            elif active_prompt_id and active_prompt_id in prompt_ids:
                                # 활성 프롬프트 (세션 중 수동 선택한 것)
                                st.session_state[selectbox_key] = active_prompt_id
                            else:
                                # 시스템 기본 템플릿 ID
                                fallback_id = "srt_scene_single" if prompt_type == "single" else "srt_scene_batch"
                                if fallback_id in prompt_ids:
                                    st.session_state[selectbox_key] = fallback_id
                                elif prompt_ids:
                                    st.session_state[selectbox_key] = prompt_ids[0]

                            # 처리 모드 기록
                            st.session_state[mode_key] = prompt_type

                        # 현재 session_state 값이 사용자 기본값과 같은지 확인 (안내 메시지용)
                        current_value = st.session_state.get(selectbox_key)
                        if current_value == user_default_prompt_id and user_default_prompt_id:
                            default_prompt_applied = True

                        # 기본 프롬프트 적용 안내
                        if default_prompt_applied:
                            st.info(f"⭐ 설정된 기본 프롬프트가 적용되었습니다.")

                        # ⭐ v3.27: on_change 콜백으로 사용자 변경만 감지
                        # 문제: 페이지 리런 시 selectbox 값과 settings 값이 달라지면 자동 저장되어 버림
                        # 해결: on_change 콜백을 사용하여 사용자가 실제로 변경할 때만 저장

                        def on_prompt_selection_change():
                            """사용자가 프롬프트 선택을 변경했을 때만 호출됨"""
                            new_id = st.session_state.get(selectbox_key)
                            if new_id:
                                # 현재 prompt_type을 가져옴 (클로저 사용 불가하므로 세션에서)
                                current_prompt_type = st.session_state.get(mode_key, "batch")
                                template_manager.set_active_prompt(current_prompt_type, new_id)
                                st.session_state['_prompt_selection_changed'] = True

                        # selectbox 렌더링 (session_state[key]가 이미 설정되어 있으므로 그 값을 사용함)
                        selected_prompt_id = st.selectbox(
                            "사용할 프롬프트",
                            options=prompt_ids,
                            format_func=lambda x: prompt_options.get(x, x),
                            key=selectbox_key,
                            on_change=on_prompt_selection_change,
                            help="선택한 프롬프트가 분석에 바로 적용됩니다. ⭐ 기본 프롬프트 설정에서 기본값을 변경할 수 있습니다."
                        )

                        # ⭐ v3.27: 사용자가 실제로 변경했을 때만 성공 메시지 표시
                        if st.session_state.get('_prompt_selection_changed'):
                            st.success(f"✅ 프롬프트가 적용되었습니다.")
                            del st.session_state['_prompt_selection_changed']

                        # 선택된 프롬프트 정보 표시
                        selected_prompt_template = template_manager.get_template(selected_prompt_id)
                        if selected_prompt_template:
                            with st.expander("📄 선택된 프롬프트 미리보기", expanded=False):
                                st.markdown(f"**{selected_prompt_template.name}**")
                                st.caption(selected_prompt_template.description)
                                st.code(selected_prompt_template.prompt, language="markdown")

                        # 세션에 선택된 프롬프트 ID 저장
                        st.session_state['selected_srt_prompt_id'] = selected_prompt_id
                    else:
                        st.warning("사용 가능한 프롬프트가 없습니다. 프롬프트 설정을 확인하세요.")
                        st.session_state['selected_srt_prompt_id'] = None

                    st.markdown("---")

            # 적용 버튼
            selected_scene_ids_final = st.session_state.get("srt_selected_scene_ids", [])
            btn_label = f"🚀 SRT 씬 적용하기 ({len(selected_scene_ids_final)}개 선택됨)"

            if not selected_scene_ids_final:
                st.warning("⚠️ 분석할 씬을 선택해주세요.")
                st.stop()

            # 새로운 분석 모드 확인 (v3.18)
            if analysis_mode == "new" and not new_analysis_confirmed:
                st.error("❌ '새로운 분석' 모드를 사용하려면 데이터 삭제에 동의해주세요.")
                st.stop()

            if st.button(btn_label, type="primary", use_container_width=True):
                progress = st.progress(0)
                status = st.empty()

                try:
                    import time as time_module
                    start_time = time_module.time()

                    # ⭐ 선택된 씬만 필터링 (v3.16)
                    status.text("선택된 씬 필터링 중...")
                    filtered_srt_scenes = [
                        s for s in srt_scenes
                        if s.get("scene_id", srt_scenes.index(s) + 1) in selected_scene_ids_final
                    ]

                    if not filtered_srt_scenes:
                        st.error("❌ 선택된 씬을 찾을 수 없습니다.")
                        st.stop()

                    st.info(f"📊 {len(filtered_srt_scenes)}개 씬 분석 시작 (전체 {len(srt_scenes)}개 중)")

                    # ⭐ 분석 모드에 따른 기존 데이터 처리 (v3.18)
                    existing_scenes_dict = {}
                    existing_characters = []
                    analysis_dir = project_path / "analysis"
                    existing_full_path = analysis_dir / "full_analysis.json"
                    existing_scenes_path = analysis_dir / "scenes.json"
                    existing_chars_path = analysis_dir / "characters.json"

                    if analysis_mode == "new":
                        # 🆕 새로운 분석 모드: 기존 파일 삭제
                        status.text("기존 분석 데이터 삭제 중...")
                        deleted_files = []
                        for fpath in [existing_full_path, existing_scenes_path, existing_chars_path]:
                            if fpath.exists():
                                try:
                                    fpath.unlink()
                                    deleted_files.append(fpath.name)
                                except Exception as e:
                                    print(f"[씬 분석] 파일 삭제 실패: {fpath} - {e}", flush=True)

                        if deleted_files:
                            st.toast(f"🗑️ 삭제됨: {', '.join(deleted_files)}")
                        print(f"[씬 분석] 새로운 분석 모드 - 기존 파일 삭제: {deleted_files}", flush=True)

                        # ⭐ v3.80: 전체 SRT 씬을 기본으로 로드 (선택된 씬만 분석하되 나머지도 유지)
                        status.text("전체 SRT 씬 기본 구조 생성 중...")
                        all_srt_analysis_scenes = convert_srt_to_scene_structure(srt_scenes)
                        for scene in all_srt_analysis_scenes:
                            sid = scene.get("scene_id")
                            if sid:
                                existing_scenes_dict[sid] = scene
                        print(f"[씬 분석] 새로운 분석 모드 - 전체 SRT {len(existing_scenes_dict)}개 씬 기본 구조 생성", flush=True)

                    elif analysis_mode == "overwrite":
                        # 📝 덮어쓰기 모드: 기존 분석 결과 로드 (병합용)
                        if existing_full_path.exists():
                            try:
                                with open(existing_full_path, "r", encoding="utf-8") as f:
                                    existing_data = json.load(f)
                                    for scene in existing_data.get("scenes", []):
                                        sid = scene.get("scene_id") or scene.get("scene_num")
                                        if sid:
                                            existing_scenes_dict[sid] = scene
                                    existing_characters = existing_data.get("characters", [])
                                print(f"[씬 분석] 덮어쓰기 모드 - 기존 {len(existing_scenes_dict)}개 씬 로드", flush=True)
                            except:
                                pass

                    # SRT 씬을 분석 결과 형식으로 변환 (선택된 씬만)
                    status.text("씬 데이터 변환 중...")
                    analysis_scenes = convert_srt_to_scene_structure(filtered_srt_scenes)

                    # 묶음 생성 (v3.15)
                    status.text(f"씬 묶음 생성 중 (묶음 크기: {bundle_size})...")
                    analysis_scenes = create_bundles(analysis_scenes, bundle_size)
                    bundle_summary = get_bundle_summary(analysis_scenes)

                    # 프롬프트 생성 (옵션)
                    if generate_prompts:
                        from utils.scene_speed_analyzer import analyze_scenes_with_mode, get_analysis_metadata
                        from utils.character_visual_prompt import post_process_analysis_characters
                        from utils.ai_providers import get_available_models, get_model

                        available = get_available_models()
                        if not available:
                            st.warning("⚠️ 사용 가능한 AI 모델이 없습니다. API 키를 설정해주세요.")
                        else:
                            # 선택된 모델 정보 표시
                            model_info = get_model(selected_model) if selected_model else None
                            model_display = model_info.name if model_info else selected_model
                            provider_display = model_info.provider.value if model_info else "unknown"

                            # ═══════════════════════════════════════════════════════════
                            # v3.73: Claude Code 모델 여부 확인 및 세션 상태 초기화
                            # ═══════════════════════════════════════════════════════════
                            is_claude_code_model = (
                                selected_model == "claude_code" or
                                "Claude Code" in str(selected_model) or
                                "claude_code" in str(selected_model).lower()
                            )

                            # Claude Code가 아닌 모델 선택 시 Claude Code 관련 세션 상태 초기화
                            if not is_claude_code_model:
                                if st.session_state.get('claude_code_auto_execution'):
                                    st.session_state['claude_code_auto_execution'] = False
                                if st.session_state.get('claude_code_agent_mode'):
                                    st.session_state['claude_code_agent_mode'] = False
                                # 기타 Claude Code 관련 상태도 초기화
                                for key in ['claude_code_prompt_file', 'claude_code_batch_file',
                                           'claude_code_scenes_path', 'claude_code_prompt_text']:
                                    if key in st.session_state:
                                        del st.session_state[key]

                            # 묶음 분석: 대표 씬만 분석
                            primary_scenes = get_bundle_primary_scenes(analysis_scenes)
                            total_bundles = len(primary_scenes)

                            if bundle_size > 1:
                                status.text(f"AI 프롬프트 생성 중... ({model_display}) - {total_bundles}개 묶음 분석")
                            else:
                                status.text(f"AI 프롬프트 생성 중... ({model_display})")

                            # 대표 씬들에 bundle_text를 narration으로 사용 (더 많은 컨텍스트)
                            for ps in primary_scenes:
                                ps['_original_narration'] = ps.get('narration', '')
                                ps['narration'] = ps.get('bundle_text', ps.get('narration', ''))

                            # ⭐ v3.27: UI에서 선택된 프롬프트 ID 가져오기
                            selected_prompt_id_for_analysis = st.session_state.get('selected_srt_prompt_id')
                            print(f"[씬분석UI] ========== 분석 실행 ==========")
                            print(f"[씬분석UI] 선택된 프롬프트 ID: {selected_prompt_id_for_analysis}")
                            print(f"[씬분석UI] 처리 모드: {processing_mode}")
                            print(f"[씬분석UI] 모델: {selected_model}")

                            # 새로운 속도 개선 분석기 사용 (멀티 프로바이더 지원)
                            # ⭐ v3.27: prompt_id 직접 전달!
                            # ⭐ v3.60: Claude Code 파라미터 추가
                            # ⭐ v13.7: selected_scene_ids 추가 (씬 범위 선택 버그 수정)
                            cc_kwargs = {}
                            # ⭐ v13.14: Claude Code용 씬 데이터 분기 처리
                            scenes_for_analysis = primary_scenes  # 기본값: Gemini 등은 대표 씬만

                            if selected_model == "claude_code" or "Claude Code" in str(selected_model):
                                # ⭐ v13.14 핵심 수정: Claude Code는 전체 씬 전달!
                                # 문제: 대표 씬만 저장 → Bundle 병합 시 멤버 씬 없음 → 프롬프트 누락
                                # 해결: 전체 씬 저장, Claude Code가 대표 씬만 분석 (프롬프트에서 지시)
                                scenes_for_analysis = analysis_scenes  # 전체 씬 (대표 + 멤버)

                                # 전체 씬 ID 추출 (Bundle 포함)
                                all_scene_ids = [s.get('scene_id', s.get('id', i+1)) for i, s in enumerate(analysis_scenes)]
                                # 대표 씬 ID만 추출 (분석 대상)
                                primary_scene_ids = [s.get('scene_id', s.get('id', i+1)) for i, s in enumerate(primary_scenes)]

                                print(f"[씬분석UI] ⭐ v13.14: Claude Code 전체 씬 전달!")
                                print(f"[씬분석UI] 📋 전체 씬: {len(all_scene_ids)}개 (ID: {min(all_scene_ids)} ~ {max(all_scene_ids)})")
                                print(f"[씬분석UI] 🎯 대표 씬 (분석 대상): {len(primary_scene_ids)}개 (ID: {primary_scene_ids})")

                                cc_kwargs = {
                                    'project_path': str(project_path),
                                    'scenes_json_path': str(existing_scenes_path) if existing_scenes_path.exists() else str(analysis_dir / "scenes.json"),
                                    'timeout': st.session_state.get("srt_claude_code_timeout", st.session_state.get("claude_code_timeout", 600)),
                                    'bundle_mode': st.session_state.get("srt_claude_code_bundle_mode", st.session_state.get("claude_code_bundle_mode", True)),
                                    'custom_instructions': st.session_state.get("srt_claude_code_custom_instructions", st.session_state.get("claude_code_custom_instructions", "")),
                                    'selected_scene_ids': primary_scene_ids,  # v13.14: 대표 씬 ID만 (분석 대상)
                                    'all_scene_ids': all_scene_ids  # v13.14: 전체 씬 ID (Bundle 포함)
                                }

                            analyzed_primary = analyze_scenes_with_mode(
                                scenes=scenes_for_analysis,  # v13.14: Claude Code는 전체 씬, Gemini 등은 대표 씬
                                mode=processing_mode,
                                model=selected_model,
                                progress_callback=lambda p: progress.progress(p * 0.7),  # 70%까지
                                status_callback=lambda s: status.text(s),
                                prompt_id=selected_prompt_id_for_analysis,  # ⭐ UI 선택값 직접 전달!
                                **cc_kwargs  # v3.60: Claude Code 파라미터
                            )

                            # ═══════════════════════════════════════════════════════════
                            # v3.72/v3.73: 자동 실행 모드 감지 (새 CMD 창에서 실행 중)
                            # v3.73: Claude Code 모델인 경우에만 UI 표시
                            # ═══════════════════════════════════════════════════════════
                            if is_claude_code_model and st.session_state.get('claude_code_auto_execution'):
                                progress.progress(0.9)
                                status.text("🚀 새 CMD 창에서 Claude Code 실행 중...")

                                st.success("🚀 **Claude Code가 새 CMD 창에서 실행 중입니다!**")

                                # ═══════════════════════════════════════════════════════════
                                # 실시간 진행률 UI (v13.6)
                                # ═══════════════════════════════════════════════════════════
                                from utils.claude_code_runner import (
                                    get_claude_code_progress,
                                    check_claude_code_completion,
                                    cleanup_claude_code_files
                                )

                                scenes_path = st.session_state.get('claude_code_scenes_path', str(project_path / "analysis" / "scenes.json"))
                                total_scenes_count = len(primary_scenes) if 'primary_scenes' in dir() else 30

                                # 시작 시간 기록
                                if 'claude_code_start_time' not in st.session_state:
                                    st.session_state['claude_code_start_time'] = time.time()

                                start_time = st.session_state.get('claude_code_start_time', time.time())
                                elapsed = int(time.time() - start_time)

                                st.markdown("---")
                                st.subheader("📊 분석 진행률")

                                # 완료 체크
                                is_complete = check_claude_code_completion(str(project_path))

                                if is_complete:
                                    st.progress(1.0)
                                    st.success("✅ **분석이 완료되었습니다!**")

                                    # 자동으로 결과 로드
                                    try:
                                        with open(scenes_path, 'r', encoding='utf-8') as f:
                                            loaded_scenes = json.load(f)

                                        if isinstance(loaded_scenes, dict):
                                            loaded_scenes = loaded_scenes.get('scenes', loaded_scenes)

                                        if loaded_scenes:
                                            analyzed_count = sum(1 for s in loaded_scenes if s.get('background_prompt_en'))
                                            st.success(f"📥 {len(loaded_scenes)}개 씬 로드 완료! ({analyzed_count}개 분석됨)")

                                            # session_state 동기화
                                            st.session_state['scenes'] = loaded_scenes
                                            st.session_state['scenes_data'] = loaded_scenes
                                            st.session_state['analysis_scenes'] = loaded_scenes
                                            st.session_state['analysis_complete'] = True

                                            # 파일 정리
                                            cleanup_claude_code_files(str(project_path))

                                            # 상태 리셋
                                            st.session_state['claude_code_auto_execution'] = False
                                            if 'claude_code_start_time' in st.session_state:
                                                del st.session_state['claude_code_start_time']

                                            st.balloons()
                                            time.sleep(2)
                                            st.rerun()
                                    except Exception as e:
                                        st.error(f"결과 로드 실패: {e}")
                                        st.session_state['claude_code_auto_execution'] = False
                                else:
                                    # 진행률 읽기
                                    progress_data = get_claude_code_progress(str(project_path))

                                    if progress_data:
                                        p_status = progress_data.get('status', 'running')
                                        p_current = progress_data.get('current', 0)
                                        p_total = progress_data.get('total', total_scenes_count)
                                        p_message = progress_data.get('message', '')

                                        pct = min(p_current / p_total, 0.99) if p_total > 0 else 0
                                        st.progress(pct)

                                        # 상태 정보 (3열)
                                        col1, col2, col3 = st.columns(3)
                                        with col1:
                                            st.metric("진행", f"{p_current} / {p_total} 씬")
                                        with col2:
                                            st.metric("완료율", f"{pct*100:.0f}%")
                                        with col3:
                                            st.metric("경과 시간", f"{elapsed}초")

                                        if p_message:
                                            st.info(f"💬 {p_message}")
                                        else:
                                            st.info(f"🔄 분석 진행 중... ({p_current}/{p_total})")
                                    else:
                                        st.progress(0.0)
                                        col1, col2 = st.columns(2)
                                        with col1:
                                            st.metric("상태", "시작 대기 중...")
                                        with col2:
                                            st.metric("경과 시간", f"{elapsed}초")
                                        st.warning("⏳ Claude Code 시작 대기 중...")

                                    st.markdown("---")

                                    # 자동 새로고침 옵션
                                    auto_refresh = st.checkbox(
                                        "🔄 자동 새로고침 (2초마다)",
                                        value=True,
                                        key="auto_refresh_claude_progress"
                                    )

                                    if auto_refresh:
                                        # 타임아웃 체크 (10분)
                                        if elapsed > 600:
                                            st.error("❌ 타임아웃 (10분 초과)")
                                            st.session_state['claude_code_auto_execution'] = False
                                        else:
                                            time.sleep(2)
                                            st.rerun()
                                    else:
                                        # 수동 버튼
                                        col1, col2, col3 = st.columns(3)
                                        with col1:
                                            if st.button("🔄 새로고침", use_container_width=True, key="manual_refresh_progress"):
                                                st.rerun()
                                        with col2:
                                            if st.button("📥 결과 확인", type="primary", use_container_width=True, key="check_auto_result_batch"):
                                                st.session_state['claude_code_auto_execution'] = False
                                                st.rerun()
                                        with col3:
                                            if st.button("❌ 취소", use_container_width=True, key="cancel_auto_batch"):
                                                st.session_state['claude_code_auto_execution'] = False
                                                if 'claude_code_start_time' in st.session_state:
                                                    del st.session_state['claude_code_start_time']
                                                st.rerun()

                                st.stop()

                            # ═══════════════════════════════════════════════════════════
                            # v3.71/v3.73: 에이전트 모드 감지 및 UI 표시
                            # v3.73: Claude Code 모델인 경우에만 UI 표시
                            # ═══════════════════════════════════════════════════════════
                            if is_claude_code_model and st.session_state.get('claude_code_agent_mode'):
                                progress.progress(1.0)
                                status.text("🤖 에이전트 모드: 프롬프트 복사 필요")

                                _render_claude_code_agent_ui()
                                st.stop()  # 에이전트 모드에서는 여기서 중단

                            # 대표 씬 narration 복원
                            for ps in analyzed_primary:
                                if '_original_narration' in ps:
                                    ps['narration'] = ps['_original_narration']
                                    del ps['_original_narration']

                            # 묶음 결과를 모든 씬에 적용 (v3.15)
                            progress.progress(0.75)
                            status.text("묶음 분석 결과 적용 중...")

                            for analyzed in analyzed_primary:
                                apply_bundle_analysis_result(analysis_scenes, analyzed)

                            # v3.29: 묶음 병합 후 확인 로깅
                            bg_count_after_bundle = sum(1 for s in analysis_scenes if s.get('background_prompt_en'))
                            print(f"[묶음 병합 후] background_prompt_en 있는 씬: {bg_count_after_bundle}/{len(analysis_scenes)}")
                            for s in analysis_scenes:
                                has_bg = "✅" if s.get('background_prompt_en') else "❌"
                                print(f"  씬 {s.get('scene_id', '?')}: {has_bg} (bundle_id={s.get('bundle_id')}, primary={s.get('is_bundle_primary')})")

                            # 캐릭터 visual_prompt 후처리 (빠른 모델 사용)
                            progress.progress(0.85)
                            status.text("캐릭터 visual_prompt 생성 중...")

                            # 캐릭터용 모델 선택 (같은 프로바이더의 빠른 모델 우선)
                            char_model = "claude-3-5-haiku-20241022"  # 기본값
                            if model_info and model_info.provider.value == "google":
                                char_model = "gemini-2.5-flash"
                            elif model_info and model_info.provider.value == "openai":
                                char_model = "gpt-4o-mini"

                            analysis_scenes, all_characters_with_prompts = post_process_analysis_characters(
                                analysis_scenes,
                                model=char_model if char_model in available else list(available.keys())[0]
                            )

                            progress.progress(0.95)

                    elapsed = time_module.time() - start_time
                    progress.progress(1.0)
                    status.text(f"결과 저장 중... ({elapsed:.1f}초 소요)")

                    # 결과 저장
                    analysis_dir = project_path / "analysis"
                    analysis_dir.mkdir(parents=True, exist_ok=True)

                    # 캐릭터 추출 (post_process에서 이미 처리된 경우 사용)
                    if generate_prompts and 'all_characters_with_prompts' in dir():
                        all_characters = all_characters_with_prompts
                    else:
                        # 폴백: 모든 씬에서 characters 수집
                        all_characters = []
                        char_names_seen = set()
                        for scene in analysis_scenes:
                            for char in scene.get('characters', []):
                                # 캐릭터가 딕셔너리인 경우
                                if isinstance(char, dict):
                                    char_name = char.get('name', '')
                                    if char_name and char_name not in char_names_seen:
                                        char_names_seen.add(char_name)
                                        all_characters.append({
                                            "name": char_name,
                                            "name_ko": char.get('name_ko', char_name),
                                            "role": char.get('role', '등장인물'),
                                            "visual_prompt": char.get('visual_prompt', '')
                                        })
                                # 캐릭터가 문자열인 경우
                                elif isinstance(char, str) and char not in char_names_seen:
                                    char_names_seen.add(char)
                                    all_characters.append({
                                        "name": char,
                                        "name_ko": char,
                                        "role": "등장인물",
                                        "visual_prompt": ""
                                    })

                    # ⭐ 분석 메타데이터 수집
                    analysis_metadata = {}
                    if generate_prompts:
                        try:
                            analysis_metadata = get_analysis_metadata()
                        except Exception as e:
                            print(f"[씬 분석] 메타데이터 수집 실패: {e}")

                    # ⭐ 부분 분석 시 기존 데이터와 병합 (v3.16)
                    if existing_scenes_dict:
                        status.text("기존 분석 결과와 병합 중...")

                        # 새로 분석된 씬으로 기존 데이터 업데이트
                        for scene in analysis_scenes:
                            sid = scene.get("scene_id") or scene.get("scene_num")
                            if sid:
                                existing_scenes_dict[sid] = scene

                        # scene_id 순으로 정렬하여 최종 리스트 생성
                        merged_scenes = sorted(
                            existing_scenes_dict.values(),
                            key=lambda x: x.get("scene_id") or x.get("scene_num") or 0
                        )
                        analysis_scenes = merged_scenes

                        # 기존 캐릭터와 새 캐릭터 병합
                        existing_char_names = {c.get('name') for c in existing_characters if c.get('name')}
                        for char in all_characters:
                            if char.get('name') and char.get('name') not in existing_char_names:
                                existing_characters.append(char)
                                existing_char_names.add(char.get('name'))
                        all_characters = existing_characters

                    # 🔴 저장 전 검증 및 자동 수정 (background_prompt_en 불일치 해결)
                    if analysis_scenes and SCENE_VALIDATOR_AVAILABLE:
                        analysis_scenes = validate_scenes_before_save(analysis_scenes, verbose=True)

                    result = {
                        "scenes": analysis_scenes,
                        "characters": all_characters,
                        "source": "srt",
                        "srt_metadata": {
                            "total_scenes": len(srt_scenes),
                            "total_duration": srt_scenes[-1]['end_seconds'] if srt_scenes else 0,
                            "has_time_codes": True
                        },
                        "bundle_metadata": {
                            "bundle_size": bundle_size,
                            "total_bundles": bundle_summary.get('total_bundles', len(analysis_scenes)),
                            "bundles": bundle_summary.get('bundles', [])
                        },
                        # ⭐ AI 분석 메타데이터 추가
                        "analysis_metadata": analysis_metadata if analysis_metadata else None,
                        "prompt_used": analysis_metadata.get('prompt_template', None) if analysis_metadata else None,
                        # ⭐ 분석 모드 정보 추가 (v3.18)
                        "analysis_mode": analysis_mode,
                        "was_merged": analysis_mode == "overwrite" and len(existing_scenes_dict) > 0
                    }

                    # character_prompt -> characters 후처리 동기화
                    try:
                        from utils.character_sync import sync_all_scenes_characters, update_characters_json
                        analysis_scenes, _sync_cnt = sync_all_scenes_characters(analysis_scenes)
                        if _sync_cnt > 0:
                            print(f"[후처리] {_sync_cnt}개 씬 characters 배열 동기화")
                    except Exception as _e:
                        print(f"[후처리] 동기화 오류 (무시): {_e}")

                    with open(analysis_dir / "scenes.json", "w", encoding="utf-8") as f:
                        json.dump(analysis_scenes, f, ensure_ascii=False, indent=2)

                    with open(analysis_dir / "characters.json", "w", encoding="utf-8") as f:
                        json.dump(all_characters, f, ensure_ascii=False, indent=2)

                    # characters.json에 씬 기반 캐릭터 추가
                    try:
                        from utils.character_sync import update_characters_json as _update_cj
                        _update_cj(analysis_scenes, analysis_dir / "characters.json")
                    except Exception:
                        pass

                    with open(analysis_dir / "full_analysis.json", "w", encoding="utf-8") as f:
                        json.dump(result, f, ensure_ascii=False, indent=2)

                    # 세션에도 저장
                    st.session_state["scene_analysis_result"] = result
                    st.session_state["scenes"] = analysis_scenes
                    st.session_state["characters"] = all_characters
                    st.session_state["scene_characters"] = all_characters
                    st.session_state["extracted_characters"] = all_characters
                    st.session_state["analysis_source"] = "srt"
                    # ⭐ 분석 메타데이터 세션에 저장
                    if analysis_metadata:
                        st.session_state["analysis_metadata"] = analysis_metadata

                    # 부분 분석 여부에 따른 통계 (v3.17.1 - 변수 정의 순서 수정)
                    analyzed_count = len(filtered_srt_scenes)
                    total_count = len(analysis_scenes)
                    is_partial = analyzed_count < total_count

                    # ⭐ 분석 완료 플래그 및 타임스탬프 (v3.17 - UI 즉시 갱신용)
                    import time as time_mod
                    st.session_state["analysis_timestamp"] = time_mod.time()
                    st.session_state["analysis_complete"] = True
                    st.session_state["last_analyzed_count"] = analyzed_count
                    st.session_state["last_total_count"] = total_count
                    st.session_state["last_analyzed_ids"] = [s.get("scene_id") for s in filtered_srt_scenes]

                    # 다른 페이지 캐시 클리어 (Problem 56)
                    clear_scene_cache(str(project_path))
                    # 캐릭터 관리 페이지 동기화 플래그 리셋 (재방문 시 재동기화)
                    st.session_state.pop(f"char_mgmt_initialized_{project_path}", None)

                    status.empty()

                    # 모드별 아이콘
                    mode_icon = "🆕" if analysis_mode == "new" else "📝"
                    mode_text = "새로운 분석" if analysis_mode == "new" else "덮어쓰기"

                    if bundle_size > 1:
                        if is_partial:
                            st.success(f"✅ SRT 씬 적용 완료! [{mode_icon} {mode_text}] {analyzed_count}개 씬 분석 → 전체 {total_count}개 씬 ({bundle_summary.get('total_bundles', 0)}개 묶음) 저장됨")
                        else:
                            st.success(f"✅ SRT 씬 적용 완료! [{mode_icon} {mode_text}] {total_count}개 씬 ({bundle_summary.get('total_bundles', 0)}개 묶음)이 저장되었습니다.")
                    else:
                        if is_partial:
                            st.success(f"✅ SRT 씬 적용 완료! [{mode_icon} {mode_text}] {analyzed_count}개 씬 분석 → 전체 {total_count}개 씬 저장됨")
                        else:
                            st.success(f"✅ SRT 씬 적용 완료! [{mode_icon} {mode_text}] {total_count}개 씬이 저장되었습니다.")
                    st.balloons()

                    time.sleep(1)
                    st.rerun()

                except Exception as e:
                    st.error(f"❌ 오류 발생: {e}")
                    import traceback
                    with st.expander("오류 상세"):
                        st.code(traceback.format_exc())

            # 현재 로드된 씬 표시
            analysis_path = project_path / "analysis" / "full_analysis.json"
            if analysis_path.exists():
                st.divider()
                st.markdown("#### 📊 현재 로드된 씬")

                with open(analysis_path, "r", encoding="utf-8") as f:
                    saved_analysis = json.load(f)

                source = saved_analysis.get("source", st.session_state.get("analysis_source", "auto"))
                if source == "srt":
                    source_label = "🎬 SRT"
                elif source == "manual":
                    source_label = "📝 수동 입력"
                else:
                    source_label = "🤖 AI 자동 분석"

                # 묶음 메타데이터 확인
                bundle_meta = saved_analysis.get("bundle_metadata", {})
                has_bundles = bundle_meta.get("bundle_size", 1) > 1

                if has_bundles:
                    col1, col2, col3, col4, col5 = st.columns(5)
                else:
                    col1, col2, col3, col4 = st.columns(4)
                    col5 = None

                col1.metric("씬 수", len(saved_analysis.get("scenes", [])))
                col2.metric("캐릭터 수", len(saved_analysis.get("characters", [])))
                col3.metric("소스", source_label)

                # SRT 메타데이터 표시
                srt_meta = saved_analysis.get("srt_metadata", {})
                if srt_meta.get("has_time_codes"):
                    total_duration = srt_meta.get("total_duration", 0)
                    col4.metric("전체 길이", f"{int(total_duration // 60)}:{int(total_duration % 60):02d}")

                # 묶음 메타데이터 표시
                if has_bundles and col5:
                    col5.metric("📦 묶음", f"{bundle_meta.get('total_bundles', 0)}개 (x{bundle_meta.get('bundle_size', 1)})")

                # 묶음 상세 정보 표시
                if has_bundles:
                    with st.expander("📦 묶음 상세 정보"):
                        bundles_info = bundle_meta.get("bundles", [])
                        if bundles_info:
                            for bundle in bundles_info[:10]:  # 최대 10개까지 표시
                                scene_ids = bundle.get("scene_ids", [])
                                duration = bundle.get("duration", 0)
                                st.markdown(f"""
                                **묶음 {bundle.get('bundle_id')}**: 씬 {scene_ids[0] if scene_ids else '?'}-{scene_ids[-1] if scene_ids else '?'} | {duration:.1f}초 | {len(scene_ids)}개 씬
                                """)
                            if len(bundles_info) > 10:
                                st.caption(f"... 외 {len(bundles_info) - 10}개 묶음")

    # ═══════════════════════════════════════════════════════════════════
    # AI 자동 분석 모드
    # ═══════════════════════════════════════════════════════════════════
    elif analysis_mode == "auto":
        # 세션에서 스크립트 가져오기
        script = st.session_state.get("scene_analysis_script")

        if not script:
            st.warning("⚠️ 분석할 스크립트가 없습니다.")
            st.info("'스크립트 입력' 탭에서 스크립트를 선택하거나 입력하세요.")
            st.stop()

        st.info("""
        **씬 분석이란?**
        - 스크립트를 장면(씬) 단위로 자동 분할
        - 각 씬에 대한 연출가이드 생성
        - 등장 캐릭터 자동 추출
        - 이미지 프롬프트 자동 생성

        세모지 스타일의 고품질 콘텐츠를 위한 핵심 단계입니다.
        """)

        # API 선택
        st.markdown("### ⚙️ AI 설정")

        # API 상태 확인
        api_status = check_api_availability()

        col1, col2 = st.columns(2)

        with col1:
            # ═══════════════════════════════════════════════════════════
            # v3.40: Claude Code 옵션 추가 (v3.50 에이전트 방식 업그레이드)
            # ═══════════════════════════════════════════════════════════
            use_claude_code = st.checkbox(
                "🖥️ Claude Code 사용 (Max Plan 무료)",
                value=False,
                key="use_claude_code_for_analysis",
                help="Claude Code Max Plan을 사용하여 무료로 씬 분석합니다. Claude Code CLI가 설치되어 있어야 합니다."
            )

            if use_claude_code:
                # Claude Code 상태 확인 (새 함수 사용)
                try:
                    from utils.claude_code_runner import check_claude_code_installation
                    status = check_claude_code_installation()

                    if status['installed']:
                        st.success(f"✅ Claude Code 설치됨: {status['version']}")

                        # Claude Code 설정 옵션
                        with st.expander("⚙️ Claude Code 설정", expanded=False):
                            cc_col1, cc_col2 = st.columns(2)

                            with cc_col1:
                                claude_code_timeout = st.number_input(
                                    "타임아웃 (초)",
                                    min_value=60,
                                    max_value=1800,
                                    value=600,
                                    step=60,
                                    key="claude_code_timeout",
                                    help="분석 작업의 최대 실행 시간"
                                )

                            with cc_col2:
                                claude_code_bundle = st.checkbox(
                                    "묶음 모드 사용",
                                    value=True,
                                    key="claude_code_bundle_mode",
                                    help="동일한 bundle_id를 가진 씬들은 같은 프롬프트 공유"
                                )

                            claude_code_instructions = st.text_area(
                                "추가 지시사항 (선택)",
                                placeholder="예: 배경 프롬프트에 '네온 조명' 스타일 강조",
                                height=60,
                                key="claude_code_custom_instructions"
                            )

                            st.markdown("""
                            **Claude Code 장점:**
                            - 🆓 Max Plan 사용 시 API 비용 무료
                            - 🧠 Claude Opus 4 수준의 고품질 분석
                            - 📁 파일 직접 수정으로 빠른 처리
                            """)

                        # ═══════════════════════════════════════════════════════════
                        # v3.70: Claude Code 수동 실행 UI 추가 (Max Plan 무료 활용)
                        # ═══════════════════════════════════════════════════════════
                        scenes_json_path = project_path / "analysis" / "scenes.json"
                        if scenes_json_path.exists():
                            render_claude_code_manual_execution_ui(
                                project_path,
                                str(scenes_json_path)
                            )
                        else:
                            st.info("💡 먼저 아래 '씬 분석 시작' 버튼으로 기본 분석을 수행하세요. 그 후 수동 실행이 가능합니다.")
                    else:
                        st.error(f"❌ Claude Code CLI 미설치: {status['error']}")
                        st.code("npm i -g @anthropic-ai/claude-code", language="bash")

                except ImportError:
                    st.error("❌ claude_code_runner 모듈을 불러올 수 없습니다")
                selected_api = None  # Claude Code 사용 시 API 선택 비활성화
            else:
                selected_api = render_api_selector(
                    task="scene_analysis",
                    label="씬 분석 AI",
                    key_prefix="scene_analysis"
                )

                # 선택된 API 상태 표시
                if selected_api:
                    selected_lower = selected_api.lower() if isinstance(selected_api, str) else ""
                    if "gemini" in selected_lower or "google" in selected_lower:
                        status = api_status.get("gemini", {})
                        if not status.get("installed"):
                            st.error("❌ google-generativeai 패키지가 설치되지 않았습니다. `pip install google-generativeai` 실행 후 재시작하세요.")
                        elif not status.get("api_key"):
                            st.warning("⚠️ GOOGLE_API_KEY 또는 GEMINI_API_KEY가 설정되지 않았습니다.")
                    elif "gpt" in selected_lower or "openai" in selected_lower:
                        status = api_status.get("openai", {})
                        if not status.get("installed"):
                            st.error("❌ openai 패키지가 설치되지 않았습니다.")
                        elif not status.get("api_key"):
                            st.warning("⚠️ OPENAI_API_KEY가 설정되지 않았습니다.")

        with col2:
            # 프롬프트 템플릿 선택 (Content Type 대체)
            scene_templates = template_manager.get_templates_by_category("scene_analysis")
            template_map = {t.name: t.id for t in scene_templates}

            # 기본값 설정 ("기본 씬 분석" 또는 첫 번째)
            default_idx = 0
            default_keys = [k for k, v in template_map.items() if v == "scene_analysis"]
            if default_keys:
                default_idx = list(template_map.keys()).index(default_keys[0])

            selected_template_name = st.selectbox(
                "분석 프롬프트",
                list(template_map.keys()),
                index=default_idx,
                help="분석에 사용할 AI 프롬프트 스타일을 선택하세요."
            )
            selected_template_id = template_map[selected_template_name]

            # API 상태 요약
            with st.expander("🔌 API 상태", expanded=False):
                for api_name, info in api_status.items():
                    status_icon = info.get("status", "❓")
                    st.caption(f"{api_name}: {status_icon}")

        st.divider()

        # ═══════════════════════════════════════════════════════════
        # v3.35: 폴백 요청 처리
        # ═══════════════════════════════════════════════════════════
        fallback_requested = st.session_state.pop("_analysis_fallback_requested", False)
        fallback_provider = st.session_state.pop("_analysis_fallback_provider", None)

        if fallback_requested and fallback_provider:
            st.info(f"🔄 **{fallback_provider.upper()}**로 폴백 분석을 시작합니다...")

        # 분석 버튼
        if st.button("🎬 씬 분석 시작", type="primary", use_container_width=True) or fallback_requested:
            api_manager = get_api_manager()

            # 프로그레스 UI
            progress = StreamlitProgressUI(
                task_name="씬 분석",
                total_steps=4,
                show_logs=True
            )

            try:
                progress.update(1, "AI 분석기 초기화...")
                progress.info("스크립트 분석을 시작합니다.")

                # 디버그: 스크립트 정보 출력
                print(f"[씬 분석 페이지] 스크립트 로드됨: {len(script)} 문자")
                print(f"[씬 분석 페이지] 스크립트 미리보기: {script[:100]}...")
                progress.info(f"로드된 스크립트: {len(script)}자")

                # ═══════════════════════════════════════════════════════════
                # v3.60: Claude Code 에이전트 분석 모드 (드롭다운 통합)
                # ═══════════════════════════════════════════════════════════
                # 체크박스 또는 드롭다운에서 Claude Code 선택 여부 확인
                from utils.ai_model_selector import is_claude_code_selected as check_cc_selected
                use_claude_code_mode = use_claude_code or check_cc_selected("srt_model")

                if use_claude_code_mode and not fallback_requested:
                    from utils.claude_code_runner import (
                        run_scene_analysis_with_claude_code,
                        run_scene_analysis_agent,
                        enable_claude_cli,
                        SceneAnalysisResult
                    )

                    progress.info("🖥️ Claude Code 에이전트 모드로 분석합니다...")
                    print(f"[씬 분석 페이지] Claude Code 에이전트 모드 활성화")

                    # Claude CLI 활성화 (비활성화 상태일 수 있음)
                    enable_claude_cli()

                    # UI에서 설정값 가져오기 (드롭다운 설정 우선, 없으면 체크박스 설정)
                    cc_timeout = st.session_state.get("srt_claude_code_timeout", st.session_state.get("claude_code_timeout", 600))
                    cc_bundle = st.session_state.get("srt_claude_code_bundle_mode", st.session_state.get("claude_code_bundle_mode", True))
                    cc_instructions = st.session_state.get("srt_claude_code_custom_instructions", st.session_state.get("claude_code_custom_instructions", ""))

                    # 기존 scenes.json이 있는지 확인
                    scenes_json_path = project_path / "analysis" / "scenes.json"
                    analysis_dir = project_path / "analysis"
                    analysis_dir.mkdir(parents=True, exist_ok=True)

                    # 기존 scenes.json이 있으면 에이전트로 프롬프트만 추가
                    # 없으면 기존 방식으로 전체 분석
                    use_agent_mode = scenes_json_path.exists()

                    progress.update(2, "Claude Code 실행 중...")

                    def progress_cb(msg):
                        progress.info(msg)

                    start_time = time.time()

                    if use_agent_mode:
                        # 에이전트 모드: 기존 scenes.json에 프롬프트 필드 추가
                        progress.info("📝 기존 씬 데이터에 프롬프트 추가 (에이전트 모드)...")
                        print(f"[씬 분석 페이지] 에이전트 모드: scenes.json 보강")

                        agent_result = run_scene_analysis_agent(
                            scenes_json_path=str(scenes_json_path),
                            project_path=str(project_path),
                            scene_range=None,  # 전체 씬
                            bundle_mode=cc_bundle,
                            custom_instructions=cc_instructions,
                            timeout=cc_timeout,
                            progress_callback=progress_cb
                        )

                        elapsed = time.time() - start_time

                        # ═══════════════════════════════════════════════════════════
                        # v3.70: AGENT_MODE_REQUIRED 처리 (subprocess 비활성화)
                        # ═══════════════════════════════════════════════════════════
                        if agent_result.error == "AGENT_MODE_REQUIRED":
                            # 에이전트 모드: 프롬프트 복사 + 수동 실행 또는 자동 실행
                            progress.update(4, "에이전트 모드: 실행 방법 선택")

                            st.warning("🤖 **Claude Code 에이전트 모드**")

                            st.info("""
                            **Claude Code Max Plan을 사용하여 무료로 분석합니다!**

                            - 🚀 **자동 실행**: 버튼 클릭 → 새 CMD 창에서 자동 실행
                            - 📋 **수동 실행**: 프롬프트 복사 → Claude Code 앱에서 붙여넣기
                            """)

                            # 프롬프트 정보 가져오기
                            prompt_text = agent_result.output  # 프롬프트가 output에 저장됨
                            fields_info = agent_result.fields_generated or {}
                            prompt_file = fields_info.get('prompt_file', '')

                            # 세션에 저장
                            st.session_state['claude_code_prompt'] = prompt_text
                            st.session_state['claude_code_prompt_file'] = prompt_file
                            st.session_state['claude_code_scenes_path'] = str(scenes_json_path)
                            st.session_state['claude_code_agent_ready'] = True

                            # ═══════════════════════════════════════════════════════════
                            # v3.71: 자동 실행 버튼 추가
                            # ═══════════════════════════════════════════════════════════
                            st.markdown("### 🚀 자동 실행 (권장)")

                            auto_col1, auto_col2 = st.columns([3, 2])

                            with auto_col1:
                                if st.button("🚀 Claude Code 자동 실행", type="primary", use_container_width=True, key="auto_execute_claude_code"):
                                    try:
                                        from utils.claude_code_runner import execute_claude_code_in_new_window

                                        # 자동 실행
                                        auto_result = execute_claude_code_in_new_window(
                                            prompt_text=prompt_text,
                                            project_path=str(project_path),
                                            scenes_json_path=str(scenes_json_path)
                                        )

                                        if auto_result.success:
                                            st.success("✅ Claude Code가 새 창에서 실행되었습니다!")

                                            # 세션에 실행 정보 저장
                                            st.session_state['claude_code_auto_executed'] = True
                                            st.session_state['claude_code_batch_file'] = auto_result.batch_file
                                            st.session_state['claude_code_running'] = True
                                            st.session_state['claude_code_start_time'] = time.time()
                                            st.rerun()  # 진행률 표시를 위해 리런
                                        else:
                                            st.error(f"❌ 실행 오류: {auto_result.error}")

                                    except Exception as e:
                                        st.error(f"❌ 자동 실행 실패: {e}")
                                        import traceback
                                        st.code(traceback.format_exc())

                            with auto_col2:
                                if st.button("🔄 결과 확인", use_container_width=True, key="check_result_auto"):
                                    # scenes.json 다시 로드
                                    try:
                                        with open(scenes_json_path, 'r', encoding='utf-8') as f:
                                            data = json.load(f)

                                        reload_scenes = data.get('scenes', data) if isinstance(data, dict) else data

                                        if reload_scenes:
                                            stats = check_scenes_analysis_status(reload_scenes)

                                            if stats['background_prompt_en'] > 0:
                                                st.success(f"✅ 분석 결과 감지! {stats['background_prompt_en']}/{stats['total']} 씬 완료")
                                                st.session_state['scenes'] = reload_scenes
                                                st.session_state['_agent_analysis_stats'] = stats
                                                st.balloons()
                                                time.sleep(1)
                                                st.rerun()
                                            else:
                                                st.warning("아직 분석 결과가 없습니다. Claude Code 실행이 완료될 때까지 기다려주세요.")
                                    except Exception as e:
                                        st.error(f"파일 로드 실패: {e}")

                            # ═══════════════════════════════════════════════════════════
                            # 실시간 진행률 표시 (Claude Code 실행 중일 때)
                            # ═══════════════════════════════════════════════════════════
                            if st.session_state.get('claude_code_running', False):
                                st.markdown("---")
                                st.markdown("### 📊 실시간 진행률")

                                progress_container = st.empty()
                                status_container = st.empty()
                                time_container = st.empty()
                                action_container = st.empty()

                                # 진행률 파일 읽기
                                from utils.claude_code_runner import get_claude_code_progress, check_claude_code_completion

                                progress_data = get_claude_code_progress(str(project_path))
                                is_complete = check_claude_code_completion(str(project_path))

                                if is_complete:
                                    # 완료됨 - 자동 로드
                                    progress_container.progress(1.0)
                                    status_container.success("✅ **분석 완료!** 결과를 로드합니다...")

                                    # 결과 로드
                                    try:
                                        with open(scenes_json_path, 'r', encoding='utf-8') as f:
                                            data = json.load(f)
                                        reload_scenes = data.get('scenes', data) if isinstance(data, dict) else data

                                        if reload_scenes:
                                            stats = check_scenes_analysis_status(reload_scenes)
                                            st.session_state['scenes'] = reload_scenes
                                            st.session_state['_agent_analysis_stats'] = stats
                                            st.session_state['claude_code_running'] = False

                                            # 파일 정리
                                            from utils.claude_code_runner import cleanup_claude_code_files
                                            cleanup_claude_code_files(str(project_path))

                                            st.balloons()
                                            time.sleep(1)
                                            st.rerun()
                                    except Exception as e:
                                        status_container.error(f"결과 로드 실패: {e}")
                                        st.session_state['claude_code_running'] = False

                                elif progress_data:
                                    # 진행 중 - 상태 표시
                                    status = progress_data.get('status', 'unknown')
                                    current = progress_data.get('current', 0)
                                    total = progress_data.get('total', 1)
                                    message = progress_data.get('message', '')

                                    pct = min(current / total, 0.99) if total > 0 else 0

                                    progress_container.progress(pct)

                                    if status == 'running':
                                        status_container.info(f"🔄 **분석 중...** ({current}/{total} 씬)")
                                    elif status == 'starting':
                                        status_container.info("🚀 **Claude Code 시작 중...**")
                                    else:
                                        status_container.info(f"⏳ 상태: {status}")

                                    if message:
                                        time_container.caption(message)

                                    # 경과 시간
                                    start_time = st.session_state.get('claude_code_start_time', time.time())
                                    elapsed = int(time.time() - start_time)
                                    time_container.caption(f"⏱️ 경과 시간: {elapsed}초")

                                    # 자동 새로고침 (2초마다)
                                    time.sleep(2)
                                    st.rerun()

                                else:
                                    # 진행률 파일 없음 - 대기 중
                                    progress_container.progress(0.0)
                                    status_container.info("⏳ **Claude Code 대기 중...**")

                                    start_time = st.session_state.get('claude_code_start_time', time.time())
                                    elapsed = int(time.time() - start_time)
                                    time_container.caption(f"⏱️ 경과 시간: {elapsed}초")

                                    # 타임아웃 체크 (10분)
                                    if elapsed > 600:
                                        status_container.error("❌ 타임아웃 (10분 초과)")
                                        st.session_state['claude_code_running'] = False
                                    else:
                                        time.sleep(2)
                                        st.rerun()

                                # 취소 버튼
                                if action_container.button("🛑 진행률 모니터링 중지", key="stop_progress_monitor"):
                                    st.session_state['claude_code_running'] = False
                                    st.rerun()

                            # ─────────────────────────────────────────────────────────
                            # 수동 실행 옵션 (접힌 상태)
                            # ─────────────────────────────────────────────────────────
                            with st.expander("📋 수동 실행 (대안)", expanded=False):
                                st.markdown("""
                                **수동 실행 방법:**
                                1. "프롬프트 복사" 버튼 클릭
                                2. Claude Code 앱 열기 (`cd longform && claude`)
                                3. 프롬프트 붙여넣기
                                4. 완료 후 "결과 확인" 버튼 클릭
                                """)

                                manual_col1, manual_col2, manual_col3 = st.columns([2, 2, 1])

                                with manual_col1:
                                    if st.button("📋 프롬프트 복사", use_container_width=True, key="copy_prompt_agent_mode"):
                                        try:
                                            import pyperclip
                                            pyperclip.copy(prompt_text)
                                            st.success("✅ 클립보드에 복사되었습니다!")
                                        except ImportError:
                                            st.warning("pyperclip 패키지가 없습니다.")
                                            st.code(prompt_text[:500] + "...", language="markdown")
                                        except Exception as e:
                                            st.error(f"복사 실패: {e}")

                                with manual_col2:
                                    if st.button("🔄 결과 확인 + Bundle 병합", use_container_width=True, key="check_result_manual"):
                                        try:
                                            # v13.13: Bundle 병합 적용
                                            from utils.claude_code_runner import sync_claude_code_results_with_bundle_merge
                                            video_path = str(Path(scenes_json_path).parent.parent)

                                            with st.spinner("Bundle 병합 적용 중..."):
                                                merge_result = sync_claude_code_results_with_bundle_merge(video_path)

                                            if merge_result.get('success'):
                                                reload_scenes = merge_result.get('scenes', [])
                                                merged_count = merge_result.get('merged_count', 0)

                                                if reload_scenes:
                                                    stats = check_scenes_analysis_status(reload_scenes)
                                                    if stats['background_prompt_en'] > 0:
                                                        st.success(f"✅ {stats['background_prompt_en']}/{stats['total']} 씬 완료 (Bundle 병합: {merged_count}개)")

                                                        # session_state 업데이트
                                                        sync_data = merge_result.get('sync_data', {})
                                                        for key, value in sync_data.items():
                                                            st.session_state[key] = value

                                                        st.session_state['scenes'] = reload_scenes
                                                        st.balloons()
                                                        time.sleep(0.5)
                                                        st.rerun()
                                                    else:
                                                        st.warning("아직 분석 결과가 없습니다.")
                                                else:
                                                    st.warning("scenes.json이 비어있습니다.")
                                            else:
                                                st.error(f"Bundle 병합 실패: {merge_result.get('error', '알 수 없는 오류')}")
                                        except ImportError:
                                            # 폴백: 기존 방식
                                            try:
                                                with open(scenes_json_path, 'r', encoding='utf-8') as f:
                                                    data = json.load(f)
                                                reload_scenes = data.get('scenes', data) if isinstance(data, dict) else data
                                                if reload_scenes:
                                                    stats = check_scenes_analysis_status(reload_scenes)
                                                    if stats['background_prompt_en'] > 0:
                                                        st.success(f"✅ {stats['background_prompt_en']}/{stats['total']} 씬 완료")
                                                        st.session_state['scenes'] = reload_scenes
                                                        st.rerun()
                                                    else:
                                                        st.warning("아직 분석 결과가 없습니다.")
                                            except Exception as e:
                                                st.error(f"파일 로드 실패: {e}")
                                        except Exception as e:
                                            st.error(f"Bundle 병합 오류: {e}")

                                with manual_col3:
                                    if st.button("📂", help="폴더 열기", key="open_folder_agent_mode"):
                                        try:
                                            os.startfile(os.path.dirname(str(scenes_json_path)))
                                        except Exception as e:
                                            st.error(f"폴더 열기 실패: {e}")

                                # 프롬프트 미리보기
                                st.markdown("**프롬프트 미리보기:**")
                                st.code(prompt_text, language="markdown")

                                # Claude Code 실행 명령어
                                st.markdown("**Claude Code 실행:**")
                                st.code("cd C:\\Users\\KIMJAEHEON\\longform\nclaude", language="bash")

                            # 작업 중단 (에이전트 모드에서는 더 이상 진행하지 않음)
                            st.stop()

                        elif agent_result.success:
                            # ═══════════════════════════════════════════════════════════
                            # v3.90: 'running' 상태 처리 - 실제 완료까지 대기
                            # ═══════════════════════════════════════════════════════════
                            fields_info = agent_result.fields_generated or {}

                            if fields_info.get('status') == 'running':
                                # CMD 창이 열렸지만 아직 분석 진행 중
                                progress.update(3, "Claude Code 분석 진행 중...")

                                st.info("🖥️ **새 CMD 창에서 Claude Code가 실행 중입니다.**")
                                st.warning("분석이 완료될 때까지 기다려주세요. 완료 후 자동으로 결과를 로드합니다.")

                                # 세션에 실행 정보 저장
                                st.session_state['claude_code_running'] = True
                                st.session_state['claude_code_start_time'] = time.time()
                                st.session_state['claude_code_batch_file'] = fields_info.get('batch_file', '')
                                st.session_state['claude_code_scenes_path'] = str(scenes_json_path)

                                # 실시간 폴링 UI
                                from utils.claude_code_runner import get_claude_code_progress, check_claude_code_completion, clear_completion_flag

                                # 기존 완료 플래그 삭제 (stale flag 방지)
                                clear_completion_flag(str(project_path))

                                progress_placeholder = st.empty()
                                status_placeholder = st.empty()
                                time_placeholder = st.empty()

                                # 폴링 루프 (최대 10분)
                                max_wait = 600  # 10분
                                poll_interval = 2  # 2초마다 확인
                                wait_elapsed = 0

                                while wait_elapsed < max_wait:
                                    is_complete = check_claude_code_completion(str(project_path))
                                    progress_data = get_claude_code_progress(str(project_path))

                                    if is_complete:
                                        progress_placeholder.progress(1.0)
                                        status_placeholder.success("✅ **분석이 완료되었습니다!**")
                                        st.session_state['claude_code_running'] = False

                                        # 결과 로드
                                        with open(scenes_json_path, 'r', encoding='utf-8') as f:
                                            scenes_data = json.load(f)
                                        success = True
                                        message = f"분석 완료"

                                        # 분석 통계 확인
                                        reload_scenes = scenes_data.get('scenes', scenes_data) if isinstance(scenes_data, dict) else scenes_data
                                        if reload_scenes:
                                            stats = check_scenes_analysis_status(reload_scenes)
                                            message = f"분석 완료 ({stats.get('background_prompt_en', 0)}/{stats.get('total', 0)} 씬)"
                                        break
                                    else:
                                        # 진행률 표시
                                        if progress_data:
                                            pct = progress_data.get('progress', 0)
                                            status_msg = progress_data.get('status', '분석 중...')
                                            progress_placeholder.progress(min(pct / 100, 0.99))
                                            status_placeholder.info(f"📝 {status_msg}")
                                        else:
                                            progress_placeholder.progress(min(wait_elapsed / max_wait, 0.5))
                                            status_placeholder.info("📝 Claude Code 분석 중...")

                                        time_placeholder.caption(f"⏱️ 경과 시간: {int(wait_elapsed)}초")
                                        time.sleep(poll_interval)
                                        wait_elapsed += poll_interval

                                if wait_elapsed >= max_wait:
                                    # 타임아웃
                                    success = False
                                    message = "분석 타임아웃 (10분 초과)"
                                    scenes_data = None
                                    st.session_state['claude_code_running'] = False
                            else:
                                # 기존 레거시 처리 (status가 없는 경우)
                                with open(scenes_json_path, 'r', encoding='utf-8') as f:
                                    scenes_data = json.load(f)
                                success = True
                                message = f"분석 완료 ({agent_result.scenes_analyzed}개 씬)"

                                # 분석 통계 표시
                                if agent_result.fields_generated:
                                    stats_msg = ", ".join([f"{k}: {v}" for k, v in agent_result.fields_generated.items()])
                                    progress.info(f"📊 생성된 필드: {stats_msg}")
                        else:
                            success = False
                            message = agent_result.error
                            scenes_data = None
                    else:
                        # 기존 방식: 스크립트에서 새로 분석
                        progress.info("📝 스크립트에서 새로 분석...")
                        print(f"[씬 분석 페이지] 기존 방식: 스크립트 분석")

                        # 임시 스크립트 파일 저장
                        script_file = project_path / "analysis" / "temp_script.txt"
                        script_file.write_text(script, encoding='utf-8')

                        success, message, scenes_data = run_scene_analysis_with_claude_code(
                            script_path=str(script_file),
                            output_path=str(scenes_json_path),
                            language=language,
                            timeout=cc_timeout,
                            progress_callback=progress_cb
                        )
                        elapsed = time.time() - start_time

                    if success and scenes_data:
                        progress.update(3, "결과 저장 중...")

                        # 결과 구성
                        result = {
                            "scenes": scenes_data,
                            "characters": [],  # 캐릭터는 씬에서 추출
                            "total_scenes": len(scenes_data),
                            "estimated_duration": sum(s.get("duration_estimate", 0) for s in scenes_data)
                        }

                        # character_prompt -> characters 후처리 동기화
                        try:
                            from utils.character_sync import sync_all_scenes_characters, extract_all_characters_from_scenes
                            scenes_data, _sync_cnt = sync_all_scenes_characters(scenes_data)
                            if _sync_cnt > 0:
                                print(f"[후처리] {_sync_cnt}개 씬 characters 배열 동기화")
                                result["scenes"] = scenes_data
                        except Exception as _e:
                            print(f"[후처리] 동기화 오류 (무시): {_e}")

                        # 캐릭터 추출 (dict/string 모두 지원)
                        try:
                            from utils.character_sync import extract_all_characters_from_scenes
                            extracted_chars = extract_all_characters_from_scenes(scenes_data)
                            result["characters"] = extracted_chars
                        except Exception:
                            all_characters = set()
                            for scene in scenes_data:
                                for char in scene.get("characters", []):
                                    if isinstance(char, str) and char:
                                        all_characters.add(char)
                                    elif isinstance(char, dict) and char.get("name"):
                                        all_characters.add(char["name"])
                            result["characters"] = [{"name": c} for c in all_characters]

                        # 파일 저장
                        analysis_dir = project_path / "analysis"
                        with open(analysis_dir / "characters.json", "w", encoding="utf-8") as f:
                            json.dump(result.get("characters", []), f, ensure_ascii=False, indent=2)
                        with open(analysis_dir / "full_analysis.json", "w", encoding="utf-8") as f:
                            json.dump(result, f, ensure_ascii=False, indent=2)

                        # 세션 저장
                        scenes = result.get("scenes", [])
                        characters = result.get("characters", [])
                        st.session_state["scene_analysis_result"] = result
                        st.session_state["scenes"] = scenes
                        st.session_state["characters"] = characters
                        st.session_state["scene_characters"] = characters
                        st.session_state["extracted_characters"] = characters

                        # 캐시 클리어
                        clear_scene_cache(str(project_path))
                        # 캐릭터 관리 페이지 동기화 플래그 리셋 (재방문 시 재동기화)
                        st.session_state.pop(f"char_mgmt_initialized_{project_path}", None)

                        progress.update(4, "완료!")
                        progress.complete(f"Claude Code: 씬 {len(scenes)}개, 캐릭터 {len(characters)}명 추출 완료!")
                        st.success(f"✅ Claude Code 분석 완료 ({elapsed:.1f}초)")

                        time.sleep(1)
                        st.rerun()
                    else:
                        # Claude Code 실패 시 Gemini 폴백 제안
                        progress.fail(f"Claude Code 실패: {message}")
                        st.error(f"❌ Claude Code 분석 실패: {message}")

                        col_retry1, col_retry2 = st.columns(2)
                        with col_retry1:
                            if st.button("🔄 Gemini로 다시 분석", type="primary"):
                                st.session_state["_analysis_fallback_requested"] = True
                                st.session_state["_analysis_fallback_provider"] = "google"
                                st.rerun()
                        with col_retry2:
                            if st.button("🔄 다시 시도"):
                                st.rerun()
                        raise Exception(f"Claude Code 분석 실패: {message}")

                # ═══════════════════════════════════════════════════════════
                # 기존 API 기반 분석
                # ═══════════════════════════════════════════════════════════
                else:
                    from core.script.scene_analyzer import SceneAnalyzer

                    # ⭐ v3.35: 폴백 요청 시 provider 강제 설정
                    if fallback_requested and fallback_provider:
                        provider = fallback_provider
                        model_name = None  # 기본 모델 사용
                        max_output_tokens = 65536
                        print(f"[씬 분석 페이지] 🔄 폴백 분석: provider={provider}")
                        progress.info(f"🔄 폴백 모드: {provider.upper()} 사용")

                    # ⭐ API 매니저에서 선택된 API 정보 가져오기
                    elif selected_api:
                        api_config = api_manager.get_api_by_id(selected_api)

                        if api_config:
                            provider = api_config.provider
                            model_name = api_config.model_id
                            max_output_tokens = api_config.max_output_tokens
                            print(f"[씬 분석 페이지] 선택된 API: {selected_api}")
                            print(f"[씬 분석 페이지]   provider: {provider}")
                            print(f"[씬 분석 페이지]   model_id: {model_name}")
                            print(f"[씬 분석 페이지]   max_output_tokens: {max_output_tokens:,}")
                        else:
                            # 폴백: 키워드 기반으로 provider 결정
                            provider = "anthropic"  # 기본값
                            model_name = None
                            max_output_tokens = 65536
                            selected_lower = selected_api.lower() if isinstance(selected_api, str) else ""
                            if "gemini" in selected_lower or "google" in selected_lower:
                                provider = "google"
                            elif "gpt" in selected_lower or "openai" in selected_lower:
                                provider = "openai"
                            elif "claude" in selected_lower or "anthropic" in selected_lower:
                                provider = "anthropic"
                            print(f"[씬 분석 페이지] 폴백 모드: {selected_api} -> provider: {provider}")
                    else:
                        # 기본값
                        provider = "google"  # 기본은 Gemini (무료)
                        model_name = None
                        max_output_tokens = 65536
                        print(f"[씬 분석 페이지] 기본 provider 사용: {provider}")

                    # ⭐ 모델명과 max_output_tokens를 SceneAnalyzer에 전달
                    analyzer = SceneAnalyzer(
                        provider=provider,
                        model_name=model_name,
                        max_output_tokens=max_output_tokens
                    )

                    progress.update(2, "스크립트 분석 중...")
                    progress.info(f"사용 프롬프트: {selected_template_name}")
                    progress.info(f"스크립트 길이: {len(script):,}자")

                    # ⭐ 실제 사용되는 모델 상세 표시
                    if provider == "google" and hasattr(analyzer, 'gemini_model_name'):
                        actual_tokens = getattr(analyzer, 'max_output_tokens', 65536)
                        progress.info(f"🤖 사용 AI: {analyzer.gemini_model_name}")
                        progress.info(f"📊 최대 출력: {actual_tokens:,} 토큰")
                    else:
                        progress.info(f"🤖 사용 AI: {provider}")

                    start_time = time.time()
                    result = analyzer.analyze_script(script, language, template_id=selected_template_id)
                    elapsed = time.time() - start_time

                    # 디버그: 결과 확인
                    print(f"[씬 분석 페이지] 분석 결과: 씬 {len(result.get('scenes', []))}개, 캐릭터 {len(result.get('characters', []))}개")
                    if result.get('error'):
                        print(f"[씬 분석 페이지] 오류: {result.get('error')}")
                        progress.info(f"분석 오류: {result.get('error')}")

                    progress.update(3, "결과 저장 중...")

                    # 결과 저장
                    analysis_dir = project_path / "analysis"
                    analysis_dir.mkdir(parents=True, exist_ok=True)

                    # 🔴 저장 전 검증 및 자동 수정 (background_prompt_en 불일치 해결)
                    scenes_to_save = result.get("scenes", [])
                    if scenes_to_save and SCENE_VALIDATOR_AVAILABLE:
                        scenes_to_save = validate_scenes_before_save(scenes_to_save, verbose=True)
                        result["scenes"] = scenes_to_save

                    # character_prompt -> characters 후처리 동기화
                    try:
                        from utils.character_sync import sync_all_scenes_characters, update_characters_json
                        scenes_to_save, _sync_cnt = sync_all_scenes_characters(scenes_to_save)
                        if _sync_cnt > 0:
                            print(f"[후처리] {_sync_cnt}개 씬 characters 배열 동기화")
                            result["scenes"] = scenes_to_save
                    except Exception as _e:
                        print(f"[후처리] 동기화 오류 (무시): {_e}")

                    with open(analysis_dir / "scenes.json", "w", encoding="utf-8") as f:
                        json.dump(scenes_to_save, f, ensure_ascii=False, indent=2)

                    with open(analysis_dir / "characters.json", "w", encoding="utf-8") as f:
                        json.dump(result.get("characters", []), f, ensure_ascii=False, indent=2)

                    # characters.json에 씬 기반 캐릭터 추가
                    try:
                        from utils.character_sync import update_characters_json as _update_cj
                        _update_cj(scenes_to_save, analysis_dir / "characters.json")
                    except Exception:
                        pass

                    with open(analysis_dir / "full_analysis.json", "w", encoding="utf-8") as f:
                        json.dump(result, f, ensure_ascii=False, indent=2)

                    # === 세션에도 저장 (캐릭터 관리 페이지 연동용) ===
                    scenes = result.get("scenes", [])
                    characters = result.get("characters", [])

                    st.session_state["scene_analysis_result"] = result
                    st.session_state["scenes"] = scenes
                    st.session_state["characters"] = characters
                    # 캐릭터 관리 페이지 호환용 키
                    st.session_state["scene_characters"] = characters
                    st.session_state["extracted_characters"] = characters

                    # 다른 페이지 캐시 클리어 (Problem 56)
                    clear_scene_cache(str(project_path))
                    # 캐릭터 관리 페이지 동기화 플래그 리셋 (재방문 시 재동기화)
                    st.session_state.pop(f"char_mgmt_initialized_{project_path}", None)

                    print(f"[씬 분석 페이지] 세션 저장 완료: 씬 {len(scenes)}개, 캐릭터 {len(characters)}개")

                    # 캐릭터 visual_prompt 디버그 출력
                    for char in characters[:3]:  # 처음 3개만
                        name = char.get("name", "Unknown")
                        has_prompt = bool(char.get("visual_prompt"))
                        print(f"  - {name}: visual_prompt={'있음' if has_prompt else '없음'}")

                    # 사용량 기록 (provider에 따른 모델 ID 결정)
                    model_id_map = {
                        "anthropic": "claude-sonnet-4-20250514",
                        "google": "gemini-2.5-flash",
                        "openai": "gpt-4o"
                    }
                    record_model_id = model_id_map.get(provider, "claude-sonnet-4-20250514")

                    api_manager.record_usage(
                        provider=provider,
                        model_id=record_model_id,
                        function="text_generation",
                        tokens_input=len(script) // 4,
                        tokens_output=len(json.dumps(result)) // 4,
                        duration_seconds=elapsed,
                        success=True,
                        project_name=project_path.name,
                        step_name="scene_analysis"
                    )

                    progress.update(4, "완료!")

                    scene_count = result.get("total_scenes", len(result.get("scenes", [])))
                    char_count = len(result.get("characters", []))
                    progress.complete(f"씬 {scene_count}개, 캐릭터 {char_count}명 추출 완료!")

                    time.sleep(1)
                    st.rerun()

            except Exception as e:
                elapsed = time.time() - start_time if 'start_time' in dir() else 0

                # ═══════════════════════════════════════════════════════════
                # v3.35: 개선된 API 에러 처리
                # v3.40: Claude Code 모드 에러 처리 추가
                # ═══════════════════════════════════════════════════════════

                # provider가 정의되어 있지 않으면 기본값 설정 (Claude Code 모드)
                if 'provider' not in dir() or provider is None:
                    provider = "claude_code" if use_claude_code else "google"

                try:
                    from utils.api_error_handler import (
                        extract_error_from_exception,
                        get_error_display_message,
                        is_credit_error,
                        is_fallback_recommended,
                        APIErrorType
                    )

                    # 에러 파싱
                    api_error = extract_error_from_exception(e, provider=provider)

                    # 에러 타입별 처리
                    if api_error.error_type == APIErrorType.CREDIT_INSUFFICIENT:
                        progress.fail("💳 API 크레딧 부족")
                        st.error(get_error_display_message(api_error))

                        # 폴백 옵션 제공
                        st.markdown("---")
                        col_fb1, col_fb2 = st.columns(2)
                        with col_fb1:
                            fallback_provider = "Gemini" if provider == "anthropic" else "Claude"
                            if st.button(f"🔄 {fallback_provider}로 다시 분석", type="primary", key="fallback_btn"):
                                # 세션에 폴백 요청 저장
                                st.session_state["_analysis_fallback_requested"] = True
                                st.session_state["_analysis_fallback_provider"] = "google" if provider == "anthropic" else "anthropic"
                                st.rerun()
                        with col_fb2:
                            if provider == "anthropic":
                                st.link_button("💳 크레딧 충전하기", "https://console.anthropic.com/settings/billing")

                    elif api_error.error_type == APIErrorType.RATE_LIMIT:
                        progress.fail("⏱️ API 속도 제한")
                        st.warning(get_error_display_message(api_error))
                        retry_seconds = api_error.retry_after_seconds or 30
                        st.info(f"💡 {retry_seconds}초 후 자동 재시도하거나, 다른 모델로 전환하세요.")

                    elif api_error.error_type == APIErrorType.AUTHENTICATION:
                        progress.fail("🔑 API 인증 실패")
                        st.error(get_error_display_message(api_error))
                        st.info("💡 API 관리 페이지에서 API 키를 확인하세요.")

                    else:
                        # 기타 에러
                        progress.fail(str(e)[:100])
                        st.error(get_error_display_message(api_error))

                        if api_error.fallback_available:
                            fallback_provider = "Gemini" if provider == "anthropic" else "Claude"
                            if st.button(f"🔄 {fallback_provider}로 다시 시도", key="fallback_other_btn"):
                                st.session_state["_analysis_fallback_requested"] = True
                                st.session_state["_analysis_fallback_provider"] = "google" if provider == "anthropic" else "anthropic"
                                st.rerun()

                except ImportError:
                    # api_error_handler import 실패 시 기존 동작
                    progress.fail(str(e))
                    st.error(f"❌ 분석 실패: {e}")

                # 에러 기록 (provider에 따른 모델 ID 결정)
                model_id_map = {
                    "anthropic": "claude-sonnet-4-20250514",
                    "google": "gemini-2.5-flash",
                    "openai": "gpt-4o"
                }
                record_model_id = model_id_map.get(provider, "claude-sonnet-4-20250514")

                api_manager.record_usage(
                    provider=provider,
                    model_id=record_model_id,
                    function="text_generation",
                    duration_seconds=elapsed,
                    success=False,
                    error_message=str(e),
                    project_name=project_path.name,
                    step_name="scene_analysis"
                )

                # 디버그 정보 (접힌 상태)
                with st.expander("🔧 디버그 정보", expanded=False):
                    import traceback
                    st.code(traceback.format_exc())

        # 기존 분석 결과 로드
        analysis_path = project_path / "analysis" / "full_analysis.json"
        if analysis_path.exists():
            with open(analysis_path, "r", encoding="utf-8") as f:
                saved_analysis = json.load(f)

            # ⭐ 저장된 분석 메타데이터 세션에 복원
            saved_metadata = saved_analysis.get("analysis_metadata", {})
            if saved_metadata:
                if saved_analysis.get("prompt_used") and 'prompt_template' not in saved_metadata:
                    saved_metadata['prompt_template'] = saved_analysis.get("prompt_used")
                st.session_state["analysis_metadata"] = saved_metadata

            st.divider()
            st.subheader("📊 분석 결과")

            scenes = saved_analysis.get("scenes", [])
            characters = saved_analysis.get("characters", [])

            # v3.36: script_ko 우선 체크 추가
            def get_script(s):
                return s.get("script_ko") or s.get("script_text", "")

            # 통계 계산
            total_chars = sum(len(get_script(s)) for s in scenes) if scenes else 0
            avg_chars = total_chars // len(scenes) if scenes else 0
            max_chars = max(len(get_script(s)) for s in scenes) if scenes else 0
            over_250_count = sum(1 for s in scenes if len(get_script(s)) > 250)

            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("총 씬 수", len(scenes))
            with col2:
                char_count_label = f"{len(characters)}" if characters else "0 ⚠️"
                st.metric("캐릭터 수", char_count_label)
            with col3:
                total_duration = sum(s.get("duration_estimate", 10) for s in scenes)
                st.metric("예상 길이", f"{total_duration // 60}분 {total_duration % 60}초")
            with col4:
                avg_label = f"{avg_chars}자" if avg_chars <= 250 else f"{avg_chars}자 ⚠️"
                st.metric("평균 글자수", avg_label)

            # 경고 메시지
            if not characters:
                st.warning("⚠️ 캐릭터가 추출되지 않았습니다. 분석 프롬프트를 확인하거나 씬 분석을 다시 실행하세요.")

            if over_250_count > 0:
                st.warning(f"⚠️ {over_250_count}개 씬이 250자를 초과합니다. Chatterbox TTS 최적화를 위해 씬을 더 나눠주세요.")

            # 씬 목록 표시
            st.subheader("🎬 씬 목록")

            for i, scene in enumerate(scenes):
                scene_id = scene.get('scene_id', i+1)
                # v3.36: script_ko 우선 체크 (위에서 정의한 get_script 사용)
                script_text = get_script(scene)
                script_preview = script_text[:50]
                char_count = len(script_text)

                # 글자 수 경고 표시
                char_warning = " ⚠️" if char_count > 250 else ""

                with st.expander(f"씬 {scene_id}: {script_preview}...{char_warning}", expanded=False):
                    # === 상단: 기본 정보 ===
                    col_info1, col_info2, col_info3, col_info4 = st.columns(4)
                    with col_info1:
                        st.metric("글자 수", f"{char_count}자")
                    with col_info2:
                        duration = scene.get("duration_estimate", 0)
                        st.metric("예상 시간", f"{duration}초")
                    with col_info3:
                        chars = scene.get("characters", [])
                        st.metric("캐릭터", f"{len(chars)}명")
                    with col_info4:
                        st.metric("분위기", scene.get("mood", "-"))

                    if char_count > 250:
                        st.warning(f"⚠️ 씬이 {char_count}자입니다. TTS 최적화를 위해 250자 이하로 분할을 권장합니다.")

                    st.divider()

                    col_left, col_right = st.columns([1, 1])

                    with col_left:
                        st.markdown("**📝 스크립트**")
                        st.write(script_text)

                        st.markdown("**🎬 연출가이드**")
                        direction = scene.get("direction_guide", "")
                        if direction:
                            st.info(direction)
                        else:
                            st.caption("(없음)")

                        st.markdown("**👤 등장 캐릭터**")
                        if chars:
                            st.write(format_character_names(chars))
                        else:
                            st.caption("없음")

                    with col_right:
                        st.markdown("**📐 시각 요소**")
                        elements = scene.get("visual_elements", [])
                        if elements:
                            st.write(", ".join(elements))
                        else:
                            st.caption("(없음)")

                        st.markdown("**📷 카메라**")
                        camera = scene.get("camera_suggestion", "")
                        if camera:
                            st.write(camera)
                        else:
                            st.caption("(없음)")

                    st.divider()

                    # === 프롬프트 탭 ===
                    st.markdown("**🎨 AI 프롬프트**")
                    prompt_tab1, prompt_tab2, prompt_tab3, prompt_tab4 = st.tabs([
                        "🏞️ 이미지",
                        "🎭 캐릭터",
                        "🎬 비디오(캐릭터)",
                        "🎬 비디오(전체)"
                    ])

                    with prompt_tab1:
                        img_prompt = scene.get("image_prompt_en", "")
                        if img_prompt:
                            st.code(img_prompt, language=None)
                            st.caption("💡 Midjourney, DALL-E, Stable Diffusion에서 사용")
                        else:
                            st.caption("(프롬프트 없음)")

                    with prompt_tab2:
                        char_prompt = scene.get("character_prompt_en", "")
                        if char_prompt:
                            st.code(char_prompt, language=None)
                            st.caption("💡 캐릭터 이미지 생성용 (배경 제거)")
                        else:
                            st.caption("(프롬프트 없음)")

                    with prompt_tab3:
                        video_char = scene.get("video_prompt_character", "")
                        if video_char and video_char != "N/A":
                            st.code(video_char, language=None)
                            st.caption("💡 D-ID, HeyGen에서 립싱크/표정 연기용")
                        else:
                            st.caption("(프롬프트 없음)")

                    with prompt_tab4:
                        video_full = scene.get("video_prompt_full", "")
                        if video_full and video_full != "N/A":
                            st.code(video_full, language=None)
                            st.caption("💡 Runway, Pika, Kling에서 시네마틱 연출용")
                        else:
                            st.caption("(프롬프트 없음)")

# === 탭 3: 캐릭터 ===
with tab3:
    st.subheader("👤 추출된 캐릭터")

    # ═══════════════════════════════════════════════════════════════════
    # 캐릭터 동기화 상태 표시 및 수동 동기화
    # ═══════════════════════════════════════════════════════════════════
    _sync_scenes_path = project_path / "analysis" / "scenes.json"
    if _sync_scenes_path.exists():
        try:
            from utils.character_sync import get_sync_status, sync_all_scenes_characters, update_characters_json

            with open(_sync_scenes_path, "r", encoding="utf-8") as _sf:
                _sync_scenes = json.load(_sf)

            _sync_status = get_sync_status(_sync_scenes)

            if _sync_status["needs_sync"] > 0:
                with st.expander(f"🔄 캐릭터 동기화 필요 ({_sync_status['needs_sync']}개 씬)", expanded=True):
                    _sc1, _sc2, _sc3, _sc4 = st.columns(4)
                    with _sc1:
                        st.metric("총 씬", _sync_status["total"])
                    with _sc2:
                        st.metric("character_prompt", _sync_status["has_prompt"])
                    with _sc3:
                        st.metric("characters 배열", _sync_status["has_array"])
                    with _sc4:
                        st.metric("동기화 필요", _sync_status["needs_sync"])

                    if _sync_status["needs_sync"] <= 20:
                        st.caption(f"불일치 씬: {_sync_status['mismatch_scenes']}")
                    else:
                        st.caption(f"불일치 씬 예시: {_sync_status['mismatch_scenes'][:20]}... 외 {_sync_status['needs_sync'] - 20}개")

                    if st.button("🔄 캐릭터 동기화 실행", type="primary", key="sync_characters_btn"):
                        _sync_scenes, _synced = sync_all_scenes_characters(_sync_scenes)
                        with open(_sync_scenes_path, "w", encoding="utf-8") as _sf:
                            json.dump(_sync_scenes, _sf, ensure_ascii=False, indent=2)
                        _chars_path = _sync_scenes_path.parent / "characters.json"
                        _added = update_characters_json(_sync_scenes, _chars_path)
                        st.success(f"✅ {_synced}개 씬 동기화 완료! (캐릭터 {_added}명 추가)")
                        time.sleep(0.5)
                        st.rerun()
            else:
                if _sync_status["has_prompt"] > 0:
                    st.caption(f"✅ 캐릭터 동기화 완료 (prompt: {_sync_status['has_prompt']}개, 배열: {_sync_status['has_array']}개)")
        except Exception as _e:
            print(f"[캐릭터 탭] 동기화 상태 확인 오류: {_e}")

    # ═══════════════════════════════════════════════════════════════════
    # v13.16: 다중 소스에서 캐릭터 로드 (characters.json → scenes.json → session_state)
    # ═══════════════════════════════════════════════════════════════════
    characters = None
    data_source = ""

    characters_path = project_path / "analysis" / "characters.json"
    scenes_path = project_path / "analysis" / "scenes.json"

    # 1순위: characters.json 파일
    if characters_path.exists():
        try:
            with open(characters_path, "r", encoding="utf-8") as f:
                characters = json.load(f)
            if characters:
                data_source = "📁 characters.json"
        except Exception as e:
            print(f"[캐릭터 탭] characters.json 로드 실패: {e}")

    # 2순위: scenes.json에서 추출
    if not characters and scenes_path.exists():
        try:
            with open(scenes_path, "r", encoding="utf-8-sig") as f:
                content = f.read()
                if content.startswith('\ufeff'):
                    content = content[1:]
                scenes_data = json.loads(content)

            # scenes.json에서 캐릭터 추출
            from utils.claude_code_runner import extract_characters_from_scenes
            characters = extract_characters_from_scenes(scenes_data)

            if characters:
                data_source = "🎬 scenes.json에서 추출"
                # characters.json에 저장 (다음 로드 시 빠르게)
                try:
                    with open(characters_path, 'w', encoding='utf-8') as f:
                        json.dump(characters, f, ensure_ascii=False, indent=2)
                    print(f"[캐릭터 탭] ✅ characters.json 자동 생성: {len(characters)}개")
                except:
                    pass
        except Exception as e:
            print(f"[캐릭터 탭] scenes.json 캐릭터 추출 실패: {e}")

    # 3순위: session_state
    if not characters:
        characters = st.session_state.get("scene_characters", [])
        if characters:
            data_source = "💾 세션 캐시"

    # 캐릭터 표시
    if characters:
        st.success(f"{len(characters)}명의 캐릭터가 추출되었습니다.")
        st.caption(f"📂 데이터 소스: {data_source}")

        for i, char in enumerate(characters):
            # === 캐릭터 데이터 정규화 (문자열/딕셔너리 모두 처리) ===
            if isinstance(char, str):
                # 문자열인 경우: 이름만 있는 것으로 처리
                char_data = {
                    "name": char,
                    "name_ko": char,
                    "name_en": "",
                    "role": "등장인물",
                    "nationality": "",
                    "era": "",
                    "description": "",
                    "appearance": "",
                    "character_prompt": "",
                    "visual_prompt": ""
                }
            elif isinstance(char, dict):
                # 딕셔너리인 경우: 필드 추출 (다양한 키 이름 처리)
                char_data = {
                    "name": char.get("name", char.get("name_ko", "Unknown")),
                    "name_ko": char.get("name_ko", char.get("name", "")),
                    "name_en": char.get("name_en", ""),
                    "role": char.get("role", "등장인물"),
                    "nationality": char.get("nationality", ""),
                    "era": char.get("era", char.get("age_era", "")),
                    "description": char.get("description", ""),
                    "appearance": char.get("appearance", ""),
                    "character_prompt": char.get("character_prompt", char.get("visual_prompt", char.get("prompt", ""))),
                    "visual_prompt": char.get("visual_prompt", char.get("character_prompt", char.get("prompt", "")))
                }
            else:
                # 기타 형식: 문자열로 변환
                char_data = {
                    "name": str(char),
                    "name_ko": str(char),
                    "name_en": "",
                    "role": "등장인물",
                    "nationality": "",
                    "era": "",
                    "description": "",
                    "appearance": "",
                    "character_prompt": "",
                    "visual_prompt": ""
                }

            char_name = char_data["name"]
            char_name_en = char_data["name_en"]

            # 표시 이름 생성
            display_name = f"👤 {char_name}"
            if char_name_en:
                display_name += f" ({char_name_en})"

            with st.expander(display_name, expanded=False):
                col1, col2 = st.columns([1, 2])

                with col1:
                    st.markdown("**역할**")
                    st.write(char_data["role"] or "정보 없음")

                    if char_data["nationality"] or char_data["era"]:
                        st.markdown("**국적/시대**")
                        st.write(f"{char_data['nationality']} / {char_data['era']}")

                with col2:
                    if char_data["description"]:
                        st.markdown("**설명**")
                        st.write(char_data["description"])

                    if char_data["appearance"]:
                        st.markdown("**외모 특징**")
                        st.write(char_data["appearance"])

                if char_data["character_prompt"]:
                    st.markdown("**🎨 캐릭터 프롬프트**")
                    st.code(char_data["character_prompt"], language=None)
                else:
                    st.info("캐릭터 프롬프트가 없습니다. 캐릭터 관리에서 생성할 수 있습니다.")
    else:
        # ═══════════════════════════════════════════════════════════════
        # v13.16: 캐릭터 없는 경우 - 씬 분석 유무에 따라 다른 메시지
        # ═══════════════════════════════════════════════════════════════
        scenes_path_check = project_path / "analysis" / "scenes.json"
        if scenes_path_check.exists():
            st.info("이 영상에서 추출된 캐릭터가 없습니다.")
            st.caption("💡 씬 분석은 완료되었지만 캐릭터 정보가 포함되지 않았습니다.")

            # 새로고침 버튼
            _retry_col1, _retry_col2 = st.columns(2)
            with _retry_col1:
                if st.button("🔄 캐릭터 다시 추출 시도", key="retry_char_extract"):
                    try:
                        with open(scenes_path_check, "r", encoding="utf-8-sig") as f:
                            content = f.read()
                            if content.startswith('\ufeff'):
                                content = content[1:]
                            scenes_reload = json.loads(content)

                        from utils.claude_code_runner import extract_characters_from_scenes
                        chars_reload = extract_characters_from_scenes(scenes_reload)

                        if chars_reload:
                            st.session_state['scene_characters'] = chars_reload
                            # characters.json 저장
                            chars_path = project_path / "analysis" / "characters.json"
                            with open(chars_path, 'w', encoding='utf-8') as f:
                                json.dump(chars_reload, f, ensure_ascii=False, indent=2)
                            st.success(f"✅ {len(chars_reload)}개 캐릭터 추출 완료!")
                            time.sleep(0.5)
                            st.rerun()
                        else:
                            st.warning("씬 데이터에 캐릭터 정보가 없습니다.")
                    except Exception as e:
                        st.error(f"추출 실패: {e}")
            with _retry_col2:
                if st.button("🔄 character_prompt에서 동기화", key="retry_char_sync"):
                    try:
                        with open(scenes_path_check, "r", encoding="utf-8-sig") as f:
                            content = f.read()
                            if content.startswith('\ufeff'):
                                content = content[1:]
                            scenes_reload = json.loads(content)

                        from utils.character_sync import sync_all_scenes_characters, update_characters_json
                        scenes_reload, synced = sync_all_scenes_characters(scenes_reload)
                        if synced > 0:
                            with open(scenes_path_check, "w", encoding="utf-8") as f:
                                json.dump(scenes_reload, f, ensure_ascii=False, indent=2)
                            chars_path = scenes_path_check.parent / "characters.json"
                            update_characters_json(scenes_reload, chars_path)
                            st.success(f"✅ {synced}개 씬 동기화 완료!")
                            time.sleep(0.5)
                            st.rerun()
                        else:
                            st.warning("동기화할 데이터가 없습니다 (character_prompt가 비어있음).")
                    except Exception as e:
                        st.error(f"동기화 실패: {e}")
        else:
            st.info("씬 분석을 먼저 실행하세요.")
            st.caption("💡 '분석' 탭에서 씬 분석을 실행한 후 캐릭터가 자동 추출됩니다.")

    # 다음 단계 안내
    st.divider()
    st.info("👉 캐릭터 배치 생성은 3.6단계 '캐릭터 관리'에서 진행하세요.")

# === 탭 4: 결과 ===
with tab4:
    st.subheader("📋 분석 결과 요약")

    analysis_path = project_path / "analysis" / "full_analysis.json"
    scenes_path = project_path / "analysis" / "scenes.json"
    characters_path = project_path / "analysis" / "characters.json"

    # ═══════════════════════════════════════════════════════════════════════════
    # ⭐ v13.15: Claude Code 결과 확인 UI (핵심 추가!)
    # Claude Code가 scenes.json을 업데이트한 후 UI에 반영하기 위한 기능
    # ═══════════════════════════════════════════════════════════════════════════
    st.markdown("---")
    st.markdown("#### 🔄 Claude Code 결과 확인")

    result_check_col1, result_check_col2, result_check_col3 = st.columns([2, 1, 1])

    with result_check_col1:
        if st.button("🔄 결과 확인 및 UI 갱신", use_container_width=True, key="check_result_tab4",
                     type="primary", help="Claude Code 분석 완료 후 클릭하여 결과를 UI에 반영"):
            if scenes_path.exists():
                try:
                    # 1. Bundle 병합 적용 시도
                    from utils.claude_code_runner import sync_claude_code_results_with_bundle_merge

                    with st.spinner("Bundle 병합 및 결과 로드 중..."):
                        video_path = str(project_path)
                        merge_result = sync_claude_code_results_with_bundle_merge(video_path)

                    if merge_result.get('success'):
                        reload_scenes = merge_result.get('scenes', [])
                        merged_count = merge_result.get('merged_count', 0)

                        if reload_scenes:
                            # 분석 상태 확인
                            analyzed_count = sum(1 for s in reload_scenes if s.get('background_prompt_en'))

                            # 세션 업데이트
                            st.session_state['scenes'] = reload_scenes
                            st.session_state['analysis_complete'] = True
                            st.session_state['force_reload_scenes'] = False

                            # sync_data 적용
                            sync_data = merge_result.get('sync_data', {})
                            for key, value in sync_data.items():
                                st.session_state[key] = value

                            # v13.16: 캐릭터 캐시 무효화 (다른 페이지에서 새 데이터 로드)
                            if 'char_load_logged' in st.session_state:
                                del st.session_state['char_load_logged']
                            st.session_state['characters_need_refresh'] = True

                            # v13.16: 캐릭터 수 표시
                            char_count = sync_data.get('characters_count', 0)
                            success_msg = f"✅ 로드 완료! {analyzed_count}/{len(reload_scenes)} 씬 분석됨"
                            if merged_count > 0:
                                success_msg += f" (Bundle 병합: {merged_count}개)"
                            if char_count > 0:
                                success_msg += f" / 캐릭터: {char_count}명"

                            st.success(success_msg)
                            time.sleep(0.3)
                            st.rerun()
                        else:
                            st.warning("씬 데이터가 비어있습니다.")
                    else:
                        # 폴백: 직접 파일 로드
                        st.warning(f"Bundle 병합 실패, 직접 로드 시도... ({merge_result.get('error', '')})")
                        with open(scenes_path, 'r', encoding='utf-8-sig') as f:
                            content = f.read()
                            if content.startswith('\ufeff'):
                                content = content[1:]
                            reload_scenes = json.loads(content)

                        if reload_scenes:
                            analyzed_count = sum(1 for s in reload_scenes if s.get('background_prompt_en'))
                            st.session_state['scenes'] = reload_scenes
                            st.session_state['analysis_complete'] = True
                            st.success(f"✅ 직접 로드 완료! {analyzed_count}/{len(reload_scenes)} 씬")
                            time.sleep(0.3)
                            st.rerun()

                except ImportError as ie:
                    # claude_code_runner 없으면 직접 로드
                    try:
                        with open(scenes_path, 'r', encoding='utf-8-sig') as f:
                            content = f.read()
                            if content.startswith('\ufeff'):
                                content = content[1:]
                            reload_scenes = json.loads(content)

                        if reload_scenes:
                            analyzed_count = sum(1 for s in reload_scenes if s.get('background_prompt_en'))
                            st.session_state['scenes'] = reload_scenes
                            st.session_state['analysis_complete'] = True
                            st.success(f"✅ {analyzed_count}/{len(reload_scenes)} 씬 로드됨")
                            time.sleep(0.3)
                            st.rerun()
                    except Exception as e:
                        st.error(f"파일 로드 실패: {e}")

                except Exception as e:
                    st.error(f"오류 발생: {e}")
                    import traceback
                    st.code(traceback.format_exc())
            else:
                st.error("❌ scenes.json 파일이 없습니다.")

    with result_check_col2:
        # 파일 수정 시간 표시
        if scenes_path.exists():
            mtime = os.path.getmtime(scenes_path)
            mtime_str = time.strftime('%H:%M:%S', time.localtime(mtime))
            st.caption(f"📅 수정: {mtime_str}")

    with result_check_col3:
        if st.button("🔃 새로고침", use_container_width=True, key="refresh_result_tab4"):
            st.rerun()

    st.markdown("---")
    # ═══════════════════════════════════════════════════════════════════════════

    # ⭐ 데이터 로드 - 세션 스테이트 우선 (v3.17)
    scenes_data = []
    characters_data = []
    full_result = None
    data_source = "file"  # 데이터 소스 추적

    # v13.15: 파일 수정 시간 확인하여 자동 리로드
    _should_reload = False
    if scenes_path.exists():
        file_mtime = os.path.getmtime(scenes_path)
        cache_mtime = st.session_state.get('_scenes_loaded_at', 0)
        if file_mtime > cache_mtime:
            _should_reload = True
            print(f"[Result Tab] 📁 파일이 수정됨, 리로드 필요 (file: {file_mtime}, cache: {cache_mtime})")

    # 1. 세션 스테이트에서 먼저 확인 (가장 최신 데이터)
    if st.session_state.get("scenes") and st.session_state.get("analysis_complete") and not _should_reload:
        scenes_data = st.session_state["scenes"]
        characters_data = st.session_state.get("characters", [])
        full_result = st.session_state.get("scene_analysis_result")
        data_source = "session"
    # 2. 파일에서 로드 (폴백 또는 리로드 필요시)
    else:
        if scenes_path.exists():
            try:
                with open(scenes_path, "r", encoding="utf-8-sig") as f:
                    content = f.read()
                    if content.startswith('\ufeff'):
                        content = content[1:]
                    scenes_data = json.loads(content)
                # 캐시 시간 업데이트
                st.session_state['_scenes_loaded_at'] = time.time()
                st.session_state['scenes'] = scenes_data
                data_source = "file (fresh)"
                print(f"[Result Tab] ✅ scenes.json 로드: {len(scenes_data)}개 씬")
            except Exception as e:
                print(f"[Result Tab] ❌ scenes.json 로드 실패: {e}")
                # 폴백: 기존 방식
                with open(scenes_path, "r", encoding="utf-8") as f:
                    scenes_data = json.load(f)

        if characters_path.exists():
            with open(characters_path, "r", encoding="utf-8") as f:
                characters_data = json.load(f)

        if analysis_path.exists():
            with open(analysis_path, "r", encoding="utf-8") as f:
                full_result = json.load(f)

    # ⭐ 최근 분석 정보 표시
    last_analyzed_count = st.session_state.get("last_analyzed_count", 0)
    last_total_count = st.session_state.get("last_total_count", 0)
    last_analyzed_ids = st.session_state.get("last_analyzed_ids", [])

    if last_analyzed_count > 0 and last_total_count > 0:
        if last_analyzed_count < last_total_count:
            st.info(f"🔄 최근 분석: {last_analyzed_count}개 씬 (전체 {last_total_count}개 중) | 소스: {data_source}")
        else:
            st.success(f"✅ 전체 {last_total_count}개 씬 분석 완료 | 소스: {data_source}")

    if scenes_data or full_result:
        # 서브 탭으로 구성
        result_tab1, result_tab2, result_tab3 = st.tabs([
            "📝 씬 목록",
            "✨ 프롬프트 뷰어",
            "📋 전체 JSON"
        ])

        with result_tab1:
            # 씬 목록 간략 표시
            st.markdown("#### 분석된 씬 목록")

            # ============================================================
            # ✅ 다운로드 버튼 영역
            # ============================================================
            if scenes_data:
                st.markdown("##### 📥 다운로드")

                dl_col1, dl_col2, dl_col3 = st.columns(3)

                with dl_col1:
                    # 스크립트만 다운로드 (TXT, /// 구분자)
                    script_text = extract_scripts_from_scenes(scenes_data)
                    script_count = script_text.count("///") if script_text else 0

                    if script_text:
                        st.download_button(
                            label=f"📝 스크립트 TXT ({script_count}개)",
                            data=script_text,
                            file_name=get_script_download_filename(project_path.name if project_path else ""),
                            mime="text/plain",
                            key="download_script_txt_result",
                            use_container_width=True,
                            help="각 씬의 스크립트가 '///'로 구분된 TXT 파일"
                        )
                    else:
                        st.button(
                            "📝 스크립트 없음",
                            disabled=True,
                            use_container_width=True
                        )

                with dl_col2:
                    # 전체 JSON 다운로드
                    json_data = json.dumps(scenes_data, ensure_ascii=False, indent=2)

                    st.download_button(
                        label=f"📄 씬 JSON ({len(scenes_data)}개)",
                        data=json_data,
                        file_name=f"scenes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                        mime="application/json",
                        key="download_scenes_json_result",
                        use_container_width=True
                    )

                with dl_col3:
                    # 프롬프트만 다운로드
                    prompts_text = extract_prompts_from_scenes(scenes_data)

                    if prompts_text:
                        st.download_button(
                            label="🎨 프롬프트 TXT",
                            data=prompts_text,
                            file_name=f"prompts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                            mime="text/plain",
                            key="download_prompts_txt_result",
                            use_container_width=True
                        )
                    else:
                        st.button(
                            "🎨 프롬프트 없음",
                            disabled=True,
                            use_container_width=True
                        )

                st.markdown("---")

            if scenes_data:
                # ⭐ 최근 분석된 씬 필터링 옵션 (v3.17)
                if last_analyzed_ids and last_analyzed_count < len(scenes_data):
                    filter_option = st.radio(
                        "씬 표시 범위",
                        ["전체 씬", "최근 분석된 씬만"],
                        horizontal=True,
                        key="scene_filter_option"
                    )
                    if filter_option == "최근 분석된 씬만":
                        scenes_data = [s for s in scenes_data if s.get("scene_id") in last_analyzed_ids]
                        st.caption(f"📍 최근 분석된 {len(scenes_data)}개 씬만 표시 중")

                for scene in scenes_data:
                    scene_id = scene.get("scene_id", "?")
                    # v3.36: script_ko 우선 체크 추가
                    script_text = scene.get("script_ko") or get_prompt(scene, "script_text") or scene.get("narration", "")
                    preview = script_text[:80] + "..." if len(script_text) > 80 else script_text

                    # ⭐ 최근 분석된 씬 하이라이트
                    is_recently_analyzed = scene_id in last_analyzed_ids if last_analyzed_ids else False
                    label_prefix = "🆕 " if is_recently_analyzed else ""

                    with st.expander(f"{label_prefix}씬 {scene_id}: {preview}", expanded=is_recently_analyzed):
                        if is_recently_analyzed:
                            st.success("✨ 최근 분석됨")

                        st.write("**스크립트:**")
                        st.write(script_text)

                        if scene.get("direction_guide"):
                            st.write("**연출 가이드:**")
                            st.write(scene.get("direction_guide"))

                        if scene.get("visual_elements"):
                            st.write("**시각 요소:**")
                            st.write(", ".join(scene.get("visual_elements", [])))

                        if scene.get("mood"):
                            st.write(f"**분위기:** {scene.get('mood')}")
            else:
                st.info("씬 데이터가 없습니다. 씬 분석을 먼저 실행하세요.")

            # 🔄 프로세스 간 동기화 섹션
            if scenes_data:
                st.markdown("---")
                from utils.sync_manager import ProcessType
                from utils.sync_ui import render_sync_buttons
                render_sync_buttons(ProcessType.SCENE_ANALYSIS)

        with result_tab2:
            # 프롬프트 뷰어 컴포넌트 사용
            if scenes_data:
                render_prompts_viewer(scenes_data)
                st.divider()
                # ✅ 향상된 다운로드 섹션 (유형별/범위별 선택 가능)
                render_enhanced_bulk_download_section(scenes_data, characters_data)
            else:
                st.info("프롬프트 데이터가 없습니다. 씬 분석을 먼저 실행하세요.")

        with result_tab3:
            # 전체 JSON 표시
            if full_result:
                st.json(full_result)
                st.download_button(
                    "📥 분석 결과 다운로드 (JSON)",
                    data=json.dumps(full_result, ensure_ascii=False, indent=2),
                    file_name="scene_analysis.json",
                    mime="application/json",
                    key="download_full_analysis_json"
                )
            elif scenes_data:
                combined = {"scenes": scenes_data, "characters": characters_data}
                st.json(combined)
                st.download_button(
                    "📥 분석 결과 다운로드 (JSON)",
                    data=json.dumps(combined, ensure_ascii=False, indent=2),
                    file_name="scene_analysis.json",
                    mime="application/json",
                    key="download_combined_json"
                )

        # ============================================================
        # ⭐ 사용된 AI 프롬프트 확인 섹션
        # ============================================================
        st.divider()

        # 메타데이터 로드 (세션 또는 full_result에서)
        metadata = st.session_state.get('analysis_metadata', {})
        if not metadata and full_result:
            metadata = full_result.get('analysis_metadata', {})
            prompt_used = full_result.get('prompt_used', '')
            if prompt_used and 'prompt_template' not in metadata:
                metadata['prompt_template'] = prompt_used

        with st.expander("🔍 사용된 AI 프롬프트 확인", expanded=False):
            if metadata:
                # 메타데이터 요약 카드
                meta_col1, meta_col2, meta_col3, meta_col4 = st.columns(4)

                with meta_col1:
                    model_name = metadata.get('model_name', 'N/A')
                    st.metric("모델", model_name)

                with meta_col2:
                    mode = metadata.get('processing_mode', metadata.get('mode', 'N/A'))
                    mode_display = {
                        'batch': '배치',
                        'single': '단일',
                        'sequential': '순차',
                        'parallel': '병렬'
                    }.get(mode, mode)
                    st.metric("분석 모드", mode_display)

                with meta_col3:
                    template_name = metadata.get('template_name', 'N/A')
                    st.metric("템플릿", template_name)

                with meta_col4:
                    char_count = metadata.get('prompt_char_count', 0)
                    st.metric("프롬프트 길이", f"{char_count:,}자")

                # 프롬프트 상세
                prompt_tab_template, prompt_tab_example = st.tabs(["📝 프롬프트 템플릿", "🔄 실제 적용 예시"])

                with prompt_tab_template:
                    prompt_template = metadata.get('prompt_template', '')
                    if prompt_template:
                        st.code(prompt_template, language='markdown')

                        # 복사 버튼 (Streamlit은 직접 클립보드 복사가 안되므로 다운로드로 대체)
                        st.download_button(
                            "📋 프롬프트 템플릿 다운로드",
                            data=prompt_template,
                            file_name="prompt_template.txt",
                            mime="text/plain",
                            key="download_prompt_template"
                        )
                    else:
                        st.info("프롬프트 템플릿 정보가 없습니다.")

                with prompt_tab_example:
                    prompt_example = metadata.get('prompt_example', '')
                    if prompt_example:
                        st.code(prompt_example, language='markdown')
                        st.caption("※ 첫 번째 씬(또는 배치)에 적용된 프롬프트 예시입니다.")

                        st.download_button(
                            "📋 적용 예시 다운로드",
                            data=prompt_example,
                            file_name="prompt_example.txt",
                            mime="text/plain",
                            key="download_prompt_example"
                        )
                    else:
                        st.info("적용 예시 정보가 없습니다.")

                # 추가 정보
                st.markdown("---")
                info_col1, info_col2 = st.columns(2)

                with info_col1:
                    timestamp = metadata.get('timestamp', '')
                    if timestamp:
                        try:
                            dt = datetime.fromisoformat(timestamp)
                            st.caption(f"📅 분석 시간: {dt.strftime('%Y-%m-%d %H:%M:%S')}")
                        except:
                            st.caption(f"📅 분석 시간: {timestamp}")

                with info_col2:
                    processing_time = metadata.get('processing_time_seconds', 0)
                    if processing_time:
                        st.caption(f"⏱️ 처리 시간: {processing_time:.1f}초")

            else:
                st.info("분석 메타데이터가 없습니다. AI 프롬프트 생성을 포함한 씬 분석을 실행하면 여기에 사용된 프롬프트가 표시됩니다.")

    else:
        st.info("분석 결과가 없습니다. 씬 분석을 먼저 실행하세요.")

# === 탭 5: 프롬프트 설정 ===
with tab5:
    st.subheader("⚙️ AI 프롬프트 템플릿 설정")

    st.info("""
    씬 분석과 캐릭터 추출에 사용되는 AI 프롬프트를 커스터마이징할 수 있습니다.
    프롬프트를 수정하면 분석 결과가 달라질 수 있습니다.
    """)

    template_manager_main = get_template_manager()

    # 탭으로 각 템플릿 표시
    prompt_tab1, prompt_tab2, prompt_tab3 = st.tabs(["🎬 씬 분석", "👤 캐릭터 추출", "🖼️ 이미지 프롬프트"])

    # 1. 씬 분석 템플릿 관리 (다중 템플릿 지원)
    with prompt_tab1:
        st.markdown(f"**씬 분석 프롬프트 관리**")
        st.caption("스크립트를 씬 단위로 분할하고 연출가이드를 생성하는 프롬프트들을 관리합니다.")

        # 템플릿 목록 가져오기
        scene_templates = template_manager_main.get_templates_by_category("scene_analysis")
        
        # UI 구성: 왼쪽 목록, 오른쪽 편집
        col_list, col_edit = st.columns([1, 2])
        
        with col_list:
            st.markdown("###### 📋 템플릿 목록")
            
            # 선택된 템플릿 관리를 위한 라디오 버튼
            # 키 관리를 위해 session_state 사용 가능하지만 간단히 radio로 구현
            
            # 템플릿 이름 목록 생성 (ID 매핑)
            t_map = {t.name: t for t in scene_templates}
            selected_t_name = st.radio(
                "편집할 템플릿 선택", 
                list(t_map.keys()),
                key="scene_template_radio"
            )
            
            st.divider()
            
            # 새 템플릿 추가 섹션
            with st.popover("➕ 새 템플릿 추가"):
                # st.form 사용하여 입력값 보존 (버튼 클릭 시 rerun으로 입력값 손실 방지)
                with st.form("add_scene_template_form", clear_on_submit=True):
                    new_t_name = st.text_input(
                        "템플릿 이름",
                        placeholder="예: 다큐멘터리 스타일",
                        help="새 템플릿의 이름을 입력하세요"
                    )
                    new_t_desc = st.text_input(
                        "설명",
                        placeholder="다큐멘터리 영상을 위한 상세 분석",
                        help="템플릿에 대한 설명 (선택사항)"
                    )

                    submitted = st.form_submit_button(
                        "추가하기",
                        type="primary",
                        use_container_width=True
                    )

                    if submitted:
                        if not new_t_name or not new_t_name.strip():
                            st.error("⚠️ 템플릿 이름을 입력하세요.")
                        else:
                            # 중복 이름 체크
                            existing_names = [t.name for t in scene_templates]
                            if new_t_name.strip() in existing_names:
                                st.error(f"⚠️ '{new_t_name}' 이름의 템플릿이 이미 존재합니다.")
                            else:
                                # 기본 프롬프트 복사해서 생성
                                base_prompt = template_manager_main.get_prompt("scene_analysis")
                                if template_manager_main.create_template(
                                    category="scene_analysis",
                                    name=new_t_name.strip(),
                                    description=new_t_desc.strip() if new_t_desc else "",
                                    prompt=base_prompt
                                ):
                                    reload_template_manager()
                                    st.success(f"✅ '{new_t_name}' 템플릿이 추가되었습니다!")
                                    st.rerun()
                                else:
                                    st.error("템플릿 생성에 실패했습니다.")

        with col_edit:
            if selected_t_name:
                t = t_map[selected_t_name]
                st.markdown(f"###### ✏️ '{t.name}' 편집")
                
                # 메타데이터 수정 (기본 템플릿은 수정 불가)
                if not t.is_default:
                    edit_name = st.text_input("이름", value=t.name, key=f"edit_name_{t.id}")
                    edit_desc = st.text_input("설명", value=t.description, key=f"edit_desc_{t.id}")
                else:
                    st.info("🔒 기본 템플릿의 이름/설명은 수정할 수 없습니다.")
                    edit_name = t.name
                    edit_desc = t.description

                # 프롬프트 편집
                edit_prompt = st.text_area(
                    "프롬프트 내용", 
                    value=t.prompt, 
                    height=400,
                    key=f"edit_prompt_{t.id}"
                )
                
                col_save, col_del = st.columns([1, 1])
                
                with col_save:
                    if st.button("💾 변경사항 저장", key=f"save_btn_{t.id}", use_container_width=True):
                        if template_manager_main.update_template(
                            t.id, 
                            edit_prompt, 
                            name=edit_name if not t.is_default else None,
                            description=edit_desc if not t.is_default else None
                        ):
                            reload_template_manager()
                            st.success("저장되었습니다.")
                            st.rerun()
                
                with col_del:
                    if not t.is_default:
                        if st.button("🗑️ 삭제", key=f"del_btn_{t.id}", use_container_width=True, type="secondary"):
                            if template_manager_main.delete_template(t.id):
                                reload_template_manager()
                                st.success("삭제되었습니다.")
                                st.rerun()
                    else:
                        if st.button("🔄 기본값으로 초기화", key=f"reset_btn_{t.id}", use_container_width=True):
                            if template_manager_main.reset_to_default(t.id):
                                reload_template_manager()
                                st.success("초기화되었습니다.")
                                st.rerun()

    templates_config = [
        ("character_extraction", prompt_tab2, "캐릭터 추출 프롬프트", "스크립트에서 캐릭터를 추출하고 상세한 외모 프롬프트를 생성합니다."),
        ("image_prompt_generation", prompt_tab3, "이미지 프롬프트 생성", "씬 설명에서 이미지 생성용 프롬프트를 만듭니다."),
    ]

    for template_id, tab, title, desc in templates_config:
        with tab:
            template = template_manager_main.get_template(template_id)

            if template:
                st.markdown(f"**{title}**")
                st.caption(desc)

                # 상태 표시
                col_status, col_updated = st.columns([1, 1])
                with col_status:
                    if template.is_default:
                        st.info("📋 기본 템플릿 사용 중")
                    else:
                        st.success("✏️ 커스텀 템플릿 사용 중")
                with col_updated:
                    if not template.is_default and template.updated_at:
                        st.caption(f"마지막 수정: {template.updated_at[:10]}")

                # 프롬프트 편집
                st.markdown("**프롬프트:**")
                new_prompt_main = st.text_area(
                    "프롬프트 내용",
                    value=template.prompt,
                    height=400,
                    key=f"main_prompt_{template_id}",
                    label_visibility="collapsed"
                )

                # 버튼
                col1, col2, col3 = st.columns([1, 1, 2])

                with col1:
                    if st.button("💾 저장", key=f"main_save_{template_id}", use_container_width=True):
                        if template_manager_main.update_template(template_id, new_prompt_main):
                            reload_template_manager()  # 싱글톤 강제 리로드
                            st.success("✅ 저장됨! 다음 분석부터 적용됩니다.")
                            st.rerun()

                with col2:
                    if st.button("🔄 기본값 복원", key=f"main_reset_{template_id}", use_container_width=True):
                        if template_manager_main.reset_to_default(template_id):
                            reload_template_manager()  # 싱글톤 강제 리로드
                            st.success("✅ 기본값으로 복원됨!")
                            st.rerun()

                # 프롬프트 작성 가이드
                if template_id == "character_extraction":
                    with st.expander("💡 캐릭터 프롬프트 작성 가이드"):
                        st.markdown("""
                        **좋은 캐릭터 프롬프트 예시:**
                        ```
                        Korean man, 47 years old, short neat black hair with gray at temples,
                        rectangular black-framed glasses, oval face with small monolid eyes,
                        clean-shaven, fair skin, medium build, wearing charcoal gray suit
                        with white shirt and burgundy tie, standing pose
                        ```

                        **반드시 포함:**
                        - 인종, 성별, 정확한 나이
                        - 헤어스타일 (길이, 색상, 스타일)
                        - 얼굴 특징 (얼굴형, 눈, 코, 피부톤)
                        - 체형 (키, 체격)
                        - 의상 (구체적인 색상과 스타일)
                        - 액세서리 (안경, 시계 등)
                        - 포즈

                        **제외할 것:**
                        - 아트 스타일 (flat vector, illustration 등)
                        - 배경 설명
                        - 추상적 특성 (professional, trustworthy 등)
                        """)

# === 탭 6: TTS + AI 타임스탬프 (v5.0) ===
with tab6:
    st.subheader("🎤 TTS 오디오 → 완벽한 SRT (v5.0 - 3단계 파이프라인)")

    st.success("""
    **v5.0 - 3단계 파이프라인 (싱크 100% + 텍스트 교정)**

    1. **Whisper 문장 분리**: 오디오에서 문장 단위로 정확한 타임스탬프 추출 (100-150개)
    2. **AI 스타일별 병합**: 잘게(1-2문장), 기본(2-4문장), 크게(4-8문장)으로 병합
    3. **원문 텍스트 교정**: Whisper 오타를 원문 기준으로 수정 (ZF→DF, 2015→2025 등)
    """)

    st.info("💡 **원문 스크립트를 입력하면 Whisper 오타가 교정됩니다!** (입력하지 않아도 변환 가능)")

    st.divider()

    # 입력 섹션 - 오디오 + 원문 스크립트
    col_audio, col_script = st.columns(2)

    with col_audio:
        st.markdown("### 📁 TTS 오디오 파일")

        uploaded_audio = st.file_uploader(
            "TTS 오디오 파일 업로드",
            type=["mp3", "wav", "flac", "m4a", "ogg"],
            key="hybrid_audio_upload"
        )

        hybrid_audio_path = None
        if uploaded_audio:
            import tempfile
            temp_dir = Path(tempfile.gettempdir()) / "longform_hybrid"
            temp_dir.mkdir(exist_ok=True)

            hybrid_audio_path = str(temp_dir / uploaded_audio.name)
            with open(hybrid_audio_path, 'wb') as f:
                f.write(uploaded_audio.getvalue())

            st.success(f"✅ {uploaded_audio.name}")
            st.audio(uploaded_audio)

    with col_script:
        st.markdown("### 📝 원본 스크립트 (선택사항)")

        hybrid_original_script = st.text_area(
            "TTS 변환에 사용한 원본 텍스트",
            height=200,
            placeholder="여러분, 삼성전자 하면 뭐가 떠오르세요?\n스마트폰? 반도체? TV?\n...\n\n(원문을 입력하면 Whisper 오타가 교정됩니다)",
            key="hybrid_original_script"
        )

        if hybrid_original_script:
            st.caption(f"✅ 원본 스크립트: {len(hybrid_original_script)}자")
        else:
            st.caption("💡 원문 없이도 변환 가능 (오타 교정 없음)")

    st.divider()

    # 설정
    st.markdown("### 변환 설정")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        hybrid_language = st.selectbox(
            "언어",
            ["ko", "en", "ja"],
            format_func=lambda x: {"ko": "한국어", "en": "영어", "ja": "일본어"}[x],
            key="hybrid_language"
        )

    with col2:
        hybrid_whisper_model = st.selectbox(
            "Whisper 모델",
            ["tiny", "base", "small", "medium"],
            index=1,
            help="tiny: 빠름, base: 균형, small/medium: 정확",
            key="hybrid_whisper_model"
        )

    with col3:
        hybrid_split_style = st.selectbox(
            "씬 분할 스타일",
            ["기본", "잘게", "크게"],
            help="기본: 1~3문장, 잘게: 1문장, 크게: 3~5문장",
            key="hybrid_split_style"
        )

    with col4:
        # AI 모델 옵션 (Claude Agent 추가)
        ai_model_options = {
            "gemini-2.5-flash": "Gemini 2.5 Flash (빠름)",
            "gemini-1.5-flash": "Gemini 1.5 Flash",
            "gemini-2.5-flash-lite": "Gemini 2.5 Flash Lite (초고속)",
            "claude-agent": "Claude Agent (씬분할+교정)"
        }
        # v1.0: 설정 영속성 - persistent_selectbox 사용
        hybrid_ai_model = persistent_selectbox(
            "AI 모델",
            options=list(ai_model_options.keys()),
            page=PAGE_SETTINGS_NAME,
            setting_key="hybrid_ai_model",
            format_func=lambda x: ai_model_options[x]
        )

        # Claude Agent 선택 시 API 키 확인
        if hybrid_ai_model == "claude-agent":
            import os
            if os.getenv("ANTHROPIC_API_KEY"):
                st.caption("Anthropic API 키 설정됨")
            else:
                st.warning("ANTHROPIC_API_KEY 환경변수 필요")

    # Whisper 엔진 선택
    st.markdown("### Whisper 엔진")

    try:
        from utils.whisper_timestamp import get_available_engines, is_faster_whisper_available, is_stable_ts_available

        available_engines = get_available_engines()
        engine_col1, engine_col2 = st.columns([1, 2])

        with engine_col1:
            engine_options = ["auto"]
            engine_labels = {"auto": "자동 선택 (빠른 엔진 우선)"}

            for eng in available_engines:
                engine_options.append(eng["id"])
                engine_labels[eng["id"]] = eng["name"]

            hybrid_whisper_engine = st.selectbox(
                "Whisper 엔진",
                engine_options,
                format_func=lambda x: engine_labels[x],
                key="hybrid_whisper_engine",
                help="faster-whisper: CPU에서 3~4배 빠름\nstable-ts: 정밀한 타임스탬프"
            )

            # 엔진 미설치 경고
            if hybrid_whisper_engine == "faster-whisper" and not is_faster_whisper_available():
                st.warning("faster-whisper 미설치\n`pip install faster-whisper`")
            elif hybrid_whisper_engine == "stable-ts" and not is_stable_ts_available():
                st.warning("stable-ts 미설치\n`pip install stable-ts`")

        with engine_col2:
            # 엔진별 설명
            if hybrid_whisper_engine == "auto":
                st.info("설치된 엔진 중 faster-whisper를 우선 사용합니다.")
            elif hybrid_whisper_engine == "faster-whisper":
                st.info("CTranslate2 기반 - CPU에서 3~4배 빠름, 메모리 50~70% 적음")
            elif hybrid_whisper_engine == "stable-ts":
                st.info("정밀한 타임스탬프, refine/align 기능 지원")

    except ImportError:
        hybrid_whisper_engine = "auto"
        st.warning("Whisper 모듈을 불러올 수 없습니다")

    # Whisper 고급 옵션
    with st.expander("Whisper 고급 옵션"):
        adv_col1, adv_col2 = st.columns(2)

        with adv_col1:
            hybrid_vad_filter = st.checkbox(
                "VAD 필터 (무음 구간 스킵)",
                value=True,
                key="hybrid_vad_filter",
                help="faster-whisper 전용: 무음 구간을 자동으로 건너뜀"
            )

            hybrid_compute_type = st.selectbox(
                "계산 타입",
                ["auto", "int8", "float16", "float32"],
                index=0,
                key="hybrid_compute_type",
                help="faster-whisper 전용: int8이 CPU에서 가장 빠름"
            )

        with adv_col2:
            hybrid_refine = st.checkbox(
                "타임스탬프 미세 조정 (Refine)",
                value=False,
                key="hybrid_refine",
                help="stable-ts 전용: 더 정밀한 타임스탬프 (처리 시간 증가)"
            )

    # 디바이스 설정
    st.markdown("### 디바이스 설정")

    try:
        from utils.device_manager import get_gpu_status, select_device, get_upgrade_instructions

        gpu_status = get_gpu_status()

        col_device, col_status = st.columns([1, 2])

        with col_device:
            device_mode_options = {
                "auto": "🔄 자동 감지 (권장)",
                "gpu": "🎮 GPU 강제",
                "cpu": "💻 CPU 강제"
            }
            hybrid_device_mode = st.selectbox(
                "디바이스 모드",
                list(device_mode_options.keys()),
                format_func=lambda x: device_mode_options[x],
                key="hybrid_device_mode",
                help="auto: GPU 사용 가능하면 GPU, 아니면 CPU\nGPU: GPU 강제 (호환 안 되면 CPU 폴백)\nCPU: CPU 강제"
            )

        with col_status:
            # GPU 상태 표시
            if gpu_status["gpu_available"]:
                if gpu_status["pytorch_compatible"]:
                    st.success(f"✅ GPU 사용 가능: **{gpu_status['gpu_name']}** ({gpu_status['gpu_memory']}, CUDA {gpu_status.get('cuda_version', 'N/A')})")
                else:
                    st.warning(f"⚠️ GPU 호환 불가: {gpu_status['gpu_name']} (compute {gpu_status['compute_capability']})")
                    if gpu_status.get("warning"):
                        st.caption(gpu_status["warning"])
            else:
                st.info("💻 CPU 모드로 실행됩니다")

            # 선택 모드에 따른 예상 디바이스
            device_result = select_device(hybrid_device_mode)
            if device_result.fallback_used:
                st.caption(f"⚠️ {device_result.message}")
            else:
                st.caption(f"ℹ️ {device_result.message}")

        # RTX 50xx 업그레이드 안내
        if gpu_status.get("needs_upgrade"):
            with st.expander("🔧 GPU 활성화 방법 (PyTorch 업그레이드 필요)", expanded=False):
                upgrade_instructions = get_upgrade_instructions()
                if upgrade_instructions:
                    st.markdown(upgrade_instructions)

                st.info("""
                **빠른 실행:**
                ```bash
                python scripts/upgrade_pytorch.py
                ```
                """)

    except ImportError:
        hybrid_device_mode = "cpu"
        st.info("💻 CPU 모드로 실행됩니다 (device_manager 없음)")

    # 프롬프트 설정 섹션
    st.markdown("### 씬 분할 프롬프트 설정")

    with st.expander("분할 기준 상세 설정", expanded=False):
        try:
            from utils.ai_scene_splitter import get_prompt_manager

            prompt_mgr = get_prompt_manager()
            current_prompt = prompt_mgr.get_prompt(hybrid_split_style)

            st.info(f"현재 스타일: **{current_prompt['name']}** - {current_prompt['description']}")

            # 글자 수 설정
            col_min, col_max = st.columns(2)
            with col_min:
                new_min_chars = st.number_input(
                    "최소 글자 수",
                    min_value=10,
                    max_value=500,
                    value=current_prompt["min_chars"],
                    key=f"prompt_min_chars_{hybrid_split_style}"
                )
            with col_max:
                new_max_chars = st.number_input(
                    "최대 글자 수",
                    min_value=50,
                    max_value=1000,
                    value=current_prompt["max_chars"],
                    key=f"prompt_max_chars_{hybrid_split_style}"
                )

            # 분할 기준 표시 및 편집
            st.markdown("**분할 기준:**")
            criteria_text = "\n".join([f"- {c}" for c in current_prompt["criteria"]])
            st.text(criteria_text)

            # 추가 지시사항
            custom_instructions = st.text_area(
                "추가 지시사항 (선택)",
                value=current_prompt.get("custom_instructions", ""),
                height=80,
                placeholder="예: 대화 장면은 더 짧게 나눠주세요",
                key=f"prompt_custom_{hybrid_split_style}"
            )

            # 저장/리셋 버튼
            col_save, col_reset = st.columns(2)
            with col_save:
                if st.button("설정 저장", key="save_prompt_settings"):
                    prompt_mgr.update_prompt(
                        hybrid_split_style,
                        min_chars=new_min_chars,
                        max_chars=new_max_chars,
                        custom_instructions=custom_instructions
                    )
                    st.success("설정 저장됨")
                    st.rerun()

            with col_reset:
                if st.button("기본값 복원", key="reset_prompt_settings"):
                    prompt_mgr.reset_prompt(hybrid_split_style)
                    st.success("기본값 복원됨")
                    st.rerun()

            # v5 세그먼트 병합 프롬프트 미리보기
            with st.expander("v5.0 스타일별 병합 프롬프트 미리보기"):
                try:
                    from utils.ai_scene_splitter import STYLE_CONFIG, MERGE_PROMPTS
                    style_config = STYLE_CONFIG.get(hybrid_split_style, STYLE_CONFIG["기본"])
                    st.info(f"**{style_config['name']}**: {style_config['description']} ({style_config['min_sentences']}-{style_config['max_sentences']}문장/씬)")
                    merge_config = MERGE_PROMPTS.get(hybrid_split_style, MERGE_PROMPTS["기본"])
                    st.code(merge_config["prompt_template"][:1000] + "...", language="markdown")
                except Exception:
                    st.warning("STYLE_CONFIG를 로드할 수 없습니다")

        except ImportError:
            st.warning("HybridPromptManager를 로드할 수 없습니다")
        except Exception as e:
            st.error(f"프롬프트 설정 로드 실패: {e}")

    st.divider()

    # 변환 실행 (v5.4)
    if st.button("🚀 6단계 파이프라인 실행 (v5.4)", type="primary", key="hybrid_convert", use_container_width=True):
        if not hybrid_audio_path:
            st.error("TTS 오디오 파일을 업로드하세요")
        else:
            try:
                from utils.tts_to_srt_hybrid import TTStoSRTHybridV5

                progress_bar = st.progress(0)
                status_text = st.empty()

                def update_progress(percent, message):
                    progress_bar.progress(percent / 100)
                    status_text.text(f"{percent}% - {message}")

                status_text.text("0% - 초기화 중...")

                converter = TTStoSRTHybridV5(
                    whisper_model=hybrid_whisper_model,
                    device_mode=hybrid_device_mode,
                    ai_model=hybrid_ai_model,
                    whisper_engine=hybrid_whisper_engine,
                    whisper_compute_type=hybrid_compute_type,
                    whisper_vad_filter=hybrid_vad_filter,
                    whisper_refine=hybrid_refine
                )

                # 저장 경로
                srt_path = str(project_path / "analysis" / "hybrid_v5.srt")
                json_path = str(project_path / "analysis" / "hybrid_v5_scenes.json")

                # v5.4: 원문 스크립트 전달 + 후처리 교정 + SRT 검증 + 최종 검증
                srt_text, results, metadata = converter.convert(
                    audio_path=hybrid_audio_path,
                    original_script=hybrid_original_script or "",
                    language=hybrid_language,
                    split_style=hybrid_split_style,
                    output_srt_path=srt_path,
                    output_json_path=json_path,
                    enable_v3_correction=True,
                    enable_srt_validation=True,  # v5.3: SRT 타임스탬프 검증
                    enable_final_validation=True,  # v5.4: 최종 SRT 검증
                    progress_callback=update_progress
                )

                # v5.4: 메타데이터 추출
                correction_changes = metadata.get("correction_changes", [])
                validation_fixes = metadata.get("validation_fixes", [])
                final_corrections = metadata.get("final_corrections", [])

                progress_bar.progress(100)
                status_text.text("완료!")

                # 세션에 저장 (기존 씬 분석 결과와 통합)
                hybrid_scenes = []
                for r in results:
                    hybrid_scenes.append({
                        "scene_id": r.scene_id,
                        "script_text": r.text,  # v4에서는 text 사용
                        "start_time": r.start_time,
                        "end_time": r.end_time,
                        "duration_estimate": r.duration,
                        "timecode": r.timecode,
                        "mood": r.mood,
                        "segment_ids": r.segment_ids,  # v4 신규
                        "scene_break_reason": r.scene_break_reason,
                        "char_count": r.char_count
                    })

                st.session_state["scenes"] = hybrid_scenes
                st.session_state["scene_data"] = {"scenes": hybrid_scenes}
                st.session_state["hybrid_srt"] = srt_text

                # 결과 표시
                device_used = converter.device_used or "cpu"
                engine_used = getattr(converter, 'whisper_engine', hybrid_whisper_engine)
                ai_model_used = metadata.get("ai_model", hybrid_ai_model)
                correction_count = len(correction_changes) if correction_changes else 0
                validation_count = len(validation_fixes) if validation_fixes else 0
                final_correction_count = len(final_corrections) if final_corrections else 0
                correction_info = f"원문 기반 {correction_count}개 씬 교정됨" if hybrid_original_script and correction_count > 0 else ("원문 없음 (교정 생략)" if not hybrid_original_script else "교정 필요 없음")
                validation_info = f"{validation_count}개 수정됨" if validation_count > 0 else "문제 없음"
                final_correction_info = f"{final_correction_count}개 최종 교정됨" if final_correction_count > 0 else "추가 교정 없음"
                st.success(f"""
                **v5.4 변환 완료! (6단계 파이프라인 - 싱크 100%)**

                - 씬 수: **{len(results)}개**
                - 총 길이: **{results[-1].end_time:.1f}초** ({int(results[-1].end_time//60)}분 {int(results[-1].end_time%60)}초)
                - Whisper 엔진: **{engine_used}**
                - 사용 디바이스: **{device_used.upper()}**
                - AI 모델: **{ai_model_used}**
                - 원문 교정: **{correction_info}**
                - 타임스탬프: **{validation_info}**
                - 최종 검증: **{final_correction_info}**
                - SRT: `{srt_path}`
                """)

                # 결과 미리보기
                with st.expander("📄 생성된 씬 미리보기", expanded=True):
                    for r in results[:5]:
                        st.markdown(f"""
                        **씬 {r.scene_id}** ({r.timecode}, {r.duration:.1f}초) [문장 ID: {r.sentence_ids}]
                        - 텍스트: {r.text[:80]}{"..." if len(r.text) > 80 else ""}
                        - 분위기: {r.mood}
                        - 씬 분할 이유: {r.scene_break_reason}
                        ---
                        """)

                # ✅ v5.2: 교정 변경 내역 표시
                if correction_changes:
                    with st.expander(f"📝 원문 기반 교정 내역 ({len(correction_changes)}개)", expanded=True):
                        for change in correction_changes[:10]:
                            col1, col2 = st.columns(2)
                            with col1:
                                st.caption(f"**씬 {change['scene_id']} - 교정 전 (Whisper)**")
                                st.text(change['original'][:100] + "..." if len(change['original']) > 100 else change['original'])
                            with col2:
                                st.caption(f"**교정 후 (원문 기반)**")
                                st.text(change['corrected'][:100] + "..." if len(change['corrected']) > 100 else change['corrected'])
                            st.divider()
                        if len(correction_changes) > 10:
                            st.info(f"... 외 {len(correction_changes) - 10}개 교정됨")

                # ✅ v5.4: 최종 검증 교정 내역 표시
                if final_corrections:
                    with st.expander(f"🔍 최종 검증 교정 내역 ({len(final_corrections)}개)", expanded=True):
                        for corr in final_corrections[:10]:
                            col1, col2 = st.columns(2)
                            with col1:
                                st.caption(f"**씬 {corr.get('scene_id', '?')} - 교정 전**")
                                orig_text = str(corr.get('original_srt', ''))
                                st.text(orig_text[:100] + "..." if len(orig_text) > 100 else orig_text)
                            with col2:
                                st.caption(f"**최종 교정 후** ({corr.get('reason', '')})")
                                corr_text = str(corr.get('corrected', ''))
                                st.text(corr_text[:100] + "..." if len(corr_text) > 100 else corr_text)
                            st.divider()
                        if len(final_corrections) > 10:
                            st.info(f"... 외 {len(final_corrections) - 10}개 최종 교정됨")

                elif hybrid_original_script:
                    with st.expander("🔍 Whisper vs 교정 비교 (샘플)", expanded=False):
                        for r in results[:3]:
                            col1, col2 = st.columns(2)
                            with col1:
                                st.caption(f"**씬 {r.scene_id} - Whisper 원본**")
                                whisper_text = r.whisper_text if hasattr(r, 'whisper_text') else r.text
                                st.text(whisper_text[:100] + "..." if len(whisper_text) > 100 else whisper_text)
                            with col2:
                                st.caption(f"**교정 후**")
                                st.text(r.text[:100] + "..." if len(r.text) > 100 else r.text)
                            st.divider()

                        if len(results) > 5:
                            st.info(f"... 외 {len(results) - 5}개 씬")

                # 다운로드 버튼
                col_dl1, col_dl2 = st.columns(2)
                with col_dl1:
                    st.download_button(
                        "SRT 다운로드",
                        srt_text,
                        "hybrid_generated.srt",
                        mime="text/plain",
                        key="download_hybrid_srt"
                    )
                with col_dl2:
                    st.download_button(
                        "JSON 다운로드",
                        json.dumps({"scenes": hybrid_scenes}, ensure_ascii=False, indent=2),
                        "hybrid_scenes.json",
                        mime="application/json",
                        key="download_hybrid_json"
                    )

            except ImportError as e:
                st.error(f"""
                **필요한 라이브러리 설치 필요**

                ```
                pip install stable-ts
                ```

                오류: {e}
                """)
            except Exception as e:
                st.error(f"오류: {e}")
                import traceback
                with st.expander("상세 오류"):
                    st.code(traceback.format_exc())


# 다음 단계 안내
st.divider()

# v3.77: 실제 분석 상태 확인 (파일 존재 여부만 확인하지 않음)
scenes_json_path = project_path / "analysis" / "scenes.json"
if scenes_json_path.exists():
    # scenes.json 내용 확인
    try:
        import json
        with open(scenes_json_path, 'r', encoding='utf-8') as f:
            scenes_data = json.load(f)

        total_scenes = len(scenes_data)
        analyzed_scenes = sum(1 for s in scenes_data if s.get('background_prompt_en'))

        # 분석 완료 판정: 분석 결과가 있고, 세션에 analysis_complete 플래그가 있거나 30% 이상 분석됨
        analysis_complete_flag = st.session_state.get("analysis_complete", False)
        if analyzed_scenes > 0 and (analysis_complete_flag or analyzed_scenes >= total_scenes * 0.3):
            pct = analyzed_scenes / total_scenes * 100 if total_scenes > 0 else 0
            if pct >= 80:
                st.success(f"씬 분석이 완료되었습니다! ({analyzed_scenes}/{total_scenes}개 씬 분석됨)")
            else:
                st.warning(f"씬 분석 부분 완료 ({analyzed_scenes}/{total_scenes}개, {pct:.0f}%) - 일부 씬의 프롬프트가 비어있을 수 있습니다.")
            col1, col2 = st.columns(2)
            with col1:
                st.page_link("pages/3.6_👤_캐릭터_관리.py", label="👤 3.6단계: 캐릭터 관리", icon="➡️")
            with col2:
                st.page_link("pages/4_🎤_TTS_생성.py", label="🎤 4단계: TTS 생성", icon="➡️")
        elif analyzed_scenes > 0:
            st.warning(f"씬 분석 진행 중... ({analyzed_scenes}/{total_scenes}개 완료)")
        else:
            # Claude Code 상태 확인
            from utils.claude_code_ui_helpers import get_analysis_status_st
            status = get_analysis_status_st(str(project_path))

            if status['status'] == 'error':
                st.error(f"분석 오류: {status['message']}")
            elif status['status'] == 'no_scenes':
                st.error(f"씬 ID 불일치 오류: {status['message']}")
                st.info("💡 SRT 파싱 결과가 scenes.json에 올바르게 저장되었는지 확인하세요.")
            elif status['status'] == 'running':
                st.info(f"분석 진행 중: {status['message']}")
            else:
                st.info("씬 분석을 시작해주세요.")
    except Exception as e:
        st.warning(f"scenes.json 확인 중 오류: {e}")
else:
    st.info("씬 분석을 시작해주세요. (scenes.json 파일이 없습니다)")
