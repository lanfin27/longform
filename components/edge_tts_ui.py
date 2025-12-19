"""
Edge TTS 확장 UI 컴포넌트

전체 음성 + 전체 기능 지원:
- 언어별 음성 선택 (한국어 9개, 영어 12개, 일본어 8개, 중국어 8개)
- 성별 필터
- 음성 미리듣기
- 스타일/감정 설정 (지원 음성)
- 속도/피치/볼륨 조절
"""
import streamlit as st
from typing import Optional, Dict, List
from pathlib import Path
import time

import sys
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

# 새로운 확장 모듈 임포트
try:
    from core.tts.edge_tts_voices import (
        get_voice_database,
        VoiceGender,
        VoiceInfo,
        STYLE_NAMES_KO
    )
    from core.tts.edge_tts_extended import (
        get_extended_edge_tts_client,
        TTSSettings,
        TTSResult
    )
    EXTENDED_AVAILABLE = True
except ImportError as e:
    print(f"[EdgeTTS UI] 확장 모듈 로드 실패: {e}")
    EXTENDED_AVAILABLE = False


def render_language_selector(key_prefix: str = "edge") -> str:
    """
    언어 선택 UI 렌더링

    Returns:
        선택된 언어 코드 ("ko", "en", "ja", "zh")
    """
    if not EXTENDED_AVAILABLE:
        return "ko"

    db = get_voice_database()
    lang_info = db.get_language_info()

    # 현재 선택된 언어
    current_lang = st.session_state.get(f"{key_prefix}_lang", "ko")

    st.markdown("### 언어 선택")

    cols = st.columns(len(lang_info))
    for i, (code, info) in enumerate(lang_info.items()):
        with cols[i]:
            is_selected = current_lang == code
            btn_type = "primary" if is_selected else "secondary"

            if st.button(
                f"{info['flag']} {info['name']} ({info['count']})",
                key=f"{key_prefix}_lang_{code}",
                type=btn_type,
                use_container_width=True
            ):
                st.session_state[f"{key_prefix}_lang"] = code
                st.rerun()

    return st.session_state.get(f"{key_prefix}_lang", "ko")


def render_voice_selector(
    language: str,
    key_prefix: str = "edge"
) -> Optional[VoiceInfo]:
    """
    음성 선택 UI 렌더링

    Args:
        language: 언어 코드
        key_prefix: 세션 상태 키 접두사

    Returns:
        선택된 VoiceInfo 또는 None
    """
    if not EXTENDED_AVAILABLE:
        return None

    db = get_voice_database()
    voices = db.get_voices_by_language(language)

    if not voices:
        st.warning(f"'{language}' 언어의 음성을 찾을 수 없습니다.")
        return None

    st.markdown("### 음성 선택")

    # 성별 필터
    gender_filter = st.radio(
        "성별 필터",
        options=["전체", "여성", "남성"],
        horizontal=True,
        key=f"{key_prefix}_gender_filter"
    )

    if gender_filter == "여성":
        voices = [v for v in voices if v.gender == VoiceGender.FEMALE]
    elif gender_filter == "남성":
        voices = [v for v in voices if v.gender == VoiceGender.MALE]

    # 현재 선택된 음성 ID
    current_voice_id = st.session_state.get(f"{key_prefix}_voice_id", voices[0].id if voices else "")

    # 음성 카드 그리드
    cols_per_row = 3
    rows = (len(voices) + cols_per_row - 1) // cols_per_row

    selected_voice = None

    for row in range(rows):
        cols = st.columns(cols_per_row)
        for col_idx in range(cols_per_row):
            voice_idx = row * cols_per_row + col_idx
            if voice_idx >= len(voices):
                break

            voice = voices[voice_idx]
            is_selected = voice.id == current_voice_id

            with cols[col_idx]:
                # 음성 카드
                gender_emoji = "👩" if voice.gender == VoiceGender.FEMALE else "👨"
                style_badge = "✨" if voice.styles else ""

                card_style = "border: 2px solid #2196F3; background: #E3F2FD;" if is_selected else "border: 1px solid #ddd;"

                st.markdown(f"""
                <div style="
                    padding: 10px;
                    border-radius: 8px;
                    {card_style}
                    margin-bottom: 8px;
                ">
                    <div style="font-weight: bold; font-size: 14px;">
                        {gender_emoji} {voice.name} {style_badge}
                    </div>
                    <div style="color: #666; font-size: 11px; margin-top: 4px;">
                        {voice.description[:35]}...
                    </div>
                </div>
                """, unsafe_allow_html=True)

                col1, col2 = st.columns(2)
                with col1:
                    if st.button("선택", key=f"{key_prefix}_select_{voice.id}", use_container_width=True):
                        st.session_state[f"{key_prefix}_voice_id"] = voice.id
                        st.rerun()

                with col2:
                    if st.button("미리듣기", key=f"{key_prefix}_preview_{voice.id}", use_container_width=True):
                        with st.spinner("샘플 생성 중..."):
                            client = get_extended_edge_tts_client()
                            sample_path = client.generate_sample(voice.id)
                            if sample_path:
                                st.audio(sample_path)
                            else:
                                st.error("샘플 생성 실패")

            if is_selected:
                selected_voice = voice

    # 선택된 음성 정보 표시
    if selected_voice:
        st.info(f"**선택된 음성:** {selected_voice.name} ({selected_voice.gender.value}) - {selected_voice.description}")

    return selected_voice


def render_voice_settings(
    voice: Optional[VoiceInfo],
    key_prefix: str = "edge"
) -> TTSSettings:
    """
    음성 설정 UI 렌더링

    Args:
        voice: 선택된 음성 정보
        key_prefix: 세션 상태 키 접두사

    Returns:
        TTSSettings 객체
    """
    if not EXTENDED_AVAILABLE:
        return TTSSettings()

    st.markdown("### TTS 설정")

    col1, col2, col3 = st.columns(3)

    with col1:
        rate = st.slider(
            "속도",
            min_value=-50,
            max_value=100,
            value=0,
            step=5,
            format="%d%%",
            help="-50% (느림) ~ +100% (빠름)",
            key=f"{key_prefix}_rate"
        )

    with col2:
        pitch = st.slider(
            "피치",
            min_value=-50,
            max_value=50,
            value=0,
            step=5,
            format="%dHz",
            help="-50Hz (낮음) ~ +50Hz (높음)",
            key=f"{key_prefix}_pitch"
        )

    with col3:
        volume = st.slider(
            "볼륨",
            min_value=-50,
            max_value=50,
            value=0,
            step=5,
            format="%d%%",
            help="-50% (작음) ~ +50% (큼)",
            key=f"{key_prefix}_volume"
        )

    # 스타일 설정 (지원 음성만)
    style = ""
    style_degree = 1.0

    if voice and voice.styles:
        st.markdown("### 감정/스타일")

        style_options = ["없음"] + voice.styles

        # 스타일 이름 매핑
        def format_style(s):
            if s == "없음":
                return "없음 (기본)"
            return STYLE_NAMES_KO.get(s, s)

        selected_style = st.selectbox(
            "스타일 선택",
            options=style_options,
            format_func=format_style,
            key=f"{key_prefix}_style"
        )

        if selected_style != "없음":
            style = selected_style
            style_degree = st.slider(
                "스타일 강도",
                min_value=0.5,
                max_value=2.0,
                value=1.0,
                step=0.1,
                key=f"{key_prefix}_style_degree"
            )

    # 휴식 설정
    st.markdown("### 휴식 설정")

    add_breaks = st.checkbox(
        "문단/문장 사이에 자동 휴식 삽입",
        value=True,
        key=f"{key_prefix}_add_breaks"
    )

    paragraph_break_ms = 800
    sentence_break_ms = 300

    if add_breaks:
        col1, col2 = st.columns(2)
        with col1:
            paragraph_break_ms = st.slider(
                "문단 간 휴식 (ms)",
                min_value=200,
                max_value=2000,
                value=800,
                step=100,
                key=f"{key_prefix}_para_break"
            )
        with col2:
            sentence_break_ms = st.slider(
                "문장 간 휴식 (ms)",
                min_value=100,
                max_value=1000,
                value=300,
                step=50,
                key=f"{key_prefix}_sent_break"
            )

    # 무음 패딩 설정
    st.markdown("### 시니어 친화 설정")

    add_silence = st.checkbox(
        "문단 사이에 무음 패딩 삽입",
        value=True,
        key=f"{key_prefix}_add_silence"
    )

    silence_ms = 1500
    if add_silence:
        silence_ms = st.slider(
            "무음 길이 (ms)",
            min_value=500,
            max_value=5000,
            value=1500,
            step=100,
            key=f"{key_prefix}_silence_ms"
        )

    # 자막 설정
    generate_subtitles = st.checkbox(
        "자막 파일 생성 (SRT)",
        value=True,
        key=f"{key_prefix}_gen_subs"
    )

    return TTSSettings(
        voice_id=voice.id if voice else "ko-KR-SunHiNeural",
        rate=rate,
        pitch=pitch,
        volume=volume,
        style=style,
        style_degree=style_degree,
        paragraph_break_ms=paragraph_break_ms,
        sentence_break_ms=sentence_break_ms,
        add_breaks=add_breaks,
        add_silence=add_silence,
        silence_ms=silence_ms,
        generate_subtitles=generate_subtitles
    )


def render_tts_generation(
    script: str,
    settings: TTSSettings,
    output_path: str,
    key_prefix: str = "edge"
) -> Optional[TTSResult]:
    """
    TTS 생성 버튼 및 결과 UI 렌더링

    Args:
        script: 스크립트 텍스트
        settings: TTS 설정
        output_path: 출력 파일 경로
        key_prefix: 세션 상태 키 접두사

    Returns:
        생성 결과 또는 None
    """
    if not EXTENDED_AVAILABLE:
        st.error("Edge TTS 확장 모듈을 사용할 수 없습니다.")
        return None

    if not script:
        st.warning("스크립트가 없습니다.")
        return None

    # 설정 요약
    st.info(f"""
    **생성 설정 요약**
    - 음성: {settings.voice_id}
    - 속도: {settings.get_rate_string()}
    - 피치: {settings.get_pitch_string()}
    - 볼륨: {settings.get_volume_string()}
    - 스타일: {settings.style or "없음"}
    - 무음 패딩: {"활성화 (" + str(settings.silence_ms) + "ms)" if settings.add_silence else "비활성화"}
    """)

    # 문자 수 표시
    st.caption(f"스크립트: {len(script):,}자 | 예상 시간: 약 {len(script) // 150}분")

    result = None

    if st.button("Edge TTS 생성", type="primary", use_container_width=True, key=f"{key_prefix}_generate"):
        start_time = time.time()

        progress = st.progress(0)
        status = st.empty()

        try:
            status.text("TTS 엔진 초기화...")
            progress.progress(10)

            client = get_extended_edge_tts_client()

            status.text("음성 생성 중...")
            progress.progress(30)

            result = client.generate_tts(script, settings, output_path)

            progress.progress(100)

            if result.success:
                elapsed = time.time() - start_time
                status.success(f"생성 완료! ({elapsed:.1f}초)")

                # 오디오 재생
                if result.audio_path:
                    st.audio(result.audio_path)

                # 다운로드 버튼
                col1, col2 = st.columns(2)

                with col1:
                    if result.audio_path:
                        with open(result.audio_path, "rb") as f:
                            st.download_button(
                                "오디오 다운로드 (MP3)",
                                data=f,
                                file_name=f"tts_{int(time.time())}.mp3",
                                mime="audio/mpeg",
                                use_container_width=True
                            )

                with col2:
                    if result.subtitle_path:
                        with open(result.subtitle_path, "rb") as f:
                            st.download_button(
                                "자막 다운로드 (SRT)",
                                data=f,
                                file_name=f"tts_{int(time.time())}.srt",
                                mime="text/plain",
                                use_container_width=True
                            )

                # 무음 패딩 정보
                if result.paragraph_count > 0:
                    st.caption(f"무음 패딩: {result.paragraph_count}개 위치, 총 {result.total_silence_ms}ms")

            else:
                status.error(f"오류: {result.error}")

        except Exception as e:
            status.error(f"예외: {e}")
            import traceback
            with st.expander("상세 오류"):
                st.code(traceback.format_exc())

    return result


def render_edge_tts_tab(
    script: str,
    output_path: str,
    key_prefix: str = "edge"
) -> Optional[TTSResult]:
    """
    Edge TTS 탭 전체 UI 렌더링

    Args:
        script: 스크립트 텍스트
        output_path: 출력 파일 경로
        key_prefix: 세션 상태 키 접두사

    Returns:
        생성 결과 또는 None
    """
    if not EXTENDED_AVAILABLE:
        st.error("""
        Edge TTS 확장 모듈을 사용할 수 없습니다.

        필요한 파일:
        - core/tts/edge_tts_voices.py
        - core/tts/edge_tts_extended.py
        """)

        # 폴백: 기존 방식
        st.info("기존 Edge TTS를 사용합니다.")
        return None

    st.subheader("Edge TTS 생성 (확장)")

    # 1. 언어 선택
    language = render_language_selector(key_prefix)

    st.divider()

    # 2. 음성 선택
    voice = render_voice_selector(language, key_prefix)

    st.divider()

    # 3. 설정
    settings = render_voice_settings(voice, key_prefix)

    st.divider()

    # 4. 생성
    return render_tts_generation(script, settings, output_path, key_prefix)
