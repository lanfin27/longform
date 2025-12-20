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
from utils.api_helper import require_api_key, show_api_status_sidebar
from utils.progress_ui import render_api_selector, StreamlitProgressUI
from core.api.api_manager import get_api_manager
from core.prompt.prompt_template_manager import get_template_manager, reload_template_manager
from components.prompt_viewer import render_prompts_viewer, render_bulk_download_section, get_prompt
import os


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

# 언어 선택
language = st.selectbox(
    "언어",
    ["ko", "ja"],
    format_func=lambda x: "한국어" if x == "ko" else "일본어",
    index=0 if project_config.get("language") == "ko" else 1
)

# 스크립트 로드 (자동)
auto_script = load_script(project_path, language, "final") or load_script(project_path, language, "draft")

# 탭 구성
tab1, tab2, tab3, tab4, tab5 = st.tabs(["📝 스크립트 입력", "🎬 씬 분석", "👤 캐릭터", "📋 결과", "⚙️ 프롬프트 설정"])

# 세션에 스크립트 저장용
if "scene_analysis_script" not in st.session_state:
    st.session_state["scene_analysis_script"] = auto_script

# === 탭 1: 스크립트 입력 ===
with tab1:
    st.subheader("📝 분석할 스크립트")

    st.info("씬 분석에 사용할 스크립트를 선택하세요. 이전 단계에서 가져오거나 직접 입력할 수 있습니다.")

    # 입력 소스 선택
    script_source = st.radio(
        "스크립트 소스",
        ["🔄 자동: 스크립트 탭에서 가져오기", "✏️ 수동: 직접 입력", "📁 수동: 파일 업로드"],
        horizontal=True,
        key="scene_script_source"
    )

    script = None

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
    elif "파일 업로드" in script_source:
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
    st.subheader("🎬 씬 자동 분석")

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

            # 선택된 API에 따라 provider 결정
            provider = "anthropic"  # 기본값
            if selected_api:
                selected_lower = selected_api.lower() if isinstance(selected_api, str) else ""

                # 키워드 기반으로 provider 결정
                if "gemini" in selected_lower or "google" in selected_lower:
                    provider = "google"
                elif "gpt" in selected_lower or "openai" in selected_lower:
                    provider = "openai"
                elif "claude" in selected_lower or "anthropic" in selected_lower:
                    provider = "anthropic"
                else:
                    provider = "anthropic"  # 기본값

                print(f"[씬 분석 페이지] 선택된 API: {selected_api} -> provider: {provider}")

            analyzer = SceneAnalyzer(provider=provider)

            progress.update(2, "스크립트 분석 중...")
            progress.update(2, "스크립트 분석 중...")
            progress.info(f"사용 프롬프트: {selected_template_name}")
            progress.info(f"스크립트 길이: {len(script):,}자")

            # 실제 사용되는 모델 표시
            if provider == "google" and hasattr(analyzer, 'gemini_model_name'):
                progress.info(f"사용 AI: Gemini ({analyzer.gemini_model_name})")
            else:
                progress.info(f"사용 AI: {provider}")

            start_time = time.time()
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

            print(f"[씬 분석 페이지] 세션 저장 완료: 씬 {len(scenes)}개, 캐릭터 {len(characters)}개")

            # 캐릭터 visual_prompt 디버그 출력
            for char in characters[:3]:  # 처음 3개만
                name = char.get("name", "Unknown")
                has_prompt = bool(char.get("visual_prompt"))
                print(f"  - {name}: visual_prompt={'있음' if has_prompt else '없음'}")

            # 사용량 기록 (provider에 따른 모델 ID 결정)
            model_id_map = {
                "anthropic": "claude-sonnet-4-20250514",
                "google": "gemini-1.5-flash",
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
                "google": "gemini-1.5-flash",
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
                        st.write(", ".join(chars))
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

    # 데이터 로드
    scenes_data = []
    characters_data = []
    full_result = None

    if scenes_path.exists():
        with open(scenes_path, "r", encoding="utf-8") as f:
            scenes_data = json.load(f)

    if characters_path.exists():
        with open(characters_path, "r", encoding="utf-8") as f:
            characters_data = json.load(f)

    if analysis_path.exists():
        with open(analysis_path, "r", encoding="utf-8") as f:
            full_result = json.load(f)

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
            if scenes_data:
                for scene in scenes_data:
                    scene_id = scene.get("scene_id", "?")
                    script_text = get_prompt(scene, "script_text") or scene.get("narration", "")
                    preview = script_text[:80] + "..." if len(script_text) > 80 else script_text

                    with st.expander(f"씬 {scene_id}: {preview}", expanded=False):
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

        with result_tab2:
            # 프롬프트 뷰어 컴포넌트 사용
            if scenes_data:
                render_prompts_viewer(scenes_data)
                st.divider()
                render_bulk_download_section(scenes_data, characters_data)
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

# 다음 단계 안내
st.divider()
if (project_path / "analysis" / "scenes.json").exists():
    st.success("씬 분석이 완료되었습니다!")
    col1, col2 = st.columns(2)
    with col1:
        st.page_link("pages/3.6_👤_캐릭터_관리.py", label="👤 3.6단계: 캐릭터 관리", icon="➡️")
    with col2:
        st.page_link("pages/4_🎤_TTS_생성.py", label="🎤 4단계: TTS 생성", icon="➡️")
