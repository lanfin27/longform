# -*- coding: utf-8 -*-
"""
인포그래픽 캐릭터 합성기 v3

인포그래픽 동영상에 캐릭터 이미지 오버레이

기능:
- 동영상 전체 길이에 캐릭터 PNG 오버레이 (FFmpeg filter_complex)
- 다양한 위치 지원 (왼쪽, 오른쪽, 중앙 등)
- 크기 조정
- 합성 결과 썸네일 생성
- 배치 합성
- 🆕 자동 배경 제거 (rembg 통합)
- 🆕 씬-캐릭터 자동 매핑
"""

import os
import subprocess
from typing import Dict, List, Optional, Tuple, Callable, Any
from pathlib import Path
from PIL import Image

from utils.models.infographic import InfographicScene, InfographicData

# 배경 제거 모듈 임포트 (옵셔널)
try:
    from utils.background_remover import (
        is_rembg_available,
        has_transparency,
        remove_background_simple
    )
    BG_REMOVER_AVAILABLE = True
except ImportError:
    BG_REMOVER_AVAILABLE = False

# 씬-캐릭터 매퍼 임포트 (옵셔널)
try:
    from utils.scene_character_mapper import SceneCharacterMapper
    MAPPER_AVAILABLE = True
except ImportError:
    MAPPER_AVAILABLE = False


class InfographicCharacterCompositor:
    """
    인포그래픽 동영상에 캐릭터 합성

    - 동영상 전체 길이에 캐릭터 PNG 오버레이
    - FFmpeg filter_complex 사용
    """

    # 수평 위치 매핑 (화면 너비 비율)
    POSITION_MAP = {
        "왼쪽": 0.05,
        "중앙-왼쪽": 0.25,
        "중앙": 0.5,
        "중앙-오른쪽": 0.75,
        "오른쪽": 0.95
    }

    # 영어 위치 지원
    POSITION_MAP_EN = {
        "left": 0.05,
        "center-left": 0.25,
        "center": 0.5,
        "center-right": 0.75,
        "right": 0.95
    }

    def __init__(
        self,
        output_dir: str = "outputs/infographic_composites",
        auto_remove_bg: bool = True,
        project_path: str = None
    ):
        """
        Args:
            output_dir: 출력 디렉토리
            auto_remove_bg: 배경 자동 제거 여부
            project_path: 프로젝트 경로 (자동 매핑용)
        """
        self.output_dir = output_dir
        self.auto_remove_bg = auto_remove_bg
        self.project_path = project_path
        self._mapper = None

        os.makedirs(output_dir, exist_ok=True)

        # 배경제거 임시 디렉토리
        self._bg_removed_cache_dir = os.path.join(output_dir, ".bg_removed_cache")
        os.makedirs(self._bg_removed_cache_dir, exist_ok=True)

    def _get_mapper(self) -> Optional['SceneCharacterMapper']:
        """씬-캐릭터 매퍼 인스턴스 반환"""
        if not MAPPER_AVAILABLE or not self.project_path:
            return None

        if self._mapper is None:
            self._mapper = SceneCharacterMapper(self.project_path)

        return self._mapper

    def _prepare_character_image(self, image_path: str, force_remove_bg: bool = False) -> str:
        """
        캐릭터 이미지 준비 (필요시 배경 제거)

        Args:
            image_path: 원본 이미지 경로
            force_remove_bg: 강제 배경 제거

        Returns:
            사용할 이미지 경로 (원본 또는 배경 제거된 버전)
        """
        if not os.path.exists(image_path):
            return image_path

        # 자동 배경 제거 비활성화면 원본 반환
        if not self.auto_remove_bg and not force_remove_bg:
            return image_path

        # 배경 제거 모듈 없으면 원본 반환
        if not BG_REMOVER_AVAILABLE:
            return image_path

        # 이미 투명 배경이면 원본 사용
        if has_transparency(image_path):
            print(f"[Compositor] 이미 투명 배경: {os.path.basename(image_path)}")
            return image_path

        # 캐시 경로 계산
        import hashlib
        filename = os.path.basename(image_path)
        name, ext = os.path.splitext(filename)
        file_hash = hashlib.md5(image_path.encode()).hexdigest()[:8]
        cached_path = os.path.join(
            self._bg_removed_cache_dir,
            f"{name}_{file_hash}_nobg.png"
        )

        # 캐시에 있으면 사용
        if os.path.exists(cached_path):
            print(f"[Compositor] 캐시된 배경제거 이미지 사용: {os.path.basename(cached_path)}")
            return cached_path

        # 배경 제거 실행
        print(f"[Compositor] 배경 제거 중: {os.path.basename(image_path)}")

        try:
            result_path = remove_background_simple(image_path, cached_path)
            if result_path and os.path.exists(result_path):
                print(f"[Compositor] 배경 제거 완료: {os.path.basename(result_path)}")
                return result_path
        except Exception as e:
            print(f"[Compositor] 배경 제거 실패: {e}")

        return image_path

    def composite_character_to_video(
        self,
        video_path: str,
        character_image_path: str,
        scene_id: int,
        position: str = "오른쪽",
        scale: float = 0.7,
        vertical_align: str = "bottom"  # top, center, bottom
    ) -> Optional[str]:
        """
        동영상 전체에 캐릭터 이미지 오버레이

        Args:
            video_path: 인포그래픽 MP4 경로
            character_image_path: 캐릭터 PNG 경로 (투명 배경 권장)
            scene_id: 씬 번호
            position: 수평 위치 (왼쪽, 중앙-왼쪽, 중앙, 중앙-오른쪽, 오른쪽)
            scale: 캐릭터 크기 (0.3~1.2, 화면 높이 대비 비율)
            vertical_align: 수직 정렬 (top, center, bottom)

        Returns:
            합성된 MP4 경로 또는 None
        """
        if not os.path.exists(video_path):
            print(f"❌ 동영상 파일 없음: {video_path}")
            return None

        if not os.path.exists(character_image_path):
            print(f"❌ 캐릭터 이미지 없음: {character_image_path}")
            return None

        # 배경 제거 처리
        prepared_image = self._prepare_character_image(character_image_path)

        try:
            output_path = os.path.join(
                self.output_dir,
                f"composite_scene_{scene_id:03d}.mp4"
            )

            # 동영상 해상도 확인
            video_width, video_height = self._get_video_dimensions(video_path)

            # 캐릭터 높이 계산 (화면 높이의 scale 비율)
            char_height = int(video_height * scale)

            # 수평 위치 계산
            x_ratio = self.POSITION_MAP.get(position)
            if x_ratio is None:
                x_ratio = self.POSITION_MAP_EN.get(position, 0.95)

            # 수직 위치 계산
            if vertical_align == "bottom":
                y_expr = "H-overlay_h-50"  # 하단 50px 여백
            elif vertical_align == "center":
                y_expr = "(H-overlay_h)/2"
            else:  # top
                y_expr = "50"

            # 수평 위치: 캐릭터 중앙이 x_ratio 위치에 오도록
            x_expr = f"W*{x_ratio}-overlay_w/2"

            # FFmpeg filter_complex
            # [1:v] = 캐릭터 이미지, scale해서 [char] 스트림 생성
            # [0:v][char] overlay로 합성
            filter_complex = (
                f"[1:v]scale=-1:{char_height}[char];"
                f"[0:v][char]overlay=x='{x_expr}':y='{y_expr}'"
            )

            # 🔴 v3.12: 색감 보존 설정 추가 (Problem 59)
            cmd = [
                "ffmpeg", "-y",
                "-i", video_path,
                "-i", prepared_image,  # 배경 제거된 이미지 사용
                "-filter_complex", filter_complex,
                "-c:v", "libx264",
                "-preset", "medium",
                "-crf", "23",
                "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                # 색감 보존 핵심 설정
                "-color_range", "pc",              # Full Range (0-255)
                "-colorspace", "bt709",
                "-color_primaries", "bt709",
                "-color_trc", "iec61966-2-1",      # sRGB 감마
                output_path
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                print(f"✅ 씬 {scene_id} 캐릭터 합성 완료: {output_path}")

                # 합성 결과 썸네일 생성
                thumb_path = self._create_composite_thumbnail(output_path, scene_id)

                return output_path
            else:
                print(f"❌ FFmpeg 오류: {result.stderr[:500]}")
                return None

        except FileNotFoundError:
            print("❌ FFmpeg이 설치되지 않았습니다")
            return None
        except Exception as e:
            print(f"❌ 합성 오류: {e}")
            return None

    def _get_video_dimensions(self, video_path: str) -> Tuple[int, int]:
        """FFprobe로 동영상 해상도 확인"""
        try:
            cmd = [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "csv=p=0",
                video_path
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)
            width, height = result.stdout.strip().split(",")
            return int(width), int(height)

        except Exception:
            return 1280, 720  # 기본값

    def _create_composite_thumbnail(self, video_path: str, scene_id: int) -> str:
        """합성된 동영상의 첫 프레임을 썸네일로 추출"""
        thumb_path = os.path.join(
            self.output_dir,
            f"composite_scene_{scene_id:03d}_thumb.png"
        )

        try:
            cmd = [
                "ffmpeg", "-y",
                "-i", video_path,
                "-vframes", "1",
                "-vf", "scale=320:180",
                thumb_path
            ]

            subprocess.run(cmd, capture_output=True)
            return thumb_path

        except Exception:
            return ""

    def batch_composite(
        self,
        infographic_data: InfographicData,
        character_image_path: str,
        position: str = "오른쪽",
        scale: float = 0.7,
        scene_ids: List[int] = None,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> Dict[int, str]:
        """
        여러 씬에 캐릭터 일괄 합성

        Args:
            infographic_data: 인포그래픽 데이터
            character_image_path: 캐릭터 이미지 경로
            position: 캐릭터 위치
            scale: 캐릭터 크기
            scene_ids: 합성할 씬 ID 목록 (None이면 동영상 있는 전체)
            progress_callback: func(current, total, message)

        Returns:
            {scene_id: composite_video_path, ...}
        """
        results = {}

        # 동영상이 있는 씬만 필터링
        target_scenes = infographic_data.get_scenes_with_videos()

        if scene_ids:
            target_scenes = [s for s in target_scenes if s.scene_id in scene_ids]

        if not target_scenes:
            print("[Compositor] 합성할 동영상이 없습니다")
            return results

        total = len(target_scenes)

        for i, scene in enumerate(target_scenes):
            if progress_callback:
                progress_callback(i + 1, total, f"씬 {scene.scene_id} 합성 중...")

            composite_path = self.composite_character_to_video(
                scene.video_path,
                character_image_path,
                scene.scene_id,
                position,
                scale
            )

            if composite_path:
                scene.composite_video_path = composite_path
                scene.composite_thumbnail_path = self._create_composite_thumbnail(
                    composite_path, scene.scene_id
                )
                scene.is_composite_ready = True
                results[scene.scene_id] = composite_path

        return results

    def batch_composite_with_mapping(
        self,
        scenes_data: List[Dict[str, Any]],
        video_paths: Dict[int, str],
        default_character_id: str = None,
        position: str = "오른쪽",
        scale: float = 0.7,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> Dict[int, Dict[str, Any]]:
        """
        자동 매핑을 활용한 배치 합성

        씬 분석 데이터에서 캐릭터를 자동 감지하여 각 씬에 맞는 캐릭터로 합성

        Args:
            scenes_data: 씬 데이터 목록 (scene_num, description, narration 등)
            video_paths: {scene_num: video_path} 맵
            default_character_id: 매핑 없을 때 기본 캐릭터
            position: 캐릭터 위치
            scale: 캐릭터 크기
            progress_callback: func(current, total, message)

        Returns:
            {scene_num: {video_path, character_id, character_name, confidence}, ...}
        """
        results = {}

        mapper = self._get_mapper()
        if not mapper:
            print("[Compositor] 자동 매핑을 사용할 수 없습니다 (프로젝트 경로 미설정)")
            return results

        # 자동 매핑 생성
        print("[Compositor] 씬-캐릭터 자동 매핑 중...")
        mappings = mapper.generate_mappings(scenes_data, default_character_id)

        if not mappings:
            print("[Compositor] 매핑된 씬이 없습니다")
            return results

        # 매핑 결과를 씬별로 정리
        mapping_dict = {m['scene_num']: m for m in mappings}

        total = len(video_paths)

        for i, (scene_num, video_path) in enumerate(video_paths.items()):
            if progress_callback:
                progress_callback(i + 1, total, f"씬 {scene_num} 합성 중...")

            mapping = mapping_dict.get(scene_num)

            if not mapping or not mapping.get('image_path'):
                print(f"[Compositor] 씬 {scene_num}: 캐릭터 매핑 없음, 건너뜀")
                continue

            character_image = mapping['image_path']

            if not os.path.exists(character_image):
                print(f"[Compositor] 씬 {scene_num}: 캐릭터 이미지 없음 ({character_image})")
                continue

            # 합성 실행
            composite_path = self.composite_character_to_video(
                video_path,
                character_image,
                scene_num,
                position,
                scale
            )

            if composite_path:
                results[scene_num] = {
                    'video_path': composite_path,
                    'character_id': mapping['character_id'],
                    'character_name': mapping['character_name'],
                    'confidence': mapping['confidence'],
                    'match_type': mapping.get('match_type', 'unknown')
                }
                print(f"[Compositor] 씬 {scene_num} 합성 완료: {mapping['character_name']} (신뢰도: {mapping['confidence']:.2f})")

        # 매핑 결과 저장
        mapper.save_mappings(mappings)

        return results


# 동기 래퍼 함수들
def composite_character_sync(
    video_path: str,
    character_image_path: str,
    scene_id: int,
    position: str = "오른쪽",
    scale: float = 0.7,
    output_dir: str = "outputs/infographic_composites",
    auto_remove_bg: bool = True
) -> Optional[str]:
    """단일 합성 (동기)"""
    compositor = InfographicCharacterCompositor(
        output_dir=output_dir,
        auto_remove_bg=auto_remove_bg
    )
    return compositor.composite_character_to_video(
        video_path, character_image_path, scene_id, position, scale
    )


def batch_composite_sync(
    infographic_data: InfographicData,
    character_image_path: str,
    position: str = "오른쪽",
    scale: float = 0.7,
    scene_ids: List[int] = None,
    output_dir: str = "outputs/infographic_composites",
    auto_remove_bg: bool = True,
    progress_callback: Optional[Callable[[int, int, str], None]] = None
) -> Dict[int, str]:
    """일괄 합성 (동기)"""
    compositor = InfographicCharacterCompositor(
        output_dir=output_dir,
        auto_remove_bg=auto_remove_bg
    )
    return compositor.batch_composite(
        infographic_data, character_image_path, position, scale, scene_ids, progress_callback
    )


def batch_composite_with_auto_mapping(
    project_path: str,
    scenes_data: List[Dict[str, Any]],
    video_paths: Dict[int, str],
    default_character_id: str = None,
    position: str = "오른쪽",
    scale: float = 0.7,
    output_dir: str = "outputs/infographic_composites",
    auto_remove_bg: bool = True,
    progress_callback: Optional[Callable[[int, int, str], None]] = None
) -> Dict[int, Dict[str, Any]]:
    """
    자동 매핑을 활용한 배치 합성 (편의 함수)

    Args:
        project_path: 프로젝트 경로 (캐릭터 폴더 포함)
        scenes_data: 씬 데이터 목록
        video_paths: {scene_num: video_path} 맵
        default_character_id: 기본 캐릭터 ID
        position: 캐릭터 위치
        scale: 캐릭터 크기
        output_dir: 출력 디렉토리
        auto_remove_bg: 배경 자동 제거
        progress_callback: 진행 콜백

    Returns:
        {scene_num: {video_path, character_id, ...}, ...}
    """
    compositor = InfographicCharacterCompositor(
        output_dir=output_dir,
        auto_remove_bg=auto_remove_bg,
        project_path=project_path
    )
    return compositor.batch_composite_with_mapping(
        scenes_data, video_paths, default_character_id, position, scale, progress_callback
    )


def get_compositor(
    output_dir: str = None,
    auto_remove_bg: bool = True,
    project_path: str = None
) -> InfographicCharacterCompositor:
    """합성기 인스턴스 생성"""
    return InfographicCharacterCompositor(
        output_dir=output_dir or "outputs/infographic_composites",
        auto_remove_bg=auto_remove_bg,
        project_path=project_path
    )


# 유틸리티 함수들
def is_bg_removal_available() -> Tuple[bool, str]:
    """배경 제거 기능 사용 가능 여부"""
    if not BG_REMOVER_AVAILABLE:
        return False, "배경 제거 모듈을 불러올 수 없습니다"

    try:
        available, msg = is_rembg_available()
        return available, msg
    except Exception as e:
        return False, f"확인 중 오류: {e}"


def is_mapper_available() -> bool:
    """씬-캐릭터 매퍼 사용 가능 여부"""
    return MAPPER_AVAILABLE
