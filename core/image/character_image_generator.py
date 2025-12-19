"""
캐릭터 이미지 생성기 (합성용)

캐릭터를 단색 배경으로 생성하여 나중에 배경과 합성할 수 있도록 함
"""
import time
from pathlib import Path
from typing import Dict, Optional, List
from dataclasses import dataclass

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.image.together_client import TogetherImageClient


@dataclass
class CharacterImageConfig:
    """캐릭터 이미지 생성 설정"""
    style: str = "animation"
    pose: str = "standing"
    background: str = "solid_gray"
    width: int = 1024
    height: int = 1024
    model: str = "black-forest-labs/FLUX.1-schnell-Free"
    style_prefix: str = ""  # 스타일 프롬프트 앞에 추가
    style_suffix: str = ""  # 스타일 프롬프트 뒤에 추가


class CharacterImageGenerator:
    """캐릭터 이미지 생성기 (합성용)"""

    # 스타일 프리셋
    STYLE_PRESETS = {
        "animation": "animation style, flat colors, clean lines, high quality illustration",
        "illustration": "digital illustration, detailed artwork, professional quality",
        "manga": "manga style, anime aesthetic, clean linework",
        "3d_render": "3D rendered character, Pixar style, high quality CGI",
        "realistic": "semi-realistic style, detailed features, professional artwork"
    }

    # 포즈 옵션
    POSE_OPTIONS = {
        "standing": "standing pose, front view, neutral expression",
        "standing_left": "standing pose, facing slightly left, three-quarter view",
        "standing_right": "standing pose, facing slightly right, three-quarter view",
        "sitting": "sitting pose, relaxed posture",
        "walking": "walking pose, side view, in motion",
        "action": "dynamic action pose, energetic",
        "portrait": "upper body portrait, shoulders up"
    }

    # 배경 옵션
    BACKGROUND_OPTIONS = {
        "solid_gray": "simple solid light gray background (#E0E0E0), no shadows on background",
        "solid_white": "simple solid pure white background, no shadows",
        "solid_blue": "simple solid light blue background (#87CEEB), no shadows",
        "gradient": "simple gradient background from light gray to white"
    }

    def __init__(self, project_path: str = None):
        """
        Args:
            project_path: 프로젝트 경로 (이미지 저장용)
        """
        self.project_path = Path(project_path) if project_path else None
        self.image_client = TogetherImageClient()
        self._last_request_time = 0

    def _build_prompt(
        self,
        visual_prompt: str,
        style: str = "animation",
        pose: str = "standing",
        background: str = "solid_gray",
        style_prefix: str = "",
        style_suffix: str = ""
    ) -> str:
        """캐릭터 이미지 생성 프롬프트 구성"""

        # 커스텀 스타일 prefix/suffix가 있으면 사용, 없으면 기본 프리셋 사용
        if style_prefix or style_suffix:
            style_text = ""  # 커스텀 스타일 사용 시 기본 프리셋 비활성화
        else:
            style_text = self.STYLE_PRESETS.get(style, self.STYLE_PRESETS["animation"])

        pose_text = self.POSE_OPTIONS.get(pose, self.POSE_OPTIONS["standing"])
        bg_text = self.BACKGROUND_OPTIONS.get(background, self.BACKGROUND_OPTIONS["solid_gray"])

        # 프롬프트 구성
        prompt_parts = []

        # 1. 스타일 prefix (맨 앞)
        if style_prefix:
            prompt_parts.append(style_prefix.strip())

        # 2. 캐릭터 visual prompt
        prompt_parts.append(visual_prompt.strip())

        # 3. 포즈와 배경
        prompt_parts.append(f"full body character, {pose_text}, {bg_text}")

        # 4. 스타일 텍스트 (커스텀이 없을 때만)
        if style_text:
            prompt_parts.append(style_text)

        # 5. 합성용 공통 요소
        prompt_parts.append("clean edges suitable for compositing, centered in frame, single character only")

        # 6. 스타일 suffix (맨 뒤)
        if style_suffix:
            prompt_parts.append(style_suffix.strip())

        prompt = ", ".join(prompt_parts)

        return prompt

    def generate_character_image(
        self,
        character: Dict,
        config: CharacterImageConfig = None,
        output_dir: Path = None
    ) -> Dict:
        """
        캐릭터 이미지 생성

        Args:
            character: 캐릭터 정보 (name, visual_prompt 또는 character_prompt 등)
            config: 생성 설정
            output_dir: 출력 디렉토리 (미지정 시 project_path/images/characters)

        Returns:
            {
                "success": bool,
                "character_name": str,
                "image_path": str,
                "prompt": str,
                "pose": str,
                "background": str,
                "error": str (실패 시)
            }
        """
        if config is None:
            config = CharacterImageConfig()

        char_name = character.get("name", "unknown")

        # visual_prompt 또는 character_prompt 가져오기
        visual_prompt = (
            character.get("visual_prompt") or
            character.get("character_prompt") or
            character.get("prompt") or
            ""
        )

        if not visual_prompt:
            return {
                "success": False,
                "character_name": char_name,
                "error": f"캐릭터 '{char_name}'에 visual_prompt가 없습니다."
            }

        # 프롬프트 생성
        prompt = self._build_prompt(
            visual_prompt=visual_prompt,
            style=config.style,
            pose=config.pose,
            background=config.background,
            style_prefix=config.style_prefix,
            style_suffix=config.style_suffix
        )

        print(f"[CharacterImageGenerator] 캐릭터 '{char_name}' 이미지 생성")
        print(f"  스타일: {config.style}")
        print(f"  포즈: {config.pose}")
        print(f"  배경: {config.background}")
        print(f"  프롬프트: {prompt[:100]}...")

        # 출력 디렉토리 설정
        if output_dir is None and self.project_path:
            output_dir = self.project_path / "images" / "characters"
        elif output_dir is None:
            output_dir = Path("images/characters")

        output_dir.mkdir(parents=True, exist_ok=True)

        # Rate limit 대기 (Free 모델)
        if "Free" in config.model:
            elapsed = time.time() - self._last_request_time
            if elapsed < 6:
                wait_time = 6 - elapsed
                print(f"  [Rate limit] {wait_time:.1f}초 대기...")
                time.sleep(wait_time)

        try:
            start_time = time.time()

            # 이미지 생성
            img_data = self.image_client.generate_image(
                prompt=prompt,
                model=config.model,
                width=config.width,
                height=config.height
            )

            self._last_request_time = time.time()
            gen_time = self._last_request_time - start_time

            # 파일명 생성 (안전한 이름)
            safe_name = "".join(c if c.isalnum() or c in "_-" else "_" for c in char_name)
            timestamp = int(time.time() * 1000)
            filename = f"char_{safe_name}_{config.pose}_{timestamp}.png"
            filepath = output_dir / filename

            # 저장
            with open(filepath, "wb") as f:
                f.write(img_data)

            print(f"  완료! ({gen_time:.1f}초) -> {filepath}")

            return {
                "success": True,
                "character_name": char_name,
                "image_path": str(filepath),
                "image_url": str(filepath),  # 로컬 경로를 URL로도 사용
                "prompt": prompt,
                "pose": config.pose,
                "background": config.background,
                "generation_time": gen_time
            }

        except Exception as e:
            print(f"  실패: {str(e)}")
            return {
                "success": False,
                "character_name": char_name,
                "prompt": prompt,
                "error": str(e)
            }

    def generate_batch(
        self,
        characters: List[Dict],
        config: CharacterImageConfig = None,
        output_dir: Path = None,
        on_progress=None
    ) -> List[Dict]:
        """
        여러 캐릭터 이미지 배치 생성

        Args:
            characters: 캐릭터 목록
            config: 생성 설정
            output_dir: 출력 디렉토리
            on_progress: 진행 콜백 (current, total, result)

        Returns:
            결과 목록
        """
        if config is None:
            config = CharacterImageConfig()

        results = []
        total = len(characters)

        print(f"\n{'='*50}")
        print(f"캐릭터 이미지 배치 생성: {total}명")
        print(f"{'='*50}\n")

        for i, char in enumerate(characters):
            result = self.generate_character_image(char, config, output_dir)
            results.append(result)

            if on_progress:
                on_progress(i + 1, total, result)

        success_count = sum(1 for r in results if r.get("success"))
        print(f"\n완료: {success_count}/{total} 성공\n")

        return results

    def generate_multiple_poses(
        self,
        character: Dict,
        poses: List[str],
        config: CharacterImageConfig = None,
        output_dir: Path = None
    ) -> List[Dict]:
        """
        한 캐릭터의 여러 포즈 이미지 생성

        Args:
            character: 캐릭터 정보
            poses: 포즈 목록 ["standing", "walking", ...]
            config: 생성 설정
            output_dir: 출력 디렉토리

        Returns:
            결과 목록
        """
        if config is None:
            config = CharacterImageConfig()

        results = []

        for pose in poses:
            pose_config = CharacterImageConfig(
                style=config.style,
                pose=pose,
                background=config.background,
                width=config.width,
                height=config.height,
                model=config.model,
                style_prefix=config.style_prefix,
                style_suffix=config.style_suffix
            )

            result = self.generate_character_image(character, pose_config, output_dir)
            results.append(result)

        return results
