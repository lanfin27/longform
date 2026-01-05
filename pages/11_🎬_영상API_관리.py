"""
Streamlit 페이지: 영상 API 관리 대시보드
- 멀티 플랫폼/멀티 모델 지원
- 실시간 비용 표시
- 사용량 추적
"""
import streamlit as st
import asyncio
from datetime import datetime
import pandas as pd
from pathlib import Path
import sys
import tempfile

# 프로젝트 경로 설정
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from utils.video_api import (
    get_rotator,
    QuotaManager,
    CostCalculator,
    get_api_key,
    PLATFORM_CONFIGS,
    ALL_MODELS,
    FAL_MODELS,
    REPLICATE_MODELS,
    PIXVERSE_MODELS,
    VideoType,
    SpeedTier,
    QualityTier,
)

st.set_page_config(
    page_title="영상 API 관리",
    page_icon="🎬",
    layout="wide"
)

st.title("🎬 영상 AI API 관리")
st.caption("멀티 플랫폼/멀티 모델 영상 생성 시스템")

# 로테이터 및 매니저 초기화
rotator = get_rotator()
quota_manager = QuotaManager()


# 사이드바 - 통계
with st.sidebar:
    st.header("📊 사용량 통계")

    stats = quota_manager.get_usage_statistics()

    col1, col2 = st.columns(2)
    with col1:
        st.metric("오늘", f"{stats.today_videos}개")
        st.metric("이번 달", f"{stats.month_videos}개")
    with col2:
        st.metric("비용", f"${stats.today_cost_usd:.2f}")
        st.metric("비용", f"${stats.month_cost_usd:.2f}")

    st.divider()

    # 플랫폼별 상태
    st.subheader("플랫폼 상태")

    available_platforms = rotator.get_available_platforms()

    for platform, config in PLATFORM_CONFIGS.items():
        balance = quota_manager.get_platform_balance(platform)
        is_available = platform in available_platforms

        if is_available:
            icon = "🟢"
        else:
            icon = "🔴"

        with st.expander(f"{icon} {balance.display_name}", expanded=False):
            if balance.balance_usd is not None:
                st.write(f"잔액: ${balance.balance_usd:.2f}")
            if balance.credits_remaining is not None:
                st.write(f"크레딧: {balance.credits_remaining}")
            st.write(f"생성: {balance.total_videos_generated}개")
            st.write(f"누적: ${balance.total_spent_usd:.4f}")

    st.divider()

    if st.button("🔄 새로고침", use_container_width=True):
        st.rerun()


# 메인 영역 - 탭
tab1, tab2, tab3, tab4 = st.tabs([
    "🎥 영상 생성",
    "💰 비용 비교",
    "📜 사용 내역",
    "⚙️ 설정"
])


# ================================================================
# 탭 1: 영상 생성
# ================================================================
with tab1:
    st.subheader("영상 생성")

    # 두 컬럼 레이아웃
    col_left, col_right = st.columns([1, 1])

    with col_left:
        st.write("### 입력")

        # 비디오 타입 선택
        video_type = st.radio(
            "생성 유형",
            ["Image-to-Video (I2V)", "Text-to-Video (T2V)"],
            horizontal=True,
            key="video_type"
        )

        is_i2v = "I2V" in video_type

        # I2V: 이미지 업로드
        image_path = None
        image_url = None

        if is_i2v:
            upload_method = st.radio(
                "이미지 입력 방식",
                ["파일 업로드", "URL 입력"],
                horizontal=True
            )

            if upload_method == "파일 업로드":
                uploaded_file = st.file_uploader(
                    "이미지 업로드",
                    type=["jpg", "jpeg", "png", "webp"],
                    key="video_gen_upload"
                )
                if uploaded_file:
                    st.image(uploaded_file, caption="업로드된 이미지", use_container_width=True)
            else:
                image_url = st.text_input(
                    "이미지 URL",
                    placeholder="https://example.com/image.jpg",
                    key="video_gen_url"
                )
                if image_url:
                    try:
                        st.image(image_url, caption="입력 이미지", use_container_width=True)
                    except:
                        pass

        # 프롬프트
        prompt = st.text_area(
            "프롬프트",
            placeholder="영상에서 일어날 동작을 설명하세요...",
            height=100,
            key="video_gen_prompt"
        )

        # 옵션
        col_opt1, col_opt2, col_opt3 = st.columns(3)
        with col_opt1:
            duration = st.selectbox("길이", [5, 10], key="video_gen_duration")
        with col_opt2:
            resolution = st.selectbox("해상도", ["480p", "720p", "1080p"], index=1, key="video_gen_resolution")
        with col_opt3:
            aspect_ratio = st.selectbox("비율", ["16:9", "9:16", "1:1"], key="video_gen_aspect")

    with col_right:
        st.write("### 모델 선택")

        # 선택 모드
        selection_mode = st.radio(
            "선택 방식",
            ["자동 추천", "직접 선택"],
            horizontal=True
        )

        selected_platform = None
        selected_model = None

        if selection_mode == "자동 추천":
            auto_mode = st.radio(
                "추천 기준",
                ["가성비 (저렴한 모델)", "빠른 생성", "최고 품질"],
                key="auto_mode"
            )

            # 예상 비용 표시
            vtype = "i2v" if is_i2v else "t2v"

            if auto_mode == "가성비 (저렴한 모델)":
                best = CostCalculator.get_cheapest_option(vtype, platforms=available_platforms)
            elif auto_mode == "빠른 생성":
                best = CostCalculator.get_fastest_option(vtype, platforms=available_platforms)
            else:
                best = CostCalculator.get_best_quality_option(vtype, platforms=available_platforms)

            if best:
                st.info(f"""
                **추천 모델:** {best.model_display_name}
                - 플랫폼: {best.platform}
                - 예상 비용: ${best.estimated_cost_usd:.4f}
                - 생성 시간: ~{best.estimated_time_seconds}초
                """)
                selected_platform = best.platform
                selected_model = best.model_key
            else:
                st.warning("사용 가능한 모델이 없습니다.")

        else:
            # 직접 선택
            platform_options = ["fal_ai", "replicate", "pixverse"]
            platform_labels = {
                "fal_ai": "fal.ai",
                "replicate": "Replicate",
                "pixverse": "PixVerse"
            }

            # 사용 가능한 플랫폼만 필터링
            platform_options = [p for p in platform_options if p in available_platforms]

            if not platform_options:
                st.error("사용 가능한 플랫폼이 없습니다. API 키를 설정하세요.")
            else:
                selected_platform = st.selectbox(
                    "플랫폼",
                    platform_options,
                    format_func=lambda x: platform_labels.get(x, x),
                    key="select_platform"
                )

                # 해당 플랫폼의 모델 목록
                platform_models = ALL_MODELS.get(selected_platform, {})

                # 비디오 타입에 맞는 모델만 필터링
                vtype = "i2v" if is_i2v else "t2v"
                filtered_models = {}

                for key, model in platform_models.items():
                    if model.video_type == VideoType.BOTH:
                        filtered_models[key] = model
                    elif model.video_type == VideoType.IMAGE_TO_VIDEO and vtype == "i2v":
                        filtered_models[key] = model
                    elif model.video_type == VideoType.TEXT_TO_VIDEO and vtype == "t2v":
                        filtered_models[key] = model

                if filtered_models:
                    model_options = list(filtered_models.keys())
                    model_labels = {k: v.display_name for k, v in filtered_models.items()}

                    selected_model = st.selectbox(
                        "모델",
                        model_options,
                        format_func=lambda x: model_labels.get(x, x),
                        key="select_model"
                    )

                    # 선택된 모델 정보
                    model_config = filtered_models[selected_model]

                    # 비용 추정
                    cost_estimate = CostCalculator.estimate_cost(
                        platform=selected_platform,
                        model_key=selected_model,
                        duration=duration,
                        resolution=resolution,
                    )

                    st.success(f"""
                    **{model_config.display_name}**
                    - 예상 비용: ${cost_estimate.estimated_cost_usd:.4f}
                    - 예상 시간: ~{cost_estimate.estimated_time_seconds}초
                    - 품질: {"⭐" * model_config.quality.value}
                    """)
                else:
                    st.warning(f"이 플랫폼에 {vtype.upper()} 모델이 없습니다.")

        # 추가 옵션
        with st.expander("고급 옵션", expanded=False):
            negative_prompt = st.text_input("네거티브 프롬프트", key="neg_prompt")
            seed = st.number_input("시드 (0=랜덤)", min_value=0, max_value=999999, value=0, key="seed")
            enable_audio = st.checkbox("오디오 생성 (지원 모델만)", key="enable_audio")
            save_locally = st.checkbox("로컬 저장", key="save_local")

    st.divider()

    # 생성 버튼
    if st.button("🎬 영상 생성", type="primary", use_container_width=True):
        # 유효성 검사
        if is_i2v:
            if upload_method == "파일 업로드" and not uploaded_file:
                st.error("이미지를 업로드하세요.")
                st.stop()
            elif upload_method == "URL 입력" and not image_url:
                st.error("이미지 URL을 입력하세요.")
                st.stop()

        if not prompt:
            st.error("프롬프트를 입력하세요.")
            st.stop()

        if not selected_platform or not selected_model:
            st.error("모델을 선택하세요.")
            st.stop()

        # 이미지 처리
        if is_i2v:
            if upload_method == "파일 업로드" and uploaded_file:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as f:
                    f.write(uploaded_file.getvalue())
                    image_path = f.name
            else:
                image_path = None

        with st.spinner("영상 생성 중... (최대 5분 소요)"):
            try:
                result = asyncio.run(rotator.generate_video(
                    prompt=prompt,
                    image_path=image_path,
                    image_url=image_url,
                    platform=selected_platform,
                    model_key=selected_model,
                    duration=duration,
                    resolution=resolution,
                    aspect_ratio=aspect_ratio,
                    negative_prompt=negative_prompt if negative_prompt else None,
                    seed=seed if seed > 0 else None,
                    enable_audio=enable_audio,
                    save_locally=save_locally,
                    output_dir=str(ROOT_DIR / "output" / "videos") if save_locally else None,
                ))

                if result.success:
                    st.success("영상 생성 완료!")

                    # 결과 메트릭
                    result_cols = st.columns(4)
                    with result_cols[0]:
                        st.metric("모델", result.model_display_name or result.model_used)
                    with result_cols[1]:
                        st.metric("비용", f"${result.cost_usd:.4f}")
                    with result_cols[2]:
                        st.metric("소요 시간", f"{result.generation_time:.1f}초")
                    with result_cols[3]:
                        st.metric("해상도", result.resolution)

                    # 영상 표시
                    if result.video_url:
                        st.video(result.video_url)
                        st.markdown(f"[다운로드 링크]({result.video_url})")

                    if result.local_path:
                        st.info(f"로컬 저장: {result.local_path}")
                else:
                    st.error(f"생성 실패: {result.error_message}")

            except Exception as e:
                st.error(f"오류 발생: {str(e)}")


# ================================================================
# 탭 2: 비용 비교
# ================================================================
with tab2:
    st.subheader("💰 모델별 비용 비교")

    # 필터 옵션
    col_f1, col_f2, col_f3 = st.columns(3)

    with col_f1:
        filter_type = st.selectbox(
            "비디오 유형",
            ["i2v", "t2v", "both"],
            format_func=lambda x: {"i2v": "Image-to-Video", "t2v": "Text-to-Video", "both": "전체"}[x],
            key="filter_type"
        )
    with col_f2:
        filter_duration = st.selectbox("영상 길이", [5, 10], key="filter_duration")
    with col_f3:
        filter_resolution = st.selectbox("해상도", ["480p", "720p", "1080p"], index=1, key="filter_resolution")

    # 모든 모델의 비용 추정
    all_estimates = CostCalculator.estimate_all_options(
        video_type=filter_type if filter_type != "both" else "i2v",
        duration=filter_duration,
        resolution=filter_resolution,
        platforms=list(PLATFORM_CONFIGS.keys())
    )

    if all_estimates:
        # 데이터프레임 생성
        data = []
        for est in all_estimates:
            # 플랫폼 사용 가능 여부
            is_available = est.platform in available_platforms

            data.append({
                "플랫폼": est.platform,
                "모델": est.model_display_name,
                "비용 (USD)": f"${est.estimated_cost_usd:.4f}",
                "비용값": est.estimated_cost_usd,  # 정렬용
                "예상 시간": f"{est.estimated_time_seconds}초",
                "상태": "✅ 사용 가능" if is_available else "❌ API 키 필요",
            })

        df = pd.DataFrame(data)

        # 비용 순으로 정렬
        df = df.sort_values("비용값")

        # 표시용 컬럼만 선택
        display_df = df[["플랫폼", "모델", "비용 (USD)", "예상 시간", "상태"]]

        st.dataframe(display_df, use_container_width=True, hide_index=True)

        # 차트
        st.subheader("비용 비교 차트")

        chart_df = df[["모델", "비용값"]].copy()
        chart_df = chart_df.rename(columns={"비용값": "비용 (USD)"})
        chart_df = chart_df.set_index("모델")

        st.bar_chart(chart_df)

        # 추천
        st.divider()
        st.subheader("💡 추천")

        col_r1, col_r2, col_r3 = st.columns(3)

        cheapest = CostCalculator.get_cheapest_option(
            filter_type if filter_type != "both" else "i2v",
            platforms=available_platforms
        )
        fastest = CostCalculator.get_fastest_option(
            filter_type if filter_type != "both" else "i2v",
            platforms=available_platforms
        )
        best = CostCalculator.get_best_quality_option(
            filter_type if filter_type != "both" else "i2v",
            platforms=available_platforms
        )

        with col_r1:
            st.write("**💵 가장 저렴한**")
            if cheapest:
                st.info(f"{cheapest.model_display_name}\n${cheapest.estimated_cost_usd:.4f}")
            else:
                st.warning("없음")

        with col_r2:
            st.write("**⚡ 가장 빠른**")
            if fastest:
                st.info(f"{fastest.model_display_name}\n~{fastest.estimated_time_seconds}초")
            else:
                st.warning("없음")

        with col_r3:
            st.write("**⭐ 최고 품질**")
            if best:
                st.info(f"{best.model_display_name}\n${best.estimated_cost_usd:.4f}")
            else:
                st.warning("없음")

    else:
        st.info("비교할 모델이 없습니다.")


# ================================================================
# 탭 3: 사용 내역
# ================================================================
with tab3:
    st.subheader("📜 사용 내역")

    # 기간 선택
    period = st.radio(
        "기간",
        ["today", "이번 주", "이번 달", "전체"],
        horizontal=True,
        format_func=lambda x: {"today": "오늘", "이번 주": "이번 주", "이번 달": "이번 달", "전체": "전체"}[x],
        key="history_period"
    )

    history = quota_manager.get_usage_history(period)

    if history:
        # 통계
        success_count = sum(1 for h in history if h.get("success"))
        fail_count = len(history) - success_count
        total_cost = sum(h.get("cost_usd", 0) for h in history)

        col_s1, col_s2, col_s3, col_s4 = st.columns(4)
        with col_s1:
            st.metric("총 요청", len(history))
        with col_s2:
            st.metric("성공", success_count)
        with col_s3:
            st.metric("실패", fail_count)
        with col_s4:
            st.metric("총 비용", f"${total_cost:.4f}")

        st.divider()

        # 테이블
        history_data = []
        for h in reversed(history):  # 최신순
            history_data.append({
                "시간": h.get("timestamp", "")[:19],
                "플랫폼": h.get("platform", ""),
                "모델": h.get("model_display_name", h.get("model_key", "")),
                "상태": "✅" if h.get("success") else "❌",
                "비용": f"${h.get('cost_usd', 0):.4f}",
                "프롬프트": (h.get("prompt", "")[:30] + "...") if len(h.get("prompt", "")) > 30 else h.get("prompt", ""),
                "에러": h.get("error_message") or "-"
            })

        st.dataframe(pd.DataFrame(history_data), use_container_width=True, hide_index=True)

        # 내역 초기화
        if st.button("🗑️ 사용 내역 초기화", type="secondary"):
            if st.session_state.get("confirm_clear_history"):
                quota_manager.reset_usage_history()
                st.session_state.confirm_clear_history = False
                st.success("사용 내역이 초기화되었습니다.")
                st.rerun()
            else:
                st.session_state.confirm_clear_history = True
                st.warning("다시 클릭하면 초기화됩니다.")

    else:
        st.info("사용 내역이 없습니다.")


# ================================================================
# 탭 4: 설정
# ================================================================
with tab4:
    st.subheader("⚙️ 설정")

    # API 키 설정
    st.write("### 🔑 API 키 상태")
    st.info("API 키는 `.env` 파일에 저장해야 합니다.")

    env_keys = [
        ("FAL_KEY", "fal.ai", "https://fal.ai/dashboard/keys"),
        ("REPLICATE_API_TOKEN", "Replicate", "https://replicate.com/account/api-tokens"),
        ("PIXVERSE_API_KEY", "PixVerse", "https://app.pixverse.ai/settings/api"),
    ]

    for env_key, label, url in env_keys:
        current_value = get_api_key(env_key)
        col1, col2, col3 = st.columns([2, 1, 1])

        with col1:
            if current_value:
                masked = current_value[:6] + "●" * 10 + current_value[-4:] if len(current_value) > 16 else "●" * 16
                st.text_input(label, value=masked, disabled=True, key=f"key_{env_key}")
            else:
                st.text_input(label, value="❌ 설정 안됨", disabled=True, key=f"key_{env_key}")

        with col2:
            if current_value:
                st.success("✅ 설정됨")
            else:
                st.error("❌ 필요")

        with col3:
            st.link_button("🔗 발급", url, use_container_width=True)

    st.divider()

    # 잔액 설정
    st.write("### 💰 잔액 수동 설정")

    col_b1, col_b2 = st.columns(2)

    with col_b1:
        st.write("**fal.ai (USD 잔액)**")
        fal_balance = quota_manager.get_platform_balance("fal_ai")
        new_fal_balance = st.number_input(
            "fal.ai 잔액 ($)",
            min_value=0.0,
            max_value=1000.0,
            value=fal_balance.balance_usd or 0.0,
            step=1.0,
            key="fal_balance"
        )
        if st.button("fal.ai 잔액 저장", key="save_fal"):
            quota_manager.set_manual_balance("fal_ai", new_fal_balance)
            st.success(f"fal.ai 잔액이 ${new_fal_balance:.2f}로 설정되었습니다.")
            st.rerun()

    with col_b2:
        st.write("**PixVerse (크레딧)**")
        pv_balance = quota_manager.get_platform_balance("pixverse")
        new_pv_credits = st.number_input(
            "PixVerse 크레딧",
            min_value=0,
            max_value=10000,
            value=pv_balance.credits_remaining or 0,
            step=10,
            key="pv_credits"
        )
        if st.button("PixVerse 크레딧 저장", key="save_pv"):
            quota_manager.set_manual_credits("pixverse", new_pv_credits)
            st.success(f"PixVerse 크레딧이 {new_pv_credits}으로 설정되었습니다.")
            st.rerun()

    st.divider()

    # .env 파일 템플릿
    st.write("### 📝 .env 파일 템플릿")

    env_template = """# Video AI API Keys

# fal.ai - https://fal.ai/dashboard/keys
FAL_KEY=your_fal_api_key

# Replicate - https://replicate.com/account/api-tokens
REPLICATE_API_TOKEN=your_replicate_token

# PixVerse - https://app.pixverse.ai/settings/api
PIXVERSE_API_KEY=your_pixverse_key
"""

    st.code(env_template, language="bash")
    st.info("위 내용을 프로젝트 루트의 `.env` 파일에 추가하고 실제 API 키로 교체하세요.")

    st.divider()

    # 모델 목록
    st.write("### 📋 지원 모델 목록")

    with st.expander("fal.ai 모델", expanded=False):
        for key, model in FAL_MODELS.items():
            st.write(f"- **{model.display_name}** (`{key}`)")
            st.caption(f"  유형: {model.video_type.value}, 가격: ${model.price_per_second}/초")

    with st.expander("Replicate 모델", expanded=False):
        for key, model in REPLICATE_MODELS.items():
            st.write(f"- **{model.display_name}** (`{key}`)")
            st.caption(f"  유형: {model.video_type.value}, 가격: ${model.price_per_second}/초")

    with st.expander("PixVerse 모델", expanded=False):
        for key, model in PIXVERSE_MODELS.items():
            st.write(f"- **{model.display_name}** (`{key}`)")
            st.caption(f"  유형: {model.video_type.value}, 크레딧: {model.credits_per_video}/영상")
