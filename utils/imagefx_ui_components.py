# -*- coding: utf-8 -*-
"""
ImageFX UI 컴포넌트

쿠키 만료 알림, 갱신 팝업 등 UI 관련 기능
"""

import streamlit as st
from utils.imagefx_cookie_manager import (
    get_cookie_state,
    CookieStatus,
    reset_cookie_state,
    save_imagefx_cookie,
    is_auth_error,
    COOKIE_RENEWAL_GUIDE_KO
)


def show_cookie_status_banner():
    """쿠키 상태 배너 표시 (페이지 상단)"""

    state = get_cookie_state()

    if state.status == CookieStatus.EXPIRED:
        st.error("""
        **ImageFX 쿠키 만료됨**

        쿠키가 만료되어 이미지 생성이 불가능합니다.
        아래 '쿠키 갱신' 버튼을 클릭하여 새 쿠키를 입력해주세요.
        """)

        if st.button("쿠키 갱신", key="cookie_renewal_btn", type="primary"):
            st.session_state["show_cookie_renewal_modal"] = True
            st.rerun()

    elif state.status == CookieStatus.NOT_SET:
        st.warning("""
        **ImageFX 쿠키 미설정**

        ImageFX를 사용하려면 먼저 쿠키를 설정해야 합니다.
        """)

        if st.button("쿠키 설정", key="cookie_setup_btn"):
            st.session_state["show_cookie_renewal_modal"] = True
            st.rerun()


def show_cookie_renewal_modal():
    """쿠키 갱신 모달 팝업"""

    if not st.session_state.get("show_cookie_renewal_modal"):
        return

    # 모달 스타일 컨테이너
    with st.container():
        st.markdown("---")
        st.markdown("## ImageFX 쿠키 갱신")

        # 갱신 가이드 표시
        with st.expander("쿠키 추출 방법 (클릭하여 펼치기)", expanded=True):
            st.markdown(COOKIE_RENEWAL_GUIDE_KO)

        # 새 쿠키 입력
        st.markdown("### 새 쿠키 입력")

        new_cookie = st.text_area(
            "쿠키 값",
            height=100,
            placeholder="Cookie Editor에서 복사한 쿠키를 여기에 붙여넣기...",
            key="new_cookie_input"
        )

        col1, col2, col3 = st.columns([1, 1, 2])

        with col1:
            if st.button("쿠키 저장", key="save_new_cookie", type="primary"):
                if new_cookie.strip():
                    # 쿠키 저장
                    if save_imagefx_cookie(new_cookie.strip()):
                        # 상태 초기화
                        reset_cookie_state()

                        # 모달 닫기
                        st.session_state["show_cookie_renewal_modal"] = False

                        st.success("새 쿠키가 저장되었습니다!")
                        st.rerun()
                    else:
                        st.error("쿠키 저장 실패")
                else:
                    st.error("쿠키를 입력해주세요.")

        with col2:
            if st.button("취소", key="cancel_cookie_renewal"):
                st.session_state["show_cookie_renewal_modal"] = False
                st.rerun()

        with col3:
            # 바로가기 링크
            st.markdown(
                "[ImageFX 페이지 열기](https://labs.google/fx/tools/image-fx)"
            )

        st.markdown("---")


def show_cookie_expired_error_in_result(error_message: str) -> bool:
    """생성 결과에서 쿠키 만료 에러 표시

    Returns:
        True if it was an auth error, False otherwise
    """

    if is_auth_error(error_message):
        st.error(f"""
        ### 쿠키 만료 오류

        ImageFX 쿠키가 만료되었습니다.

        **오류 내용:**
        ```
        {error_message[:300]}...
        ```
        """)

        # 즉시 갱신 버튼
        if st.button("지금 쿠키 갱신하기", key="immediate_renewal", type="primary"):
            st.session_state["show_cookie_renewal_modal"] = True
            st.rerun()

        # 간단 가이드
        with st.expander("빠른 쿠키 갱신 방법"):
            st.markdown("""
            1. [labs.google/fx/tools/image-fx](https://labs.google/fx/tools/image-fx) 접속
            2. Cookie Editor 아이콘 클릭
            3. **Export** -> **Header String** 클릭
            4. 위 '쿠키 갱신하기' 버튼 클릭 후 붙여넣기
            """)

        return True

    return False


def check_cookie_before_generation() -> bool:
    """
    이미지 생성 전 쿠키 상태 확인

    Returns:
        True: 생성 가능
        False: 쿠키 문제로 생성 불가
    """

    state = get_cookie_state()

    if state.status == CookieStatus.NOT_SET:
        st.error("ImageFX 쿠키가 설정되지 않았습니다.")
        if st.button("쿠키 설정하기", key="pre_gen_cookie_setup"):
            st.session_state["show_cookie_renewal_modal"] = True
            st.rerun()
        return False

    if state.status == CookieStatus.EXPIRED:
        st.error("ImageFX 쿠키가 만료되었습니다.")
        if st.button("쿠키 갱신하기", key="pre_gen_cookie_renewal"):
            st.session_state["show_cookie_renewal_modal"] = True
            st.rerun()
        return False

    return True


def render_cookie_status_indicator():
    """쿠키 상태 인디케이터 (사이드바용)"""

    state = get_cookie_state()

    if state.status == CookieStatus.VALID:
        st.success("ImageFX: 정상")
        if state.last_success:
            st.caption(f"마지막 성공: {state.last_success.strftime('%m/%d %H:%M')}")

    elif state.status == CookieStatus.EXPIRED:
        st.error("ImageFX: 쿠키 만료")
        if st.button("갱신", key="sidebar_cookie_renewal"):
            st.session_state["show_cookie_renewal_modal"] = True
            st.rerun()

    elif state.status == CookieStatus.NOT_SET:
        st.warning("ImageFX: 미설정")
        if st.button("설정", key="sidebar_cookie_setup"):
            st.session_state["show_cookie_renewal_modal"] = True
            st.rerun()
