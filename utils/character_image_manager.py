"""
캐릭터 이미지 관리 유틸리티 (v2.0 - 캐싱 최적화)

기능:
- 이미지 목록 조회
- 전체/개별 선택
- 일괄 삭제
- 대표 이미지 관리 (최신 이미지 자동 대표)

v2.0 변경사항:
- 클래스 레벨 캐싱 추가 (중복 호출 방지)
- 씬-캐릭터 연동 결과 캐싱
- 로그 출력 최소화 (캐시 히트 시 무출력)
"""

import os
import json
import shutil
import re
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Tuple


class CharacterImageManager:
    # ═══════════════════════════════════════════════════════════════════
    # 클래스 레벨 캐시 (v2.0)
    # ═══════════════════════════════════════════════════════════════════
    _instance_cache = {}          # 프로젝트별 인스턴스 캐시
    _scene_link_cache = {}        # 씬-캐릭터 연동 결과 캐시
    _all_images_cache = {}        # 전체 이미지 목록 캐시
    _cache_timestamp = {}         # 캐시 타임스탬프
    CACHE_TTL = 60                # 캐시 유효 시간 (초)

    @classmethod
    def get_instance(cls, project_path: str) -> 'CharacterImageManager':
        """싱글톤 패턴 - 프로젝트별 인스턴스 재사용"""
        if project_path not in cls._instance_cache:
            cls._instance_cache[project_path] = cls(project_path)
        return cls._instance_cache[project_path]

    @classmethod
    def clear_all_caches(cls):
        """모든 캐시 초기화"""
        cls._instance_cache.clear()
        cls._scene_link_cache.clear()
        cls._all_images_cache.clear()
        cls._cache_timestamp.clear()
        print("[CharImageManager] 모든 캐시 초기화됨")

    @classmethod
    def is_cache_valid(cls, cache_key: str) -> bool:
        """캐시 유효성 확인"""
        import time
        if cache_key not in cls._cache_timestamp:
            return False
        elapsed = time.time() - cls._cache_timestamp[cache_key]
        return elapsed < cls.CACHE_TTL
    """캐릭터 이미지 관리자"""

    def __init__(self, project_path: str):
        """
        Args:
            project_path: 프로젝트 경로
        """
        self.project_path = Path(project_path)
        self.characters_dir = self.project_path / "characters"
        self.images_dir = self.project_path / "images" / "characters"
        self.analysis_file = self.project_path / "analysis" / "characters.json"
        self.char_data_file = self.project_path / "characters" / "characters.json"

        # 디렉토리 확인
        self.characters_dir.mkdir(parents=True, exist_ok=True)
        self.images_dir.mkdir(parents=True, exist_ok=True)

    def get_all_character_images(self, use_cache: bool = True) -> List[Dict]:
        """
        모든 캐릭터 이미지 목록 조회 (v2.0: 캐싱 지원)

        Args:
            use_cache: 캐시 사용 여부 (기본 True)

        Returns:
            [
                {
                    "filename": "char_자말카슈크지_standing_1703001234.png",
                    "path": "full/path/to/image.png",
                    "character_name": "자말 카슈크지",
                    "pose": "standing",
                    "timestamp": 1703001234,
                    "created_at": "2024-12-27 10:30:45",
                    "size_bytes": 123456,
                    "is_representative": True
                },
                ...
            ]
        """
        import time

        # 캐시 확인
        cache_key = f"all_images_{self.project_path}"
        if use_cache and cache_key in CharacterImageManager._all_images_cache:
            if CharacterImageManager.is_cache_valid(cache_key):
                return CharacterImageManager._all_images_cache[cache_key]

        images = []

        # 여러 디렉토리에서 이미지 검색
        search_dirs = [
            self.images_dir,
            self.characters_dir,
            self.project_path / "images",
        ]

        for search_dir in search_dirs:
            if not search_dir.exists():
                continue

            # char_*.png 패턴 검색
            for img_file in search_dir.glob("char_*.png"):
                img_info = self._parse_image_filename(img_file)
                if img_info:
                    images.append(img_info)

            # 캐릭터 ID 기반 파일 검색 (예: char_001.png)
            for img_file in search_dir.glob("*.png"):
                if img_file.name.startswith("char_"):
                    continue  # 이미 처리됨

                # ID 기반 파일 처리
                img_info = self._parse_id_based_filename(img_file)
                if img_info:
                    images.append(img_info)

        # 중복 제거 (파일 경로 기준)
        seen = set()
        unique_images = []
        for img in images:
            if img["path"] not in seen:
                seen.add(img["path"])
                unique_images.append(img)

        # 타임스탬프 기준 정렬 (최신순)
        unique_images.sort(key=lambda x: x.get("timestamp", 0), reverse=True)

        # 대표 이미지 표시
        self._mark_representative_images(unique_images)

        # 캐시에 저장
        CharacterImageManager._all_images_cache[cache_key] = unique_images
        CharacterImageManager._cache_timestamp[cache_key] = time.time()

        return unique_images

    def _parse_image_filename(self, img_path: Path) -> Optional[Dict]:
        """
        이미지 파일명 파싱

        패턴들:
        - char_{캐릭터명}_{포즈}_{타임스탬프}.png
        - char_{캐릭터명}_{타임스탬프}.png
        """
        filename = img_path.name

        # 패턴 1: char_XXX_YYY_TIMESTAMP.png
        pattern1 = r"char_(.+?)_(\w+)_(\d{10,13})\.png"
        match = re.match(pattern1, filename)

        if match:
            char_name = match.group(1).replace("_", " ")
            pose = match.group(2)
            timestamp = int(match.group(3))
        else:
            # 패턴 2: char_XXX_TIMESTAMP.png
            pattern2 = r"char_(.+?)_(\d{10,13})\.png"
            match2 = re.match(pattern2, filename)

            if match2:
                char_name = match2.group(1).replace("_", " ")
                pose = "default"
                timestamp = int(match2.group(2))
            else:
                # 패턴 3: char_XXX.png (타임스탬프 없음 → 파일 수정 시간 사용)
                pattern3 = r"char_(.+?)\.png"
                match3 = re.match(pattern3, filename)

                if match3:
                    char_name = match3.group(1).replace("_", " ")
                    pose = "default"
                    timestamp = int(img_path.stat().st_mtime * 1000)
                else:
                    return None

        # 파일 정보
        try:
            stat = img_path.stat()
            size_bytes = stat.st_size
        except:
            size_bytes = 0

        # 타임스탬프 변환
        if timestamp > 1e12:  # 밀리초
            created_at = datetime.fromtimestamp(timestamp / 1000)
        else:  # 초
            created_at = datetime.fromtimestamp(timestamp)

        return {
            "filename": filename,
            "path": str(img_path.absolute()),
            "character_name": char_name,
            "pose": pose,
            "timestamp": timestamp,
            "created_at": created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "size_bytes": size_bytes,
            "is_representative": False
        }

    def _parse_id_based_filename(self, img_path: Path) -> Optional[Dict]:
        """
        ID 기반 파일명 파싱 (예: char_001.png → 캐릭터 데이터에서 이름 조회)
        """
        filename = img_path.name

        # 캐릭터 데이터 로드
        char_data = self._load_character_data()

        # 파일명에서 ID 추출
        stem = img_path.stem  # 확장자 제외

        # ID로 캐릭터 찾기
        char_name = None
        for char in char_data:
            if char.get("id") == stem or char.get("id") == filename:
                char_name = char.get("name", stem)
                break

        if not char_name:
            return None

        try:
            stat = img_path.stat()
            timestamp = int(stat.st_mtime * 1000)
            size_bytes = stat.st_size
        except:
            timestamp = 0
            size_bytes = 0

        created_at = datetime.fromtimestamp(timestamp / 1000)

        return {
            "filename": filename,
            "path": str(img_path.absolute()),
            "character_name": char_name,
            "pose": "default",
            "timestamp": timestamp,
            "created_at": created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "size_bytes": size_bytes,
            "is_representative": False
        }

    def _load_character_data(self) -> List[Dict]:
        """캐릭터 데이터 로드"""
        # characters/characters.json 먼저 시도
        if self.char_data_file.exists():
            try:
                with open(self.char_data_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except:
                pass

        # analysis/characters.json 시도
        if self.analysis_file.exists():
            try:
                with open(self.analysis_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except:
                pass

        return []

    def _mark_representative_images(self, images: List[Dict]):
        """각 캐릭터별 최신 이미지를 대표로 표시"""
        # 캐릭터별 그룹화
        char_groups = {}
        for img in images:
            char_name = img["character_name"]
            if char_name not in char_groups:
                char_groups[char_name] = []
            char_groups[char_name].append(img)

        # 각 그룹에서 최신(첫 번째)을 대표로
        for char_name, group in char_groups.items():
            # 이미 timestamp 기준 정렬됨 (최신순)
            if group:
                group[0]["is_representative"] = True

    def get_images_by_character(self, character_name: str) -> List[Dict]:
        """특정 캐릭터의 모든 이미지"""
        all_images = self.get_all_character_images()
        return [img for img in all_images if img["character_name"] == character_name]

    def get_representative_image(self, character_name: str) -> Optional[str]:
        """
        캐릭터의 대표 이미지 경로 반환 (최신 이미지)

        Returns:
            이미지 파일 경로 또는 None
        """
        images = self.get_images_by_character(character_name)
        if not images:
            return None

        # 최신 이미지 (첫 번째)
        return images[0]["path"]

    def delete_images(self, filenames: List[str]) -> Dict:
        """
        이미지 삭제

        Args:
            filenames: 삭제할 파일명 리스트

        Returns:
            {"deleted": [...], "failed": [...]}
        """
        result = {"deleted": [], "failed": []}

        all_images = self.get_all_character_images()
        path_map = {img["filename"]: img["path"] for img in all_images}

        for filename in filenames:
            if filename not in path_map:
                result["failed"].append({"filename": filename, "reason": "파일 없음"})
                continue

            try:
                file_path = Path(path_map[filename])
                if file_path.exists():
                    file_path.unlink()
                    result["deleted"].append(filename)
                    print(f"[캐릭터 이미지] 삭제됨: {filename}")
                else:
                    result["failed"].append({"filename": filename, "reason": "파일 없음"})
            except Exception as e:
                result["failed"].append({"filename": filename, "reason": str(e)})
                print(f"[캐릭터 이미지] 삭제 실패: {filename} - {e}")

        return result

    def delete_all_images(self) -> Dict:
        """모든 캐릭터 이미지 삭제"""
        all_images = self.get_all_character_images()
        filenames = [img["filename"] for img in all_images]
        return self.delete_images(filenames)

    def delete_old_images(self, character_name: str, keep_count: int = 1) -> Dict:
        """
        특정 캐릭터의 오래된 이미지 삭제 (최신 N개만 유지)

        Args:
            character_name: 캐릭터 이름
            keep_count: 유지할 이미지 수 (기본 1 = 대표만)

        Returns:
            삭제 결과
        """
        images = self.get_images_by_character(character_name)

        if len(images) <= keep_count:
            return {"deleted": [], "failed": []}

        # 최신 keep_count개 제외하고 삭제
        to_delete = [img["filename"] for img in images[keep_count:]]
        return self.delete_images(to_delete)

    def set_representative_image(self, character_name: str, filename: str) -> bool:
        """
        대표 이미지 수동 설정
        (파일을 가장 최신 타임스탬프로 복사)
        """
        images = self.get_images_by_character(character_name)

        target = None
        for img in images:
            if img["filename"] == filename:
                target = img
                break

        if not target:
            return False

        # 새 타임스탬프로 복사
        new_timestamp = int(datetime.now().timestamp() * 1000)
        old_path = Path(target["path"])

        # 새 파일명 생성
        safe_name = character_name.replace(" ", "_")
        new_filename = f"char_{safe_name}_{target['pose']}_{new_timestamp}.png"
        new_path = old_path.parent / new_filename

        try:
            shutil.copy2(old_path, new_path)
            print(f"[캐릭터 이미지] 대표 설정: {character_name} → {new_filename}")
            return True
        except Exception as e:
            print(f"[캐릭터 이미지] 대표 설정 실패: {e}")
            return False

    def update_character_data_with_latest_images(self) -> int:
        """
        캐릭터 데이터에 최신 이미지 경로 반영

        Returns:
            업데이트된 캐릭터 수
        """
        updated = 0

        # characters/characters.json 업데이트
        if self.char_data_file.exists():
            updated += self._update_json_file(self.char_data_file)

        return updated

    def _update_json_file(self, json_path: Path) -> int:
        """JSON 파일의 캐릭터 이미지 경로 업데이트"""
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                characters = json.load(f)
        except Exception as e:
            print(f"[캐릭터 이미지] JSON 로드 실패: {e}")
            return 0

        updated = 0

        for char in characters:
            char_name = char.get("name", "")
            if not char_name:
                continue

            latest_image = self.get_representative_image(char_name)

            if latest_image:
                # generated_images 리스트 업데이트 (최신을 맨 앞으로)
                if "generated_images" in char:
                    if latest_image not in char["generated_images"]:
                        char["generated_images"].insert(0, latest_image)
                        updated += 1
                else:
                    char["generated_images"] = [latest_image]
                    updated += 1

        if updated > 0:
            try:
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(characters, f, ensure_ascii=False, indent=2)
                print(f"[캐릭터 이미지] {updated}개 캐릭터 이미지 경로 업데이트됨")
            except Exception as e:
                print(f"[캐릭터 이미지] JSON 저장 실패: {e}")
                return 0

        return updated

    def get_statistics(self) -> Dict:
        """이미지 통계"""
        all_images = self.get_all_character_images()

        # 캐릭터별 이미지 수
        char_counts = {}
        total_size = 0

        for img in all_images:
            char_name = img["character_name"]
            char_counts[char_name] = char_counts.get(char_name, 0) + 1
            total_size += img.get("size_bytes", 0)

        return {
            "total_images": len(all_images),
            "total_characters": len(char_counts),
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "images_per_character": char_counts,
            "duplicates": sum(1 for c in char_counts.values() if c > 1)
        }

    def cleanup_duplicate_images(self, keep_count: int = 1) -> Dict:
        """
        모든 캐릭터의 중복 이미지 정리

        Args:
            keep_count: 캐릭터당 유지할 이미지 수

        Returns:
            삭제 결과
        """
        stats = self.get_statistics()

        total_result = {"deleted": [], "failed": []}

        for char_name, count in stats["images_per_character"].items():
            if count > keep_count:
                result = self.delete_old_images(char_name, keep_count=keep_count)
                total_result["deleted"].extend(result["deleted"])
                total_result["failed"].extend(result["failed"])

        # 대표 이미지 업데이트
        if total_result["deleted"]:
            self.update_character_data_with_latest_images()

        return total_result


    # ===================================================================
    # v3.28: 씬-캐릭터 이미지 연동 메서드
    # ===================================================================

    def find_character_image(self, character_name: str) -> Optional[Dict]:
        """
        캐릭터 이름으로 이미지 찾기 (유연한 매칭 지원)

        매칭 우선순위:
        1. 정확한 이름 매칭
        2. 정규화된 이름 매칭 (공백, 특수문자 무시)
        3. 부분 매칭 (포함 관계)
        4. 유사도 매칭 (60% 이상)

        Args:
            character_name: 캐릭터 이름 (예: "노동자")

        Returns:
            {
                "path": "full/path/to/image.png",
                "name": "노동자",
                "is_representative": True,
                "match_type": "exact" | "normalized" | "partial" | "similar"
            } 또는 None
        """
        if not character_name or not character_name.strip():
            return None

        character_name = character_name.strip()
        all_images = self.get_all_character_images()

        if not all_images:
            print(f"[CharImageManager] 캐릭터 이미지 없음 (전체 0개)")
            return None

        # 캐릭터별로 그룹화
        char_groups = {}
        for img in all_images:
            name = img["character_name"]
            if name not in char_groups:
                char_groups[name] = []
            char_groups[name].append(img)

        # 1. 정확한 이름 매칭
        if character_name in char_groups:
            img = char_groups[character_name][0]  # 최신(대표) 이미지
            print(f"[CharImageManager] ✅ 정확 매칭: '{character_name}'")
            return {
                "path": img["path"],
                "name": character_name,
                "is_representative": img.get("is_representative", True),
                "match_type": "exact"
            }

        # 2. 정규화된 이름 매칭
        normalized_query = self._normalize_name(character_name)
        for name, images in char_groups.items():
            if self._normalize_name(name) == normalized_query:
                img = images[0]
                print(f"[CharImageManager] ✅ 정규화 매칭: '{character_name}' → '{name}'")
                return {
                    "path": img["path"],
                    "name": name,
                    "is_representative": img.get("is_representative", True),
                    "match_type": "normalized"
                }

        # 3. 부분 매칭 (포함 관계)
        for name, images in char_groups.items():
            if character_name in name or name in character_name:
                img = images[0]
                print(f"[CharImageManager] ✅ 부분 매칭: '{character_name}' ~ '{name}'")
                return {
                    "path": img["path"],
                    "name": name,
                    "is_representative": img.get("is_representative", True),
                    "match_type": "partial"
                }

        # 4. 유사도 매칭
        best_match = self._find_similar_name(character_name, list(char_groups.keys()))
        if best_match:
            images = char_groups[best_match]
            img = images[0]
            print(f"[CharImageManager] ✅ 유사도 매칭: '{character_name}' ≈ '{best_match}'")
            return {
                "path": img["path"],
                "name": best_match,
                "is_representative": img.get("is_representative", True),
                "match_type": "similar"
            }

        print(f"[CharImageManager] ❌ 캐릭터 '{character_name}' 이미지 없음")
        return None

    def _normalize_name(self, name: str) -> str:
        """이름 정규화 (공백, 특수문자 제거, 소문자)"""
        if not name:
            return ""
        # 공백, 특수문자 제거
        normalized = re.sub(r'[^가-힣a-zA-Z0-9]', '', name)
        return normalized.lower()

    def _find_similar_name(self, query: str, names: List[str], threshold: float = 0.6) -> Optional[str]:
        """유사한 이름 찾기 (SequenceMatcher 기반)"""
        from difflib import SequenceMatcher

        best_match = None
        best_ratio = 0

        for name in names:
            # 한글 이름 비교
            ratio = SequenceMatcher(None, query, name).ratio()

            # 정규화된 이름으로도 비교
            norm_ratio = SequenceMatcher(
                None,
                self._normalize_name(query),
                self._normalize_name(name)
            ).ratio()

            max_ratio = max(ratio, norm_ratio)

            if max_ratio > best_ratio and max_ratio >= threshold:
                best_ratio = max_ratio
                best_match = name

        return best_match

    def get_character_for_scene(self, scene: Dict, use_cache: bool = True) -> Optional[Dict]:
        """
        씬 데이터에서 캐릭터 이미지 찾기 (v2.0: 캐싱 지원)

        Args:
            scene: 씬 데이터 (characters 배열 또는 character_prompt 포함)
            use_cache: 캐시 사용 여부 (기본 True)

        Returns:
            캐릭터 이미지 정보 또는 None
        """
        import time

        scene_id = scene.get('scene_id') or scene.get('scene_number', '?')

        # v2.0: 캐시 확인
        cache_key = f"scene_char_{self.project_path}_{scene_id}"
        if use_cache and cache_key in CharacterImageManager._scene_link_cache:
            if CharacterImageManager.is_cache_valid(cache_key):
                # 캐시 히트 - 로그 출력 없이 반환
                return CharacterImageManager._scene_link_cache[cache_key]

        # 0. appearance_scenes 기반 매칭 (v3.33 추가)
        # characters.json에서 이 씬에 등장하는 캐릭터 찾기
        char_data = self._load_character_data()
        for char in char_data:
            appearance_scenes = char.get('appearance_scenes', [])
            if scene_id in appearance_scenes or str(scene_id) in [str(s) for s in appearance_scenes]:
                char_name = char.get('name', '')
                if char_name:
                    result = self.find_character_image(char_name)
                    if result:
                        # 캐시에 저장
                        CharacterImageManager._scene_link_cache[cache_key] = result
                        CharacterImageManager._cache_timestamp[cache_key] = time.time()
                        return result

        # 1. characters 배열에서 이름 추출
        characters = scene.get('characters', [])
        for char in characters:
            char_name = char.get('name', '').strip()
            if char_name:
                result = self.find_character_image(char_name)
                if result:
                    # 캐시에 저장
                    CharacterImageManager._scene_link_cache[cache_key] = result
                    CharacterImageManager._cache_timestamp[cache_key] = time.time()
                    return result

        # 2. character_prompt에서 이름 추출 시도
        char_prompt = (
            scene.get('character_prompt_en', '') or
            scene.get('character_prompt', '')
        )

        if char_prompt:
            # 알려진 캐릭터 이름과 매칭
            all_images = self.get_all_character_images()
            known_names = list(set(img["character_name"] for img in all_images))

            for name in known_names:
                if name in char_prompt or name.lower() in char_prompt.lower():
                    result = self.find_character_image(name)
                    if result:
                        # 캐시에 저장
                        CharacterImageManager._scene_link_cache[cache_key] = result
                        CharacterImageManager._cache_timestamp[cache_key] = time.time()
                        return result

        # 결과 없음 - None도 캐시에 저장 (재호출 방지)
        CharacterImageManager._scene_link_cache[cache_key] = None
        CharacterImageManager._cache_timestamp[cache_key] = time.time()
        return None

    def get_all_characters_for_scene(self, scene: Dict, use_cache: bool = True) -> List[Dict]:
        """
        씬에 등장하는 모든 캐릭터의 이미지 찾기 (v2.0: 캐싱 지원)

        Args:
            scene: 씬 데이터
            use_cache: 캐시 사용 여부 (기본 True)

        Returns:
            캐릭터 이미지 정보 리스트 (여러 캐릭터 지원)
        """
        import time

        scene_id = scene.get('scene_id') or scene.get('scene_number', '?')

        # v2.0: 캐시 확인
        cache_key = f"scene_all_chars_{self.project_path}_{scene_id}"
        if use_cache and cache_key in CharacterImageManager._scene_link_cache:
            if CharacterImageManager.is_cache_valid(cache_key):
                # 캐시 히트 - 로그 출력 없이 반환
                return CharacterImageManager._scene_link_cache[cache_key]

        matched_characters = []
        seen_names = set()

        # 1. appearance_scenes 기반 매칭
        char_data = self._load_character_data()
        for char in char_data:
            appearance_scenes = char.get('appearance_scenes', [])
            if scene_id in appearance_scenes or str(scene_id) in [str(s) for s in appearance_scenes]:
                char_name = char.get('name', '')
                if char_name and char_name not in seen_names:
                    result = self.find_character_image(char_name)
                    if result:
                        matched_characters.append(result)
                        seen_names.add(char_name)

        # 2. characters 배열에서 이름 추출
        characters = scene.get('characters', [])
        for char in characters:
            char_name = char.get('name', '').strip()
            if char_name and char_name not in seen_names:
                result = self.find_character_image(char_name)
                if result:
                    matched_characters.append(result)
                    seen_names.add(char_name)

        # 캐시에 저장 (빈 리스트도 저장하여 재호출 방지)
        CharacterImageManager._scene_link_cache[cache_key] = matched_characters
        CharacterImageManager._cache_timestamp[cache_key] = time.time()

        return matched_characters

    def get_all_character_names(self) -> List[str]:
        """모든 캐릭터 이름 목록"""
        all_images = self.get_all_character_images()
        names = list(set(img["character_name"] for img in all_images))
        names.sort()
        return names


def on_character_image_generated(project_path: str, character_name: str, image_path: str):
    """
    캐릭터 이미지 생성 완료 후 호출
    최신 이미지를 대표로 자동 설정
    """
    manager = CharacterImageManager(project_path)
    manager.update_character_data_with_latest_images()
    print(f"[캐릭터 이미지] {character_name} 대표 이미지 자동 업데이트됨")
