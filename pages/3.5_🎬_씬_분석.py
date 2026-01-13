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
import os
import re
from datetime import datetime


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
        possible_keys = ["script_text", "text", "narration", "대사", "content", "dialogue", "나레이션"]

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

st.title("🎬 3.5단계: 씬 분석")
st.caption("스크립트를 씬 단위로 분할하고 연출가이드 생성")

# API 키 확인
if not require_api_key("ANTHROPIC_API_KEY", "Anthropic API"):
    st.stop()

st.divider()

# ═══════════════════════════════════════════════════════════════
# 동기화된 스크립트 확인 (스크립트 생성 페이지에서 저장한 최신 데이터)
# ═══════════════════════════════════════════════════════════════
synced_script, synced_language = sync_load_script(str(project_path))
synced_info = get_synced_script_info()

# 동기화된 스크립트가 있으면 언어 기본값을 동기화
if synced_script and synced_info.get("has_content"):
    default_lang_index = 0 if synced_language == "ko" else 1
    st.info(f"📝 스크립트 탭에서 저장된 **{synced_info.get('language_name', synced_language)}** 스크립트가 있습니다 ({synced_info.get('char_count', 0):,}자)")
else:
    default_lang_index = 0 if project_config.get("language") == "ko" else 1

# 언어 선택
language = st.selectbox(
    "언어",
    ["ko", "ja"],
    format_func=lambda x: "한국어" if x == "ko" else "일본어",
    index=default_lang_index
)

# 스크립트 로드 (동기화 우선, 없으면 기존 파일)
if synced_script and synced_language == language:
    auto_script = synced_script
elif synced_script:
    # 동기화된 스크립트가 있지만 언어가 다른 경우
    auto_script = synced_script
    if language != synced_language:
        st.warning(f"⚠️ 저장된 스크립트는 **{synced_info.get('language_name')}**입니다. 언어 설정을 확인하세요.")
else:
    # 동기화된 스크립트가 없으면 기존 파일에서 로드
    auto_script = load_script(project_path, language, "final") or load_script(project_path, language, "draft")

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
    script_source = st.radio(
        "스크립트 소스",
        [
            "🔄 자동: 스크립트 탭에서 가져오기",
            "✏️ 수동: 직접 입력",
            "📁 수동: 파일 업로드",
            "🎬 SRT: 자막 파일 업로드"
        ],
        horizontal=True,
        key="scene_script_source"
    )

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

    analysis_mode = st.radio(
        "분석 방식",
        options=analysis_options,
        format_func=lambda x: analysis_format_func[x],
        horizontal=True,
        help="SRT 파일을 업로드했다면 'SRT 직접 적용'으로 시간 코드 기반 씬 구분을 유지할 수 있습니다.",
        key="scene_analysis_mode"
    )

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
                script_text = scene.get("script_text", scene.get("text", scene.get("narration", "")))

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
                        st.markdown(f"**씬 {scene.get('scene_id')}**: {scene.get('script_text', '')[:100]}...")

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

                with open(analysis_dir / "scenes.json", "w", encoding="utf-8") as f:
                    json.dump(result.get("scenes", []), f, ensure_ascii=False, indent=2)

                with open(analysis_dir / "characters.json", "w", encoding="utf-8") as f:
                    json.dump(result.get("characters", []), f, ensure_ascii=False, indent=2)

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
                        st.caption("현재 적용된 SRT 분석 프롬프트를 확인하고 수정할 수 있습니다.")

                        # 단일 씬 프롬프트 표시/수정
                        st.markdown("**📌 단일 씬 분석 프롬프트**")
                        st.caption("순차/병렬 처리 시 각 씬에 적용되는 프롬프트")

                        single_template = template_manager.get_srt_single_template()
                        if single_template:
                            single_prompt_key = "srt_single_prompt_edit"
                            edited_single = st.text_area(
                                "단일 씬 프롬프트",
                                value=single_template.prompt,
                                height=200,
                                key=single_prompt_key,
                                label_visibility="collapsed"
                            )

                            # 수정 여부 확인
                            single_modified = edited_single != single_template.prompt

                            if single_modified:
                                col_s1, col_s2 = st.columns(2)
                                with col_s1:
                                    if st.button("💾 단일 프롬프트 저장", key="save_single_prompt"):
                                        if template_manager.update_template(
                                            single_template.id,
                                            edited_single,
                                            name=single_template.name,
                                            description=single_template.description
                                        ):
                                            st.success("✅ 저장됨!")
                                            st.rerun()
                                        else:
                                            st.error("저장 실패")
                                with col_s2:
                                    if st.button("🔄 되돌리기", key="revert_single_prompt"):
                                        st.rerun()

                        st.markdown("---")

                        # 배치 프롬프트 표시/수정
                        st.markdown("**📦 배치 분석 프롬프트**")
                        st.caption("배치 처리 시 여러 씬을 한 번에 분석하는 프롬프트")

                        batch_template = template_manager.get_srt_batch_template()
                        if batch_template:
                            batch_prompt_key = "srt_batch_prompt_edit"
                            edited_batch = st.text_area(
                                "배치 프롬프트",
                                value=batch_template.prompt,
                                height=200,
                                key=batch_prompt_key,
                                label_visibility="collapsed"
                            )

                            # 수정 여부 확인
                            batch_modified = edited_batch != batch_template.prompt

                            if batch_modified:
                                col_b1, col_b2 = st.columns(2)
                                with col_b1:
                                    if st.button("💾 배치 프롬프트 저장", key="save_batch_prompt"):
                                        if template_manager.update_template(
                                            batch_template.id,
                                            edited_batch,
                                            name=batch_template.name,
                                            description=batch_template.description
                                        ):
                                            st.success("✅ 저장됨!")
                                            st.rerun()
                                        else:
                                            st.error("저장 실패")
                                with col_b2:
                                    if st.button("🔄 되돌리기", key="revert_batch_prompt"):
                                        st.rerun()

                        st.markdown("---")

                        # 새 버전 생성
                        st.markdown("**➕ 새 프롬프트 버전 생성**")
                        new_name = st.text_input(
                            "새 프롬프트 이름",
                            placeholder="예: SRT 분석 프롬프트 (상세 버전)",
                            key="new_srt_template_name"
                        )
                        new_prompt = st.text_area(
                            "프롬프트 내용",
                            placeholder="새 프롬프트 내용을 입력하세요...",
                            height=150,
                            key="new_srt_template_content"
                        )
                        if st.button("➕ 새 버전 추가", key="add_new_srt_template"):
                            if new_name and new_prompt:
                                new_template = template_manager.create_srt_template(
                                    name=new_name,
                                    description="사용자 정의 SRT 분석 프롬프트",
                                    prompt=new_prompt
                                )
                                if new_template:
                                    st.success(f"✅ '{new_name}' 생성 완료!")
                                    st.rerun()
                                else:
                                    st.error("생성 실패")
                            else:
                                st.warning("이름과 내용을 모두 입력하세요.")

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

            # 분석 범위 선택 라디오
            range_mode = st.radio(
                "범위 선택 모드",
                options=["all", "range", "individual"],
                format_func=lambda x: {"all": "🌐 전체", "range": "📏 구간 지정", "individual": "☑️ 개별 선택"}[x],
                horizontal=True,
                key="srt_range_mode",
                label_visibility="collapsed"
            )

            # 선택된 씬 ID 저장용
            selected_scene_ids = []
            total_scenes = len(srt_scenes)

            if range_mode == "all":
                # 전체 선택
                selected_scene_ids = [s.get("scene_id", i+1) for i, s in enumerate(srt_scenes)]
                st.info(f"✅ 전체 {total_scenes}개 씬이 선택되었습니다.")

            elif range_mode == "range":
                # 구간 지정
                range_col1, range_col2 = st.columns(2)

                with range_col1:
                    start_scene = st.number_input(
                        "시작 씬 번호",
                        min_value=1,
                        max_value=total_scenes,
                        value=1,
                        key="srt_range_start"
                    )

                with range_col2:
                    end_scene = st.number_input(
                        "종료 씬 번호",
                        min_value=1,
                        max_value=total_scenes,
                        value=min(10, total_scenes),
                        key="srt_range_end"
                    )

                # 빠른 선택 버튼
                st.markdown("**⚡ 빠른 선택**")
                quick_col1, quick_col2, quick_col3, quick_col4 = st.columns(4)

                with quick_col1:
                    if st.button("처음 10개", key="quick_first_10", use_container_width=True):
                        st.session_state["srt_range_start"] = 1
                        st.session_state["srt_range_end"] = min(10, total_scenes)
                        st.rerun()

                with quick_col2:
                    if st.button("처음 50개", key="quick_first_50", use_container_width=True):
                        st.session_state["srt_range_start"] = 1
                        st.session_state["srt_range_end"] = min(50, total_scenes)
                        st.rerun()

                with quick_col3:
                    if st.button("마지막 50개", key="quick_last_50", use_container_width=True):
                        st.session_state["srt_range_start"] = max(1, total_scenes - 49)
                        st.session_state["srt_range_end"] = total_scenes
                        st.rerun()

                with quick_col4:
                    if st.button("전체 선택", key="quick_all", use_container_width=True):
                        st.session_state["srt_range_start"] = 1
                        st.session_state["srt_range_end"] = total_scenes
                        st.rerun()

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
                bundle_size = st.selectbox(
                    "묶음 크기",
                    options=[1, 2, 3, 4, 5],
                    index=1,  # 기본값 2
                    help="N개의 씬을 묶어서 하나의 분석 단위로 처리합니다. 안정적인 이미지 전환(5-10초)에 효과적입니다.",
                    key="srt_bundle_size"
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

                from utils.ai_model_selector import render_model_selector, render_processing_mode_selector, render_api_key_status
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
                        provider_icon = {"anthropic": "🟠", "google": "🔵", "openai": "🟢"}.get(model_info.provider.value, "")
                        st.caption(f"{provider_icon} 선택된 모델: **{model_info.name}** - {model_info.description}")

                    # 속도 예상 표시 (선택된 씬 수 기반)
                    selected_count = len(st.session_state.get("srt_selected_scene_ids", srt_scenes))
                    speed_info = {
                        "sequential": f"⏱️ 예상 시간: ~{selected_count * 3}초 (순차 처리)",
                        "batch": f"⚡ 예상 시간: ~{(selected_count // 5 + 1) * 5}초 (배치 처리)",
                        "parallel": f"🚀 예상 시간: ~{max(selected_count // 3, 5)}초 (병렬 처리)"
                    }
                    st.caption(speed_info.get(processing_mode, ""))

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
                        # existing_scenes_dict, existing_characters는 빈 상태 유지

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

                            # 새로운 속도 개선 분석기 사용 (멀티 프로바이더 지원)
                            analyzed_primary = analyze_scenes_with_mode(
                                scenes=primary_scenes,
                                mode=processing_mode,
                                model=selected_model,
                                progress_callback=lambda p: progress.progress(p * 0.7),  # 70%까지
                                status_callback=lambda s: status.text(s)
                            )

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

                            # 캐릭터 visual_prompt 후처리 (빠른 모델 사용)
                            progress.progress(0.85)
                            status.text("캐릭터 visual_prompt 생성 중...")

                            # 캐릭터용 모델 선택 (같은 프로바이더의 빠른 모델 우선)
                            char_model = "claude-3-5-haiku-20241022"  # 기본값
                            if model_info and model_info.provider.value == "google":
                                char_model = "gemini-2.0-flash-exp"
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

                    with open(analysis_dir / "scenes.json", "w", encoding="utf-8") as f:
                        json.dump(analysis_scenes, f, ensure_ascii=False, indent=2)

                    with open(analysis_dir / "characters.json", "w", encoding="utf-8") as f:
                        json.dump(all_characters, f, ensure_ascii=False, indent=2)

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

        # 분석 버튼
        if st.button("🎬 씬 분석 시작", type="primary", use_container_width=True):
            api_manager = get_api_manager()

            # 프로그레스 UI
            progress = StreamlitProgressUI(
                task_name="씬 분석",
                total_steps=4,
                show_logs=True
            )

            try:
                from core.script.scene_analyzer import SceneAnalyzer

                progress.update(1, "AI 분석기 초기화...")
                progress.info("스크립트 분석을 시작합니다.")

                # 디버그: 스크립트 정보 출력
                print(f"[씬 분석 페이지] 스크립트 로드됨: {len(script)} 문자")
                print(f"[씬 분석 페이지] 스크립트 미리보기: {script[:100]}...")
                progress.info(f"로드된 스크립트: {len(script)}자")

                # ⭐ API 매니저에서 선택된 API 정보 가져오기
                api_config = api_manager.get_api_by_id(selected_api) if selected_api else None

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
                    if selected_api:
                        selected_lower = selected_api.lower() if isinstance(selected_api, str) else ""
                        if "gemini" in selected_lower or "google" in selected_lower:
                            provider = "google"
                        elif "gpt" in selected_lower or "openai" in selected_lower:
                            provider = "openai"
                        elif "claude" in selected_lower or "anthropic" in selected_lower:
                            provider = "anthropic"
                    print(f"[씬 분석 페이지] 폴백 모드: {selected_api} -> provider: {provider}")

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

                with open(analysis_dir / "scenes.json", "w", encoding="utf-8") as f:
                    json.dump(result.get("scenes", []), f, ensure_ascii=False, indent=2)

                with open(analysis_dir / "characters.json", "w", encoding="utf-8") as f:
                    json.dump(result.get("characters", []), f, ensure_ascii=False, indent=2)

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

                print(f"[씬 분석 페이지] 세션 저장 완료: 씬 {len(scenes)}개, 캐릭터 {len(characters)}개")

                # 캐릭터 visual_prompt 디버그 출력
                for char in characters[:3]:  # 처음 3개만
                    name = char.get("name", "Unknown")
                    has_prompt = bool(char.get("visual_prompt"))
                    print(f"  - {name}: visual_prompt={'있음' if has_prompt else '없음'}")

                # 사용량 기록 (provider에 따른 모델 ID 결정)
                model_id_map = {
                    "anthropic": "claude-sonnet-4-20250514",
                    "google": "gemini-2.0-flash-exp",
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
                progress.fail(str(e))

                # 에러 기록 (provider에 따른 모델 ID 결정)
                model_id_map = {
                    "anthropic": "claude-sonnet-4-20250514",
                    "google": "gemini-2.0-flash-exp",
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

            # 통계 계산
            total_chars = sum(len(s.get("script_text", "")) for s in scenes) if scenes else 0
            avg_chars = total_chars // len(scenes) if scenes else 0
            max_chars = max(len(s.get("script_text", "")) for s in scenes) if scenes else 0
            over_250_count = sum(1 for s in scenes if len(s.get("script_text", "")) > 250)

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
                script_text = scene.get('script_text', '')
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

    characters_path = project_path / "analysis" / "characters.json"
    if characters_path.exists():
        with open(characters_path, "r", encoding="utf-8") as f:
            characters = json.load(f)

        if characters:
            st.success(f"{len(characters)}명의 캐릭터가 추출되었습니다.")

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
            st.info("추출된 캐릭터가 없습니다. 씬 분석을 먼저 실행하세요.")
    else:
        st.info("씬 분석을 먼저 실행하세요.")

    # 다음 단계 안내
    st.divider()
    st.info("👉 캐릭터 배치 생성은 3.6단계 '캐릭터 관리'에서 진행하세요.")

# === 탭 4: 결과 ===
with tab4:
    st.subheader("📋 분석 결과 요약")

    analysis_path = project_path / "analysis" / "full_analysis.json"
    scenes_path = project_path / "analysis" / "scenes.json"
    characters_path = project_path / "analysis" / "characters.json"

    # ⭐ 데이터 로드 - 세션 스테이트 우선 (v3.17)
    scenes_data = []
    characters_data = []
    full_result = None
    data_source = "file"  # 데이터 소스 추적

    # 1. 세션 스테이트에서 먼저 확인 (가장 최신 데이터)
    if st.session_state.get("scenes") and st.session_state.get("analysis_complete"):
        scenes_data = st.session_state["scenes"]
        characters_data = st.session_state.get("characters", [])
        full_result = st.session_state.get("scene_analysis_result")
        data_source = "session"
    # 2. 파일에서 로드 (폴백)
    else:
        if scenes_path.exists():
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
                    script_text = get_prompt(scene, "script_text") or scene.get("narration", "")
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
            "gemini-2.0-flash-exp": "Gemini 2.0 Flash (빠름)",
            "gemini-1.5-flash": "Gemini 1.5 Flash",
            "gemini-1.5-pro": "Gemini 1.5 Pro (고품질)",
            "claude-agent": "Claude Agent (씬분할+교정)"
        }
        hybrid_ai_model = st.selectbox(
            "AI 모델",
            list(ai_model_options.keys()),
            format_func=lambda x: ai_model_options[x],
            key="hybrid_ai_model"
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
if (project_path / "analysis" / "scenes.json").exists():
    st.success("씬 분석이 완료되었습니다!")
    col1, col2 = st.columns(2)
    with col1:
        st.page_link("pages/3.6_👤_캐릭터_관리.py", label="👤 3.6단계: 캐릭터 관리", icon="➡️")
    with col2:
        st.page_link("pages/4_🎤_TTS_생성.py", label="🎤 4단계: TTS 생성", icon="➡️")
