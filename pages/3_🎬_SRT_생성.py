# -*- coding: utf-8 -*-
"""
3단계: SRT 생성 (워크플로우 v2.0)

오디오 파일에서 SRT 자막 생성:
1단계: Whisper SRT 생성 (정확한 타임스탬프, 오타 있을 수 있음)
1.5단계: 씬 묶음 (선택) - N개의 씬을 하나로 병합
1.7단계: 자막 줄바꿈 (선택) - 긴 자막 줄바꿈
2단계: AI 원문 교정 (선택) - 타임스탬프 유지하면서 텍스트만 교정

⭐ 각 단계별 SRT/JSON 다운로드 가능
⭐ 선택 단계는 건너뛰기 가능
"""

import streamlit as st
import os
import json
import time
from pathlib import Path
from datetime import datetime
import sys

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from utils.project_manager import (
    ensure_project_selected,
    get_current_project,
    get_current_project_config,
    render_project_sidebar,
)
from utils.api_helper import show_api_status_sidebar

# ============================================================
# 페이지 설정
# ============================================================

st.set_page_config(
    page_title="SRT 생성",
    page_icon="🎬",
    layout="wide"
)

render_project_sidebar()
show_api_status_sidebar()

st.title("🎬 SRT 생성 (워크플로우 v2.0)")

# ============================================================
# AI 모델 설정
# ============================================================

# ⭐ v4.0: Claude 먼저 (빠름, Rate Limit 없음!)
AI_MODELS = {
    'anthropic': {
        'name': 'Anthropic Claude (권장)',
        'speed': '빠름',
        'models': [
            {'id': 'claude-3-5-sonnet-20241022', 'name': 'Claude 3.5 Sonnet (추천)', 'default': True},
            {'id': 'claude-sonnet-4-20250514', 'name': 'Claude Sonnet 4'},
            {'id': 'claude-3-opus-20240229', 'name': 'Claude 3 Opus (최고 품질)'},
            {'id': 'claude-3-haiku-20240307', 'name': 'Claude 3 Haiku (빠름)'},
        ]
    },
    'google': {
        'name': 'Google Gemini',
        'speed': '느림 (Rate Limit)',
        'models': [
            {'id': 'gemini-2.5-flash', 'name': 'Gemini 2.5 Flash (무료)', 'default': True},
            {'id': 'gemini-1.5-flash', 'name': 'Gemini 1.5 Flash'},
            {'id': 'gemini-2.5-flash-lite', 'name': 'Gemini 2.5 Flash Lite (초고속)'},
        ]
    }
}

# ============================================================
# 세션 상태 초기화
# ============================================================

if "whisper_srt_result" not in st.session_state:
    st.session_state["whisper_srt_result"] = None

if "ai_corrected_result" not in st.session_state:
    st.session_state["ai_corrected_result"] = None

if "original_script" not in st.session_state:
    st.session_state["original_script"] = ""

if "ai_correction_provider" not in st.session_state:
    st.session_state["ai_correction_provider"] = "anthropic"  # ⭐ v4.0: Claude 기본값 (빠름!)

if "ai_correction_model" not in st.session_state:
    st.session_state["ai_correction_model"] = "claude-3-5-sonnet-20241022"

if "ai_correction_running" not in st.session_state:
    st.session_state["ai_correction_running"] = False

# ⭐ 건너뛰기 상태 관리
if "skip_scene_merge" not in st.session_state:
    st.session_state["skip_scene_merge"] = False

if "skip_line_wrap" not in st.session_state:
    st.session_state["skip_line_wrap"] = False

# ============================================================
# HybridSRTGenerator import
# ============================================================

try:
    from utils.hybrid_srt_generator import (
        HybridSRTGenerator,
        get_hybrid_generator
    )
    GENERATOR_AVAILABLE = True
except ImportError as e:
    GENERATOR_AVAILABLE = False
    st.error(f"HybridSRTGenerator import 실패: {e}")

# ============================================================
# 메인 UI
# ============================================================

# 설명
st.markdown("""
### SRT 생성 워크플로우 v2.0

| 단계 | 기능 | 설명 | 필수 |
|------|------|------|------|
| **1단계** | Whisper SRT 생성 | 오디오에서 정확한 타임스탬프 추출 | ✅ |
| **1.5단계** | 씬 묶음 | N개의 연속 씬을 하나로 병합 | ⭕ 선택 |
| **1.7단계** | 자막 줄바꿈 | 긴 자막을 읽기 쉽게 줄바꿈 | ⭕ 선택 |
| **2단계** | AI 원문 교정 | 원문 스크립트와 비교해서 오타 교정 | ⭕ 선택 |

> **핵심**: 타임스탬프는 1단계에서 확정! 이후 단계에서는 텍스트만 가공!
>
> 💡 각 단계별 **SRT/JSON 다운로드** 가능 | 선택 단계는 **건너뛰기** 가능
""")

st.markdown("---")

# ============================================================
# 입력 영역
# ============================================================

col_input1, col_input2 = st.columns(2)

with col_input1:
    st.subheader("🎵 오디오 파일")

    # 파일 업로드
    uploaded_audio = st.file_uploader(
        "오디오 파일 선택",
        type=["mp3", "wav", "m4a", "flac", "ogg"],
        key="audio_uploader"
    )

    # 또는 경로 직접 입력
    audio_path_input = st.text_input(
        "또는 오디오 파일 경로 입력",
        placeholder="C:/path/to/audio.mp3",
        key="audio_path_input"
    )

    # 오디오 경로 결정
    audio_path = None
    if uploaded_audio:
        # 업로드된 파일 임시 저장
        temp_dir = Path(ROOT_DIR) / "data" / "temp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_path = temp_dir / uploaded_audio.name

        with open(temp_path, "wb") as f:
            f.write(uploaded_audio.getbuffer())

        audio_path = str(temp_path)
        st.success(f"업로드됨: {uploaded_audio.name}")

    elif audio_path_input and os.path.exists(audio_path_input):
        audio_path = audio_path_input
        st.success(f"파일 확인됨: {os.path.basename(audio_path)}")

with col_input2:
    st.subheader("📝 원문 스크립트 (2단계용)")

    original_script = st.text_area(
        "원문 스크립트 (AI 교정 시 기준 텍스트)",
        value=st.session_state.get("original_script", ""),
        height=200,
        placeholder="2단계 AI 원문 교정 시 사용할 원문 스크립트를 입력하세요.\n\n1단계만 실행할 경우 비워둬도 됩니다.",
        key="original_script_input"
    )

    if original_script:
        st.session_state["original_script"] = original_script
        st.info(f"원문: {len(original_script)}자")

st.markdown("---")

# ============================================================
# 설정 영역
# ============================================================

st.subheader("⚙️ 생성 설정")

col_set1, col_set2, col_set3 = st.columns(3)

with col_set1:
    whisper_model = st.selectbox(
        "Whisper 모델",
        options=["tiny", "base", "small", "medium", "large", "large-v2", "large-v3"],
        index=2,  # small
        help="모델이 클수록 정확하지만 느림"
    )

with col_set2:
    SRT_STYLES = [
        "잘게", "기본",
        "시간 단위 (1초)", "시간 단위 (2초)", "시간 단위 (3초)",
        "시간 단위 (5초)", "시간 단위 (10초)", "시간 단위 (커스텀)",
    ]
    srt_style = st.selectbox(
        "SRT 스타일",
        options=SRT_STYLES,
        index=0,
        help=(
            "잘게/기본: 음성 인식(VAD) 기준 자동 분할 (동일 동작). "
            "시간 단위: 음성 인식 결과를 지정한 초 단위로 균등 분할합니다. "
            "단어/문장 경계는 보존되며, 실제 길이는 ±30% 오차가 있을 수 있습니다."
        )
    )

    # ⭐ 시간 단위 분할 목표 시간(초) 파싱
    target_sec = None
    if srt_style == "시간 단위 (커스텀)":
        target_sec = st.number_input(
            "목표 시간(초)",
            min_value=0.5,
            max_value=30.0,
            value=2.0,
            step=0.5,
            format="%.1f",
            help="0.5~30초 사이의 임의 값 (소수점 1자리). 각 세그먼트가 약 이 길이가 되도록 분할합니다."
        )
    elif srt_style.startswith("시간 단위"):
        # "시간 단위 (2초)" -> 2.0
        target_sec = float(srt_style.split("(")[1].split("초")[0])

with col_set3:
    language = st.selectbox(
        "언어",
        options=["ko", "en", "ja", "zh"],
        index=0,
        help="오디오의 언어"
    )

# ============================================================
# VAD 고급 설정 (v6.11)
# ============================================================

with st.expander("🎛️ 고급 설정: VAD (음성 활동 감지)", expanded=False):
    st.markdown("""
    **VAD 설정**으로 Whisper가 문장을 어떻게 분리할지 조정할 수 있습니다.
    기본값으로도 잘 작동하지만, 필요시 조정하세요.
    """)

    # 세션 상태 초기화 (기본값 설정)
    if "vad_threshold" not in st.session_state:
        st.session_state["vad_threshold"] = 0.05
    if "min_silence_ms" not in st.session_state:
        st.session_state["min_silence_ms"] = 50
    if "min_speech_ms" not in st.session_state:
        st.session_state["min_speech_ms"] = 30
    if "speech_pad_ms" not in st.session_state:
        st.session_state["speech_pad_ms"] = 30
    if "auto_enhance" not in st.session_state:
        st.session_state["auto_enhance"] = False

    col_vad1, col_vad2 = st.columns(2)

    with col_vad1:
        # 1. VAD 민감도
        vad_threshold = st.slider(
            "🎚️ VAD 민감도",
            min_value=0.01,
            max_value=0.5,
            value=st.session_state.get('vad_threshold', 0.05),
            step=0.01,
            key="vad_threshold_slider",
            help="""
**낮을수록 민감** (더 많은 음성 감지)

| 값 | 효과 |
|-----|------|
| 0.01~0.05 | 매우 민감 (조용한 음성도 감지) |
| 0.1~0.2 | 보통 |
| 0.3~0.5 | 둔감 (명확한 음성만) |

**권장: 0.05**
            """
        )
        st.session_state["vad_threshold"] = vad_threshold

        # 2. 무음 감지 최소 시간
        min_silence_ms = st.slider(
            "⏱️ 무음 감지 최소 시간 (ms)",
            min_value=30,
            max_value=500,
            value=st.session_state.get('min_silence_ms', 50),
            step=10,
            key="min_silence_slider",
            help="""
**문장 분리 기준이 되는 무음 길이** ⭐ 가장 큰 영향!

| 값 | 효과 | 예상 씬 수 |
|-----|------|----------|
| 30~50ms | 짧은 pause도 분리 | 300개↑ |
| 100~200ms | 보통 | 250~300개 |
| 300~500ms | 긴 pause만 분리 | 200개↓ |

**권장: 50ms**
            """
        )
        st.session_state["min_silence_ms"] = min_silence_ms

    with col_vad2:
        # 3. 음성 감지 최소 시간
        min_speech_ms = st.slider(
            "🎤 음성 감지 최소 시간 (ms)",
            min_value=10,
            max_value=200,
            value=st.session_state.get('min_speech_ms', 30),
            step=10,
            key="min_speech_slider",
            help="""
**음성으로 인식되는 최소 길이**

| 값 | 효과 |
|-----|------|
| 10~30ms | 짧은 발화도 감지 |
| 50~100ms | 보통 |
| 150~200ms | 긴 발화만 감지 |

**권장: 30ms**
            """
        )
        st.session_state["min_speech_ms"] = min_speech_ms

        # 4. 문장 패딩
        speech_pad_ms = st.slider(
            "📐 문장 앞뒤 패딩 (ms)",
            min_value=10,
            max_value=200,
            value=st.session_state.get('speech_pad_ms', 30),
            step=10,
            key="speech_pad_slider",
            help="""
**문장 시작/끝에 추가되는 여유 시간**

| 값 | 효과 |
|-----|------|
| 10~30ms | 타이트한 분리 |
| 50~100ms | 보통 |
| 150~200ms | 여유로운 분리 |

**권장: 30ms**
            """
        )
        st.session_state["speech_pad_ms"] = speech_pad_ms

    # 5. 오디오 향상 옵션
    auto_enhance = st.checkbox(
        "🔊 오디오 향상 (저볼륨 구간 증폭)",
        value=st.session_state.get('auto_enhance', False),
        key="auto_enhance_checkbox",
        help="""
**저볼륨 구간을 자동으로 증폭합니다.**

⚠️ **주의**: 활성화하면 VAD 정확도가 떨어질 수 있습니다!
- ✅ **권장: 비활성화** (기본값)
- 볼륨이 매우 낮은 오디오에서만 사용하세요.
        """
    )
    st.session_state["auto_enhance"] = auto_enhance

    # 설정 요약
    st.divider()
    st.markdown("**📊 현재 설정 요약:**")

    setting_col1, setting_col2, setting_col3 = st.columns(3)
    with setting_col1:
        st.metric("VAD 민감도", f"{vad_threshold}")
        st.metric("무음 감지", f"{min_silence_ms}ms")
    with setting_col2:
        st.metric("음성 감지", f"{min_speech_ms}ms")
        st.metric("패딩", f"{speech_pad_ms}ms")
    with setting_col3:
        st.metric("오디오 향상", "활성화" if auto_enhance else "비활성화")

        # 예상 씬 수 표시
        if min_silence_ms <= 50:
            expected = "300개↑"
        elif min_silence_ms <= 150:
            expected = "250~300개"
        else:
            expected = "200개↓"
        st.metric("예상 씬 수", expected)

    # 프리셋 버튼
    st.divider()
    st.markdown("**⚡ 빠른 설정 (프리셋):**")

    preset_col1, preset_col2, preset_col3 = st.columns(3)

    with preset_col1:
        if st.button("🔬 잘게 쪼개기", use_container_width=True, key="preset_fine"):
            st.session_state["vad_threshold"] = 0.03
            st.session_state["min_silence_ms"] = 30
            st.session_state["min_speech_ms"] = 20
            st.session_state["speech_pad_ms"] = 20
            st.session_state["auto_enhance"] = False
            st.rerun()

    with preset_col2:
        if st.button("⚖️ 기본값 (권장)", use_container_width=True, key="preset_default"):
            st.session_state["vad_threshold"] = 0.05
            st.session_state["min_silence_ms"] = 50
            st.session_state["min_speech_ms"] = 30
            st.session_state["speech_pad_ms"] = 30
            st.session_state["auto_enhance"] = False
            st.rerun()

    with preset_col3:
        if st.button("📦 크게 묶기", use_container_width=True, key="preset_coarse"):
            st.session_state["vad_threshold"] = 0.1
            st.session_state["min_silence_ms"] = 200
            st.session_state["min_speech_ms"] = 50
            st.session_state["speech_pad_ms"] = 100
            st.session_state["auto_enhance"] = False
            st.rerun()

    # 파라미터 영향 가이드
    with st.expander("📖 파라미터 영향 가이드", expanded=False):
        st.markdown("""
### 🎯 어떤 값을 조정하면 결과가 어떻게 바뀌나요?

#### 1. VAD 민감도 (threshold)
- **낮추면** (0.01~0.03): 작은 소리도 음성으로 인식 → 씬 수 증가
- **높이면** (0.2~0.5): 큰 소리만 음성으로 인식 → 씬 수 감소

#### 2. 무음 감지 최소 시간 (min_silence_duration_ms) ⭐ 가장 큰 영향!
- **낮추면** (30~50ms): 짧은 숨소리도 문장 경계 → 씬 많이 쪼개짐
- **높이면** (200~500ms): 긴 침묵만 문장 경계 → 씬 합쳐짐

#### 3. 음성 감지 최소 시간 (min_speech_duration_ms)
- **낮추면** (10~20ms): 짧은 "음", "어" 도 인식
- **높이면** (100~200ms): 긴 발화만 인식

#### 4. 문장 패딩 (speech_pad_ms)
- **낮추면** (10~20ms): 문장이 타이트하게 잘림
- **높이면** (100~200ms): 문장 앞뒤에 여유 시간 추가

#### 5. 오디오 향상 (auto_enhance_audio) ⚠️ 주의!
- **비활성화 (권장)**: VAD가 정확하게 작동
- **활성화**: 저볼륨 증폭 → VAD 정확도 저하 가능

---

### 📋 상황별 권장 설정

| 상황 | 민감도 | 무음 | 음성 | 패딩 | 향상 |
|------|--------|------|------|------|------|
| **일반 (권장)** | 0.05 | 50ms | 30ms | 30ms | ❌ |
| 빠른 말투 | 0.03 | 30ms | 20ms | 20ms | ❌ |
| 느린 말투 | 0.1 | 150ms | 50ms | 80ms | ❌ |
| 조용한 음성 | 0.02 | 50ms | 30ms | 30ms | ✅ |
| 배경 소음 많음 | 0.2 | 100ms | 50ms | 50ms | ❌ |
        """)

st.markdown("---")

# ============================================================
# 1단계: Whisper SRT 생성
# ============================================================

st.subheader("📌 1단계: Whisper SRT 생성")

st.markdown("""
> Whisper로 오디오를 분석하여 **정확한 타임스탬프**를 가진 SRT를 생성합니다.
> - 타임스탬프는 이 단계에서 확정됩니다.
> - 텍스트에 오타가 있을 수 있습니다 (예: "만들어갈요", "14조 조원").
""")

col_btn1, col_status1 = st.columns([1, 3])

with col_btn1:
    btn_whisper = st.button(
        "🎤 Whisper SRT 생성",
        type="primary",
        disabled=not GENERATOR_AVAILABLE or not audio_path,
        use_container_width=True
    )

with col_status1:
    if not GENERATOR_AVAILABLE:
        st.warning("HybridSRTGenerator를 사용할 수 없습니다.")
    elif not audio_path:
        st.info("오디오 파일을 선택하세요.")

# 1단계 실행
if btn_whisper and GENERATOR_AVAILABLE and audio_path:
    with st.spinner("🎤 Whisper SRT 생성 중..."):
        try:
            # VAD 설정 가져오기 (v6.11)
            vad_threshold_val = st.session_state.get('vad_threshold', 0.05)
            min_silence_ms_val = st.session_state.get('min_silence_ms', 50)
            min_speech_ms_val = st.session_state.get('min_speech_ms', 30)
            speech_pad_ms_val = st.session_state.get('speech_pad_ms', 30)
            auto_enhance_val = st.session_state.get('auto_enhance', False)

            # Generator 생성 (VAD 설정 전달)
            generator = get_hybrid_generator(
                whisper_model=whisper_model,
                vad_threshold=vad_threshold_val,
                min_speech_duration_ms=min_speech_ms_val,
                min_silence_duration_ms=min_silence_ms_val,
                speech_pad_ms=speech_pad_ms_val,
                auto_enhance_audio=auto_enhance_val
            )

            # 1단계: Whisper SRT 생성
            progress_bar = st.progress(0)
            status_text = st.empty()

            status_text.text("Whisper 모델 로딩 중...")
            progress_bar.progress(10)

            result = generator.generate_whisper_srt(
                audio_path=audio_path,
                style=srt_style,
                language=language,
                target_sec=target_sec
            )

            progress_bar.progress(100)
            status_text.text("완료!")

            if result.get("success"):
                st.session_state["whisper_srt_result"] = result
                st.success(f"✅ 1단계 완료! {len(result.get('scenes', []))}개 씬 생성됨")

                # 통계
                stats = result.get("stats", {})

                # ⭐ 시간 단위 분할 적용 시 추가 정보 표시
                ts = stats.get("time_split")
                if ts:
                    st.info(
                        f"⏱️ 시간분할 적용: target={ts['target_sec']:.1f}s · "
                        f"평균 {ts['avg_duration']:.1f}s · "
                        f"std {ts.get('std_duration', 0):.1f}s · "
                        f"세그먼트 {ts['segment_count']}개 "
                        f"(min {ts['min_duration']:.1f}s / max {ts['max_duration']:.1f}s)"
                    )
                col_s1, col_s2, col_s3 = st.columns(3)
                with col_s1:
                    st.metric("총 씬 수", f"{len(result.get('scenes', []))}개")
                with col_s2:
                    st.metric("총 길이", f"{stats.get('total_duration', 0):.1f}초")
                with col_s3:
                    st.metric("평균 길이", f"{stats.get('avg_duration', 0):.1f}초")

            else:
                st.error(f"1단계 실패: {result.get('error', '알 수 없는 오류')}")

        except Exception as e:
            st.error(f"오류 발생: {e}")
            import traceback
            st.code(traceback.format_exc())

# 1단계 결과 표시
if st.session_state.get("whisper_srt_result"):
    result = st.session_state["whisper_srt_result"]

    with st.expander("📄 1단계 결과 (Whisper SRT)", expanded=True):
        # SRT 미리보기
        srt_content = result.get("srt_content", "")

        col_preview, col_download = st.columns([3, 1])

        with col_preview:
            st.text_area(
                "SRT 내용 (처음 20개)",
                value="\n".join(srt_content.split("\n\n")[:20]),
                height=300,
                disabled=True
            )

        with col_download:
            # 다운로드 버튼
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            st.download_button(
                "📥 SRT 다운로드",
                data=srt_content,
                file_name=f"whisper_srt_{timestamp}.srt",
                mime="text/plain",
                use_container_width=True
            )

            # JSON도 다운로드
            scenes_json = json.dumps(result.get("scenes", []), ensure_ascii=False, indent=2)
            st.download_button(
                "📥 JSON 다운로드",
                data=scenes_json,
                file_name=f"whisper_scenes_{timestamp}.json",
                mime="application/json",
                use_container_width=True
            )

st.markdown("---")

# ============================================================
# 1.5단계: 씬 묶음 (순서 변경: 자막 줄바꿈보다 먼저!)
# ============================================================

st.subheader("🔗 1.5단계: 씬 묶음 (선택)")

# 건너뛰기 상태 표시
if st.session_state.get("skip_scene_merge"):
    st.info("⏭️ 이 단계는 **건너뛰기** 상태입니다.")
    if st.button("🔄 건너뛰기 취소 (씬 묶음)", key="cancel_skip_merge"):
        st.session_state["skip_scene_merge"] = False
        st.rerun()
    st.markdown("---")

st.markdown("""
> N개의 연속된 씬을 하나로 묶습니다.
> - 타임스탬프: 첫 씬 시작 ~ 마지막 씬 끝
> - 텍스트: 공백으로 연결
> - **원본 복원 가능**: 묶기 전 원본을 백업해 둡니다
""")

# 세션 상태 초기화
if "original_scenes_backup" not in st.session_state:
    st.session_state["original_scenes_backup"] = None

# 현재 씬 데이터 확인
whisper_result_for_merge = st.session_state.get('whisper_srt_result')
has_whisper_for_merge = whisper_result_for_merge and whisper_result_for_merge.get('scenes')

# 씬 묶음 설정
col_merge1, col_merge2, col_merge3 = st.columns([1, 1, 2])

with col_merge1:
    merge_count = st.selectbox(
        "묶을 씬 개수",
        options=[1, 2, 3, 4, 5],
        index=1,  # 기본값 2
        help="N개의 연속된 씬을 하나로 묶습니다. 1 선택 시 변경 없음.",
        key='scene_merge_count'
    )

with col_merge2:
    # 미리보기 정보
    if has_whisper_for_merge:
        from utils.scene_merger_simple import get_merge_preview
        current_scenes = whisper_result_for_merge.get('scenes', [])
        preview = get_merge_preview(current_scenes, merge_count)

        st.metric(
            "결과 미리보기",
            f"{preview['merged_count']}개 씬",
            delta=f"-{preview['reduction_percent']}%" if preview['reduction_percent'] > 0 else None,
            delta_color="normal"
        )
    else:
        st.metric("결과 미리보기", "-")

with col_merge3:
    # 현재 상태 표시
    if has_whisper_for_merge:
        current_count = len(whisper_result_for_merge.get('scenes', []))
        backup_exists = st.session_state.get("original_scenes_backup") is not None

        if backup_exists:
            backup_count = len(st.session_state["original_scenes_backup"])
            st.info(f"📊 현재: {current_count}개 씬 | 백업: {backup_count}개 씬")
        else:
            st.info(f"📊 현재: {current_count}개 씬")

# 버튼 영역 (건너뛰기 포함)
if not st.session_state.get("skip_scene_merge"):
    col_merge_btn1, col_merge_btn2, col_merge_btn3, col_merge_status = st.columns([1, 1, 1, 1])

    with col_merge_btn1:
        btn_merge = st.button(
            "🔗 씬 묶기",
            disabled=not has_whisper_for_merge or merge_count == 1,
            use_container_width=True
        )

    with col_merge_btn2:
        btn_restore = st.button(
            "↩️ 원본 복원",
            disabled=not st.session_state.get("original_scenes_backup"),
            use_container_width=True
        )

    with col_merge_btn3:
        btn_skip_merge = st.button(
            "⏭️ 건너뛰기",
            disabled=not has_whisper_for_merge,
            use_container_width=True,
            key="btn_skip_merge"
        )

    with col_merge_status:
        if not has_whisper_for_merge:
            st.info("먼저 1단계를 실행하세요.")
        elif merge_count == 1:
            st.info("묶을 개수를 2 이상으로 선택하세요.")
        elif has_whisper_for_merge:
            st.success("씬 묶기 준비 완료!")

    # 건너뛰기 처리
    if btn_skip_merge and has_whisper_for_merge:
        st.session_state["skip_scene_merge"] = True
        st.success("⏭️ 씬 묶음 단계를 건너뛰었습니다.")
        st.rerun()

    # 씬 묶기 실행
    if btn_merge and has_whisper_for_merge and merge_count > 1:
        try:
            import copy
            from utils.scene_merger_simple import merge_scenes_by_count

            current_scenes = whisper_result_for_merge.get('scenes', [])

            # 원본 백업 (아직 백업이 없으면)
            if st.session_state.get("original_scenes_backup") is None:
                st.session_state["original_scenes_backup"] = copy.deepcopy(current_scenes)
                print(f"[씬묶음] 원본 백업 완료: {len(current_scenes)}개 씬")

            # 씬 묶기 실행
            merged_scenes = merge_scenes_by_count(current_scenes, merge_count)

            # 결과 저장
            st.session_state['whisper_srt_result']['scenes'] = merged_scenes

            # 결과 표시
            original_count = len(current_scenes)
            merged_count = len(merged_scenes)
            reduction = round((1 - merged_count / original_count) * 100, 1)

            st.success(f"✅ 씬 묶기 완료! {original_count}개 → {merged_count}개 ({reduction}% 감소)")

            # 묶인 씬 미리보기
            with st.expander(f"📝 묶인 씬 미리보기 (처음 5개)", expanded=True):
                for scene in merged_scenes[:5]:
                    scene_id = scene.get('scene_id', '?')
                    text = scene.get('text', '')[:100]
                    merged_from = scene.get('_merged_from', [])

                    st.markdown(f"**씬 {scene_id}** (원본: {merged_from})")
                    st.code(text + ('...' if len(scene.get('text', '')) > 100 else ''), language=None)

        except Exception as e:
            st.error(f"❌ 씬 묶기 오류: {e}")
            import traceback
            st.code(traceback.format_exc())

    # 원본 복원 실행
    if btn_restore and st.session_state.get("original_scenes_backup"):
        try:
            import copy

            backup_scenes = copy.deepcopy(st.session_state["original_scenes_backup"])
            st.session_state['whisper_srt_result']['scenes'] = backup_scenes

            # 백업 초기화 (다시 묶을 수 있도록)
            st.session_state["original_scenes_backup"] = None

            st.success(f"✅ 원본 복원 완료! {len(backup_scenes)}개 씬으로 복원됨")
            st.rerun()

        except Exception as e:
            st.error(f"❌ 복원 오류: {e}")
            import traceback
            st.code(traceback.format_exc())

# ⭐ 1.5단계 다운로드 버튼
if has_whisper_for_merge:
    with st.expander("📥 1.5단계 결과 다운로드", expanded=False):
        merge_scenes = whisper_result_for_merge.get('scenes', [])

        # SRT 생성
        def _generate_srt_for_step(scene_list):
            def to_srt_time(seconds):
                if seconds is None or seconds < 0:
                    seconds = 0
                h = int(seconds // 3600)
                m = int((seconds % 3600) // 60)
                s = int(seconds % 60)
                ms = int((seconds % 1) * 1000)
                return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

            srt_blocks = []
            for i, scene in enumerate(scene_list, 1):
                start_time = scene.get('start_time', scene.get('start', 0))
                end_time = scene.get('end_time', scene.get('end', 0))
                timecode = f"{to_srt_time(start_time)} --> {to_srt_time(end_time)}"
                text = scene.get('text', '')
                srt_blocks.append(f"{i}\n{timecode}\n{text}")
            return "\n\n".join(srt_blocks)

        merge_srt_content = _generate_srt_for_step(merge_scenes)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        col_dl1, col_dl2 = st.columns(2)
        with col_dl1:
            st.download_button(
                "📥 SRT 다운로드 (씬 묶음 후)",
                data=merge_srt_content,
                file_name=f"step1.5_merged_{timestamp}.srt",
                mime="text/plain",
                use_container_width=True
            )
        with col_dl2:
            merge_json = json.dumps(merge_scenes, ensure_ascii=False, indent=2)
            st.download_button(
                "📥 JSON 다운로드 (씬 묶음 후)",
                data=merge_json,
                file_name=f"step1.5_merged_{timestamp}.json",
                mime="application/json",
                use_container_width=True
            )

st.markdown("---")

# ============================================================
# 1.7단계: 자막 줄바꿈 (순서 변경: 씬 묶음 이후!)
# ============================================================

st.subheader("📏 1.7단계: 자막 줄바꿈 (선택)")

# 건너뛰기 상태 표시
if st.session_state.get("skip_line_wrap"):
    st.info("⏭️ 이 단계는 **건너뛰기** 상태입니다.")
    if st.button("🔄 건너뛰기 취소 (자막 줄바꿈)", key="cancel_skip_wrap"):
        st.session_state["skip_line_wrap"] = False
        st.rerun()
    st.markdown("---")

st.markdown("""
> 한 줄이 너무 길면 읽기 어렵습니다.
> - 지정된 글자수(기본 43자)를 초과하면 자동으로 줄바꿈합니다
> - **단어가 잘리지 않도록** 단어 경계에서 줄바꿈합니다
""")

# 줄바꿈 설정
col_wrap1, col_wrap2 = st.columns([1, 2])

with col_wrap1:
    max_chars = st.number_input(
        "한 줄 최대 글자수",
        min_value=20,
        max_value=100,
        value=43,
        step=1,
        help="공백 포함. 이 글자수를 초과하면 줄바꿈됩니다. 일반적으로 40~45자가 적당합니다.",
        key='subtitle_max_chars'
    )

with col_wrap2:
    # 미리보기 예시
    example_text = "그리고 7 시리즈 같은 최상의 모델에는 더 강력한 B920이 들어갈 거라는 얘기도 있어요."
    st.caption(f"예시 ({len(example_text)}자):")

    from utils.subtitle_formatter import SubtitleFormatter
    formatter_preview = SubtitleFormatter(max_chars=max_chars)
    wrapped_example = formatter_preview.wrap_text(example_text)
    st.code(wrapped_example, language=None)

# 줄바꿈 필요 통계
whisper_result_for_wrap = st.session_state.get('whisper_srt_result')
has_whisper_for_wrap = whisper_result_for_wrap and whisper_result_for_wrap.get('scenes')

if has_whisper_for_wrap:
    scenes_for_stats = whisper_result_for_wrap.get('scenes', [])
    need_wrap_count = sum(1 for s in scenes_for_stats if len(s.get('text', '')) > max_chars)
    already_wrapped = sum(1 for s in scenes_for_stats if '\n' in s.get('text', ''))

    if need_wrap_count > 0:
        st.info(f"📊 **{need_wrap_count}개** 자막이 {max_chars}자를 초과합니다. (이미 줄바꿈: {already_wrapped}개)")

# 줄바꿈 실행 버튼 (건너뛰기 포함)
if not st.session_state.get("skip_line_wrap"):
    col_wrap_btn, col_wrap_btn2, col_wrap_status = st.columns([1, 1, 2])

    with col_wrap_btn:
        btn_wrap = st.button(
            "📏 자막 줄바꿈 적용",
            disabled=not has_whisper_for_wrap,
            use_container_width=True
        )

    with col_wrap_btn2:
        btn_skip_wrap = st.button(
            "⏭️ 건너뛰기",
            disabled=not has_whisper_for_wrap,
            use_container_width=True,
            key="btn_skip_wrap"
        )

    with col_wrap_status:
        if not has_whisper_for_wrap:
            st.info("먼저 1단계를 실행하세요.")
        elif has_whisper_for_wrap:
            st.success("줄바꿈 준비 완료!")

    # 건너뛰기 처리
    if btn_skip_wrap and has_whisper_for_wrap:
        st.session_state["skip_line_wrap"] = True
        st.success("⏭️ 자막 줄바꿈 단계를 건너뛰었습니다.")
        st.rerun()
else:
    btn_wrap = False  # 건너뛴 경우 실행 안 함

# 줄바꿈 실행
if btn_wrap and has_whisper_for_wrap:
    try:
        import copy
        scenes_to_wrap = copy.deepcopy(whisper_result_for_wrap.get('scenes', []))

        if not scenes_to_wrap:
            st.error("Whisper 결과가 없습니다.")
            st.stop()

        # 줄바꿈 적용
        formatter = SubtitleFormatter(max_chars=max_chars)
        formatted_scenes = formatter.format_scenes(scenes_to_wrap)

        # 결과 저장 (세션에)
        st.session_state['whisper_srt_result']['scenes'] = formatted_scenes

        # 줄바꿈된 씬 수 계산
        wrapped_count = sum(1 for s in formatted_scenes if '\n' in s.get('text', ''))

        st.success(f"✅ 자막 줄바꿈 완료! **{wrapped_count}개** 자막이 줄바꿈되었습니다.")

        # 줄바꿈된 예시 보여주기
        if wrapped_count > 0:
            with st.expander(f"📝 줄바꿈 결과 미리보기 ({wrapped_count}개)", expanded=True):
                display_count = 0
                for scene in formatted_scenes:
                    if '\n' in scene.get('text', ''):
                        scene_id = scene.get('scene_id', '?')
                        text = scene.get('text', '')
                        st.markdown(f"**씬 {scene_id}** ({len(text.replace(chr(10), ''))}자)")
                        st.code(text, language=None)
                        display_count += 1
                        if display_count >= 10:
                            break

                if wrapped_count > 10:
                    st.info(f"... 외 {wrapped_count - 10}개")

    except Exception as e:
        st.error(f"❌ 줄바꿈 오류: {e}")
        import traceback
        st.code(traceback.format_exc())

# ⭐ 1.7단계 다운로드 버튼
if has_whisper_for_wrap:
    with st.expander("📥 1.7단계 결과 다운로드", expanded=False):
        wrap_scenes = whisper_result_for_wrap.get('scenes', [])

        # SRT 생성 함수 (재사용)
        def _generate_srt_for_wrap(scene_list):
            def to_srt_time(seconds):
                if seconds is None or seconds < 0:
                    seconds = 0
                h = int(seconds // 3600)
                m = int((seconds % 3600) // 60)
                s = int(seconds % 60)
                ms = int((seconds % 1) * 1000)
                return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

            srt_blocks = []
            for i, scene in enumerate(scene_list, 1):
                start_time = scene.get('start_time', scene.get('start', 0))
                end_time = scene.get('end_time', scene.get('end', 0))
                timecode = f"{to_srt_time(start_time)} --> {to_srt_time(end_time)}"
                text = scene.get('text', '')
                srt_blocks.append(f"{i}\n{timecode}\n{text}")
            return "\n\n".join(srt_blocks)

        wrap_srt_content = _generate_srt_for_wrap(wrap_scenes)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        col_dl1, col_dl2 = st.columns(2)
        with col_dl1:
            st.download_button(
                "📥 SRT 다운로드 (줄바꿈 후)",
                data=wrap_srt_content,
                file_name=f"step1.7_wrapped_{timestamp}.srt",
                mime="text/plain",
                use_container_width=True,
                key="download_wrap_srt"
            )
        with col_dl2:
            wrap_json = json.dumps(wrap_scenes, ensure_ascii=False, indent=2)
            st.download_button(
                "📥 JSON 다운로드 (줄바꿈 후)",
                data=wrap_json,
                file_name=f"step1.7_wrapped_{timestamp}.json",
                mime="application/json",
                use_container_width=True,
                key="download_wrap_json"
            )

st.markdown("---")

# ============================================================
# 2단계: AI 원문 교정
# ============================================================

st.subheader("📌 2단계: AI 원문 교정 (선택)")

st.markdown("""
> 원문 스크립트를 기준으로 Whisper SRT의 **텍스트만** 교정합니다.
> - **타임스탬프는 절대 변경되지 않습니다!**
> - 오타 교정: "만들어갈요" → "만들어요", "14조 조원" → "14조원"
""")

# ============================================================
# AI 모델 선택 섹션
# ============================================================

st.markdown("#### 🤖 AI 모델 선택")

col_ai1, col_ai2 = st.columns(2)

with col_ai1:
    # Provider 선택 (Google vs Anthropic)
    provider_options = list(AI_MODELS.keys())
    provider_names = [AI_MODELS[p]['name'] for p in provider_options]

    # 현재 선택된 provider 인덱스 (⭐ v4.0: 기본값 Claude!)
    current_provider = st.session_state.get("ai_correction_provider", "anthropic")
    current_provider_idx = provider_options.index(current_provider) if current_provider in provider_options else 0

    selected_provider_idx = st.selectbox(
        "AI 제공자",
        range(len(provider_options)),
        format_func=lambda i: provider_names[i],
        index=current_provider_idx,
        key="ai_provider_select"
    )

    selected_provider = provider_options[selected_provider_idx]
    st.session_state["ai_correction_provider"] = selected_provider

with col_ai2:
    # 모델 선택 (선택된 Provider에 따라)
    available_models = AI_MODELS[selected_provider]['models']
    model_ids = [m['id'] for m in available_models]
    model_names = [m['name'] for m in available_models]

    # 현재 선택된 모델이 해당 provider에 있는지 확인
    current_model = st.session_state.get("ai_correction_model", "")
    if current_model in model_ids:
        default_idx = model_ids.index(current_model)
    else:
        # 기본 모델 찾기
        default_idx = next((i for i, m in enumerate(available_models) if m.get('default')), 0)

    selected_model_idx = st.selectbox(
        "모델",
        range(len(model_ids)),
        format_func=lambda i: model_names[i],
        index=default_idx,
        key="ai_model_select"
    )

    selected_model = model_ids[selected_model_idx]
    st.session_state["ai_correction_model"] = selected_model

# ⭐ v4.0: 선택된 모델 정보 + 속도 안내
if selected_provider == 'anthropic':
    st.success(f"⚡ **Claude** 선택됨 - {model_names[selected_model_idx]} | Rate Limit 없음, ~40초 완료!")
else:
    st.warning(f"🐢 **Gemini** 선택됨 - {model_names[selected_model_idx]} | Rate Limit 있음, ~2분 이상 소요")

# 2단계 활성화 조건 (중복 실행 방지 포함)
can_run_stage2 = (
    GENERATOR_AVAILABLE and
    st.session_state.get("whisper_srt_result") and
    st.session_state.get("original_script") and
    not st.session_state.get("ai_correction_running", False)
)

col_btn2, col_status2 = st.columns([1, 3])

with col_btn2:
    btn_ai_correct = st.button(
        "🤖 AI 원문 교정",
        type="secondary",
        disabled=not can_run_stage2,
        use_container_width=True
    )

with col_status2:
    if st.session_state.get("ai_correction_running"):
        st.warning("⏳ AI 교정 실행 중... 잠시 기다려주세요.")
    elif not st.session_state.get("whisper_srt_result"):
        st.info("먼저 1단계를 실행하세요.")
    elif not st.session_state.get("original_script"):
        st.info("원문 스크립트를 입력하세요.")
    elif can_run_stage2:
        st.success("2단계 준비 완료!")

# 2단계 실행
if btn_ai_correct and can_run_stage2:
    # ⭐ 중복 실행 방지
    st.session_state["ai_correction_running"] = True

    # 선택된 provider와 model 가져오기 (⭐ v4.0: 기본값 Claude!)
    ai_provider = st.session_state.get("ai_correction_provider", "anthropic")
    ai_model = st.session_state.get("ai_correction_model", "claude-3-5-sonnet-20241022")
    model_display_name = f"{AI_MODELS[ai_provider]['name']} - {ai_model}"

    # 2단계: AI 원문 교정
    progress_bar = st.progress(0)
    status_text = st.empty()

    try:
        status_text.text(f"AI 원문 교정 준비 중... ({ai_model})")
        progress_bar.progress(10)

        # BUG FIX: session state의 scenes를 우선 사용 (1.5/1.7단계 결과 반영)
        # 이전 코드는 json_path 파일에서 로드하여 1.5/1.7단계 결과가 소실되었음
        whisper_result = st.session_state["whisper_srt_result"]
        import copy
        scenes = copy.deepcopy(whisper_result.get("scenes", []))

        if not scenes:
            # session state에 scenes가 없을 때만 JSON 파일 폴백
            json_path = whisper_result.get('json_path')
            if json_path and os.path.exists(json_path):
                with open(json_path, 'r', encoding='utf-8') as f:
                    scenes = json.load(f)
                print(f"[SRT생성] JSON 파일에서 폴백 로드: {len(scenes)}개 씬")
        else:
            print(f"[SRT생성] 세션에서 로드: {len(scenes)}개 씬 (1.5/1.7단계 결과 포함)")

        original = st.session_state["original_script"]

        if not scenes:
            st.error("Whisper 결과가 없습니다. 1단계를 먼저 실행하세요.")
            st.session_state["ai_correction_running"] = False
            st.stop()

        status_text.text(f"AI 교정기 초기화 중...")
        progress_bar.progress(20)

        # AIOriginalCorrector 직접 사용 (선택된 provider/model)
        from utils.ai_original_corrector import AIOriginalCorrector

        corrector = AIOriginalCorrector(
            provider=ai_provider,
            model=ai_model
        )

        # ⭐ 진행률 콜백
        def update_progress(progress, message):
            # 20~90% 범위로 매핑
            mapped = 0.2 + progress * 0.7
            progress_bar.progress(mapped)
            status_text.text(message)

        status_text.text(f"AI 원문 교정 중... (배치 크기: 150, v4.0 속도 최적화)")
        progress_bar.progress(25)

        # BUG FIX: 1.7단계 줄바꿈 보존 - 교정 전 줄바꿈 맵 저장
        had_linebreaks = {
            s.get('scene_id'): True
            for s in scenes
            if '\n' in s.get('text', '')
        }

        # AI 원문 교정 실행 (v4.0: 배치 크기 150, Claude 최적화)
        corrected_scenes, corrections = corrector.correct_with_original(
            scenes=scenes,
            original_script=original,
            progress_callback=update_progress
        )

        # BUG FIX: 1.7단계 줄바꿈이 2단계 교정 후에도 유지되도록 후처리
        if had_linebreaks:
            max_chars_val = st.session_state.get('subtitle_max_chars', 43)
            from utils.subtitle_formatter import SubtitleFormatter as _SF
            _fmt = _SF(max_chars=max_chars_val)
            restored_count = 0
            for sc in corrected_scenes:
                sid = sc.get('scene_id')
                text = sc.get('text', '')
                if sid in had_linebreaks and '\n' not in text and len(text) > max_chars_val:
                    sc['text'] = _fmt.wrap_text(text)
                    restored_count += 1
            if restored_count > 0:
                print(f"[SRT생성] 줄바꿈 복원: {restored_count}개 씬")

        progress_bar.progress(90)

        # SRT 내용 생성
        def to_srt_time(seconds):
            """초를 SRT 타임스탬프로 변환"""
            if seconds is None or seconds < 0:
                seconds = 0
            h = int(seconds // 3600)
            m = int((seconds % 3600) // 60)
            s = int(seconds % 60)
            ms = int((seconds % 1) * 1000)
            return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

        def get_scene_timestamp(scene, prefix):
            """
            씬에서 타임스탬프 추출 (다양한 키 지원)

            Args:
                scene: 씬 딕셔너리
                prefix: 'start' 또는 'end'

            Returns:
                SRT 타임스탬프 문자열
            """
            # 1순위: start_time / end_time (초 단위 float)
            ts = scene.get(f'{prefix}_time')
            if ts is not None and isinstance(ts, (int, float)) and ts >= 0:
                return to_srt_time(float(ts))

            # 2순위: start / end (초 단위 float)
            ts = scene.get(prefix)
            if ts is not None and isinstance(ts, (int, float)) and ts >= 0:
                return to_srt_time(float(ts))

            # 3순위: start_sec / end_sec
            ts = scene.get(f'{prefix}_sec')
            if ts is not None and isinstance(ts, (int, float)) and ts >= 0:
                return to_srt_time(float(ts))

            return '00:00:00,000'

        def generate_srt_from_scenes(scene_list):
            """씬 리스트를 SRT 문자열로 변환"""
            srt_blocks = []

            # 디버깅: 첫 번째 씬 구조 확인
            if scene_list:
                sample = scene_list[0]
                print(f"[SRT생성] 첫 번째 씬 키: {list(sample.keys())}")
                print(f"[SRT생성] timecode: {sample.get('timecode')}")
                print(f"[SRT생성] start_time: {sample.get('start_time')}")
                print(f"[SRT생성] end_time: {sample.get('end_time')}")

            for i, scene in enumerate(scene_list, 1):
                # 1순위: timecode 필드 (이미 포맷된 문자열)
                timecode = scene.get('timecode', '')

                # timecode가 없거나 유효하지 않으면 직접 생성
                if not timecode or '-->' not in timecode:
                    start_ts = get_scene_timestamp(scene, 'start')
                    end_ts = get_scene_timestamp(scene, 'end')
                    timecode = f"{start_ts} --> {end_ts}"

                text = scene.get('text', '')
                srt_blocks.append(f"{i}\n{timecode}\n{text}")

            return "\n\n".join(srt_blocks)

        srt_content = generate_srt_from_scenes(corrected_scenes)

        progress_bar.progress(100)
        status_text.text("완료!")

        # 결과 저장
        result = {
            'success': True,
            'scenes': corrected_scenes,
            'srt_content': srt_content,
            'corrections': corrections,
            'model_used': f"{ai_provider}/{ai_model}",
            'stats': {
                'total_scenes': len(corrected_scenes),
                'corrected_scenes': len(corrections)
            }
        }

        st.session_state["ai_corrected_result"] = result
        st.success(f"✅ 2단계 완료! {len(corrections)}개 교정됨 (모델: {ai_model})")

        # 교정 내역
        if corrections:
            st.markdown("**교정 내역:**")
            for c in corrections[:10]:
                before_short = c['before'][:30] + '...' if len(c['before']) > 30 else c['before']
                after_short = c['after'][:30] + '...' if len(c['after']) > 30 else c['after']
                st.markdown(f"- 씬 {c['scene_id']}: `{before_short}` → `{after_short}`")

        if len(corrections) > 10:
            st.info(f"... 외 {len(corrections) - 10}개")

    except Exception as e:
        st.error(f"오류 발생: {e}")
        import traceback
        st.code(traceback.format_exc())

    finally:
        # ⭐ 실행 완료 플래그 해제
        st.session_state["ai_correction_running"] = False

# 2단계 결과 표시
if st.session_state.get("ai_corrected_result"):
    result = st.session_state["ai_corrected_result"]

    with st.expander("📄 2단계 결과 (AI 교정된 SRT)", expanded=True):
        # 사용된 모델 표시
        model_used = result.get("model_used", "unknown")
        st.caption(f"🤖 사용된 모델: {model_used}")

        # SRT 미리보기
        srt_content = result.get("srt_content", "")

        col_preview, col_download = st.columns([3, 1])

        with col_preview:
            st.text_area(
                "교정된 SRT 내용 (처음 20개)",
                value="\n".join(srt_content.split("\n\n")[:20]),
                height=300,
                disabled=True
            )

        with col_download:
            # 다운로드 버튼
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            st.download_button(
                "📥 교정된 SRT 다운로드",
                data=srt_content,
                file_name=f"corrected_srt_{timestamp}.srt",
                mime="text/plain",
                use_container_width=True,
                type="primary"
            )

            # JSON도 다운로드
            scenes_json = json.dumps(result.get("scenes", []), ensure_ascii=False, indent=2)
            st.download_button(
                "📥 교정된 JSON 다운로드",
                data=scenes_json,
                file_name=f"corrected_scenes_{timestamp}.json",
                mime="application/json",
                use_container_width=True
            )

st.markdown("---")

# ============================================================
# 비교 영역
# ============================================================

if st.session_state.get("whisper_srt_result") and st.session_state.get("ai_corrected_result"):
    st.subheader("📊 1단계 vs 2단계 비교")

    col_compare1, col_compare2 = st.columns(2)

    with col_compare1:
        st.markdown("**1단계 (Whisper 원본)**")
        whisper_scenes = st.session_state["whisper_srt_result"].get("scenes", [])[:5]
        for scene in whisper_scenes:
            st.markdown(f"- [{scene.get('scene_id')}] {scene.get('text', '')[:50]}...")

    with col_compare2:
        st.markdown("**2단계 (AI 교정)**")
        corrected_scenes = st.session_state["ai_corrected_result"].get("scenes", [])[:5]
        for scene in corrected_scenes:
            st.markdown(f"- [{scene.get('scene_id')}] {scene.get('text', '')[:50]}...")

# ============================================================
# 초기화 버튼
# ============================================================

st.markdown("---")

if st.button("🔄 초기화", use_container_width=False):
    st.session_state["whisper_srt_result"] = None
    st.session_state["ai_corrected_result"] = None
    st.session_state["original_script"] = ""
    st.session_state["original_scenes_backup"] = None  # 씬 묶음 백업도 초기화
    st.session_state["skip_scene_merge"] = False  # 건너뛰기 상태 초기화
    st.session_state["skip_line_wrap"] = False  # 건너뛰기 상태 초기화
    st.rerun()
