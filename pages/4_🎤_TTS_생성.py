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
import json

# 경로 설정
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 프로젝트 매니저 임포트 (씬 분석 결과 로드용)
from utils.project_manager import get_current_project

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

# TTS 다운로드 컴포넌트
from components.tts_audio_downloader import (
    render_tts_download_section,
    get_simple_filename,
    TTSAudioDownloader
)

# TTS 텍스트 정규화 (콤마 숫자, 영어 약어 등)
from utils.text_normalizer import normalize_for_tts

# AI 텍스트 전처리 (영어 → 발음 변환)
from components.ai_preprocessing_panel import (
    render_ai_preprocessing_panel,
    apply_preprocessing_to_scenes
)

# 씬 구간 선택 컴포넌트
from components.scene_range_selector import (
    render_scene_range_selector,
    parse_range_string,
    format_selection_summary
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

# ⭐ 참조 음성 분석기 v2.2 (텍스트 기반 정확 측정 + 파라미터 자동 추천 + 최적화)
from utils.voice_analyzer import (
    VoiceAnalyzer,
    analyze_voice_and_get_params,
    analyze_voice_with_text,
    get_voice_transcript,
    set_voice_transcript,
    get_profile_manager,
    optimize_voice_for_cloning,  # 참조 음성 최적화 (15~30초 추출)
    is_voice_optimization_needed,  # ⭐ 최적화 필요 여부 확인
    get_optimized_voice_path,  # ⭐ 최적화 버전 경로 반환
    optimize_and_register_voice,  # ⭐ 최적화 후 프로필 등록
    scan_optimized_versions,  # ⭐ 모든 최적화 버전 스캔
    get_version_manager,  # ⭐ 버전 관리자
    create_manual_optimized_voice  # ⭐ 수동 구간 선택 최적화
)

# ⭐ 파형 시각화 및 수동 구간 선택
from utils.waveform_visualizer import (
    WaveformVisualizer,
    get_waveform_visualizer
)

# ⭐ TTS 자연스러움 최적화 (temperature/repetition_penalty 조정)
from utils.tts_naturalness import (
    get_natural_params,
    get_base_natural_params,
    TTSNaturalnessOptimizer
)

# ⭐ TTS 설정 프리셋 관리자
from utils.preset_manager import get_preset_manager

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


# ============================================================
# 씬 분석 결과 로드 함수
# ============================================================

def load_scenes_from_json(force_reload: bool = False) -> tuple[list, bool]:
    """
    프로젝트의 scenes.json 파일에서 씬 분석 결과를 로드합니다.

    Args:
        force_reload: True이면 세션 상태를 무시하고 파일에서 강제 로드

    Returns:
        (scenes_list, is_loaded_from_file)
        - scenes_list: 씬 목록
        - is_loaded_from_file: 파일에서 새로 로드됐는지 여부
    """
    # 현재 프로젝트 정보 가져오기 (Path 객체 반환)
    project_path = get_current_project()
    if not project_path:
        return [], False

    # get_current_project()는 Path 객체를 반환함
    if not isinstance(project_path, Path):
        project_path = Path(project_path)

    scenes_json_path = project_path / "analysis" / "scenes.json"

    if not scenes_json_path.exists():
        return [], False

    try:
        # 파일 수정 시간 확인
        file_mtime = scenes_json_path.stat().st_mtime
        last_loaded_mtime = st.session_state.get("scenes_json_mtime", 0)

        # 강제 로드이거나 파일이 수정된 경우 로드
        if force_reload or file_mtime > last_loaded_mtime:
            with open(scenes_json_path, "r", encoding="utf-8") as f:
                scenes = json.load(f)

            # 세션 상태에 저장
            st.session_state["scenes"] = scenes
            st.session_state["scenes_json_mtime"] = file_mtime

            # 씬 분석 스크립트도 업데이트
            if scenes:
                script_texts = []
                for scene in scenes:
                    text = scene.get("script_text", "") or scene.get("text", "")
                    if text:
                        script_texts.append(text)
                st.session_state["scene_analysis_script"] = "\n\n".join(script_texts)

            return scenes, True
        else:
            # 세션 상태에서 반환
            return st.session_state.get("scenes", []), False

    except Exception as e:
        st.error(f"씬 데이터 로드 실패: {e}")
        return [], False


def get_scenes_json_info() -> dict:
    """
    scenes.json 파일 정보를 반환합니다.

    Returns:
        {"exists": bool, "scene_count": int, "last_modified": str, "path": str}
    """
    project_path = get_current_project()
    if not project_path:
        return {"exists": False, "scene_count": 0, "last_modified": "", "path": ""}

    # get_current_project()는 Path 객체를 반환함
    if not isinstance(project_path, Path):
        project_path = Path(project_path)

    scenes_json_path = project_path / "analysis" / "scenes.json"

    if not scenes_json_path.exists():
        return {"exists": False, "scene_count": 0, "last_modified": "", "path": str(scenes_json_path)}

    try:
        mtime = scenes_json_path.stat().st_mtime
        from datetime import datetime
        last_modified = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")

        with open(scenes_json_path, "r", encoding="utf-8") as f:
            scenes = json.load(f)

        return {
            "exists": True,
            "scene_count": len(scenes),
            "last_modified": last_modified,
            "path": str(scenes_json_path)
        }
    except Exception:
        return {"exists": False, "scene_count": 0, "last_modified": "", "path": str(scenes_json_path)}


# Chatterbox 서버 설정
CHATTERBOX_URL = "http://localhost:8100"


# ============================================================
# 음성 품질 프리셋 정의 (Chatterbox 전처리/후처리 설정)
# ============================================================

VOICE_QUALITY_PRESETS = {
    # ⭐⭐⭐ 새로운 프리셋: 원본 그대로 (Raw) ⭐⭐⭐
    "raw": {
        "name": "🎯 원본 그대로 (Raw)",
        "description": "전처리/후처리 없음. 참조 음성 특성 100% 보존. 가장 자연스러운 한국어 발음.",
        "badge": "자연스러움 ★★★★★★",
        "preprocess": {
            "enabled": False,  # ⭐ 전처리 완전 비활성화
            "noisereduce_strength": 0.0,
            "bandpass_low": 0,
            "bandpass_high": 24000,
            "noise_gate_db": -100,
            "normalize_peak": 1.0,
        },
        "postprocess": {
            "enabled": False,  # ⭐ 후처리 완전 비활성화
            "noisereduce_strength": 0.0,
            "lowpass_cutoff": 24000,
            "soft_clip": False,
        },
        "tts_params": {
            "exaggeration": 0.35,          # 낮춤 → 더 안정적
            "temperature": 0.72,           # 낮춤 → 더 일관적
            "cfg_weight": 0.65,            # 높임 → 참조 음성에 더 충실
            "repetition_penalty": 1.10,    # ⭐ 낮춤 → 자연스러운 반복
        }
    },
    # ⭐ 최소 처리 (Minimal) - 리샘플링만
    "minimal": {
        "name": "🌱 최소 처리 (Minimal)",
        "description": "리샘플링만 적용. 노이즈 제거/필터 없음. 거의 원본 수준.",
        "badge": "자연스러움 ★★★★★☆",
        "preprocess": {
            "enabled": True,
            "noisereduce_strength": 0.0,   # 노이즈 제거 없음
            "bandpass_low": 20,            # 최소 필터
            "bandpass_high": 22000,        # 거의 전체 대역
            "noise_gate_db": -80,          # 거의 없음
            "normalize_peak": 0.98,        # 거의 원본
        },
        "postprocess": {
            "enabled": True,
            "noisereduce_strength": 0.0,   # 없음
            "lowpass_cutoff": 22000,
            "soft_clip": False,
        },
        "tts_params": {
            "exaggeration": 0.40,
            "temperature": 0.55,           # 0.75 → 0.55 (일관성 강화)
            "cfg_weight": 0.70,            # 0.60 → 0.70 (참조 음성 충실)
            "repetition_penalty": 1.15,    # 추가 (자연스러운 반복)
        }
    },
    # ⭐⭐⭐ 새로운 프리셋: 발음 일관성 (Consistent) ⭐⭐⭐
    "consistent": {
        "name": "🎯 발음 일관성 (Consistent)",
        "description": "씬 간 발음 일관성 최대화. 같은 단어가 항상 같게 발음됨. 한국어 TTS 권장.",
        "badge": "일관성 ★★★★★★",
        "preprocess": {
            "enabled": True,
            "noisereduce_strength": 0.15,
            "bandpass_low": 30,
            "bandpass_high": 20000,
            "noise_gate_db": -60,
            "normalize_peak": 0.95,
        },
        "postprocess": {
            "enabled": True,
            "noisereduce_strength": 0.05,
            "lowpass_cutoff": 20000,
            "soft_clip": False,
        },
        "tts_params": {
            "exaggeration": 0.38,          # ⭐ 낮춤 → 안정적 발음
            "temperature": 0.50,           # ⭐ 낮춤 → 결정적 출력
            "cfg_weight": 0.72,            # ⭐ 높임 → 참조 음성에 충실
            "repetition_penalty": 1.10,    # ⭐ 낮춤 → 자연스러운 반복
        }
    },
    # ⭐⭐⭐ 새로운 프리셋: 표현력 (Expressive) ⭐⭐⭐
    "expressive": {
        "name": "🎭 표현력 (Expressive)",
        "description": "감정 표현 풍부, 자연스러운 억양. 딱딱하지 않은 생동감 있는 음성.",
        "badge": "표현력 ★★★★★",
        "preprocess": {
            "enabled": True,
            "noisereduce_strength": 0.10,
            "bandpass_low": 25,
            "bandpass_high": 21000,
            "noise_gate_db": -65,
            "normalize_peak": 0.95,
        },
        "postprocess": {
            "enabled": True,
            "noisereduce_strength": 0.05,
            "lowpass_cutoff": 21000,
            "soft_clip": False,
        },
        "tts_params": {
            "exaggeration": 0.65,          # ⭐ 높음 → 감정 표현 풍부
            "temperature": 0.60,           # ⭐ 적당히 높음 → 자연스러운 변화
            "cfg_weight": 0.75,            # ⭐ 높음 → 참조 음성 특성 강화
            "repetition_penalty": 1.15,    # 자연스러운 반복
        }
    },
    "ultra_natural": {
        "name": "🎙️ 완전 자연스러운",
        "description": "매우 약한 처리. 원본 특성 최대 보존. 발음 일관성 강화됨.",
        "badge": "자연스러움 ★★★★★",
        "preprocess": {
            "enabled": True,
            "noisereduce_strength": 0.15,  # 20% → 15%로 낮춤
            "bandpass_low": 30,            # 35 → 30으로 낮춤
            "bandpass_high": 20000,        # 19000 → 20000으로 높임
            "noise_gate_db": -60,          # -58 → -60으로 낮춤
            "normalize_peak": 0.95,
        },
        "postprocess": {
            "enabled": True,
            "noisereduce_strength": 0.05,  # 10% → 5%로 낮춤
            "lowpass_cutoff": 20000,       # 19000 → 20000
            "soft_clip": False,
        },
        "tts_params": {
            "exaggeration": 0.42,          # 0.45 → 0.42 (더 안정적)
            "temperature": 0.55,           # 0.78 → 0.55 (일관성 강화)
            "cfg_weight": 0.68,            # 0.55 → 0.68 (참조 음성 충실)
            "repetition_penalty": 1.12,    # 추가 (자연스러운 반복)
        }
    },
    "natural": {
        "name": "🌿 자연스러운",
        "description": "약한 처리. 자연스러운 발음과 적당한 노이즈 제거. 발음 일관성 강화됨.",
        "badge": "자연스러움 ★★★★☆",
        "preprocess": {
            "enabled": True,
            "noisereduce_strength": 0.25,  # 30% → 25%
            "bandpass_low": 35,            # 40 → 35
            "bandpass_high": 19000,        # 18000 → 19000
            "noise_gate_db": -58,          # -55 → -58
            "normalize_peak": 0.92,
        },
        "postprocess": {
            "enabled": True,
            "noisereduce_strength": 0.10,  # 15% → 10%
            "lowpass_cutoff": 19000,       # 18000 → 19000
            "soft_clip": False,
        },
        "tts_params": {
            "exaggeration": 0.45,          # 0.50 → 0.45
            "temperature": 0.58,           # 0.80 → 0.58 (일관성 강화)
            "cfg_weight": 0.65,            # 0.55 → 0.65 (참조 음성 충실)
            "repetition_penalty": 1.15,    # 추가
        }
    },
    "balanced": {
        "name": "⚖️ 균형 잡힌",
        "description": "노이즈 제거와 음질의 균형. 대부분의 경우 권장.",
        "badge": "균형 ★★★☆☆",
        "preprocess": {
            "enabled": True,
            "noisereduce_strength": 0.40,  # 45% → 40%
            "bandpass_low": 45,            # 50 → 45
            "bandpass_high": 17000,        # 16000 → 17000
            "noise_gate_db": -52,          # -50 → -52
            "normalize_peak": 0.90,
        },
        "postprocess": {
            "enabled": True,
            "noisereduce_strength": 0.20,  # 25% → 20%
            "lowpass_cutoff": 17000,       # 16000 → 17000
            "soft_clip": False,            # True → False (자연스러움)
        },
        "tts_params": {
            "exaggeration": 0.48,          # 0.50 → 0.48
            "temperature": 0.60,           # 0.80 → 0.60 (일관성 강화)
            "cfg_weight": 0.62,            # 0.50 → 0.62 (참조 음성 충실)
            "repetition_penalty": 1.18,    # 추가
        }
    },
    "broadcast": {
        "name": "🎬 방송용",
        "description": "방송/팟캐스트에 적합. 명확하고 깔끔한 발음. 일관성 강화됨.",
        "badge": "깨끗함 ★★★★☆",
        "preprocess": {
            "enabled": True,
            "noisereduce_strength": 0.45,  # 50% → 45%
            "bandpass_low": 55,            # 60 → 55
            "bandpass_high": 16000,        # 15000 → 16000
            "noise_gate_db": -50,          # -48 → -50
            "normalize_peak": 0.88,
        },
        "postprocess": {
            "enabled": True,
            "noisereduce_strength": 0.25,  # 30% → 25%
            "lowpass_cutoff": 16000,       # 15000 → 16000
            "soft_clip": True,
        },
        "tts_params": {
            "exaggeration": 0.43,          # 0.45 → 0.43
            "temperature": 0.58,           # 0.78 → 0.58 (일관성 강화)
            "cfg_weight": 0.65,            # 0.50 → 0.65 (참조 음성 충실)
            "repetition_penalty": 1.15,    # 추가
        }
    },
    "clean": {
        "name": "🔇 깨끗한",
        "description": "노이즈 최소화. 다소 딱딱하거나 기계적일 수 있음.",
        "badge": "깨끗함 ★★★★★",
        "preprocess": {
            "enabled": True,
            "noisereduce_strength": 0.60,  # 70% → 60%
            "bandpass_low": 70,            # 80 → 70
            "bandpass_high": 15000,        # 14000 → 15000
            "noise_gate_db": -48,          # -45 → -48
            "normalize_peak": 0.85,
        },
        "postprocess": {
            "enabled": True,
            "noisereduce_strength": 0.35,  # 40% → 35%
            "lowpass_cutoff": 15000,       # 14000 → 15000
            "soft_clip": True,
        },
        "tts_params": {
            "exaggeration": 0.38,          # 0.40 → 0.38
            "temperature": 0.55,           # 0.75 → 0.55 (일관성 강화)
            "cfg_weight": 0.68,            # 0.50 → 0.68 (참조 음성 충실)
            "repetition_penalty": 1.12,    # 추가
        }
    },
    "custom": {
        "name": "⚙️ 사용자 정의",
        "description": "모든 설정을 직접 조절합니다.",
        "badge": "",
        "preprocess": {
            "enabled": True,  # 사용자 정의도 기본 활성화
        },
        "postprocess": {
            "enabled": True,
        },
        "tts_params": {},
    }
}


# ============================================================
# TTS 설정 프리셋 저장/불러오기 함수
# ============================================================

def save_current_settings_as_preset(name: str, description: str = ""):
    """
    현재 세션의 TTS 설정을 프리셋으로 저장

    Returns:
        저장된 프리셋 ID 또는 None
    """
    try:
        preset_manager = get_preset_manager()

        # 현재 세션에서 설정 수집
        voice_reference = {
            "voice_name": st.session_state.get("selected_voice_name", ""),
            "voice_path": st.session_state.get("selected_voice_path", ""),
            "optimized_version": os.path.basename(
                st.session_state.get("selected_reference_voice", "")
            ) if st.session_state.get("selected_reference_voice") else "",
            "optimized_path": st.session_state.get("selected_reference_voice", "")
        }

        voice_parameters = {
            "cfg_weight": st.session_state.get("chatter_cfg", 0.5),
            "temperature": st.session_state.get("chatter_temp", 0.85),
            "exaggeration": st.session_state.get("chatter_exag", 0.5),
            "speed": st.session_state.get("chatter_speed", 1.0),
            "repetition_penalty": st.session_state.get("tts_repetition_penalty", 1.15)
        }

        quality_settings = {
            "preset_key": st.session_state.get("chatter_quality_preset", 1),
            "settings": st.session_state.get("chatter_quality_settings", {})
        }

        generation_options = {
            "generation_mode": st.session_state.get("chatter_generation_mode", "씬별 개별 생성"),
            "seed": st.session_state.get("chatter_seed_input"),
            "use_random_seed": st.session_state.get("chatter_random_seed", True),
        }

        post_processing = {
            "unified_processor_enabled": False,  # 현재 비활성화됨
            "final_adjust_enabled": False,
            "target_speed": st.session_state.get("target_speech_rate", 6.4),
        }

        # 저장
        preset_id = preset_manager.save_preset(
            name=name,
            voice_reference=voice_reference,
            voice_parameters=voice_parameters,
            quality_settings=quality_settings,
            generation_options=generation_options,
            post_processing=post_processing,
            description=description
        )

        return preset_id

    except Exception as e:
        print(f"[Preset] 저장 오류: {e}")
        return None


def apply_preset_to_session(preset: dict):
    """
    프리셋을 현재 세션에 적용

    Args:
        preset: 프리셋 딕셔너리

    ⚠️ 중요: Streamlit 위젯 key는 session_state에 저장되어 value 파라미터를 무시함!
    → 위젯 key를 삭제해야 value 파라미터가 다시 적용됨
    """
    try:
        print(f"\n[Preset] 프리셋 적용 시작: {preset.get('preset_name')}")

        # ⭐⭐⭐ 1단계: 위젯 key 삭제 (핵심!) ⭐⭐⭐
        # Streamlit 위젯 key가 session_state에 있으면 value 파라미터 무시됨
        # → 삭제해야 위젯이 value 파라미터로 다시 초기화됨
        widget_keys_to_delete = [
            "chatter_cfg_slider",
            "chatter_speed_slider",
            "chatter_exag_slider",
            "chatter_temp_slider",
            "chatter_quality_preset",
            "chatter_random_seed",
            "chatter_seed_input",
        ]

        for key in widget_keys_to_delete:
            if key in st.session_state:
                del st.session_state[key]
                print(f"  🗑️ 위젯 key 삭제: {key}")

        # ⭐⭐⭐ 2단계: 참조 음성 설정 ⭐⭐⭐
        voice_ref = preset.get("voice_reference", {})
        if voice_ref.get("voice_name"):
            st.session_state["selected_voice_name"] = voice_ref.get("voice_name", "")
            print(f"  ✅ 음성 이름: {voice_ref.get('voice_name')}")
        if voice_ref.get("voice_path"):
            st.session_state["selected_voice_path"] = voice_ref.get("voice_path", "")
        if voice_ref.get("optimized_path") and os.path.exists(voice_ref.get("optimized_path", "")):
            st.session_state["selected_reference_voice"] = voice_ref.get("optimized_path", "")
            print(f"  ✅ 최적화 버전: {os.path.basename(voice_ref.get('optimized_path', ''))}")

        # ⭐⭐⭐ 3단계: 음성 파라미터 설정 ⭐⭐⭐
        # 위젯의 value 파라미터가 읽는 키에 저장!
        params = preset.get("voice_parameters", {})
        if "cfg_weight" in params:
            st.session_state["chatter_cfg"] = params["cfg_weight"]
        if "temperature" in params:
            st.session_state["chatter_temp"] = params["temperature"]
        if "exaggeration" in params:
            st.session_state["chatter_exag"] = params["exaggeration"]
        if "speed" in params:
            st.session_state["chatter_speed"] = params["speed"]
        if "repetition_penalty" in params:
            st.session_state["tts_repetition_penalty"] = params["repetition_penalty"]

        print(f"  ✅ 파라미터: cfg={params.get('cfg_weight')}, temp={params.get('temperature')}, exag={params.get('exaggeration')}")

        # ⭐⭐⭐ 4단계: 품질 설정 ⭐⭐⭐
        quality = preset.get("quality_settings", {})
        if "preset_key" in quality:
            # selectbox의 index 값으로 저장
            st.session_state["_preset_quality_index"] = quality["preset_key"]
        if "settings" in quality:
            st.session_state["chatter_quality_settings"] = quality["settings"]

        # ⭐⭐⭐ 5단계: 생성 옵션 ⭐⭐⭐
        gen_opts = preset.get("generation_options", {})
        if "use_random_seed" in gen_opts:
            st.session_state["_preset_random_seed"] = gen_opts["use_random_seed"]
        if "seed" in gen_opts and gen_opts["seed"] is not None:
            st.session_state["_preset_seed"] = gen_opts["seed"]

        # ⭐⭐⭐ 6단계: 프리셋 로드 플래그 설정 ⭐⭐⭐
        st.session_state["loaded_preset"] = preset
        st.session_state["_preset_just_loaded"] = True
        st.session_state["_preset_loaded_name"] = preset.get("preset_name", "")

        print(f"\n[Preset] ✅ 프리셋 적용 완료!")
        print(f"  이름: {preset.get('preset_name')}")
        print(f"  음성: {voice_ref.get('voice_name')}")

    except Exception as e:
        print(f"[Preset] ❌ 적용 오류: {e}")
        import traceback
        traceback.print_exc()


def render_preset_ui():
    """프리셋 저장/불러오기 UI 렌더링"""

    st.markdown("---")
    st.markdown("#### 💾 TTS 설정 프리셋")

    preset_manager = get_preset_manager()

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**📂 프리셋 불러오기**")

        # 프리셋 목록 가져오기
        presets = preset_manager.list_presets()

        if presets:
            preset_options = {
                f"{p['preset_name']} ({p['voice_name']})": p['preset_id']
                for p in presets
            }

            selected_preset_name = st.selectbox(
                "저장된 프리셋",
                options=["선택하세요..."] + list(preset_options.keys()),
                key="preset_selector"
            )

            if selected_preset_name != "선택하세요...":
                preset_id = preset_options[selected_preset_name]

                btn_col1, btn_col2 = st.columns(2)
                with btn_col1:
                    if st.button("📥 불러오기", key="load_preset_btn", use_container_width=True):
                        preset = preset_manager.load_preset(preset_id)

                        if preset:
                            apply_preset_to_session(preset)
                            st.success(f"'{preset['preset_name']}' 불러옴!")
                            st.rerun()

                with btn_col2:
                    if st.button("🗑️ 삭제", key="delete_preset_btn", use_container_width=True):
                        if preset_manager.delete_preset(preset_id):
                            st.success("프리셋 삭제됨")
                            st.rerun()
        else:
            st.info("저장된 프리셋이 없습니다.")

    with col2:
        st.markdown("**💾 현재 설정 저장**")

        voice_name = st.session_state.get("selected_voice_name", "음성")
        preset_name = st.text_input(
            "프리셋 이름",
            value=f"{voice_name} - 커스텀",
            key="new_preset_name"
        )

        preset_description = st.text_input(
            "설명 (선택)",
            value="",
            key="new_preset_description"
        )

        if st.button("💾 현재 설정 저장", key="save_preset_btn", type="primary", use_container_width=True):
            if preset_name:
                preset_id = save_current_settings_as_preset(
                    name=preset_name,
                    description=preset_description
                )

                if preset_id:
                    st.success(f"'{preset_name}' 저장됨!")
                    st.balloons()
                else:
                    st.error("프리셋 저장 실패")
            else:
                st.warning("프리셋 이름을 입력하세요.")

    # 적용된 프리셋 정보 표시
    if st.session_state.get("loaded_preset"):
        with st.expander("📋 현재 적용된 프리셋 정보", expanded=False):
            preset = st.session_state.loaded_preset
            st.caption(f"**이름:** {preset.get('preset_name', 'N/A')}")
            st.caption(f"**음성:** {preset.get('voice_reference', {}).get('voice_name', 'N/A')}")
            st.caption(f"**생성일:** {preset.get('created_at', 'N/A')[:10]}")
            if preset.get("description"):
                st.caption(f"**설명:** {preset.get('description')}")


def render_preset_quick_buttons():
    """프리셋 빠른 선택 버튼 (상단용)"""

    preset_manager = get_preset_manager()
    presets = preset_manager.list_presets()[:4]  # 최근 4개만

    if presets:
        st.markdown("**⚡ 빠른 프리셋:**")
        cols = st.columns(min(len(presets), 4))

        for i, preset_info in enumerate(presets):
            with cols[i]:
                display_name = preset_info['preset_name'][:12]
                if len(preset_info['preset_name']) > 12:
                    display_name += "..."

                if st.button(
                    f"📌 {display_name}",
                    key=f"quick_preset_{preset_info['preset_id']}",
                    help=f"음성: {preset_info['voice_name']}",
                    use_container_width=True
                ):
                    preset = preset_manager.load_preset(preset_info['preset_id'])
                    if preset:
                        apply_preset_to_session(preset)
                        st.success(f"프리셋 적용!")
                        st.rerun()


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
    timeout: int = 120,
    quality_settings: dict = None
) -> dict:
    """
    단일 청크 TTS 생성

    Args:
        text: 텍스트
        voice_ref_path: 참조 음성 경로
        params: TTS 파라미터
        repetition_penalty: 반복 억제 강도
        timeout: 타임아웃 (초)
        quality_settings: 음성 품질 설정 (preprocess, postprocess)

    Returns:
        {success, audio_data, duration, error}
    """
    # 디버그 로깅
    seed_value = params.get("seed")
    print(f"[TTS] generate_single_chunk 호출:")
    print(f"  - text: {text[:30]}...")
    print(f"  - voice_ref_path: {voice_ref_path}")
    print(f"  - seed: {seed_value} ({'고정' if seed_value is not None else '랜덤'})")
    if quality_settings:
        print(f"  - quality_settings: 적용됨")

    payload = {
        "text": text,
        "settings": {
            "language": "ko",
            "exaggeration": params.get("exaggeration", 0.5),
            "cfg_weight": params.get("cfg_weight", 0.5),
            "temperature": params.get("temperature", 0.8),
            "speed": 1.0,  # ⭐ 원본 속도로 생성 (후처리에서 조정)
            "seed": seed_value,
            "voice_ref_path": voice_ref_path,
            "repetition_penalty": repetition_penalty,
            "quality_settings": quality_settings,
            "skip_speed_adjustment": True  # ⭐ Chatterbox 속도 조정 스킵
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
    max_retries: int = 3,
    quality_settings: dict = None
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
        quality_settings: 음성 품질 설정

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
            repetition_penalty=current_rep_penalty,
            quality_settings=quality_settings  # 품질 설정 전달
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
    progress_callback=None,
    quality_settings: dict = None
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
            max_retries=max_retries,
            quality_settings=quality_settings
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

    # 파일에서 씬 데이터 존재 여부도 확인
    scenes_json_info = get_scenes_json_info()
    has_scene_file = scenes_json_info.get("exists", False)

    if st.session_state.get("scene_analysis_script") or has_scene_data or has_scene_file:
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
        # 🔄 새로고침 버튼 및 파일 정보
        refresh_col1, refresh_col2 = st.columns([3, 1])
        with refresh_col1:
            edge_scenes_json_info = get_scenes_json_info()
            if edge_scenes_json_info["exists"]:
                st.caption(f"📁 마지막 수정: {edge_scenes_json_info['last_modified']} ({edge_scenes_json_info['scene_count']}개 씬)")
        with refresh_col2:
            if st.button("🔄 새로고침", key="edge_refresh_scenes", help="씬 분석 결과를 다시 로드합니다"):
                loaded_scenes, was_loaded = load_scenes_from_json(force_reload=True)
                if was_loaded and loaded_scenes:
                    st.success(f"✅ {len(loaded_scenes)}개 씬 새로고침 완료!")
                    st.rerun()
                else:
                    st.warning("씬 데이터가 없거나 로드에 실패했습니다.")

        # 씬별 생성 모드 UI
        st.info(f"📊 총 **{len(scenes_data)}개** 씬이 분석되어 있습니다.")

    elif script_source == "씬 분석 스크립트" and not has_scene_data and has_scene_file:
        # 파일은 있지만 세션에 로드되지 않은 경우
        st.warning(f"📁 씬 분석 파일이 있습니다 ({scenes_json_info['scene_count']}개 씬). 로드 버튼을 눌러주세요.")
        if st.button("📥 씬 데이터 로드", key="edge_load_scenes", type="primary"):
            loaded_scenes, was_loaded = load_scenes_from_json(force_reload=True)
            if was_loaded and loaded_scenes:
                st.success(f"✅ {len(loaded_scenes)}개 씬 로드 완료!")
                st.rerun()
            else:
                st.error("씬 데이터 로드에 실패했습니다.")

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
            # 씬 데이터를 컴포넌트용 형식으로 변환
            edge_scenes_for_selector = []
            for idx, scene in enumerate(scenes_data):
                scene_id = scene.get('scene_id', idx + 1)
                scene_text = scene.get('script_text', '')
                edge_scenes_for_selector.append({
                    "scene_id": scene_id,
                    "text": scene_text,
                    "script_text": scene_text,
                    "duration_estimate": scene.get('duration_estimate', max(1, len(scene_text) // 10))
                })

            # 씬 구간 선택 컴포넌트 사용
            selected_scene_numbers = render_scene_range_selector(
                total_scenes=len(scenes_data),
                scenes_data=edge_scenes_for_selector,
                key_prefix="edge_scene",
                show_header=True,
                default_mode="전체"
            )

            # 선택된 씬 필터링
            edge_selected_scenes = []
            for scene_num in selected_scene_numbers:
                if scene_num <= len(scenes_data):
                    scene = scenes_data[scene_num - 1]
                    scene_id = scene.get('scene_id', scene_num)
                    scene_text = scene.get('script_text', '')
                    edge_selected_scenes.append({
                        "scene_id": scene_id,
                        "text": scene_text,
                        "char_count": len(scene_text),
                        "duration_estimate": scene.get('duration_estimate', max(1, len(scene_text) // 10))
                    })

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

        # ⭐ AI 텍스트 전처리 (영어 → 발음 변환)
        if edge_selected_scenes:
            st.markdown("---")
            preprocess_result = render_ai_preprocessing_panel(
                scenes=edge_selected_scenes,
                session_key="edge_tts_preprocess",
                default_language=selected_lang,
                show_preview=True,
                expanded=False
            )
            # 전처리 적용
            if preprocess_result.get("use_preprocessed"):
                edge_selected_scenes = preprocess_result.get("preprocessed_scenes", edge_selected_scenes)
                # script_text도 업데이트
                script_text = "\n\n".join([
                    s.get("preprocessed_text") or s.get("text", "")
                    for s in edge_selected_scenes
                ])

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

        # ⭐ 세션에서 이전 생성 결과 복원 (다운로드 옵션 선택 시 화면 유지)
        elif st.session_state.get("edge_tts_generation_done"):
            edge_audio_files = st.session_state.get("edge_tts_audio_files", [])
            edge_timestamp = st.session_state.get("edge_tts_timestamp", 0)
            generated_files = st.session_state.get("last_tts_scenes", [])

            if edge_audio_files:
                # 결과 요약
                success_count = len([f for f in generated_files if f.get("status") == "success"])
                st.success(f"✅ **{success_count}개** 씬 생성 완료!")

                # 씬별 오디오 플레이어
                st.markdown("### 🎵 생성된 음성 파일")
                for file_info in generated_files:
                    if file_info.get("status") == "success":
                        scene_id = file_info["scene_id"]
                        with st.expander(f"📢 씬 {scene_id} - {file_info.get('text_preview', '')} ({file_info.get('char_count', 0)}자)", expanded=False):
                            col1, col2 = st.columns([3, 1])
                            with col1:
                                if file_info.get("path") and os.path.exists(file_info["path"]):
                                    st.audio(file_info["path"])
                            with col2:
                                if file_info.get("path") and os.path.exists(file_info["path"]):
                                    with open(file_info["path"], "rb") as f:
                                        st.download_button(
                                            "⬇️",
                                            data=f.read(),
                                            file_name=f"{scene_id}.mp3",
                                            mime="audio/mpeg",
                                            key=f"edge_restore_dl_{scene_id}",
                                            use_container_width=True
                                        )

                # 다운로드 섹션
                if len(edge_audio_files) > 1:
                    st.markdown("---")
                    render_tts_download_section(
                        audio_files=edge_audio_files,
                        project_name=f"edge_tts_{edge_timestamp}",
                        extension="mp3",
                        key_prefix="edge_dl"
                    )

                # 초기화 버튼
                if st.button("🗑️ 결과 초기화", key="edge_clear_results"):
                    st.session_state["edge_tts_generation_done"] = False
                    st.session_state["edge_tts_audio_files"] = []
                    st.session_state["last_tts_scenes"] = []
                    st.rerun()
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

            # ⭐⭐⭐ 핵심 수정: AI 전처리 텍스트 우선 사용 ⭐⭐⭐
            if scene.get("preprocessed_text"):
                # AI가 이미 전처리한 텍스트 사용 (추가 정규화 불필요)
                scene_text = scene["preprocessed_text"]
                print(f"[EdgeTTS] 씬 {scene_id}: ✅ AI 전처리 텍스트 사용")
            else:
                # AI 전처리 없으면 원본에 규칙 기반 정규화 적용
                scene_text = scene.get("text", "")
                original_text = scene_text
                scene_text = normalize_for_tts(scene_text)
                if scene_text != original_text:
                    print(f"[EdgeTTS] 씬 {scene_id} 정규화: {original_text[:40]}... → {scene_text[:40]}...")

            if not scene_text.strip():
                continue
            # scene 객체도 업데이트
            scene = dict(scene)
            scene["text"] = scene_text

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
                                        file_name=f"{scene_id}.mp3",
                                        mime="audio/mpeg",
                                        key=f"download_scene_{scene_id}_{timestamp}",
                                        use_container_width=True
                                    )
                    else:
                        st.error(f"❌ 씬 {scene_id} 생성 실패: {file_info.get('error', '알 수 없는 오류')}")

                # 전체 ZIP 다운로드 (새 컴포넌트 사용)
                if success_count > 1:
                    st.markdown("---")

                    # 다운로드용 데이터 준비
                    edge_audio_files = []
                    for file_info in generated_files:
                        if file_info["status"] == "success" and file_info["path"]:
                            edge_audio_files.append({
                                "scene_id": file_info["scene_id"],
                                "path": file_info["path"]
                            })

                    # 세션에 다운로드용 데이터 저장 (rerun 시 복원용)
                    st.session_state["edge_tts_audio_files"] = edge_audio_files
                    st.session_state["edge_tts_timestamp"] = timestamp
                    st.session_state["edge_tts_generation_done"] = True

                    # 새 다운로드 UI 렌더링
                    render_tts_download_section(
                        audio_files=edge_audio_files,
                        project_name=f"edge_tts_{timestamp}",
                        extension="mp3",
                        key_prefix="edge_dl"  # 고정 키 사용 (timestamp 제거)
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

                # ⭐⭐⭐ 최적화 버전 보존 로직 ⭐⭐⭐
                # 이미 선택된 최적화 버전이 있으면 덮어쓰지 않음!
                current_ref = st.session_state.get("selected_reference_voice", "")
                voice_basename = os.path.splitext(os.path.basename(selected_path))[0].rstrip('_')

                # 현재 저장된 경로가 같은 음성의 최적화 버전인지 확인
                is_optimized_of_same_voice = (
                    current_ref and
                    os.path.exists(current_ref) and
                    voice_basename in os.path.basename(current_ref) and
                    any(p in current_ref for p in ["__manual_", "__opt_", "_최적화"])
                )

                if is_optimized_of_same_voice:
                    # 이미 최적화 버전이 선택되어 있음 - 덮어쓰지 않음!
                    print(f"[VoiceSelector] ⭐ 기존 최적화 버전 유지: {os.path.basename(current_ref)}")
                else:
                    # 원본 경로로 설정
                    st.session_state["selected_reference_voice"] = selected_path
                    print(f"[VoiceSelector] 원본 경로 설정: {os.path.basename(selected_path)}")

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

                    # ⭐ 입력 방식 선택
                    input_mode = st.radio(
                        "입력 방식",
                        ["일반 텍스트", "📋 SRT 자막 (타임스탬프 기반 정확 측정)"],
                        horizontal=True,
                        key="text_input_mode",
                        label_visibility="collapsed"
                    )

                    if input_mode == "일반 텍스트":
                        # 기존 일반 텍스트 입력
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

                    else:  # SRT 모드
                        st.info("💡 SRT 자막을 붙여넣으면 타임스탬프 기반으로 **밀리초 단위 정확한 발화속도**를 측정합니다.")

                        # SRT 입력 방법 선택
                        srt_method = st.radio(
                            "SRT 입력 방법",
                            ["직접 붙여넣기", "파일 업로드"],
                            horizontal=True,
                            key="srt_input_method_radio"
                        )

                        srt_content = ""

                        if srt_method == "직접 붙여넣기":
                            # ⭐ 세션 상태에서 기존 값 가져오기
                            default_srt = st.session_state.get("srt_content_cache", "")

                            srt_content = st.text_area(
                                "SRT 내용 붙여넣기",
                                value=default_srt,  # ⭐ 명시적 value 설정
                                height=250,
                                placeholder="""1
00:00:00,100 --> 00:00:01,533
2018년 언론인 자말

2
00:00:01,600 --> 00:00:02,766
카슈크지가 튀르키의

...""",
                                key="srt_paste_textarea_input",  # ⭐ 고유한 key
                                disabled=False,  # ⭐ 명시적 활성화
                                help="SRT 파일 내용을 여기에 붙여넣으세요 (Ctrl+V)"
                            )

                            # 세션에 저장
                            if srt_content:
                                st.session_state["srt_content_cache"] = srt_content

                        else:  # 파일 업로드
                            uploaded_srt = st.file_uploader(
                                "SRT 파일 업로드",
                                type=["srt", "txt"],
                                key="srt_file_upload_input"
                            )

                            if uploaded_srt:
                                try:
                                    srt_content = uploaded_srt.read().decode("utf-8")
                                    st.session_state["srt_content_cache"] = srt_content
                                    st.success(f"✅ 파일 로드됨: {uploaded_srt.name}")
                                except Exception as e:
                                    st.error(f"❌ 파일 읽기 오류: {e}")

                        # SRT 파싱 및 분석
                        if srt_content and len(srt_content.strip()) > 20:
                            try:
                                from utils.srt_parser import SRTParser, SpeakingRateAnalyzer

                                scenes = SRTParser.parse_content(srt_content)

                                if scenes:
                                    analyzer = SpeakingRateAnalyzer(scenes)
                                    analysis = analyzer.analyze()

                                    # 분석 결과 표시
                                    st.success(f"✅ {analysis['segment_count']}개 세그먼트 파싱 완료!")

                                    col1, col2, col3, col4 = st.columns(4)
                                    col1.metric("⭐ 평균 발화속도", f"{analysis['weighted_average_rate']:.2f}", "글자/초")
                                    col2.metric("중앙값", f"{analysis['median_rate']:.2f}", "글자/초")
                                    col3.metric("총 발화시간", f"{analysis['total_duration']:.1f}초")
                                    col4.metric("총 글자수", f"{analysis['total_chars']:,}자")

                                    # 상세 통계 (접기)
                                    with st.expander("📊 상세 통계"):
                                        st.write(f"- 최소: {analysis['min_rate']:.2f} 글자/초")
                                        st.write(f"- 최대: {analysis['max_rate']:.2f} 글자/초")
                                        st.write(f"- 표준편차: {analysis['std_dev']:.2f}")
                                        st.write(f"- 이상치 제거: {analysis['outliers_removed']}개")

                                    # 저장 버튼
                                    col_save1, col_save2 = st.columns(2)

                                    with col_save1:
                                        if st.button("💾 텍스트만 저장", key="save_srt_text", use_container_width=True):
                                            plain_text = ' '.join(s['narration'] for s in scenes)
                                            set_voice_transcript(selected_path, plain_text)
                                            st.session_state["_prev_analyzed_voice_path"] = None
                                            st.success("✅ 텍스트 저장 완료!")
                                            st.rerun()

                                    with col_save2:
                                        if st.button("⭐ 발화속도 측정값으로 저장", key="save_srt_with_rate", use_container_width=True):
                                            plain_text = ' '.join(s['narration'] for s in scenes)
                                            set_voice_transcript(selected_path, plain_text)

                                            # 정확한 발화속도 저장
                                            st.session_state["accurate_speaking_rate"] = analysis['weighted_average_rate']
                                            st.session_state["speaking_rate_source"] = "srt_timestamp"
                                            st.session_state["_prev_analyzed_voice_path"] = None

                                            st.success(
                                                f"✅ 저장 완료!\n"
                                                f"- 텍스트: {analysis['total_chars']}자\n"
                                                f"- 정확한 발화속도: {analysis['weighted_average_rate']:.2f} 글자/초"
                                            )
                                            st.rerun()
                                else:
                                    st.warning("⚠️ SRT 파싱 실패. 형식을 확인해주세요.")

                            except Exception as e:
                                st.error(f"❌ SRT 파싱 오류: {e}")

                # ⭐ 음성 최적화 UI v2.0 (여러 버전 선택 + 품질 점수 표시)
                needs_opt, opt_reason = is_voice_optimization_needed(selected_path)
                voice_name = os.path.splitext(os.path.basename(selected_path))[0]

                # 모든 최적화 버전 스캔
                optimized_versions = scan_optimized_versions(voice_name)

                with st.expander("🎯 음성 최적화 (Voice Cloning 품질 향상)", expanded=needs_opt or len(optimized_versions) > 0):
                    if optimized_versions:
                        # ✅ 최적화 버전 있음 - 선택 UI 표시
                        st.success(f"✅ 최적화 버전 {len(optimized_versions)}개 발견")

                        # 버전 선택 라디오 버튼
                        st.markdown("##### 📂 최적화 버전 선택")

                        # 세션 상태 초기화
                        if "selected_opt_version_idx" not in st.session_state:
                            st.session_state.selected_opt_version_idx = 0

                        # 옵션 생성
                        version_labels = []
                        for i, v in enumerate(optimized_versions):
                            label = f"{v['filename']}"
                            badges = []
                            if v.get("is_latest"):
                                badges.append("⭐최신")
                            if v.get("quality_score", 0) >= 0.8:
                                badges.append("🏆고품질")
                            if v.get("is_manual"):
                                badges.append("✂️수동")
                            if badges:
                                label += f" ({', '.join(badges)})"

                            # 상세 정보
                            detail = f"📍 {v.get('start_time', 0):.1f}~{v.get('end_time', 0):.1f}초"
                            detail += f" | 길이: {v.get('duration', 0):.1f}초"
                            if v.get("quality_score", 0) > 0:
                                detail += f" | 품질: {v['quality_score']:.3f}"

                            version_labels.append(f"{label}\n   {detail}")

                        selected_idx = st.radio(
                            "버전 선택:",
                            range(len(version_labels)),
                            format_func=lambda i: version_labels[i],
                            key="opt_version_radio",
                            index=st.session_state.selected_opt_version_idx,
                            label_visibility="collapsed"
                        )
                        st.session_state.selected_opt_version_idx = selected_idx

                        # 선택된 버전 정보
                        selected_version = optimized_versions[selected_idx]

                        # 상세 정보 표시
                        with st.container():
                            st.markdown("##### 📊 선택된 버전 정보")
                            col1, col2 = st.columns(2)

                            with col1:
                                st.markdown(f"**파일:** `{selected_version['filename']}`")
                                st.markdown(f"**구간:** {selected_version.get('start_time', 0):.1f}초 ~ {selected_version.get('end_time', 0):.1f}초")
                                st.markdown(f"**길이:** {selected_version.get('duration', 0):.1f}초")

                            with col2:
                                quality = selected_version.get('quality_score', 0)
                                quality_emoji = "🏆" if quality >= 0.8 else "✅" if quality >= 0.6 else "⚠️"
                                st.markdown(f"**품질:** {quality_emoji} {quality:.3f}" if quality > 0 else "**품질:** 측정 안됨")
                                st.markdown(f"**생성일:** {selected_version.get('created_at', 'N/A')}")
                                # 상태 배지
                                status_parts = []
                                if selected_version.get("is_latest"):
                                    status_parts.append("⭐ 최신")
                                if selected_version.get("is_manual"):
                                    status_parts.append("✂️ 수동선택")
                                else:
                                    status_parts.append("🤖 자동선택")
                                st.markdown(f"**상태:** {', '.join(status_parts)}")

                        # 미리듣기
                        st.markdown("##### 🎧 미리듣기")
                        col_play1, col_play2 = st.columns(2)
                        with col_play1:
                            st.audio(selected_version["filepath"], format="audio/mp3")
                            st.caption("선택된 버전")
                        with col_play2:
                            st.audio(selected_path, format="audio/mp3")
                            st.caption("원본 음성")

                        # 액션 버튼
                        st.markdown("---")
                        col_use, col_new, col_manage = st.columns(3)

                        with col_use:
                            if st.button("✅ 선택한 버전 사용", key="use_selected_version", type="primary", use_container_width=True):
                                st.session_state["selected_reference_voice"] = selected_version["filepath"]
                                st.session_state["_prev_analyzed_voice_path"] = None
                                st.success(f"✅ '{selected_version['filename']}' 사용")
                                st.rerun()

                        with col_new:
                            if st.button("🔄 새로 최적화", key="create_new_optimization", use_container_width=True):
                                with st.spinner("새로운 최적화 버전 생성 중..."):
                                    result = optimize_and_register_voice(selected_path)
                                    if result.get("success"):
                                        st.success(f"✅ 새 버전 생성!")
                                        st.info(f"품질 점수: {result.get('quality_score', 0):.3f}")
                                        st.rerun()
                                    else:
                                        st.error(f"❌ 실패: {result.get('error')}")

                        with col_manage:
                            if st.button("🗑️ 버전 관리", key="manage_versions", use_container_width=True):
                                st.session_state.show_version_manager = not st.session_state.get("show_version_manager", False)

                        # 버전 관리 모달
                        if st.session_state.get("show_version_manager", False):
                            st.markdown("---")
                            st.markdown("##### 🗂️ 버전 관리")
                            for v in optimized_versions:
                                col_name, col_quality, col_del = st.columns([4, 2, 1])
                                with col_name:
                                    st.text(f"{v['filename']} ({v.get('duration', 0):.1f}초)")
                                with col_quality:
                                    st.text(f"품질: {v.get('quality_score', 0):.3f}")
                                with col_del:
                                    del_key = f"del_{v['filename']}"
                                    if st.button("🗑️", key=del_key):
                                        try:
                                            get_version_manager().delete_version(v["filepath"])
                                            st.success(f"삭제됨: {v['filename']}")
                                            st.rerun()
                                        except Exception as e:
                                            st.error(f"삭제 실패: {e}")

                            if st.button("닫기", key="close_version_manager"):
                                st.session_state.show_version_manager = False
                                st.rerun()

                    elif needs_opt:
                        # ⚠️ 최적화 필요
                        st.warning(f"⚠️ {opt_reason}")
                        st.caption("긴 음성은 Voice Cloning 품질이 저하될 수 있습니다. 최적의 20초 구간을 추출합니다.")

                        if st.button("🎯 최적화 및 저장", key="optimize_voice", use_container_width=True):
                            with st.spinner("최적 구간 추출 중..."):
                                result = optimize_and_register_voice(selected_path)

                                if result.get("success"):
                                    st.success(f"✅ 최적화 완료!")
                                    st.info(f"📁 새 음성: {os.path.basename(result['optimized_path'])}")
                                    st.info(f"⏱️ 길이: {result['original_duration']:.0f}초 → {result['optimized_duration']:.0f}초")
                                    st.info(f"📊 품질 점수: {result.get('quality_score', 0):.3f}")

                                    # 최적화된 버전으로 전환
                                    st.session_state["selected_reference_voice"] = result["optimized_path"]
                                    st.session_state["_prev_analyzed_voice_path"] = None
                                    st.rerun()
                                else:
                                    st.error(f"❌ 최적화 실패: {result.get('error')}")
                    else:
                        # ✅ 최적화 불필요
                        st.success(f"✅ {opt_reason}")

                        # 새 최적화 버전 생성 옵션 제공
                        if st.button("🔄 새 최적화 버전 생성", key="create_opt_anyway", use_container_width=True):
                            with st.spinner("최적 구간 추출 중..."):
                                result = optimize_and_register_voice(selected_path)
                                if result.get("success"):
                                    st.success(f"✅ 완료! 품질: {result.get('quality_score', 0):.3f}")
                                    st.rerun()
                                else:
                                    st.error(f"❌ 실패: {result.get('error')}")

                    # ⭐⭐⭐ 수동 구간 선택 섹션 (v2.0 - 텍스트 입력 + 발화속도 측정) ⭐⭐⭐
                    st.markdown("---")
                    st.markdown("##### ✂️ 수동 구간 선택")
                    st.caption("자동 최적화가 적합하지 않을 때 직접 구간을 선택할 수 있습니다.")

                    # 수동 선택 모드 토글
                    show_manual = st.checkbox(
                        "수동 구간 선택 모드 활성화",
                        value=st.session_state.get("show_manual_segment", False),
                        key="manual_segment_toggle"
                    )
                    st.session_state["show_manual_segment"] = show_manual

                    if show_manual:
                        try:
                            import re
                            import hashlib
                            from datetime import datetime
                            from pydub import AudioSegment

                            # 오디오 길이 확인 (pydub 사용)
                            visualizer = get_waveform_visualizer()
                            audio_duration = visualizer.get_audio_duration(selected_path)

                            if audio_duration <= 0:
                                st.error("원본 음성을 로드할 수 없습니다.")
                            else:
                                voice_name = os.path.splitext(os.path.basename(selected_path))[0]
                                st.info(f"📁 원본: **{os.path.basename(selected_path)}** ({audio_duration:.1f}초)")

                                # 원본 듣기
                                with st.expander("🎧 원본 음성 듣기"):
                                    st.audio(selected_path)
                                    st.caption("인터뷰 화자나 배경음이 없는 깨끗한 구간을 찾아보세요.")

                                st.markdown("---")

                                # 구간 설정 (숫자 입력)
                                st.markdown("**🎚️ 구간 설정** (권장: 15~20초)")
                                col_start, col_end = st.columns(2)

                                with col_start:
                                    start_sec = st.number_input(
                                        "시작 시간 (초)",
                                        min_value=0.0,
                                        max_value=max(0.0, audio_duration - 10.0),
                                        value=st.session_state.get("manual_start_sec", 0.0),
                                        step=5.0,
                                        key="manual_start_input"
                                    )
                                    st.session_state.manual_start_sec = start_sec

                                with col_end:
                                    default_end = min(start_sec + 20.0, audio_duration)
                                    end_sec = st.number_input(
                                        "끝 시간 (초)",
                                        min_value=start_sec + 10.0,
                                        max_value=audio_duration,
                                        value=max(default_end, start_sec + 15.0),
                                        step=5.0,
                                        key="manual_end_input"
                                    )
                                    st.session_state.manual_end_sec = end_sec

                                # 선택 구간 정보
                                segment_duration = end_sec - start_sec

                                if 15.0 <= segment_duration <= 20.0:
                                    st.success(f"✅ 선택: **{start_sec:.0f}~{end_sec:.0f}초** ({segment_duration:.1f}초, 최적 범위)")
                                elif 10.0 <= segment_duration <= 30.0:
                                    st.info(f"ℹ️ 선택: **{start_sec:.0f}~{end_sec:.0f}초** ({segment_duration:.1f}초)")
                                else:
                                    st.warning(f"⚠️ 선택: {segment_duration:.1f}초 (15~20초 권장)")

                                st.markdown("---")

                                # ⭐ 텍스트 입력 (발화속도 측정용) - 새로 추가!
                                st.markdown("**📝 구간 텍스트 입력** (발화속도 측정용)")
                                st.caption("선택한 구간에서 화자가 말하는 내용을 입력하면 발화속도를 계산합니다.")

                                segment_text = st.text_area(
                                    "구간 텍스트",
                                    value=st.session_state.get("manual_segment_text", ""),
                                    height=100,
                                    placeholder="예: 안녕하세요 여러분 오늘은 삼성전자에 대해 이야기해보겠습니다...",
                                    key="manual_segment_text_input",
                                    help="SRT 파일의 해당 구간 자막을 붙여넣기 해도 됩니다."
                                )
                                st.session_state.manual_segment_text = segment_text

                                # 발화속도 계산
                                speaking_rate = None
                                char_count = 0

                                if segment_text.strip():
                                    # 글자수 계산 (공백, 특수문자 제외)
                                    clean_text = re.sub(r'[^\w가-힣a-zA-Z0-9]', '', segment_text)
                                    char_count = len(clean_text)

                                    if segment_duration > 0:
                                        speaking_rate = char_count / segment_duration

                                        st.markdown("**📊 발화속도 분석**")
                                        col_sr1, col_sr2, col_sr3 = st.columns(3)

                                        with col_sr1:
                                            st.metric("글자수", f"{char_count}자")
                                        with col_sr2:
                                            st.metric("구간 길이", f"{segment_duration:.1f}초")
                                        with col_sr3:
                                            if 5.5 <= speaking_rate <= 7.5:
                                                st.metric("발화속도", f"{speaking_rate:.2f} 글자/초", "정상")
                                            elif speaking_rate < 5.5:
                                                st.metric("발화속도", f"{speaking_rate:.2f} 글자/초", "느림")
                                            else:
                                                st.metric("발화속도", f"{speaking_rate:.2f} 글자/초", "빠름")

                                        # 추천 speed 파라미터
                                        if speaking_rate < 5.5:
                                            recommended_speed = 0.7
                                        elif speaking_rate < 6.5:
                                            recommended_speed = 0.75
                                        elif speaking_rate < 7.5:
                                            recommended_speed = 0.85
                                        else:
                                            recommended_speed = 1.0
                                        st.caption(f"💡 추천 TTS speed 파라미터: **{recommended_speed}**")
                                else:
                                    st.caption("💡 텍스트를 입력하면 발화속도를 계산합니다. (선택사항)")

                                st.markdown("---")

                                # 미리듣기
                                st.markdown("**🎧 미리듣기**")
                                col_preview1, col_preview2 = st.columns(2)

                                with col_preview1:
                                    if st.button("▶️ 선택 구간 듣기", key="preview_segment", use_container_width=True):
                                        with st.spinner("추출 중..."):
                                            preview_path = visualizer.extract_segment(selected_path, start_sec, end_sec)
                                            if preview_path:
                                                st.session_state["manual_preview_path"] = preview_path
                                                st.rerun()

                                with col_preview2:
                                    from_time = st.number_input(
                                        "특정 시점부터",
                                        min_value=0.0,
                                        max_value=max(0.0, audio_duration - 10.0),
                                        value=start_sec,
                                        step=10.0,
                                        key="from_time_input"
                                    )
                                    if st.button("▶️ 30초 듣기", key="preview_from", use_container_width=True):
                                        with st.spinner("추출 중..."):
                                            to_time = min(from_time + 30.0, audio_duration)
                                            preview_path = visualizer.extract_segment(selected_path, from_time, to_time)
                                            if preview_path:
                                                st.session_state["manual_preview_30s"] = preview_path
                                                st.rerun()

                                # 미리듣기 재생
                                if st.session_state.get("manual_preview_path"):
                                    st.audio(st.session_state["manual_preview_path"], format="audio/mp3")
                                    st.caption(f"🎵 선택 구간: {start_sec:.0f} ~ {end_sec:.0f}초")

                                if st.session_state.get("manual_preview_30s"):
                                    st.audio(st.session_state["manual_preview_30s"], format="audio/mp3")
                                    st.caption(f"🎵 30초 미리듣기")

                                st.markdown("---")

                                # ⭐ 최적화 결과 표시 (세션 상태 기반)
                                if "manual_opt_result" not in st.session_state:
                                    st.session_state.manual_opt_result = None

                                # 이전 결과가 있으면 표시
                                if st.session_state.manual_opt_result:
                                    result = st.session_state.manual_opt_result
                                    if result.get("success"):
                                        st.success(f"✅ 최적화 완료!")
                                        st.info(f"📁 파일: `{result.get('filename', '')}`")
                                        st.info(f"⏱️ 길이: {result.get('duration', 0):.1f}초")
                                        if result.get("speaking_rate"):
                                            st.info(f"⭐ 발화속도: {result['speaking_rate']:.2f} 글자/초")

                                        # 생성된 파일 듣기
                                        if result.get("filepath") and os.path.exists(result["filepath"]):
                                            st.audio(result["filepath"])

                                        col_use, col_reset = st.columns(2)
                                        with col_use:
                                            if st.button("✅ 이 버전 사용", key="use_new_manual_opt", type="primary", use_container_width=True):
                                                # ⭐ 선택된 버전 경로 저장
                                                st.session_state["selected_reference_voice"] = result["filepath"]
                                                st.session_state["_prev_analyzed_voice_path"] = None
                                                st.session_state["show_manual_segment"] = False
                                                # ⭐ 결과는 유지 (다음 rerun에서 표시됨)
                                                # st.session_state.manual_opt_result = None  # 결과 유지!
                                                st.success(f"✅ '{result['filename']}' 버전이 선택되었습니다!")
                                                st.balloons()
                                                import time
                                                time.sleep(0.5)  # 메시지 표시 시간
                                                st.session_state.manual_opt_result = None  # 결과 초기화
                                                st.rerun()
                                        with col_reset:
                                            if st.button("🔄 다른 구간 선택", key="reset_manual_opt", use_container_width=True):
                                                st.session_state.manual_opt_result = None
                                                st.rerun()
                                    else:
                                        st.error(f"❌ 최적화 실패: {result.get('error', '알 수 없는 오류')}")
                                        if st.button("🔄 다시 시도", key="retry_manual_opt"):
                                            st.session_state.manual_opt_result = None
                                            st.rerun()
                                else:
                                    # 생성 버튼
                                    st.markdown("**🔧 최적화 생성**")
                                    if st.button("✅ 선택한 구간으로 최적화 생성", key="create_manual_opt", type="primary", use_container_width=True):
                                        with st.spinner(f"수동 최적화 버전 생성 중... ({start_sec:.0f}~{end_sec:.0f}초)"):
                                            try:
                                                # 직접 최적화 생성 (함수 인라인)
                                                print(f"\n{'='*60}")
                                                print(f"[ManualOpt] 수동 최적화 시작")
                                                print(f"  원본: {os.path.basename(selected_path)}")
                                                print(f"  구간: {start_sec:.1f} ~ {end_sec:.1f}초")
                                                if segment_text.strip():
                                                    print(f"  텍스트: {char_count}자")
                                                if speaking_rate:
                                                    print(f"  발화속도: {speaking_rate:.2f} 글자/초")
                                                print(f"{'='*60}")

                                                # 출력 디렉토리 설정
                                                base_dir = os.path.dirname(selected_path)
                                                if "default" in base_dir:
                                                    base_dir = os.path.dirname(base_dir)
                                                output_dir = os.path.join(base_dir, "optimized")
                                                os.makedirs(output_dir, exist_ok=True)

                                                # 파일명 생성 (⭐ 끝의 언더스코어 제거하여 정규화)
                                                clean_name = voice_name.replace(" ", "_")
                                                if "_최적화" in clean_name:
                                                    clean_name = clean_name.split("_최적화")[0]
                                                if "_opt_" in clean_name:
                                                    clean_name = clean_name.split("_opt_")[0]
                                                if "__manual_" in clean_name:
                                                    clean_name = clean_name.split("__manual_")[0]
                                                # ⭐ 끝의 연속 언더스코어 제거
                                                clean_name = clean_name.rstrip('_')

                                                print(f"[ManualOpt] voice_name 정규화: '{voice_name}' → '{clean_name}'")

                                                time_str = f"{int(start_sec)}-{int(end_sec)}s"
                                                hash_str = hashlib.md5(f"{clean_name}{start_sec}{end_sec}{datetime.now().isoformat()}".encode()).hexdigest()[:8]
                                                filename = f"{clean_name}__manual_{time_str}_{hash_str}.mp3"
                                                output_path = os.path.join(output_dir, filename)

                                                print(f"[ManualOpt] 출력 파일: {filename}")

                                                # 오디오 로드 및 구간 추출
                                                audio = AudioSegment.from_file(selected_path)
                                                start_ms = int(start_sec * 1000)
                                                end_ms = int(end_sec * 1000)
                                                segment = audio[start_ms:end_ms]

                                                # 음량 정규화
                                                original_dBFS = segment.dBFS
                                                target_dBFS = -3.0
                                                change = target_dBFS - original_dBFS
                                                if 0 < change < 15:
                                                    segment = segment.apply_gain(change)
                                                    print(f"[ManualOpt] 음량 조정: {original_dBFS:.1f} → {segment.dBFS:.1f} dBFS")

                                                # MP3로 저장
                                                segment.export(output_path, format="mp3", bitrate="192k")
                                                print(f"[ManualOpt] ✅ 저장 완료: {os.path.getsize(output_path)} bytes")

                                                # 메타데이터 저장
                                                metadata = {
                                                    "source_file": selected_path,
                                                    "start_time": start_sec,
                                                    "end_time": end_sec,
                                                    "duration": segment_duration,
                                                    "optimization_type": "manual",
                                                    "created_at": datetime.now().isoformat(),
                                                    "is_manual": True,
                                                }
                                                if speaking_rate:
                                                    metadata["speaking_rate"] = speaking_rate
                                                    metadata["char_count"] = char_count
                                                if segment_text.strip():
                                                    metadata["segment_text"] = segment_text

                                                # 메타데이터 파일 저장
                                                meta_path = os.path.join(output_dir, "optimization_metadata.json")
                                                all_meta = {"versions": {}}
                                                if os.path.exists(meta_path):
                                                    try:
                                                        with open(meta_path, "r", encoding="utf-8") as f:
                                                            all_meta = json.load(f)
                                                    except:
                                                        pass
                                                all_meta.setdefault("versions", {})[filename] = metadata
                                                with open(meta_path, "w", encoding="utf-8") as f:
                                                    json.dump(all_meta, f, ensure_ascii=False, indent=2, default=str)

                                                # 텍스트 파일 저장
                                                if segment_text.strip():
                                                    text_path = output_path.replace(".mp3", ".txt")
                                                    with open(text_path, "w", encoding="utf-8") as f:
                                                        f.write(segment_text)
                                                    print(f"[ManualOpt] ✅ 텍스트 저장: {os.path.basename(text_path)}")

                                                print(f"[ManualOpt] ✅✅✅ 최적화 완료! ✅✅✅\n")

                                                # 결과 세션에 저장
                                                st.session_state.manual_opt_result = {
                                                    "success": True,
                                                    "filename": filename,
                                                    "filepath": output_path,
                                                    "duration": segment_duration,
                                                    "speaking_rate": speaking_rate,
                                                    "char_count": char_count,
                                                }
                                                st.rerun()

                                            except Exception as e:
                                                import traceback
                                                print(f"[ManualOpt] ❌ 오류: {e}")
                                                traceback.print_exc()
                                                st.session_state.manual_opt_result = {
                                                    "success": False,
                                                    "error": str(e)
                                                }
                                                st.rerun()

                        except Exception as e:
                            st.error(f"수동 구간 선택 오류: {e}")
                            import traceback
                            st.code(traceback.format_exc())

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

    # ⭐ 프리셋 로드 성공 메시지 표시
    if st.session_state.pop("_preset_just_loaded", False):
        preset_name = st.session_state.get("_preset_loaded_name", "")
        st.success(f"✅ '{preset_name}' 프리셋이 적용되었습니다!")

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

    # =========================================================
    # 🎚️ 음성 품질 설정 (전처리/후처리)
    # =========================================================
    st.markdown("---")
    st.markdown("#### 🎚️ 음성 품질 설정")

    # 프리셋 선택
    preset_keys = list(VOICE_QUALITY_PRESETS.keys())
    preset_names = [VOICE_QUALITY_PRESETS[k]["name"] for k in preset_keys]

    # ⭐ 프리셋에서 로드된 인덱스 확인
    preset_quality_idx = st.session_state.pop("_preset_quality_index", None)
    default_quality_idx = preset_quality_idx if preset_quality_idx is not None else 1

    quality_col1, quality_col2 = st.columns([2, 1])

    with quality_col1:
        selected_preset_idx = st.selectbox(
            "프리셋 선택",
            range(len(preset_keys)),
            format_func=lambda i: preset_names[i],
            index=default_quality_idx,  # ⭐ 프리셋 값 또는 기본값
            key="chatter_quality_preset",
            help="미리 정의된 음성 품질 설정"
        )

    selected_preset = preset_keys[selected_preset_idx]
    preset = VOICE_QUALITY_PRESETS[selected_preset]

    with quality_col2:
        if preset.get("badge"):
            st.markdown(f"**{preset['badge']}**")

    # 설명
    st.info(f"📝 {preset['description']}")

    # 사용자 정의 모드
    if selected_preset == "custom":
        with st.expander("🔧 상세 설정", expanded=True):
            st.markdown("**📥 참조 음성 전처리**")

            custom_col1, custom_col2 = st.columns(2)

            with custom_col1:
                pre_noisereduce = st.slider(
                    "노이즈 제거 (%)",
                    0, 100, 30, 5,
                    key="custom_pre_nr",
                    help="높을수록 노이즈↓, 자연스러움↓"
                )
                pre_bandpass_low = st.slider(
                    "저음역 (Hz)",
                    20, 150, 40, 5,
                    key="custom_bp_low",
                    help="높을수록 저음↓"
                )
                pre_noise_gate = st.slider(
                    "노이즈 게이트 (dB)",
                    -60, -30, -55, 1,
                    key="custom_gate",
                    help="낮을수록 미세음 보존↑"
                )

            with custom_col2:
                pre_bandpass_high = st.slider(
                    "고음역 (Hz)",
                    10000, 20000, 18000, 500,
                    key="custom_bp_high",
                    help="높을수록 치찰음(ㅅ,ㅆ) 선명↑"
                )
                pre_normalize_peak = st.slider(
                    "정규화 피크",
                    0.50, 1.00, 0.92, 0.02,
                    key="custom_peak",
                    help="높을수록 다이내믹↑"
                )

            st.markdown("**📤 TTS 후처리**")

            custom_col3, custom_col4 = st.columns(2)

            with custom_col3:
                post_noisereduce = st.slider(
                    "후처리 노이즈 제거 (%)",
                    0, 50, 15, 5,
                    key="custom_post_nr"
                )
                post_soft_clip = st.checkbox(
                    "소프트 클리핑",
                    value=False,
                    key="custom_soft_clip",
                    help="켜면 기계음 감소, 끄면 더 자연스러움"
                )

            with custom_col4:
                post_lowpass = st.slider(
                    "저역 통과 (Hz)",
                    10000, 20000, 18000, 500,
                    key="custom_lowpass"
                )

            # 사용자 정의 설정 저장
            custom_settings = {
                "preprocess": {
                    "noisereduce_strength": pre_noisereduce / 100,
                    "bandpass_low": pre_bandpass_low,
                    "bandpass_high": pre_bandpass_high,
                    "noise_gate_db": pre_noise_gate,
                    "normalize_peak": pre_normalize_peak,
                },
                "postprocess": {
                    "noisereduce_strength": post_noisereduce / 100,
                    "lowpass_cutoff": post_lowpass,
                    "soft_clip": post_soft_clip,
                }
            }
            st.session_state["chatter_quality_settings"] = custom_settings
    else:
        # 프리셋 설정 표시 (읽기 전용)
        with st.expander("📋 현재 설정 보기", expanded=False):
            pre = preset["preprocess"]
            post = preset["postprocess"]

            info_col1, info_col2 = st.columns(2)

            with info_col1:
                st.markdown("**📥 전처리**")
                st.caption(f"• 노이즈 제거: {int(pre['noisereduce_strength']*100)}%")
                st.caption(f"• 밴드패스: {pre['bandpass_low']}~{pre['bandpass_high']}Hz")
                st.caption(f"• 노이즈 게이트: {pre['noise_gate_db']}dB")
                st.caption(f"• 정규화 피크: {pre['normalize_peak']}")

            with info_col2:
                st.markdown("**📤 후처리**")
                st.caption(f"• 노이즈 제거: {int(post['noisereduce_strength']*100)}%")
                st.caption(f"• 저역 통과: {post['lowpass_cutoff']}Hz")
                st.caption(f"• 소프트 클리핑: {'✅' if post['soft_clip'] else '❌'}")

        # 프리셋에서 설정 가져오기
        preset_settings = {
            "preprocess": preset["preprocess"],
            "postprocess": preset["postprocess"],
        }
        st.session_state["chatter_quality_settings"] = preset_settings

    # ============================================================
    # ⭐ TTS 설정 프리셋 저장/불러오기 UI
    # ============================================================
    render_preset_ui()

    st.markdown("---")

    # 시드 설정
    # ⭐ 프리셋에서 로드된 값 확인
    preset_random_seed = st.session_state.pop("_preset_random_seed", None)
    preset_seed = st.session_state.pop("_preset_seed", None)

    col1, col2 = st.columns([1, 1])
    with col1:
        # 프리셋 값이 있으면 사용, 없으면 기본값
        default_random = preset_random_seed if preset_random_seed is not None else True
        use_random_seed = st.checkbox("🎲 랜덤 시드", value=default_random, key="chatter_random_seed")
    with col2:
        if not use_random_seed:
            # 프리셋 값이 있으면 사용, 없으면 기본값
            default_seed = preset_seed if preset_seed is not None else 42
            seed = st.number_input("Seed", min_value=0, value=default_seed, key="chatter_seed_input")
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

    # 파일에서 씬 데이터 존재 여부도 확인
    chatter_scenes_json_info = get_scenes_json_info()
    chatter_has_scene_file = chatter_scenes_json_info.get("exists", False)

    if st.session_state.get("scene_analysis_script") or chatter_has_scene_data or chatter_has_scene_file:
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
        # 🔄 새로고침 버튼 및 파일 정보
        chatter_refresh_col1, chatter_refresh_col2 = st.columns([3, 1])
        with chatter_refresh_col1:
            chatter_scenes_json_info = get_scenes_json_info()
            if chatter_scenes_json_info["exists"]:
                st.caption(f"📁 마지막 수정: {chatter_scenes_json_info['last_modified']} ({chatter_scenes_json_info['scene_count']}개 씬)")
        with chatter_refresh_col2:
            if st.button("🔄 새로고침", key="chatter_refresh_scenes", help="씬 분석 결과를 다시 로드합니다"):
                loaded_scenes, was_loaded = load_scenes_from_json(force_reload=True)
                if was_loaded and loaded_scenes:
                    st.success(f"✅ {len(loaded_scenes)}개 씬 새로고침 완료!")
                    st.rerun()
                else:
                    st.warning("씬 데이터가 없거나 로드에 실패했습니다.")

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
            # 씬 데이터를 컴포넌트용 형식으로 변환
            chatter_scenes_for_selector = []
            for idx, scene in enumerate(chatter_scenes_data):
                scene_id = scene.get('scene_id', idx + 1)
                scene_text = scene.get('script_text', '')
                chatter_scenes_for_selector.append({
                    "scene_id": scene_id,
                    "text": scene_text,
                    "script_text": scene_text,
                    "duration_estimate": scene.get('duration_estimate', max(1, len(scene_text) // 10))
                })

            # 씬 구간 선택 컴포넌트 사용
            chatter_selected_scene_numbers = render_scene_range_selector(
                total_scenes=len(chatter_scenes_data),
                scenes_data=chatter_scenes_for_selector,
                key_prefix="chatter_scene",
                show_header=True,
                default_mode="전체"
            )

            # 선택된 씬 필터링
            chatter_selected_scenes = []
            for scene_num in chatter_selected_scene_numbers:
                if scene_num <= len(chatter_scenes_data):
                    scene = chatter_scenes_data[scene_num - 1]
                    scene_id = scene.get('scene_id', scene_num)
                    scene_text = scene.get('script_text', '')
                    chatter_selected_scenes.append({
                        "scene_id": scene_id,
                        "text": scene_text,
                        "char_count": len(scene_text),
                        "duration_estimate": scene.get('duration_estimate', max(1, len(scene_text) // 10))
                    })

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

        # ⭐ AI 텍스트 전처리 (영어 → 발음 변환)
        if chatter_selected_scenes:
            st.markdown("---")
            chatter_preprocess_result = render_ai_preprocessing_panel(
                scenes=chatter_selected_scenes,
                session_key="chatterbox_preprocess",
                default_language="ko",  # Chatterbox는 주로 한국어
                show_preview=True,
                expanded=False
            )
            # 전처리 적용
            if chatter_preprocess_result.get("use_preprocessed"):
                chatter_selected_scenes = chatter_preprocess_result.get("preprocessed_scenes", chatter_selected_scenes)
                # script_text도 업데이트
                script_text = "\n\n".join([
                    s.get("preprocessed_text") or s.get("text", "")
                    for s in chatter_selected_scenes
                ])

    elif chatter_script_source == "씬 분석 스크립트" and not chatter_has_scene_data and chatter_has_scene_file:
        # 파일은 있지만 세션에 로드되지 않은 경우
        st.warning(f"📁 씬 분석 파일이 있습니다 ({chatter_scenes_json_info['scene_count']}개 씬). 로드 버튼을 눌러주세요.")
        if st.button("📥 씬 데이터 로드", key="chatter_load_scenes", type="primary"):
            loaded_scenes, was_loaded = load_scenes_from_json(force_reload=True)
            if was_loaded and loaded_scenes:
                st.success(f"✅ {len(loaded_scenes)}개 씬 로드 완료!")
                st.rerun()
            else:
                st.error("씬 데이터 로드에 실패했습니다.")

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

        # ⭐ 세션에서 이전 생성 결과 복원 (다운로드 옵션 선택 시 화면 유지)
        elif st.session_state.get("chatter_tts_generation_done"):
            chatter_audio_files = st.session_state.get("chatter_tts_audio_files", [])
            chatter_timestamp = st.session_state.get("chatter_tts_timestamp", 0)
            generated_files = st.session_state.get("last_chatterbox_scenes", [])

            if chatter_audio_files and generated_files:
                # 결과 요약
                success_count = len([f for f in generated_files if f and f.get("success") and f.get("audio_data")])
                st.success(f"✅ **{success_count}개** 씬 생성 완료!")

                # 씬별 오디오 플레이어
                st.markdown("### 🎵 생성된 음성 파일")
                for file_info in generated_files:
                    if not file_info:
                        continue
                    is_success = file_info.get("success") and file_info.get("audio_data")
                    if is_success:
                        scene_id = file_info.get("scene_id", 0)
                        text_preview = file_info.get("text_preview", file_info.get("text", "")[:50])
                        char_count = file_info.get("char_count", len(file_info.get("text", "")))
                        with st.expander(f"✅ 씬 {scene_id} - {text_preview} ({char_count}자)", expanded=False):
                            col1, col2 = st.columns([3, 1])
                            with col1:
                                if file_info.get("audio_data"):
                                    st.audio(file_info["audio_data"], format="audio/wav")
                                st.caption(f"⏱️ {file_info.get('duration', 0):.1f}초")
                            with col2:
                                if file_info.get("audio_data"):
                                    st.download_button(
                                        "⬇️",
                                        data=file_info["audio_data"],
                                        file_name=f"{scene_id}.wav",
                                        mime="audio/wav",
                                        key=f"chatter_restore_dl_{scene_id}",
                                        use_container_width=True
                                    )

                # 다운로드 섹션
                if len(chatter_audio_files) > 1:
                    st.markdown("---")
                    render_tts_download_section(
                        audio_files=chatter_audio_files,
                        project_name=f"chatterbox_{chatter_timestamp}",
                        extension="wav",
                        key_prefix="chatter_dl"
                    )

                # 초기화 버튼
                if st.button("🗑️ 결과 초기화", key="chatter_clear_results"):
                    st.session_state["chatter_tts_generation_done"] = False
                    st.session_state["chatter_tts_audio_files"] = []
                    st.session_state["last_chatterbox_scenes"] = []
                    st.rerun()

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
            # 품질 설정 가져오기
            quality_settings = st.session_state.get("chatter_quality_settings", None)

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
                norm_options=norm_options,
                quality_settings=quality_settings  # 품질 설정 전달
            )


def _handle_chatterbox_single_generation(text, voice_path, params, gen_options, norm_options=None, quality_settings=None):
    """단일 텍스트 Chatterbox 생성 핸들러 (청크 분할 + 재시도 + 정규화)"""

    if norm_options is None:
        norm_options = {"enabled": False}

    # 품질 설정 로깅
    if quality_settings:
        print(f"[TTS] 품질 설정 적용: {quality_settings.get('preprocess', {}).get('noisereduce_strength', 'default')}")

    result_container = st.container()

    with result_container:
        progress_bar = st.progress(0, text="준비 중...")
        status_text = st.empty()

        voice_name = os.path.basename(voice_path) if voice_path else "기본 음성"
        mode_label = "프리뷰" if gen_options["mode"] == "preview" else "전체"
        norm_label = " + 정규화" if norm_options.get("enabled") else ""

        status_text.info(f"🎙️ {mode_label}{norm_label} TTS 생성 준비 중... (참조 음성: {voice_name})")

        # ⭐⭐⭐ 참조 음성 최적화 - 사용자 선택 최우선! ⭐⭐⭐
        optimized_voice_path = voice_path
        if voice_path:
            try:
                # ⭐⭐⭐ 1순위: 사용자가 명시적으로 선택한 버전 ⭐⭐⭐
                user_selected = st.session_state.get("selected_reference_voice")
                if user_selected and os.path.exists(user_selected):
                    optimized_voice_path = user_selected
                    opt_type = "📌수동" if "__manual_" in user_selected else "🤖자동"
                    print(f"\n{'='*60}")
                    print(f"[VoiceOptimizer] ⭐ 사용자 선택 버전 사용!")
                    print(f"  경로: {user_selected}")
                    print(f"  파일: {os.path.basename(user_selected)}")
                    print(f"  타입: {opt_type}")
                    print(f"{'='*60}")
                # 2순위: 기존 자동 최적화 버전
                else:
                    existing_optimized = get_optimized_voice_path(voice_path)
                    if existing_optimized:
                        optimized_voice_path = existing_optimized
                        print(f"[VoiceOptimizer] ✅ 기존 자동 최적화 버전 사용: {os.path.basename(existing_optimized)}")
                    else:
                        # 3순위: 새로 최적화 생성
                        needs_opt, opt_reason = is_voice_optimization_needed(voice_path)
                        if needs_opt:
                            status_text.text(f"🔍 참조 음성 최적화 중...")
                            optimized_voice_path = optimize_voice_for_cloning(voice_path)

                            if optimized_voice_path != voice_path:
                                from pydub import AudioSegment
                                opt_audio = AudioSegment.from_file(optimized_voice_path)
                                print(f"[VoiceOptimizer] 최적화 적용: {len(opt_audio)/1000:.0f}초")
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
            progress_callback=progress_callback,
            quality_settings=quality_settings
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

    # ⭐⭐⭐ 참조 음성 최적화 - 사용자 선택 최우선! ⭐⭐⭐
    optimized_voice_path = voice_path
    if voice_path:
        try:
            # ⭐⭐⭐ 1순위: 사용자가 명시적으로 선택한 버전 ⭐⭐⭐
            user_selected = st.session_state.get("selected_reference_voice")
            if user_selected and os.path.exists(user_selected):
                optimized_voice_path = user_selected
                opt_type = "📌수동" if "__manual_" in user_selected else "🤖자동"
                print(f"\n{'='*60}")
                print(f"[VoiceOptimizer] 씬별 생성: ⭐ 사용자 선택 버전 사용!")
                print(f"  경로: {user_selected}")
                print(f"  파일: {os.path.basename(user_selected)}")
                print(f"  타입: {opt_type}")
                print(f"{'='*60}")
            # 2순위: 기존 자동 최적화 버전
            else:
                existing_optimized = get_optimized_voice_path(voice_path)
                if existing_optimized:
                    optimized_voice_path = existing_optimized
                    print(f"[VoiceOptimizer] 씬별 생성: ✅ 기존 자동 최적화 버전 사용: {os.path.basename(existing_optimized)}")
                else:
                    # 3순위: 새로 최적화 생성
                    needs_opt, opt_reason = is_voice_optimization_needed(voice_path)
                    if needs_opt:
                        status_text.text(f"🔍 참조 음성 최적화 중...")
                        optimized_voice_path = optimize_voice_for_cloning(voice_path)

                        if optimized_voice_path != voice_path:
                            from pydub import AudioSegment
                            opt_audio = AudioSegment.from_file(optimized_voice_path)
                            print(f"[VoiceOptimizer] 씬별 생성: 최적화 적용 {len(opt_audio)/1000:.0f}초")
        except Exception as e:
            print(f"[VoiceOptimizer] 씬별 생성: 최적화 실패 - {e}")
            optimized_voice_path = voice_path

    scene_params["voice_ref_path"] = optimized_voice_path  # ⭐ 사용자 선택 or 최적화된 음성 사용

    # 처리 방식 옵션 확인
    use_sequential = gen_options.get("use_sequential", True)
    use_smart_chunking = gen_options.get("use_smart_chunking", True)
    timeout_per_scene = gen_options.get("timeout_per_scene", 180)
    max_concurrent = gen_options.get("max_concurrent", 2)
    chunk_size = gen_options.get("chunk_size", 70)

    voice_info = os.path.basename(voice_path) if voice_path else "기본 음성"
    total_start = time.time()

    # 씬 데이터 준비 + ⭐⭐⭐ AI 전처리 텍스트 우선 사용! ⭐⭐⭐
    scene_list = []
    for idx, s in enumerate(scenes):
        scene_id = s.get("scene_id", idx + 1)

        # ============================================================
        # ⭐⭐⭐ 핵심 수정: AI 전처리 텍스트 우선 사용 ⭐⭐⭐
        # ============================================================
        if s.get("preprocessed_text"):
            # AI가 이미 전처리한 텍스트 사용 (추가 정규화 불필요!)
            final_text = s["preprocessed_text"]
            print(f"[TTS] 씬 {scene_id}: ✅ AI 전처리 텍스트 사용")
            print(f"[TTS] 씬 {scene_id}: '{final_text[:60]}...'")
        else:
            # AI 전처리 없는 경우에만 규칙 기반 정규화 적용
            original_text = s.get("text", "")
            if not original_text.strip():
                continue
            final_text = normalize_for_tts(original_text)
            if final_text != original_text:
                print(f"[TTS] 씬 {scene_id} 정규화: {original_text[:40]}... → {final_text[:40]}...")

        if not final_text.strip():
            continue

        scene_list.append({
            "scene_id": scene_id,
            "text": final_text
        })

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
    # ⭐⭐⭐ 통합 처리 완전 비활성화 (Voice Clone 원본 보존!) ⭐⭐⭐
    # ============================================================
    # 🔴 기존 문제:
    #   - UnifiedProcessor: 속도 조정 ±15% → 리듬 변형
    #   - FinalAdjust: 추가 속도 조정 ±5% → 추가 변형
    #   - 총 20%+ 속도 변형 → 기계적 음성!
    #
    # ✅ 해결:
    #   - 모든 후처리 스킵!
    #   - Chatterbox 생성 결과를 원본 그대로 사용
    #   - "예전에 잘 되었을 때"와 동일한 상태로 복원
    # ============================================================
    if norm_options.get("enabled") and generated_files:
        print("\n" + "="*60)
        print("[TTS] ⭐⭐⭐ Voice Clone 원본 보존 모드 (후처리 완전 비활성화!)")
        print("[TTS] ❌ UnifiedProcessor 스킵 → 속도 조정 없음")
        print("[TTS] ❌ FinalAdjust 스킵 → 추가 조정 없음")
        print("[TTS] ✅ Chatterbox 원본 그대로 사용!")
        print("="*60)

        # 처리 전 상태만 분석 (참고용)
        pre_stats = analyze_normalization_stats(generated_files)
        if not pre_stats.get("error"):
            print(f"[TTS] 현재 발화속도: {pre_stats['rate_min']:.2f} ~ {pre_stats['rate_max']:.2f} (±{pre_stats['rate_deviation_pct']:.1f}%)")
            print(f"[TTS] 💡 속도 편차가 있지만, 자연스러움 보존이 더 중요!")

        # ⭐⭐⭐ 후처리 완전 스킵! ⭐⭐⭐
        # generated_files = process_all_unified(...)  # ❌ 삭제!

        for i, f in enumerate(generated_files):
            if f and f.get("success"):
                print(f"  씬 {i+1}: 원본 유지 ✅")

        print("\n[TTS] ✅ 후처리 없이 원본 사용 완료")
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
                                    file_name=f"{scene_id}.wav",
                                    mime="audio/wav",
                                    key=f"chatter_robust_dl_scene_{scene_id}_{timestamp}",
                                    use_container_width=True
                                )
                else:
                    st.error(f"❌ 씬 {scene_id} 생성 실패: {file_info.get('error', '알 수 없는 오류')}")

            # 전체 ZIP 다운로드 (새 컴포넌트 사용)
            if success_count > 1:
                st.markdown("---")

                # 다운로드용 데이터 준비
                chatter_audio_files = []
                for file_info in generated_files:
                    if file_info["status"] in ["success", "partial"] and file_info.get("audio_data"):
                        chatter_audio_files.append({
                            "scene_id": file_info["scene_id"],
                            "data": file_info["audio_data"],
                            "format": "wav"
                        })

                # ⭐ 세션에 다운로드용 데이터 저장 (rerun 시 복원용)
                st.session_state["chatter_tts_audio_files"] = chatter_audio_files
                st.session_state["chatter_tts_timestamp"] = timestamp
                st.session_state["chatter_tts_generation_done"] = True

                # 새 다운로드 UI 렌더링
                render_tts_download_section(
                    audio_files=chatter_audio_files,
                    project_name=f"chatterbox_{timestamp}",
                    extension="wav",
                    key_prefix="chatter_dl"  # 고정 키 사용 (timestamp 제거)
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
                    "speed": 1.0,  # ⭐ 원본 속도로 생성 (후처리에서 조정)
                    "seed": seed,
                    "voice_ref_path": voice_ref_path,
                    "skip_speed_adjustment": True  # ⭐ Chatterbox 속도 조정 스킵
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

            # ⭐⭐⭐ 핵심 수정: AI 전처리 텍스트 우선 사용 ⭐⭐⭐
            if scene.get("preprocessed_text"):
                # AI가 이미 전처리한 텍스트 사용 (추가 정규화 불필요)
                scene_text = scene["preprocessed_text"]
                print(f"[TTS] 씬 {scene_id}: ✅ AI 전처리 텍스트 사용")
            else:
                # AI 전처리 없으면 원본에 규칙 기반 정규화 적용
                scene_text = scene.get("text", "")
                original_text = scene_text
                scene_text = normalize_for_tts(scene_text)
                if scene_text != original_text:
                    print(f"[TTS] 씬 {scene_id} 정규화: {original_text[:40]}... → {scene_text[:40]}...")
                else:
                    print(f"[TTS] 씬 {scene_id}: 원본 텍스트 사용")

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
                        "speed": 1.0,  # ⭐ 원본 속도로 생성 (후처리에서 조정)
                        "seed": seed,
                        "voice_ref_path": voice_ref_path,
                        "skip_speed_adjustment": True  # ⭐ Chatterbox 속도 조정 스킵
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
                                duration = result.get("duration_seconds", 0)
                                char_count = len(scene_text)

                                # ⭐⭐⭐ TTS 결과 검증: 비정상적인 speaking rate 감지 ⭐⭐⭐
                                speaking_rate = char_count / duration if duration > 0 else 0
                                MAX_SPEAKING_RATE = 12  # 정상: 5~8 char/sec, 비정상: > 12

                                if speaking_rate > MAX_SPEAKING_RATE and duration > 0:
                                    print(f"[TTS] ⚠️ 씬 {scene_id} 비정상 감지: {speaking_rate:.1f} char/sec (정상: 5-8)")

                                    # 재시도: temperature 낮추고 cfg_weight 높임
                                    retry_payload = {
                                        "text": scene_text,
                                        "settings": {
                                            "language": "ko",
                                            "exaggeration": max(0.3, exaggeration - 0.1),
                                            "cfg_weight": min(1.0, cfg_weight + 0.1),
                                            "temperature": max(0.3, temperature - 0.1),
                                            "speed": 1.0,  # ⭐ 원본 속도로 생성 (후처리에서 조정)
                                            "seed": seed + 1 if seed else None,
                                            "voice_ref_path": voice_ref_path,
                                            "skip_speed_adjustment": True  # ⭐ Chatterbox 속도 조정 스킵
                                        }
                                    }
                                    print(f"[TTS] 🔄 씬 {scene_id} 재시도 중...")
                                    retry_r = requests.post(f"{CHATTERBOX_URL}/generate", json=retry_payload, timeout=120)

                                    if retry_r.status_code == 200:
                                        retry_result = retry_r.json()
                                        if retry_result.get("success"):
                                            retry_url = f"{CHATTERBOX_URL}{retry_result.get('audio_url', '')}"
                                            retry_audio = requests.get(retry_url, timeout=30)
                                            if retry_audio.status_code == 200:
                                                retry_duration = retry_result.get("duration_seconds", 0)
                                                retry_rate = char_count / retry_duration if retry_duration > 0 else 0

                                                # 재시도 결과가 더 나으면 사용
                                                if retry_rate < speaking_rate:
                                                    print(f"[TTS] ✅ 씬 {scene_id} 재시도 성공: {retry_rate:.1f} char/sec")
                                                    audio_response = retry_audio
                                                    duration = retry_duration
                                                    speaking_rate = retry_rate
                                                else:
                                                    print(f"[TTS] ❌ 씬 {scene_id} 재시도 실패, 원본 사용")

                                with open(audio_path, "wb") as f:
                                    f.write(audio_response.content)

                                # speaking rate 경고 추가
                                status_msg = "success"
                                if speaking_rate > MAX_SPEAKING_RATE:
                                    status_msg = "warning"  # 여전히 비정상적인 경우 경고
                                    print(f"[TTS] ⚠️ 씬 {scene_id}: 최종 speaking rate {speaking_rate:.1f} char/sec (비정상)")

                                generated_files.append({
                                    "scene_id": scene_id,
                                    "path": audio_path,
                                    "text_preview": scene_text[:50] + "..." if len(scene_text) > 50 else scene_text,
                                    "char_count": char_count,
                                    "duration": duration,
                                    "speaking_rate": speaking_rate,
                                    "processing_time": elapsed,
                                    "status": status_msg
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
        success_count = len([f for f in generated_files if f["status"] in ("success", "warning")])
        warning_count = len([f for f in generated_files if f["status"] == "warning"])
        failed_count = len([f for f in generated_files if f["status"] == "failed"])

        with results_container:
            if success_count > 0:
                if warning_count > 0:
                    st.warning(f"⚠️ **{success_count}/{total_scenes}개** 씬 생성 완료 ({warning_count}개 비정상 speaking rate)")
                else:
                    st.success(f"✅ **{success_count}/{total_scenes}개** 씬 생성 완료!")

                # 씬별 오디오 플레이어 및 다운로드
                st.markdown("### 🎵 생성된 음성 파일")

                for file_info in generated_files:
                    scene_id = file_info["scene_id"]

                    if file_info["status"] in ("success", "warning"):
                        # 경고 표시 추가
                        warn_icon = "⚠️" if file_info["status"] == "warning" else "📢"
                        rate_info = f" | {file_info.get('speaking_rate', 0):.1f} 글자/초" if file_info.get("speaking_rate") else ""

                        with st.expander(f"{warn_icon} 씬 {scene_id} - {file_info['text_preview']} ({file_info['char_count']}자)", expanded=True):
                            # 비정상 speaking rate 경고
                            if file_info["status"] == "warning":
                                st.warning(f"⚠️ 비정상 speaking rate: {file_info.get('speaking_rate', 0):.1f} 글자/초 (정상: 5-8)")

                            col1, col2 = st.columns([3, 1])

                            with col1:
                                st.audio(file_info["path"])
                                st.caption(f"⏱️ {file_info.get('duration', 0):.1f}초 | 처리시간: {file_info.get('processing_time', 0):.1f}s{rate_info}")

                            with col2:
                                with open(file_info["path"], "rb") as f:
                                    st.download_button(
                                        "⬇️ 다운로드",
                                        data=f.read(),
                                        file_name=f"{scene_id}.wav",
                                        mime="audio/wav",
                                        key=f"chatter_download_scene_{scene_id}_{timestamp}",
                                        use_container_width=True
                                    )
                    else:
                        st.error(f"❌ 씬 {scene_id} 생성 실패: {file_info.get('error', '알 수 없는 오류')}")

                # 전체 ZIP 다운로드 (새 컴포넌트 사용)
                if success_count > 1:
                    st.markdown("---")

                    # 다운로드용 데이터 준비
                    chatter_legacy_files = []
                    for file_info in generated_files:
                        if file_info["status"] == "success" and file_info["path"]:
                            chatter_legacy_files.append({
                                "scene_id": file_info["scene_id"],
                                "path": file_info["path"]
                            })

                    # 새 다운로드 UI 렌더링
                    render_tts_download_section(
                        audio_files=chatter_legacy_files,
                        project_name=f"chatterbox_{timestamp}",
                        extension="wav",
                        key_prefix=f"chatter_legacy_dl_{timestamp}"
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

    # ============================================================
    # 🔄 씬 분석 결과 자동 로드
    # ============================================================
    # 페이지 진입 시 scenes.json 파일에서 자동으로 씬 데이터 로드
    scenes_info = get_scenes_json_info()
    if scenes_info["exists"]:
        # 파일이 수정됐거나 세션에 데이터가 없으면 자동 로드
        current_scenes = st.session_state.get("scenes", [])
        if not current_scenes:
            loaded_scenes, was_loaded = load_scenes_from_json(force_reload=False)
            if was_loaded and loaded_scenes:
                st.toast(f"✅ 씬 분석 결과 자동 로드됨 ({len(loaded_scenes)}개 씬)", icon="📥")

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
