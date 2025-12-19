"""
입력 소스 선택기 컴포넌트

각 탭에서 사용할 수 있는 공통 컴포넌트.
자동(이전 단계) vs 수동(직접 입력) 선택 가능.
"""
import streamlit as st
from pathlib import Path
from typing import Optional, Callable, Any, List, Dict
import json


def render_input_source_selector(
    tab_name: str,
    auto_source_name: str,
    auto_load_func: Callable[[], Optional[Any]],
    manual_input_types: List[str] = None,
    file_types: List[str] = None,
    placeholder: str = "",
    height: int = 200,
    key_prefix: str = ""
) -> Dict[str, Any]:
    """
    입력 소스 선택기 렌더링

    Args:
        tab_name: 현재 탭 이름 (예: "씬 분석")
        auto_source_name: 자동 소스 이름 (예: "스크립트 탭")
        auto_load_func: 자동 로드 함수 (이전 단계 데이터 로드)
        manual_input_types: 수동 입력 유형 ["text", "file", "json"]
        file_types: 허용 파일 확장자 (예: ["txt", "docx"])
        placeholder: 텍스트 입력 플레이스홀더
        height: 텍스트 영역 높이
        key_prefix: 세션 상태 키 접두사

    Returns:
        {
            "source": "auto" | "manual_text" | "manual_file" | "manual_json",
            "data": 실제 데이터,
            "valid": bool
        }
    """
    if manual_input_types is None:
        manual_input_types = ["text", "file"]

    if file_types is None:
        file_types = ["txt"]

    key = f"{key_prefix}_{tab_name}_input_source"

    st.markdown("### 📥 입력 소스 선택")

    # 소스 선택 옵션 구성
    source_options = [f"🔄 자동: {auto_source_name}에서 가져오기"]

    if "text" in manual_input_types:
        source_options.append("✏️ 수동: 직접 입력")

    if "file" in manual_input_types:
        source_options.append("📁 수동: 파일 업로드")

    if "json" in manual_input_types:
        source_options.append("📋 수동: JSON 붙여넣기")

    selected_source = st.radio(
        "입력 방식 선택",
        source_options,
        key=f"{key}_radio",
        horizontal=True
    )

    result = {
        "source": "auto",
        "data": None,
        "valid": False
    }

    # === 자동 모드 ===
    if "자동" in selected_source:
        result["source"] = "auto"

        with st.spinner("이전 단계 데이터 로드 중..."):
            auto_data = auto_load_func()

        if auto_data:
            st.success(f"✅ {auto_source_name}에서 데이터를 가져왔습니다.")

            # 데이터 미리보기
            with st.expander("📋 데이터 미리보기", expanded=False):
                if isinstance(auto_data, str):
                    preview = auto_data[:2000]
                    st.text_area("내용", preview, height=150, disabled=True, key=f"{key}_auto_preview")
                    if len(auto_data) > 2000:
                        st.caption(f"... 외 {len(auto_data) - 2000}자 더 있음")
                elif isinstance(auto_data, list):
                    st.write(f"**총 {len(auto_data)}개 항목**")
                    st.json(auto_data[:3])  # 처음 3개만 표시
                elif isinstance(auto_data, dict):
                    st.json(auto_data)

            result["data"] = auto_data
            result["valid"] = True
        else:
            st.warning(f"⚠️ {auto_source_name}에 데이터가 없습니다.")
            st.info(f"'{auto_source_name}'에서 먼저 작업하거나, 수동 입력을 선택하세요.")

    # === 수동: 직접 입력 ===
    elif "직접 입력" in selected_source:
        result["source"] = "manual_text"

        st.markdown("**직접 입력:**")

        manual_text = st.text_area(
            "내용을 입력하세요",
            value=st.session_state.get(f"{key}_manual_text", ""),
            height=height,
            placeholder=placeholder,
            key=f"{key}_text_input"
        )

        # 세션에 저장
        st.session_state[f"{key}_manual_text"] = manual_text

        if manual_text and manual_text.strip():
            result["data"] = manual_text.strip()
            result["valid"] = True
            st.success(f"✅ {len(manual_text)}자 입력됨")
        else:
            st.info("내용을 입력하세요.")

    # === 수동: 파일 업로드 ===
    elif "파일 업로드" in selected_source:
        result["source"] = "manual_file"

        st.markdown(f"**파일 업로드:** (지원 형식: {', '.join(file_types)})")

        uploaded_file = st.file_uploader(
            "파일 선택",
            type=file_types,
            key=f"{key}_file_upload"
        )

        if uploaded_file:
            try:
                # 파일 읽기
                if uploaded_file.name.endswith('.txt'):
                    content = uploaded_file.read().decode('utf-8')
                elif uploaded_file.name.endswith('.docx'):
                    content = read_docx_file(uploaded_file)
                elif uploaded_file.name.endswith('.json'):
                    content = json.load(uploaded_file)
                elif uploaded_file.name.endswith('.csv'):
                    content = read_csv_file(uploaded_file)
                else:
                    content = uploaded_file.read().decode('utf-8')

                result["data"] = content
                result["valid"] = True

                st.success(f"✅ 파일 로드 완료: {uploaded_file.name}")

                # 미리보기
                with st.expander("📋 파일 내용 미리보기"):
                    if isinstance(content, str):
                        st.text_area("내용", content[:2000], height=150, disabled=True, key=f"{key}_file_preview")
                    else:
                        st.json(content if len(str(content)) < 5000 else "데이터가 너무 큽니다")

            except Exception as e:
                st.error(f"❌ 파일 읽기 실패: {e}")

    # === 수동: JSON 붙여넣기 ===
    elif "JSON" in selected_source:
        result["source"] = "manual_json"

        st.markdown("**JSON 데이터 붙여넣기:**")

        json_text = st.text_area(
            "JSON 형식으로 입력",
            height=height,
            placeholder='{"key": "value", ...} 또는 [{"item": 1}, ...]',
            key=f"{key}_json_input"
        )

        if json_text:
            try:
                parsed = json.loads(json_text)
                result["data"] = parsed
                result["valid"] = True
                st.success("✅ JSON 파싱 성공")

                with st.expander("📋 파싱된 데이터"):
                    st.json(parsed)
            except json.JSONDecodeError as e:
                st.error(f"❌ JSON 파싱 실패: {e}")

    return result


def read_docx_file(uploaded_file) -> str:
    """DOCX 파일 읽기"""
    try:
        from docx import Document
        import io

        doc = Document(io.BytesIO(uploaded_file.read()))
        text = "\n".join([para.text for para in doc.paragraphs])
        return text
    except ImportError:
        raise ImportError("python-docx 패키지가 필요합니다: pip install python-docx")


def read_csv_file(uploaded_file) -> List[Dict]:
    """CSV 파일 읽기"""
    import pandas as pd
    import io

    df = pd.read_csv(io.BytesIO(uploaded_file.read()))
    return df.to_dict('records')


def render_simple_text_input(
    label: str,
    placeholder: str = "",
    height: int = 200,
    key: str = "simple_text"
) -> Optional[str]:
    """간단한 텍스트 입력 (파일 업로드 포함)"""

    input_method = st.radio(
        "입력 방식",
        ["📝 텍스트 직접 입력", "📁 파일 업로드"],
        horizontal=True,
        key=f"{key}_method"
    )

    content = None

    if "텍스트" in input_method:
        content = st.text_area(
            label,
            height=height,
            placeholder=placeholder,
            key=f"{key}_textarea"
        )
    else:
        uploaded = st.file_uploader(
            "파일 선택",
            type=["txt", "docx"],
            key=f"{key}_file"
        )

        if uploaded:
            try:
                if uploaded.name.endswith('.txt'):
                    content = uploaded.read().decode('utf-8')
                elif uploaded.name.endswith('.docx'):
                    content = read_docx_file(uploaded)

                st.success(f"✅ 파일 로드: {uploaded.name}")

                with st.expander("미리보기"):
                    st.text_area("내용", content[:1000], disabled=True, key=f"{key}_preview")
            except Exception as e:
                st.error(f"파일 읽기 실패: {e}")

    return content if content and content.strip() else None


def render_json_import(
    label: str = "데이터 가져오기",
    expected_format: str = "배열 또는 객체",
    key: str = "json_import"
) -> Optional[Any]:
    """JSON 데이터 가져오기 (파일 또는 직접 입력)"""

    import_method = st.radio(
        "가져오기 방식",
        ["📁 JSON 파일 업로드", "📋 JSON 직접 입력"],
        horizontal=True,
        key=f"{key}_method"
    )

    data = None

    if "파일" in import_method:
        uploaded = st.file_uploader(
            "JSON 파일 선택",
            type=["json"],
            key=f"{key}_file"
        )

        if uploaded:
            try:
                data = json.load(uploaded)
                st.success(f"✅ 파일 로드: {uploaded.name}")
            except Exception as e:
                st.error(f"파일 파싱 실패: {e}")
    else:
        json_text = st.text_area(
            label,
            height=200,
            placeholder=f'예상 형식: {expected_format}',
            key=f"{key}_textarea"
        )

        if json_text:
            try:
                data = json.loads(json_text)
                st.success("✅ JSON 파싱 성공")
            except json.JSONDecodeError as e:
                st.error(f"JSON 파싱 실패: {e}")

    if data:
        with st.expander("📋 데이터 미리보기"):
            if isinstance(data, list):
                st.write(f"**{len(data)}개 항목**")
                st.json(data[:5])
            else:
                st.json(data)

    return data
