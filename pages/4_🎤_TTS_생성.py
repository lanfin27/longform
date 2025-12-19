# -*- coding: utf-8 -*-
"""
TTS 생성 페이지

Edge TTS와 Chatterbox 중 선택하여 TTS 생성
"""
import streamlit as st
import os
import sys
import time
import requests
from pathlib import Path

# 경로 설정
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 페이지 설정
st.set_page_config(
    page_title="TTS 생성",
    page_icon="🎤",
    layout="wide"
)

# CSS 스타일
st.markdown("""
<style>
.stButton > button { width: 100%; }
.success-box { padding: 1rem; background: #d4edda; border-radius: 0.5rem; }
.error-box { padding: 1rem; background: #f8d7da; border-radius: 0.5rem; }

.voice-card {
    background: white;
    padding: 12px;
    border-radius: 8px;
    border: 2px solid #e0e0e0;
    margin-bottom: 8px;
}

.voice-card:hover {
    border-color: #667eea;
}
</style>
""", unsafe_allow_html=True)

# Chatterbox 서버 설정
CHATTERBOX_URL = "http://localhost:8100"


# ============================================================
# Edge TTS 음성 목록
# ============================================================

# 실제 Edge TTS에서 지원하는 음성만 포함 (2024년 검증됨)
# 한국어는 3개만 지원됨!
EDGE_VOICES = {
    "ko": [
        {"id": "ko-KR-SunHiNeural", "name": "선희", "gender": "여성", "desc": "밝고 친근함 (추천)"},
        {"id": "ko-KR-InJoonNeural", "name": "인준", "gender": "남성", "desc": "차분하고 신뢰감"},
        {"id": "ko-KR-HyunsuNeural", "name": "현수", "gender": "남성", "desc": "젊고 활기참"},
    ],
    "en": [
        {"id": "en-US-JennyNeural", "name": "Jenny", "gender": "여성", "desc": "친근하고 자연스러움 (추천)"},
        {"id": "en-US-GuyNeural", "name": "Guy", "gender": "남성", "desc": "전문적이고 신뢰감"},
        {"id": "en-US-AriaNeural", "name": "Aria", "gender": "여성", "desc": "명확하고 표현력"},
        {"id": "en-US-DavisNeural", "name": "Davis", "gender": "남성", "desc": "깊고 풍부함"},
        {"id": "en-GB-SoniaNeural", "name": "Sonia (UK)", "gender": "여성", "desc": "영국 억양"},
        {"id": "en-GB-RyanNeural", "name": "Ryan (UK)", "gender": "남성", "desc": "영국 억양"},
    ],
    "ja": [
        {"id": "ja-JP-NanamiNeural", "name": "ナナミ", "gender": "여성", "desc": "밝고 자연스러움 (추천)"},
        {"id": "ja-JP-KeitaNeural", "name": "ケイタ", "gender": "남성", "desc": "차분하고 신뢰감"},
    ],
    "zh": [
        {"id": "zh-CN-XiaoxiaoNeural", "name": "晓晓", "gender": "여성", "desc": "밝고 친근함 (추천)"},
        {"id": "zh-CN-YunxiNeural", "name": "云希", "gender": "남성", "desc": "젊고 활기참"},
        {"id": "zh-CN-YunjianNeural", "name": "云健", "gender": "남성", "desc": "강하고 힘있음"},
        {"id": "zh-TW-HsiaoChenNeural", "name": "曉臻 (TW)", "gender": "여성", "desc": "대만 억양"},
    ]
}

# 기본 음성 (폴백용)
DEFAULT_VOICE = {
    "ko": "ko-KR-SunHiNeural",
    "en": "en-US-JennyNeural",
    "ja": "ja-JP-NanamiNeural",
    "zh": "zh-CN-XiaoxiaoNeural",
}


# ============================================================
# 유틸리티 함수
# ============================================================

def check_chatterbox_server():
    """Chatterbox 서버 연결 확인"""
    try:
        r = requests.get(f"{CHATTERBOX_URL}/health", timeout=2)
        return r.status_code == 200
    except:
        return False


def get_chatterbox_status():
    """Chatterbox 서버 상태 조회"""
    try:
        r = requests.get(f"{CHATTERBOX_URL}/status", timeout=3)
        if r.status_code == 200:
            return r.json()
    except:
        pass
    return None


def get_voice_files():
    """음성 라이브러리 파일 목록"""
    voice_dir = Path("voice_library/ko")
    if voice_dir.exists():
        files = list(voice_dir.glob("*.mp3")) + list(voice_dir.glob("*.wav"))
        return [f.name for f in files]
    return []


# ============================================================
# 설정 탭
# ============================================================

def render_settings_tab():
    """공통 설정 탭"""
    st.markdown("### ⚙️ TTS 공통 설정")

    # 언어 선택
    st.markdown("#### 🌐 언어 선택")

    lang_cols = st.columns(4)
    languages = [
        ("ko", "🇰🇷 한국어"),
        ("en", "🇺🇸 영어"),
        ("ja", "🇯🇵 일본어"),
        ("zh", "🇨🇳 중국어"),
    ]

    selected_lang = st.session_state.get("tts_lang", "ko")

    for i, (code, name) in enumerate(languages):
        with lang_cols[i]:
            if st.button(
                name,
                key=f"setting_lang_{code}",
                type="primary" if selected_lang == code else "secondary",
                use_container_width=True
            ):
                st.session_state["tts_lang"] = code
                st.session_state["edge_tts_lang"] = code
                st.rerun()

    st.info(f"선택된 언어: **{dict(languages).get(selected_lang, selected_lang)}**")

    st.markdown("---")

    # 시니어 친화 설정
    st.markdown("#### 👴 시니어 친화 설정")

    col1, col2 = st.columns(2)

    with col1:
        add_breaks = st.checkbox(
            "문단 사이 무음 추가",
            value=st.session_state.get("setting_breaks", True),
            key="setting_breaks_cb"
        )
        st.session_state["setting_breaks"] = add_breaks

        if add_breaks:
            break_length = st.slider(
                "무음 길이 (초)",
                min_value=0.5,
                max_value=3.0,
                value=st.session_state.get("setting_break_length", 1.5),
                step=0.5,
                key="setting_break_length_slider"
            )
            st.session_state["setting_break_length"] = break_length
            st.caption(f"문단 사이에 {break_length}초 무음이 삽입됩니다.")

    with col2:
        slow_mode = st.checkbox(
            "느린 속도 모드 (시니어용)",
            value=st.session_state.get("setting_slow", False),
            key="setting_slow_cb"
        )
        st.session_state["setting_slow"] = slow_mode

        if slow_mode:
            st.session_state["edge_tts_rate"] = -20
            st.caption("기본 속도가 -20%로 설정됩니다.")

    st.markdown("---")

    # 출력 설정
    st.markdown("#### 📁 출력 설정")

    output_dir = st.text_input(
        "출력 디렉토리",
        value=st.session_state.get("tts_output_dir", "data/tts"),
        key="tts_output_dir_input"
    )
    st.session_state["tts_output_dir"] = output_dir

    generate_srt = st.checkbox(
        "자막 파일 자동 생성 (SRT)",
        value=st.session_state.get("auto_srt", True),
        key="auto_srt_cb"
    )
    st.session_state["auto_srt"] = generate_srt


# ============================================================
# Edge TTS 탭
# ============================================================

def render_edge_tts_tab():
    """Edge TTS 탭 렌더링"""
    st.markdown("### ✨ Edge TTS")
    st.info("Microsoft의 무료 TTS 서비스입니다. 다양한 음성과 언어를 지원합니다.")

    # 음성 현황 표시
    with st.expander("📋 지원 음성 현황", expanded=False):
        st.markdown("""
        | 언어 | 지원 음성 |
        |------|----------|
        | 🇰🇷 한국어 | 선희(여), 인준(남), 현수(남) - **3개** |
        | 🇺🇸 영어 | Jenny, Guy, Aria, Davis, Sonia(UK), Ryan(UK) - **6개** |
        | 🇯🇵 일본어 | ナナミ(여), ケイタ(남) - **2개** |
        | 🇨🇳 중국어 | 晓晓, 云希, 云健, 曉臻(TW) - **4개** |
        """)

    # === 언어 선택 ===
    st.markdown("#### 🌐 언어 선택")

    lang_cols = st.columns(4)
    languages = [("ko", "🇰🇷 한국어"), ("en", "🇺🇸 영어"), ("ja", "🇯🇵 일본어"), ("zh", "🇨🇳 중국어")]

    selected_lang = st.session_state.get("edge_tts_lang", "ko")

    for i, (code, name) in enumerate(languages):
        with lang_cols[i]:
            if st.button(
                name,
                key=f"edge_lang_{code}",
                type="primary" if selected_lang == code else "secondary",
                use_container_width=True
            ):
                st.session_state["edge_tts_lang"] = code
                st.rerun()

    selected_lang = st.session_state.get("edge_tts_lang", "ko")

    st.markdown("---")

    # === 음성 선택 ===
    st.markdown("#### 🎙️ 음성 선택")

    voices = EDGE_VOICES.get(selected_lang, EDGE_VOICES["ko"])
    all_voice_ids = [v["id"] for v in voices]

    # 저장된 음성이 현재 언어에서 유효한지 확인
    stored_voice = st.session_state.get("selected_edge_voice", "")
    if stored_voice and stored_voice not in all_voice_ids:
        # 유효하지 않으면 기본 음성으로 재설정
        st.session_state["selected_edge_voice"] = DEFAULT_VOICE.get(selected_lang, voices[0]["id"])

    # 성별 필터
    gender_filter = st.radio(
        "성별 필터",
        options=["전체", "여성", "남성"],
        horizontal=True,
        key="edge_gender_filter"
    )

    filtered_voices = voices
    if gender_filter != "전체":
        filtered_voices = [v for v in voices if v["gender"] == gender_filter]

    # 필터링 후 음성이 없으면 전체 음성 표시
    if not filtered_voices:
        filtered_voices = voices

    # 음성 그리드
    selected_voice = st.session_state.get("selected_edge_voice", DEFAULT_VOICE.get(selected_lang, voices[0]["id"]))

    cols = st.columns(3)
    for i, voice in enumerate(filtered_voices):
        with cols[i % 3]:
            is_selected = voice["id"] == selected_voice
            icon = "👩" if voice["gender"] == "여성" else "👨"

            if st.button(
                f"{icon} {voice['name']}\n{voice['desc']}",
                key=f"voice_{voice['id']}",
                type="primary" if is_selected else "secondary",
                use_container_width=True
            ):
                st.session_state["selected_edge_voice"] = voice["id"]
                st.rerun()

    # 선택된 음성 표시
    selected_voice_info = next((v for v in EDGE_VOICES.get(selected_lang, []) if v["id"] == selected_voice), None)
    if selected_voice_info:
        st.success(f"선택된 음성: **{selected_voice_info['name']}** ({selected_voice_info['gender']}) - {selected_voice_info['desc']}")

    st.markdown("---")

    # === TTS 설정 ===
    st.markdown("#### ⚙️ 음성 설정")

    col1, col2, col3 = st.columns(3)

    with col1:
        tts_rate = st.slider(
            "🚀 속도",
            min_value=-50,
            max_value=100,
            value=st.session_state.get("edge_tts_rate", 0),
            step=5,
            format="%d%%",
            help="-50% (느림) ~ +100% (빠름)",
            key="edge_tts_rate_slider"
        )
        st.session_state["edge_tts_rate"] = tts_rate

    with col2:
        tts_pitch = st.slider(
            "🎵 피치",
            min_value=-50,
            max_value=50,
            value=st.session_state.get("edge_tts_pitch", 0),
            step=5,
            format="%dHz",
            help="-50Hz (낮음) ~ +50Hz (높음)",
            key="edge_tts_pitch_slider"
        )
        st.session_state["edge_tts_pitch"] = tts_pitch

    with col3:
        tts_volume = st.slider(
            "🔊 볼륨",
            min_value=-50,
            max_value=50,
            value=st.session_state.get("edge_tts_volume", 0),
            step=5,
            format="%d%%",
            help="-50% (작음) ~ +50% (큼)",
            key="edge_tts_volume_slider"
        )
        st.session_state["edge_tts_volume"] = tts_volume

    # 추가 옵션
    col1, col2 = st.columns(2)

    with col1:
        add_breaks = st.checkbox(
            "문단/문장 사이에 자동 휴식 삽입",
            value=True,
            key="edge_add_breaks"
        )

    with col2:
        generate_subs = st.checkbox(
            "자막 파일 생성 (SRT)",
            value=True,
            key="edge_gen_subs"
        )

    st.markdown("---")

    # === 스크립트 입력 ===
    st.markdown("#### 📝 스크립트")

    script_source = st.radio(
        "스크립트 소스",
        options=["직접 입력", "프로젝트 스크립트 사용"],
        horizontal=True,
        key="edge_script_source"
    )

    if script_source == "직접 입력":
        script_text = st.text_area(
            "텍스트 입력",
            height=200,
            placeholder="TTS로 변환할 텍스트를 입력하세요...",
            key="edge_script_input"
        )
    else:
        if "generated_script" in st.session_state and st.session_state["generated_script"]:
            script_text = st.session_state["generated_script"]
            st.text_area("프로젝트 스크립트", value=script_text, height=200, disabled=True)
        else:
            script_text = ""
            st.warning("생성된 스크립트가 없습니다. 먼저 스크립트 생성을 해주세요.")

    # 문자 수
    if script_text:
        st.caption(f"📊 {len(script_text)}자 | 예상 시간: 약 {max(1, len(script_text) // 150)}분")

    st.markdown("---")

    # === 생성 버튼 ===
    if st.button(
        "🎵 Edge TTS 생성",
        type="primary",
        use_container_width=True,
        disabled=not script_text,
        key="generate_edge_tts"
    ):
        generate_edge_tts(
            text=script_text,
            voice_id=selected_voice,
            rate=tts_rate,
            pitch=tts_pitch,
            volume=tts_volume,
            add_breaks=add_breaks,
            generate_subs=generate_subs
        )


def generate_edge_tts(text, voice_id, rate, pitch, volume, add_breaks, generate_subs):
    """Edge TTS 생성"""
    import asyncio

    progress = st.progress(0)
    status = st.empty()

    # 음성 ID 유효성 검사
    all_valid_voices = []
    for lang_voices in EDGE_VOICES.values():
        all_valid_voices.extend([v["id"] for v in lang_voices])

    if voice_id not in all_valid_voices:
        status.error(f"⚠️ 유효하지 않은 음성 ID: {voice_id}")
        st.warning("지원되는 음성 목록에서 선택해주세요.")
        return

    status.text("Edge TTS 생성 중...")
    progress.progress(30)

    try:
        import edge_tts

        # 설정 문자열
        rate_str = f"{'+' if rate >= 0 else ''}{rate}%"
        pitch_str = f"{'+' if pitch >= 0 else ''}{pitch}Hz"
        volume_str = f"{'+' if volume >= 0 else ''}{volume}%"

        # 출력 경로
        output_dir = st.session_state.get("tts_output_dir", "data/tts")
        os.makedirs(output_dir, exist_ok=True)

        timestamp = int(time.time() * 1000)
        audio_path = os.path.join(output_dir, f"edge_tts_{timestamp}.mp3")
        srt_path = os.path.join(output_dir, f"edge_tts_{timestamp}.srt")

        async def generate():
            communicate = edge_tts.Communicate(
                text=text,
                voice=voice_id,
                rate=rate_str,
                volume=volume_str,
                pitch=pitch_str
            )

            if generate_subs:
                submaker = edge_tts.SubMaker()

                with open(audio_path, "wb") as f:
                    async for chunk in communicate.stream():
                        if chunk["type"] == "audio":
                            f.write(chunk["data"])
                        elif chunk["type"] == "WordBoundary":
                            submaker.create_sub(
                                (chunk["offset"], chunk["duration"]),
                                chunk["text"]
                            )

                # 자막 저장
                srt_content = ""
                if hasattr(submaker, 'generate_subs'):
                    try:
                        srt_content = submaker.generate_subs()
                    except:
                        pass
                if not srt_content and hasattr(submaker, 'get_srt'):
                    try:
                        srt_content = submaker.get_srt()
                    except:
                        pass
                if not srt_content:
                    try:
                        srt_content = str(submaker)
                    except:
                        pass

                if srt_content and srt_content.strip():
                    with open(srt_path, "w", encoding="utf-8") as f:
                        f.write(srt_content)
                    return audio_path, srt_path

                return audio_path, None
            else:
                await communicate.save(audio_path)
                return audio_path, None

        # 비동기 실행
        audio_path, subtitle_path = asyncio.run(generate())

        progress.progress(100)
        status.success("생성 완료!")

        # 결과 표시
        st.audio(audio_path)

        col1, col2 = st.columns(2)

        with col1:
            with open(audio_path, "rb") as f:
                st.download_button(
                    "💾 오디오 다운로드 (MP3)",
                    data=f,
                    file_name=f"edge_tts_{timestamp}.mp3",
                    mime="audio/mpeg",
                    use_container_width=True
                )

        with col2:
            if subtitle_path and os.path.exists(subtitle_path):
                with open(subtitle_path, "rb") as f:
                    st.download_button(
                        "📄 자막 다운로드 (SRT)",
                        data=f,
                        file_name=f"edge_tts_{timestamp}.srt",
                        mime="text/plain",
                        use_container_width=True
                    )

        # 세션에 저장
        st.session_state["last_tts_audio"] = audio_path
        st.session_state["last_tts_subtitle"] = subtitle_path

    except ImportError:
        status.error("edge-tts 라이브러리가 설치되지 않았습니다.")
        st.code("pip install edge-tts")
    except Exception as e:
        error_msg = str(e)
        if "No audio was received" in error_msg:
            status.error("⚠️ 오디오를 받지 못했습니다.")
            st.warning(f"""
            **가능한 원인:**
            - 선택한 음성 ID({voice_id})가 Microsoft Edge TTS에서 지원되지 않습니다
            - 네트워크 연결 문제가 있습니다

            **해결 방법:**
            - 다른 음성을 선택해보세요
            - 한국어는 선희, 인준, 현수 3개 음성만 지원됩니다
            """)
        else:
            status.error(f"오류: {e}")
        import traceback
        with st.expander("상세 오류"):
            st.code(traceback.format_exc())


# ============================================================
# Chatterbox 탭 - 음성 클론 관리
# ============================================================

def get_voice_samples_dir():
    """프로젝트별 음성 샘플 디렉토리 반환"""
    current_project = st.session_state.get("current_project")
    if current_project:
        samples_dir = Path(f"data/projects/{current_project}/voice_samples")
    else:
        samples_dir = Path("data/voice_samples/default")
    samples_dir.mkdir(parents=True, exist_ok=True)
    return samples_dir


def get_voice_samples(samples_dir: Path) -> list:
    """음성 샘플 목록 조회"""
    import json

    samples = []
    meta_path = samples_dir / "samples_meta.json"

    if meta_path.exists():
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)

        for s in meta.get("samples", []):
            filepath = samples_dir / s["filename"]
            if filepath.exists():
                samples.append({
                    "name": s["name"],
                    "path": str(filepath),
                    "description": s.get("description", ""),
                    "created_at": s.get("created_at", "")
                })
    else:
        # 메타 없으면 파일 직접 스캔
        for f in samples_dir.glob("*"):
            if f.suffix.lower() in ['.wav', '.mp3', '.m4a', '.ogg']:
                samples.append({
                    "name": f.stem,
                    "path": str(f),
                    "description": "",
                    "created_at": ""
                })

    # voice_library/ko 폴더도 포함
    voice_lib = Path("voice_library/ko")
    if voice_lib.exists():
        for f in voice_lib.glob("*"):
            if f.suffix.lower() in ['.wav', '.mp3', '.m4a', '.ogg']:
                samples.append({
                    "name": f"[라이브러리] {f.stem}",
                    "path": str(f),
                    "description": "기본 음성 라이브러리",
                    "created_at": ""
                })

    return samples


def save_voice_sample(uploaded_file, name: str, description: str, samples_dir: Path):
    """음성 샘플 저장"""
    import json

    # 파일 저장
    ext = uploaded_file.name.rsplit('.', 1)[-1]
    filename = f"{name.replace(' ', '_')}.{ext}"
    filepath = samples_dir / filename

    with open(filepath, "wb") as f:
        f.write(uploaded_file.getbuffer())

    # 메타데이터 저장
    meta_path = samples_dir / "samples_meta.json"

    if meta_path.exists():
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
    else:
        meta = {"samples": []}

    # 중복 제거
    meta["samples"] = [s for s in meta["samples"] if s["filename"] != filename]

    meta["samples"].append({
        "name": name,
        "filename": filename,
        "description": description,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
    })

    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    st.success(f"✅ '{name}' 샘플이 저장되었습니다!")
    time.sleep(0.5)
    st.rerun()


def delete_voice_sample(filepath: str):
    """음성 샘플 삭제"""
    import json

    filepath = Path(filepath)

    if filepath.exists():
        filepath.unlink()

    # 메타데이터에서도 제거
    samples_dir = filepath.parent
    meta_path = samples_dir / "samples_meta.json"

    if meta_path.exists():
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)

        filename = filepath.name
        meta["samples"] = [s for s in meta["samples"] if s["filename"] != filename]

        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

    st.success("삭제되었습니다.")
    time.sleep(0.5)
    st.rerun()


def render_voice_clone_manager():
    """🎭 음성 클론 관리 섹션"""
    st.markdown("### 🎭 음성 클론 관리")

    samples_dir = get_voice_samples_dir()

    # 탭: 업로드 / 녹음 / 관리
    clone_tabs = st.tabs(["📤 업로드", "🎙️ 녹음", "📋 클론 목록"])

    # ─────────────────────────────────────────────
    # 탭 1: 음성 샘플 업로드
    # ─────────────────────────────────────────────
    with clone_tabs[0]:
        st.markdown("#### 📤 새 음성 샘플 업로드")
        st.info("💡 3~10초 길이의 깨끗한 음성 파일을 업로드하세요. (WAV/MP3 권장)")

        uploaded_file = st.file_uploader(
            "음성 파일 선택",
            type=["wav", "mp3", "m4a", "ogg"],
            key="voice_sample_upload"
        )

        if uploaded_file:
            # 미리듣기
            st.audio(uploaded_file)

            col1, col2 = st.columns(2)

            with col1:
                sample_name = st.text_input(
                    "샘플 이름",
                    value=uploaded_file.name.rsplit('.', 1)[0],
                    key="sample_name_input"
                )

            with col2:
                sample_desc = st.text_input(
                    "설명 (선택)",
                    placeholder="예: 밝은 톤, 차분한 목소리",
                    key="sample_desc_input"
                )

            if st.button("💾 샘플 저장", type="primary", use_container_width=True, key="save_sample"):
                if sample_name:
                    save_voice_sample(uploaded_file, sample_name, sample_desc, samples_dir)
                else:
                    st.warning("샘플 이름을 입력하세요.")

    # ─────────────────────────────────────────────
    # 탭 2: 음성 녹음
    # ─────────────────────────────────────────────
    with clone_tabs[1]:
        st.markdown("#### 🎙️ 음성 녹음")

        # audiorecorder 라이브러리 시도
        try:
            from audiorecorder import audiorecorder

            st.info("💡 🔴 버튼을 클릭하여 녹음을 시작/중지하세요.")

            audio = audiorecorder("🔴 녹음 시작", "⏹️ 녹음 중지", key="voice_recorder")

            if len(audio) > 0:
                st.audio(audio.export().read())

                col1, col2 = st.columns(2)

                with col1:
                    rec_name = st.text_input("녹음 이름", key="rec_name_input")

                with col2:
                    rec_desc = st.text_input("설명", key="rec_desc_input")

                if st.button("💾 녹음 저장", type="primary", key="save_recording"):
                    if rec_name:
                        # WAV로 저장
                        filepath = samples_dir / f"{rec_name}.wav"
                        audio.export(str(filepath), format="wav")

                        # 메타데이터 저장
                        import json
                        meta_path = samples_dir / "samples_meta.json"

                        if meta_path.exists():
                            with open(meta_path, "r", encoding="utf-8") as f:
                                meta = json.load(f)
                        else:
                            meta = {"samples": []}

                        meta["samples"].append({
                            "name": rec_name,
                            "filename": f"{rec_name}.wav",
                            "description": rec_desc,
                            "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
                        })

                        with open(meta_path, "w", encoding="utf-8") as f:
                            json.dump(meta, f, ensure_ascii=False, indent=2)

                        st.success("녹음이 저장되었습니다!")
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.warning("녹음 이름을 입력하세요.")

        except ImportError:
            st.warning("녹음 기능을 사용하려면 라이브러리를 설치하세요:")
            st.code("pip install streamlit-audiorecorder")

            st.markdown("---")
            st.markdown("**대안: 녹음 파일 직접 업로드**")
            st.info("휴대폰이나 다른 기기로 녹음 후 '📤 업로드' 탭에서 업로드하세요.")

    # ─────────────────────────────────────────────
    # 탭 3: 클론 목록 관리
    # ─────────────────────────────────────────────
    with clone_tabs[2]:
        st.markdown("#### 📋 저장된 음성 클론")

        samples = get_voice_samples(samples_dir)

        if not samples:
            st.info("저장된 음성 샘플이 없습니다. 위에서 업로드하거나 녹음하세요.")
        else:
            st.caption(f"총 {len(samples)}개의 음성 샘플")

            for i, sample in enumerate(samples):
                with st.container():
                    col1, col2, col3, col4 = st.columns([4, 1, 1, 1])

                    with col1:
                        st.markdown(f"**{sample['name']}**")
                        if sample.get('description'):
                            st.caption(sample['description'])

                    with col2:
                        # 미리듣기
                        if st.button("▶️", key=f"play_sample_{i}", help="미리듣기"):
                            st.session_state[f"preview_sample_{i}"] = True

                    with col3:
                        # 기본 음성으로 설정
                        is_default = sample['path'] == st.session_state.get("default_voice_sample")
                        if st.button(
                            "⭐" if is_default else "☆",
                            key=f"default_sample_{i}",
                            help="기본 음성으로 설정"
                        ):
                            st.session_state["default_voice_sample"] = sample['path']
                            st.toast(f"'{sample['name']}'을 기본 음성으로 설정했습니다.")

                    with col4:
                        # 삭제 (라이브러리 파일은 삭제 불가)
                        if "[라이브러리]" not in sample['name']:
                            if st.button("🗑️", key=f"delete_sample_{i}", help="삭제"):
                                delete_voice_sample(sample['path'])
                        else:
                            st.caption("🔒")

                    # 미리듣기 오디오
                    if st.session_state.get(f"preview_sample_{i}"):
                        st.audio(sample['path'])
                        st.session_state[f"preview_sample_{i}"] = False

                    st.markdown("---")


def render_reference_voice_selector():
    """참조 음성 선택 (개선된 버전)"""
    st.markdown("#### 🎤 참조 음성 선택")

    samples_dir = get_voice_samples_dir()
    samples = get_voice_samples(samples_dir)

    if not samples:
        st.warning("저장된 음성 샘플이 없습니다. 위 '음성 클론 관리'에서 먼저 샘플을 추가하세요.")
        return None

    # 기본 음성 확인
    default_voice = st.session_state.get("default_voice_sample")
    default_index = 0

    sample_options = ["없음 (기본 음성)"] + [s['name'] for s in samples]
    sample_paths = {s['name']: s['path'] for s in samples}

    if default_voice:
        for i, s in enumerate(samples):
            if s['path'] == default_voice:
                default_index = i + 1
                break

    selected_name = st.selectbox(
        "참조 음성",
        options=sample_options,
        index=default_index,
        key="ref_voice_select"
    )

    if selected_name and selected_name != "없음 (기본 음성)":
        selected_path = sample_paths.get(selected_name)

        if selected_path:
            # 미리듣기
            st.audio(selected_path)
            st.session_state["selected_reference_voice"] = selected_path
            return selected_path

    return None


# ============================================================
# Chatterbox 탭
# ============================================================

def render_chatterbox_tab():
    """Chatterbox 탭 렌더링"""
    st.markdown("### 🎤 Chatterbox TTS")
    st.info("Chatterbox는 고품질 음성 합성 서버입니다. 로컬 서버가 실행 중이어야 합니다.")

    # 서버 상태 확인
    server_status = check_chatterbox_server()

    if not server_status:
        st.error("Chatterbox 서버에 연결할 수 없습니다.")

        col1, col2, col3 = st.columns(3)

        with col1:
            if st.button("🚀 서버 시작 (새 창)", type="primary", use_container_width=True):
                try:
                    import subprocess
                    subprocess.Popen(
                        'start cmd /k "cd /d C:\\Users\\KIMJAEHEON\\chatter && call venv\\Scripts\\activate.bat && python run.py"',
                        shell=True
                    )
                    st.success("서버 시작 명령 전송!")
                    st.info("새 콘솔 창에서 서버가 시작됩니다. 잠시 후 새로고침하세요.")
                except Exception as e:
                    st.error(f"오류: {e}")

        with col2:
            if st.button("🔄 연결 확인", use_container_width=True):
                st.rerun()

        with col3:
            st.caption("또는 수동으로:")
            st.code("cd C:\\Users\\KIMJAEHEON\\chatter\npython run.py", language="bash")

        return

    st.success("Chatterbox 서버 연결됨")

    # 서버 상태 정보
    status = get_chatterbox_status()
    if status:
        model_loaded = status.get("model_loaded", False)
        if model_loaded:
            st.success("🟢 모델 로드됨")
        else:
            st.warning("🟡 모델 미로드")
            if st.button("🔄 모델 로드", key="load_chatterbox_model"):
                with st.spinner("모델 로딩 중..."):
                    try:
                        r = requests.post(f"{CHATTERBOX_URL}/load", timeout=120)
                        if r.status_code == 200:
                            st.success("모델 로드 완료!")
                            st.rerun()
                    except Exception as e:
                        st.error(f"로드 실패: {e}")

    st.markdown("---")

    # =========================================================
    # 🎭 음성 클론 관리 (핵심 기능!)
    # =========================================================
    with st.expander("🎭 음성 클론 관리", expanded=True):
        render_voice_clone_manager()

    st.markdown("---")

    # === 음성 파라미터 ===
    st.markdown("#### 🎚️ 음성 파라미터")

    # 빠른 프리셋
    preset_cols = st.columns(5)

    with preset_cols[0]:
        if st.button("🐢 차분", use_container_width=True, key="preset_calm"):
            st.session_state["chatter_exag"] = 0.3
            st.session_state["chatter_speed"] = 0.9

    with preset_cols[1]:
        if st.button("⚡ 빠름", use_container_width=True, key="preset_fast"):
            st.session_state["chatter_speed"] = 1.3

    with preset_cols[2]:
        if st.button("😊 감정", use_container_width=True, key="preset_emotion"):
            st.session_state["chatter_exag"] = 0.7

    with preset_cols[3]:
        if st.button("🎯 정확", use_container_width=True, key="preset_precise"):
            st.session_state["chatter_cfg"] = 0.7

    with preset_cols[4]:
        if st.button("🔄 초기화", use_container_width=True, key="preset_reset"):
            st.session_state["chatter_exag"] = 0.5
            st.session_state["chatter_cfg"] = 0.5
            st.session_state["chatter_speed"] = 1.0
            st.session_state["chatter_temp"] = 0.8

    col1, col2 = st.columns(2)

    with col1:
        cfg_weight = st.slider(
            "🎯 CFG Weight (품질/속도)",
            min_value=0.0,
            max_value=1.0,
            value=st.session_state.get("chatter_cfg", 0.5),
            step=0.05,
            key="chatter_cfg_slider"
        )
        st.session_state["chatter_cfg"] = cfg_weight

        speed = st.slider(
            "⏱️ 말하기 속도",
            min_value=0.5,
            max_value=2.0,
            value=st.session_state.get("chatter_speed", 1.0),
            step=0.05,
            key="chatter_speed_slider"
        )
        st.session_state["chatter_speed"] = speed

    with col2:
        exaggeration = st.slider(
            "😊 감정 강도 (Exaggeration)",
            min_value=0.0,
            max_value=1.0,
            value=st.session_state.get("chatter_exag", 0.5),
            step=0.05,
            key="chatter_exag_slider"
        )
        st.session_state["chatter_exag"] = exaggeration

        temperature = st.slider(
            "🌡️ Temperature (다양성)",
            min_value=0.3,
            max_value=1.5,
            value=st.session_state.get("chatter_temp", 0.8),
            step=0.05,
            key="chatter_temp_slider"
        )
        st.session_state["chatter_temp"] = temperature

    # 시드 설정
    col1, col2 = st.columns([1, 1])
    with col1:
        use_random_seed = st.checkbox("🎲 랜덤 시드", value=True, key="chatter_random_seed")
    with col2:
        if not use_random_seed:
            seed = st.number_input("Seed", min_value=0, value=42, key="chatter_seed_input")
        else:
            seed = None

    st.markdown("---")

    # === 참조 음성 선택 (개선된 버전) ===
    voice_path = render_reference_voice_selector()

    st.markdown("---")

    # === 텍스트 입력 ===
    st.markdown("#### 📝 텍스트 입력")

    script_text = st.text_area(
        "텍스트 입력",
        value="안녕하세요. Chatterbox TTS 테스트입니다. 음성 품질을 확인해보세요.",
        height=150,
        key="chatter_text_input"
    )

    if script_text:
        st.caption(f"📊 {len(script_text)}자 | 예상 시간: 약 {max(1, len(script_text) // 100)}분")

    st.markdown("---")

    # === 생성 버튼 ===
    col1, col2 = st.columns([2, 1])

    with col1:
        if st.button(
            "🎧 프리뷰 생성",
            type="primary",
            use_container_width=True,
            disabled=not script_text or not server_status,
            key="generate_chatterbox"
        ):
            generate_chatterbox_tts(
                text=script_text,
                cfg_weight=cfg_weight,
                exaggeration=exaggeration,
                temperature=temperature,
                speed=speed,
                seed=seed,
                voice_ref_path=voice_path
            )

    with col2:
        st.button("🚀 전체 TTS 생성", use_container_width=True, key="full_chatterbox")


def generate_chatterbox_tts(text, cfg_weight, exaggeration, temperature, speed, seed, voice_ref_path):
    """Chatterbox TTS 생성"""
    progress = st.progress(0)
    status = st.empty()

    status.text("Chatterbox TTS 생성 중...")
    progress.progress(30)

    try:
        payload = {
            "text": text,
            "settings": {
                "language": "ko",
                "exaggeration": exaggeration,
                "cfg_weight": cfg_weight,
                "temperature": temperature,
                "speed": speed,
                "seed": seed,
                "voice_ref_path": voice_ref_path
            }
        }

        start_time = time.time()
        r = requests.post(f"{CHATTERBOX_URL}/generate", json=payload, timeout=120)
        elapsed = time.time() - start_time

        if r.status_code == 200:
            result = r.json()

            if result.get("success"):
                progress.progress(100)
                status.success(f"생성 완료! ({result.get('duration_seconds', 0):.1f}초, 처리시간: {elapsed:.1f}s)")

                # 오디오 재생
                audio_url = result.get("audio_url", "")
                if audio_url:
                    full_url = f"{CHATTERBOX_URL}{audio_url}"
                    try:
                        audio_response = requests.get(full_url, timeout=30)
                        if audio_response.status_code == 200:
                            st.audio(audio_response.content, format="audio/wav")
                    except:
                        st.warning(f"오디오 로드 실패: {full_url}")

                # 생성 정보
                with st.expander("생성 정보"):
                    st.json({
                        "duration": result.get("duration_seconds"),
                        "seed_used": result.get("seed_used"),
                        "processing_time": f"{elapsed:.2f}s"
                    })
            else:
                status.error(f"생성 실패: {result.get('error', 'Unknown error')}")
        else:
            status.error(f"서버 오류: {r.status_code}")

    except requests.exceptions.Timeout:
        status.error("요청 시간 초과")
    except Exception as e:
        status.error(f"오류: {e}")
        import traceback
        with st.expander("상세 오류"):
            st.code(traceback.format_exc())


# ============================================================
# 수동 입력 탭
# ============================================================

def render_manual_input_tab():
    """수동 입력 탭"""
    st.markdown("### ✏️ 수동 입력")
    st.info("스크립트를 직접 입력하거나 파일에서 불러옵니다.")

    # 파일 업로드
    uploaded_file = st.file_uploader(
        "텍스트 파일 업로드",
        type=["txt", "md"],
        key="manual_upload"
    )

    if uploaded_file:
        content = uploaded_file.read().decode("utf-8")
        st.session_state["manual_script"] = content
        st.success(f"파일 로드: {len(content)}자")

    # 텍스트 입력
    script = st.text_area(
        "스크립트",
        value=st.session_state.get("manual_script", ""),
        height=400,
        placeholder="TTS로 변환할 텍스트를 입력하세요...",
        key="manual_script_input"
    )

    if script:
        st.caption(f"📊 {len(script)}자 | {len(script.split())}단어 | {script.count(chr(10)) + 1}줄")
        st.session_state["generated_script"] = script

    # 저장 버튼
    if st.button("💾 스크립트 저장", use_container_width=True, key="save_manual_script"):
        if script:
            st.session_state["generated_script"] = script
            st.success("스크립트가 저장되었습니다!")


# ============================================================
# 미리듣기 탭
# ============================================================

def render_preview_tab():
    """미리듣기 탭"""
    st.markdown("### 🎧 미리듣기")

    # 마지막 생성 오디오
    if "last_tts_audio" in st.session_state and st.session_state["last_tts_audio"]:
        st.markdown("#### 🔊 마지막 생성 오디오")
        if os.path.exists(st.session_state["last_tts_audio"]):
            st.audio(st.session_state["last_tts_audio"])
        else:
            st.warning("파일을 찾을 수 없습니다.")

    st.markdown("---")

    # 생성 히스토리
    st.markdown("#### 📜 생성 히스토리")

    tts_dir = st.session_state.get("tts_output_dir", "data/tts")

    if os.path.exists(tts_dir):
        files = []
        for f in os.listdir(tts_dir):
            if f.endswith(('.wav', '.mp3')):
                files.append(f)

        files = sorted(
            files,
            key=lambda x: os.path.getmtime(os.path.join(tts_dir, x)),
            reverse=True
        )[:10]

        if files:
            for f in files:
                file_path = os.path.join(tts_dir, f)
                file_size = os.path.getsize(file_path) / 1024  # KB

                with st.expander(f"▶️ {f} ({file_size:.1f} KB)"):
                    st.audio(file_path)

                    col1, col2 = st.columns(2)
                    with col1:
                        with open(file_path, "rb") as file:
                            st.download_button(
                                "💾 다운로드",
                                data=file,
                                file_name=f,
                                use_container_width=True,
                                key=f"dl_{f}"
                            )
                    with col2:
                        if st.button("🗑️ 삭제", key=f"del_{f}", use_container_width=True):
                            os.remove(file_path)
                            st.rerun()
        else:
            st.info("생성된 오디오가 없습니다.")
    else:
        st.info("출력 디렉토리가 없습니다.")


# ============================================================
# 메인
# ============================================================

def main():
    """메인 함수"""
    st.title("🎤 TTS 생성")

    # 프로젝트 선택
    col1, col2 = st.columns([3, 1])
    with col1:
        project = st.selectbox(
            "프로젝트 선택",
            options=["세모지", "프로젝트 2", "프로젝트 3"],
            key="tts_project"
        )

    st.markdown("---")

    # === 탭 구성 ===
    tabs = st.tabs([
        "⚙️ 설정",
        "✨ Edge TTS",
        "🎤 Chatterbox",
        "✏️ 수동 입력",
        "🎧 미리듣기"
    ])

    with tabs[0]:
        render_settings_tab()

    with tabs[1]:
        render_edge_tts_tab()

    with tabs[2]:
        render_chatterbox_tab()

    with tabs[3]:
        render_manual_input_tab()

    with tabs[4]:
        render_preview_tab()


if __name__ == "__main__":
    main()
