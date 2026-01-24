"""
씬별 캐릭터 이미지 갤러리 유틸리티 v1.0

씬 번호별로 캐릭터 이미지를 그룹화하고,
재생성 등의 작업을 지원합니다.

작성: 2026-01
"""

import os
import json
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class CharacterImage:
    """캐릭터 이미지 정보"""
    character_name: str
    pose: str
    image_path: str
    scene_numbers: List[int] = field(default_factory=list)
    created_at: str = ""
    file_size: int = 0
    dimensions: Tuple[int, int] = (0, 0)
    needs_regeneration: bool = False
    regeneration_reason: str = ""


@dataclass
class SceneCharacters:
    """씬별 캐릭터 정보"""
    scene_number: int
    characters: List[CharacterImage] = field(default_factory=list)
    has_background: bool = False
    background_path: str = ""
    is_complete: bool = False  # 배경 + 캐릭터 모두 있음


class CharacterGalleryManager:
    """씬별 캐릭터 갤러리 관리자"""

    def __init__(self, project_path: str):
        """
        초기화

        Args:
            project_path: 프로젝트 경로
        """
        self.project_path = Path(project_path)
        self.characters_dir = self.project_path / 'images' / 'characters'
        self.backgrounds_dir = self.project_path / 'images' / 'backgrounds'
        self.scenes_json = self.project_path / 'analysis' / 'scenes.json'
        self.characters_json = self.project_path / 'characters' / 'characters.json'
        self.analysis_chars_json = self.project_path / 'analysis' / 'characters.json'
        # v1.1: scene_characters.json 추가 (씬별 캐릭터 매핑)
        self.scene_characters_json = self.project_path / 'scene_characters.json'

        # 캐시
        self._scene_data = None
        self._character_data = None
        self._scene_characters_data = None

    def get_scenes_with_characters(self) -> List[SceneCharacters]:
        """
        캐릭터가 있는 모든 씬 정보 가져오기 (씬 번호순 정렬)

        v1.1: 다양한 데이터 소스 지원
        - scene_characters.json (씬별 캐릭터 매핑)
        - scenes.json의 characters 필드
        - characters.json의 appearance_scenes
        - character_prompt 필드

        Returns:
            SceneCharacters 목록
        """
        # 1. 씬 분석 데이터에서 캐릭터 정보 로드
        scenes_data = self._load_scenes_data()

        # 2. 캐릭터 데이터 로드 (appearance_scenes 포함)
        characters_data = self._load_characters_data()

        # 3. scene_characters.json 로드 (v1.1 추가)
        scene_characters_data = self._load_scene_characters_data()

        # 4. 캐릭터 이미지 파일 스캔
        character_images = self._scan_character_images()

        # 5. 씬별로 그룹화
        scene_characters_map: Dict[int, List[CharacterImage]] = {}

        # ═══════════════════════════════════════════════════════════════
        # v1.1: scene_characters.json 기반 매핑 (최우선)
        # ═══════════════════════════════════════════════════════════════
        for scene_num_str, scene_data in scene_characters_data.items():
            try:
                scene_num = int(scene_num_str)
            except ValueError:
                continue

            if scene_num not in scene_characters_map:
                scene_characters_map[scene_num] = []

            # scene_data.characters 딕셔너리 순회
            chars_dict = scene_data.get('characters', {})
            for char_name, char_info in chars_dict.items():
                if not char_name:
                    continue

                # 이미지 경로 추출
                poses = char_info.get('poses', {})
                image_path = ""
                pose = "standing"

                # 첫 번째 포즈의 이미지 사용
                for pose_name, pose_data in poses.items():
                    if pose_data.get('image_path'):
                        image_path = pose_data['image_path']
                        pose = pose_name
                        break

                # 이미지 없으면 스캔된 이미지에서 찾기
                if not image_path or not os.path.exists(image_path):
                    found_img = self._find_character_image(char_name, character_images)
                    if found_img:
                        image_path = found_img.image_path
                        pose = found_img.pose

                # 중복 체크
                existing_names = [c.character_name for c in scene_characters_map[scene_num]]
                if char_name not in existing_names:
                    char_image = self._create_character_image(char_name, pose, image_path)
                    char_image.scene_numbers = [scene_num]
                    scene_characters_map[scene_num].append(char_image)

        print(f"[CharacterGallery] scene_characters.json에서 {len(scene_characters_map)}개 씬 로드")

        # ═══════════════════════════════════════════════════════════════
        # v1.1: scenes.json의 characters 필드 기반 매핑
        # ═══════════════════════════════════════════════════════════════
        for scene in scenes_data:
            scene_num = scene.get('scene_id') or scene.get('scene_number', 0)
            if not scene_num:
                continue

            # characters 필드 (리스트)
            scene_chars = self._extract_characters_from_scene(scene)

            for char_name in scene_chars:
                if scene_num not in scene_characters_map:
                    scene_characters_map[scene_num] = []

                # 중복 체크
                existing_names = [c.character_name for c in scene_characters_map[scene_num]]
                if char_name not in existing_names:
                    # 이미지 찾기
                    char_image = self._find_character_image(char_name, character_images)
                    if char_image:
                        new_char_image = CharacterImage(
                            character_name=char_image.character_name,
                            pose=char_image.pose,
                            image_path=char_image.image_path,
                            scene_numbers=[scene_num],
                            created_at=char_image.created_at,
                            file_size=char_image.file_size,
                            dimensions=char_image.dimensions,
                            needs_regeneration=char_image.needs_regeneration,
                            regeneration_reason=char_image.regeneration_reason
                        )
                    else:
                        # 이미지 없는 캐릭터도 표시
                        new_char_image = CharacterImage(
                            character_name=char_name,
                            pose='standing',
                            image_path='',
                            scene_numbers=[scene_num],
                            needs_regeneration=True,
                            regeneration_reason='이미지 없음'
                        )
                    scene_characters_map[scene_num].append(new_char_image)

        # ═══════════════════════════════════════════════════════════════
        # appearance_scenes 기반 매핑 (기존 로직 유지)
        # ═══════════════════════════════════════════════════════════════
        for char_data in characters_data:
            char_name = char_data.get('name', '')
            appearance_scenes = char_data.get('appearance_scenes', [])

            if not char_name or not appearance_scenes:
                continue

            # 이 캐릭터의 이미지 찾기
            char_image = self._find_character_image(char_name, character_images)

            if char_image:
                for scene_num in appearance_scenes:
                    if isinstance(scene_num, str):
                        try:
                            scene_num = int(scene_num)
                        except ValueError:
                            continue

                    if scene_num not in scene_characters_map:
                        scene_characters_map[scene_num] = []

                    # 중복 체크 (이름 기준)
                    existing_names = [c.character_name for c in scene_characters_map[scene_num]]
                    if char_name not in existing_names:
                        # 새 CharacterImage 생성 (scene_numbers 업데이트)
                        new_char_image = CharacterImage(
                            character_name=char_image.character_name,
                            pose=char_image.pose,
                            image_path=char_image.image_path,
                            scene_numbers=[scene_num],
                            created_at=char_image.created_at,
                            file_size=char_image.file_size,
                            dimensions=char_image.dimensions,
                            needs_regeneration=char_image.needs_regeneration,
                            regeneration_reason=char_image.regeneration_reason
                        )
                        scene_characters_map[scene_num].append(new_char_image)

        # ═══════════════════════════════════════════════════════════════
        # 캐릭터 프롬프트 기반 씬 추가 (이미지 없어도)
        # ═══════════════════════════════════════════════════════════════
        for scene in scenes_data:
            scene_num = scene.get('scene_id') or scene.get('scene_number', 0)
            char_prompt = scene.get('character_prompt_en', '') or scene.get('character_prompt', '')

            if not scene_num:
                continue

            # 캐릭터 프롬프트가 있지만 아직 매핑되지 않은 씬
            if char_prompt and char_prompt.lower() not in ['n/a', 'none', '없음', '', 'no character']:
                if scene_num not in scene_characters_map:
                    scene_characters_map[scene_num] = []

        # 6. SceneCharacters 객체 생성
        result = []

        all_scene_nums = sorted(scene_characters_map.keys())

        for scene_num in all_scene_nums:
            characters = scene_characters_map.get(scene_num, [])

            # 배경 이미지 확인
            bg_path = self._find_background_image(scene_num)

            scene_chars = SceneCharacters(
                scene_number=scene_num,
                characters=characters,
                has_background=bool(bg_path),
                background_path=bg_path or "",
                is_complete=bool(bg_path) and len(characters) > 0
            )

            result.append(scene_chars)

        # v1.2: 로그 최초 1회만 출력
        if not hasattr(self, '_logged_scene_count'):
            print(f"[CharacterGallery] 총 {len(result)}개 씬, {sum(len(s.characters) for s in result)}개 캐릭터 이미지")
            self._logged_scene_count = True
        return result

    def _extract_characters_from_scene(self, scene: Dict) -> List[str]:
        """
        씬 데이터에서 캐릭터 이름 추출 (다중 필드 지원 v1.1)

        지원 필드: characters, character_names, 등장_캐릭터, character_list 등
        """
        # 시도할 필드명들 (우선순위 순)
        field_names = [
            'characters',
            'character_names',
            '등장_캐릭터',
            'character_list',
            'character',
            '캐릭터',
            '등장인물',
            'cast'
        ]

        for field in field_names:
            if field not in scene:
                continue

            value = scene[field]

            if value is None:
                continue

            # 리스트인 경우
            if isinstance(value, list):
                if not value:
                    continue

                characters = []
                for item in value:
                    if isinstance(item, str):
                        char_name = item.strip()
                    elif isinstance(item, dict):
                        char_name = item.get('name', '') or item.get('이름', '')
                    else:
                        continue

                    if self._is_valid_character_name(char_name):
                        characters.append(char_name)

                if characters:
                    return characters

            # 문자열인 경우
            elif isinstance(value, str):
                value = value.strip()

                if not self._is_valid_character_name(value):
                    continue

                # 쉼표로 구분된 여러 캐릭터
                if ',' in value:
                    characters = [c.strip() for c in value.split(',')]
                    characters = [c for c in characters if self._is_valid_character_name(c)]
                    if characters:
                        return characters

                return [value]

        return []

    def _is_valid_character_name(self, name: str) -> bool:
        """유효한 캐릭터 이름인지 확인"""
        if not name or not isinstance(name, str):
            return False

        name_lower = name.lower().strip()

        # 무효한 값들
        invalid_values = [
            '', 'n/a', 'na', 'none', 'null', '없음', '없다',
            '-', '--', '해당없음', '해당 없음', 'no character',
            'no characters', 'background only', '배경만'
        ]

        if name_lower in invalid_values:
            return False

        if len(name.strip()) < 1:
            return False

        return True

    def _load_scene_characters_data(self) -> Dict:
        """scene_characters.json 로드 (v1.1 추가)"""
        if self._scene_characters_data is not None:
            return self._scene_characters_data

        if not self.scene_characters_json.exists():
            self._scene_characters_data = {}
            return self._scene_characters_data

        try:
            with open(self.scene_characters_json, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self._scene_characters_data = data if isinstance(data, dict) else {}
                print(f"[CharacterGallery] scene_characters.json 로드: {len(self._scene_characters_data)}개 씬")
                return self._scene_characters_data
        except Exception as e:
            print(f"[CharacterGallery] scene_characters.json 로드 오류: {e}")
            self._scene_characters_data = {}
            return self._scene_characters_data

    def get_scene_characters(self, scene_num: int) -> SceneCharacters:
        """
        특정 씬의 캐릭터 정보 가져오기

        Args:
            scene_num: 씬 번호

        Returns:
            SceneCharacters 객체
        """
        all_scenes = self.get_scenes_with_characters()

        for scene in all_scenes:
            if scene.scene_number == scene_num:
                return scene

        # 없으면 빈 객체 반환
        return SceneCharacters(
            scene_number=scene_num,
            characters=[],
            has_background=False,
            background_path="",
            is_complete=False
        )

    def _load_scenes_data(self) -> List[Dict]:
        """씬 분석 데이터 로드"""
        if not self.scenes_json.exists():
            return []

        try:
            with open(self.scenes_json, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 리스트 형태로 반환
            if isinstance(data, list):
                return data
            elif isinstance(data, dict):
                return data.get('scenes', [])
            return []
        except Exception as e:
            print(f"[CharacterGallery] 씬 데이터 로드 오류: {e}")
            return []

    def _load_characters_data(self) -> List[Dict]:
        """캐릭터 데이터 로드 (characters/characters.json 우선)"""
        # characters/characters.json 먼저 시도
        if self.characters_json.exists():
            try:
                with open(self.characters_json, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if data:
                        return data if isinstance(data, list) else []
            except Exception as e:
                print(f"[CharacterGallery] 캐릭터 데이터 로드 오류 (characters): {e}")

        # analysis/characters.json 폴백
        if self.analysis_chars_json.exists():
            try:
                with open(self.analysis_chars_json, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data if isinstance(data, list) else []
            except Exception as e:
                print(f"[CharacterGallery] 캐릭터 데이터 로드 오류 (analysis): {e}")

        return []

    def _scan_character_images(self) -> List[CharacterImage]:
        """캐릭터 이미지 디렉토리 스캔"""
        images = []

        if not self.characters_dir.exists():
            return images

        for filepath in self.characters_dir.iterdir():
            if not filepath.suffix.lower() in ['.png', '.jpg', '.jpeg', '.webp']:
                continue

            # 파일명에서 정보 추출
            char_info = self._parse_character_filename(filepath.name)

            if char_info:
                char_image = self._create_character_image(
                    char_info['name'],
                    char_info['pose'],
                    str(filepath)
                )
                images.append(char_image)

        return images

    def _parse_character_filename(self, filename: str) -> Optional[Dict]:
        """
        파일명에서 캐릭터 정보 추출

        지원 패턴:
        - char_캐릭터이름_포즈_타임스탬프.png
        - char_캐릭터이름_타임스탬프.png
        - char_캐릭터이름.png
        """
        try:
            # 확장자 제거
            name_part = Path(filename).stem

            if not name_part.startswith('char_'):
                return None

            name_part = name_part[5:]  # 'char_' 제거

            # 뒤에서부터 분리
            parts = name_part.rsplit('_', 2)

            # 타임스탬프 확인 및 제거
            if len(parts) >= 2 and parts[-1].isdigit() and len(parts[-1]) >= 10:
                parts = parts[:-1]

            # 포즈 확인
            known_poses = ['standing', 'sitting', 'walking', 'running', 'talking', 'default']
            pose = 'standing'  # 기본값

            if len(parts) >= 2 and parts[-1].lower() in known_poses:
                pose = parts[-1].lower()
                name = '_'.join(parts[:-1])
            else:
                name = '_'.join(parts)

            # 언더스코어를 공백으로 변환
            name = name.replace('_', ' ')

            return {
                'name': name,
                'pose': pose
            }
        except Exception as e:
            print(f"[CharacterGallery] 파일명 파싱 오류: {filename} - {e}")
            return None

    def _find_character_image(self, char_name: str, images: List[CharacterImage]) -> Optional[CharacterImage]:
        """캐릭터 이름으로 이미지 찾기 (유연한 매칭)"""
        char_name_normalized = char_name.replace(' ', '').lower()

        # 정확한 매칭
        for img in images:
            if img.character_name == char_name:
                return img

        # 정규화된 매칭
        for img in images:
            img_name_normalized = img.character_name.replace(' ', '').lower()
            if img_name_normalized == char_name_normalized:
                return img

        # 부분 매칭
        for img in images:
            if char_name in img.character_name or img.character_name in char_name:
                return img

        return None

    def _create_character_image(
        self,
        name: str,
        pose: str,
        image_path: str
    ) -> CharacterImage:
        """CharacterImage 객체 생성"""
        file_size = 0
        dimensions = (0, 0)
        created_at = ""
        needs_regeneration = False
        regeneration_reason = ""

        path = Path(image_path)

        if path.exists():
            stat = path.stat()
            file_size = stat.st_size
            created_at = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")

            # 이미지 크기
            try:
                from PIL import Image
                with Image.open(path) as img:
                    dimensions = img.size
            except Exception:
                pass

            # 재생성 필요 여부 판단
            needs_regeneration, regeneration_reason = self._check_needs_regeneration(
                image_path, file_size, dimensions
            )
        else:
            needs_regeneration = True
            regeneration_reason = "이미지 파일 없음"

        return CharacterImage(
            character_name=name,
            pose=pose,
            image_path=image_path,
            scene_numbers=[],
            created_at=created_at,
            file_size=file_size,
            dimensions=dimensions,
            needs_regeneration=needs_regeneration,
            regeneration_reason=regeneration_reason
        )

    def _check_needs_regeneration(
        self,
        image_path: str,
        file_size: int,
        dimensions: Tuple[int, int]
    ) -> Tuple[bool, str]:
        """재생성 필요 여부 판단"""
        # 파일 크기가 너무 작음 (손상 의심)
        if file_size < 10000:  # 10KB 미만
            return True, "파일 크기 너무 작음 (손상 의심)"

        # 해상도가 너무 낮음
        if dimensions[0] > 0 and dimensions[1] > 0:
            if dimensions[0] < 256 or dimensions[1] < 256:
                return True, f"해상도 낮음 ({dimensions[0]}x{dimensions[1]})"

        return False, ""

    def _find_background_image(self, scene_num: int) -> Optional[str]:
        """씬의 배경 이미지 찾기"""
        if not self.backgrounds_dir.exists():
            return None

        patterns = [
            f"bg_scene_{scene_num:03d}",
            f"bg_scene_{scene_num}",
            f"background_{scene_num}",
            f"scene_{scene_num}_bg",
        ]

        for filepath in self.backgrounds_dir.iterdir():
            filename = filepath.name
            for pattern in patterns:
                if pattern in filename:
                    return str(filepath)

        return None

    def get_statistics(self) -> Dict:
        """갤러리 통계"""
        scenes = self.get_scenes_with_characters()

        total_scenes = len(scenes)
        scenes_with_characters = sum(1 for s in scenes if s.characters)
        scenes_complete = sum(1 for s in scenes if s.is_complete)
        total_characters = sum(len(s.characters) for s in scenes)
        needs_regeneration = sum(
            sum(1 for c in s.characters if c.needs_regeneration)
            for s in scenes
        )

        return {
            'total_scenes': total_scenes,
            'scenes_with_characters': scenes_with_characters,
            'scenes_complete': scenes_complete,
            'total_character_images': total_characters,
            'needs_regeneration': needs_regeneration,
            'completion_rate': (scenes_complete / total_scenes * 100) if total_scenes > 0 else 0
        }


def get_gallery_manager(project_path: str) -> CharacterGalleryManager:
    """갤러리 매니저 인스턴스 반환 (캐싱 적용 v1.2)"""
    return _get_gallery_manager_cached(project_path)


# v1.2: 성능 최적화 - Streamlit 캐싱
try:
    import streamlit as st

    @st.cache_resource(show_spinner=False)
    def _get_gallery_manager_cached(project_path: str) -> CharacterGalleryManager:
        """캐싱된 갤러리 매니저 인스턴스"""
        return CharacterGalleryManager(project_path)
except ImportError:
    # Streamlit이 없는 환경에서는 캐싱 없이 직접 생성
    def _get_gallery_manager_cached(project_path: str) -> CharacterGalleryManager:
        return CharacterGalleryManager(project_path)
