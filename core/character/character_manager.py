"""
캐릭터 관리 시스템

주요 기능:
1. 캐릭터 CRUD (생성, 조회, 수정, 삭제)
2. 캐릭터 프롬프트 관리
3. 캐릭터 이미지 생성 및 저장
4. 캐릭터 라이브러리
"""
import json
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict, field
from datetime import datetime


@dataclass
class Character:
    """캐릭터 데이터 클래스"""
    id: str
    name: str
    name_en: str
    description: str
    role: str = "주연"
    nationality: str = ""
    era: str = "현대"
    appearance: str = ""
    character_prompt: str = ""
    reference_urls: List[str] = field(default_factory=list)
    generated_images: List[str] = field(default_factory=list)
    appearance_scenes: List[int] = field(default_factory=list)  # 🔴 v3.12: 등장 씬 목록 추가
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        self.updated_at = datetime.now().isoformat()


class CharacterManager:
    """캐릭터 관리자"""

    def __init__(self, project_path: str):
        self.project_path = Path(project_path)
        self.characters_dir = self.project_path / "characters"
        self.characters_dir.mkdir(parents=True, exist_ok=True)
        self.characters_file = self.characters_dir / "characters.json"
        self.characters: List[Character] = []
        self._load_characters()

    def _load_characters(self):
        """저장된 캐릭터 로드"""
        if self.characters_file.exists():
            try:
                with open(self.characters_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                    # 🔴 v3.12: 필드 호환성 처리
                    valid_fields = {f.name for f in Character.__dataclass_fields__.values()}
                    self.characters = []

                    for c in data:
                        # 알려진 필드만 사용 (새 필드 추가 시 호환성 유지)
                        filtered = {k: v for k, v in c.items() if k in valid_fields}
                        self.characters.append(Character(**filtered))

            except (json.JSONDecodeError, TypeError) as e:
                print(f"[CharacterManager] 캐릭터 로드 오류: {e}")
                self.characters = []

    def _save_characters(self):
        """캐릭터 저장"""
        with open(self.characters_file, "w", encoding="utf-8") as f:
            data = [asdict(c) for c in self.characters]
            json.dump(data, f, ensure_ascii=False, indent=2)

    def add_character(self, character: Character) -> Character:
        """캐릭터 추가"""
        # ID 중복 체크
        existing_ids = [c.id for c in self.characters]
        if character.id in existing_ids:
            character.id = f"{character.id}_{len(existing_ids)}"

        self.characters.append(character)
        self._save_characters()
        return character

    def get_character(self, character_id: str) -> Optional[Character]:
        """캐릭터 조회"""
        for c in self.characters:
            if c.id == character_id:
                return c
        return None

    def get_character_by_name(self, name: str) -> Optional[Character]:
        """이름으로 캐릭터 조회"""
        for c in self.characters:
            if c.name == name or c.name_en == name:
                return c
        return None

    def update_character(self, character_id: str, updates: Dict) -> Optional[Character]:
        """캐릭터 수정"""
        for i, c in enumerate(self.characters):
            if c.id == character_id:
                for key, value in updates.items():
                    if hasattr(c, key):
                        setattr(c, key, value)
                c.updated_at = datetime.now().isoformat()
                self._save_characters()
                return c
        return None

    def delete_character(self, character_id: str) -> bool:
        """캐릭터 삭제"""
        for i, c in enumerate(self.characters):
            if c.id == character_id:
                self.characters.pop(i)
                self._save_characters()
                return True
        return False

    def get_all_characters(self) -> List[Character]:
        """모든 캐릭터 조회"""
        return self.characters

    def import_from_analysis(self, analysis_characters: List[Dict]) -> int:
        """씬 분석 결과에서 캐릭터 가져오기"""
        imported = 0
        for char_data in analysis_characters:
            # 문자열인 경우 딕셔너리로 변환
            if isinstance(char_data, str):
                char_data = {"name": char_data, "name_ko": char_data}

            # 이미 존재하는지 확인
            name = char_data.get("name", char_data.get("name_ko", ""))
            if not name:
                continue

            existing = self.get_character_by_name(name)
            if existing:
                continue

            # ID 생성
            name_en = char_data.get("name_en", "")
            char_id = name_en.lower().replace(" ", "_") if name_en else f"char_{len(self.characters)}"

            # character_prompt 또는 visual_prompt 사용 (둘 다 지원)
            prompt = (
                char_data.get("character_prompt") or
                char_data.get("visual_prompt") or
                char_data.get("prompt") or
                ""
            )

            # 🔴 v3.12: appearance_scenes 추출
            appearance_scenes = char_data.get("appearance_scenes", [])
            # 정수 리스트로 변환
            appearance_scenes = [int(s) for s in appearance_scenes if isinstance(s, (int, str)) and str(s).isdigit()]

            character = Character(
                id=char_id,
                name=name,
                name_en=name_en,
                description=char_data.get("description", ""),
                role=char_data.get("role", "주연"),
                nationality=char_data.get("nationality", ""),
                era=char_data.get("era", "현대"),
                appearance=char_data.get("appearance", ""),
                character_prompt=prompt,
                appearance_scenes=appearance_scenes  # 🔴 등장 씬 목록 추가
            )
            self.add_character(character)
            imported += 1
            print(f"[CharacterManager] 캐릭터 '{name}' 가져옴 (prompt={bool(prompt)}, scenes={appearance_scenes})")

        return imported

    def add_generated_image(self, character_id: str, image_path: str):
        """캐릭터에 생성된 이미지 추가"""
        char = self.get_character(character_id)
        if char:
            if image_path not in char.generated_images:
                char.generated_images.append(image_path)
                self._save_characters()

    def get_character_prompt_for_scene(self, character_names: List[str]) -> str:
        """씬에 등장하는 캐릭터들의 프롬프트 조합"""
        prompts = []
        for name in character_names:
            char = self.get_character_by_name(name)
            if char and char.character_prompt:
                prompts.append(char.character_prompt)
        return ", ".join(prompts)

    def export_to_dict(self) -> List[Dict]:
        """캐릭터 목록을 딕셔너리로 내보내기"""
        return [asdict(c) for c in self.characters]

    def sync_appearance_scenes(self, analysis_characters: List[Dict]) -> int:
        """
        🔴 v3.12: 씬 분석 결과에서 등장 씬 정보 동기화

        기존 캐릭터의 appearance_scenes를 분석 결과에서 업데이트합니다.

        Args:
            analysis_characters: 분석 결과의 캐릭터 목록

        Returns:
            업데이트된 캐릭터 수
        """
        updated = 0

        # 분석 결과에서 이름 → appearance_scenes 매핑 생성
        scene_map = {}
        for char_data in analysis_characters:
            if isinstance(char_data, str):
                continue

            name = char_data.get("name", char_data.get("name_ko", ""))
            scenes = char_data.get("appearance_scenes", [])

            if name and scenes:
                scene_map[name] = scenes

        # 기존 캐릭터 업데이트
        for char in self.characters:
            if char.name in scene_map:
                new_scenes = [int(s) for s in scene_map[char.name] if isinstance(s, (int, str)) and str(s).isdigit()]

                if new_scenes != char.appearance_scenes:
                    char.appearance_scenes = new_scenes
                    char.updated_at = datetime.now().isoformat()
                    updated += 1
                    print(f"[CharacterManager] '{char.name}' 등장 씬 업데이트: {new_scenes}")

        if updated > 0:
            self._save_characters()
            print(f"[CharacterManager] {updated}명의 캐릭터 등장 씬 동기화 완료")

        return updated
