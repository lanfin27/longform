"""
3단계: 스크립트 생성

Claude AI를 활용한 시니어 타겟 스크립트 생성
Trans-creation(초월 번역) 지원
"""
import streamlit as st
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
from utils.data_loader import (
    load_selected_videos,
    save_script,
    load_script,
    save_script_metadata
)
from utils.script_sync_manager import sync_save_script
from config.settings import ANTHROPIC_API_KEY, SUPPORTED_LANGUAGES
from config.senior_style_guide import get_style_prompt, get_style_checklist, get_example
from config.constants import SCRIPT_TONES
from utils.api_helper import (
    require_api_key,
    show_api_status_sidebar
)
from utils.progress_ui import render_api_selector, StreamlitProgressUI
from core.api.api_manager import get_api_manager


# ============================================================
# ⭐ 성능 최적화: 캐싱 데코레이터
# ============================================================
@st.cache_data(ttl=60, show_spinner=False)
def _cached_load_selected_videos(project_path_str):
    """선택된 영상 로드 (캐싱 적용)"""
    from pathlib import Path
    return load_selected_videos(Path(project_path_str))


@st.cache_data(ttl=60, show_spinner=False)
def _cached_load_script(project_path, language: str, script_type: str):
    """스크립트 로드 (캐싱 적용)"""
    return load_script(project_path, language, script_type)


# 페이지 설정
st.set_page_config(
    page_title="스크립트 생성",
    page_icon="📝",
    layout="wide"
)

render_project_sidebar()
show_api_status_sidebar()

if not ensure_project_selected():
    st.stop()

project_path = get_current_project()
project_config = get_current_project_config()

st.title("📝 3단계: 스크립트 생성")
st.caption("Claude AI + 시니어 톤앤매너 가이드")

# API 키 확인
if not require_api_key("ANTHROPIC_API_KEY", "Anthropic Claude API"):
    st.stop()

st.divider()

# === 탭 구성 ===
tab_settings, tab_generate, tab_manual, tab_preview, tab_translate = st.tabs([
    "⚙️ 설정", "✨ AI 생성", "✏️ 수동 입력", "👁️ 미리보기", "🌏 번역"
])

# === 설정 탭 ===
with tab_settings:
    st.subheader("스크립트 설정")

    col1, col2 = st.columns(2)

    with col1:
        topic = st.text_input(
            "영상 주제",
            placeholder="예: 2024년 1인 창업 아이디어 10가지"
        )

        language = st.selectbox(
            "타겟 언어",
            options=list(SUPPORTED_LANGUAGES.keys()),
            format_func=lambda x: SUPPORTED_LANGUAGES[x],
            index=0 if project_config.get("language") == "ko" else 1
        )

        target_length = st.slider(
            "목표 길이 (분)",
            min_value=5,
            max_value=30,
            value=15,
            help="스크립트 분량 (분당 약 250자)"
        )

    with col2:
        tone = st.selectbox(
            "톤",
            options=list(SCRIPT_TONES.keys()),
            format_func=lambda x: SCRIPT_TONES[x]
        )

        include_hook = st.checkbox("HOOK 포함 (처음 30초)", value=True)
        include_cta = st.checkbox("CTA 포함 (구독 유도)", value=True)

    st.divider()

    # 시니어 톤앤매너 가이드
    st.subheader("🎯 시니어 톤앤매너 가이드")

    apply_senior_style = st.checkbox("시니어 톤앤매너 적용", value=True)

    if apply_senior_style:
        with st.expander("📋 스타일 가이드 보기", expanded=False):
            checklist = get_style_checklist(language)
            for item in checklist:
                st.markdown(f"- {item}")

            st.divider()
            example = get_example(language)
            st.markdown("**예시:**")
            st.error(f"❌ {example['bad']}")
            st.success(f"✅ {example['good']}")

    st.divider()

    # 벤치마킹 정보
    st.subheader("📚 벤치마킹 정보")

    selected_videos = _cached_load_selected_videos(str(project_path))
    if selected_videos:
        st.success(f"✅ {len(selected_videos)}개의 벤치마킹 영상이 로드되었습니다.")

        with st.expander("영상 목록"):
            for v in selected_videos:
                st.caption(f"- {v['title'][:50]}...")
    else:
        st.warning("선택된 벤치마킹 영상이 없습니다. 2단계에서 영상을 선택하세요.")

    # 추가 지시사항
    additional_instructions = st.text_area(
        "추가 지시사항 (선택)",
        placeholder="특별히 강조할 내용이나 포함할 사항을 입력하세요.",
        height=100
    )

# === 생성 탭 ===
with tab_generate:
    st.subheader("스크립트 생성")

    # API 선택
    st.markdown("### ⚙️ AI 설정")
    col1, col2 = st.columns(2)

    with col1:
        selected_api = render_api_selector(
            task="script_generation",
            label="스크립트 생성 AI",
            key_prefix="script_gen"
        )

    with col2:
        st.caption("선택한 AI로 스크립트를 생성합니다.")

    st.divider()

    if st.button("✨ 스크립트 생성", type="primary", use_container_width=True):
        if not topic:
            st.error("영상 주제를 입력하세요.")
        else:
            import time
            start_time = time.time()

            # 프로그레스 UI
            progress = StreamlitProgressUI(
                task_name="스크립트 생성",
                total_steps=3,
                show_logs=True
            )

            api_manager = get_api_manager()

            try:
                from core.ai.claude_client import ClaudeClient

                progress.update(1, "AI 클라이언트 초기화...")
                progress.info("Claude API 연결 중...")

                client = ClaudeClient()

                # 벤치마킹 스크립트 (있으면)
                benchmark_scripts = None
                benchmark_comments = None

                progress.update(2, "스크립트 생성 중...")
                progress.info(f"주제: {topic}")
                progress.info(f"목표 길이: {target_length}분")

                result = client.generate_script(
                    topic=topic,
                    language=language,
                    target_length=target_length,
                    tone=tone,
                    benchmark_scripts=benchmark_scripts,
                    benchmark_comments=benchmark_comments,
                    include_hook=include_hook,
                    include_cta=include_cta,
                    additional=additional_instructions
                )

                script = result["script"]
                elapsed = time.time() - start_time

                progress.update(3, "저장 중...")

                # 저장 (기존 + 동기화)
                save_script(project_path, script, language, "draft")
                sync_save_script(script, language, "ai", str(project_path))  # 씬 분석과 동기화
                save_script_metadata(project_path, {
                    "topic": topic,
                    "language": language,
                    "target_length": target_length,
                    "tone": tone,
                    "tokens_used": result.get("tokens_used", 0),
                    "word_count": result.get("word_count", 0)
                })

                # 사용량 기록
                api_manager.record_usage(
                    provider="anthropic",
                    model_id="claude-sonnet-4-20250514",
                    function="text_generation",
                    tokens_input=result.get("tokens_used", 0) // 2,
                    tokens_output=result.get("tokens_used", 0) // 2,
                    duration_seconds=elapsed,
                    success=True,
                    project_name=project_path.name,
                    step_name="script_generation"
                )

                st.session_state["generated_script"] = script
                update_project_step(3)

                progress.complete(f"스크립트 생성 완료! (토큰: {result.get('tokens_used', 0):,})")

            except Exception as e:
                elapsed = time.time() - start_time
                progress.fail(str(e))

                # 에러 기록
                api_manager.record_usage(
                    provider="anthropic",
                    model_id="claude-sonnet-4-20250514",
                    function="text_generation",
                    duration_seconds=elapsed,
                    success=False,
                    error_message=str(e),
                    project_name=project_path.name,
                    step_name="script_generation"
                )

    # 생성된 스크립트 표시
    if "generated_script" in st.session_state:
        st.divider()
        st.text_area(
            "생성된 스크립트",
            st.session_state["generated_script"],
            height=400
        )

# === 수동 입력 탭 ===
with tab_manual:
    st.subheader("✏️ 스크립트 수동 입력")

    st.info("""
    **외부에서 작성한 스크립트를 직접 입력하거나 파일로 업로드하세요.**

    - AI 생성 없이 기존 스크립트 사용 가능
    - TXT, DOCX 파일 지원
    """)

    # 언어 선택
    manual_language = st.selectbox(
        "스크립트 언어",
        options=list(SUPPORTED_LANGUAGES.keys()),
        format_func=lambda x: SUPPORTED_LANGUAGES[x],
        key="manual_language"
    )

    # 입력 방식 선택
    input_method = st.radio(
        "입력 방식",
        ["📝 텍스트 직접 입력", "📁 파일 업로드 (.txt, .docx)"],
        horizontal=True,
        key="script_input_method"
    )

    script_content = None

    if "텍스트" in input_method:
        script_content = st.text_area(
            "스크립트 내용",
            height=400,
            placeholder="여기에 스크립트를 입력하세요...\n\n안녕하세요, 오늘은 ...",
            key="manual_script_textarea"
        )

    else:  # 파일 업로드
        uploaded_file = st.file_uploader(
            "파일 선택",
            type=["txt", "docx"],
            help="텍스트 파일 또는 Word 문서를 업로드하세요.",
            key="manual_script_file"
        )

        if uploaded_file:
            try:
                if uploaded_file.name.endswith('.txt'):
                    script_content = uploaded_file.read().decode('utf-8')
                elif uploaded_file.name.endswith('.docx'):
                    from components.input_source_selector import read_docx_file
                    script_content = read_docx_file(uploaded_file)

                st.success(f"✅ 파일 로드 완료: {uploaded_file.name}")

                # 미리보기
                with st.expander("📋 스크립트 미리보기", expanded=True):
                    st.text_area("내용", script_content[:2000], height=200, disabled=True, key="manual_preview")
                    if len(script_content) > 2000:
                        st.caption(f"... 외 {len(script_content) - 2000}자 더 있음")

            except Exception as e:
                st.error(f"파일 읽기 실패: {e}")

    # 저장 버튼
    if script_content and script_content.strip():
        st.markdown("---")

        col1, col2 = st.columns([3, 1])
        with col1:
            st.write(f"📊 글자 수: **{len(script_content):,}자** | 예상 길이: **~{len(script_content) // 250}분**")

        with col2:
            save_type = st.selectbox(
                "저장 유형",
                ["draft", "final"],
                format_func=lambda x: "초안" if x == "draft" else "최종본",
                key="manual_save_type"
            )

        if st.button("💾 스크립트 저장", type="primary", use_container_width=True, key="save_manual_script"):
            save_script(project_path, script_content.strip(), manual_language, save_type)
            sync_save_script(script_content.strip(), manual_language, "manual", str(project_path))  # 씬 분석과 동기화
            st.session_state["generated_script"] = script_content.strip()
            update_project_step(3)
            st.success(f"✅ {SUPPORTED_LANGUAGES[manual_language]} 스크립트({save_type})가 저장되었습니다!")
            st.balloons()

# === 미리보기 탭 ===
with tab_preview:
    st.subheader("스크립트 미리보기")

    # 언어 선택
    preview_lang = st.selectbox(
        "언어 선택",
        ["ko", "ja"],
        format_func=lambda x: "한국어" if x == "ko" else "일본어",
        key="preview_lang"
    )

    # 스크립트 타입 선택
    script_type = st.radio(
        "버전",
        ["draft", "final"],
        format_func=lambda x: "초안" if x == "draft" else "최종",
        horizontal=True
    )

    # 스크립트 로드 (⭐ 캐싱 적용)
    script = _cached_load_script(project_path, preview_lang, script_type)

    if script:
        st.text_area("스크립트 내용", script, height=500)

        # 통계
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("글자 수", f"{len(script):,}")
        with col2:
            st.metric("예상 길이", f"{len(script) // 250}분")
        with col3:
            st.metric("문단 수", script.count("\n\n") + 1)

        # 최종본으로 저장
        if script_type == "draft":
            if st.button("✅ 최종본으로 저장"):
                save_script(project_path, script, preview_lang, "final")
                sync_save_script(script, preview_lang, "manual", str(project_path))  # 씬 분석과 동기화
                st.success("최종본으로 저장되었습니다!")
    else:
        st.info("저장된 스크립트가 없습니다.")

# === 번역 탭 ===
with tab_translate:
    st.subheader("🌏 일본어 Trans-creation")

    st.info("""
    **Trans-creation(초월 번역)**: 단순 번역이 아닌 문화 적응형 재창작

    - 한국어 원문의 '의도'와 '감정'을 전달
    - 일본 시니어가 공감할 수 있는 표현으로 변환
    - 문화적 요소 적응 (예시, 비유 등)
    """)

    # 한국어 스크립트 로드 (⭐ 캐싱 적용)
    ko_script = _cached_load_script(project_path, "ko", "final") or _cached_load_script(project_path, "ko", "draft")

    if ko_script:
        st.text_area("원본 (한국어)", ko_script, height=200)

        if st.button("🌏 일본어로 Trans-creation", type="primary"):
            with st.spinner("Trans-creation 진행 중..."):
                try:
                    from core.ai.claude_client import ClaudeClient

                    client = ClaudeClient()
                    result = client.transcreate_to_japanese(ko_script, topic or "")

                    ja_script = result["script"]
                    save_script(project_path, ja_script, "ja", "draft")
                    sync_save_script(ja_script, "ja", "ai", str(project_path))  # 씬 분석과 동기화

                    st.session_state["ja_script"] = ja_script
                    st.success("✅ Trans-creation 완료!")

                except Exception as e:
                    st.error(f"실패: {str(e)}")

        if "ja_script" in st.session_state:
            st.text_area("결과 (일본어)", st.session_state["ja_script"], height=300)

    else:
        st.warning("한국어 스크립트를 먼저 생성하세요.")

st.divider()

# 다음 단계
st.page_link("pages/4_🎤_TTS_생성.py", label="🎤 4단계: TTS 생성으로 이동", icon="➡️")
