"""
AI 롱폼 유튜브 생성 Tool - 메인 앱

시니어 타겟 롱폼 유튜브 영상 제작 자동화 도구

실행 방법:
    streamlit run app.py
"""
import streamlit as st
from pathlib import Path
import sys

# 루트 디렉토리를 path에 추가
ROOT_DIR = Path(__file__).parent
sys.path.insert(0, str(ROOT_DIR))

from utils.project_manager import (
    init_session_state,
    render_project_sidebar,
    get_current_project,
    get_current_project_config,
    list_projects,
    render_project_info,
    render_workflow_progress
)
from config.settings import validate_api_keys, get_missing_api_keys
from config.constants import WORKFLOW_STEPS

# 외부 프로젝트 런처
from utils.external_launcher import (
    EXTERNAL_PROJECTS,
    get_project_status,
    launch_project,
    open_folder,
    open_in_browser,
    is_port_in_use
)

# 페이지 설정
st.set_page_config(
    page_title="AI 롱폼 유튜브 Tool",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 세션 상태 초기화
init_session_state()

# 사이드바 렌더링
render_project_sidebar()

# === 메인 콘텐츠 ===
st.title("🎬 AI 롱폼 유튜브 생성 Tool")
st.caption("시니어 타겟 롱폼 유튜브 영상 제작 자동화")

# API 키 확인
missing_keys = get_missing_api_keys()
if missing_keys:
    st.warning(f"⚠️ 다음 API 키가 설정되지 않았습니다: {', '.join(missing_keys)}")
    st.info("`.env` 파일을 생성하고 API 키를 입력하세요. `.env.example` 파일을 참고하세요.")

st.divider()

# 현재 프로젝트 정보
project_path = get_current_project()

if project_path:
    # 프로젝트 정보 표시
    render_project_info()

    st.divider()

    # 워크플로우 진행 상황
    st.subheader("📋 워크플로우")
    render_workflow_progress()

    st.divider()

    # 단계별 바로가기
    st.subheader("🚀 단계별 바로가기")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.markdown("### 리서치")
        st.page_link("pages/1_📊_키워드_리서치.py", label="📊 키워드 리서치", icon="1️⃣")
        st.page_link("pages/2_🔍_영상_리서치.py", label="🔍 영상 리서치", icon="2️⃣")

    with col2:
        st.markdown("### 콘텐츠")
        st.page_link("pages/3_📝_스크립트_생성.py", label="📝 스크립트 생성", icon="3️⃣")
        st.page_link("pages/4_🎤_TTS_생성.py", label="🎤 TTS 생성", icon="4️⃣")

    with col3:
        st.markdown("### 이미지")
        st.page_link("pages/5_🖼️_이미지_프롬프트.py", label="🖼️ 이미지 프롬프트", icon="5️⃣")
        st.page_link("pages/6_🎨_이미지_생성.py", label="🎨 이미지 생성", icon="6️⃣")

    with col4:
        st.markdown("### 마무리")
        st.page_link("pages/7_📦_Vrew_Export.py", label="📦 Vrew Export", icon="7️⃣")

    st.divider()

    # 프로젝트 폴더 구조
    with st.expander("📁 프로젝트 폴더 구조"):
        st.code(f"""
{project_path.name}/
├── research/           # 2단계: 영상 리서치 결과
│   ├── video_list.xlsx
│   ├── selected_videos.json
│   └── transcripts/    # 자막 추출
├── scripts/            # 3단계: 생성된 스크립트
│   ├── draft_ko.txt
│   └── final_ko.txt
├── audio/              # 4단계: TTS 오디오
│   ├── voice_ko.mp3
│   ├── voice_ko.srt
│   └── paragraph_breaks.json
├── prompts/            # 5단계: 이미지 프롬프트
│   ├── segment_groups.json
│   ├── image_prompts.xlsx
│   └── thumbnail_prompts.json
├── images/             # 6단계: 생성된 이미지
│   ├── content/
│   └── thumbnail/
└── export/             # 7단계: Vrew Export
    ├── images/
    ├── audio.mp3
    ├── subtitles.srt
    ├── script_for_vrew.txt
    └── image_mapping.xlsx
        """)

    # ═══════════════════════════════════════════════════════
    # 🚀 외부 프로젝트 실행 섹션 (v1.0)
    # ═══════════════════════════════════════════════════════
    st.divider()
    st.subheader("🚀 외부 프로젝트 실행")

    ext_cols = st.columns(len(EXTERNAL_PROJECTS))

    for idx, (project_id, project) in enumerate(EXTERNAL_PROJECTS.items()):
        with ext_cols[idx]:
            status = get_project_status(project_id)

            # 프로젝트 카드
            st.markdown(f"#### {project['icon']} {project['name']}")
            st.caption(f"📁 `{project['path']}`")
            st.caption(f"📝 {project['description']}")

            # 상태 표시
            if not status.get("exists"):
                st.error("❌ 경로 없음")
            elif project["type"] == "streamlit":
                if status.get("running"):
                    st.success(f"🟢 실행 중 (포트: {status['port']})")
                else:
                    st.info("⚪ 중지됨")
            else:
                st.info(f"📦 {project['type']}")

            # 버튼들
            btn_col1, btn_col2 = st.columns(2)

            with btn_col1:
                if project["type"] == "streamlit" and status.get("running"):
                    # 실행 중: 브라우저에서 열기
                    if st.button(
                        "🌐 열기",
                        key=f"open_{project_id}",
                        use_container_width=True
                    ):
                        open_in_browser(status["url"])
                        st.toast(f"✅ {project['name']} 브라우저에서 열림")
                elif status.get("exists"):
                    # 실행 버튼
                    btn_label = "🚀 실행" if project["type"] == "streamlit" else "🌐 열기"
                    if st.button(
                        btn_label,
                        key=f"launch_{project_id}",
                        type="primary",
                        use_container_width=True
                    ):
                        with st.spinner(f"{project['name']} 실행 중..."):
                            result = launch_project(project_id)

                        if result["success"]:
                            st.success(f"✅ {result['message']}")
                            if result.get("url"):
                                import time
                                time.sleep(2)
                                open_in_browser(result["url"])
                            st.rerun()
                        elif result.get("already_running"):
                            st.warning(f"⚠️ {result['message']}")
                            open_in_browser(result["url"])
                        else:
                            st.error(f"❌ {result['message']}")

            with btn_col2:
                # 폴더 열기 버튼
                if st.button(
                    "📂 폴더",
                    key=f"folder_{project_id}",
                    use_container_width=True,
                    disabled=not status.get("exists")
                ):
                    if open_folder(project["path"]):
                        st.toast(f"✅ 폴더 열림")
                    else:
                        st.error("❌ 폴더 열기 실패")

else:
    # 프로젝트 미선택 시
    st.info("👈 왼쪽 사이드바에서 프로젝트를 생성하거나 선택하세요.")

    st.divider()

    # 소개 섹션
    st.subheader("📖 소개")

    st.markdown("""
    이 도구는 **시니어 대상 롱폼 유튜브 영상 제작**을 자동화합니다.

    ### 🎯 타겟 오디언스
    - 55세 이상 한국인
    - 60세 이상 일본인

    ### ⚙️ 핵심 기능
    - **영상 리서치**: YouTube API로 트렌드 분석 (캐싱으로 할당량 절약)
    - **스크립트 생성**: Claude AI + 시니어 톤앤매너 가이드
    - **TTS 생성**: Edge TTS + 문단별 무음 패딩 (1.5초)
    - **이미지 생성**: FLUX + SRT 세그먼트 그룹 기준
    - **Vrew Export**: 바로 편집 가능한 폴더 구조

    ### 🔄 워크플로우
    """)

    # 워크플로우 다이어그램
    cols = st.columns(len(WORKFLOW_STEPS))
    for i, step in enumerate(WORKFLOW_STEPS):
        with cols[i]:
            st.markdown(f"**{step['icon']}**")
            st.caption(step['name'])

    st.divider()

    # 최근 프로젝트
    projects = list_projects()
    if projects:
        st.subheader("📂 최근 프로젝트")

        for project in projects[:5]:
            col1, col2, col3 = st.columns([3, 1, 1])
            with col1:
                st.write(f"**{project['name']}**")
            with col2:
                st.caption(project.get('language', 'ko').upper())
            with col3:
                st.caption(f"단계 {project.get('current_step', 1)}/7")

# === 푸터 ===
st.divider()
st.caption("AI 롱폼 유튜브 생성 Tool v2.1 | Vrew 편집을 위한 소스 생성기")
