"""
캐릭터 관리 시스템

주요 기능:
1. 캐릭터 CRUD (생성, 조회, 수정, 삭제)
2. 캐릭터 프롬프트 관리
3. 캐릭터 이미지 생성 및 저장
4. 캐릭터 라이브러리
"""
import json
import re
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict, field
from datetime import datetime


# ============================================================
# 🔴 캐릭터 이름 유효성 검증 (Problem 49)
# ============================================================

INVALID_CHARACTER_WORDS = {
    '의', '이', '가', '은', '는', '를', '을', '에서', '로', '으로',
    '회사', '기업', '브랜드', '제품', '서비스', '시장', '산업',
    '대표', '회장', '사장', '이사', '임원', '창업자', '설립자',
    '한국', '미국', '중국', '일본', '사우디', '유럽', '아시아',
    '하는', '되는', '있는', '없는', '같은', '다른', '모든',
}

# 🔴 v3.74: 유효한 직업/역할 캐릭터 이름 화이트리스트
VALID_ROLE_NAMES = {
    # 직업명 (가로 끝나는 이름들)
    '사업가', '작가', '음악가', '투자가', '정치가', '과학자', '화가',
    '건축가', '무용가', '소설가', '시인', '배우', '가수', '모델',
    # 일반적인 역할/호칭
    '아버지', '어머니', '할머니', '할아버지', '동생', '언니', '오빠', '누나', '형',
    '아들', '딸', '며느리', '사위', '손자', '손녀',
    # 직책/직위
    '기자', '의사', '변호사', '검사', '판사', '교수', '선생님', '학생',
    '비서', '경호원', '운전사', '요리사', '간호사',
    # 일반적인 역할
    '친구', '동료', '상사', '부하', '조수', '제자', '스승',
    '이웃', '손님', '점원', '직원', '고객',
}


def is_valid_character_name(name: str) -> bool:
    """
    유효한 캐릭터 이름인지 검증 (v3.76 - 관대한 버전)

    v3.76: 긴 한글 이름 허용
      - 기존: len(name) > 10 필터링 → "역경을 딛고 일어서는 사람" 제외됨
      - 수정: len(name) > 50 으로 변경 (사실상 무제한)
      - 한글+공백 조합 허용 확대

    유효한 이름:
    - 한글 이름: "관객", "이재용"
    - 공백 포함 역할명: "자동차 회사 임원", "역경을 딛고 일어서는 사람"
    - 영문 이름: "John", "Main Character"

    무효한 이름:
    - 숫자만: "0", "1", "123"
    - 자음/모음만: "ㄱㄴㄷ", "ㅏㅓㅗ"
    - 빈 문자열
    """
    if not name:
        return False

    name_clean = name.strip()

    # 🔴 v3.76: 길이 제한 완화 (10 → 50)
    # "역경을 딛고 일어서는 사람" (12자) 허용
    if len(name_clean) < 2 or len(name_clean) > 50:
        return False

    name_lower = name_clean.lower()

    # 🔴 v3.74: 화이트리스트 먼저 체크 - 유효한 역할/직업명은 바로 허용
    if name_clean in VALID_ROLE_NAMES:
        return True

    if name_lower in INVALID_CHARACTER_WORDS:
        return False

    # 숫자만 있는 경우 필터링
    if name_clean.isdigit():
        return False

    # 자음/모음만 있는 경우 필터링
    if re.match(r'^[ㄱ-ㅎㅏ-ㅣ]+$', name_clean):
        return False

    # 🔴 v3.76: 한글+공백 조합은 먼저 허용 (긴 역할명 대응)
    # "역경을 딛고 일어서는 사람", "자동차 회사 임원" 등
    if re.match(r'^[가-힣]+(\s+[가-힣]+)+$', name_clean):
        # 공백 포함 한글 구문은 거의 모두 허용
        # 단, 명백한 문장 어미로 끝나는 경우만 제외
        obvious_sentence_endings = ['습니다', '입니다', '네요', '군요', '해요', '하죠']
        for ending in obvious_sentence_endings:
            if name_clean.endswith(ending):
                return False
        return True  # 🔴 긴 한글 역할명 허용!

    # 문장 어미 패턴 감지 (공백 없는 긴 문자열에 대해)
    sentence_endings = [
        '면', '해서', '니까', '으니', '지만', '으면', '어서', '아서',
        '다', '요', '습니다', '입니다', '네요', '군요',
    ]

    if ' ' in name_clean and len(name_clean) >= 4:
        for ending in sentence_endings:
            if name_clean.endswith(ending):
                return False

    # 동사/형용사 패턴 감지 (5글자 이상, 공백 없는 경우만)
    if len(name_clean) >= 5 and ' ' not in name_clean:
        verb_patterns = [
            r'[가-힣]+(하|되|이|지|시|았|었|겠|는|ㄴ|을|를|한|된|인)$',
            r'[가-힣]+(해서|해야|하면|하고|하는|했다|했음|하여)$',
            r'[가-힣]+(으면|면서|니까|지만|어서|아서|라서|려고)$',
        ]
        for pattern in verb_patterns:
            if re.search(pattern, name_clean):
                return False

    # 조사로 끝나는지 체크 (공백 없는 경우만)
    # 🔴 v3.74: '가'로 끝나는 직업/역할명 허용 (사업가, 작가, 음악가 등)
    if ' ' not in name_clean:
        particle_endings = ['의', '이', '가', '은', '는', '를', '을', '에', '로', '과', '와', '도']
        for particle in particle_endings:
            if name_clean.endswith(particle) and len(name_clean) > 2:
                # '의'로 끝나는 3글자 한글 이름 허용 (예: 김철의)
                if particle == '의' and len(name_clean) == 3 and re.match(r'^[가-힣]{3}$', name_clean):
                    continue
                # 🔴 v3.74: '가'로 끝나는 2-4글자 한글 이름/직업명 허용 (예: 사업가, 작가, 음악가)
                if particle == '가' and len(name_clean) >= 2 and re.match(r'^[가-힣]{2,4}$', name_clean):
                    continue
                return False

    # 유효한 이름 패턴
    if re.match(r'^[가-힣]{2,4}$', name_clean):
        return True

    # 🔴 v3.77: 영어 이름 패턴 확장 - 숫자 포함 허용
    # 기존: r'^[A-Z][a-z]+(\s+[A-Z][a-z]+)+$' → "Executive 1" 실패
    # 수정: 숫자, 단일 단어, 다양한 조합 허용
    # 예: "Executive 1", "Executive 2", "John", "Main Character", "Person 3"
    if re.match(r'^[A-Za-z][A-Za-z0-9]*(\s+[A-Za-z0-9]+)*$', name_clean):
        return True

    # 🔴 v3.76: 한글이 포함된 짧은 이름 허용 범위 확대 (5 → 20자)
    if len(name_clean) <= 20 and re.search(r'[가-힣]', name_clean):
        return True

    return False


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
    # 🔴 v3.78: 이미지 선택 기능
    selected_image_path: str = ""  # 현재 적용 중인 이미지 경로 (비어있으면 최신 이미지)
    auto_select_latest: bool = True  # 새 이미지 생성 시 자동으로 최신 선택
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        self.updated_at = datetime.now().isoformat()

    def get_selected_image(self) -> Optional[str]:
        """
        현재 선택된 (적용 중인) 이미지 경로 반환

        Returns:
            선택된 이미지 경로, 없으면 최신 이미지, 그것도 없으면 None
        """
        # 명시적으로 선택된 이미지가 있고 존재하면 반환
        if self.selected_image_path and Path(self.selected_image_path).exists():
            return self.selected_image_path

        # 생성된 이미지가 있으면 최신(마지막) 이미지 반환
        if self.generated_images:
            for img_path in reversed(self.generated_images):
                if Path(img_path).exists():
                    return img_path

        return None

    def select_image(self, image_path: str) -> bool:
        """
        특정 이미지를 적용 이미지로 선택

        Args:
            image_path: 선택할 이미지 경로

        Returns:
            성공 여부
        """
        if image_path in self.generated_images and Path(image_path).exists():
            self.selected_image_path = image_path
            self.auto_select_latest = False  # 수동 선택 시 자동 선택 비활성화
            self.updated_at = datetime.now().isoformat()
            return True
        return False

    def is_image_selected(self, image_path: str) -> bool:
        """특정 이미지가 현재 선택된 이미지인지 확인"""
        selected = self.get_selected_image()
        if selected:
            return Path(selected).resolve() == Path(image_path).resolve()
        return False


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

    def import_from_analysis(self, analysis_characters: List[Dict], validate: bool = True) -> int:
        """
        씬 분석 결과에서 캐릭터 가져오기

        Args:
            analysis_characters: 분석된 캐릭터 데이터 리스트
            validate: True면 유효한 캐릭터 이름만 가져옴 (Problem 49)

        Returns:
            가져온 캐릭터 수
        """
        imported = 0
        filtered = 0

        for char_data in analysis_characters:
            # 문자열인 경우 딕셔너리로 변환
            if isinstance(char_data, str):
                char_data = {"name": char_data, "name_ko": char_data}

            # 이미 존재하는지 확인
            name = char_data.get("name", char_data.get("name_ko", ""))
            if not name:
                continue

            # 🔴 유효성 검증 (Problem 49)
            if validate and not is_valid_character_name(name):
                filtered += 1
                print(f"[CharacterManager] ❌ 유효하지 않은 캐릭터 이름 필터링: '{name}'")
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

        if filtered > 0:
            print(f"[CharacterManager] ⚠️ {filtered}개의 유효하지 않은 캐릭터 이름 필터링됨")

        return imported

    def add_generated_image(self, character_id: str, image_path: str):
        """
        캐릭터에 생성된 이미지 추가

        v3.78: auto_select_latest가 True이면 새 이미지를 자동 선택
        """
        char = self.get_character(character_id)
        if char:
            if image_path not in char.generated_images:
                char.generated_images.append(image_path)

                # 🔴 v3.78: 자동 최신 선택이 켜져 있으면 새 이미지를 선택
                if char.auto_select_latest:
                    char.selected_image_path = image_path
                    print(f"[CharacterManager] ✅ '{char.name}' 이미지 자동 선택: {Path(image_path).name}")

                char.updated_at = datetime.now().isoformat()
                self._save_characters()

    # ═══════════════════════════════════════════════════════════════════
    # 🔴 v3.78: 이미지 선택 기능
    # ═══════════════════════════════════════════════════════════════════

    def select_character_image(self, character_id: str, image_path: str) -> bool:
        """
        캐릭터의 적용 이미지를 수동으로 선택

        Args:
            character_id: 캐릭터 ID
            image_path: 선택할 이미지 경로

        Returns:
            성공 여부
        """
        char = self.get_character(character_id)
        if char and char.select_image(image_path):
            self._save_characters()
            print(f"[CharacterManager] ✅ '{char.name}' 이미지 수동 선택: {Path(image_path).name}")
            return True
        return False

    def get_character_selected_image(self, character_id: str) -> Optional[str]:
        """
        캐릭터의 현재 선택된 이미지 경로 반환

        Args:
            character_id: 캐릭터 ID

        Returns:
            선택된 이미지 경로 또는 None
        """
        char = self.get_character(character_id)
        if char:
            return char.get_selected_image()
        return None

    def set_auto_select_latest(self, character_id: str, enabled: bool) -> bool:
        """
        자동 최신 선택 설정 변경

        Args:
            character_id: 캐릭터 ID
            enabled: 자동 선택 활성화 여부

        Returns:
            성공 여부
        """
        char = self.get_character(character_id)
        if char:
            char.auto_select_latest = enabled

            # 켜지면 즉시 최신 이미지 선택
            if enabled and char.generated_images:
                # 최신(마지막) 이미지 선택
                for img_path in reversed(char.generated_images):
                    if Path(img_path).exists():
                        char.selected_image_path = img_path
                        break

            char.updated_at = datetime.now().isoformat()
            self._save_characters()
            print(f"[CharacterManager] '{char.name}' 자동 선택: {'켜짐' if enabled else '꺼짐'}")
            return True
        return False

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
