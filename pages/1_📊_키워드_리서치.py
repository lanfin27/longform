"""
1단계: 키워드 리서치

Claude/Gemini를 활용한 키워드 분석 및 선정
"""
import streamlit as st
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from utils.project_manager import (
    ensure_project_selected,
    get_current_project,
    render_project_sidebar,
    update_project_step
)
from utils.api_helper import (
    require_api_key,
    show_api_status_sidebar
)

# 페이지 설정
st.set_page_config(
    page_title="키워드 리서치",
    page_icon="📊",
    layout="wide"
)

render_project_sidebar()
show_api_status_sidebar()

if not ensure_project_selected():
    st.stop()

project_path = get_current_project()

st.title("📊 1단계: 키워드 리서치")
st.caption("Claude/Gemini를 활용한 키워드 분석 및 선정 (반자동)")

st.divider()

st.info("""
### 📝 키워드 리서치 가이드

이 단계는 **반자동**으로 진행됩니다.

1. **시드 키워드 입력**: 영상 주제와 관련된 기본 키워드를 입력합니다.
2. **AI 분석**: Claude 또는 Gemini가 연관 키워드와 트렌드를 분석합니다.
3. **키워드 선정**: 분석 결과를 바탕으로 최종 키워드를 선정합니다.

💡 **팁**: 다음 단계(영상 리서치)에서 선정된 키워드로 YouTube 검색을 진행합니다.
""")

st.divider()

# 시드 키워드 입력
st.subheader("🌱 시드 키워드")
seed_keyword = st.text_input(
    "기본 키워드",
    placeholder="예: 1인 창업, 시니어 부업, 은퇴 후 수입"
)

category = st.selectbox(
    "카테고리",
    ["비즈니스/창업", "건강/웰빙", "재테크/투자", "취미/라이프스타일", "교육/자기계발", "기타"]
)

st.divider()

# AI 분석 섹션 (향후 구현)
st.subheader("🤖 AI 키워드 분석")

col1, col2 = st.columns(2)

with col1:
    if st.button("Claude로 분석", use_container_width=True):
        if require_api_key("ANTHROPIC_API_KEY", "Anthropic Claude API"):
            st.info("Claude API 연동 예정")
        else:
            st.stop()

with col2:
    if st.button("Gemini로 분석", use_container_width=True):
        if require_api_key("GEMINI_API_KEY", "Google Gemini API"):
            st.info("Gemini API 연동 예정")
        else:
            st.stop()

st.divider()

# 수동 키워드 입력
st.subheader("📝 최종 키워드 선정")

final_keywords = st.text_area(
    "선정된 키워드 (줄바꿈으로 구분)",
    placeholder="1인 창업 아이디어\n시니어 부업\n은퇴 후 수입원",
    height=150
)

if st.button("✅ 키워드 저장", type="primary"):
    if final_keywords:
        # 키워드 저장 로직
        keywords_list = [k.strip() for k in final_keywords.split("\n") if k.strip()]

        keywords_file = project_path / "research" / "keywords.txt"
        keywords_file.parent.mkdir(parents=True, exist_ok=True)

        with open(keywords_file, "w", encoding="utf-8") as f:
            f.write("\n".join(keywords_list))

        update_project_step(1)
        st.success(f"✅ {len(keywords_list)}개 키워드가 저장되었습니다!")

        st.divider()
        st.page_link("pages/2_🔍_영상_리서치.py", label="🔍 2단계: 영상 리서치로 이동", icon="➡️")
    else:
        st.error("키워드를 입력하세요.")
