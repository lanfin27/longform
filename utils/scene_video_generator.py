# -*- coding: utf-8 -*-
"""
utils/scene_video_generator.py
씬 이미지에서 AI 비디오 생성

주요 기능:
1. 씬 이미지를 Video API로 변환
2. 비디오 프롬프트 조합
3. 생성 결과 저장
4. ⭐ v3.22: SRT/TTS 기반 비디오 길이 자동 추천
5. ⭐ v3.23: 묶음 비디오 길이 캐싱 (중복 계산 방지)
"""

import os
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime

# Video API imports
try:
    from utils.video_api import (
        generate_video_sync,
        ALL_MODELS,
        PLATFORM_CONFIGS,
        VideoType,
        CostCalculator,
        VideoGenerationRequest,
        VideoGenerationResult,
        get_api_key,
    )
    VIDEO_API_AVAILABLE = True
except ImportError as e:
    VIDEO_API_AVAILABLE = False
    print(f"[SceneVideoGenerator] Video API 모듈 로드 실패: {e}")


# ============================================================
# ⭐ v3.22: SRT/TTS 기반 비디오 길이 자동 추천
# ============================================================

def get_scene_srt_duration(scene: Dict) -> Optional[float]:
    """
    씬의 SRT/TTS duration 가져오기

    여러 필드를 확인하여 실제 오디오/SRT 기반 duration 반환.
    추정치(duration_estimate)는 사용하지 않음.

    Args:
        scene: 씬 데이터 딕셔너리

    Returns:
        실제 duration (초) 또는 None (데이터 없음)
    """
    # 실제 TTS/오디오 duration 필드들 (추정치 제외)
    duration = (
        scene.get("tts_duration") or
        scene.get("audio_duration") or
        scene.get("final_duration") or
        scene.get("srt_duration") or
        scene.get("duration") or
        scene.get("scene_duration") or
        None
    )

    # duration_estimate는 텍스트 길이 기반 추정치이므로 제외
    # 실제 TTS/SRT 데이터가 있는 경우에만 반환
    if duration and duration > 0:
        return float(duration)

    return None


def estimate_scene_duration(scene: Dict, chars_per_second: float = 4.0) -> float:
    """
    씬의 스크립트 길이 기반 duration 추정

    실제 TTS duration이 없을 때 폴백으로 사용.

    Args:
        scene: 씬 데이터 딕셔너리
        chars_per_second: 초당 글자 수 (기본: 4.0)

    Returns:
        추정 duration (초)
    """
    # 스크립트 텍스트 가져오기
    script = (
        scene.get("script_text") or
        scene.get("스크립트") or
        scene.get("text") or
        ""
    )

    if not script:
        return 5.0  # 기본값

    # 공백 제거한 글자 수
    char_count = len(script.replace(" ", "").replace("\n", ""))

    # 최소 2초, 최대 30초
    duration = max(2.0, min(30.0, char_count / chars_per_second))

    return round(duration, 2)


def get_recommended_video_duration(
    scene: Dict,
    threshold: float = 6.0,
    short_duration: int = 5,
    long_duration: int = 10
) -> Tuple[int, Optional[float], str]:
    """
    씬의 SRT/TTS duration에 따른 비디오 길이 추천

    규칙:
    - 0~6초 씬 → 5초 비디오 (짧은 씬)
    - 7초 이상 씬 → 10초 비디오 (긴 씬)

    Args:
        scene: 씬 데이터 딕셔너리
        threshold: 기준점 (초) - 이하면 short, 초과면 long
        short_duration: 짧은 씬용 비디오 길이
        long_duration: 긴 씬용 비디오 길이

    Returns:
        (추천_비디오_길이, 씬_duration, 추천_이유)
    """
    # 실제 SRT/TTS duration 확인
    scene_duration = get_scene_srt_duration(scene)

    if scene_duration is not None:
        # 실제 데이터 기반 추천
        if scene_duration <= threshold:
            return (
                short_duration,
                scene_duration,
                f"SRT {scene_duration:.1f}초 → {short_duration}초 추천"
            )
        else:
            return (
                long_duration,
                scene_duration,
                f"SRT {scene_duration:.1f}초 → {long_duration}초 추천"
            )
    else:
        # 실제 데이터 없음 - 추정치 사용
        estimated = scene.get("duration_estimate") or estimate_scene_duration(scene)

        if estimated <= threshold:
            return (
                short_duration,
                None,
                f"추정 {estimated:.1f}초 → {short_duration}초 (TTS 없음)"
            )
        else:
            return (
                long_duration,
                None,
                f"추정 {estimated:.1f}초 → {long_duration}초 (TTS 없음)"
            )


# ============================================================
# ⭐ v3.24: 묶음(Bundle) 기반 최적화 비디오 길이 계산
# ============================================================

def calculate_bundle_srt_duration(bundle_scenes: List[Dict]) -> float:
    """
    묶음 내 모든 씬의 총 SRT/TTS 길이 계산

    Args:
        bundle_scenes: 같은 묶음에 속한 씬들의 리스트

    Returns:
        총 길이 (초)
    """
    total_duration = 0.0

    for scene in bundle_scenes:
        # 실제 TTS/SRT duration 우선
        scene_dur = get_scene_srt_duration(scene)

        if scene_dur is not None:
            total_duration += scene_dur
        else:
            # 폴백: duration 또는 duration_estimate 사용
            fallback_dur = scene.get('duration', scene.get('duration_estimate', 0))
            if isinstance(fallback_dur, (int, float)):
                total_duration += float(fallback_dur)

    return total_duration


# ⭐ v1.1: 묶음 비디오 길이 캐싱 (중복 계산 방지)
_bundle_video_dur_cache: Dict[str, Tuple[float, float, str]] = {}


def get_optimal_bundle_video_duration(
    bundle_scenes: List[Dict],
    buffer: float = 0.5,
    min_duration: float = 2.0,
    max_duration: float = 10.0
) -> Tuple[float, float, str]:
    """
    API 비용 최적화를 위한 묶음 비디오 생성 길이 계산

    규칙: 비디오 길이 = 묶음 SRT 총 길이 + 버퍼(0.5초)

    v1.1: 캐싱 추가 - 동일 씬 조합에 대해 재계산 방지

    Args:
        bundle_scenes: 같은 묶음에 속한 씬들의 리스트
        buffer: 추가 버퍼 시간 (기본 0.5초)
        min_duration: 최소 비디오 길이 (기본 2.0초)
        max_duration: 최대 비디오 길이 (기본 10.0초)

    Returns:
        (최적화_비디오_길이, 묶음_SRT_길이, 설명)
    """
    global _bundle_video_dur_cache

    # v1.1: 캐시 키 생성 (씬 ID 조합)
    scene_ids = tuple(sorted(s.get('scene_id', s.get('id', 0)) for s in bundle_scenes))
    cache_key = f"{scene_ids}_{buffer}_{min_duration}_{max_duration}"

    # 캐시 히트
    if cache_key in _bundle_video_dur_cache:
        return _bundle_video_dur_cache[cache_key]

    # 묶음 SRT 총 길이 계산
    srt_duration = calculate_bundle_srt_duration(bundle_scenes)

    # 비디오 길이 = SRT + 버퍼
    video_duration = srt_duration + buffer

    # 소수점 첫째자리까지 반올림
    video_duration = round(video_duration, 1)

    # 최소/최대 범위 적용
    original_video_duration = video_duration
    video_duration = max(min_duration, min(max_duration, video_duration))

    # 설명 생성
    if original_video_duration != video_duration:
        if original_video_duration < min_duration:
            reason = f"SRT {srt_duration:.1f}초 + {buffer}초 → {video_duration}초 (최소값 적용)"
        else:
            reason = f"SRT {srt_duration:.1f}초 + {buffer}초 → {video_duration}초 (최대값 적용)"
    else:
        reason = f"SRT {srt_duration:.1f}초 + {buffer}초 = {video_duration}초"

    # v1.1: 최초 계산 시에만 로그 출력
    print(f"[BundleVideoDur] 씬 {list(scene_ids)}: SRT={srt_duration:.1f}초 → {video_duration}초")

    # 캐시 저장
    result = (video_duration, srt_duration, reason)
    _bundle_video_dur_cache[cache_key] = result

    return result


def get_bundle_scenes_by_id(
    scenes: List[Dict],
    bundle_id: int
) -> List[Dict]:
    """
    묶음 ID로 해당 묶음의 모든 씬 가져오기

    Args:
        scenes: 전체 씬 리스트
        bundle_id: 묶음 ID

    Returns:
        해당 묶음의 씬 리스트 (scene_id 순 정렬)
    """
    bundle_scenes = []

    for scene in scenes:
        bid = scene.get('bundle_id', scene.get('scene_id', scene.get('id', 0)))
        if bid == bundle_id:
            bundle_scenes.append(scene)

    # scene_id 순 정렬
    bundle_scenes.sort(key=lambda s: s.get('scene_id', s.get('id', 0)))

    return bundle_scenes


def get_batch_duration_info(
    scenes: List[Dict],
    threshold: float = 6.0
) -> Dict[str, Any]:
    """
    배치 생성을 위한 씬별 duration 정보 요약

    Args:
        scenes: 씬 리스트
        threshold: 기준점 (초)

    Returns:
        요약 정보 딕셔너리
    """
    short_scenes = []  # 5초 추천
    long_scenes = []   # 10초 추천
    no_data_scenes = []  # TTS 데이터 없음

    for scene in scenes:
        scene_id = scene.get("scene_id") or scene.get("scene_num") or 0
        recommended, actual_duration, reason = get_recommended_video_duration(
            scene, threshold=threshold
        )

        info = {
            "scene_id": scene_id,
            "recommended_duration": recommended,
            "actual_duration": actual_duration,
            "reason": reason
        }

        if actual_duration is None:
            no_data_scenes.append(info)
        elif actual_duration <= threshold:
            short_scenes.append(info)
        else:
            long_scenes.append(info)

    return {
        "total": len(scenes),
        "short_count": len(short_scenes),  # 5초 추천
        "long_count": len(long_scenes),    # 10초 추천
        "no_data_count": len(no_data_scenes),
        "short_scenes": short_scenes,
        "long_scenes": long_scenes,
        "no_data_scenes": no_data_scenes,
        "has_tts_data": len(no_data_scenes) < len(scenes),
    }


def get_available_video_platforms() -> List[str]:
    """사용 가능한 Video API 플랫폼 목록"""
    if not VIDEO_API_AVAILABLE:
        return []

    available = []
    for platform, config in PLATFORM_CONFIGS.items():
        env_key = config.get("env_key")
        if env_key and get_api_key(env_key):
            available.append(platform)

    return available


def get_i2v_models_for_platform(platform: str) -> Dict[str, Any]:
    """플랫폼의 Image-to-Video 모델 목록"""
    if not VIDEO_API_AVAILABLE or platform not in ALL_MODELS:
        return {}

    return {
        k: v for k, v in ALL_MODELS[platform].items()
        if v.video_type in [VideoType.IMAGE_TO_VIDEO, VideoType.BOTH]
    }


def estimate_video_cost(
    platform: str,
    model_key: str,
    duration: int = 5,
    resolution: str = "720p"
) -> Optional[Dict]:
    """비디오 생성 비용 예측"""
    if not VIDEO_API_AVAILABLE:
        return None

    try:
        estimate = CostCalculator.estimate_cost(
            platform=platform,
            model_key=model_key,
            duration=duration,
            resolution=resolution
        )

        return {
            "cost_usd": estimate.estimated_cost_usd,
            "credits": estimate.estimated_credits,
            "time_seconds": estimate.estimated_time_seconds,
            "speed_tier": estimate.speed_tier,
            "quality_tier": estimate.quality_tier,
            "model_name": estimate.model_display_name,
            "legal_warning": estimate.legal_warning,
        }
    except Exception as e:
        return {"error": str(e)}


def generate_scene_video(
    image_path: str,
    prompt: str,
    platform: str = "fal_ai",
    model_key: str = "wan_i2v",
    duration: int = 5,
    resolution: str = "720p",
    output_dir: str = None,
    scene_id: int = None,
    negative_prompt: str = None,
) -> Dict[str, Any]:
    """
    씬 이미지에서 AI 비디오 생성 (v3.23: 상세 로깅 추가)

    Args:
        image_path: 소스 이미지 경로
        prompt: 비디오 프롬프트
        platform: API 플랫폼 (fal_ai, replicate, pixverse)
        model_key: 모델 키
        duration: 영상 길이 (초)
        resolution: 해상도
        output_dir: 출력 디렉토리
        scene_id: 씬 번호 (파일명용)
        negative_prompt: 네거티브 프롬프트

    Returns:
        생성 결과 딕셔너리
    """
    print(f"[SceneVideoGen] ========== 비디오 생성 시작 ==========")
    print(f"[SceneVideoGen] 씬 ID: {scene_id}")
    print(f"[SceneVideoGen] 플랫폼: {platform}, 모델: {model_key}")
    print(f"[SceneVideoGen] 길이: {duration}초, 해상도: {resolution}")
    print(f"[SceneVideoGen] 이미지: {image_path}")
    print(f"[SceneVideoGen] 프롬프트: {prompt[:100]}..." if len(prompt) > 100 else f"[SceneVideoGen] 프롬프트: {prompt}")

    if not VIDEO_API_AVAILABLE:
        print(f"[SceneVideoGen] ❌ Video API 모듈 없음")
        return {
            "success": False,
            "error": "Video API 모듈이 설치되지 않았습니다."
        }

    # 이미지 확인
    if not image_path or not Path(image_path).exists():
        print(f"[SceneVideoGen] ❌ 이미지 없음: {image_path}")
        return {
            "success": False,
            "error": f"이미지를 찾을 수 없습니다: {image_path}"
        }
    print(f"[SceneVideoGen] ✅ 이미지 확인됨")

    # 출력 디렉토리
    if not output_dir:
        output_dir = str(Path(image_path).parent.parent / "videos" / "ai_generated")

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    print(f"[SceneVideoGen] 출력 디렉토리: {output_dir}")

    # 출력 파일명
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if scene_id:
        output_filename = f"scene_{scene_id:03d}_video_{timestamp}.mp4"
    else:
        output_filename = f"video_{timestamp}.mp4"

    output_path = str(Path(output_dir) / output_filename)
    print(f"[SceneVideoGen] 출력 파일: {output_path}")

    try:
        # Duration 검증 및 보정 (모델별 허용 값으로 스냅)
        from utils.video_api.config import validate_video_duration
        validated_duration = validate_video_duration(duration, platform, model_key)
        if validated_duration != duration:
            print(f"[SceneVideoGen] Duration 보정: {duration}초 → {validated_duration}초")
        duration = validated_duration

        print(f"[SceneVideoGen] Video API 호출 중...")
        # Video API 호출
        result = generate_video_sync(
            prompt=prompt,
            image_path=image_path,
            platform=platform,
            model_key=model_key,
            duration=duration,
            resolution=resolution,
            save_locally=True,
            output_dir=output_dir,
            negative_prompt=negative_prompt,
        )

        print(f"[SceneVideoGen] API 응답 수신")
        print(f"[SceneVideoGen] 성공 여부: {result.success}")

        if result.success:
            local_path = result.local_path or output_path
            print(f"[SceneVideoGen] ✅ 비디오 생성 성공!")
            print(f"[SceneVideoGen] 비디오 URL: {result.video_url}")
            print(f"[SceneVideoGen] 로컬 경로: {local_path}")
            print(f"[SceneVideoGen] 파일 존재: {Path(local_path).exists() if local_path else False}")
            print(f"[SceneVideoGen] 비용: ${result.cost_usd:.3f}")
            print(f"[SceneVideoGen] 생성 시간: {result.generation_time:.1f}초")

            # ⭐ v2.4: 최종 프롬프트 정보 추가
            metadata = result.metadata or {}
            return {
                "success": True,
                "video_url": result.video_url,
                "video_path": local_path,
                "cost_usd": result.cost_usd,
                "credits_used": result.credits_used,
                "platform": result.platform_used,
                "model": result.model_display_name,
                "duration": result.duration,
                "generation_time": result.generation_time,
                # 프롬프트 정보 (v2.4)
                "original_prompt": metadata.get("original_prompt", prompt),
                "final_prompt": metadata.get("final_prompt", prompt),
                "prompt_expanded": metadata.get("prompt_expanded", False),
            }
        else:
            error_msg = result.error_message or "비디오 생성 실패"
            print(f"[SceneVideoGen] ❌ 생성 실패: {error_msg}")
            return {
                "success": False,
                "error": error_msg
            }

    except Exception as e:
        import traceback
        print(f"[SceneVideoGen] ❌ 예외 발생: {e}")
        print(f"[SceneVideoGen] 스택 트레이스:\n{traceback.format_exc()}")
        return {
            "success": False,
            "error": str(e)
        }


def get_video_prompt_for_scene(
    scene: Dict,
    prompt_type: str = "full"
) -> str:
    """
    씬 데이터에서 비디오 프롬프트 추출

    Args:
        scene: 씬 데이터 딕셔너리
        prompt_type: "character" 또는 "full"

    Returns:
        비디오 프롬프트 문자열
    """
    if prompt_type == "character":
        # 캐릭터 중심 프롬프트
        prompt = (
            scene.get("video_prompt_character", "") or
            scene.get("prompts", {}).get("video_prompt_character", "") or
            ""
        )
    else:
        # 전체 장면 프롬프트
        prompt = (
            scene.get("video_prompt_full", "") or
            scene.get("prompts", {}).get("video_prompt_full", "") or
            ""
        )

    # 프롬프트가 없으면 이미지 프롬프트로 대체
    if not prompt or prompt.upper() == "N/A":
        image_prompt = (
            scene.get("image_prompt", "") or
            scene.get("image_prompt_en", "") or
            scene.get("prompts", {}).get("image_prompt", "") or
            ""
        )

        if image_prompt:
            # 이미지 프롬프트에 모션 힌트 추가
            if prompt_type == "character":
                prompt = f"{image_prompt}. Subtle character movement, natural breathing, slight head turn."
            else:
                prompt = f"{image_prompt}. Cinematic camera movement, ambient motion, atmospheric lighting."
        else:
            # 기본 프롬프트
            prompt = "Cinematic video with subtle motion and atmospheric lighting."

    return prompt


def get_scene_image_path(scene: Dict, project_path: str = None) -> Optional[str]:
    """씬의 이미지 경로 추출 (v2.4: Step3 실사 대체 이미지 지원 강화)"""

    # ⭐ v2.4: Step3 실사 대체 이미지 경로 필드 우선 확인
    real_image_path = (
        scene.get("real_image_path") or           # Step3에서 설정
        scene.get("replaced_image_path") or
        scene.get("composited_image_path") or     # Step3에서 설정
        None
    )
    if real_image_path and Path(real_image_path).exists():
        return str(real_image_path)

    # 다양한 이미지 경로 필드 확인 (v2.5: nano_composite_image, composite_image_path 추가)
    image_path = (
        scene.get("nano_composite_image") or       # Step1/Step2 생성 이미지
        scene.get("composite_image_path") or       # 합성 이미지
        scene.get("image_path") or
        scene.get("background_image_path") or
        scene.get("scene_image_path") or
        None
    )

    if image_path and Path(image_path).exists():
        return str(image_path)

    # scene_id로 이미지 찾기
    scene_id = scene.get("scene_id") or scene.get("scene_num") or scene.get("scene_number")

    if scene_id and project_path:
        project = Path(project_path)

        # ⭐ v2.3: 실사 이미지 폴더 먼저 확인
        real_folder = project / "images" / "real"
        if real_folder.exists():
            for ext in [".png", ".jpg", ".jpeg", ".webp"]:
                real_path = real_folder / f"real_scene_{scene_id:03d}{ext}"
                if real_path.exists():
                    return str(real_path)

        # 1. 정확한 파일명 패턴 먼저 확인 (AI 매핑 패턴 포함)
        exact_patterns = [
            f"images/composited/scene_{scene_id:03d}.png",
            f"images/composited/{scene_id}.png",
            f"images/scenes/scene_{scene_id:03d}.png",
            f"images/scenes/{scene_id:03d}_scene.png",  # AI 매핑 패턴
            f"images/scenes/{scene_id:03d}_scene.jpg",  # AI 매핑 패턴
            f"images/scenes/{scene_id:03d}_scene_composed.jpg",  # 합성 이미지 패턴
            f"images/backgrounds/scene_{scene_id:03d}.png",
        ]

        for pattern in exact_patterns:
            full_path = project / pattern
            if full_path.exists():
                return str(full_path)

        # 2. ⭐ 타임스탬프가 포함된 파일 검색 (최신 이미지 선택)
        search_dirs = [
            project / "images" / "real",  # ⭐ v2.3: 실사 이미지 폴더 추가
            project / "images" / "composited",
            project / "images" / "korean_text",    # ⭐ v2.5: 한글 텍스트 이미지 폴더 추가
            project / "images" / "backgrounds",
            project / "images" / "scenes",
        ]

        all_matches = []
        for search_dir in search_dirs:
            if not search_dir.exists():
                continue

            # ⭐ v2.4: Step3 실사 대체 패턴 추가 (composited_XXX_timestamp.ext)
            # composited_046_*, real_scene_*, bg_scene_017_*, scene_017_*, 017_scene* 패턴 검색
            for pattern in [f"composited_{scene_id:03d}_*", f"real_scene_{scene_id:03d}*", f"korean_text_scene_{scene_id:03d}_*", f"*scene_{scene_id:03d}_*.png", f"*_{scene_id:03d}_*.png", f"{scene_id:03d}_scene*"]:
                for img in search_dir.glob(pattern):
                    try:
                        mtime = img.stat().st_mtime
                        all_matches.append((img, mtime))
                    except (OSError, IOError):
                        continue

        if all_matches:
            # 최신 이미지 선택
            all_matches.sort(key=lambda x: x[1], reverse=True)
            return str(all_matches[0][0])

    return None


def batch_generate_scene_videos(
    scenes: List[Dict],
    project_path: str,
    platform: str = "fal_ai",
    model_key: str = "wan_i2v",
    prompt_type: str = "full",
    duration: int = 5,
    resolution: str = "720p",
    progress_callback=None,
    auto_duration: bool = False,
    duration_threshold: float = 6.0,
) -> List[Dict]:
    """
    여러 씬의 비디오 일괄 생성

    Args:
        scenes: 씬 데이터 리스트
        project_path: 프로젝트 경로
        platform: API 플랫폼
        model_key: 모델 키
        prompt_type: 프롬프트 타입
        duration: 영상 길이 (auto_duration=False일 때 사용)
        resolution: 해상도
        progress_callback: 진행률 콜백 (current, total, message)
        auto_duration: ⭐ v3.22: True면 씬별 SRT duration에 따라 자동 결정
        duration_threshold: ⭐ v3.22: 자동 모드 기준점 (기본 6초)

    Returns:
        생성 결과 리스트
    """
    results = []
    total = len(scenes)
    output_dir = str(Path(project_path) / "videos" / "ai_generated")

    for idx, scene in enumerate(scenes):
        scene_id = scene.get("scene_id") or scene.get("scene_num") or (idx + 1)

        # ⭐ v3.22: 자동 모드일 때 씬별 duration 결정
        if auto_duration:
            scene_duration, actual_dur, reason = get_recommended_video_duration(
                scene, threshold=duration_threshold
            )
            duration_msg = f"({reason})"
        else:
            scene_duration = duration
            duration_msg = f"({duration}초)"

        if progress_callback:
            progress_callback(idx, total, f"씬 {scene_id} 처리 중... {duration_msg}")

        # ⭐ v3.23: 이미지 경로 확인 (캐시된 경로 우선 사용)
        image_path = scene.get("_batch_image_path") or get_scene_image_path(scene, project_path)
        if not image_path:
            results.append({
                "scene_id": scene_id,
                "success": False,
                "error": "이미지를 찾을 수 없습니다"
            })
            continue

        # 프롬프트 추출
        prompt = get_video_prompt_for_scene(scene, prompt_type)

        # 비디오 생성
        result = generate_scene_video(
            image_path=image_path,
            prompt=prompt,
            platform=platform,
            model_key=model_key,
            duration=scene_duration,
            resolution=resolution,
            output_dir=output_dir,
            scene_id=scene_id,
        )

        result["scene_id"] = scene_id
        # ⭐ v3.22: 사용된 duration 정보 추가
        result["video_duration"] = scene_duration
        if auto_duration:
            result["auto_duration_reason"] = reason
        results.append(result)

    if progress_callback:
        progress_callback(total, total, "완료!")

    return results
