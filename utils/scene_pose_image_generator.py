# -*- coding: utf-8 -*-
"""
씬별 포즈 캐릭터 이미지 생성기

기능:
- AI 포즈 분석 결과에 따라 각 씬에 맞는 포즈별 캐릭터 이미지 생성
- 동일 포즈는 재사용하여 효율화 (중복 생성 방지)
- characters.json에 scene_poses 정보 자동 저장
"""

import os
import json
import time
from pathlib import Path
from typing import List, Dict, Optional, Callable
from datetime import datetime


class ScenePoseImageGenerator:
    """씬별 포즈 캐릭터 이미지 생성기"""

    def __init__(self, project_path: str):
        """
        Args:
            project_path: 프로젝트 경로
        """
        self.project_path = Path(project_path)
        self.characters_path = self.project_path / "images" / "characters"
        self.characters_path.mkdir(parents=True, exist_ok=True)
        self.analysis_path = self.project_path / "analysis"
        self.analysis_path.mkdir(parents=True, exist_ok=True)

    def generate_scene_pose_images(
        self,
        character_name: str,
        visual_prompt: str,
        pose_assignments: List[Dict],
        image_generator,
        config=None,
        on_progress: Optional[Callable[[int, int, str], None]] = None
    ) -> Dict:
        """
        씬별 포즈 이미지 일괄 생성

        Args:
            character_name: 캐릭터 이름
            visual_prompt: 캐릭터 외형 프롬프트
            pose_assignments: AI 분석 결과 [{"scene_id": 1, "pose": "standing", "character": "..."}, ...]
            image_generator: 이미지 생성기 인스턴스 (CharacterImageGenerator)
            config: CharacterImageConfig 설정 (선택)
            on_progress: 진행률 콜백 (current, total, message)

        Returns:
            {
                "character": "김정빈",
                "total_scenes": 6,
                "unique_poses": 5,
                "images_generated": 5,
                "scene_poses": {...},
                "pose_images": {...}
            }
        """
        from utils.pose_analyzer import get_pose_prompt

        print(f"\n{'='*60}")
        print(f"[ScenePoseGenerator] 캐릭터 '{character_name}' 씬별 포즈 이미지 생성")
        print(f"[ScenePoseGenerator] 총 씬: {len(pose_assignments)}개")
        print(f"{'='*60}\n")

        # 1. 포즈별 씬 그룹화 (동일 포즈는 1개만 생성)
        pose_to_scenes = {}
        scene_to_pose = {}

        for assignment in pose_assignments:
            scene_id = assignment.get("scene_id")
            pose = assignment.get("pose", "standing")

            scene_to_pose[str(scene_id)] = pose

            if pose not in pose_to_scenes:
                pose_to_scenes[pose] = []
            pose_to_scenes[pose].append(scene_id)

        unique_poses = list(pose_to_scenes.keys())
        print(f"[ScenePoseGenerator] 고유 포즈: {len(unique_poses)}개")
        print(f"[ScenePoseGenerator] 포즈별 씬:")
        for pose, scenes in pose_to_scenes.items():
            print(f"  - {pose}: 씬 {scenes}")

        # 2. 각 고유 포즈별로 이미지 생성
        pose_images = {}
        scene_poses = {}

        total = len(unique_poses)

        for idx, pose in enumerate(unique_poses, 1):
            scenes_for_pose = pose_to_scenes[pose]
            first_scene = scenes_for_pose[0]

            print(f"\n[ScenePoseGenerator] [{idx}/{total}] 포즈 '{pose}' 이미지 생성...")
            print(f"  → 적용될 씬: {scenes_for_pose}")

            # 진행률 콜백
            if on_progress:
                on_progress(idx, total, f"'{character_name}' {pose} 포즈 생성 중...")

            # 이미지 생성
            try:
                image_path = self._generate_single_pose_image(
                    character_name=character_name,
                    visual_prompt=visual_prompt,
                    pose=pose,
                    scene_id=first_scene,
                    image_generator=image_generator,
                    config=config
                )

                if image_path:
                    pose_images[pose] = image_path
                    print(f"  ✅ 생성 완료: {image_path}")
                else:
                    print(f"  ❌ 생성 실패")

            except Exception as e:
                print(f"  ❌ 에러: {e}")
                continue

        # 3. 씬별 포즈 매핑 구성
        for scene_id_str, pose in scene_to_pose.items():
            image_path = pose_images.get(pose)

            scene_poses[scene_id_str] = {
                "pose": pose,
                "image_path": image_path
            }

        # 4. 결과 저장
        result = {
            "character": character_name,
            "visual_prompt": visual_prompt,
            "total_scenes": len(pose_assignments),
            "unique_poses": len(unique_poses),
            "images_generated": len(pose_images),
            "scene_poses": scene_poses,
            "pose_images": pose_images,
            "generated_at": datetime.now().isoformat()
        }

        # characters.json 업데이트
        self._update_character_data(character_name, result)

        print(f"\n{'='*60}")
        print(f"[ScenePoseGenerator] ✅ 완료!")
        print(f"  - 총 씬: {len(pose_assignments)}개")
        print(f"  - 고유 포즈: {len(unique_poses)}개")
        print(f"  - 생성된 이미지: {len(pose_images)}개")
        print(f"{'='*60}\n")

        return result

    def _generate_single_pose_image(
        self,
        character_name: str,
        visual_prompt: str,
        pose: str,
        scene_id: int,
        image_generator,
        config=None
    ) -> Optional[str]:
        """단일 포즈 이미지 생성"""
        from core.image.character_image_generator import CharacterImageConfig

        if config is None:
            config = CharacterImageConfig()

        # 포즈 설정으로 새 config 생성
        pose_config = CharacterImageConfig(
            style=config.style,
            pose=pose,  # 해당 포즈 사용
            background=config.background,
            width=config.width,
            height=config.height,
            model=config.model,
            style_prefix=config.style_prefix,
            style_suffix=config.style_suffix,
            api_provider=config.api_provider,
            parallel_count=1
        )

        # 캐릭터 정보 구성
        character = {
            "name": character_name,
            "visual_prompt": visual_prompt,
            "character_prompt": visual_prompt
        }

        # 이미지 생성
        result = image_generator.generate_character_image(
            character=character,
            config=pose_config,
            output_dir=self.characters_path
        )

        if result.get("success"):
            return result.get("image_path")

        return None

    def _update_character_data(self, character_name: str, pose_result: Dict):
        """characters.json에 씬별 포즈 정보 업데이트"""

        characters_file = self.analysis_path / "characters.json"

        if not characters_file.exists():
            # characters/characters.json 시도
            alt_file = self.project_path / "characters" / "characters.json"
            if alt_file.exists():
                characters_file = alt_file
            else:
                print(f"[ScenePoseGenerator] ⚠️ characters.json 없음")
                return

        try:
            with open(characters_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            # 캐릭터 찾기
            characters = data if isinstance(data, list) else data.get("characters", data)

            for char in characters:
                if char.get("name") == character_name:
                    # 씬별 포즈 정보 추가
                    char["scene_poses"] = pose_result["scene_poses"]
                    char["pose_images"] = pose_result["pose_images"]

                    # 기본 이미지는 첫 번째 포즈 이미지
                    if pose_result["pose_images"]:
                        first_pose = list(pose_result["pose_images"].keys())[0]
                        first_image = pose_result["pose_images"][first_pose]
                        char["default_image_path"] = first_image

                        # generated_images 리스트에도 추가
                        if "generated_images" not in char:
                            char["generated_images"] = []
                        for img_path in pose_result["pose_images"].values():
                            if img_path and img_path not in char["generated_images"]:
                                char["generated_images"].append(img_path)

                    print(f"[ScenePoseGenerator] ✅ '{character_name}' 데이터 업데이트됨")
                    break

            # 저장
            with open(characters_file, "w", encoding="utf-8") as f:
                json.dump(data if isinstance(data, dict) else characters, f, ensure_ascii=False, indent=2)

        except Exception as e:
            print(f"[ScenePoseGenerator] ❌ 데이터 업데이트 실패: {e}")


def get_character_image_for_scene(
    character_name: str,
    scene_id: int,
    characters_data: List[Dict]
) -> Optional[str]:
    """
    특정 씬에 사용할 캐릭터 이미지 경로 반환

    Args:
        character_name: 캐릭터 이름
        scene_id: 씬 ID
        characters_data: 캐릭터 데이터 리스트

    Returns:
        이미지 경로 또는 None
    """

    for char in characters_data:
        if char.get("name") != character_name:
            continue

        # 씬별 포즈가 있으면 해당 이미지 사용
        scene_poses = char.get("scene_poses", {})
        scene_key = str(scene_id)

        if scene_key in scene_poses:
            pose_info = scene_poses[scene_key]
            image_path = pose_info.get("image_path")

            if image_path and os.path.exists(image_path):
                return image_path

            # image_path가 없거나 파일이 없으면 동일 포즈의 다른 이미지 찾기
            pose = pose_info.get("pose")
            pose_images = char.get("pose_images", {})

            if pose in pose_images:
                alt_path = pose_images[pose]
                if alt_path and os.path.exists(alt_path):
                    return alt_path

        # 씬별 포즈가 없으면 기본 이미지 사용
        default_path = char.get("default_image_path") or char.get("image_path")
        if default_path:
            # generated_images에서 최신 이미지 찾기
            generated = char.get("generated_images", [])
            if generated:
                for img in reversed(generated):  # 최신 먼저
                    if os.path.exists(img):
                        return img

            if os.path.exists(default_path):
                return default_path

    return None


def generate_all_character_scene_poses(
    characters: List[Dict],
    pose_assignments: List[Dict],
    project_path: str,
    config=None,
    on_progress: Optional[Callable[[int, int, str], None]] = None,
    on_character_complete: Optional[Callable[[str, Dict], None]] = None
) -> Dict:
    """
    모든 캐릭터의 씬별 포즈 이미지 일괄 생성

    Args:
        characters: 캐릭터 데이터 리스트
        pose_assignments: 전체 AI 분석 결과
        project_path: 프로젝트 경로
        config: CharacterImageConfig 설정
        on_progress: 진행률 콜백
        on_character_complete: 캐릭터별 완료 콜백

    Returns:
        {
            "total_characters": 3,
            "total_images": 15,
            "results": {...}
        }
    """
    from core.image.character_image_generator import CharacterImageGenerator

    generator = ScenePoseImageGenerator(project_path)
    image_gen = CharacterImageGenerator(project_path)

    total_images = 0
    results = {}

    # 캐릭터별 포즈 할당 그룹화
    char_assignments = {}
    for assignment in pose_assignments:
        char_name = assignment.get("character", "")
        if char_name not in char_assignments:
            char_assignments[char_name] = []
        char_assignments[char_name].append(assignment)

    total_chars = len(char_assignments)
    char_idx = 0

    for char_name, assignments in char_assignments.items():
        char_idx += 1

        # 캐릭터 정보 찾기
        char_info = next((c for c in characters if c.get("name") == char_name), None)

        if not char_info:
            print(f"[ScenePoseGenerator] ⚠️ '{char_name}' 캐릭터 정보 없음")
            continue

        visual_prompt = (
            char_info.get("visual_prompt") or
            char_info.get("character_prompt") or
            char_info.get("prompt") or
            ""
        )

        if not visual_prompt:
            print(f"[ScenePoseGenerator] ⚠️ '{char_name}' visual_prompt 없음")
            continue

        # 진행률 래퍼
        def char_progress(current, total, msg):
            if on_progress:
                overall = (char_idx - 1) / total_chars + (current / total) / total_chars
                on_progress(int(overall * 100), 100, f"[{char_idx}/{total_chars}] {msg}")

        # 캐릭터 씬별 포즈 이미지 생성
        result = generator.generate_scene_pose_images(
            character_name=char_name,
            visual_prompt=visual_prompt,
            pose_assignments=assignments,
            image_generator=image_gen,
            config=config,
            on_progress=char_progress
        )

        results[char_name] = result
        total_images += result.get("images_generated", 0)

        # 캐릭터 완료 콜백
        if on_character_complete:
            on_character_complete(char_name, result)

    return {
        "total_characters": len(results),
        "total_images": total_images,
        "results": results
    }
