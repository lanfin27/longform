# -*- coding: utf-8 -*-
"""
ImageFX UI 컴포넌트

쿠키 만료 알림, 갱신 팝업 등 UI 관련 기능
시드 잠금 기능 (v1.3) - 이미지 일관성 유지
- v1.2: 업로드 이미지 기준 시드 설정 기능 추가
- v1.3: 커스텀 시드 이미지 생성 기능 추가 (프롬프트 입력 → ImageFX 생성 → 시드 잠금)
"""

import streamlit as st
import random
import os
from pathlib import Path
from typing import Tuple, Optional
from utils.imagefx_cookie_manager import (
    get_cookie_state,
    CookieStatus,
    reset_cookie_state,
    save_imagefx_cookie,
    is_auth_error,
    COOKIE_RENEWAL_GUIDE_KO,
    auto_refresh_cookies,
    check_auto_refresh_available,
    get_auto_refresh_status_message
)


def show_cookie_status_banner():
    """쿠키 상태 배너 표시 (페이지 상단) - v2.0 자동 갱신 지원"""

    state = get_cookie_state()
    auto_status = check_auto_refresh_available()

    if state.status == CookieStatus.EXPIRED:
        st.error("**🍪 ImageFX 쿠키 만료됨** - 쿠키가 만료되어 이미지 생성이 불가능합니다.")

        col1, col2 = st.columns(2)

        with col1:
            if auto_status["any_available"]:
                if st.button("🔄 자동 갱신", key="cookie_auto_renewal_btn", type="primary"):
                    _handle_auto_refresh_banner()
            else:
                st.button("🔄 자동 갱신", key="cookie_auto_renewal_btn_disabled", disabled=True)

        with col2:
            if st.button("✏️ 수동 갱신", key="cookie_manual_renewal_btn"):
                st.session_state["show_cookie_renewal_modal"] = True
                st.rerun()

    elif state.status == CookieStatus.NOT_SET:
        st.warning("**🍪 ImageFX 쿠키 미설정** - ImageFX를 사용하려면 먼저 쿠키를 설정해야 합니다.")

        col1, col2 = st.columns(2)

        with col1:
            if auto_status["any_available"]:
                if st.button("🔄 자동 설정", key="cookie_auto_setup_btn", type="primary"):
                    _handle_auto_refresh_banner()
            else:
                st.button("🔄 자동 설정", key="cookie_auto_setup_btn_disabled", disabled=True)

        with col2:
            if st.button("✏️ 수동 설정", key="cookie_manual_setup_btn"):
                st.session_state["show_cookie_renewal_modal"] = True
                st.rerun()


def _handle_auto_refresh_banner():
    """배너에서의 자동 갱신 처리"""
    with st.spinner("🔄 쿠키 자동 갱신 중..."):
        success, message, method = auto_refresh_cookies(use_selenium_fallback=True)

        if success:
            st.success(f"✅ {message}")
            st.balloons()
            import time
            time.sleep(1)
            st.rerun()
        else:
            st.error(f"❌ {message}")
            st.session_state["show_cookie_renewal_modal"] = True
            st.rerun()


def show_cookie_renewal_modal():
    """쿠키 갱신 모달 팝업 (v2.0 - 자동/수동 갱신 지원)"""

    if not st.session_state.get("show_cookie_renewal_modal"):
        return

    # 모달 스타일 컨테이너
    with st.container():
        st.markdown("---")
        st.markdown("## 🍪 ImageFX 쿠키 갱신")

        # 자동 갱신 가능 여부 확인
        auto_status = check_auto_refresh_available()

        # 탭으로 자동/수동 선택
        tab_auto, tab_manual = st.tabs(["🔄 자동 갱신", "✏️ 수동 갱신"])

        with tab_auto:
            st.markdown("### 자동 쿠키 갱신")

            if auto_status["any_available"]:
                st.info(f"💡 {get_auto_refresh_status_message()}")

                # 사용 가능한 방법 표시
                if auto_status["chrome_available"]:
                    st.success(f"✅ Chrome 직접 추출: {auto_status['chrome_message']}")
                else:
                    st.warning(f"⚠️ Chrome 직접 추출: {auto_status['chrome_message']}")

                if auto_status["selenium_available"]:
                    st.success(f"✅ Selenium: {auto_status['selenium_message']}")
                else:
                    st.warning(f"⚠️ Selenium: {auto_status['selenium_message']}")

                st.markdown("---")

                col1, col2 = st.columns(2)

                with col1:
                    if st.button(
                        "🔄 자동 갱신 시작",
                        key="modal_auto_refresh_btn",
                        type="primary",
                        use_container_width=True
                    ):
                        with st.spinner("🔄 쿠키 자동 갱신 중... (최대 2분 소요)"):
                            success, message, method = auto_refresh_cookies(use_selenium_fallback=True)

                            if success:
                                st.success(f"✅ {message}")
                                st.balloons()
                                st.session_state["show_cookie_renewal_modal"] = False
                                import time
                                time.sleep(1)
                                st.rerun()
                            else:
                                st.error(f"❌ {message}")
                                st.info("'수동 갱신' 탭에서 직접 입력해주세요.")

                with col2:
                    if st.button("❌ 취소", key="modal_auto_cancel_btn", use_container_width=True):
                        st.session_state["show_cookie_renewal_modal"] = False
                        st.rerun()

            else:
                st.warning("⚠️ 자동 갱신 기능을 사용할 수 없습니다.")
                st.markdown("""
                **자동 갱신을 활성화하려면 아래 패키지를 설치하세요:**

                ```bash
                # 방법 1: Chrome 프로필 직접 추출 (권장, Windows만)
                pip install pywin32 pycryptodome

                # 방법 2: Selenium 브라우저 자동화
                pip install selenium webdriver-manager
                ```

                설치 후 앱을 **재시작**하면 자동 갱신을 사용할 수 있습니다.
                """)

                if st.button("❌ 닫기", key="modal_auto_close_btn"):
                    st.session_state["show_cookie_renewal_modal"] = False
                    st.rerun()

        with tab_manual:
            st.markdown("### 수동 쿠키 입력")

            # 갱신 가이드 표시
            with st.expander("📖 쿠키 추출 방법", expanded=False):
                st.markdown(COOKIE_RENEWAL_GUIDE_KO)

            # 새 쿠키 입력
            new_cookie = st.text_area(
                "쿠키 값 (Cookie Editor → Export → Header String)",
                height=120,
                placeholder="Cookie Editor에서 복사한 쿠키를 여기에 붙여넣기...\n\n예: SID=xxx; HSID=yyy; __Secure-1PSID=zzz; ...",
                key="new_cookie_input"
            )

            col1, col2, col3 = st.columns([1, 1, 2])

            with col1:
                if st.button("💾 쿠키 저장", key="save_new_cookie", type="primary", use_container_width=True):
                    if new_cookie.strip():
                        # 쿠키 저장
                        if save_imagefx_cookie(new_cookie.strip()):
                            # 상태 초기화
                            reset_cookie_state()

                            # 모달 닫기
                            st.session_state["show_cookie_renewal_modal"] = False

                            st.success("✅ 새 쿠키가 저장되었습니다!")
                            st.rerun()
                        else:
                            st.error("❌ 쿠키 저장 실패")
                    else:
                        st.error("쿠키를 입력해주세요.")

            with col2:
                if st.button("❌ 취소", key="cancel_cookie_renewal", use_container_width=True):
                    st.session_state["show_cookie_renewal_modal"] = False
                    st.rerun()

            with col3:
                # 바로가기 링크
                st.markdown(
                    "🔗 [ImageFX 페이지 열기](https://labs.google.com/fx/ko/tools/image-fx)"
                )

        st.markdown("---")


def show_cookie_expired_error_in_result(error_message: str) -> bool:
    """생성 결과에서 쿠키 만료 에러 표시 (v2.0 - 자동 갱신 지원)

    Returns:
        True if it was an auth error, False otherwise
    """

    if is_auth_error(error_message):
        st.error("### 🍪 쿠키 만료 오류")

        st.write("ImageFX 쿠키가 만료되었습니다.")

        # 자동 갱신 가능 여부 확인
        auto_status = check_auto_refresh_available()

        # 버튼 행
        col1, col2 = st.columns(2)

        with col1:
            # 자동 갱신 버튼 (v2.0)
            auto_btn_disabled = not auto_status["any_available"]
            auto_btn_label = "🔄 자동 쿠키 갱신" if auto_status["any_available"] else "🔄 자동 갱신 불가"

            if st.button(
                auto_btn_label,
                key="auto_cookie_refresh_btn",
                type="primary",
                use_container_width=True,
                disabled=auto_btn_disabled
            ):
                _handle_auto_refresh()

        with col2:
            # 수동 갱신 버튼
            if st.button(
                "✏️ 수동 갱신",
                key="manual_cookie_refresh_btn",
                use_container_width=True
            ):
                st.session_state["show_cookie_renewal_modal"] = True
                st.rerun()

        # 자동 갱신 상태 표시
        if auto_status["any_available"]:
            status_msg = get_auto_refresh_status_message()
            st.caption(f"💡 {status_msg}")
        else:
            # 자동 갱신 불가 시 설치 안내
            with st.expander("🔧 자동 갱신 활성화 방법"):
                st.markdown("""
                **자동 갱신을 사용하려면 추가 패키지 설치가 필요합니다:**

                ```bash
                # Chrome 프로필 직접 추출용 (권장)
                pip install pywin32 pycryptodome

                # 또는 Selenium 브라우저 자동화용
                pip install selenium webdriver-manager
                ```

                설치 후 앱을 재시작하면 자동 갱신 버튼이 활성화됩니다.
                """)

        # 오류 상세 (접기)
        with st.expander("📋 오류 상세"):
            st.code(error_message[:500], language=None)

        # 빠른 수동 갱신 방법 안내
        with st.expander("📖 빠른 수동 갱신 방법"):
            st.markdown("""
            1. **[ImageFX 페이지](https://labs.google.com/fx/ko/tools/image-fx)** 접속
            2. Google 계정으로 로그인 확인
            3. **Cookie Editor** 확장 프로그램 아이콘 클릭
            4. **Export** 버튼 → **Header String** 선택
            5. 위 **'수동 갱신'** 버튼 클릭 후 붙여넣기
            """)

        return True

    return False


def _handle_auto_refresh():
    """자동 쿠키 갱신 처리"""
    with st.spinner("🔄 쿠키 자동 갱신 중... (최대 2분 소요될 수 있습니다)"):
        success, message, method = auto_refresh_cookies(use_selenium_fallback=True)

        if success:
            st.success(f"✅ {message}")
            st.balloons()

            # 페이지 새로고침
            import time
            time.sleep(1)
            st.rerun()
        else:
            st.error(f"❌ {message}")
            st.info("수동 갱신 버튼을 눌러 직접 갱신해주세요.")


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


# ============================================================
# 시드 잠금 기능 (v1.1) - 이미지 일관성 유지
# ============================================================

def render_seed_lock_options(key_prefix: str = "seed", style_segment: str = "background") -> Tuple[bool, Optional[int]]:
    """
    시드 잠금 옵션 UI 렌더링

    Args:
        key_prefix: Streamlit 위젯 키 접두사
        style_segment: 스타일 세그먼트 ("character" 또는 "background", 기본값: "background")
                      - "character": 캐릭터 스타일 선택 UI 표시
                      - "background": 배경 스타일 선택 UI 표시

    Returns:
        (seed_lock_enabled: bool, locked_seed: int or None)
    """
    st.markdown("### 🔒 이미지 일관성 유지 (시드 잠금)")
    st.caption("동일한 시드를 사용하여 이미지 스타일/캐릭터 일관성을 유지합니다.")

    col1, col2 = st.columns([2, 1])

    with col1:
        # 시드 잠금 활성화
        seed_lock_enabled = st.checkbox(
            "🔒 시드 잠금 활성화",
            value=st.session_state.get(f'{key_prefix}_lock_enabled', False),
            key=f"{key_prefix}_lock_checkbox",
            help="첫 번째 이미지 생성 후 시드를 잠가 이후 이미지들의 스타일/캐릭터 일관성을 유지합니다."
        )

        st.session_state[f'{key_prefix}_lock_enabled'] = seed_lock_enabled

    with col2:
        # 현재 잠긴 시드 표시
        locked_seed = st.session_state.get(f'{key_prefix}_locked_seed', None)
        if locked_seed:
            st.metric("잠긴 시드", f"{locked_seed:,}")
        else:
            st.caption("시드 없음")

    if seed_lock_enabled:
        # 시드 잠금 모드 선택 (v1.3: custom 모드 추가)
        seed_mode = st.radio(
            "시드 모드",
            options=["auto", "manual", "first_image", "upload", "custom"],
            format_func=lambda x: {
                "auto": "🔄 자동 (첫 이미지 시드 자동 잠금)",
                "manual": "✏️ 수동 (시드 직접 입력)",
                "first_image": "🖼️ 첫 이미지 기준",
                "upload": "📤 업로드 이미지 기준",
                "custom": "🎨 커스텀 시드 이미지 생성"
            }[x],
            key=f"{key_prefix}_mode_radio",
            horizontal=False,
            label_visibility="collapsed"
        )

        st.session_state[f'{key_prefix}_mode'] = seed_mode

        if seed_mode == "manual":
            # 수동 시드 입력
            manual_seed = st.number_input(
                "시드 값 입력",
                min_value=1,
                max_value=2147483647,
                value=st.session_state.get(f'{key_prefix}_locked_seed', 12345),
                key=f"{key_prefix}_manual_input",
                help="1 ~ 2,147,483,647 사이의 정수"
            )
            st.session_state[f'{key_prefix}_locked_seed'] = manual_seed
            locked_seed = manual_seed

        elif seed_mode == "first_image":
            # 첫 이미지 시드 사용
            if locked_seed:
                st.success(f"✅ 첫 이미지 시드 잠금됨: {locked_seed:,}")
            else:
                st.info("ℹ️ 첫 번째 이미지 생성 시 시드가 자동으로 잠깁니다.")

        elif seed_mode == "auto":
            if locked_seed:
                st.success(f"✅ 자동 잠금된 시드: {locked_seed:,}")
            else:
                st.info("ℹ️ 첫 번째 이미지 생성 시 시드가 자동으로 잠깁니다.")

        elif seed_mode == "upload":
            # v1.2: 업로드 이미지 기준 시드 설정
            locked_seed = _render_upload_reference_mode(key_prefix, locked_seed)

        elif seed_mode == "custom":
            # v1.3: 커스텀 시드 이미지 생성
            # v1.5: style_segment 파라미터 전달 (캐릭터/배경 스타일 선택)
            locked_seed = _render_custom_seed_generation_mode(key_prefix, locked_seed, style_segment)

        # 버튼 행
        btn_col1, btn_col2 = st.columns(2)

        with btn_col1:
            if st.button("🔓 시드 잠금 해제", key=f"{key_prefix}_unlock_btn", use_container_width=True):
                st.session_state[f'{key_prefix}_locked_seed'] = None
                st.session_state[f'{key_prefix}_lock_enabled'] = False
                st.success("시드 잠금이 해제되었습니다.")
                st.rerun()

        with btn_col2:
            if st.button("🎲 새 시드 생성", key=f"{key_prefix}_new_btn", use_container_width=True):
                new_seed = random.randint(1, 2147483647)
                st.session_state[f'{key_prefix}_locked_seed'] = new_seed
                st.success(f"새 시드 생성됨: {new_seed:,}")
                st.rerun()

        # 일관성 유지 팁
        with st.expander("💡 일관성 유지 팁", expanded=False):
            st.markdown("""
            **⚠️ ImageFX/Imagen 시드 특성:**

            | API | 시드 효과 |
            |-----|-----------|
            | Stable Diffusion | ✅ 완전히 동일한 이미지 |
            | **ImageFX/Imagen** | ⚡ **유사한 스타일/구도** (완전 동일 X) |
            | DALL-E | ❌ 시드 미지원 |

            > 💡 ImageFX에서 시드 잠금 시:
            > - ✅ 비슷한 색감, 스타일, 전체적 분위기 유지
            > - ✅ 유사한 구도와 레이아웃
            > - ❌ **픽셀 단위 동일 이미지는 보장되지 않음**

            ---

            **시드 잠금 사용 시 팁:**

            1. **첫 이미지가 중요**: 마음에 드는 첫 이미지가 나올 때까지 시도 후 시드 잠금
            2. **프롬프트 일관성**: 시드가 같아도 프롬프트가 크게 다르면 결과 달라짐
            3. **캐릭터 설명 유지**: 캐릭터 외모 설명은 모든 프롬프트에 포함
            4. **스타일 키워드 고정**: "cinematic", "anime style" 등 스타일 키워드 일관되게 사용

            **권장 워크플로우:**
            ```
            1. 시드 잠금 OFF로 여러 이미지 생성
            2. 마음에 드는 이미지 선택
            3. 해당 이미지의 시드 확인 (메타데이터)
            4. 시드 잠금 ON + 해당 시드 입력
            5. 이후 씬들 일괄 생성
            ```
            """)

    return seed_lock_enabled, locked_seed


def lock_seed(seed: int, key_prefix: str = "seed"):
    """시드 잠금 설정"""
    st.session_state[f'{key_prefix}_locked_seed'] = seed
    st.session_state[f'{key_prefix}_lock_enabled'] = True
    print(f"[시드 잠금] 🔒 시드 잠금: {seed}", flush=True)


def unlock_seed(key_prefix: str = "seed"):
    """시드 잠금 해제"""
    st.session_state[f'{key_prefix}_locked_seed'] = None
    st.session_state[f'{key_prefix}_lock_enabled'] = False
    print("[시드 잠금] 🔓 시드 잠금 해제", flush=True)


def get_seed_for_generation(key_prefix: str = "seed") -> Optional[int]:
    """
    이미지 생성에 사용할 시드 반환

    Returns:
        잠긴 시드 값 또는 None (랜덤 시드 사용)
    """
    if not st.session_state.get(f'{key_prefix}_lock_enabled', False):
        return None

    return st.session_state.get(f'{key_prefix}_locked_seed', None)


def update_locked_seed_from_result(seed: int, key_prefix: str = "seed"):
    """
    이미지 생성 결과에서 시드를 잠금 (자동/첫 이미지 모드용)

    첫 번째 이미지 생성 후 호출하여 시드 자동 잠금
    """
    seed_mode = st.session_state.get(f'{key_prefix}_mode', 'auto')
    locked_seed = st.session_state.get(f'{key_prefix}_locked_seed', None)

    # 아직 시드가 잠기지 않은 경우에만 자동 잠금
    if locked_seed is None and seed_mode in ['auto', 'first_image']:
        st.session_state[f'{key_prefix}_locked_seed'] = seed
        print(f"[시드 잠금] 🔒 첫 이미지 시드 자동 잠금: {seed}", flush=True)


def render_image_with_seed_info(
    image_path: str,
    seed: int,
    scene_id: int,
    key_prefix: str = "seed"
):
    """
    이미지 표시 + 시드 정보 및 잠금 버튼

    Args:
        image_path: 이미지 경로
        seed: 사용된 시드
        scene_id: 씬 ID
        key_prefix: 키 접두사
    """
    col1, col2 = st.columns([3, 1])

    with col1:
        st.image(image_path, caption=f"씬 {scene_id}")

    with col2:
        st.metric("시드", f"{seed:,}" if seed else "N/A")

        if seed and st.button(
            "🔒 이 시드 잠금",
            key=f"lock_seed_{key_prefix}_{scene_id}",
            use_container_width=True
        ):
            lock_seed(seed, key_prefix)
            st.success(f"시드 {seed:,} 잠금됨!")
            st.rerun()


# ============================================================
# v1.2: 업로드 이미지 기준 시드 설정 기능
# ============================================================

def _render_upload_reference_mode(key_prefix: str, current_locked_seed: Optional[int]) -> Optional[int]:
    """
    📤 업로드 이미지 기준 시드 설정 UI

    Args:
        key_prefix: session_state 키 접두사
        current_locked_seed: 현재 잠긴 시드 값

    Returns:
        설정된 시드 값 (또는 기존 값)
    """
    st.markdown("---")
    st.markdown("#### 📤 기준 이미지 업로드")

    st.info("""
    **사용 방법:**
    1. ImageFX 웹사이트에서 마음에 드는 이미지를 생성합니다.
    2. 해당 이미지를 다운로드하고, 시드 번호를 복사합니다.
    3. 아래에 이미지를 업로드하고 시드 번호를 입력합니다.
    4. "기준으로 설정" 버튼을 클릭합니다.
    """)

    col1, col2 = st.columns([1, 1])

    with col1:
        # 이미지 업로드
        uploaded_file = st.file_uploader(
            "기준 이미지 업로드",
            type=["png", "jpg", "jpeg", "webp"],
            key=f"{key_prefix}_reference_upload",
            help="ImageFX에서 생성한 이미지를 업로드하세요."
        )

        # 업로드된 이미지 미리보기
        if uploaded_file:
            st.image(uploaded_file, caption="업로드된 기준 이미지", use_container_width=True)

            # 이미지 정보
            try:
                from PIL import Image
                img = Image.open(uploaded_file)
                st.caption(f"크기: {img.size[0]}x{img.size[1]} | 파일: {uploaded_file.name}")
                # 파일 포인터 리셋
                uploaded_file.seek(0)
            except Exception as e:
                st.caption(f"파일: {uploaded_file.name}")

    with col2:
        # 시드 입력
        st.markdown("**🔢 시드 번호 입력**")

        # 기존 저장된 시드가 있으면 기본값으로 사용
        saved_seed = st.session_state.get(f'{key_prefix}_upload_seed', "")
        if current_locked_seed and not saved_seed:
            saved_seed = str(current_locked_seed)

        seed_input = st.text_input(
            "ImageFX 시드 번호",
            value=saved_seed,
            key=f"{key_prefix}_upload_seed_input",
            placeholder="예: 1234567890",
            help="ImageFX에서 이미지 생성 시 표시된 시드 번호를 입력하세요."
        )

        # 시드 유효성 검사
        seed_valid = False
        seed_value = None
        if seed_input:
            try:
                seed_value = int(seed_input.strip())
                if seed_value > 0:
                    seed_valid = True
                    st.success(f"유효한 시드: {seed_value:,}")
                else:
                    st.error("시드는 양수여야 합니다.")
            except ValueError:
                st.error("시드는 숫자여야 합니다.")

        st.markdown("---")

        # 기준 설정 버튼
        set_reference_btn = st.button(
            "✅ 이 이미지와 시드를 기준으로 설정",
            type="primary",
            disabled=not (uploaded_file and seed_valid),
            key=f"{key_prefix}_set_upload_ref_btn",
            use_container_width=True
        )

        clear_reference_btn = st.button(
            "🗑️ 기준 초기화",
            key=f"{key_prefix}_clear_upload_ref_btn",
            use_container_width=True
        )

        # 버튼 동작
        if set_reference_btn and uploaded_file and seed_valid:
            # 이미지 저장
            saved_path = _save_reference_image(uploaded_file, key_prefix)

            # 시드 잠금
            st.session_state[f'{key_prefix}_locked_seed'] = seed_value
            st.session_state[f'{key_prefix}_upload_seed'] = seed_input
            st.session_state[f'{key_prefix}_reference_image_path'] = saved_path
            st.session_state[f'{key_prefix}_reference_set'] = True

            st.success(f"""
            **기준 설정 완료!**
            - 시드: {seed_value:,}
            - 이미지: {uploaded_file.name}
            """)
            st.balloons()
            current_locked_seed = seed_value

        if clear_reference_btn:
            _clear_reference_settings(key_prefix)
            st.info("기준 설정이 초기화되었습니다.")
            st.rerun()

    # 현재 설정된 기준 정보 표시
    _render_current_reference_info(key_prefix)

    return current_locked_seed


def _save_reference_image(uploaded_file, key_prefix: str) -> str:
    """기준 이미지를 프로젝트에 저장"""

    # 저장 디렉토리
    reference_dir = Path("data/reference_images")
    reference_dir.mkdir(parents=True, exist_ok=True)

    # 파일 저장 (기존 파일 덮어쓰기)
    import time
    timestamp = int(time.time())
    safe_name = uploaded_file.name.replace(" ", "_")
    file_path = reference_dir / f"ref_{key_prefix}_{timestamp}_{safe_name}"

    with open(file_path, "wb") as f:
        f.write(uploaded_file.getvalue())

    print(f"[기준이미지] 저장 완료: {file_path}", flush=True)

    return str(file_path)


def _clear_reference_settings(key_prefix: str):
    """기준 설정 초기화"""

    keys_to_clear = [
        f'{key_prefix}_locked_seed',
        f'{key_prefix}_upload_seed',
        f'{key_prefix}_reference_image_path',
        f'{key_prefix}_reference_set',
    ]

    for key in keys_to_clear:
        if key in st.session_state:
            del st.session_state[key]

    print(f"[기준이미지] {key_prefix} 설정 초기화 완료", flush=True)


def _render_current_reference_info(key_prefix: str):
    """현재 설정된 기준 정보 표시"""

    if st.session_state.get(f'{key_prefix}_reference_set', False):
        st.markdown("---")
        st.markdown("##### 📌 현재 기준 설정")

        ref_path = st.session_state.get(f'{key_prefix}_reference_image_path')
        locked_seed = st.session_state.get(f'{key_prefix}_locked_seed')

        col1, col2 = st.columns([1, 2])

        with col1:
            if ref_path and os.path.exists(ref_path):
                st.image(ref_path, caption="현재 기준 이미지", use_container_width=True)
            else:
                st.warning("기준 이미지 파일을 찾을 수 없습니다.")

        with col2:
            st.markdown(f"""
            **🔒 잠긴 시드:** `{locked_seed:,}`

            **📁 기준 이미지:** `{os.path.basename(ref_path) if ref_path else 'N/A'}`

            **✅ 상태:** 활성화됨
            """)

            # 기준 이미지 다운로드
            if ref_path and os.path.exists(ref_path):
                with open(ref_path, "rb") as f:
                    st.download_button(
                        label="📥 기준 이미지 다운로드",
                        data=f.read(),
                        file_name=os.path.basename(ref_path),
                        mime="image/png",
                        key=f"{key_prefix}_download_ref_btn"
                    )


# ============================================================
# v1.3: 커스텀 시드 이미지 생성 기능
# v1.4: 배경 스타일 선택 기능 추가 (prefix/suffix/negative 적용)
# ============================================================

def _render_custom_seed_generation_mode(key_prefix: str, current_locked_seed: Optional[int], style_segment: str = "background") -> Optional[int]:
    """
    🎨 커스텀 시드 이미지 생성 UI

    사용자가 직접 프롬프트를 입력하여 시드 잠금용 기준 이미지를 생성
    v1.4: 배경 스타일 선택 및 prefix/suffix/negative 적용
    v1.5: style_segment 파라미터 추가 (캐릭터/배경 스타일 선택 지원)

    Args:
        key_prefix: session_state 키 접두사
        current_locked_seed: 현재 잠긴 시드 값
        style_segment: 스타일 세그먼트 ("character" 또는 "background")

    Returns:
        설정된 시드 값 (또는 기존 값)
    """
    from utils.style_manager import get_styles_by_segment, get_style_by_id

    # ⭐ v1.5: 스타일 세그먼트에 따른 UI 레이블 설정
    is_character = style_segment == "character"
    style_label = "캐릭터 스타일" if is_character else "배경 스타일"
    style_icon = "👤" if is_character else "🎨"
    style_desc = "캐릭터" if is_character else "배경"

    st.markdown("---")
    st.markdown("#### 🎨 커스텀 시드 이미지 생성")

    st.info(f"""
    **사용 방법:**
    1. **{style_label} 선택** (실제 이미지 생성과 동일한 스타일 적용)
    2. 원본 씬 프롬프트 작성 (스타일 없이 순수 묘사)
    3. "시드 이미지 생성" 버튼 클릭
    4. 마음에 드는 이미지가 나올 때까지 재생성
    5. "이 시드로 잠금" 버튼으로 시드 적용
    """)

    # ═══════════════════════════════════════════════════════
    # v1.5: 스타일 세그먼트에 따른 스타일 선택
    # ═══════════════════════════════════════════════════════
    st.markdown(f"##### {style_icon} {style_label}")

    # 스타일 목록 로드 (캐릭터 또는 배경)
    styles = get_styles_by_segment(style_segment)
    style_names = ["(스타일 없음)"] + [f"{s.name_ko} ({s.name})" for s in styles]
    style_ids = [None] + [s.id for s in styles]

    # 기본값: 상위 생성 옵션에서 선택된 스타일 동기화
    default_style_id = st.session_state.get(f'{key_prefix}_selected_style_id')
    default_idx = 0
    if default_style_id and default_style_id in style_ids:
        default_idx = style_ids.index(default_style_id)

    selected_style_name = st.selectbox(
        f"{style_label} 선택",
        options=style_names,
        index=default_idx,
        key=f"{key_prefix}_custom_{style_segment}_style",
        help=f"실제 이미지 생성 시와 동일한 {style_desc} 스타일의 Prefix/Suffix/Negative가 적용됩니다."
    )

    # 선택된 스타일 정보 가져오기
    selected_idx = style_names.index(selected_style_name)
    selected_style_id = style_ids[selected_idx]
    selected_style = get_style_by_id(selected_style_id) if selected_style_id else None

    # 스타일 프롬프트 미리보기
    if selected_style:
        with st.expander("📋 스타일 프롬프트 미리보기", expanded=False):
            if selected_style.prompt_prefix:
                st.markdown("**Prefix:**")
                prefix_preview = selected_style.prompt_prefix[:200] + "..." if len(selected_style.prompt_prefix) > 200 else selected_style.prompt_prefix
                st.code(prefix_preview, language=None)

            if selected_style.prompt_suffix:
                st.markdown("**Suffix:**")
                st.code(selected_style.prompt_suffix, language=None)

            if selected_style.negative_prompt:
                st.markdown("**🚫 Negative Prompt:**")
                neg_preview = selected_style.negative_prompt[:200] + "..." if len(selected_style.negative_prompt) > 200 else selected_style.negative_prompt
                st.code(neg_preview, language=None)

    st.markdown("---")

    # ═══════════════════════════════════════════════════════
    # 원본 씬 프롬프트 입력
    # ═══════════════════════════════════════════════════════
    st.markdown("##### 📝 원본 씬 프롬프트")
    st.caption("스타일 없이 순수한 씬/캐릭터 묘사만 입력하세요. 위에서 선택한 스타일이 자동 적용됩니다.")

    custom_prompt = st.text_area(
        "원본 씬 프롬프트",
        value=st.session_state.get(f'{key_prefix}_custom_prompt', ''),
        placeholder="예: 30대 한국인 남성 CEO, 검정 정장, 단정한 헤어스타일, 전문적인 표정, 밝은 오피스 배경",
        height=100,
        key=f"{key_prefix}_custom_prompt_input",
        help="일관성을 유지하고 싶은 캐릭터나 장면을 상세히 설명하세요.",
        label_visibility="collapsed"
    )

    # ═══════════════════════════════════════════════════════
    # v1.4: 최종 프롬프트 미리보기
    # ═══════════════════════════════════════════════════════
    if custom_prompt.strip():
        # 최종 프롬프트 조합
        final_prompt_parts = []
        if selected_style and selected_style.prompt_prefix:
            final_prompt_parts.append(selected_style.prompt_prefix.strip())
        final_prompt_parts.append(custom_prompt.strip())
        if selected_style and selected_style.prompt_suffix:
            final_prompt_parts.append(selected_style.prompt_suffix.strip())

        preview_final_prompt = ", ".join(final_prompt_parts)
        preview_negative = selected_style.negative_prompt if selected_style else ""

        with st.expander("👁️ 최종 프롬프트 미리보기", expanded=True):
            st.markdown("**✨ 최종 프롬프트 (Prefix + 원본 + Suffix):**")
            preview_text = preview_final_prompt[:500] + "..." if len(preview_final_prompt) > 500 else preview_final_prompt
            st.code(preview_text, language=None)
            st.caption(f"총 길이: {len(preview_final_prompt)}자")

            if preview_negative:
                st.markdown("**🚫 Negative Prompt:**")
                neg_text = preview_negative[:200] + "..." if len(preview_negative) > 200 else preview_negative
                st.code(neg_text, language=None)

    st.markdown("---")

    # 이미지 비율 선택
    st.markdown("##### 📐 이미지 비율")
    aspect_options = {
        "IMAGE_ASPECT_RATIO_LANDSCAPE": "🖼️ 가로 (16:9)",
        "IMAGE_ASPECT_RATIO_PORTRAIT": "📱 세로 (9:16)",
        "IMAGE_ASPECT_RATIO_SQUARE": "⬜ 정사각형 (1:1)"
    }
    selected_aspect = st.selectbox(
        "이미지 비율",
        options=list(aspect_options.keys()),
        format_func=lambda x: aspect_options[x],
        index=0,
        key=f"{key_prefix}_custom_aspect",
        label_visibility="collapsed"
    )

    # 생성 버튼
    gen_col1, gen_col2 = st.columns([2, 1])

    with gen_col1:
        generate_btn = st.button(
            "🎲 시드 이미지 생성",
            key=f"{key_prefix}_generate_custom_btn",
            type="primary",
            use_container_width=True,
            disabled=not custom_prompt.strip()
        )

    with gen_col2:
        if st.session_state.get(f'{key_prefix}_custom_generated'):
            if st.button("🔄 재생성", key=f"{key_prefix}_regenerate_custom_btn", use_container_width=True):
                st.session_state[f'{key_prefix}_custom_generated'] = False
                st.session_state[f'{key_prefix}_custom_result'] = None
                st.rerun()

    # 이미지 생성 처리
    if generate_btn and custom_prompt.strip():
        with st.spinner("🎨 시드 이미지 생성 중... (약 30초 소요)"):
            try:
                # v1.4: 스타일 prefix/suffix 적용
                final_prompt_parts = []
                if selected_style and selected_style.prompt_prefix:
                    final_prompt_parts.append(selected_style.prompt_prefix.strip())
                final_prompt_parts.append(custom_prompt.strip())
                if selected_style and selected_style.prompt_suffix:
                    final_prompt_parts.append(selected_style.prompt_suffix.strip())

                final_prompt = ", ".join(final_prompt_parts)
                negative_prompt = selected_style.negative_prompt if selected_style else ""

                print(f"[CustomSeed v1.4] 스타일: {selected_style.name_ko if selected_style else '없음'}")
                print(f"[CustomSeed v1.4] 최종 프롬프트 길이: {len(final_prompt)}자")
                if negative_prompt:
                    print(f"[CustomSeed v1.4] 네거티브: {negative_prompt[:80]}...")

                # ImageFX 클라이언트 임포트 및 생성 (v2.0 최적화)
                from utils.imagefx_client import (
                    get_optimized_imagefx_client,
                    ImageFXCache,
                    AspectRatio,
                    GeneratedImage
                )
                from config.settings import load_imagefx_cookie

                # ⭐ 쿠키 로드 (session_state > 파일 순서)
                imagefx_cookie = st.session_state.get("imagefx_cookie", "") or load_imagefx_cookie()
                if not imagefx_cookie:
                    st.error("❌ ImageFX 쿠키가 설정되지 않았습니다. API 관리 페이지에서 쿠키를 입력해주세요.")
                    st.info("⚙️ API 관리 → ImageFX 쿠키 설정에서 쿠키를 입력하세요.")
                    raise ValueError("ImageFX 쿠키 미설정")

                print(f"[CustomSeed v2.0] ⚡ 최적화된 워커 사용")
                print(f"[CustomSeed v2.0] ImageFX 쿠키 로드됨 (길이: {len(imagefx_cookie)})")

                # v2.0: 최적화된 클라이언트 사용 (싱글톤 워커 재사용)
                manager = get_optimized_imagefx_client(imagefx_cookie)

                # 비율 변환
                aspect_map = {
                    "IMAGE_ASPECT_RATIO_LANDSCAPE": "LANDSCAPE",
                    "IMAGE_ASPECT_RATIO_PORTRAIT": "PORTRAIT",
                    "IMAGE_ASPECT_RATIO_SQUARE": "SQUARE"
                }
                aspect_value = aspect_map.get(selected_aspect, "LANDSCAPE")

                # v2.0: 이미지 생성 (워커 재사용 + 네거티브 프롬프트 적용)
                gen_result = manager.generate_image(
                    prompt=final_prompt,
                    aspect_ratio=aspect_value,
                    seed=None,  # 랜덤 시드 사용
                    negative_prompt=negative_prompt  # 스타일 네거티브 적용
                )

                if gen_result.get("success"):
                    # GeneratedImage 객체로 변환 (호환성)
                    result = GeneratedImage(
                        file_path=gen_result.get("path", ""),
                        prompt=final_prompt,
                        seed=gen_result.get("seed")
                    )

                    # v1.4: 결과 저장 (스타일 정보 포함)
                    # v1.5: style_segment 추가
                    st.session_state[f'{key_prefix}_custom_generated'] = True
                    st.session_state[f'{key_prefix}_custom_result'] = {
                        'image_path': result.path,
                        'seed': result.seed,
                        'prompt': custom_prompt,
                        'final_prompt': final_prompt,
                        'negative_prompt': negative_prompt,
                        'style_id': selected_style_id,
                        'style_name': selected_style.name_ko if selected_style else "없음",
                        'style_segment': style_segment  # ⭐ v1.5: 캐릭터/배경 구분
                    }
                    st.session_state[f'{key_prefix}_custom_prompt'] = custom_prompt

                    st.success(f"✅ 시드 이미지 생성 완료! (시드: {result.seed:,})")
                    st.rerun()
                else:
                    # v2.0: 상세 오류 메시지 표시
                    error_msg = gen_result.get("error", "알 수 없는 오류")
                    st.error(f"❌ 이미지 생성 실패: {error_msg}")

            except Exception as e:
                st.error(f"❌ 이미지 생성 오류: {str(e)}")
                print(f"[CustomSeed v1.4] 생성 오류: {e}", flush=True)

    # 생성된 이미지 미리보기
    if st.session_state.get(f'{key_prefix}_custom_generated') and st.session_state.get(f'{key_prefix}_custom_result'):
        result = st.session_state[f'{key_prefix}_custom_result']

        st.markdown("---")
        st.markdown("##### 📷 생성된 시드 이미지")

        img_col, info_col = st.columns([2, 1])

        with img_col:
            if result.get('image_path') and os.path.exists(result['image_path']):
                st.image(result['image_path'], caption="시드 이미지 미리보기", use_container_width=True)
            else:
                st.warning("이미지 파일을 찾을 수 없습니다.")

        with info_col:
            # v1.4: 스타일 정보 표시 개선
            # v1.5: style_segment에 따른 레이블 변경
            result_style_segment = result.get('style_segment', 'background')
            style_type_label = "캐릭터 스타일" if result_style_segment == "character" else "배경 스타일"
            style_icon = "👤" if result_style_segment == "character" else "🎨"
            st.markdown(f"""
            **🔢 생성된 시드:** `{result.get('seed', 'N/A'):,}`

            **{style_icon} {style_type_label}:** {result.get('style_name', '없음')}
            """)

            st.markdown("**📝 사용된 프롬프트:**")
            st.caption(result.get('prompt', '')[:100] + ('...' if len(result.get('prompt', '')) > 100 else ''))

            st.markdown("---")

            # 이 시드로 잠금 버튼
            if st.button(
                "✅ 이 시드로 잠금",
                key=f"{key_prefix}_apply_custom_seed_btn",
                type="primary",
                use_container_width=True
            ):
                seed_value = result.get('seed')
                if seed_value:
                    # 시드 잠금 설정
                    st.session_state[f'{key_prefix}_locked_seed'] = seed_value
                    st.session_state[f'{key_prefix}_custom_seed_set'] = True
                    st.session_state[f'{key_prefix}_custom_seed_image'] = result.get('image_path')

                    # 기준 이미지 저장
                    _save_custom_seed_image(result.get('image_path'), key_prefix)

                    st.success(f"✅ 시드 {seed_value:,}이(가) 잠금되었습니다!")
                    st.balloons()
                    current_locked_seed = seed_value
                else:
                    st.error("시드 값을 찾을 수 없습니다.")

            # 취소 버튼
            if st.button(
                "❌ 취소 (다시 생성)",
                key=f"{key_prefix}_cancel_custom_btn",
                use_container_width=True
            ):
                st.session_state[f'{key_prefix}_custom_generated'] = False
                st.session_state[f'{key_prefix}_custom_result'] = None
                st.rerun()

    # 현재 커스텀 시드 설정 정보 표시
    _render_custom_seed_status(key_prefix)

    return current_locked_seed


def _save_custom_seed_image(image_path: str, key_prefix: str) -> Optional[str]:
    """커스텀 시드 이미지를 기준 이미지로 저장"""
    if not image_path or not os.path.exists(image_path):
        return None

    try:
        # 저장 디렉토리
        import shutil
        reference_dir = Path("data/reference_images")
        reference_dir.mkdir(parents=True, exist_ok=True)

        # 파일 복사
        import time
        timestamp = int(time.time())
        dest_filename = f"custom_seed_{key_prefix}_{timestamp}.png"
        dest_path = reference_dir / dest_filename

        shutil.copy2(image_path, dest_path)

        # session_state에 경로 저장
        st.session_state[f'{key_prefix}_reference_image_path'] = str(dest_path)

        print(f"[CustomSeed] 기준 이미지 저장: {dest_path}", flush=True)
        return str(dest_path)

    except Exception as e:
        print(f"[CustomSeed] 이미지 저장 실패: {e}", flush=True)
        return None


def _render_custom_seed_status(key_prefix: str):
    """현재 커스텀 시드 설정 상태 표시"""

    if st.session_state.get(f'{key_prefix}_custom_seed_set', False):
        locked_seed = st.session_state.get(f'{key_prefix}_locked_seed')
        ref_path = st.session_state.get(f'{key_prefix}_reference_image_path')

        st.markdown("---")
        st.markdown("##### 📌 현재 커스텀 시드 설정")

        status_col1, status_col2 = st.columns([1, 2])

        with status_col1:
            if ref_path and os.path.exists(ref_path):
                st.image(ref_path, caption="현재 기준 이미지", use_container_width=True)
            else:
                st.info("기준 이미지 없음")

        with status_col2:
            st.markdown(f"""
            **🔒 잠긴 시드:** `{locked_seed:,}`

            **✅ 상태:** 커스텀 시드 활성화됨

            이후 생성되는 모든 이미지에 이 시드가 적용됩니다.
            """)

            # 해제 버튼
            if st.button(
                "🗑️ 커스텀 시드 설정 초기화",
                key=f"{key_prefix}_clear_custom_seed_btn",
                use_container_width=True
            ):
                _clear_custom_seed_settings(key_prefix)
                st.info("커스텀 시드 설정이 초기화되었습니다.")
                st.rerun()


def _clear_custom_seed_settings(key_prefix: str):
    """커스텀 시드 설정 초기화"""

    keys_to_clear = [
        f'{key_prefix}_custom_generated',
        f'{key_prefix}_custom_result',
        f'{key_prefix}_custom_prompt',
        f'{key_prefix}_custom_seed_set',
        f'{key_prefix}_custom_seed_image',
        f'{key_prefix}_reference_image_path',
        f'{key_prefix}_locked_seed',
    ]

    for key in keys_to_clear:
        if key in st.session_state:
            del st.session_state[key]

    print(f"[CustomSeed] {key_prefix} 설정 초기화 완료", flush=True)
