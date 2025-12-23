# -*- coding: utf-8 -*-
"""
캐릭터-씬 자동 연동 모듈

기능:
1. 캐릭터의 appearance_scenes 정보 활용
2. 이미지 생성 시 해당 씬에 자동 연결
3. 스토리보드에서 바로 사용 가능
4. 포즈별 씬 매핑 지원
"""

import json
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime


class CharacterSceneLinker:
    """캐릭터-씬 자동 연동기"""

    def __init__(self, project_path: Path):
        """
        Args:
            project_path: 프로젝트 경로
        """
        self.project_path = Path(project_path)
        self.characters_file = self.project_path / "analysis" / "characters.json"
        self.scenes_file = self.project_path / "analysis" / "scenes.json"
        self.scene_characters_file = self.project_path / "scene_characters.json"

    def get_character_scenes(self, character_name: str) -> List[int]:
        """
        캐릭터가 등장하는 씬 번호 목록 가져오기

        Args:
            character_name: 캐릭터 이름

        Returns:
            [1, 2, 5, 8] - 등장 씬 번호 리스트
        """
        characters = self._load_characters()

        for char in characters:
            if char.get("name") == character_name:
                scenes = char.get("appearance_scenes", [])
                # 문자열인 경우 정수로 변환
                return [int(s) if isinstance(s, str) else s for s in scenes]

        return []

    def get_all_character_scenes(self) -> Dict[str, List[int]]:
        """
        모든 캐릭터의 등장 씬 정보 가져오기

        Returns:
            {
                "자말 카슈끄지": [1, 2, 5],
                "무함마드 빈 살만": [2, 3, 4]
            }
        """
        characters = self._load_characters()
        result = {}

        for char in characters:
            name = char.get("name")
            if name:
                scenes = char.get("appearance_scenes", [])
                result[name] = [int(s) if isinstance(s, str) else s for s in scenes]

        return result

    def link_character_image_to_scenes(
        self,
        character_name: str,
        image_path: str,
        pose: str,
        specific_scenes: List[int] = None
    ) -> Dict:
        """
        캐릭터 이미지를 씬에 연결

        Args:
            character_name: 캐릭터 이름
            image_path: 생성된 이미지 경로
            pose: 포즈 종류
            specific_scenes: 특정 씬만 연결 (None이면 모든 등장 씬)

        Returns:
            {
                "success": True,
                "linked_scenes": [1, 2, 5],
                "character_name": "자말 카슈끄지"
            }
        """
        # 캐릭터 등장 씬 가져오기
        appearance_scenes = self.get_character_scenes(character_name)

        if not appearance_scenes:
            return {
                "success": False,
                "error": f"캐릭터 '{character_name}'의 등장 씬 정보가 없습니다.",
                "linked_scenes": []
            }

        # 특정 씬만 선택된 경우
        if specific_scenes:
            target_scenes = [s for s in specific_scenes if s in appearance_scenes]
        else:
            target_scenes = appearance_scenes

        if not target_scenes:
            return {
                "success": False,
                "error": "연결할 씬이 없습니다.",
                "linked_scenes": []
            }

        # 씬-캐릭터 매핑 데이터 로드/생성
        scene_characters = self._load_scene_characters()

        linked_scenes = []

        for scene_id in target_scenes:
            scene_key = str(scene_id)

            if scene_key not in scene_characters:
                scene_characters[scene_key] = {"characters": {}}

            # 캐릭터 이미지 정보 저장
            if character_name not in scene_characters[scene_key]["characters"]:
                scene_characters[scene_key]["characters"][character_name] = {"poses": {}}

            scene_characters[scene_key]["characters"][character_name]["poses"][pose] = {
                "image_path": str(image_path),
                "updated_at": datetime.now().isoformat()
            }

            linked_scenes.append(scene_id)

        # 저장
        self._save_scene_characters(scene_characters)

        print(f"[CharacterSceneLinker] '{character_name}' ({pose}) → 씬 {linked_scenes}에 연결됨")

        return {
            "success": True,
            "linked_scenes": linked_scenes,
            "character_name": character_name,
            "pose": pose,
            "image_path": str(image_path)
        }

    def get_scene_character_images(self, scene_id: int) -> Dict[str, Dict]:
        """
        특정 씬의 캐릭터 이미지 목록 가져오기

        Args:
            scene_id: 씬 번호

        Returns:
            {
                "자말 카슈끄지": {
                    "poses": {
                        "정면 서있기": {"image_path": "..."},
                        "왼쪽 향해 서있기": {"image_path": "..."}
                    }
                }
            }
        """
        scene_characters = self._load_scene_characters()
        scene_key = str(scene_id)

        if scene_key in scene_characters:
            return scene_characters[scene_key].get("characters", {})

        return {}

    def auto_link_all_characters(self, generated_images: List[Dict]) -> Dict:
        """
        생성된 모든 캐릭터 이미지를 등장 씬에 자동 연결

        Args:
            generated_images: [
                {
                    "character_name": "자말 카슈끄지",
                    "image_path": "...",
                    "pose": "정면 서있기",
                    "success": True,
                    "target_scenes": [1, 2]  # 선택적
                }
            ]

        Returns:
            {
                "total_linked": 15,
                "by_character": {
                    "자말 카슈끄지": [1, 2, 5],
                    "무함마드 빈 살만": [2, 3, 4]
                }
            }
        """
        total_linked = 0
        by_character = {}

        for img in generated_images:
            if not img.get("success"):
                continue

            char_name = img.get("character_name")
            image_path = img.get("image_path")
            pose = img.get("pose", "default")
            specific_scenes = img.get("target_scenes")

            result = self.link_character_image_to_scenes(
                character_name=char_name,
                image_path=image_path,
                pose=pose,
                specific_scenes=specific_scenes
            )

            if result.get("success"):
                linked = result.get("linked_scenes", [])
                total_linked += len(linked)

                if char_name not in by_character:
                    by_character[char_name] = []
                by_character[char_name].extend(linked)

        return {
            "total_linked": total_linked,
            "by_character": by_character
        }

    def get_pose_scene_mapping_for_character(self, character_name: str) -> Dict[str, List[int]]:
        """
        캐릭터의 포즈별 씬 매핑 가져오기

        Returns:
            {
                "정면 서있기": [1, 2],
                "왼쪽 향해 서있기": [3]
            }
        """
        scene_characters = self._load_scene_characters()
        result = {}

        for scene_key, scene_data in scene_characters.items():
            characters = scene_data.get("characters", {})
            if character_name in characters:
                poses = characters[character_name].get("poses", {})
                for pose in poses:
                    if pose not in result:
                        result[pose] = []
                    try:
                        result[pose].append(int(scene_key))
                    except ValueError:
                        pass

        return result

    def clear_character_links(self, character_name: str = None):
        """
        캐릭터 연결 정보 삭제

        Args:
            character_name: 특정 캐릭터만 삭제 (None이면 전체)
        """
        if character_name is None:
            # 전체 삭제
            self._save_scene_characters({})
        else:
            scene_characters = self._load_scene_characters()
            for scene_key in scene_characters:
                chars = scene_characters[scene_key].get("characters", {})
                if character_name in chars:
                    del chars[character_name]
            self._save_scene_characters(scene_characters)

    def _load_characters(self) -> List[Dict]:
        """캐릭터 데이터 로드"""
        if not self.characters_file.exists():
            return []
        try:
            with open(self.characters_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _load_scene_characters(self) -> Dict:
        """씬-캐릭터 매핑 데이터 로드"""
        if not self.scene_characters_file.exists():
            return {}
        try:
            with open(self.scene_characters_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_scene_characters(self, data: Dict):
        """씬-캐릭터 매핑 데이터 저장"""
        self.project_path.mkdir(parents=True, exist_ok=True)
        with open(self.scene_characters_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


# 포즈 옵션 상수
POSE_OPTIONS = [
    ("standing_front", "정면 서있기", "캐릭터가 정면을 바라보며 서 있는 자세"),
    ("standing_left", "왼쪽 향해 서있기", "캐릭터가 왼쪽을 향해 서 있는 자세"),
    ("standing_right", "오른쪽 향해 서있기", "캐릭터가 오른쪽을 향해 서 있는 자세"),
    ("portrait", "상반신 초상화", "얼굴과 상반신 클로즈업"),
    ("sitting", "앉아있기", "캐릭터가 앉아 있는 자세"),
]


def get_pose_prompt_modifier(pose_key: str) -> str:
    """포즈 키에 해당하는 프롬프트 수식어 반환"""
    modifiers = {
        "standing_front": "standing, facing viewer, front view",
        "standing_left": "standing, looking left, side view",
        "standing_right": "standing, looking right, side view",
        "portrait": "portrait, upper body, close-up face",
        "sitting": "sitting, relaxed pose",
    }
    return modifiers.get(pose_key, "standing, facing viewer")
