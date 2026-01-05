# -*- coding: utf-8 -*-
"""
대표 캐릭터 라이브러리 관리자

여러 대표 캐릭터를 저장/로드하고 관리합니다.
- 캐릭터 CRUD (생성, 조회, 수정, 삭제)
- 캐릭터 선택 및 전환
- 썸네일 관리
- 검색 및 태그 필터링
"""

import os
import json
import shutil
import re
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Any

# 전역 라이브러리 경로
LIBRARY_PATH = Path(__file__).parent.parent / "data" / "rep_characters"
INDEX_FILE = LIBRARY_PATH / "index.json"


class RepCharacterLibrary:
    """대표 캐릭터 라이브러리 관리자"""

    _instance = None
    _initialized = False

    def __new__(cls):
        """싱글톤 패턴"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._ensure_library_dir()
        self._load_index()
        self._initialized = True
        print(f"[RepCharLibrary] 초기화 완료: {len(self._index.get('characters', []))}개 캐릭터")

    def _ensure_library_dir(self):
        """라이브러리 디렉토리 생성"""
        LIBRARY_PATH.mkdir(parents=True, exist_ok=True)

    def _load_index(self):
        """인덱스 파일 로드"""
        if INDEX_FILE.exists():
            try:
                with open(INDEX_FILE, 'r', encoding='utf-8') as f:
                    self._index = json.load(f)
                print(f"[RepCharLibrary] 인덱스 로드 완료")
            except Exception as e:
                print(f"[RepCharLibrary] 인덱스 로드 실패: {e}")
                self._index = self._create_default_index()
        else:
            self._index = self._create_default_index()
            self._save_index()

    def _create_default_index(self) -> dict:
        """기본 인덱스 구조 생성"""
        return {
            "version": "1.0",
            "characters": [],
            "last_selected_id": None,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }

    def _save_index(self):
        """인덱스 파일 저장"""
        try:
            self._index["updated_at"] = datetime.now().isoformat()
            with open(INDEX_FILE, 'w', encoding='utf-8') as f:
                json.dump(self._index, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[RepCharLibrary] 인덱스 저장 실패: {e}")

    def _generate_id(self) -> str:
        """고유 ID 생성"""
        existing_ids = [c["id"] for c in self._index.get("characters", [])]
        num = 1
        while f"char_{num:03d}" in existing_ids:
            num += 1
        return f"char_{num:03d}"

    def _sanitize_folder_name(self, name: str) -> str:
        """폴더명에 사용 가능한 문자열로 변환"""
        # 특수문자 제거, 공백을 언더스코어로
        sanitized = re.sub(r'[^\w가-힣\s]', '', name)
        sanitized = sanitized.replace(' ', '_')
        return sanitized[:20]  # 최대 20자

    def _create_thumbnail(self, source_path: str, dest_path: Path, size: tuple = (200, 200)):
        """썸네일 생성"""
        try:
            from PIL import Image
            with Image.open(source_path) as img:
                img.thumbnail(size, Image.Resampling.LANCZOS)
                # RGBA면 RGB로 변환 (JPEG 저장용)
                if img.mode == 'RGBA':
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    background.paste(img, mask=img.split()[3])
                    img = background
                img.save(dest_path)
            print(f"[RepCharLibrary] 썸네일 생성: {dest_path.name}")
        except Exception as e:
            print(f"[RepCharLibrary] 썸네일 생성 실패: {e}")

    # ===================================================================
    # 캐릭터 CRUD
    # ===================================================================

    def get_all_characters(self) -> List[Dict]:
        """모든 캐릭터 목록 반환 (인덱스 정보만)"""
        return self._index.get("characters", [])

    def get_character(self, char_id: str) -> Optional[Dict]:
        """특정 캐릭터 상세 정보 반환"""
        for char in self._index.get("characters", []):
            if char["id"] == char_id:
                # 상세 정보 로드
                char_folder = LIBRARY_PATH / char["folder"]
                char_file = char_folder / "character.json"

                if char_file.exists():
                    try:
                        with open(char_file, 'r', encoding='utf-8') as f:
                            return json.load(f)
                    except Exception as e:
                        print(f"[RepCharLibrary] 캐릭터 로드 실패 ({char_id}): {e}")
        return None

    def get_character_by_name(self, name: str) -> Optional[Dict]:
        """이름으로 캐릭터 조회"""
        for char in self._index.get("characters", []):
            if char["name"] == name:
                return self.get_character(char["id"])
        return None

    def create_character(
        self,
        name: str,
        description: str = "",
        prompt: str = "",
        negative_prompt: str = "text, watermark, low quality, blurry, deformed",
        style_preset: str = "",
        style_suffix: str = "",
        tags: List[str] = None,
        base_images: List[str] = None  # 이미지 경로 리스트
    ) -> str:
        """새 캐릭터 생성

        Args:
            name: 캐릭터 이름
            description: 간단한 설명
            prompt: 캐릭터 생성 프롬프트
            negative_prompt: 네거티브 프롬프트
            style_preset: 스타일 프리셋 ID
            style_suffix: 스타일 suffix
            tags: 태그 목록
            base_images: 기본 이미지 경로 목록

        Returns:
            생성된 캐릭터 ID
        """
        char_id = self._generate_id()
        folder_name = f"{char_id}_{self._sanitize_folder_name(name)}"
        char_folder = LIBRARY_PATH / folder_name
        char_folder.mkdir(parents=True, exist_ok=True)

        # 기본 이미지 복사
        base_images_data = []
        thumbnail_created = False

        if base_images:
            images_folder = char_folder / "base_images"
            images_folder.mkdir(exist_ok=True)

            for i, img_path in enumerate(base_images):
                if img_path and os.path.exists(img_path):
                    ext = Path(img_path).suffix or ".png"
                    new_name = f"image_{i+1:02d}{ext}"
                    new_path = images_folder / new_name
                    shutil.copy2(img_path, new_path)

                    base_images_data.append({
                        "type": f"image_{i+1}",
                        "path": f"base_images/{new_name}",
                        "generated_at": datetime.now().isoformat()
                    })

                    # 첫 번째 이미지를 썸네일로
                    if not thumbnail_created:
                        self._create_thumbnail(img_path, char_folder / "thumbnail.png")
                        thumbnail_created = True

        # 캐릭터 상세 정보 저장
        char_data = {
            "id": char_id,
            "name": name,
            "description": description,
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "style_preset": style_preset,
            "style_suffix": style_suffix,
            "base_images": base_images_data,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }

        with open(char_folder / "character.json", 'w', encoding='utf-8') as f:
            json.dump(char_data, f, ensure_ascii=False, indent=2)

        # 인덱스에 추가
        index_entry = {
            "id": char_id,
            "name": name,
            "description": description,
            "folder": folder_name,
            "thumbnail": "thumbnail.png" if thumbnail_created else None,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "tags": tags or [],
            "usage_count": 0
        }

        self._index["characters"].append(index_entry)
        self._save_index()

        print(f"[RepCharLibrary] ✅ 캐릭터 생성: {name} ({char_id})")
        return char_id

    def update_character(
        self,
        char_id: str,
        name: str = None,
        description: str = None,
        prompt: str = None,
        negative_prompt: str = None,
        style_preset: str = None,
        style_suffix: str = None,
        tags: List[str] = None
    ) -> bool:
        """캐릭터 정보 수정"""

        char = self.get_character(char_id)
        if not char:
            print(f"[RepCharLibrary] 캐릭터 없음: {char_id}")
            return False

        # 인덱스에서 찾기
        index_entry = None
        for entry in self._index.get("characters", []):
            if entry["id"] == char_id:
                index_entry = entry
                break

        if not index_entry:
            return False

        char_folder = LIBRARY_PATH / index_entry["folder"]

        # 업데이트
        if name is not None:
            char["name"] = name
            index_entry["name"] = name
        if description is not None:
            char["description"] = description
            index_entry["description"] = description
        if prompt is not None:
            char["prompt"] = prompt
        if negative_prompt is not None:
            char["negative_prompt"] = negative_prompt
        if style_preset is not None:
            char["style_preset"] = style_preset
        if style_suffix is not None:
            char["style_suffix"] = style_suffix
        if tags is not None:
            index_entry["tags"] = tags

        char["updated_at"] = datetime.now().isoformat()
        index_entry["updated_at"] = datetime.now().isoformat()

        # 저장
        with open(char_folder / "character.json", 'w', encoding='utf-8') as f:
            json.dump(char, f, ensure_ascii=False, indent=2)

        self._save_index()

        print(f"[RepCharLibrary] ✅ 캐릭터 수정: {char_id}")
        return True

    def delete_character(self, char_id: str) -> bool:
        """캐릭터 삭제"""

        index_entry = None
        index_pos = -1

        for i, entry in enumerate(self._index.get("characters", [])):
            if entry["id"] == char_id:
                index_entry = entry
                index_pos = i
                break

        if not index_entry:
            return False

        # 폴더 삭제
        char_folder = LIBRARY_PATH / index_entry["folder"]
        if char_folder.exists():
            shutil.rmtree(char_folder)

        # 인덱스에서 제거
        self._index["characters"].pop(index_pos)

        # 선택된 캐릭터였다면 해제
        if self._index.get("last_selected_id") == char_id:
            self._index["last_selected_id"] = None

        self._save_index()

        print(f"[RepCharLibrary] ✅ 캐릭터 삭제: {char_id}")
        return True

    def duplicate_character(self, char_id: str, new_name: str = None) -> Optional[str]:
        """캐릭터 복제"""

        char = self.get_character(char_id)
        if not char:
            return None

        # 새 이름
        if not new_name:
            new_name = f"{char['name']} (복사본)"

        # 인덱스에서 원본 찾기
        index_entry = None
        for entry in self._index.get("characters", []):
            if entry["id"] == char_id:
                index_entry = entry
                break

        # 기본 이미지 경로 수집
        base_image_paths = []
        if index_entry:
            char_folder = LIBRARY_PATH / index_entry["folder"]
            for img in char.get("base_images", []):
                img_path = char_folder / img["path"]
                if img_path.exists():
                    base_image_paths.append(str(img_path))

        # 새 캐릭터 생성
        new_id = self.create_character(
            name=new_name,
            description=char.get("description", ""),
            prompt=char.get("prompt", ""),
            negative_prompt=char.get("negative_prompt", ""),
            style_preset=char.get("style_preset", ""),
            style_suffix=char.get("style_suffix", ""),
            tags=index_entry.get("tags", []) if index_entry else [],
            base_images=base_image_paths
        )

        print(f"[RepCharLibrary] ✅ 캐릭터 복제: {char_id} → {new_id}")
        return new_id

    # ===================================================================
    # 캐릭터 선택
    # ===================================================================

    def select_character(self, char_id: str) -> bool:
        """캐릭터 선택"""

        # 존재 확인
        exists = any(c["id"] == char_id for c in self._index.get("characters", []))
        if not exists:
            print(f"[RepCharLibrary] 캐릭터 없음: {char_id}")
            return False

        self._index["last_selected_id"] = char_id

        # 사용 횟수 증가
        for char in self._index.get("characters", []):
            if char["id"] == char_id:
                char["usage_count"] = char.get("usage_count", 0) + 1
                break

        self._save_index()

        print(f"[RepCharLibrary] ✅ 캐릭터 선택: {char_id}")
        return True

    def get_selected_character(self) -> Optional[Dict]:
        """현재 선택된 캐릭터 반환 (상세 정보)"""
        selected_id = self._index.get("last_selected_id")
        if selected_id:
            return self.get_character(selected_id)
        return None

    def get_selected_character_id(self) -> Optional[str]:
        """현재 선택된 캐릭터 ID 반환"""
        return self._index.get("last_selected_id")

    def get_selected_character_index_entry(self) -> Optional[Dict]:
        """현재 선택된 캐릭터 인덱스 항목 반환"""
        selected_id = self._index.get("last_selected_id")
        if selected_id:
            for char in self._index.get("characters", []):
                if char["id"] == selected_id:
                    return char
        return None

    # ===================================================================
    # 이미지 관리
    # ===================================================================

    def get_thumbnail_path(self, char_id: str) -> Optional[str]:
        """캐릭터 썸네일 경로 반환"""
        for char in self._index.get("characters", []):
            if char["id"] == char_id:
                if char.get("thumbnail"):
                    path = LIBRARY_PATH / char["folder"] / char["thumbnail"]
                    if path.exists():
                        return str(path)
        return None

    def get_base_image_paths(self, char_id: str) -> List[str]:
        """캐릭터 기본 이미지 경로 목록 반환"""
        char = self.get_character(char_id)
        if not char:
            return []

        index_entry = None
        for entry in self._index.get("characters", []):
            if entry["id"] == char_id:
                index_entry = entry
                break

        if not index_entry:
            return []

        char_folder = LIBRARY_PATH / index_entry["folder"]
        paths = []

        for img in char.get("base_images", []):
            img_path = char_folder / img["path"]
            if img_path.exists():
                paths.append(str(img_path))

        return paths

    def add_base_image(self, char_id: str, image_path: str, image_type: str = None) -> bool:
        """기본 이미지 추가"""

        char = self.get_character(char_id)
        if not char:
            return False

        index_entry = None
        for entry in self._index.get("characters", []):
            if entry["id"] == char_id:
                index_entry = entry
                break

        if not index_entry:
            return False

        char_folder = LIBRARY_PATH / index_entry["folder"]
        images_folder = char_folder / "base_images"
        images_folder.mkdir(exist_ok=True)

        # 새 이미지 복사
        existing_count = len(char.get("base_images", []))
        ext = Path(image_path).suffix or ".png"
        new_name = f"image_{existing_count + 1:02d}{ext}"
        new_path = images_folder / new_name
        shutil.copy2(image_path, new_path)

        # 데이터 업데이트
        if "base_images" not in char:
            char["base_images"] = []

        char["base_images"].append({
            "type": image_type or f"image_{existing_count + 1}",
            "path": f"base_images/{new_name}",
            "generated_at": datetime.now().isoformat()
        })

        char["updated_at"] = datetime.now().isoformat()

        # 저장
        with open(char_folder / "character.json", 'w', encoding='utf-8') as f:
            json.dump(char, f, ensure_ascii=False, indent=2)

        # 썸네일 없으면 생성
        if not index_entry.get("thumbnail"):
            self._create_thumbnail(image_path, char_folder / "thumbnail.png")
            index_entry["thumbnail"] = "thumbnail.png"
            self._save_index()

        print(f"[RepCharLibrary] ✅ 이미지 추가: {char_id}")
        return True

    def update_thumbnail(self, char_id: str, image_path: str) -> bool:
        """썸네일 업데이트"""
        index_entry = None
        for entry in self._index.get("characters", []):
            if entry["id"] == char_id:
                index_entry = entry
                break

        if not index_entry:
            return False

        char_folder = LIBRARY_PATH / index_entry["folder"]
        self._create_thumbnail(image_path, char_folder / "thumbnail.png")
        index_entry["thumbnail"] = "thumbnail.png"
        self._save_index()

        return True

    # ===================================================================
    # 검색 및 필터링
    # ===================================================================

    def search_characters(self, query: str) -> List[Dict]:
        """캐릭터 검색"""
        if not query:
            return self.get_all_characters()

        query = query.lower()
        results = []

        for char in self._index.get("characters", []):
            if (query in char["name"].lower() or
                query in char.get("description", "").lower() or
                any(query in tag.lower() for tag in char.get("tags", []))):
                results.append(char)

        return results

    def get_characters_by_tag(self, tag: str) -> List[Dict]:
        """태그로 캐릭터 필터링"""
        return [
            char for char in self._index.get("characters", [])
            if tag.lower() in [t.lower() for t in char.get("tags", [])]
        ]

    def get_all_tags(self) -> List[str]:
        """모든 태그 목록 반환"""
        tags = set()
        for char in self._index.get("characters", []):
            for tag in char.get("tags", []):
                tags.add(tag)
        return sorted(list(tags))

    # ===================================================================
    # 마이그레이션
    # ===================================================================

    def migrate_from_old_format(self, old_data: Dict, project_path: str = None) -> Optional[str]:
        """
        기존 RepresentativeCharacter 형식에서 마이그레이션

        Args:
            old_data: 기존 캐릭터 데이터 (RepresentativeCharacter.to_dict())
            project_path: 프로젝트 경로 (기본 이미지 경로 해석용)

        Returns:
            새로 생성된 캐릭터 ID
        """
        if not old_data:
            return None

        name = old_data.get("name", "마이그레이션된 캐릭터")

        # 이미 같은 이름의 캐릭터가 있으면 스킵
        if self.get_character_by_name(name):
            print(f"[RepCharLibrary] 이미 존재하는 캐릭터: {name}")
            return None

        # 기본 이미지 경로 수집
        base_images = []
        old_base_images = old_data.get("base_images", {})

        if isinstance(old_base_images, dict):
            for img_type, img_path in old_base_images.items():
                if img_path and os.path.exists(img_path):
                    base_images.append(img_path)
                elif project_path:
                    full_path = Path(project_path) / img_path
                    if full_path.exists():
                        base_images.append(str(full_path))

        # 새 캐릭터 생성
        new_id = self.create_character(
            name=name,
            description=old_data.get("description", ""),
            prompt=old_data.get("base_prompt", ""),
            negative_prompt=old_data.get("negative_prompt", ""),
            style_preset=old_data.get("style_preset", ""),
            base_images=base_images
        )

        print(f"[RepCharLibrary] ✅ 마이그레이션 완료: {name} → {new_id}")
        return new_id


# ===================================================================
# 전역 인스턴스 및 헬퍼 함수
# ===================================================================

def get_rep_char_library() -> RepCharacterLibrary:
    """RepCharacterLibrary 싱글톤 인스턴스 반환"""
    return RepCharacterLibrary()


def get_selected_rep_char() -> Optional[Dict]:
    """현재 선택된 대표 캐릭터 반환 (단축 함수)"""
    return get_rep_char_library().get_selected_character()


def get_selected_rep_char_id() -> Optional[str]:
    """현재 선택된 대표 캐릭터 ID 반환 (단축 함수)"""
    return get_rep_char_library().get_selected_character_id()
