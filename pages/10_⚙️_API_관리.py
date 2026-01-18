"""
API 관리 및 모니터링 대시보드

탭:
1. 🔑 API 키 설정 - API 키 입력, 저장, 검증
2. 📊 사용량 대시보드 - 전체 API 사용량 시각화
3. ⚙️ API 선택 - 기능별 API 선택
4. 📋 사용 기록 - 상세 사용 기록
5. 💰 비용 분석 - 비용 추정 및 분석
"""
import streamlit as st
import json
from pathlib import Path
from datetime import datetime, timedelta
import sys
import os

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from core.api.api_manager import get_api_manager, APIProvider, APIFunction
from utils.imagefx_cookie_manager import (
    get_cookie_state,
    CookieStatus,
    reset_cookie_state
)

st.set_page_config(page_title="API 관리", page_icon="⚙️", layout="wide")

st.title("⚙️ API 관리 및 모니터링")
st.caption("API 키 설정, 사용량 추적, 비용 분석")

api_manager = get_api_manager()

# 탭 구성
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🔑 API 키 설정",
    "📊 대시보드",
    "⚙️ API 선택",
    "📋 사용 기록",
    "💰 비용 분석"
])


# === 탭 1: API 키 설정 (개선됨) ===
with tab1:
    st.subheader("🔑 API 키 설정")

    st.info("""
    **사용 방법:**
    1. 아래에서 사용할 API의 키를 입력하세요
    2. '저장 및 검증' 버튼을 클릭하세요
    3. ✅ 표시되면 해당 API를 사용할 수 있습니다
    """)

    # API 제공자 목록
    providers = [
        {
            "id": "together",
            "name": "Together.ai",
            "description": "FLUX 이미지 생성 (무료 포함)",
            "signup_url": "https://api.together.xyz",
            "env_var": "TOGETHER_API_KEY",
            "placeholder": "your_together_api_key",
            "required_for": ["FLUX.1 Schnell Free", "FLUX.1 Schnell", "FLUX.1 Dev"]
        },
        {
            "id": "openai",
            "name": "OpenAI",
            "description": "DALL-E 3, GPT-4o, Whisper",
            "signup_url": "https://platform.openai.com/api-keys",
            "env_var": "OPENAI_API_KEY",
            "placeholder": "sk-proj-...",
            "required_for": ["DALL-E 3", "DALL-E 2", "GPT-4o", "Whisper"]
        },
        {
            "id": "anthropic",
            "name": "Anthropic",
            "description": "Claude AI",
            "signup_url": "https://console.anthropic.com",
            "env_var": "ANTHROPIC_API_KEY",
            "placeholder": "sk-ant-api03-...",
            "required_for": ["Claude Sonnet", "Claude Opus", "Claude Haiku"]
        },
        {
            "id": "google",
            "name": "Google AI",
            "description": "Gemini, Imagen 3",
            "signup_url": "https://aistudio.google.com/apikey",
            "env_var": "GOOGLE_API_KEY",
            "placeholder": "AIza...",
            "required_for": ["Gemini Flash", "Gemini Pro", "Imagen 3 (Vertex AI 필요)"]
        },
        {
            "id": "elevenlabs",
            "name": "ElevenLabs",
            "description": "고품질 TTS, 음성 복제",
            "signup_url": "https://elevenlabs.io",
            "env_var": "ELEVENLABS_API_KEY",
            "placeholder": "your_elevenlabs_key",
            "required_for": ["ElevenLabs TTS", "Voice Clone"]
        },
        {
            "id": "youtube",
            "name": "YouTube Data API",
            "description": "동영상 검색, 자막 추출",
            "signup_url": "https://console.cloud.google.com/apis/library/youtube.googleapis.com",
            "env_var": "YOUTUBE_API_KEY",
            "placeholder": "AIza...",
            "required_for": ["YouTube 검색", "자막 추출"]
        },
        {
            "id": "imagefx",
            "name": "Google ImageFX",
            "description": "Imagen 4 이미지 생성 (무료, 쿠키 필요)",
            "signup_url": "https://labs.google/fx/tools/image-fx",
            "env_var": "IMAGEFX_COOKIE",
            "placeholder": "__Secure-1PSID=...; __Secure-1PSIDTS=...",
            "required_for": ["Imagen 4", "Imagen 3.5", "Imagen 3.1", "Imagen 3"],
            "is_cookie": True
        },
    ]

    # API 키 상태 요약
    st.markdown("### 현재 상태")

    status_cols = st.columns(7)
    for i, provider in enumerate(providers):
        with status_cols[i]:
            # ImageFX 특별 처리: 세션 쿠키 또는 파일에서 동적 로드
            if provider.get("is_cookie"):
                from config.settings import load_imagefx_cookie
                has_key = bool(st.session_state.get("imagefx_cookie") or load_imagefx_cookie())
            else:
                has_key = api_manager.has_api_key(provider["id"])
            if has_key:
                st.success(f"✅ {provider['name'][:6]}")
            else:
                st.warning(f"⚠️ {provider['name'][:6]}")

    st.markdown("---")

    # 각 API 설정
    for provider in providers:
        with st.expander(f"**{provider['name']}** - {provider['description']}", expanded=False):
            # ImageFX 인증 (v6.0 - 쿠키 기반)
            if provider.get("is_cookie"):
                from config.settings import load_imagefx_cookie, SECRETS_DIR

                st.warning("""
                ⚠️ **v6.0 변경사항: 쿠키 기반 인증**
                - ImageFX는 비공식 API입니다
                - **Node.js + imagefx-api 패키지** 사용
                - Cookie Editor로 쿠키 추출 필요
                """)

                # 사전 요구사항 확인
                st.markdown("### ⚙️ 사전 요구사항")
                col_node, col_npm = st.columns(2)

                with col_node:
                    if st.button("🔍 Node.js 확인", key="check_nodejs", use_container_width=True):
                        from utils.imagefx_client import check_node_installation
                        ok, msg = check_node_installation()
                        if ok:
                            st.success(f"✅ {msg}")
                        else:
                            st.error(f"❌ {msg}")
                            st.info("https://nodejs.org 에서 Node.js 설치 필요")

                with col_npm:
                    if st.button("📦 패키지 설치", key="install_npm", use_container_width=True):
                        from utils.imagefx_client import install_npm_package
                        with st.spinner("imagefx-api 패키지 설치 중..."):
                            ok, msg = install_npm_package()
                            if ok:
                                st.success(msg)
                            else:
                                st.error(msg)

                st.markdown("---")

                # 쿠키 추출 안내
                st.markdown("""
                ### 🍪 쿠키 추출 방법

                1. **[Cookie Editor](https://chromewebstore.google.com/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm)** 확장 프로그램 설치
                2. [labs.google/fx/tools/image-fx](https://labs.google/fx/tools/image-fx) 접속
                3. **Google 계정으로 로그인**
                4. Cookie Editor 아이콘 클릭 → **Export** → **Header String**
                5. 아래 입력란에 붙여넣기
                """)

                # 현재 쿠키 상태 (동적 로드 + 유효성 상태)
                current_cookie = st.session_state.get("imagefx_cookie") or load_imagefx_cookie()
                cookie_state = get_cookie_state()

                st.markdown("### 🔐 쿠키 상태")

                if cookie_state.status == CookieStatus.VALID:
                    if current_cookie:
                        preview = current_cookie[:50] + "..." if len(current_cookie) > 50 else current_cookie
                        st.success(f"✅ 쿠키 유효: `{preview}`")
                    else:
                        st.success("✅ 쿠키 유효")
                    if cookie_state.last_success:
                        st.caption(f"마지막 성공: {cookie_state.last_success.strftime('%Y-%m-%d %H:%M')}")

                elif cookie_state.status == CookieStatus.EXPIRED:
                    st.error("❌ 쿠키 만료됨")
                    if cookie_state.error_time:
                        st.caption(f"만료 시각: {cookie_state.error_time.strftime('%Y-%m-%d %H:%M')}")
                    if cookie_state.last_error:
                        with st.expander("에러 상세"):
                            st.code(cookie_state.last_error[:500])

                    # 상태 초기화 버튼
                    if st.button("🔄 쿠키 상태 초기화", key="reset_cookie_state_api"):
                        reset_cookie_state()
                        st.success("상태가 초기화되었습니다. 새 쿠키를 입력해주세요.")
                        st.rerun()

                elif cookie_state.status == CookieStatus.NOT_SET:
                    st.warning("⚠️ 쿠키가 설정되지 않았습니다")
                    st.info("아래에서 쿠키를 입력해주세요.")

                else:  # UNKNOWN
                    if current_cookie:
                        preview = current_cookie[:50] + "..." if len(current_cookie) > 50 else current_cookie
                        st.info(f"ℹ️ 쿠키 저장됨 (상태 미확인): `{preview}`")
                    else:
                        st.info("ℹ️ 쿠키 상태를 확인할 수 없습니다")

                # 쿠키 입력
                new_cookie = st.text_area(
                    "🔑 Google 쿠키 (필수)",
                    value="",
                    height=120,
                    placeholder="Cookie Editor → Export → Header String으로 복사한 전체 쿠키",
                    key="imagefx_cookie_input_v6"
                )

                col_save, col_test = st.columns(2)

                with col_save:
                    if st.button("💾 쿠키 저장", key="save_imagefx_v6", use_container_width=True):
                        if new_cookie.strip():
                            cookie_value = new_cookie.strip()
                            if cookie_value.lower().startswith("cookie:"):
                                cookie_value = cookie_value[7:].strip()

                            st.session_state["imagefx_cookie"] = cookie_value
                            try:
                                cookie_file = SECRETS_DIR / "imagefx_cookie.txt"
                                cookie_file.write_text(cookie_value, encoding="utf-8")
                                # 새 쿠키 저장 시 상태 초기화
                                reset_cookie_state()
                                st.success("✅ 쿠키가 저장되었습니다!")
                                st.rerun()
                            except Exception as e:
                                st.warning(f"파일 저장 실패: {e}")
                        else:
                            st.warning("쿠키를 입력해주세요")

                with col_test:
                    if st.button("🧪 테스트", key="test_imagefx_v6", use_container_width=True):
                        test_cookie = new_cookie.strip() or current_cookie
                        if test_cookie:
                            from utils.imagefx_client import ImageFXClient, AspectRatio

                            # 1단계: 검증
                            with st.spinner("1/2 쿠키 검증 중..."):
                                is_valid, message, _ = ImageFXClient.validate_credentials(cookie=test_cookie)
                                if not is_valid:
                                    st.error(f"❌ {message}")
                                else:
                                    st.success(f"✓ {message}")

                                    # 2단계: API 테스트
                                    with st.spinner("2/2 API 테스트 중... (최대 2분)"):
                                        try:
                                            client = ImageFXClient(cookie=test_cookie)
                                            images = client.generate_image(
                                                prompt="A cute cat sitting on a red cushion",
                                                aspect_ratio=AspectRatio.SQUARE,
                                                num_images=1,
                                                timeout=120
                                            )

                                            if images:
                                                st.success("✅ API 테스트 성공!")
                                                with st.expander("테스트 이미지 보기"):
                                                    st.image(images[0].get_bytes(), caption="테스트 이미지", width=200)
                                            else:
                                                st.warning("이미지 생성 실패")
                                        except Exception as e:
                                            st.error(f"❌ API 테스트 실패: {str(e)}")
                        else:
                            st.warning("쿠키를 먼저 입력해주세요")

                st.caption(f"사용 가능 기능: {', '.join(provider['required_for'])}")
                st.markdown(f"[🔗 ImageFX 사이트 방문]({provider['signup_url']})")
            else:
                # 일반 API 키 처리
                col1, col2 = st.columns([3, 1])

                with col1:
                    # 현재 키 상태
                    current_key = api_manager.get_api_key(provider["id"])
                    has_key = bool(current_key)

                    if has_key:
                        # 마스킹된 키 표시
                        if len(current_key) > 12:
                            masked = f"{current_key[:6]}...{current_key[-4:]}"
                        else:
                            masked = "***"
                        st.info(f"현재 키: {masked}")
                    else:
                        st.warning("API 키가 설정되지 않았습니다.")

                    # 키 입력
                    new_key = st.text_input(
                        f"새 API 키 입력",
                        value="",
                        type="password",
                        placeholder=provider["placeholder"],
                        key=f"key_input_{provider['id']}",
                    )

                    # 필요한 기능 표시
                    st.caption(f"사용 가능 기능: {', '.join(provider['required_for'])}")

                    # 가입 링크
                    st.markdown(f"[🔗 API 키 발급받기]({provider['signup_url']})")

                with col2:
                    # 현재 상태 표시
                    if has_key:
                        st.success("✅ 설정됨")
                    else:
                        st.warning("⚠️ 미설정")

                # 버튼들
                st.markdown("---")
                col_save, col_verify, col_clear = st.columns(3)

                with col_save:
                    if st.button("💾 저장", key=f"save_{provider['id']}", use_container_width=True):
                        if new_key:
                            if api_manager.set_api_key(provider["id"], new_key):
                                st.success("✅ 저장되었습니다!")
                                st.rerun()
                            else:
                                st.error("저장 실패")
                        else:
                            st.warning("키를 입력하세요")

                with col_verify:
                    if st.button("🔍 검증", key=f"verify_{provider['id']}", use_container_width=True):
                        with st.spinner("검증 중..."):
                            result = api_manager.validate_api_key(provider["id"])
                            if result.valid:
                                st.success(f"✅ {result.message}")
                                if result.details:
                                    st.info(result.details)
                            else:
                                st.error(f"❌ {result.message}")
                                if result.details:
                                    st.code(result.details)

                with col_clear:
                    if st.button("🗑️ 삭제", key=f"clear_{provider['id']}", use_container_width=True):
                        if api_manager.set_api_key(provider["id"], ""):
                            st.success("삭제됨")
                            st.rerun()

    # .env 파일 직접 편집
    st.markdown("---")
    st.subheader("📄 .env 파일 직접 편집")

    env_file = api_manager.ENV_FILE
    st.caption(f"파일 위치: {env_file}")

    if env_file.exists():
        with open(env_file, "r", encoding="utf-8") as f:
            env_content = f.read()

        new_content = st.text_area(
            ".env 파일 내용",
            value=env_content,
            height=300,
            key="env_editor"
        )

        col1, col2 = st.columns(2)
        with col1:
            if st.button("💾 .env 파일 저장", type="primary"):
                with open(env_file, "w", encoding="utf-8") as f:
                    f.write(new_content)
                st.success("저장됨! 앱을 재시작하면 적용됩니다.")
                st.info("재시작: 터미널에서 Ctrl+C 후 `streamlit run app.py`")
        with col2:
            if st.button("🔄 다시 로드"):
                st.rerun()
    else:
        st.warning(".env 파일이 없습니다. API 키를 저장하면 자동으로 생성됩니다.")


# === 탭 2: 대시보드 ===
with tab2:
    st.subheader("📊 API 사용량 대시보드")

    # 기간 선택
    col1, col2 = st.columns(2)
    with col1:
        period = st.selectbox(
            "기간",
            ["오늘", "최근 7일", "최근 30일", "전체"],
            index=1
        )

    # 기간에 따른 날짜 계산
    now = datetime.now()
    if period == "오늘":
        start_date = now.replace(hour=0, minute=0, second=0)
    elif period == "최근 7일":
        start_date = now - timedelta(days=7)
    elif period == "최근 30일":
        start_date = now - timedelta(days=30)
    else:
        start_date = None

    # 사용량 요약
    summary = api_manager.get_usage_summary(start_date=start_date)

    # 주요 지표
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "총 요청 수",
            f"{summary['total_requests']:,}",
            delta=f"성공: {summary['successful_requests']}"
        )

    with col2:
        st.metric(
            "총 비용 (추정)",
            f"${summary['total_cost']:.4f}"
        )

    with col3:
        total_tokens = summary['total_tokens_input'] + summary['total_tokens_output']
        st.metric(
            "총 토큰 사용",
            f"{total_tokens:,}"
        )

    with col4:
        avg_duration = summary['total_duration'] / max(summary['total_requests'], 1)
        st.metric(
            "평균 응답 시간",
            f"{avg_duration:.2f}초"
        )

    st.divider()

    # 제공자별 사용량
    st.markdown("### 📈 제공자별 사용량")

    if summary['by_provider']:
        provider_data = []
        for provider, data in summary['by_provider'].items():
            provider_data.append({
                "제공자": provider.upper(),
                "요청 수": data['requests'],
                "비용 ($)": f"{data['cost']:.4f}",
                "토큰": f"{data['tokens']:,}"
            })

        cols = st.columns(len(provider_data)) if provider_data else []
        for i, pdata in enumerate(provider_data):
            with cols[i % len(cols)]:
                with st.container(border=True):
                    st.markdown(f"**{pdata['제공자']}**")
                    st.write(f"요청: {pdata['요청 수']}")
                    st.write(f"비용: {pdata['비용 ($)']}")
                    st.write(f"토큰: {pdata['토큰']}")

        if len(provider_data) > 0:
            chart_data = {p['제공자']: p['요청 수'] for p in provider_data}
            st.bar_chart(chart_data)
    else:
        st.info("사용 기록이 없습니다.")

    # 기능별 사용량
    st.markdown("### 📊 기능별 사용량")

    if summary['by_function']:
        func_labels = {
            "text_generation": "텍스트 생성",
            "image_generation": "이미지 생성",
            "image_analysis": "이미지 분석",
            "tts": "TTS",
            "video_search": "비디오 검색"
        }

        func_cols = st.columns(min(4, len(summary['by_function'])))
        for i, (func, data) in enumerate(summary['by_function'].items()):
            with func_cols[i % len(func_cols)]:
                with st.container(border=True):
                    st.markdown(f"**{func_labels.get(func, func)}**")
                    st.write(f"요청: {data['requests']}")
                    st.write(f"비용: ${data['cost']:.4f}")

    # 일별 추이
    st.markdown("### 📅 일별 사용 추이")

    if summary['by_date']:
        dates = sorted(summary['by_date'].keys())[-14:]
        date_data = {d: summary['by_date'][d]['requests'] for d in dates}
        st.line_chart(date_data)


# === 탭 3: API 선택 ===
with tab3:
    st.subheader("⚙️ 기능별 API 선택")

    st.info("각 기능에 사용할 API를 선택하세요. 선택한 API는 해당 기능에서 기본으로 사용됩니다.")

    task_labels = {
        "script_generation": "📝 스크립트 생성",
        "scene_analysis": "🎬 씬 분석",
        "character_extraction": "👤 캐릭터 추출",
        "image_prompt_generation": "💬 이미지 프롬프트 생성",
        "image_generation": "🎨 이미지 생성",
        "image_analysis": "👁️ 이미지 분석 (Vision)",
        "tts": "🎤 TTS (음성 합성)",
        "video_search": "📹 비디오 검색",
    }

    task_functions = {
        "script_generation": "text_generation",
        "scene_analysis": "text_generation",
        "character_extraction": "text_generation",
        "image_prompt_generation": "text_generation",
        "image_generation": "image_generation",
        "image_analysis": "image_analysis",
        "tts": "tts",
        "video_search": "video_search",
    }

    for task, label in task_labels.items():
        col1, col2, col3 = st.columns([2, 3, 2])

        with col1:
            st.write(label)

        with col2:
            function = task_functions[task]

            api_options = {}
            for api_id, api in api_manager.AVAILABLE_APIS.items():
                if api.function == function:
                    # API 키 상태 확인
                    has_key = api_manager.has_api_key(api.provider)
                    key_status = "✅" if has_key else "⚠️"

                    price_str = '무료' if api.is_free else f'${api.price_per_unit}/{api.unit_name}'
                    api_options[f"{key_status} {api.name} ({price_str})"] = api_id

            current_api_id = api_manager.settings.get("selected_apis", {}).get(task, "")
            current_api = api_manager.get_api_by_id(current_api_id)

            default_idx = 0
            for i, (name, api_id) in enumerate(api_options.items()):
                if api_id == current_api_id:
                    default_idx = i
                    break

            selected_name = st.selectbox(
                f"{task} API",
                list(api_options.keys()),
                index=default_idx,
                key=f"select_{task}",
                label_visibility="collapsed"
            )

            if selected_name:
                selected_id = api_options[selected_name]
                if selected_id != current_api_id:
                    api_manager.set_selected_api(task, selected_id)

        with col3:
            if current_api:
                desc = current_api.description[:30] + "..." if len(current_api.description) > 30 else current_api.description
                st.caption(desc)


# === 탭 4: 사용 기록 ===
with tab4:
    st.subheader("📋 API 사용 기록")

    # 필터
    col1, col2 = st.columns(2)
    with col1:
        filter_provider = st.selectbox(
            "제공자 필터",
            ["전체"] + [p.value for p in APIProvider],
            key="filter_provider"
        )
    with col2:
        filter_limit = st.selectbox(
            "표시 개수",
            [50, 100, 200, 500],
            index=0
        )

    # 사용 기록
    records = api_manager.get_recent_usage(limit=filter_limit)

    if filter_provider != "전체":
        records = [r for r in records if r.provider == filter_provider]

    if records:
        st.success(f"총 {len(records)}개 기록")

        for r in records[:50]:
            status_icon = "✅" if r.success else "❌"
            tokens = r.tokens_input + r.tokens_output

            with st.expander(f"{status_icon} [{r.timestamp[11:19]}] {r.provider.upper()} - {r.function}"):
                col1, col2 = st.columns(2)
                with col1:
                    st.write(f"**모델:** {r.model_id}")
                    st.write(f"**프로젝트:** {r.project_name or 'N/A'}")
                    st.write(f"**단계:** {r.step_name or 'N/A'}")
                with col2:
                    st.write(f"**토큰:** {tokens:,}")
                    st.write(f"**비용:** ${r.cost_estimate:.4f}")
                    st.write(f"**시간:** {r.duration_seconds:.2f}초")

                if not r.success:
                    st.error(f"**에러:** {r.error_message}")

        # 다운로드 - v1.1: 생성/다운로드 분리 (rerun 버그 수정)
        csv_cache_key = "_api_usage_csv_cache"
        csv_meta_key = "_api_usage_csv_meta"

        # 현재 레코드 해시 계산 (데이터 변경 감지용)
        current_record_hash = hash(tuple((r.timestamp, r.provider, r.model_id) for r in records))
        cached_meta = st.session_state.get(csv_meta_key, {})
        cached_csv = st.session_state.get(csv_cache_key)
        data_changed = cached_meta.get("record_hash") != current_record_hash

        dl_col1, dl_col2 = st.columns([1, 1])

        with dl_col1:
            gen_label = "📝 CSV 생성" if not cached_csv or data_changed else "🔄 CSV 재생성"
            if st.button(gen_label, key="api_csv_generate"):
                csv_lines = ["시간,제공자,모델,기능,토큰,비용,상태,프로젝트"]
                for r in records:
                    status = "성공" if r.success else "실패"
                    tokens = r.tokens_input + r.tokens_output
                    csv_lines.append(f"{r.timestamp},{r.provider},{r.model_id},{r.function},{tokens},{r.cost_estimate:.4f},{status},{r.project_name}")

                csv_data = "\n".join(csv_lines)
                st.session_state[csv_cache_key] = csv_data.encode("utf-8-sig")
                st.session_state[csv_meta_key] = {
                    "record_hash": current_record_hash,
                    "generated_at": datetime.now().strftime('%Y%m%d_%H%M%S')
                }
                st.rerun()

        with dl_col2:
            if cached_csv and not data_changed:
                st.download_button(
                    "📥 다운로드",
                    data=cached_csv,
                    file_name=f"api_usage_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    key="api_csv_download"
                )
            else:
                st.button("📥 다운로드", disabled=True, key="api_csv_download_disabled", help="먼저 CSV를 생성하세요")
    else:
        st.info("사용 기록이 없습니다.")


# === 탭 5: 비용 분석 ===
with tab5:
    st.subheader("💰 비용 분석")

    # 기간별 비용
    st.markdown("### 📅 기간별 비용")

    periods_config = {
        "오늘": timedelta(days=1),
        "이번 주": timedelta(days=7),
        "이번 달": timedelta(days=30),
        "전체": None
    }

    cost_cols = st.columns(4)
    for i, (period_name, delta) in enumerate(periods_config.items()):
        start = datetime.now() - delta if delta else None
        period_summary = api_manager.get_usage_summary(start_date=start)

        with cost_cols[i]:
            with st.container(border=True):
                st.markdown(f"**{period_name}**")
                st.write(f"요청: {period_summary['total_requests']}")
                st.write(f"비용: ${period_summary['total_cost']:.4f}")

    st.divider()

    # 제공자별 비용
    st.markdown("### 📊 제공자별 비용 비중")

    full_summary = api_manager.get_usage_summary()

    if full_summary['by_provider']:
        costs = {p.upper(): d['cost'] for p, d in full_summary['by_provider'].items()}
        if any(costs.values()):
            st.bar_chart(costs)
        else:
            st.info("비용 데이터가 없습니다.")
    else:
        st.info("사용 기록이 없습니다.")

    # 비용 추정
    st.markdown("### 🧮 월간 비용 추정")

    week_summary = api_manager.get_usage_summary(
        start_date=datetime.now() - timedelta(days=7)
    )

    daily_cost = week_summary['total_cost'] / 7
    monthly_estimate = daily_cost * 30

    col1, col2 = st.columns(2)
    with col1:
        st.metric("일 평균 비용", f"${daily_cost:.4f}")
    with col2:
        st.metric("월 예상 비용", f"${monthly_estimate:.2f}")

    # 기록 삭제
    st.divider()
    st.markdown("### 🗑️ 데이터 관리")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("30일 이전 기록 삭제", type="secondary"):
            api_manager.clear_usage_history(before_date=datetime.now() - timedelta(days=30))
            st.success("삭제 완료!")
            st.rerun()
    with col2:
        confirm_delete = st.checkbox("전체 삭제 확인")
        if st.button("전체 기록 삭제", type="secondary", disabled=not confirm_delete):
            api_manager.clear_usage_history()
            st.success("삭제 완료!")
            st.rerun()
