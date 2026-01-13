# -*- coding: utf-8 -*-
"""
ImageFX UI 컴포넌트

쿠키 만료 알림, 갱신 팝업 등 UI 관련 기능
시드 잠금 기능 (v1.1) - 이미지 일관성 유지
"""

import streamlit as st
import random
from typing import Tuple, Optional
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


# ============================================================
# 시드 잠금 기능 (v1.1) - 이미지 일관성 유지
# ============================================================

def render_seed_lock_options(key_prefix: str = "seed") -> Tuple[bool, Optional[int]]:
    """
    시드 잠금 옵션 UI 렌더링

    Args:
        key_prefix: Streamlit 위젯 키 접두사

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
        # 시드 잠금 모드 선택
        seed_mode = st.radio(
            "시드 모드",
            options=["auto", "manual", "first_image"],
            format_func=lambda x: {
                "auto": "🔄 자동 (첫 이미지 시드 자동 잠금)",
                "manual": "✏️ 수동 (시드 직접 입력)",
                "first_image": "🖼️ 첫 이미지 기준"
            }[x],
            key=f"{key_prefix}_mode_radio",
            horizontal=True,
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
