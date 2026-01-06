"""
스타일 관리 페이지

3개의 세그먼트로 스타일 분리 관리:
1. 캐릭터 스타일 - 캐릭터 이미지 생성용
2. 배경 스타일 - 배경 이미지 생성용
3. 씬 합성 스타일 - 씬+캐릭터 통합 이미지 생성용
"""
import streamlit as st
from pathlib import Path
from datetime import datetime
import json
import os
import time

from utils.style_manager import Style, StyleManager, get_style_manager, invalidate_style_cache
from core.image.image_generator import ImageGenerator, ImageConfig

st.set_page_config(page_title="스타일 관리", page_icon="🎨", layout="wide")


def get_project_path() -> str:
    """현재 프로젝트 경로 반환"""
    return st.session_state.get("project_path", "")


def check_api_key(provider: str) -> bool:
    """API 키 확인"""
    if provider == "together":
        return bool(os.environ.get("TOGETHER_API_KEY"))
    elif provider == "openai":
        return bool(os.environ.get("OPENAI_API_KEY"))
    elif provider == "google":
        return bool(os.environ.get("GOOGLE_API_KEY"))
    return False


def render_style_card(style: Style, manager: StyleManager, segment: str, idx: int):
    """스타일 카드 렌더링"""
    with st.container(border=True):
        # 헤더
        col_t, col_l = st.columns([4, 1])
        with col_t:
            st.markdown(f"**{style.name_ko}** ({style.name})")
        with col_l:
            if style.is_default:
                st.caption("🔒 기본")
            else:
                st.caption("✨ 커스텀")

        # 설명
        if style.description:
            st.caption(style.description)

        # 프롬프트 미리보기
        with st.expander("프롬프트 상세"):
            st.markdown("**Prefix:**")
            st.code(style.prompt_prefix or "(없음)", language=None)

            st.markdown("**Suffix:**")
            st.code(style.prompt_suffix or "(없음)", language=None)

            if style.negative_prompt:
                st.markdown("**Negative:**")
                st.code(style.negative_prompt, language=None)

        # 버튼 (segment를 포함하여 고유 키 생성)
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("✏️ 수정", key=f"edit_{segment}_{style.id}_{idx}", use_container_width=True):
                st.session_state["editing_style_id"] = style.id
                st.session_state["editing_segment"] = segment
                st.rerun()
        with col_b:
            if not style.is_default:
                if st.button("🗑️ 삭제", key=f"del_{segment}_{style.id}_{idx}", use_container_width=True):
                    if st.session_state.get(f"confirm_del_{segment}_{style.id}"):
                        manager.delete_style(style.id)
                        invalidate_style_cache()  # 다른 페이지에 알림
                        st.success("삭제됨!")
                        st.rerun()
                    else:
                        st.session_state[f"confirm_del_{segment}_{style.id}"] = True
                        st.warning("다시 클릭하면 삭제됩니다.")


def render_style_list(manager: StyleManager, segment: str):
    """세그먼트별 스타일 목록"""
    segment_info = manager.get_segment_info(segment)
    styles = manager.get_styles_by_segment(segment)

    st.subheader(f"📋 {segment_info['name']} 목록")
    st.caption(segment_info['description'])

    # 통계
    col1, col2 = st.columns(2)
    col1.metric("전체", len(styles))
    col2.metric("기본", sum(1 for s in styles if s.is_default))

    st.markdown("---")

    if not styles:
        st.info("스타일이 없습니다.")
        return

    # 카드 그리드
    cols = st.columns(2)
    for i, style in enumerate(styles):
        with cols[i % 2]:
            render_style_card(style, manager, segment, i)


def render_add_style(manager: StyleManager, segment: str):
    """새 스타일 추가"""
    segment_info = manager.get_segment_info(segment)

    st.subheader(f"➕ 새 {segment_info['name']} 추가")

    col1, col2 = st.columns([2, 1])

    with col1:
        new_id = st.text_input(
            "ID (영문, 밑줄)",
            placeholder=f"{segment}_my_style",
            key=f"add_id_{segment}"
        )
        new_name = st.text_input(
            "이름 (영문) *",
            placeholder="My Style",
            key=f"add_name_{segment}"
        )
        new_name_ko = st.text_input(
            "이름 (한글) *",
            placeholder="나만의 스타일",
            key=f"add_name_ko_{segment}"
        )

        new_prefix = st.text_area(
            "Prompt Prefix *",
            placeholder="스타일 설명을 프롬프트 앞에 추가",
            height=100,
            key=f"add_prefix_{segment}"
        )
        new_suffix = st.text_area(
            "Prompt Suffix",
            placeholder="프롬프트 뒤에 추가할 내용",
            height=80,
            key=f"add_suffix_{segment}"
        )

    with col2:
        new_negative = st.text_area(
            "Negative Prompt",
            placeholder="제외할 요소",
            height=80,
            key=f"add_neg_{segment}"
        )
        new_desc = st.text_area(
            "설명",
            height=80,
            key=f"add_desc_{segment}"
        )

    st.markdown("---")

    if st.button("➕ 스타일 추가", type="primary", key=f"add_submit_{segment}"):
        if not new_name or not new_name_ko or not new_prefix:
            st.error("이름과 Prefix는 필수입니다.")
            return

        import uuid
        import re

        # ID 정규화: 공백 → 언더스코어, 특수문자 제거
        if new_id:
            style_id = new_id.replace(" ", "_")
            style_id = re.sub(r'[^a-zA-Z0-9_가-힣]', '', style_id)
            style_id = style_id.lower() if style_id else f"{segment}_{uuid.uuid4().hex[:8]}"
        else:
            style_id = f"{segment}_{uuid.uuid4().hex[:8]}"

        new_style = Style(
            id=style_id,
            name=new_name,
            name_ko=new_name_ko,
            segment=segment,
            prompt_prefix=new_prefix,
            prompt_suffix=new_suffix or "",
            negative_prompt=new_negative or "",
            description=new_desc or "",
            is_default=False
        )

        # ✅ 튜플 반환 처리 (성공여부, 메시지)
        result = manager.add_style(new_style)

        # 하위 호환성: bool 또는 tuple 처리
        if isinstance(result, tuple):
            success, message = result
        else:
            success = result
            message = "추가됨" if result else "추가 실패"

        if success:
            invalidate_style_cache()  # 다른 페이지에 알림
            st.success(f"✅ {message}")
            st.rerun()
        else:
            st.error(f"❌ {message}")


def render_edit_style(manager: StyleManager):
    """스타일 수정 (st.form 사용으로 안정적인 저장)"""
    style_id = st.session_state.get("editing_style_id")
    segment = st.session_state.get("editing_segment")

    if not style_id:
        st.info("수정할 스타일을 선택하세요.")
        return

    style = manager.get_style_by_id(style_id)
    if not style:
        st.error("스타일을 찾을 수 없습니다.")
        return

    st.subheader(f"✏️ '{style.name_ko}' 수정")

    if style.is_default:
        st.info("기본 스타일은 프롬프트/설명만 수정 가능합니다.")

    # st.form 사용 - 폼 제출 시에만 rerun되므로 안정적
    # 폼 키는 style_id를 포함하여 유니크하게 생성
    form_key = f"edit_style_form_{style_id}"
    with st.form(key=form_key):
        col1, col2 = st.columns([2, 1])

        with col1:
            st.text_input("ID", value=style.id, disabled=True, key=f"{form_key}_id")

            new_name = st.text_input(
                "이름 (영문)",
                value=style.name,
                disabled=style.is_default,
                key=f"{form_key}_name"
            )
            new_name_ko = st.text_input(
                "이름 (한글)",
                value=style.name_ko,
                disabled=style.is_default,
                key=f"{form_key}_name_ko"
            )

            new_prefix = st.text_area(
                "Prompt Prefix",
                value=style.prompt_prefix,
                height=100,
                key=f"{form_key}_prefix"
            )
            new_suffix = st.text_area(
                "Prompt Suffix",
                value=style.prompt_suffix,
                height=80,
                key=f"{form_key}_suffix"
            )

        with col2:
            new_negative = st.text_area(
                "Negative Prompt",
                value=style.negative_prompt,
                height=80,
                key=f"{form_key}_neg"
            )
            new_desc = st.text_area(
                "설명",
                value=style.description,
                height=80,
                key=f"{form_key}_desc"
            )

        st.markdown("---")

        col_s, col_c = st.columns(2)
        with col_s:
            save_clicked = st.form_submit_button(
                "💾 저장",
                type="primary",
                use_container_width=True
            )
        with col_c:
            cancel_clicked = st.form_submit_button(
                "↩️ 취소",
                use_container_width=True
            )

    # 폼 제출 처리 (폼 외부에서)
    if save_clicked:
        # ⭐ 현재 세그먼트 가져오기 (세그먼트 불일치 방지!)
        target_segment = st.session_state.get("editing_segment")

        # 디버깅: 저장할 값 확인
        print(f"\n{'='*60}")
        print(f"[스타일 관리] 저장 버튼 클릭됨")
        print(f"[스타일 관리] style_id: {style_id}")
        print(f"[스타일 관리] target_segment: {target_segment}")  # ⭐ 세그먼트 로그 추가
        print(f"[스타일 관리] new_prefix (len={len(new_prefix)}): {new_prefix[:50]}...")
        print(f"[스타일 관리] new_suffix (len={len(new_suffix)}): {new_suffix[:50] if new_suffix else 'empty'}...")
        print(f"[스타일 관리] new_negative (len={len(new_negative)}): {new_negative[:50] if new_negative else 'empty'}...")
        print(f"{'='*60}")

        updates = {
            "prompt_prefix": new_prefix,
            "prompt_suffix": new_suffix,
            "negative_prompt": new_negative,
            "description": new_desc
        }
        if not style.is_default:
            updates["name"] = new_name
            updates["name_ko"] = new_name_ko

        # ⭐ target_segment 전달하여 올바른 세그먼트 수정!
        result = manager.update_style(style_id, updates, target_segment=target_segment)
        print(f"[스타일 관리] update_style 결과: {result}")

        if result:
            invalidate_style_cache()  # 다른 페이지에 알림
            st.success("✅ 저장되었습니다!")
            # 세션 상태 정리
            if "editing_style_id" in st.session_state:
                del st.session_state["editing_style_id"]
            if "editing_segment" in st.session_state:
                del st.session_state["editing_segment"]
            time.sleep(0.5)  # 저장 메시지를 보여주기 위한 짧은 대기
            st.rerun()
        else:
            st.error("❌ 저장에 실패했습니다. 콘솔 로그를 확인하세요.")

    if cancel_clicked:
        if "editing_style_id" in st.session_state:
            del st.session_state["editing_style_id"]
        if "editing_segment" in st.session_state:
            del st.session_state["editing_segment"]
        st.rerun()


def render_test_style(manager: StyleManager, segment: str):
    """스타일 테스트"""
    segment_info = manager.get_segment_info(segment)
    styles = manager.get_styles_by_segment(segment)

    st.subheader(f"🧪 {segment_info['name']} 테스트")

    if not styles:
        st.info("테스트할 스타일이 없습니다.")
        return

    # 스타일 선택
    style_names = {f"{s.name_ko} ({s.name})": s.id for s in styles}
    selected_name = st.selectbox("스타일 선택", list(style_names.keys()), key=f"test_style_{segment}")
    selected_style = manager.get_style_by_id(style_names[selected_name])

    # 테스트 주제
    default_subjects = {
        "character": "a young woman with brown hair",
        "background": "a modern office interior",
        "scene_composite": "a person standing in a modern office"
    }
    test_subject = st.text_input(
        "테스트 주제",
        value=default_subjects.get(segment, "test subject"),
        key=f"test_subject_{segment}"
    )

    # 모델 선택
    st.markdown("**이미지 생성 AI**")
    model_options = {
        "FLUX.2 Dev (권장, ~20원)": {"provider": "together", "model": "black-forest-labs/FLUX.2-dev"},
        "FLUX.2 Flex (~40원)": {"provider": "together", "model": "black-forest-labs/FLUX.2-flex"},
        "FLUX.2 Pro (고품질, ~40원)": {"provider": "together", "model": "black-forest-labs/FLUX.2-pro"},
        "DALL-E 3 ($0.04)": {"provider": "openai", "model": "dall-e-3"},
    }
    selected_model_name = st.selectbox("모델", list(model_options.keys()), key=f"test_model_{segment}")
    selected_model = model_options[selected_model_name]

    # API 키 상태
    has_key = check_api_key(selected_model["provider"])
    if has_key:
        st.success(f"✅ {selected_model['provider'].upper()} API 키 설정됨")
    else:
        st.warning(f"⚠️ {selected_model['provider'].upper()}_API_KEY 필요")

    # 크기
    col_w, col_h = st.columns(2)
    with col_w:
        test_width = st.selectbox("너비", [512, 768, 1024, 1280], index=2, key=f"test_w_{segment}")
    with col_h:
        test_height = st.selectbox("높이", [512, 768, 1024, 1280], index=2, key=f"test_h_{segment}")

    # 프롬프트 미리보기
    st.markdown("---")
    st.markdown("### 📝 최종 프롬프트")

    full_prompt = manager.build_prompt(selected_style, test_subject)
    final_prompt = st.text_area(
        "최종 프롬프트 (편집 가능)",
        value=full_prompt,
        height=150,
        key=f"final_prompt_{segment}"
    )

    # 생성 버튼
    if st.button("🎨 테스트 이미지 생성", type="primary", disabled=not has_key, key=f"gen_test_{segment}"):
        if not has_key:
            st.error("API 키를 설정하세요.")
            return

        test_dir = Path("data/style_tests") / segment
        test_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = test_dir / f"test_{selected_style.id}_{timestamp}.png"

        with st.spinner("이미지 생성 중..."):
            try:
                generator = ImageGenerator()
                config = ImageConfig(
                    provider=selected_model["provider"],
                    model=selected_model["model"],
                    width=test_width,
                    height=test_height
                )

                result = generator.generate(final_prompt, str(output_path), config)

                if result.success:
                    st.success(f"생성 완료! ({result.generation_time:.1f}초)")
                    st.image(result.image_path, use_container_width=True)
                    st.caption(f"저장: {result.image_path}")
                else:
                    st.error(f"생성 실패: {result.error}")

            except Exception as e:
                st.error(f"오류: {e}")


def render_segment_tab(manager: StyleManager, segment: str):
    """세그먼트별 탭 내용"""
    # 수정 모드인지 확인
    if st.session_state.get("editing_style_id") and st.session_state.get("editing_segment") == segment:
        render_edit_style(manager)
        return

    # 서브 탭
    sub_tabs = st.tabs(["📋 목록", "➕ 추가", "🧪 테스트"])

    with sub_tabs[0]:
        render_style_list(manager, segment)

    with sub_tabs[1]:
        render_add_style(manager, segment)

    with sub_tabs[2]:
        render_test_style(manager, segment)


def render_infographic_style_tab(manager: StyleManager):
    """인포그래픽 스타일 탭 - 레이아웃 미리보기 포함"""

    # 수정 모드인지 확인
    if st.session_state.get("editing_style_id") and st.session_state.get("editing_segment") == "infographic":
        render_edit_style(manager)
        return

    # 설명 섹션
    with st.expander("💡 인포그래픽 스타일이란?", expanded=False):
        st.markdown("""
        **인포그래픽용 이미지**는 가운데를 비워두고 모서리/가장자리에 요소를 배치합니다.

        이렇게 생성된 이미지는 인포그래픽(텍스트, 그래프 등)과 합성할 때
        서로 겹치지 않고 자연스럽게 조화를 이룹니다.

        ```
        일반 이미지:           인포그래픽용 이미지:
        ┌─────────────┐       ┌─────────────┐
        │  [캐릭터]   │       │[A]       [B]│
        │   가운데    │       │             │
        │             │       │   (비움)    │
        └─────────────┘       │             │
                              │[C]       [D]│
                              └─────────────┘
        ```
        """)

    # 서브 탭
    sub_tabs = st.tabs(["📋 목록", "➕ 추가", "📐 레이아웃", "🧪 테스트"])

    with sub_tabs[0]:
        render_style_list(manager, "infographic")

    with sub_tabs[1]:
        render_add_style(manager, "infographic")

    with sub_tabs[2]:
        render_layout_preview()

    with sub_tabs[3]:
        render_test_style(manager, "infographic")


def render_layout_preview():
    """레이아웃 미리보기"""

    st.markdown("### 📐 레이아웃 옵션")
    st.caption("인포그래픽 이미지 생성 시 선택할 수 있는 레이아웃입니다.")

    try:
        from utils.infographic_image_generator import get_available_layouts, get_layout_preview_html

        layouts = get_available_layouts()

        cols = st.columns(3)

        for idx, layout in enumerate(layouts):
            with cols[idx % 3]:
                with st.container(border=True):
                    st.markdown(f"**{layout['icon']} {layout['name']}**")
                    st.caption(layout['description'])

                    # 시각적 미리보기
                    preview_html = get_layout_preview_html(layout['id'])
                    st.markdown(preview_html, unsafe_allow_html=True)

    except ImportError:
        st.warning("인포그래픽 생성기 모듈을 로드할 수 없습니다.")


def main():
    st.title("🎨 스타일 관리")
    st.caption("캐릭터, 배경, 씬 합성, 인포그래픽 스타일을 세그먼트별로 관리합니다.")

    # StyleManager 초기화
    project_path = get_project_path()
    manager = get_style_manager(project_path if project_path else None)

    # 메인 탭 (4개 세그먼트)
    segment_tabs = st.tabs([
        "👤 캐릭터 스타일",
        "🏞️ 배경 스타일",
        "🎬 씬 합성 스타일",
        "📊 인포그래픽 스타일"
    ])

    with segment_tabs[0]:
        render_segment_tab(manager, "character")

    with segment_tabs[1]:
        render_segment_tab(manager, "background")

    with segment_tabs[2]:
        render_segment_tab(manager, "scene_composite")

    with segment_tabs[3]:
        render_infographic_style_tab(manager)

    # 사이드바 - Export/Import
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 📦 Export / Import")

    if st.sidebar.button("📤 스타일 내보내기"):
        export_data = {
            "character": [s.to_dict() for s in manager.get_styles_by_segment("character") if not s.is_default],
            "background": [s.to_dict() for s in manager.get_styles_by_segment("background") if not s.is_default],
            "scene_composite": [s.to_dict() for s in manager.get_styles_by_segment("scene_composite") if not s.is_default],
            "infographic": [s.to_dict() for s in manager.get_styles_by_segment("infographic") if not s.is_default]
        }

        st.sidebar.download_button(
            "💾 JSON 다운로드",
            data=json.dumps(export_data, ensure_ascii=False, indent=2),
            file_name="styles_export.json",
            mime="application/json"
        )

    uploaded = st.sidebar.file_uploader("📥 스타일 가져오기", type=['json'], key="import_styles")
    if uploaded:
        try:
            import_data = json.load(uploaded)
            count = 0
            for segment, styles in import_data.items():
                for style_data in styles:
                    style = Style.from_dict(style_data)
                    result = manager.add_style(style)
                    # 하위 호환성: bool 또는 tuple 처리
                    success = result[0] if isinstance(result, tuple) else result
                    if success:
                        count += 1
            if count > 0:
                invalidate_style_cache()  # 다른 페이지에 알림
            st.sidebar.success(f"{count}개 스타일 가져옴!")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"가져오기 실패: {e}")


if __name__ == "__main__":
    main()
