# -*- coding: utf-8 -*-
"""
씬별 캐릭터 이미지 선택기

기능:
- 합성 시 각 씬에 맞는 캐릭터 포즈 이미지 선택
- 단일 포즈 / 씬별 다중 포즈 모드 지원
- scene_poses, pose_images 데이터 활용
"""

import os
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from enum import Enum


class CharacterPoseMode(Enum):
    """캐릭터 포즈 적용 모드"""
    SINGLE = "single"           # 단일 포즈 (모든 씬에 동일)
    SCENE_BASED = "scene_based" # 씬별 다른 포즈


class CharacterImageSelector:
    """씬별 캐릭터 이미지 선택"""

    def __init__(self, project_path: str = None, characters_data: List[Dict] = None):
        """
        Args:
            project_path: 프로젝트 경로 (파일에서 로드)
            characters_data: 캐릭터 데이터 직접 전달 (세션에서)
        """
        self.project_path = Path(project_path) if project_path else None

        if characters_data:
            self.characters_data = characters_data
        elif self.project_path:
            self.characters_data = self._load_characters_data()
        else:
            self.characters_data = []

    def _load_characters_data(self) -> List[Dict]:
        """캐릭터 데이터 로드"""

        # 여러 가능한 경로 시도
        possible_paths = [
            self.project_path / "analysis" / "characters.json",
            self.project_path / "characters" / "characters.json",
        ]

        for characters_file in possible_paths:
            if characters_file.exists():
                try:
                    with open(characters_file, "r", encoding="utf-8") as f:
                        data = json.load(f)

                    if isinstance(data, list):
                        print(f"[ImageSelector] ✅ 캐릭터 {len(data)}개 로드됨: {characters_file}")
                        return data
                    return data.get("characters", [])

                except Exception as e:
                    print(f"[ImageSelector] ❌ 로드 실패: {e}")

        print(f"[ImageSelector] ⚠️ characters.json 없음")
        return []

    def get_character_info(self, character_name: str) -> Optional[Dict]:
        """캐릭터 정보 가져오기"""

        for char in self.characters_data:
            if char.get("name") == character_name:
                return char
        return None

    def get_available_poses(self, character_name: str) -> Dict[str, str]:
        """
        캐릭터의 사용 가능한 포즈와 이미지 경로 반환

        Returns:
            {"standing": "/path/to/standing.png", "talking": "/path/to/talking.png", ...}
        """

        char = self.get_character_info(character_name)

        if not char:
            return {}

        # pose_images 필드 확인 (새 구조 - ScenePoseImageGenerator가 생성)
        pose_images = char.get("pose_images", {})

        if pose_images:
            # 존재하는 파일만 반환
            valid_poses = {}
            for pose, path in pose_images.items():
                if path and os.path.exists(path):
                    valid_poses[pose] = path

            if valid_poses:
                return valid_poses

        # generated_images 리스트에서 포즈 추출 시도
        generated = char.get("generated_images", [])

        if generated:
            poses = {}
            for img_path in generated:
                if not os.path.exists(img_path):
                    continue

                filename = os.path.basename(img_path)
                parts = filename.lower().split("_")

                # 포즈 이름 추출 시도
                known_poses = [
                    "standing", "sitting", "walking", "talking",
                    "thinking", "surprised", "happy", "angry",
                    "sad", "pointing", "presenting", "waving"
                ]

                for part in parts:
                    if part in known_poses:
                        poses[part] = img_path
                        break
                else:
                    # 포즈를 찾지 못하면 인덱스로
                    poses[f"pose_{len(poses)+1}"] = img_path

            if poses:
                return poses

        # 단일 이미지만 있는 경우
        single_image = (
            char.get("default_image_path") or
            char.get("image_path") or
            char.get("image_url")
        )

        if single_image and os.path.exists(single_image):
            return {"default": single_image}

        return {}

    def get_scene_pose_mapping(self, character_name: str) -> Dict[int, Dict]:
        """
        씬별 포즈 매핑 정보 반환

        Returns:
            {
                1: {"pose": "standing", "image_path": "/path/to/..."},
                2: {"pose": "talking", "image_path": "/path/to/..."},
                ...
            }
        """

        char = self.get_character_info(character_name)

        if not char:
            return {}

        scene_poses = char.get("scene_poses", {})

        # 문자열 키를 정수로 변환
        result = {}
        for scene_key, pose_info in scene_poses.items():
            try:
                scene_id = int(scene_key)
                result[scene_id] = pose_info
            except ValueError:
                continue

        return result

    def has_scene_poses(self, character_name: str) -> bool:
        """캐릭터에 씬별 포즈가 설정되어 있는지 확인"""

        char = self.get_character_info(character_name)

        if not char:
            return False

        scene_poses = char.get("scene_poses", {})
        pose_images = char.get("pose_images", {})

        # 씬별 포즈 데이터가 있고, 포즈 이미지도 1개 이상인 경우
        return bool(scene_poses) and len(pose_images) > 0

    def get_image_for_scene(
        self,
        character_name: str,
        scene_id: int,
        mode: CharacterPoseMode = CharacterPoseMode.SCENE_BASED,
        fallback_pose: str = None
    ) -> Optional[str]:
        """
        특정 씬에 사용할 캐릭터 이미지 경로 반환

        Args:
            character_name: 캐릭터 이름
            scene_id: 씬 ID
            mode: 포즈 적용 모드
            fallback_pose: 씬별 포즈가 없을 때 사용할 기본 포즈

        Returns:
            이미지 경로 또는 None
        """

        char = self.get_character_info(character_name)

        if not char:
            print(f"[ImageSelector] ⚠️ 캐릭터 '{character_name}' 없음")
            return None

        # 단일 포즈 모드
        if mode == CharacterPoseMode.SINGLE:
            return self._get_single_pose_image(char, fallback_pose)

        # 씬별 포즈 모드
        return self._get_scene_based_image(char, scene_id, fallback_pose)

    def _get_single_pose_image(
        self,
        char: Dict,
        preferred_pose: str = None
    ) -> Optional[str]:
        """단일 포즈 이미지 반환 (모든 씬에 동일)"""

        # 선호 포즈가 있으면 해당 포즈 이미지
        if preferred_pose:
            pose_images = char.get("pose_images", {})
            if preferred_pose in pose_images:
                path = pose_images[preferred_pose]
                if path and os.path.exists(path):
                    return path

        # 대표 이미지 반환
        default = (
            char.get("default_image_path") or
            char.get("image_path") or
            char.get("image_url")
        )

        if default and os.path.exists(default):
            return default

        # generated_images 리스트의 첫 번째
        generated = char.get("generated_images", [])
        for img in generated:
            if os.path.exists(img):
                return img

        # pose_images의 첫 번째
        pose_images = char.get("pose_images", {})
        for pose, path in pose_images.items():
            if path and os.path.exists(path):
                return path

        return None

    def _get_scene_based_image(
        self,
        char: Dict,
        scene_id: int,
        fallback_pose: str = None
    ) -> Optional[str]:
        """씬 기반 포즈 이미지 반환"""

        char_name = char.get("name", "unknown")
        scene_poses = char.get("scene_poses", {})
        scene_key = str(scene_id)

        # 해당 씬의 포즈 정보 확인
        if scene_key in scene_poses:
            pose_info = scene_poses[scene_key]
            image_path = pose_info.get("image_path")

            if image_path and os.path.exists(image_path):
                pose_name = pose_info.get("pose", "unknown")
                print(f"[ImageSelector] ✅ '{char_name}' 씬 {scene_id}: {pose_name} 포즈")
                return image_path

            # image_path가 없거나 파일이 없으면 pose 이름으로 pose_images에서 찾기
            pose_name = pose_info.get("pose")
            pose_images = char.get("pose_images", {})

            if pose_name and pose_name in pose_images:
                path = pose_images[pose_name]
                if path and os.path.exists(path):
                    print(f"[ImageSelector] ✅ '{char_name}' 씬 {scene_id}: {pose_name} 포즈 (pose_images)")
                    return path

        # 폴백: 단일 포즈 이미지
        print(f"[ImageSelector] ⚠️ '{char_name}' 씬 {scene_id}: 씬별 포즈 없음, 기본 이미지 사용")
        return self._get_single_pose_image(char, fallback_pose)

    def get_all_scene_images(
        self,
        character_name: str,
        scene_ids: List[int],
        mode: CharacterPoseMode = CharacterPoseMode.SCENE_BASED
    ) -> Dict[int, str]:
        """
        여러 씬의 캐릭터 이미지 일괄 반환

        Returns:
            {1: "/path/to/scene1.png", 2: "/path/to/scene2.png", ...}
        """

        result = {}

        for scene_id in scene_ids:
            image_path = self.get_image_for_scene(
                character_name=character_name,
                scene_id=scene_id,
                mode=mode
            )

            if image_path:
                result[scene_id] = image_path

        return result

    def get_pose_summary(self) -> Dict[str, Dict]:
        """모든 캐릭터의 포즈 정보 요약"""

        summary = {}

        for char in self.characters_data:
            char_name = char.get("name", "unknown")

            pose_images = char.get("pose_images", {})
            scene_poses = char.get("scene_poses", {})

            valid_pose_count = sum(
                1 for path in pose_images.values()
                if path and os.path.exists(path)
            )

            summary[char_name] = {
                "has_scene_poses": bool(scene_poses),
                "unique_poses": len(pose_images),
                "valid_images": valid_pose_count,
                "scene_count": len(scene_poses),
                "poses": list(pose_images.keys()),
                "scenes_with_poses": [int(k) for k in scene_poses.keys() if k.isdigit()]
            }

        return summary


# ============================================================
# 헬퍼 함수
# ============================================================

def get_character_image_for_composition(
    project_path: str = None,
    characters_data: List[Dict] = None,
    character_name: str = "",
    scene_id: int = 1,
    use_scene_pose: bool = True
) -> Optional[str]:
    """
    합성용 캐릭터 이미지 경로 반환 (간편 함수)

    Args:
        project_path: 프로젝트 경로 (characters_data 없을 때)
        characters_data: 캐릭터 데이터 리스트 (세션에서 가져올 때)
        character_name: 캐릭터 이름
        scene_id: 씬 ID
        use_scene_pose: 씬별 포즈 사용 여부

    Returns:
        이미지 경로
    """

    selector = CharacterImageSelector(
        project_path=project_path,
        characters_data=characters_data
    )

    mode = CharacterPoseMode.SCENE_BASED if use_scene_pose else CharacterPoseMode.SINGLE

    return selector.get_image_for_scene(
        character_name=character_name,
        scene_id=scene_id,
        mode=mode
    )


def get_character_image_for_scene_from_session(
    character_info: Dict,
    scene_id: int,
    use_scene_pose: bool = True
) -> Optional[str]:
    """
    세션에 있는 개별 캐릭터 정보에서 씬별 이미지 반환

    execute_composite 함수에서 직접 사용

    Args:
        character_info: 개별 캐릭터 정보 딕셔너리
        scene_id: 씬 ID
        use_scene_pose: 씬별 포즈 사용 여부

    Returns:
        이미지 경로
    """

    if not character_info:
        return None

    char_name = character_info.get("name", "unknown")

    # 씬별 포즈 모드
    if use_scene_pose:
        scene_poses = character_info.get("scene_poses", {})
        scene_key = str(scene_id)

        if scene_key in scene_poses:
            pose_info = scene_poses[scene_key]
            image_path = pose_info.get("image_path")

            if image_path and os.path.exists(image_path):
                pose_name = pose_info.get("pose", "unknown")
                print(f"[ImageSelector] ✅ '{char_name}' 씬 {scene_id}: {pose_name} 포즈")
                return image_path

            # pose_images에서 찾기
            pose_name = pose_info.get("pose")
            pose_images = character_info.get("pose_images", {})

            if pose_name and pose_name in pose_images:
                path = pose_images[pose_name]
                if path and os.path.exists(path):
                    print(f"[ImageSelector] ✅ '{char_name}' 씬 {scene_id}: {pose_name} 포즈 (pose_images)")
                    return path

        print(f"[ImageSelector] ⚠️ '{char_name}' 씬 {scene_id}: 씬별 포즈 없음, 기본 이미지")

    # 기본 이미지 반환
    return (
        character_info.get("image_path") or
        character_info.get("image_url") or
        character_info.get("default_image_path")
    )


def check_characters_have_scene_poses(characters_data: List[Dict]) -> Tuple[bool, Dict[str, bool]]:
    """
    캐릭터들이 씬별 포즈를 가지고 있는지 확인

    Returns:
        (any_has_poses, {char_name: has_poses})
    """

    result = {}
    any_has = False

    for char in characters_data:
        char_name = char.get("name", "unknown")
        scene_poses = char.get("scene_poses", {})
        pose_images = char.get("pose_images", {})

        has_poses = bool(scene_poses) and len(pose_images) > 1
        result[char_name] = has_poses

        if has_poses:
            any_has = True

    return any_has, result
