"""
씬 이미지 생성기 - 배경과 캐릭터를 조합한 씬 이미지 생성

세모지 스타일 워크플로우:
1. 씬 분석 결과에서 연출가이드 + 등장 캐릭터 정보 로드
2. 캐릭터 프롬프트 + 배경/연출 프롬프트 조합
3. 통합된 프롬프트로 이미지 생성
"""
import json
import time
from pathlib import Path
from typing import List, Dict, Optional, Callable
from dataclasses import dataclass

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.character.character_manager import CharacterManager
from core.image.together_client import TogetherImageClient


@dataclass
class SceneImageConfig:
    """씬 이미지 생성 설정"""
    style_prefix: str = "animation style, infographic illustration, clean lines, vibrant colors, no text"
    width: int = 1280
    height: int = 720
    model: str = "black-forest-labs/FLUX.2-dev"
    include_characters: bool = True
    character_style: str = "full body, standing"
    negative_prompt: str = "text, words, letters, watermark, low quality, blurry"


class SceneImageGenerator:
    """씬 이미지 생성기"""

    def __init__(self, project_path: str):
        self.project_path = Path(project_path)
        self.character_manager = CharacterManager(project_path)
        self.image_client = TogetherImageClient()

        # 씬 데이터 로드
        self.scenes = self._load_scenes()

    def _load_scenes(self) -> List[Dict]:
        """씬 분석 결과 로드"""
        scenes_path = self.project_path / "analysis" / "scenes.json"
        if scenes_path.exists():
            with open(scenes_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    def _get_character_prompt(self, character_names: List[str]) -> str:
        """등장 캐릭터들의 프롬프트 조합"""
        prompts = []

        for name in character_names:
            char = self.character_manager.get_character_by_name(name)
            if char and char.character_prompt:
                prompts.append(char.character_prompt)

        if prompts:
            return ", ".join(prompts)
        return ""

    def generate_scene_prompt(self, scene: Dict, config: SceneImageConfig) -> str:
        """
        씬에 대한 통합 프롬프트 생성

        구조: [스타일] + [배경/연출] + [캐릭터들] + [분위기]
        """
        parts = []

        # 1. 스타일 프리픽스
        parts.append(config.style_prefix)

        # 2. 씬의 이미지 프롬프트 (연출가이드 기반)
        scene_prompt = scene.get("image_prompt_en", "")
        if scene_prompt:
            parts.append(scene_prompt)

        # 3. 캐릭터 프롬프트 (씬에 등장하는 캐릭터)
        if config.include_characters:
            character_names = scene.get("characters", [])
            if character_names:
                char_prompt = self._get_character_prompt(character_names)
                if char_prompt:
                    # 캐릭터 수에 따른 구도 추가
                    if len(character_names) == 1:
                        parts.append(f"single character in scene, {config.character_style}, {char_prompt}")
                    elif len(character_names) == 2:
                        parts.append(f"two characters interacting, {char_prompt}")
                    else:
                        parts.append(f"multiple characters ({len(character_names)} people), {char_prompt}")

        # 4. 분위기/무드
        mood = scene.get("mood", "")
        if mood:
            parts.append(f"{mood} mood")

        # 5. 시각 요소
        visual_elements = scene.get("visual_elements", [])
        if visual_elements:
            parts.append(", ".join(visual_elements))

        return ", ".join(filter(None, parts))

    def generate_single_scene_image(self, scene_id: int, config: SceneImageConfig,
                                     output_dir: Path) -> Dict:
        """단일 씬 이미지 생성"""

        # 씬 찾기
        scene = None
        for s in self.scenes:
            if s.get("scene_id") == scene_id:
                scene = s
                break

        if not scene:
            return {"success": False, "error": f"Scene {scene_id} not found"}

        # 프롬프트 생성
        prompt = self.generate_scene_prompt(scene, config)

        # 파일명
        filename = f"scene_{scene_id:03d}.png"
        output_path = output_dir / filename

        try:
            # 이미지 생성
            img_data = self.image_client.generate_image(
                prompt=prompt,
                model=config.model,
                width=config.width,
                height=config.height
            )

            # 저장
            with open(output_path, "wb") as f:
                f.write(img_data)

            return {
                "success": True,
                "scene_id": scene_id,
                "prompt": prompt,
                "characters": scene.get("characters", []),
                "saved_path": str(output_path),
                "filename": filename
            }

        except Exception as e:
            return {
                "success": False,
                "scene_id": scene_id,
                "prompt": prompt,
                "characters": scene.get("characters", []),
                "error": str(e)
            }

    def generate_all_scene_images(self, config: SceneImageConfig,
                                   start_scene: int = 1, end_scene: int = None,
                                   on_progress: Callable = None) -> List[Dict]:
        """모든 씬 이미지 배치 생성"""

        output_dir = self.project_path / "images" / "scenes"
        output_dir.mkdir(parents=True, exist_ok=True)

        results = []

        # 씬 범위 설정
        scenes_to_generate = [s for s in self.scenes
                             if s.get("scene_id", 0) >= start_scene]
        if end_scene:
            scenes_to_generate = [s for s in scenes_to_generate
                                 if s.get("scene_id", 0) <= end_scene]

        total = len(scenes_to_generate)
        is_free_model = "Free" in config.model

        for i, scene in enumerate(scenes_to_generate):
            scene_id = scene.get("scene_id", i + 1)

            start_time = time.time()

            # Rate limit 대기 (첫 번째 제외)
            if i > 0 and is_free_model:
                # 이전 요청 이후 경과 시간 확인
                elapsed_since_last = time.time() - self._last_request_time if hasattr(self, '_last_request_time') else 0
                wait_time = max(0, 6 - elapsed_since_last)
                if wait_time > 0:
                    time.sleep(wait_time)

            result = self.generate_single_scene_image(scene_id, config, output_dir)
            elapsed = time.time() - start_time

            self._last_request_time = time.time()

            result["generation_time"] = elapsed
            results.append(result)

            if on_progress:
                on_progress(i + 1, total, result)

        # 결과 저장
        log_path = output_dir / "generation_log.json"
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        return results

    def get_scene_with_characters(self, scene_id: int) -> Dict:
        """씬 정보와 캐릭터 상세 정보 조회"""
        scene = None
        for s in self.scenes:
            if s.get("scene_id") == scene_id:
                scene = s.copy()
                break

        if not scene:
            return {}

        # 캐릭터 상세 정보 추가
        character_details = []
        for name in scene.get("characters", []):
            char = self.character_manager.get_character_by_name(name)
            if char:
                character_details.append({
                    "name": char.name,
                    "name_en": char.name_en,
                    "prompt": char.character_prompt,
                    "images": char.generated_images if hasattr(char, 'generated_images') else []
                })

        scene["character_details"] = character_details
        return scene

    def get_scenes_summary(self) -> Dict:
        """씬 요약 정보"""
        if not self.scenes:
            return {"total": 0, "with_characters": 0, "without_characters": 0}

        with_chars = sum(1 for s in self.scenes if s.get("characters"))
        return {
            "total": len(self.scenes),
            "with_characters": with_chars,
            "without_characters": len(self.scenes) - with_chars,
            "characters": list(set(
                char for s in self.scenes for char in s.get("characters", [])
            ))
        }
