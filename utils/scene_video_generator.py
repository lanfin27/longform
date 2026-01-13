# -*- coding: utf-8 -*-
"""
utils/scene_video_generator.py
씬 이미지에서 AI 비디오 생성

주요 기능:
1. 씬 이미지를 Video API로 변환
2. 비디오 프롬프트 조합
3. 생성 결과 저장
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
    씬 이미지에서 AI 비디오 생성

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
    if not VIDEO_API_AVAILABLE:
        return {
            "success": False,
            "error": "Video API 모듈이 설치되지 않았습니다."
        }

    # 이미지 확인
    if not image_path or not Path(image_path).exists():
        return {
            "success": False,
            "error": f"이미지를 찾을 수 없습니다: {image_path}"
        }

    # 출력 디렉토리
    if not output_dir:
        output_dir = str(Path(image_path).parent.parent / "videos" / "ai_generated")

    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # 출력 파일명
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if scene_id:
        output_filename = f"scene_{scene_id:03d}_video_{timestamp}.mp4"
    else:
        output_filename = f"video_{timestamp}.mp4"

    output_path = str(Path(output_dir) / output_filename)

    try:
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

        if result.success:
            return {
                "success": True,
                "video_url": result.video_url,
                "video_path": result.local_path or output_path,
                "cost_usd": result.cost_usd,
                "credits_used": result.credits_used,
                "platform": result.platform_used,
                "model": result.model_display_name,
                "duration": result.duration,
                "generation_time": result.generation_time,
            }
        else:
            return {
                "success": False,
                "error": result.error_message or "비디오 생성 실패"
            }

    except Exception as e:
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
    """씬의 이미지 경로 추출 (최신 이미지 우선)"""
    # 다양한 이미지 경로 필드 확인
    image_path = (
        scene.get("composited_image_path") or
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
            project / "images" / "composited",
            project / "images" / "backgrounds",
            project / "images" / "scenes",
        ]

        all_matches = []
        for search_dir in search_dirs:
            if not search_dir.exists():
                continue

            # bg_scene_017_*, scene_017_*, 017_scene* 패턴 검색
            for pattern in [f"*scene_{scene_id:03d}_*.png", f"*_{scene_id:03d}_*.png", f"{scene_id:03d}_scene*"]:
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
) -> List[Dict]:
    """
    여러 씬의 비디오 일괄 생성

    Args:
        scenes: 씬 데이터 리스트
        project_path: 프로젝트 경로
        platform: API 플랫폼
        model_key: 모델 키
        prompt_type: 프롬프트 타입
        duration: 영상 길이
        resolution: 해상도
        progress_callback: 진행률 콜백 (current, total, message)

    Returns:
        생성 결과 리스트
    """
    results = []
    total = len(scenes)
    output_dir = str(Path(project_path) / "videos" / "ai_generated")

    for idx, scene in enumerate(scenes):
        scene_id = scene.get("scene_id") or scene.get("scene_num") or (idx + 1)

        if progress_callback:
            progress_callback(idx, total, f"씬 {scene_id} 처리 중...")

        # 이미지 경로 확인
        image_path = get_scene_image_path(scene, project_path)
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
            duration=duration,
            resolution=resolution,
            output_dir=output_dir,
            scene_id=scene_id,
        )

        result["scene_id"] = scene_id
        results.append(result)

    if progress_callback:
        progress_callback(total, total, "완료!")

    return results
