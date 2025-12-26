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
import tempfile
import io
from pathlib import Path

# 경로 설정
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# TTS 유틸리티 임포트
from utils.tts_utils import (
    split_text_for_tts,
    get_preview_text,
    validate_chunk_duration,
    merge_chunk_results
)

# 오디오 정규화 유틸리티 임포트
from utils.audio_normalize import (
    normalize_audio_full,
    normalize_scenes_batch,
    normalize_scenes_perfect,
    analyze_audio
)

# 병렬 처리 모듈 임포트
from utils.chatterbox_async import (
    run_parallel_generation,
    run_threaded_generation
)

# 순차 처리 + 청크 분할 유틸리티 (타임아웃 방지)
from utils.chatterbox_utils import (
    generate_scenes_sequential_safe,
    generate_scenes_with_chunking,
    generate_with_chunking
)

# 정밀 정규화 (±3% 편차 목표)
from utils.audio_normalize_v2 import (
    AudioNormalizer,
    normalize_scenes_v2,
    analyze_scenes_stats
)

# 강제 정규화 (반드시 실행, ±5% 편차 목표, 속도 방향 수정됨!)
from utils.audio_normalizer_forced import (
    ForcedAudioNormalizer,
    normalize_scenes_forced,
    analyze_normalization_stats
)

# 완벽 정규화 (3-Pass, ±1% 편차 목표)
from utils.audio_perfect_normalizer import (
    PerfectAudioNormalizer,
    normalize_perfect
)

# 구간별 속도 정규화 (씬 내 발화속도 가속 문제 해결)
from utils.audio_segment_normalizer import (
    SegmentSpeedNormalizer,
    normalize_segments_all
)

# 발화속도 가속 보정 (뒤로 갈수록 빨라지는 문제 해결)
from utils.audio_speed_corrector import (
    SpeedAccelerationCorrector,
    correct_all_speed_acceleration
)

# ⭐ 통합 단일 패스 처리기 (FFmpeg 1회만 호출 → 울림/변조 방지)
from utils.audio_unified_processor import (
    UnifiedAudioProcessor,
    process_all_unified
)

# ⭐ 참조 음성 분석기 v2.0 (텍스트 기반 정확 측정 + 파라미터 자동 추천)
from utils.voice_analyzer import (
    VoiceAnalyzer,
    analyze_voice_and_get_params,
    analyze_voice_with_text,
    get_voice_transcript,
    set_voice_transcript,
    get_profile_manager,
    optimize_voice_for_cloning  # ⭐ 참조 음성 최적화 (15~30초 추출)
)

# ⭐ TTS 자연스러움 최적화 (temperature/repetition_penalty 조정)
from utils.tts_naturalness import (
    get_natural_params,
    get_base_natural_params,
    TTSNaturalnessOptimizer
)

# 직접 생성기 (청크 분할 없음 - 속도 최적화)
from utils.tts_direct_generator import (
    generate_scene_direct,
    generate_all_scenes_direct,
    generate_with_smart_chunking
)

# 병렬 생성기 (40% 속도 향상)
from utils.tts_parallel_generator import (
    generate_scenes_parallel,
    ParallelTTSGenerator
)

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

# 서버 상태 캐시 TTL (초)
CHATTERBOX_CACHE_TTL = 10


def check_chatterbox_server(force_refresh=False):
    """
    Chatterbox 서버 연결 확인 (캐싱 적용)
    - 캐시된 결과가 있으면 즉시 반환 (TTL 내)
    - force_refresh=True로 강제 새로고침 가능
    """
    cache_key = "chatterbox_server_status"
    cache_time_key = "chatterbox_server_status_time"

    # 캐시 확인
    if not force_refresh:
        cached_status = st.session_state.get(cache_key)
        cached_time = st.session_state.get(cache_time_key, 0)

        if cached_status is not None and (time.time() - cached_time) < CHATTERBOX_CACHE_TTL:
            return cached_status

    # 실제 서버 확인
    try:
        r = requests.get(f"{CHATTERBOX_URL}/health", timeout=2)
        status = r.status_code == 200
    except:
        status = False

    # 캐시 저장
    st.session_state[cache_key] = status
    st.session_state[cache_time_key] = time.time()

    return status


def get_chatterbox_status(force_refresh=False):
    """
    Chatterbox 서버 상태 조회 (캐싱 적용)
    - 캐시된 결과가 있으면 즉시 반환 (TTL 내)
    - force_refresh=True로 강제 새로고침 가능
    """
    cache_key = "chatterbox_model_status"
    cache_time_key = "chatterbox_model_status_time"

    # 캐시 확인
    if not force_refresh:
        cached_status = st.session_state.get(cache_key)
        cached_time = st.session_state.get(cache_time_key, 0)

        if cached_status is not None and (time.time() - cached_time) < CHATTERBOX_CACHE_TTL:
            return cached_status

    # 실제 상태 조회
    try:
        r = requests.get(f"{CHATTERBOX_URL}/status", timeout=3)
        if r.status_code == 200:
            status = r.json()
        else:
            status = None
    except:
        status = None

    # 캐시 저장
    st.session_state[cache_key] = status
    st.session_state[cache_time_key] = time.time()

    return status


def invalidate_chatterbox_cache():
    """Chatterbox 캐시 무효화"""
    for key in ["chatterbox_server_status", "chatterbox_server_status_time",
                "chatterbox_model_status", "chatterbox_model_status_time"]:
        if key in st.session_state:
            del st.session_state[key]


def get_voice_files():
    """음성 라이브러리 파일 목록"""
    voice_dir = Path("voice_library/ko")
    if voice_dir.exists():
        files = list(voice_dir.glob("*.mp3")) + list(voice_dir.glob("*.wav"))
        return [f.name for f in files]
    return []


# ============================================================
# Chatterbox 청크 분할 생성 함수
# ============================================================

def render_chatterbox_generation_options():
    """
    Chatterbox 생성 옵션 UI (프리뷰/전체 모드, 청크 설정)

    Returns:
        dict: 생성 옵션 {mode, preview_length, chunk_size, repetition_penalty}
    """
    st.markdown("#### 🎯 생성 모드")

    col1, col2 = st.columns(2)

    with col1:
        generation_mode = st.radio(
            "모드 선택",
            ["🎬 전체 생성 (권장)", "👁️ 프리뷰 (빠른 확인)"],
            key="chatterbox_generation_mode_option",
            help="""
• 전체 생성: 텍스트 전체를 음성으로 변환
• 프리뷰: 처음 50자만 빠르게 생성하여 음색 확인
            """
        )

    preview_length = 50
    with col2:
        if "프리뷰" in generation_mode:
            preview_length = st.slider(
                "프리뷰 길이 (글자)",
                min_value=30,
                max_value=100,
                value=50,
                step=10,
                key="chatter_preview_length"
            )
            st.info(f"💡 처음 {preview_length}자만 생성합니다.")
        else:
            st.success("✅ 전체 텍스트를 생성합니다.")

    # 고급 옵션 (접힘)
    with st.expander("⚙️ 고급 생성 옵션 (텍스트 잘림 방지)"):
        st.caption("긴 텍스트가 중간에 잘리는 문제가 있다면 아래 설정을 조정하세요.")

        col_a, col_b = st.columns(2)

        with col_a:
            chunk_size = st.slider(
                "청크 크기 (글자)",
                min_value=40,
                max_value=150,
                value=st.session_state.get("chatter_chunk_size", 80),
                step=10,
                key="chatter_chunk_size_slider",
                help="긴 텍스트를 이 크기로 나눠서 생성합니다. 작을수록 안정적이지만 느립니다."
            )
            st.session_state["chatter_chunk_size"] = chunk_size

        with col_b:
            repetition_penalty = st.slider(
                "반복 억제 강도",
                min_value=1.0,
                max_value=2.0,
                value=st.session_state.get("chatter_rep_penalty", 1.2),  # ⭐ 1.4→1.2 자연스러움 최적화
                step=0.1,
                key="chatter_rep_penalty_slider",
                help="낮을수록 자연스러움. 1.2 권장 (기존 1.4는 딱딱함)"
            )
            st.session_state["chatter_rep_penalty"] = repetition_penalty

        col_c, col_d = st.columns(2)

        with col_c:
            max_retries = st.number_input(
                "최대 재시도 횟수",
                min_value=1,
                max_value=5,
                value=st.session_state.get("chatter_max_retries", 3),
                key="chatter_max_retries_input",
                help="잘림 감지 시 재시도 횟수"
            )
            st.session_state["chatter_max_retries"] = max_retries

        with col_d:
            pause_ms = st.slider(
                "청크 간 휴식 (ms)",
                min_value=0,
                max_value=500,
                value=st.session_state.get("chatter_pause_ms", 200),
                step=50,
                key="chatter_pause_ms_slider",
                help="청크 사이에 삽입할 무음 길이"
            )
            st.session_state["chatter_pause_ms"] = pause_ms

        # 처리 방식 옵션
        st.markdown("---")
        st.markdown("**⚡ 처리 방식 설정**")

        col_e, col_f = st.columns(2)

        with col_e:
            processing_mode = st.radio(
                "처리 방식",
                ["🔄 순차 처리 (안정적)", "🚀 병렬 처리 (빠름)"],
                index=0,  # 기본: 순차 처리
                key="chatter_processing_mode",
                help="""
• 순차 처리: 타임아웃 방지, 안정적 (권장)
• 병렬 처리: 빠르지만 GPU 경쟁으로 타임아웃 가능
                """
            )
            use_sequential = "순차" in processing_mode

            # 순차 처리 시 청크 분할 옵션
            if use_sequential:
                use_smart_chunking = st.checkbox(
                    "📝 스마트 청크 분할",
                    value=st.session_state.get("chatter_smart_chunking", True),
                    key="chatter_smart_chunking_checkbox",
                    help="긴 텍스트를 70자 단위로 분할하여 안정적으로 생성합니다."
                )
                st.session_state["chatter_smart_chunking"] = use_smart_chunking
            else:
                use_smart_chunking = False

        with col_f:
            if use_sequential:
                timeout_per_scene = st.slider(
                    "씬당 타임아웃 (초)",
                    min_value=60,
                    max_value=300,
                    value=st.session_state.get("chatter_timeout", 180),
                    step=30,
                    key="chatter_timeout_slider",
                    help="긴 텍스트는 더 긴 타임아웃이 필요합니다. (기본: 180초)"
                )
                st.session_state["chatter_timeout"] = timeout_per_scene
                max_concurrent = 1
            else:
                max_concurrent = st.slider(
                    "동시 생성 수",
                    min_value=1,
                    max_value=4,
                    value=st.session_state.get("chatter_max_concurrent", 2),
                    step=1,
                    key="chatter_max_concurrent_slider",
                    help="동시에 생성할 씬 수. (기본: 2)"
                )
                st.session_state["chatter_max_concurrent"] = max_concurrent
                timeout_per_scene = 180
                use_smart_chunking = False

    return {
        "mode": "preview" if "프리뷰" in generation_mode else "full",
        "preview_length": preview_length,
        "chunk_size": chunk_size,
        "repetition_penalty": repetition_penalty,
        "max_retries": max_retries,
        "pause_ms": pause_ms,
        "use_sequential": use_sequential,
        "use_smart_chunking": use_smart_chunking,
        "timeout_per_scene": timeout_per_scene,
        "parallel_enabled": not use_sequential,
        "max_concurrent": max_concurrent
    }


def render_normalization_options():
    """
    음성 정규화 옵션 UI

    Returns:
        dict: 정규화 옵션 {enabled, target_lufs, normalize_speed, normalize_silence}
    """
    st.markdown("#### 🎚️ 음성 일관성 설정")

    with st.expander("음성 정규화 옵션", expanded=False):
        st.caption("씬별 음량, 속도, 무음 구간을 일관되게 맞춥니다.")

        col1, col2 = st.columns(2)

        with col1:
            enable_normalization = st.checkbox(
                "✅ 음성 정규화 적용",
                value=st.session_state.get("enable_normalization", True),
                key="enable_norm_checkbox",
                help="씬별 음량, 속도를 일관되게 맞춥니다."
            )
            st.session_state["enable_normalization"] = enable_normalization

            if enable_normalization:
                target_lufs = st.slider(
                    "🔊 목표 음량 (LUFS)",
                    min_value=-24,
                    max_value=-12,
                    value=st.session_state.get("target_lufs", -16),
                    step=1,
                    key="target_lufs_slider",
                    help="-16 LUFS: 스트리밍 표준\n-14 LUFS: 약간 큰 소리\n-20 LUFS: 조용한 소리"
                )
                st.session_state["target_lufs"] = target_lufs
            else:
                target_lufs = -16

        with col2:
            if enable_normalization:
                normalize_speed = st.checkbox(
                    "⏱️ 발화 속도 일관성",
                    value=st.session_state.get("normalize_speed", True),
                    key="normalize_speed_checkbox",
                    help="모든 씬의 발화 속도를 평균값으로 맞춥니다."
                )
                st.session_state["normalize_speed"] = normalize_speed

                normalize_silence = st.checkbox(
                    "🔇 무음 구간 표준화",
                    value=st.session_state.get("normalize_silence", True),
                    key="normalize_silence_checkbox",
                    help="각 씬 앞뒤의 무음 구간을 100ms로 표준화합니다."
                )
                st.session_state["normalize_silence"] = normalize_silence
            else:
                normalize_speed = False
                normalize_silence = False

    return {
        "enabled": enable_normalization,
        "target_lufs": target_lufs,
        "normalize_speed": normalize_speed,
        "normalize_silence": normalize_silence
    }


def apply_normalization_to_result(
    result: dict,
    text: str,
    norm_opts: dict
) -> dict:
    """
    단일 TTS 결과에 정규화 적용

    Args:
        result: TTS 생성 결과 (audio_data 포함)
        text: 원본 텍스트
        norm_opts: 정규화 옵션

    Returns:
        정규화된 결과 dict
    """
    print(f"[Normalize] apply_normalization_to_result 호출")
    print(f"[Normalize] 옵션: enabled={norm_opts.get('enabled')}, target_lufs={norm_opts.get('target_lufs')}")

    if not norm_opts.get("enabled", True):
        print("[Normalize] ❌ 정규화 비활성화됨 - 스킵")
        return result

    if not result.get("success") or not result.get("audio_data"):
        print("[Normalize] ❌ 유효한 오디오 데이터 없음 - 스킵")
        return result

    try:
        print(f"[Normalize] 정규화 시작: 텍스트 {len(text)}자")
        normalized = normalize_audio_full(
            audio_data=result["audio_data"],
            text=text,
            target_lufs=norm_opts.get("target_lufs", -16),
            target_speech_rate=None,  # 단일 생성에서는 속도 조정 안함
            standardize_silence_ms=(100, 100) if norm_opts.get("normalize_silence", True) else None
        )

        result["audio_data"] = normalized["audio_data"]
        result["original_rate"] = normalized["original_rate"]
        result["final_rate"] = normalized["final_rate"]
        result["original_duration"] = normalized["original_duration"]
        result["final_duration"] = normalized["final_duration"]
        result["normalized"] = True

        print(f"[Normalize] ✅ 정규화 완료: {normalized['original_duration']:.1f}초 → {normalized['final_duration']:.1f}초")

    except Exception as e:
        print(f"[Normalize] ❌ 정규화 실패: {e}")
        import traceback
        traceback.print_exc()
        result["normalized"] = False

    return result


def apply_normalization_to_scenes(
    scene_results: list,
    norm_opts: dict,
    progress_callback=None
) -> list:
    """
    씬별 TTS 결과에 일괄 정규화 적용

    Args:
        scene_results: 씬별 생성 결과 리스트
        norm_opts: 정규화 옵션
        progress_callback: 진행 콜백

    Returns:
        정규화된 결과 리스트
    """
    print(f"[Normalization] apply_normalization_to_scenes 호출")
    print(f"[Normalization] 옵션: enabled={norm_opts.get('enabled')}, target_lufs={norm_opts.get('target_lufs')}")

    if not norm_opts.get("enabled", True):
        print("[Normalization] ❌ 정규화 비활성화됨 - 스킵")
        return scene_results

    # 성공한 씬만 필터링
    valid_scenes = []
    for r in scene_results:
        if r.get("audio_data"):
            valid_scenes.append({
                "scene_id": r.get("scene_id"),
                "audio_data": r.get("audio_data"),
                "text": r.get("text_preview", "") if len(r.get("text_preview", "")) > 30 else r.get("text", "")
            })

    print(f"[Normalization] 유효한 씬 수: {len(valid_scenes)}/{len(scene_results)}")

    if not valid_scenes:
        print("[Normalization] ❌ 유효한 씬 없음 - 스킵")
        return scene_results

    # 배치 정규화 적용
    print(f"[Normalization] 배치 정규화 시작...")
    normalized = normalize_scenes_batch(
        scene_audios=valid_scenes,
        target_lufs=norm_opts.get("target_lufs", -16),
        use_consistent_speed=norm_opts.get("normalize_speed", True),
        standardize_silence_ms=(100, 100) if norm_opts.get("normalize_silence", True) else None,
        progress_callback=progress_callback
    )
    print(f"[Normalization] ✅ 배치 정규화 완료: {len(normalized)}개 씬")

    # 결과 병합
    normalized_map = {n["scene_id"]: n for n in normalized}

    normalized_count = 0
    for r in scene_results:
        scene_id = r.get("scene_id")
        if scene_id in normalized_map:
            norm_data = normalized_map[scene_id]
            r["audio_data"] = norm_data.get("audio_data", r.get("audio_data"))
            r["original_rate"] = norm_data.get("original_rate", 0)
            r["final_rate"] = norm_data.get("final_rate", 0)
            r["original_duration"] = norm_data.get("original_duration", 0)
            r["final_duration"] = norm_data.get("final_duration", 0)
            r["normalized"] = norm_data.get("normalized", False)
            if r["normalized"]:
                normalized_count += 1

    print(f"[Normalization] 최종 결과: {normalized_count}개 씬 정규화됨")
    return scene_results


def generate_single_chunk(
    text: str,
    voice_ref_path: str,
    params: dict,
    repetition_penalty: float = 1.3,
    timeout: int = 120
) -> dict:
    """
    단일 청크 TTS 생성

    Args:
        text: 텍스트
        voice_ref_path: 참조 음성 경로
        params: TTS 파라미터
        repetition_penalty: 반복 억제 강도
        timeout: 타임아웃 (초)

    Returns:
        {success, audio_data, duration, error}
    """
    # 디버그 로깅
    seed_value = params.get("seed")
    print(f"[TTS] generate_single_chunk 호출:")
    print(f"  - text: {text[:30]}...")
    print(f"  - voice_ref_path: {voice_ref_path}")
    print(f"  - seed: {seed_value} ({'고정' if seed_value is not None else '랜덤'})")

    payload = {
        "text": text,
        "settings": {
            "language": "ko",
            "exaggeration": params.get("exaggeration", 0.5),
            "cfg_weight": params.get("cfg_weight", 0.5),
            "temperature": params.get("temperature", 0.8),
            "speed": params.get("speed", 1.0),
            "seed": seed_value,
            "voice_ref_path": voice_ref_path,
            "repetition_penalty": repetition_penalty
        }
    }

    try:
        start_time = time.time()
        r = requests.post(f"{CHATTERBOX_URL}/generate", json=payload, timeout=timeout)
        elapsed = time.time() - start_time

        if r.status_code == 200:
            result = r.json()

            if result.get("success"):
                # 오디오 다운로드
                audio_url = result.get("audio_url", "")
                audio_data = None

                if audio_url:
                    full_url = f"{CHATTERBOX_URL}{audio_url}"
                    audio_response = requests.get(full_url, timeout=30)
                    if audio_response.status_code == 200:
                        audio_data = audio_response.content

                return {
                    "success": True,
                    "audio_data": audio_data,
                    "duration": result.get("duration_seconds", 0),
                    "processing_time": elapsed,
                    "seed_used": result.get("seed_used")
                }
            else:
                return {
                    "success": False,
                    "error": result.get("error", "알 수 없는 오류")
                }
        else:
            return {
                "success": False,
                "error": f"HTTP {r.status_code}"
            }

    except requests.exceptions.Timeout:
        return {"success": False, "error": "타임아웃"}
    except requests.exceptions.ConnectionError:
        invalidate_chatterbox_cache()
        return {"success": False, "error": "서버 연결 실패"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def generate_chunk_with_retry(
    text: str,
    voice_ref_path: str,
    params: dict,
    initial_rep_penalty: float = 1.3,
    max_retries: int = 3
) -> dict:
    """
    청크 생성 (재시도 로직 포함)

    잘림 감지 시 seed 변경 + repetition_penalty 증가 후 재시도.

    Args:
        text: 텍스트
        voice_ref_path: 참조 음성 경로
        params: TTS 파라미터
        initial_rep_penalty: 초기 반복 억제 강도
        max_retries: 최대 재시도 횟수

    Returns:
        생성 결과 dict
    """
    import random
    current_rep_penalty = initial_rep_penalty
    text_length = len(text)
    base_seed = params.get("seed")

    for attempt in range(max_retries):
        # 재시도 시 seed 변경 (다른 토큰 패턴 유도)
        retry_params = params.copy()
        if attempt > 0:
            if base_seed is not None:
                retry_params["seed"] = base_seed + (attempt * 1000)
            else:
                retry_params["seed"] = random.randint(0, 2**31 - 1)
            print(f"[Retry {attempt}] seed={retry_params['seed']}, rep_penalty={current_rep_penalty}")

        result = generate_single_chunk(
            text=text,
            voice_ref_path=voice_ref_path,
            params=retry_params,
            repetition_penalty=current_rep_penalty
        )

        if not result.get("success"):
            # 실패 시 재시도
            if attempt < max_retries - 1:
                current_rep_penalty += 0.2
                time.sleep(0.5)
                continue
            return result

        # 잘림 검증
        duration = result.get("duration", 0)
        validation = validate_chunk_duration(text_length, duration)

        if validation["is_valid"]:
            result["status"] = "success"
            result["char_count"] = text_length
            chars_per_sec = validation.get("chars_per_second", 0)
            print(f"[Generate] ✅ 정상: {duration:.2f}초, {chars_per_sec:.1f} 글자/초")
            return result
        else:
            # 잘림 감지!
            chars_per_sec = validation.get("chars_per_second", 0)
            print(f"[Generate] ⚠️ 잘림: {duration:.2f}초 < {validation['expected_min']:.2f}초 ({chars_per_sec:.1f} 글자/초)")

            if attempt < max_retries - 1:
                # 재시도: seed 변경 + rep_penalty 증가
                current_rep_penalty = min(current_rep_penalty + 0.3, 2.5)
                time.sleep(0.3)
                continue
            else:
                # 마지막 시도에서도 잘림 → 그래도 반환
                result["status"] = "truncated"
                result["char_count"] = text_length
                result["warning"] = f"텍스트 잘림 ({chars_per_sec:.1f} 글자/초, 최대 재시도 초과)"
                return result

    return {"success": False, "error": "최대 재시도 횟수 초과"}


def merge_audio_chunks(audio_data_list: list, pause_ms: int = 200) -> bytes:
    """
    오디오 청크들을 하나로 병합

    Args:
        audio_data_list: 오디오 데이터 바이트 리스트
        pause_ms: 청크 간 휴식 시간 (ms)

    Returns:
        병합된 WAV 바이트
    """
    try:
        from pydub import AudioSegment

        combined = AudioSegment.empty()
        silence = AudioSegment.silent(duration=pause_ms) if pause_ms > 0 else None

        for idx, audio_data in enumerate(audio_data_list):
            if not audio_data:
                continue

            # BytesIO로 변환하여 로드
            audio_io = io.BytesIO(audio_data)
            try:
                audio = AudioSegment.from_file(audio_io, format="wav")

                if idx > 0 and silence:
                    combined += silence

                combined += audio
            except Exception as e:
                print(f"[Merge] 청크 {idx + 1} 로드 실패: {e}")
                continue

        # 결과를 BytesIO로 출력
        output_io = io.BytesIO()
        combined.export(output_io, format="wav")
        output_io.seek(0)

        return output_io.read()

    except ImportError:
        # pydub이 없으면 첫 번째 청크만 반환
        for audio_data in audio_data_list:
            if audio_data:
                return audio_data
        return b""
    except Exception as e:
        print(f"[Merge] 병합 오류: {e}")
        # 오류 시 첫 번째 청크만 반환
        for audio_data in audio_data_list:
            if audio_data:
                return audio_data
        return b""


def generate_chatterbox_tts_robust(
    text: str,
    voice_ref_path: str,
    params: dict,
    mode: str = "full",
    preview_length: int = 50,
    chunk_size: int = 80,
    repetition_penalty: float = 1.3,
    max_retries: int = 3,
    pause_ms: int = 200,
    progress_callback=None
) -> dict:
    """
    안정적인 Chatterbox TTS 생성 (청크 분할 + 재시도)

    긴 텍스트를 청크로 나눠서 생성하고 병합합니다.
    토큰 반복으로 인한 조기 종료를 감지하여 재시도합니다.

    Args:
        text: 입력 텍스트
        voice_ref_path: 참조 음성 파일 경로
        params: TTS 파라미터
        mode: "full" (전체) 또는 "preview" (프리뷰)
        preview_length: 프리뷰 모드 시 글자 수
        chunk_size: 청크당 최대 글자 수
        repetition_penalty: 반복 억제 강도
        max_retries: 청크당 최대 재시도 횟수
        pause_ms: 청크 간 휴식 시간 (ms)
        progress_callback: 진행 상황 콜백 (current, total, message)

    Returns:
        {success, audio_data, duration, chunks_info, ...}
    """
    # 1. 프리뷰 모드면 텍스트 자르기
    original_length = len(text)
    if mode == "preview":
        text = get_preview_text(text, preview_length)
        if progress_callback:
            progress_callback(0, 1, f"프리뷰 모드: {len(text)}자 생성")

    # 2. 텍스트 분할
    chunks = split_text_for_tts(text, max_chars=chunk_size)
    total_chunks = len(chunks)

    if progress_callback:
        progress_callback(0, total_chunks, f"총 {total_chunks}개 청크로 분할")

    # 3. 각 청크 생성
    audio_data_list = []
    chunks_info = []

    for chunk_data in chunks:
        chunk_idx = chunk_data["index"]
        chunk_text = chunk_data["text"]

        if progress_callback:
            progress_callback(chunk_idx - 1, total_chunks, f"청크 {chunk_idx}/{total_chunks} 생성 중...")

        # 청크 생성 (재시도 포함)
        result = generate_chunk_with_retry(
            text=chunk_text,
            voice_ref_path=voice_ref_path,
            params=params,
            initial_rep_penalty=repetition_penalty,
            max_retries=max_retries
        )

        if result.get("success") or result.get("status") == "truncated":
            audio_data_list.append(result.get("audio_data"))
            chunks_info.append({
                "index": chunk_idx,
                "text_preview": chunk_text[:30] + "..." if len(chunk_text) > 30 else chunk_text,
                "char_count": len(chunk_text),
                "duration": result.get("duration", 0),
                "status": result.get("status", "success"),
                "warning": result.get("warning")
            })
        else:
            chunks_info.append({
                "index": chunk_idx,
                "text_preview": chunk_text[:30] + "...",
                "char_count": len(chunk_text),
                "error": result.get("error", "알 수 없는 오류"),
                "status": "failed"
            })

    if progress_callback:
        progress_callback(total_chunks, total_chunks, "오디오 병합 중...")

    # 4. 결과 집계
    stats = merge_chunk_results(chunks_info)

    if stats["success_count"] == 0:
        return {
            "success": False,
            "error": "모든 청크 생성 실패",
            "chunks_info": chunks_info,
            "stats": stats
        }

    # 5. 오디오 병합
    valid_audio_data = [a for a in audio_data_list if a]

    if len(valid_audio_data) == 1:
        # 단일 청크면 병합 불필요
        merged_audio = valid_audio_data[0]
    else:
        merged_audio = merge_audio_chunks(valid_audio_data, pause_ms=pause_ms)

    return {
        "success": True,
        "audio_data": merged_audio,
        "duration": stats["total_duration"],
        "chunks_info": chunks_info,
        "stats": stats,
        "mode": mode,
        "original_length": original_length,
        "processed_length": len(text)
    }


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

    # 사용 가능한 스크립트 소스 동적 생성
    script_sources = ["직접 입력"]
    script_data = {}

    # 1. 스크립트 생성 탭 결과 (generated_script)
    if st.session_state.get("generated_script"):
        script_sources.append("스크립트 생성 결과")
        script_data["스크립트 생성 결과"] = st.session_state["generated_script"]

    # 2. 씬 분석 스크립트 (scene_analysis_script) - 개별 씬 데이터 확인
    scenes_data = st.session_state.get("scenes", [])
    has_scene_data = len(scenes_data) > 0

    if st.session_state.get("scene_analysis_script") or has_scene_data:
        script_sources.append("씬 분석 스크립트")
        script_data["씬 분석 스크립트"] = st.session_state.get("scene_analysis_script", "")

    script_source = st.radio(
        "스크립트 소스",
        options=script_sources,
        horizontal=True,
        key="edge_script_source"
    )

    # 씬별 생성 모드 변수 초기화
    edge_generation_mode = "single"
    edge_selected_scenes = []
    script_text = ""

    if script_source == "직접 입력":
        script_text = st.text_area(
            "텍스트 입력",
            height=200,
            placeholder="TTS로 변환할 텍스트를 입력하세요...",
            key="edge_script_input"
        )
    elif script_source == "씬 분석 스크립트" and has_scene_data:
        # 씬별 생성 모드 UI
        st.info(f"📊 총 **{len(scenes_data)}개** 씬이 분석되어 있습니다.")

        # 생성 모드 선택
        edge_generation_mode = st.radio(
            "🎯 생성 모드",
            options=["씬별 개별 생성", "전체 합쳐서 생성"],
            horizontal=True,
            key="edge_generation_mode",
            help="씬별 개별 생성: 각 씬마다 별도 음성 파일 생성\n전체 합쳐서 생성: 모든 씬을 하나의 파일로 생성"
        )

        st.markdown("---")

        if edge_generation_mode == "씬별 개별 생성":
            st.markdown("**📋 생성할 씬 선택**")

            # 전체 선택/해제
            col_sel1, col_sel2 = st.columns([1, 3])
            with col_sel1:
                select_all = st.checkbox("전체 선택", value=True, key="edge_select_all_scenes")

            # 씬 목록 표시
            edge_selected_scenes = []
            for idx, scene in enumerate(scenes_data):
                scene_id = scene.get('scene_id', idx + 1)
                scene_text = scene.get('script_text', '')
                char_count = len(scene_text)
                duration_est = scene.get('duration_estimate', char_count // 10)

                # 체크박스와 미리보기를 같은 행에
                col_check, col_info = st.columns([1, 4])

                with col_check:
                    is_selected = st.checkbox(
                        f"씬 {scene_id}",
                        value=select_all,
                        key=f"edge_scene_select_{scene_id}"
                    )

                with col_info:
                    with st.expander(f"{scene_text[:40]}... ({char_count}자, ~{duration_est}초)", expanded=False):
                        st.text_area(
                            "내용",
                            value=scene_text,
                            height=100,
                            disabled=True,
                            key=f"edge_scene_preview_{scene_id}"
                        )

                if is_selected:
                    edge_selected_scenes.append({
                        "scene_id": scene_id,
                        "text": scene_text,
                        "char_count": char_count,
                        "duration_estimate": duration_est
                    })

            # 선택 요약
            total_chars = sum(s["char_count"] for s in edge_selected_scenes)
            st.success(f"✅ **{len(edge_selected_scenes)}개** 씬 선택됨 (총 {total_chars:,}자)")

            # 전체 텍스트 (미리보기용)
            script_text = "\n\n".join([s["text"] for s in edge_selected_scenes]) if edge_selected_scenes else ""

        else:
            # 전체 합쳐서 생성 모드
            full_text = "\n\n".join([s.get('script_text', '') for s in scenes_data])
            script_text = full_text

            # 메타 정보
            total_chars = sum(len(s.get('script_text', '')) for s in scenes_data)
            total_duration = sum(s.get('duration_estimate', 10) for s in scenes_data)

            cols = st.columns(3)
            cols[0].metric("총 씬 수", f"{len(scenes_data)}개")
            cols[1].metric("총 글자 수", f"{total_chars:,}자")
            cols[2].metric("예상 길이", f"{total_duration // 60}분 {total_duration % 60}초")

            st.text_area(
                "전체 스크립트 (읽기 전용)",
                value=full_text,
                height=200,
                disabled=True,
                key="edge_full_script_preview"
            )

            # 전체 씬을 선택된 씬으로 설정
            edge_selected_scenes = [{
                "scene_id": s.get('scene_id', idx + 1),
                "text": s.get('script_text', ''),
                "char_count": len(s.get('script_text', '')),
                "duration_estimate": s.get('duration_estimate', 10)
            } for idx, s in enumerate(scenes_data)]

    elif script_source in script_data:
        script_text = script_data[script_source]
        st.text_area(f"{script_source}", value=script_text, height=200, disabled=True, key="edge_script_preview")
    else:
        script_text = ""
        st.warning("생성된 스크립트가 없습니다. 먼저 스크립트 생성 또는 씬 분석을 해주세요.")

    # 문자 수
    if script_text:
        st.caption(f"📊 {len(script_text)}자 | 예상 시간: 약 {max(1, len(script_text) // 150)}분")

    st.markdown("---")

    # === 생성 버튼 ===
    # 씬별 개별 생성 모드일 때
    if script_source == "씬 분석 스크립트" and has_scene_data and edge_generation_mode == "씬별 개별 생성":
        if st.button(
            f"🎵 Edge TTS 씬별 생성 ({len(edge_selected_scenes)}개)",
            type="primary",
            use_container_width=True,
            disabled=len(edge_selected_scenes) == 0,
            key="generate_edge_tts_by_scenes"
        ):
            generate_edge_tts_by_scenes(
                scenes=edge_selected_scenes,
                voice_id=selected_voice,
                rate=tts_rate,
                pitch=tts_pitch,
                volume=tts_volume,
                add_breaks=add_breaks,
                generate_subs=generate_subs
            )
    else:
        # 일반 생성 모드
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


def generate_edge_tts_by_scenes(scenes, voice_id, rate, pitch, volume, add_breaks, generate_subs):
    """씬별 Edge TTS 개별 생성"""
    import asyncio

    # 음성 ID 유효성 검사
    all_valid_voices = []
    for lang_voices in EDGE_VOICES.values():
        all_valid_voices.extend([v["id"] for v in lang_voices])

    if voice_id not in all_valid_voices:
        st.error(f"⚠️ 유효하지 않은 음성 ID: {voice_id}")
        st.warning("지원되는 음성 목록에서 선택해주세요.")
        return

    # 진행 상황 UI
    progress_bar = st.progress(0)
    status_text = st.empty()
    results_container = st.container()

    # 출력 디렉토리 설정
    output_dir = st.session_state.get("tts_output_dir", "data/tts")
    timestamp = int(time.time())
    scene_output_dir = os.path.join(output_dir, f"scenes_{timestamp}")
    os.makedirs(scene_output_dir, exist_ok=True)

    # 설정 문자열
    rate_str = f"{'+' if rate >= 0 else ''}{rate}%"
    pitch_str = f"{'+' if pitch >= 0 else ''}{pitch}Hz"
    volume_str = f"{'+' if volume >= 0 else ''}{volume}%"

    generated_files = []
    total_scenes = len(scenes)

    try:
        import edge_tts

        async def generate_single_scene(scene_data, output_path):
            """단일 씬 TTS 생성"""
            text = scene_data.get("text", "")
            if not text.strip():
                return None

            communicate = edge_tts.Communicate(
                text=text,
                voice=voice_id,
                rate=rate_str,
                volume=volume_str,
                pitch=pitch_str
            )

            await communicate.save(output_path)
            return output_path

        # 씬별 생성 루프
        for idx, scene in enumerate(scenes):
            scene_id = scene.get("scene_id", idx + 1)
            scene_text = scene.get("text", "")

            if not scene_text.strip():
                continue

            # 진행 상황 업데이트
            progress_bar.progress((idx + 1) / total_scenes)
            status_text.text(f"씬 {scene_id} 생성 중... ({idx + 1}/{total_scenes})")

            # 출력 파일 경로
            audio_path = os.path.join(scene_output_dir, f"scene_{scene_id:02d}.mp3")

            try:
                # 비동기 실행
                asyncio.run(generate_single_scene(scene, audio_path))

                generated_files.append({
                    "scene_id": scene_id,
                    "path": audio_path,
                    "text_preview": scene_text[:50] + "..." if len(scene_text) > 50 else scene_text,
                    "char_count": len(scene_text),
                    "status": "success"
                })

            except Exception as e:
                generated_files.append({
                    "scene_id": scene_id,
                    "path": None,
                    "error": str(e),
                    "status": "failed"
                })

        progress_bar.progress(1.0)
        status_text.empty()

        # 결과 표시
        success_count = len([f for f in generated_files if f["status"] == "success"])
        failed_count = len([f for f in generated_files if f["status"] == "failed"])

        with results_container:
            if success_count > 0:
                st.success(f"✅ **{success_count}/{total_scenes}개** 씬 생성 완료!")

                # 씬별 오디오 플레이어 및 다운로드
                st.markdown("### 🎵 생성된 음성 파일")

                for file_info in generated_files:
                    scene_id = file_info["scene_id"]

                    if file_info["status"] == "success":
                        with st.expander(f"📢 씬 {scene_id} - {file_info['text_preview']} ({file_info['char_count']}자)", expanded=True):
                            col1, col2 = st.columns([3, 1])

                            with col1:
                                st.audio(file_info["path"])

                            with col2:
                                with open(file_info["path"], "rb") as f:
                                    st.download_button(
                                        "⬇️ 다운로드",
                                        data=f.read(),
                                        file_name=f"scene_{scene_id:02d}.mp3",
                                        mime="audio/mpeg",
                                        key=f"download_scene_{scene_id}_{timestamp}",
                                        use_container_width=True
                                    )
                    else:
                        st.error(f"❌ 씬 {scene_id} 생성 실패: {file_info.get('error', '알 수 없는 오류')}")

                # 전체 ZIP 다운로드
                if success_count > 1:
                    st.markdown("---")
                    st.markdown("### 📦 일괄 다운로드")

                    # ZIP 파일 생성
                    import zipfile
                    import io

                    zip_buffer = io.BytesIO()
                    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                        for file_info in generated_files:
                            if file_info["status"] == "success" and file_info["path"]:
                                scene_id = file_info["scene_id"]
                                zip_file.write(file_info["path"], f"scene_{scene_id:02d}.mp3")

                    zip_buffer.seek(0)

                    st.download_button(
                        f"📦 전체 다운로드 (ZIP, {success_count}개 파일)",
                        data=zip_buffer.getvalue(),
                        file_name=f"tts_scenes_{timestamp}.zip",
                        mime="application/zip",
                        key=f"download_all_zip_{timestamp}",
                        use_container_width=True
                    )

                # 세션에 저장
                st.session_state["last_tts_scenes"] = generated_files
                st.session_state["last_tts_output_dir"] = scene_output_dir

            if failed_count > 0:
                st.warning(f"⚠️ {failed_count}개 씬 생성 실패")

    except ImportError:
        status_text.error("edge-tts 라이브러리가 설치되지 않았습니다.")
        st.code("pip install edge-tts")
    except Exception as e:
        status_text.error(f"오류: {e}")
        import traceback
        with st.expander("상세 오류"):
            st.code(traceback.format_exc())


# ============================================================
# Chatterbox 탭 - 음성 클론 관리
# ============================================================

def get_voice_samples_dir():
    """프로젝트별 음성 샘플 디렉토리 반환 (절대 경로)"""
    # 현재 파일의 디렉토리 기준으로 절대 경로 생성
    base_dir = Path(__file__).parent.parent.resolve()  # longform 루트 디렉토리

    current_project = st.session_state.get("current_project")
    if current_project:
        samples_dir = base_dir / "data" / "projects" / current_project / "voice_samples"
    else:
        samples_dir = base_dir / "data" / "voice_samples" / "default"
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
                    "path": str(filepath.resolve()),  # 절대 경로 확실히 적용
                    "description": s.get("description", ""),
                    "created_at": s.get("created_at", "")
                })
    else:
        # 메타 없으면 파일 직접 스캔
        for f in samples_dir.glob("*"):
            if f.suffix.lower() in ['.wav', '.mp3', '.m4a', '.ogg']:
                samples.append({
                    "name": f.stem,
                    "path": str(f.resolve()),  # 절대 경로 확실히 적용
                    "description": "",
                    "created_at": ""
                })

    # voice_library/ko 폴더도 포함 (절대 경로)
    base_dir = Path(__file__).parent.parent.resolve()
    voice_lib = base_dir / "voice_library" / "ko"
    if voice_lib.exists():
        for f in voice_lib.glob("*"):
            if f.suffix.lower() in ['.wav', '.mp3', '.m4a', '.ogg']:
                samples.append({
                    "name": f"[라이브러리] {f.stem}",
                    "path": str(f.resolve()),  # 절대 경로 확실히 적용
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
    """참조 음성 선택 (개선된 버전 + 음성 분석)"""
    st.markdown("#### 🎤 참조 음성 선택")

    samples_dir = get_voice_samples_dir()
    samples = get_voice_samples(samples_dir)

    if not samples:
        st.warning("저장된 음성 샘플이 없습니다. 위 '음성 클론 관리'에서 먼저 샘플을 추가하세요.")
        st.session_state["selected_reference_voice"] = None
        return None

    sample_options = ["없음 (기본 음성)"] + [s['name'] for s in samples]
    sample_paths = {s['name']: s['path'] for s in samples}
    path_to_name = {s['path']: s['name'] for s in samples}

    # 초기 인덱스 결정: 이전 선택 > 기본 음성 > 0
    initial_index = 0

    # 1. 이전에 선택된 음성이 있으면 그것을 우선
    stored_selection = st.session_state.get("ref_voice_select")
    if stored_selection and stored_selection in sample_options:
        initial_index = sample_options.index(stored_selection)
    else:
        # 2. 세션에 저장된 참조 음성 경로 확인
        stored_ref_path = st.session_state.get("selected_reference_voice")
        if stored_ref_path and stored_ref_path in path_to_name:
            stored_name = path_to_name[stored_ref_path]
            if stored_name in sample_options:
                initial_index = sample_options.index(stored_name)
        else:
            # 3. 기본 음성 설정 확인
            default_voice = st.session_state.get("default_voice_sample")
            if default_voice and default_voice in path_to_name:
                default_name = path_to_name[default_voice]
                if default_name in sample_options:
                    initial_index = sample_options.index(default_name)

    selected_name = st.selectbox(
        "참조 음성",
        options=sample_options,
        index=initial_index,
        key="ref_voice_select"
    )

    # 디버그 로깅
    print(f"[VoiceSelector] selected_name: {selected_name}")

    if selected_name and selected_name != "없음 (기본 음성)":
        selected_path = sample_paths.get(selected_name)
        print(f"[VoiceSelector] selected_path from dict: {selected_path}")

        if selected_path:
            # 파일 존재 확인
            if os.path.exists(selected_path):
                # 선택된 음성 정보 표시
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.audio(selected_path)
                with col2:
                    st.success(f"✓ {selected_name}")

                st.session_state["selected_reference_voice"] = selected_path

                # ⭐ 텍스트 입력 UI (정확한 발화속도 측정용)
                current_transcript = get_voice_transcript(selected_path) or ""
                has_transcript = bool(current_transcript)

                with st.expander(
                    f"📝 텍스트 {'편집' if has_transcript else '입력'} (정확한 발화속도 측정)",
                    expanded=not has_transcript  # 텍스트 없으면 펼쳐서 입력 유도
                ):
                    if has_transcript:
                        st.success(f"✅ 텍스트 등록됨 ({len(current_transcript)}자)")
                    else:
                        st.warning("⚠️ 텍스트 없음 - 발화속도 추정 모드 (정확도 ±20%)")
                        st.caption("참조 음성의 텍스트를 입력하면 정확한 발화속도를 측정할 수 있습니다.")

                    new_transcript = st.text_area(
                        "참조 음성 텍스트",
                        value=current_transcript,
                        height=80,
                        placeholder="예: 안녕하세요, 오늘은 회계사 시험 준비에 대해 이야기해 보려고 합니다.",
                        key="transcript_input",
                        label_visibility="collapsed"
                    )

                    col_save, col_clear = st.columns(2)
                    with col_save:
                        if st.button("💾 텍스트 저장", key="save_transcript", use_container_width=True):
                            if new_transcript.strip():
                                set_voice_transcript(selected_path, new_transcript.strip())
                                # 재분석 강제
                                st.session_state["_prev_analyzed_voice_path"] = None
                                st.success("✅ 텍스트 저장 완료! 재분석 중...")
                                st.rerun()
                            else:
                                st.error("텍스트를 입력해주세요")
                    with col_clear:
                        if has_transcript:
                            if st.button("🗑️ 텍스트 삭제", key="delete_transcript", use_container_width=True):
                                set_voice_transcript(selected_path, "")
                                st.session_state["_prev_analyzed_voice_path"] = None
                                st.rerun()

                # ⭐ 음성 분석 및 파라미터 추천
                prev_analyzed_path = st.session_state.get("_prev_analyzed_voice_path")
                if selected_path != prev_analyzed_path:
                    # 새 음성 선택됨 → 분석 실행
                    _analyze_and_update_params(selected_path, selected_name)
                    st.session_state["_prev_analyzed_voice_path"] = selected_path

                # ⭐ 분석 결과 표시 (정확/추정 구분)
                if "voice_analysis" in st.session_state:
                    analysis = st.session_state["voice_analysis"]
                    tempo = analysis.get("tempo", "normal")
                    speech_rate = analysis.get("speech_rate", 8.5)
                    accurate = analysis.get("speech_rate_accurate", False)

                    tempo_emoji = {"slow": "🐢", "normal": "🚶", "fast": "🏃"}.get(tempo, "🚶")
                    tempo_kr = {"slow": "느림", "normal": "보통", "fast": "빠름"}.get(tempo, "보통")

                    if accurate:
                        st.success(f"⭐ **정확한 측정**: {speech_rate:.2f} 글자/초 ({tempo_emoji} {tempo_kr}) → 파라미터 자동 조정됨")
                    else:
                        st.info(f"📊 **추정 측정**: {speech_rate:.1f} 글자/초 ({tempo_emoji} {tempo_kr}) → 파라미터 자동 조정됨")

                print(f"[VoiceSelector] ✅ 반환: {selected_path}")
                return selected_path
            else:
                st.warning(f"⚠️ 음성 파일이 존재하지 않습니다: {selected_path}")
                print(f"[VoiceSelector] ❌ 파일 없음: {selected_path}")
        else:
            st.warning(f"⚠️ 선택된 음성 '{selected_name}'의 경로를 찾을 수 없습니다.")
            print(f"[VoiceSelector] ❌ 경로 매핑 실패: {selected_name}")

    # 기본 음성 선택됨 → 기본 파라미터로 리셋
    st.session_state["selected_reference_voice"] = None
    st.session_state["voice_analysis"] = None
    st.session_state["recommended_params"] = None
    st.session_state["_prev_analyzed_voice_path"] = None
    st.info("기본 Chatterbox 음성이 사용됩니다.")
    print("[VoiceSelector] 기본 음성 반환 (None)")
    return None


def _analyze_and_update_params(voice_path: str, voice_name: str):
    """
    참조 음성 분석 후 세션 상태의 파라미터 업데이트

    ⭐ 핵심: 음성 특성에 맞는 파라미터 자동 설정
    """
    print(f"\n[VoiceAnalysis] 음성 분석 시작: {voice_name}")

    try:
        result = analyze_voice_and_get_params(voice_path)

        analysis = result.get("analysis", {})
        params = result.get("recommended_params", {})

        # 세션에 저장
        st.session_state["voice_analysis"] = analysis
        st.session_state["recommended_params"] = params

        # ⭐ 파라미터 자동 업데이트 (슬라이더 기본값으로 사용됨)
        if "speed" in params:
            st.session_state["chatter_speed"] = params["speed"]
        if "cfg_weight" in params:
            st.session_state["chatter_cfg"] = params["cfg_weight"]
        if "exaggeration" in params:
            st.session_state["chatter_exag"] = params["exaggeration"]
        if "temperature" in params:
            st.session_state["chatter_temp"] = params["temperature"]
        if "target_speed" in params:
            st.session_state["target_speech_rate"] = params["target_speed"]

        tempo = analysis.get("tempo", "normal")
        speech_rate = analysis.get("speech_rate", 8.5)
        tempo_kr = {"slow": "느림", "normal": "보통", "fast": "빠름"}.get(tempo, "보통")

        print(f"[VoiceAnalysis] 완료: {tempo_kr} ({speech_rate:.1f} 글자/초)")
        print(f"[VoiceAnalysis] 추천 파라미터: {params}")

    except Exception as e:
        print(f"[VoiceAnalysis] ⚠️ 분석 실패: {e}")
        # 기본값 유지


# ============================================================
# Chatterbox 탭
# ============================================================

def render_chatterbox_tab():
    """Chatterbox 탭 렌더링"""
    st.markdown("### 🎤 Chatterbox TTS")
    st.info("Chatterbox는 고품질 음성 합성 서버입니다. 로컬 서버가 실행 중이어야 합니다.")

    # 서버 상태 확인 (캐싱 적용)
    server_status = check_chatterbox_server()

    # 서버 상태 표시 영역
    status_container = st.container()

    if not server_status:
        with status_container:
            st.error("❌ Chatterbox 서버에 연결할 수 없습니다.")

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
                    st.info("새 콘솔 창에서 서버가 시작됩니다. 잠시 후 '연결 확인' 버튼을 클릭하세요.")
                except Exception as e:
                    st.error(f"오류: {e}")

        with col2:
            if st.button("🔄 연결 확인", use_container_width=True, key="check_connection_btn"):
                # 캐시 무효화 후 강제 새로고침
                invalidate_chatterbox_cache()
                with st.spinner("서버 연결 확인 중..."):
                    new_status = check_chatterbox_server(force_refresh=True)
                if new_status:
                    st.success("서버 연결됨!")
                    st.rerun()
                else:
                    st.error("서버에 연결할 수 없습니다.")

        with col3:
            st.caption("또는 수동으로:")
            st.code("cd C:\\Users\\KIMJAEHEON\\chatter\npython run.py", language="bash")

        return

    # 서버 연결됨 - 상태 표시
    with status_container:
        col_status1, col_status2 = st.columns([3, 1])
        with col_status1:
            st.success("✅ Chatterbox 서버 연결됨")
        with col_status2:
            if st.button("🔄", key="refresh_status_btn", help="상태 새로고침"):
                invalidate_chatterbox_cache()
                st.rerun()

    # 서버 상태 정보 (캐싱 적용)
    status = get_chatterbox_status()
    if status:
        model_loaded = status.get("model_loaded", False)
        if model_loaded:
            st.success("🟢 모델 로드됨 - TTS 생성 준비 완료")
        else:
            st.warning("🟡 모델 미로드 - TTS 사용 전 모델 로드가 필요합니다")
            if st.button("📥 모델 로드", key="load_chatterbox_model", type="primary"):
                progress_bar = st.progress(0, text="모델 로딩 중...")
                status_text = st.empty()

                status_text.text("🔄 Chatterbox 모델 로딩 중... (최초 1회만 필요, 약 30초~1분 소요)")
                progress_bar.progress(10)

                try:
                    progress_bar.progress(30, text="서버에 로드 요청 중...")
                    r = requests.post(f"{CHATTERBOX_URL}/load", timeout=180)
                    progress_bar.progress(80, text="로드 완료 확인 중...")

                    if r.status_code == 200:
                        progress_bar.progress(100, text="완료!")
                        status_text.success("✅ 모델 로드 완료!")
                        # 캐시 무효화
                        invalidate_chatterbox_cache()
                        time.sleep(1)
                        st.rerun()
                    else:
                        status_text.error(f"로드 실패: HTTP {r.status_code}")
                except requests.exceptions.Timeout:
                    status_text.error("⏱️ 요청 시간 초과 (180초). 서버 로그를 확인하세요.")
                except Exception as e:
                    status_text.error(f"❌ 로드 실패: {e}")

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
            value=st.session_state.get("chatter_temp", 0.85),  # ⭐ 0.8→0.85 자연스러움 최적화
            step=0.05,
            key="chatter_temp_slider",
            help="높을수록 다양한 톤. 0.85 권장 (기존 0.8은 단조로움)"
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

    # 사용 가능한 스크립트 소스 동적 생성
    chatter_script_sources = ["직접 입력"]
    chatter_script_data = {}

    # 1. 스크립트 생성 탭 결과 (generated_script)
    if st.session_state.get("generated_script"):
        chatter_script_sources.append("스크립트 생성 결과")
        chatter_script_data["스크립트 생성 결과"] = st.session_state["generated_script"]

    # 2. 씬 분석 스크립트 (scene_analysis_script) - 개별 씬 데이터 확인
    chatter_scenes_data = st.session_state.get("scenes", [])
    chatter_has_scene_data = len(chatter_scenes_data) > 0

    if st.session_state.get("scene_analysis_script") or chatter_has_scene_data:
        chatter_script_sources.append("씬 분석 스크립트")
        chatter_script_data["씬 분석 스크립트"] = st.session_state.get("scene_analysis_script", "")

    chatter_script_source = st.radio(
        "스크립트 소스",
        options=chatter_script_sources,
        horizontal=True,
        key="chatter_script_source"
    )

    # 씬별 생성 모드 변수 초기화
    chatter_generation_mode = "single"
    chatter_selected_scenes = []
    script_text = ""

    if chatter_script_source == "직접 입력":
        script_text = st.text_area(
            "텍스트 입력",
            value=st.session_state.get("chatter_text_input_value", "안녕하세요. Chatterbox TTS 테스트입니다. 음성 품질을 확인해보세요."),
            height=150,
            key="chatter_text_input"
        )
    elif chatter_script_source == "씬 분석 스크립트" and chatter_has_scene_data:
        # 씬별 생성 모드 UI
        st.info(f"📊 총 **{len(chatter_scenes_data)}개** 씬이 분석되어 있습니다.")

        # 생성 모드 선택
        chatter_generation_mode = st.radio(
            "🎯 생성 모드",
            options=["씬별 개별 생성", "전체 합쳐서 생성"],
            horizontal=True,
            key="chatter_generation_mode",
            help="씬별 개별 생성: 각 씬마다 별도 음성 파일 생성\n전체 합쳐서 생성: 모든 씬을 하나의 파일로 생성"
        )

        st.markdown("---")

        if chatter_generation_mode == "씬별 개별 생성":
            st.markdown("**📋 생성할 씬 선택**")

            # 전체 선택/해제
            col_sel1, col_sel2 = st.columns([1, 3])
            with col_sel1:
                chatter_select_all = st.checkbox("전체 선택", value=True, key="chatter_select_all_scenes")

            # 씬 목록 표시
            chatter_selected_scenes = []
            for idx, scene in enumerate(chatter_scenes_data):
                scene_id = scene.get('scene_id', idx + 1)
                scene_text = scene.get('script_text', '')
                char_count = len(scene_text)
                duration_est = scene.get('duration_estimate', char_count // 10)

                # 체크박스와 미리보기를 같은 행에
                col_check, col_info = st.columns([1, 4])

                with col_check:
                    is_selected = st.checkbox(
                        f"씬 {scene_id}",
                        value=chatter_select_all,
                        key=f"chatter_scene_select_{scene_id}"
                    )

                with col_info:
                    with st.expander(f"{scene_text[:40]}... ({char_count}자, ~{duration_est}초)", expanded=False):
                        st.text_area(
                            "내용",
                            value=scene_text,
                            height=100,
                            disabled=True,
                            key=f"chatter_scene_preview_{scene_id}"
                        )

                if is_selected:
                    chatter_selected_scenes.append({
                        "scene_id": scene_id,
                        "text": scene_text,
                        "char_count": char_count,
                        "duration_estimate": duration_est
                    })

            # 선택 요약
            total_chars = sum(s["char_count"] for s in chatter_selected_scenes)
            st.success(f"✅ **{len(chatter_selected_scenes)}개** 씬 선택됨 (총 {total_chars:,}자)")

            # 전체 텍스트 (미리보기용)
            script_text = "\n\n".join([s["text"] for s in chatter_selected_scenes]) if chatter_selected_scenes else ""

        else:
            # 전체 합쳐서 생성 모드
            full_text = "\n\n".join([s.get('script_text', '') for s in chatter_scenes_data])
            script_text = full_text

            # 메타 정보
            total_chars = sum(len(s.get('script_text', '')) for s in chatter_scenes_data)
            total_duration = sum(s.get('duration_estimate', 10) for s in chatter_scenes_data)

            cols = st.columns(3)
            cols[0].metric("총 씬 수", f"{len(chatter_scenes_data)}개")
            cols[1].metric("총 글자 수", f"{total_chars:,}자")
            cols[2].metric("예상 길이", f"{total_duration // 60}분 {total_duration % 60}초")

            st.text_area(
                "전체 스크립트 (읽기 전용)",
                value=full_text,
                height=150,
                disabled=True,
                key="chatter_full_script_preview"
            )

            # 전체 씬을 선택된 씬으로 설정
            chatter_selected_scenes = [{
                "scene_id": s.get('scene_id', idx + 1),
                "text": s.get('script_text', ''),
                "char_count": len(s.get('script_text', '')),
                "duration_estimate": s.get('duration_estimate', 10)
            } for idx, s in enumerate(chatter_scenes_data)]

    elif chatter_script_source in chatter_script_data:
        script_text = chatter_script_data[chatter_script_source]
        st.text_area(f"{chatter_script_source}", value=script_text, height=150, disabled=True, key="chatter_script_preview")
    else:
        script_text = ""
        st.warning("생성된 스크립트가 없습니다. 먼저 스크립트 생성 또는 씬 분석을 해주세요.")

    if script_text:
        st.caption(f"📊 {len(script_text)}자 | 예상 시간: 약 {max(1, len(script_text) // 100)}분")

    st.markdown("---")

    # === 생성 모드 옵션 (프리뷰/전체, 청크 설정) ===
    gen_options = render_chatterbox_generation_options()

    # === 음성 정규화 옵션 (씬별 일관성) ===
    norm_options = render_normalization_options()

    st.markdown("---")

    # === 생성 버튼 ===
    # 씬별 개별 생성 모드일 때
    if chatter_script_source == "씬 분석 스크립트" and chatter_has_scene_data and chatter_generation_mode == "씬별 개별 생성":
        # 씬별 생성 - 새로운 robust 함수 사용
        btn_label = f"🎤 씬별 생성 ({len(chatter_selected_scenes)}개)"
        if gen_options["mode"] == "preview":
            btn_label += " [프리뷰]"
        if norm_options["enabled"]:
            btn_label += " + 정규화"

        if st.button(
            btn_label,
            type="primary",
            use_container_width=True,
            disabled=len(chatter_selected_scenes) == 0 or not server_status,
            key="generate_chatterbox_by_scenes"
        ):
            _handle_chatterbox_scenes_generation(
                scenes=chatter_selected_scenes,
                voice_path=voice_path,
                params={
                    "cfg_weight": cfg_weight,
                    "exaggeration": exaggeration,
                    "temperature": temperature,
                    "speed": speed,
                    "seed": seed
                },
                gen_options=gen_options,
                norm_options=norm_options
            )
    else:
        # 일반 생성 모드 - 프리뷰/전체 통합
        btn_label = "🎤 TTS 생성"
        if gen_options["mode"] == "preview":
            btn_label = "👁️ 프리뷰 생성"
        else:
            btn_label = "🎬 전체 TTS 생성"
        if norm_options["enabled"]:
            btn_label += " + 정규화"

        if st.button(
            btn_label,
            type="primary",
            use_container_width=True,
            disabled=not script_text or not server_status,
            key="generate_chatterbox_robust"
        ):
            _handle_chatterbox_single_generation(
                text=script_text,
                voice_path=voice_path,
                params={
                    "cfg_weight": cfg_weight,
                    "exaggeration": exaggeration,
                    "temperature": temperature,
                    "speed": speed,
                    "seed": seed
                },
                gen_options=gen_options,
                norm_options=norm_options
            )


def _handle_chatterbox_single_generation(text, voice_path, params, gen_options, norm_options=None):
    """단일 텍스트 Chatterbox 생성 핸들러 (청크 분할 + 재시도 + 정규화)"""

    if norm_options is None:
        norm_options = {"enabled": False}

    result_container = st.container()

    with result_container:
        progress_bar = st.progress(0, text="준비 중...")
        status_text = st.empty()

        voice_name = os.path.basename(voice_path) if voice_path else "기본 음성"
        mode_label = "프리뷰" if gen_options["mode"] == "preview" else "전체"
        norm_label = " + 정규화" if norm_options.get("enabled") else ""

        status_text.info(f"🎙️ {mode_label}{norm_label} TTS 생성 준비 중... (참조 음성: {voice_name})")

        # ⭐ 참조 음성 최적화 (긴 음성 → 15~30초 추출)
        optimized_voice_path = voice_path
        if voice_path:
            try:
                from pydub import AudioSegment
                voice_audio = AudioSegment.from_file(voice_path)
                voice_duration = len(voice_audio) / 1000

                if voice_duration > 60:  # 60초 이상이면 최적화
                    status_text.text(f"🔍 참조 음성 최적화 중... ({voice_duration:.0f}초 → 20초)")
                    optimized_voice_path = optimize_voice_for_cloning(voice_path)

                    if optimized_voice_path != voice_path:
                        opt_audio = AudioSegment.from_file(optimized_voice_path)
                        print(f"[VoiceOptimizer] 최적화 적용: {voice_duration:.0f}초 → {len(opt_audio)/1000:.0f}초")
            except Exception as e:
                print(f"[VoiceOptimizer] 최적화 실패: {e}")
                optimized_voice_path = voice_path

        def progress_callback(current, total, message):
            if total > 0:
                progress_bar.progress((current / total), text=message)
            status_text.text(message)

        # Robust 생성 함수 호출
        result = generate_chatterbox_tts_robust(
            text=text,
            voice_ref_path=optimized_voice_path,  # ⭐ 최적화된 음성 사용
            params=params,
            mode=gen_options["mode"],
            preview_length=gen_options["preview_length"],
            chunk_size=gen_options["chunk_size"],
            repetition_penalty=gen_options["repetition_penalty"],
            max_retries=gen_options["max_retries"],
            pause_ms=gen_options["pause_ms"],
            progress_callback=progress_callback
        )

        # 정규화 적용 (활성화된 경우)
        if result.get("success") and norm_options.get("enabled"):
            progress_bar.progress(0.9, text="음성 정규화 중...")
            status_text.text("🎚️ 음성 정규화 적용 중...")
            result = apply_normalization_to_result(result, text, norm_options)

        progress_bar.progress(1.0, text="완료!")

        if result.get("success"):
            stats = result.get("stats", {})
            mode_info = "프리뷰" if result.get("mode") == "preview" else "전체"
            norm_info = " (정규화됨)" if result.get("normalized") else ""

            # 성공 메시지
            if stats.get("truncated_count", 0) > 0:
                status_text.warning(
                    f"⚠️ {mode_info} 생성 완료{norm_info} (일부 잘림 경고)\n"
                    f"청크: {stats['success_count']}/{stats['total_chunks']}개 성공, "
                    f"길이: {result.get('final_duration', result['duration']):.1f}초"
                )
            else:
                status_text.success(
                    f"✅ {mode_info} 생성 완료{norm_info}! "
                    f"청크: {stats['success_count']}/{stats['total_chunks']}개, "
                    f"길이: {result.get('final_duration', result['duration']):.1f}초"
                )

            # 오디오 재생
            if result.get("audio_data"):
                st.audio(result["audio_data"], format="audio/wav")

                # 다운로드 버튼
                timestamp = int(time.time())
                st.download_button(
                    "⬇️ 오디오 다운로드 (WAV)",
                    data=result["audio_data"],
                    file_name=f"chatterbox_{mode_info}_{timestamp}.wav",
                    mime="audio/wav",
                    key=f"download_chatterbox_robust_{timestamp}"
                )

            # 청크별 상세 정보
            with st.expander("📊 생성 상세 정보", expanded=False):
                st.json({
                    "mode": result.get("mode"),
                    "original_length": result.get("original_length"),
                    "processed_length": result.get("processed_length"),
                    "total_duration": f"{result['duration']:.2f}초",
                    "chunks": stats
                })

                # 청크별 상태
                if result.get("chunks_info"):
                    st.markdown("**청크별 결과:**")
                    for chunk in result["chunks_info"]:
                        if chunk.get("status") == "success":
                            st.success(f"✅ 청크 {chunk['index']}: {chunk['text_preview']} ({chunk['duration']:.1f}초)")
                        elif chunk.get("status") == "truncated":
                            st.warning(f"⚠️ 청크 {chunk['index']}: {chunk['text_preview']} - {chunk.get('warning', '잘림')}")
                        else:
                            st.error(f"❌ 청크 {chunk['index']}: {chunk.get('error', '실패')}")
        else:
            status_text.error(f"❌ 생성 실패: {result.get('error', '알 수 없는 오류')}")

            # 실패 상세 정보
            if result.get("chunks_info"):
                with st.expander("상세 오류 정보"):
                    for chunk in result["chunks_info"]:
                        if chunk.get("status") == "failed":
                            st.error(f"청크 {chunk['index']}: {chunk.get('error', '실패')}")


def _handle_chatterbox_scenes_generation(scenes, voice_path, params, gen_options, norm_options=None):
    """씬별 Chatterbox 생성 핸들러 (순차/병렬 + 청크 분할 + 재시도 + 정밀 정규화)"""

    if norm_options is None:
        norm_options = {"enabled": False}

    progress_bar = st.progress(0)
    status_text = st.empty()
    time_display = st.empty()
    results_container = st.container()

    # 출력 디렉토리 설정
    output_dir = st.session_state.get("tts_output_dir", "data/tts")
    timestamp = int(time.time())
    scene_output_dir = os.path.join(output_dir, f"chatterbox_scenes_{timestamp}")
    os.makedirs(scene_output_dir, exist_ok=True)

    generated_files = []
    total_scenes = len(scenes)

    # 🔧 Seed 일관성 보장: 전체 씬에 동일한 seed 사용
    import random
    scene_seed = params.get("seed")
    if scene_seed is None:
        scene_seed = random.randint(0, 2**31 - 1)
        print(f"[TTS] 씬별 생성: 랜덤 seed 고정 → {scene_seed}")
    else:
        print(f"[TTS] 씬별 생성: 사용자 지정 seed → {scene_seed}")

    # params 복사본에 고정 seed 적용
    scene_params = params.copy()
    scene_params["seed"] = scene_seed

    # ⭐ 참조 음성 최적화 (긴 음성 → 15~30초 추출)
    optimized_voice_path = voice_path
    if voice_path:
        try:
            from pydub import AudioSegment
            voice_audio = AudioSegment.from_file(voice_path)
            voice_duration = len(voice_audio) / 1000

            if voice_duration > 60:  # 60초 이상이면 최적화
                status_text.text(f"🔍 참조 음성 최적화 중... ({voice_duration:.0f}초 → 20초)")
                optimized_voice_path = optimize_voice_for_cloning(voice_path)

                if optimized_voice_path != voice_path:
                    opt_audio = AudioSegment.from_file(optimized_voice_path)
                    print(f"[VoiceOptimizer] 씬별 생성: 최적화 적용 {voice_duration:.0f}초 → {len(opt_audio)/1000:.0f}초")
        except Exception as e:
            print(f"[VoiceOptimizer] 씬별 생성: 최적화 실패 - {e}")
            optimized_voice_path = voice_path

    scene_params["voice_ref_path"] = optimized_voice_path  # ⭐ 최적화된 음성 사용

    # 처리 방식 옵션 확인
    use_sequential = gen_options.get("use_sequential", True)
    use_smart_chunking = gen_options.get("use_smart_chunking", True)
    timeout_per_scene = gen_options.get("timeout_per_scene", 180)
    max_concurrent = gen_options.get("max_concurrent", 2)
    chunk_size = gen_options.get("chunk_size", 70)

    voice_info = os.path.basename(voice_path) if voice_path else "기본 음성"
    total_start = time.time()

    # 씬 데이터 준비
    scene_list = [
        {"scene_id": s.get("scene_id", idx + 1), "text": s.get("text", "")}
        for idx, s in enumerate(scenes)
        if s.get("text", "").strip()
    ]

    if use_sequential:
        # ============================================================
        # 🚀 병렬 생성 모드 (동시 3개 처리 - 40% 속도 향상!)
        # ============================================================
        parallel_workers = 4  # RTX 5070 + FP16 최적화로 4개 동시 처리
        mode_label = f"🚀 병렬 생성 (동시 {parallel_workers}개)"
        status_text.info(f"{mode_label} ({total_scenes}개 씬) - {voice_info}")
        print(f"\n[TTS] 🚀 병렬 생성 모드 - 동시 {parallel_workers}개 처리!")

        def parallel_gen_progress(current, total, message):
            progress = current / total * (0.8 if norm_options.get("enabled") else 1.0)
            progress_bar.progress(min(progress, 1.0))
            status_text.text(f"🚀 {message}")
            elapsed = time.time() - total_start
            time_display.text(f"⏱️ 경과: {elapsed:.0f}초")

        try:
            # 🎯 순차 생성 모드 (GPU 1개 환경 최적화)
            # 병렬은 서버에서 큐잉되어 실제로는 순차 + 오버헤드
            generated_files = generate_scenes_parallel(
                scenes=scene_list,
                params=scene_params,
                max_workers=parallel_workers,
                timeout_per_scene=timeout_per_scene,
                use_sequential=True,  # ⭐ 순차 모드 (GPU 1개 최적)
                progress_callback=parallel_gen_progress
            )

            gen_time = time.time() - total_start
            success_count = sum(1 for f in generated_files if f.get("success") and f.get("audio_data"))
            print(f"[TTS] 🎯 순차 생성 완료: {success_count}/{total_scenes}개, {gen_time:.1f}초")
            print(f"[TTS] 씬당 평균: {gen_time/total_scenes:.1f}초")

        except Exception as e:
            print(f"[TTS] 병렬 생성 오류: {e}")
            st.error(f"생성 오류: {e}")
            generated_files = []

    else:
        # ============================================================
        # 🚀 병렬 처리 모드 (빠르지만 타임아웃 위험)
        # ============================================================
        status_text.info(f"🚀 병렬 생성 시작 ({total_scenes}개 씬, 동시 {max_concurrent}개) - {voice_info}")

        def parallel_progress(current, total, message):
            progress = current / total * (0.8 if norm_options.get("enabled") else 1.0)
            progress_bar.progress(min(progress, 1.0))
            status_text.text(f"🚀 {message} ({current}/{total})")
            elapsed = time.time() - total_start
            time_display.text(f"⏱️ 경과: {elapsed:.0f}초")

        try:
            parallel_results = run_threaded_generation(
                scenes=scene_list,
                params=scene_params,
                max_workers=max_concurrent,
                progress_callback=parallel_progress
            )

            # 결과 변환
            for pr in parallel_results:
                scene_id = pr.get("scene_id", 0)
                scene_text = next((s["text"] for s in scene_list if s["scene_id"] == scene_id), "")

                if pr.get("success"):
                    generated_files.append({
                        "scene_id": scene_id,
                        "audio_data": pr.get("audio_data"),
                        "text": scene_text,
                        "text_preview": scene_text[:50] + "..." if len(scene_text) > 50 else scene_text,
                        "char_count": len(scene_text),
                        "duration": pr.get("duration", 0),
                        "chunks_count": 1,
                        "status": "success",
                        "success": True
                    })
                else:
                    generated_files.append({
                        "scene_id": scene_id,
                        "audio_data": None,
                        "text": scene_text,
                        "error": pr.get("error", "생성 실패"),
                        "status": "failed",
                        "success": False
                    })

            gen_time = time.time() - total_start
            success_count = sum(1 for f in generated_files if f.get("success"))
            print(f"[TTS] 병렬 생성 완료: {success_count}/{total_scenes}개, {gen_time:.1f}초")

        except Exception as e:
            print(f"[TTS] 병렬 생성 실패: {e}")
            st.error(f"병렬 생성 오류: {e}")
            generated_files = []

    gen_time = time.time() - total_start

    # ============================================================
    # ⭐ 통합 단일 패스 처리 (정규화 + 가속보정 + 미세조정)
    # ============================================================
    # 기존 파이프라인 (문제):
    #   1단계: normalize_perfect (FFmpeg 2~3회)
    #   2단계: correct_all_speed_acceleration (FFmpeg 4회)
    #   3단계: normalize_segments_all (FFmpeg 1~2회)
    #   → 총 6~9회 FFmpeg → 울림, 변조, 품질 저하
    #
    # 새 파이프라인 (해결):
    #   process_all_unified (구간당 FFmpeg 1회)
    #   → 품질 유지, 울림 없음
    # ============================================================
    if norm_options.get("enabled") and generated_files:
        status_text.text("🔧 통합 처리 중... (정규화 + 가속보정 + 미세조정)")
        print("\n" + "="*60)
        print("[TTS] ⭐ 통합 단일 패스 처리 시작")
        print("[TTS] ⭐ FFmpeg 최소 호출 → 울림/변조 방지")
        print("[TTS] ⭐ 적응형 가속 보정 → 정확한 속도 균일화")
        print("="*60)

        # 처리 전 상태 분석
        pre_stats = analyze_normalization_stats(generated_files)
        if not pre_stats.get("error"):
            print(f"[TTS] 처리 전 발화속도: {pre_stats['rate_min']:.2f} ~ {pre_stats['rate_max']:.2f} (±{pre_stats['rate_deviation_pct']:.1f}%)")

        def unified_progress(current, total, message):
            base_progress = 0.75
            step = (current / total) * 0.23  # 0.75 ~ 0.98
            progress_bar.progress(min(base_progress + step, 0.98))
            status_text.text(f"🔧 {message}")

        # ⭐ 통합 단일 패스 처리
        # 참조 음성 분석 결과 또는 기본값 사용
        target_speed = st.session_state.get("target_speech_rate", 8.5)
        print(f"[TTS] 목표 발화속도: {target_speed:.2f} 글자/초 (참조 음성 기반)")

        generated_files = process_all_unified(
            generated_files,
            target_speed=target_speed,  # ⭐ 참조 음성 기반 목표
            accel_profile="adaptive",   # 적응형 가속 보정
            progress_callback=unified_progress
        )

        # 처리 후 상태 확인
        post_stats = analyze_normalization_stats(generated_files)
        if not post_stats.get("error"):
            print(f"[TTS] 처리 후 발화속도: {post_stats['rate_min']:.2f} ~ {post_stats['rate_max']:.2f} (±{post_stats['rate_deviation_pct']:.1f}%)")
            improvement = pre_stats.get('rate_deviation_pct', 0) - post_stats.get('rate_deviation_pct', 0)
            if improvement > 0:
                print(f"[TTS] ✅ 편차 개선: {improvement:.1f}% 감소")

        print("[TTS] 통합 처리 완료")
        print("="*60 + "\n")

    total_time = time.time() - total_start
    time_display.text(f"⏱️ 총 {total_time:.1f}초 (생성: {gen_time:.1f}초)")

    # 파일 저장 (정규화 후)
    for file_info in generated_files:
        if file_info.get("audio_data") and file_info["status"] in ["success", "partial"]:
            audio_path = os.path.join(scene_output_dir, f"scene_{file_info['scene_id']:02d}.wav")
            with open(audio_path, "wb") as f:
                f.write(file_info["audio_data"])
            file_info["path"] = audio_path

    progress_bar.progress(1.0)
    status_text.empty()

    # 결과 표시 (안전한 접근)
    # ⭐ 핵심: success=True AND audio_data 있어야 성공
    success_count = len([
        f for f in generated_files
        if f and f.get("success") == True and f.get("audio_data")
    ])
    failed_count = len([
        f for f in generated_files
        if f and (not f.get("success") or not f.get("audio_data"))
    ])
    normalized_count = len([f for f in generated_files if f and f.get("normalized")])

    # 디버그 로깅
    print(f"\n[TTS 결과] 성공: {success_count}, 실패: {failed_count}")
    for idx, f in enumerate(generated_files):
        if f:
            has_audio = "O" if f.get("audio_data") else "X"
            print(f"  [{idx+1}] success={f.get('success')}, audio={has_audio}, status={f.get('status')}")

    with results_container:
        if success_count > 0:
            norm_info = f" (정규화: {normalized_count}개)" if norm_options.get("enabled") else ""
            st.success(f"✅ **{success_count}/{total_scenes}개** 씬 생성 완료!{norm_info}")

            st.markdown("### 🎵 생성된 음성 파일")

            for file_info in generated_files:
                if not file_info:
                    continue
                scene_id = file_info.get("scene_id", 0)
                file_status = file_info.get("status", "")
                has_audio = file_info.get("audio_data") is not None
                is_success = file_info.get("success") == True and has_audio

                if is_success or file_status in ["success", "partial"]:
                    status_icon = "✅" if is_success else "⚠️"
                    text_preview = file_info.get("text_preview", file_info.get("text", "")[:50])
                    char_count = file_info.get("char_count", len(file_info.get("text", "")))
                    with st.expander(f"{status_icon} 씬 {scene_id} - {text_preview} ({char_count}자)", expanded=True):
                        col1, col2 = st.columns([3, 1])

                        with col1:
                            if file_info.get("audio_data"):
                                st.audio(file_info["audio_data"], format="audio/wav")
                            elif file_info.get("path"):
                                st.audio(file_info["path"])
                            st.caption(f"⏱️ {file_info.get('duration', 0):.1f}초 | 청크: {file_info.get('chunks_count', 1)}개")

                        with col2:
                            if file_info.get("audio_data"):
                                st.download_button(
                                    "⬇️ 다운로드",
                                    data=file_info["audio_data"],
                                    file_name=f"scene_{scene_id:02d}.wav",
                                    mime="audio/wav",
                                    key=f"chatter_robust_dl_scene_{scene_id}_{timestamp}",
                                    use_container_width=True
                                )
                else:
                    st.error(f"❌ 씬 {scene_id} 생성 실패: {file_info.get('error', '알 수 없는 오류')}")

            # 전체 ZIP 다운로드
            if success_count > 1:
                st.markdown("---")
                st.markdown("### 📦 일괄 다운로드")

                import zipfile

                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                    for file_info in generated_files:
                        if file_info["status"] in ["success", "partial"] and file_info.get("audio_data"):
                            scene_id = file_info["scene_id"]
                            zip_file.writestr(f"scene_{scene_id:02d}.wav", file_info["audio_data"])

                zip_buffer.seek(0)

                st.download_button(
                    f"📦 전체 다운로드 (ZIP, {success_count}개 파일)",
                    data=zip_buffer.getvalue(),
                    file_name=f"chatterbox_scenes_{timestamp}.zip",
                    mime="application/zip",
                    key=f"chatter_robust_dl_all_zip_{timestamp}",
                    use_container_width=True
                )

            # 세션에 저장
            st.session_state["last_chatterbox_scenes"] = generated_files
            st.session_state["last_chatterbox_output_dir"] = scene_output_dir

        if failed_count > 0:
            st.warning(f"⚠️ {failed_count}개 씬 생성 실패")


def generate_chatterbox_tts(text, cfg_weight, exaggeration, temperature, speed, seed, voice_ref_path):
    """Chatterbox TTS 생성 (개선된 로딩 UI)"""

    # 결과 표시 영역
    result_container = st.container()

    with result_container:
        # 단계별 진행 상황 표시
        progress_bar = st.progress(0, text="준비 중...")
        status_text = st.empty()

        # 참조 음성 정보
        voice_name = os.path.basename(voice_ref_path) if voice_ref_path else "기본 음성"

        # 1단계: 준비
        status_text.info(f"🎙️ TTS 생성 준비 중... (참조 음성: {voice_name})")
        progress_bar.progress(10, text="서버 연결 확인...")

        try:
            # 2단계: 서버 상태 확인 (캐시 사용)
            if not check_chatterbox_server():
                status_text.error("❌ Chatterbox 서버에 연결할 수 없습니다.")
                progress_bar.empty()
                return

            progress_bar.progress(20, text="요청 준비 중...")

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

            # 3단계: TTS 생성 요청
            progress_bar.progress(30, text="🎤 음성 생성 중... (10~30초 소요)")
            status_text.info(f"🔄 Chatterbox에서 음성 생성 중... ({len(text)}자)")

            start_time = time.time()
            r = requests.post(f"{CHATTERBOX_URL}/generate", json=payload, timeout=180)
            elapsed = time.time() - start_time

            # 4단계: 응답 처리
            progress_bar.progress(80, text="응답 처리 중...")

            if r.status_code == 200:
                result = r.json()

                if result.get("success"):
                    progress_bar.progress(90, text="오디오 로딩 중...")

                    # 오디오 다운로드
                    audio_url = result.get("audio_url", "")
                    audio_data = None

                    if audio_url:
                        full_url = f"{CHATTERBOX_URL}{audio_url}"
                        try:
                            audio_response = requests.get(full_url, timeout=30)
                            if audio_response.status_code == 200:
                                audio_data = audio_response.content
                        except Exception as e:
                            st.warning(f"오디오 로드 실패: {e}")

                    # 완료!
                    progress_bar.progress(100, text="완료!")
                    voice_info = f"🎤 {voice_name}"
                    status_text.success(f"✅ 생성 완료! (길이: {result.get('duration_seconds', 0):.1f}초, 처리시간: {elapsed:.1f}s, {voice_info})")

                    # 오디오 재생
                    if audio_data:
                        st.audio(audio_data, format="audio/wav")

                        # 다운로드 버튼
                        timestamp = int(time.time())
                        st.download_button(
                            "⬇️ 오디오 다운로드 (WAV)",
                            data=audio_data,
                            file_name=f"chatterbox_{timestamp}.wav",
                            mime="audio/wav",
                            key=f"download_chatterbox_{timestamp}"
                        )

                    # 생성 정보
                    with st.expander("📊 생성 정보", expanded=False):
                        st.json({
                            "duration_seconds": result.get("duration_seconds"),
                            "seed_used": result.get("seed_used"),
                            "processing_time": f"{elapsed:.2f}s",
                            "text_length": len(text),
                            "voice_ref": voice_name
                        })
                else:
                    progress_bar.empty()
                    status_text.error(f"❌ 생성 실패: {result.get('error', 'Unknown error')}")
            else:
                progress_bar.empty()
                status_text.error(f"❌ 서버 오류: HTTP {r.status_code}")

        except requests.exceptions.Timeout:
            progress_bar.empty()
            status_text.error("⏱️ 요청 시간 초과 (180초). 텍스트가 너무 길거나 서버가 바쁠 수 있습니다.")
        except requests.exceptions.ConnectionError:
            progress_bar.empty()
            status_text.error("🔌 서버 연결 실패. Chatterbox 서버가 실행 중인지 확인하세요.")
            invalidate_chatterbox_cache()  # 캐시 무효화
        except Exception as e:
            progress_bar.empty()
            status_text.error(f"❌ 오류: {e}")
            import traceback
            with st.expander("상세 오류"):
                st.code(traceback.format_exc())


def generate_chatterbox_tts_by_scenes(scenes, cfg_weight, exaggeration, temperature, speed, seed, voice_ref_path):
    """씬별 Chatterbox TTS 개별 생성"""

    # 진행 상황 UI
    progress_bar = st.progress(0)
    status_text = st.empty()
    results_container = st.container()

    # 출력 디렉토리 설정
    output_dir = st.session_state.get("tts_output_dir", "data/tts")
    timestamp = int(time.time())
    scene_output_dir = os.path.join(output_dir, f"chatterbox_scenes_{timestamp}")
    os.makedirs(scene_output_dir, exist_ok=True)

    generated_files = []
    total_scenes = len(scenes)

    try:
        # 씬별 생성 루프
        for idx, scene in enumerate(scenes):
            scene_id = scene.get("scene_id", idx + 1)
            scene_text = scene.get("text", "")

            if not scene_text.strip():
                continue

            # 진행 상황 업데이트
            progress_bar.progress((idx + 1) / total_scenes)
            voice_info = os.path.basename(voice_ref_path) if voice_ref_path else "기본 음성"
            status_text.text(f"씬 {scene_id} 생성 중... ({idx + 1}/{total_scenes}) - {voice_info}")

            # 출력 파일 경로
            audio_path = os.path.join(scene_output_dir, f"scene_{scene_id:02d}.wav")

            try:
                # Chatterbox TTS API 호출
                payload = {
                    "text": scene_text,
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
                        # 오디오 파일 다운로드 및 저장
                        audio_url = result.get("audio_url", "")
                        if audio_url:
                            full_url = f"{CHATTERBOX_URL}{audio_url}"
                            audio_response = requests.get(full_url, timeout=30)
                            if audio_response.status_code == 200:
                                with open(audio_path, "wb") as f:
                                    f.write(audio_response.content)

                                generated_files.append({
                                    "scene_id": scene_id,
                                    "path": audio_path,
                                    "text_preview": scene_text[:50] + "..." if len(scene_text) > 50 else scene_text,
                                    "char_count": len(scene_text),
                                    "duration": result.get("duration_seconds", 0),
                                    "processing_time": elapsed,
                                    "status": "success"
                                })
                            else:
                                raise Exception(f"오디오 다운로드 실패: {audio_response.status_code}")
                        else:
                            raise Exception("오디오 URL이 없습니다")
                    else:
                        raise Exception(result.get("error", "알 수 없는 오류"))
                else:
                    raise Exception(f"서버 오류: {r.status_code}")

            except requests.exceptions.ConnectionError:
                # 연결 오류 시 캐시 무효화
                invalidate_chatterbox_cache()
                generated_files.append({
                    "scene_id": scene_id,
                    "path": None,
                    "error": "서버 연결 실패 - Chatterbox 서버가 실행 중인지 확인하세요",
                    "status": "failed"
                })
                # 연결 오류 발생 시 나머지 씬도 실패할 가능성이 높으므로 중단
                status_text.error("🔌 서버 연결이 끊어졌습니다. 생성을 중단합니다.")
                break
            except requests.exceptions.Timeout:
                generated_files.append({
                    "scene_id": scene_id,
                    "path": None,
                    "error": "서버 응답 시간 초과 (120초)",
                    "status": "failed"
                })
            except Exception as e:
                generated_files.append({
                    "scene_id": scene_id,
                    "path": None,
                    "error": str(e),
                    "status": "failed"
                })

        progress_bar.progress(1.0)
        status_text.empty()

        # 결과 표시
        success_count = len([f for f in generated_files if f["status"] == "success"])
        failed_count = len([f for f in generated_files if f["status"] == "failed"])

        with results_container:
            if success_count > 0:
                st.success(f"✅ **{success_count}/{total_scenes}개** 씬 생성 완료!")

                # 씬별 오디오 플레이어 및 다운로드
                st.markdown("### 🎵 생성된 음성 파일")

                for file_info in generated_files:
                    scene_id = file_info["scene_id"]

                    if file_info["status"] == "success":
                        with st.expander(f"📢 씬 {scene_id} - {file_info['text_preview']} ({file_info['char_count']}자)", expanded=True):
                            col1, col2 = st.columns([3, 1])

                            with col1:
                                st.audio(file_info["path"])
                                st.caption(f"⏱️ {file_info.get('duration', 0):.1f}초 | 처리시간: {file_info.get('processing_time', 0):.1f}s")

                            with col2:
                                with open(file_info["path"], "rb") as f:
                                    st.download_button(
                                        "⬇️ 다운로드",
                                        data=f.read(),
                                        file_name=f"scene_{scene_id:02d}.wav",
                                        mime="audio/wav",
                                        key=f"chatter_download_scene_{scene_id}_{timestamp}",
                                        use_container_width=True
                                    )
                    else:
                        st.error(f"❌ 씬 {scene_id} 생성 실패: {file_info.get('error', '알 수 없는 오류')}")

                # 전체 ZIP 다운로드
                if success_count > 1:
                    st.markdown("---")
                    st.markdown("### 📦 일괄 다운로드")

                    # ZIP 파일 생성
                    import zipfile
                    import io

                    zip_buffer = io.BytesIO()
                    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                        for file_info in generated_files:
                            if file_info["status"] == "success" and file_info["path"]:
                                scene_id = file_info["scene_id"]
                                zip_file.write(file_info["path"], f"scene_{scene_id:02d}.wav")

                    zip_buffer.seek(0)

                    st.download_button(
                        f"📦 전체 다운로드 (ZIP, {success_count}개 파일)",
                        data=zip_buffer.getvalue(),
                        file_name=f"chatterbox_scenes_{timestamp}.zip",
                        mime="application/zip",
                        key=f"chatter_download_all_zip_{timestamp}",
                        use_container_width=True
                    )

                # 세션에 저장
                st.session_state["last_chatterbox_scenes"] = generated_files
                st.session_state["last_chatterbox_output_dir"] = scene_output_dir

            if failed_count > 0:
                st.warning(f"⚠️ {failed_count}개 씬 생성 실패")

    except Exception as e:
        status_text.error(f"오류: {e}")
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
