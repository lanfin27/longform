# -*- coding: utf-8 -*-
"""
프로젝트 경로 관리 통합 모듈

모든 페이지에서 동일한 경로를 사용하도록 중앙 집중화

변경사항 (v1.0):
- ProjectPaths 클래스
- 캐릭터 데이터 로드/저장
- 동영상 목록 관리
- 씬별 시각 자료 상태 조회
"""

import os
import json
import uuid
from pathlib import Path
from typing import Optional, Dict, List, Any
import logging

logger = logging.getLogger(__name__)


class ProjectPaths:
    """프로젝트 경로 관리자"""

    def __init__(self, project_path: str):
        """
        Args:
            project_path: 프로젝트 루트 경로
        """
        self.root = Path(project_path)

        # 주요 디렉토리
        self.data_dir = self.root / "data"
        self.images_dir = self.root / "images"
        self.characters_dir = self.root / "characters"
        self.infographics_dir = self.root / "infographics"

        # 세부 디렉토리
        self.scenes_dir = self.images_dir / "scenes"
        self.thumbnails_dir = self.infographics_dir / "thumbnails"
        self.videos_dir = self.infographics_dir / "videos"
        self.composed_dir = self.infographics_dir / "composed"
        self.composites_dir = self.infographics_dir / "composites"  # 캐릭터 합성 결과

        # 데이터 파일
        self.characters_json = self.data_dir / "characters.json"
        self.visual_settings_json = self.data_dir / "visual_settings.json"
        self.project_json = self.data_dir / "project.json"

        # 디렉토리 생성
        self._ensure_directories()

    def _ensure_directories(self):
        """필요한 디렉토리 생성"""
        dirs = [
            self.data_dir,
            self.images_dir,
            self.characters_dir,
            self.infographics_dir,
            self.scenes_dir,
            self.thumbnails_dir,
            self.videos_dir,
            self.composed_dir,
            self.composites_dir,
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)

    # ========================================
    # 동영상 관련
    # ========================================

    def get_video_path(self, scene_num: int) -> Path:
        """씬 번호로 동영상 경로 반환"""
        return self.videos_dir / f"infographic_scene_{scene_num:03d}.mp4"

    def get_composed_video_path(self, scene_num: int) -> Path:
        """씬 번호로 합성된 동영상 경로 반환"""
        return self.composites_dir / f"composite_scene_{scene_num:03d}.mp4"

    def list_videos(self) -> List[Dict]:
        """생성된 동영상 목록 반환"""
        videos = []

        if self.videos_dir.exists():
            for f in sorted(self.videos_dir.glob("infographic_scene_*.mp4")):
                try:
                    # infographic_scene_001.mp4 → 1
                    scene_num = int(f.stem.split('_')[-1])
                    videos.append({
                        'scene_num': scene_num,
                        'path': str(f),
                        'filename': f.name,
                        'size_mb': f.stat().st_size / (1024 * 1024),
                        'exists': True
                    })
                except (ValueError, IndexError):
                    pass

        return videos

    def list_composed_videos(self) -> List[Dict]:
        """합성된 동영상 목록 반환"""
        videos = []

        if self.composites_dir.exists():
            for f in sorted(self.composites_dir.glob("composite_scene_*.mp4")):
                try:
                    scene_num = int(f.stem.split('_')[-1])
                    videos.append({
                        'scene_num': scene_num,
                        'path': str(f),
                        'filename': f.name,
                        'size_mb': f.stat().st_size / (1024 * 1024),
                        'exists': True
                    })
                except (ValueError, IndexError):
                    pass

        return videos

    def get_video_status(self, scene_num: int) -> Dict:
        """씬별 동영상 상태 반환"""
        video_path = self.get_video_path(scene_num)
        composed_path = self.get_composed_video_path(scene_num)

        return {
            'scene_num': scene_num,
            'video_exists': video_path.exists(),
            'video_path': str(video_path) if video_path.exists() else None,
            'video_size_mb': video_path.stat().st_size / (1024*1024) if video_path.exists() else 0,
            'composed_exists': composed_path.exists(),
            'composed_path': str(composed_path) if composed_path.exists() else None,
        }

    # ========================================
    # 캐릭터 관련
    # ========================================

    def get_character_image_path(self, char_id: str) -> Path:
        """캐릭터 ID로 이미지 경로 반환"""
        return self.characters_dir / f"{char_id}.png"

    def load_characters(self) -> List[Dict]:
        """
        캐릭터 데이터 로드

        1. JSON 파일에서 로드
        2. characters 폴더에서 PNG 파일 직접 스캔 (폴백)
        """
        characters = []

        # 1. JSON 파일에서 로드
        if self.characters_json.exists():
            try:
                with open(self.characters_json, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                for char in data.get('characters', []):
                    # 이미지 경로 정규화
                    img_path = char.get('image_path', '')

                    # 상대 경로 → 절대 경로
                    if img_path and not os.path.isabs(img_path):
                        full_path = self.root / img_path
                    else:
                        full_path = Path(img_path) if img_path else Path()

                    char['full_image_path'] = str(full_path)
                    char['image_exists'] = full_path.exists()

                    if char['image_exists']:
                        characters.append(char)

            except Exception as e:
                logger.warning(f"캐릭터 JSON 로드 오류: {e}")

        # 2. characters 폴더에서 직접 스캔 (JSON에 없는 파일)
        if self.characters_dir.exists():
            existing_ids = {c.get('id') for c in characters}

            for img_file in self.characters_dir.glob("*.png"):
                char_id = img_file.stem

                # 이미 JSON에서 로드된 캐릭터는 스킵
                if char_id in existing_ids:
                    continue

                characters.append({
                    'id': char_id,
                    'name': char_id.replace('_', ' ').title(),
                    'name_en': char_id,
                    'image_path': f"characters/{img_file.name}",
                    'full_image_path': str(img_file),
                    'image_exists': True,
                    'position': 'bottom-right',
                    'scale': 0.3,
                })

        return characters

    def save_characters(self, characters: List[Dict]) -> bool:
        """캐릭터 데이터 저장"""
        try:
            # 저장 전 full_image_path 제거 (상대 경로만 저장)
            save_data = []
            for char in characters:
                char_copy = char.copy()
                char_copy.pop('full_image_path', None)
                char_copy.pop('image_exists', None)
                save_data.append(char_copy)

            self.data_dir.mkdir(parents=True, exist_ok=True)

            with open(self.characters_json, 'w', encoding='utf-8') as f:
                json.dump({'characters': save_data}, f, ensure_ascii=False, indent=2)

            return True
        except Exception as e:
            logger.error(f"캐릭터 저장 오류: {e}")
            return False

    def add_character(
        self,
        name: str,
        name_en: str,
        image_data: bytes,
        position: str = 'bottom-right',
        scale: float = 0.3
    ) -> Optional[Dict]:
        """새 캐릭터 추가"""
        try:
            from PIL import Image
            import io

            # ID 생성
            char_id = f"char_{uuid.uuid4().hex[:8]}"

            # 이미지 저장
            img_path = self.characters_dir / f"{char_id}.png"
            img = Image.open(io.BytesIO(image_data))

            # RGBA로 변환 (투명 배경 지원)
            if img.mode != 'RGBA':
                img = img.convert('RGBA')

            img.save(str(img_path), 'PNG')

            # 캐릭터 데이터
            new_char = {
                'id': char_id,
                'name': name,
                'name_en': name_en,
                'image_path': f"characters/{char_id}.png",
                'position': position,
                'scale': scale,
                'scenes': []
            }

            # 기존 데이터 로드 및 추가
            characters = self.load_characters()

            # JSON용 데이터 (full_image_path 제외)
            for c in characters:
                c.pop('full_image_path', None)
                c.pop('image_exists', None)

            characters.append(new_char)
            self.save_characters(characters)

            # 반환용 데이터
            new_char['full_image_path'] = str(img_path)
            new_char['image_exists'] = True

            logger.info(f"캐릭터 추가 완료: {name} ({char_id})")
            return new_char

        except Exception as e:
            logger.error(f"캐릭터 추가 오류: {e}")
            return None

    def delete_character(self, char_id: str) -> bool:
        """캐릭터 삭제"""
        try:
            # 이미지 파일 삭제
            img_path = self.get_character_image_path(char_id)
            if img_path.exists():
                img_path.unlink()

            # JSON에서 제거
            characters = self.load_characters()
            characters = [c for c in characters if c.get('id') != char_id]

            # JSON용 데이터 정리
            for c in characters:
                c.pop('full_image_path', None)
                c.pop('image_exists', None)

            self.save_characters(characters)

            logger.info(f"캐릭터 삭제 완료: {char_id}")
            return True

        except Exception as e:
            logger.error(f"캐릭터 삭제 오류: {e}")
            return False

    def get_character_by_id(self, char_id: str) -> Optional[Dict]:
        """ID로 캐릭터 찾기"""
        characters = self.load_characters()
        return next((c for c in characters if c.get('id') == char_id), None)

    # ========================================
    # 썸네일/이미지 관련
    # ========================================

    def get_thumbnail_path(self, scene_num: int) -> Path:
        """씬 번호로 인포그래픽 썸네일 경로 반환"""
        return self.thumbnails_dir / f"scene_{scene_num:03d}.png"

    def get_ai_image_path(self, scene_num: int) -> Path:
        """씬 번호로 AI 이미지 경로 반환"""
        return self.scenes_dir / f"scene_{scene_num:03d}.png"

    def list_thumbnails(self) -> List[Dict]:
        """생성된 썸네일 목록 반환"""
        thumbnails = []

        if self.thumbnails_dir.exists():
            for f in sorted(self.thumbnails_dir.glob("scene_*.png")):
                try:
                    scene_num = int(f.stem.split('_')[-1])
                    thumbnails.append({
                        'scene_num': scene_num,
                        'path': str(f),
                        'filename': f.name,
                        'exists': True
                    })
                except (ValueError, IndexError):
                    pass

        return thumbnails

    def list_ai_images(self) -> List[Dict]:
        """생성된 AI 이미지 목록 반환"""
        images = []

        if self.scenes_dir.exists():
            for f in sorted(self.scenes_dir.glob("scene_*.png")):
                try:
                    scene_num = int(f.stem.split('_')[-1])
                    images.append({
                        'scene_num': scene_num,
                        'path': str(f),
                        'filename': f.name,
                        'exists': True
                    })
                except (ValueError, IndexError):
                    pass

        return images

    def get_scene_visual_status(self, scene_num: int) -> Dict:
        """씬별 시각 자료 상태 종합"""
        ai_img = self.get_ai_image_path(scene_num)
        thumb = self.get_thumbnail_path(scene_num)
        video = self.get_video_path(scene_num)
        composed = self.get_composed_video_path(scene_num)

        return {
            'scene_num': scene_num,
            'ai_image': {
                'exists': ai_img.exists(),
                'path': str(ai_img) if ai_img.exists() else None
            },
            'infographic_thumb': {
                'exists': thumb.exists(),
                'path': str(thumb) if thumb.exists() else None
            },
            'video': {
                'exists': video.exists(),
                'path': str(video) if video.exists() else None,
                'size_mb': video.stat().st_size / (1024*1024) if video.exists() else 0
            },
            'composed_video': {
                'exists': composed.exists(),
                'path': str(composed) if composed.exists() else None
            }
        }

    # ========================================
    # 유틸리티
    # ========================================

    def get_all_scene_nums(self) -> List[int]:
        """
        모든 씬 번호 반환 (동영상, 썸네일, AI 이미지 통합)
        """
        scene_nums = set()

        # 동영상
        for v in self.list_videos():
            scene_nums.add(v['scene_num'])

        # 썸네일
        for t in self.list_thumbnails():
            scene_nums.add(t['scene_num'])

        # AI 이미지
        for i in self.list_ai_images():
            scene_nums.add(i['scene_num'])

        return sorted(scene_nums)

    def get_stats(self) -> Dict:
        """프로젝트 통계"""
        videos = self.list_videos()
        composed = self.list_composed_videos()
        thumbnails = self.list_thumbnails()
        ai_images = self.list_ai_images()
        characters = self.load_characters()

        return {
            'videos': len(videos),
            'composed_videos': len(composed),
            'thumbnails': len(thumbnails),
            'ai_images': len(ai_images),
            'characters': len(characters),
            'total_video_size_mb': sum(v['size_mb'] for v in videos),
        }


def get_project_paths(project_path: str) -> ProjectPaths:
    """ProjectPaths 인스턴스 반환"""
    return ProjectPaths(project_path)


# ============================================================
# 테스트
# ============================================================

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        test_path = sys.argv[1]
    else:
        test_path = os.getcwd()

    print(f"프로젝트 경로: {test_path}")
    print("=" * 50)

    paths = get_project_paths(test_path)

    print(f"\n디렉토리 구조:")
    print(f"  root: {paths.root}")
    print(f"  data: {paths.data_dir}")
    print(f"  characters: {paths.characters_dir}")
    print(f"  videos: {paths.videos_dir}")
    print(f"  thumbnails: {paths.thumbnails_dir}")

    print(f"\n통계:")
    stats = paths.get_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")

    print(f"\n캐릭터:")
    for char in paths.load_characters():
        print(f"  - {char.get('name')} ({char.get('id')}): {char.get('image_exists')}")

    print(f"\n동영상:")
    for video in paths.list_videos()[:5]:
        print(f"  - 씬 {video['scene_num']}: {video['size_mb']:.1f}MB")
