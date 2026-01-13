# -*- coding: utf-8 -*-
"""
씬 이미지 경로 통합 관리자 (v2.0 - 성능 최적화)

기능:
- 배경/합성 이미지 경로 저장/조회
- 최신 이미지 자동 감지
- 모든 생성 모드에서 일관된 업데이트
- scenes.json 및 세션 상태 동기화
- ✅ 캐싱 최적화 (파일 시스템 I/O 최소화)
- ✅ v2.0: 동기화 간격 강화 (60초 → 120초)
- ✅ v2.0: 로그 출력 최소화 (DEBUG 모드에서만 상세 로그)
"""

import os
import json
import glob
import hashlib
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import streamlit as st

# ============================================================
# 설정
# ============================================================
CACHE_TTL_SECONDS = 120  # 캐시 유효 시간 (1분 → 2분)
DEBUG_MODE = os.getenv("DEBUG", "false").lower() == "true"


def _debug_log(message: str):
    """디버그 모드에서만 출력"""
    if DEBUG_MODE:
        print(message)


class SceneImageManager:
    """씬별 이미지 경로 관리"""

    def __init__(self, project_path: str):
        self.project_path = Path(project_path)
        self.images_dir = self.project_path / "images"
        self.scenes_file = self.project_path / "analysis" / "scenes.json"
        self.scenes_data = self._load_scenes()

    def _load_scenes(self) -> List[Dict]:
        """씬 데이터 로드"""

        if not self.scenes_file.exists():
            print(f"[SceneImageManager] ⚠️ scenes.json 없음")
            return []

        try:
            with open(self.scenes_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            if isinstance(data, list):
                return data
            return data.get("scenes", [])

        except Exception as e:
            print(f"[SceneImageManager] ❌ 로드 실패: {e}")
            return []

    def _save_scenes(self):
        """씬 데이터 저장"""

        try:
            # 기존 파일 구조 유지
            if self.scenes_file.exists():
                with open(self.scenes_file, "r", encoding="utf-8") as f:
                    existing = json.load(f)

                if isinstance(existing, dict):
                    existing["scenes"] = self.scenes_data
                    data_to_save = existing
                else:
                    data_to_save = self.scenes_data
            else:
                data_to_save = self.scenes_data

            # 저장
            self.scenes_file.parent.mkdir(parents=True, exist_ok=True)

            with open(self.scenes_file, "w", encoding="utf-8") as f:
                json.dump(data_to_save, f, ensure_ascii=False, indent=2)

            _debug_log(f"[SceneImageManager] ✅ 씬 데이터 저장됨")

        except Exception as e:
            print(f"[SceneImageManager] ❌ 저장 실패: {e}")

    # ============================================================
    # 이미지 경로 업데이트 메서드
    # ============================================================

    def update_background_image(self, scene_id: int, image_path: str) -> bool:
        """
        배경 이미지 경로 업데이트

        Args:
            scene_id: 씬 ID
            image_path: 새 배경 이미지 경로

        Returns:
            성공 여부
        """

        scene = self._get_scene(scene_id)

        if not scene:
            print(f"[SceneImageManager] ⚠️ 씬 {scene_id} 없음")
            return False

        if not os.path.exists(image_path):
            print(f"[SceneImageManager] ⚠️ 파일 없음: {image_path}")
            return False

        # 새 경로 저장
        scene["background_image"] = image_path
        scene["background_updated_at"] = datetime.now().isoformat()

        # 파일에 저장
        self._save_scenes()

        # 세션에도 저장 (즉시 반영)
        self._update_session(scene_id, "background", image_path)

        _debug_log(f"[SceneImageManager] ✅ 씬 {scene_id} 배경 업데이트: {os.path.basename(image_path)}")

        return True

    def update_composite_image(self, scene_id: int, image_path: str) -> bool:
        """
        합성 이미지 경로 업데이트

        Args:
            scene_id: 씬 ID
            image_path: 새 합성 이미지 경로

        Returns:
            성공 여부
        """

        scene = self._get_scene(scene_id)

        if not scene:
            print(f"[SceneImageManager] ⚠️ 씬 {scene_id} 없음")
            return False

        if not os.path.exists(image_path):
            print(f"[SceneImageManager] ⚠️ 파일 없음: {image_path}")
            return False

        # 새 경로 저장
        scene["composite_image"] = image_path
        scene["composite_updated_at"] = datetime.now().isoformat()

        # ✅ 핵심: display_image도 업데이트 (씬별 생성 탭에서 사용)
        scene["display_image"] = image_path

        # 파일에 저장
        self._save_scenes()

        # 세션에도 저장
        self._update_session(scene_id, "composite", image_path)

        _debug_log(f"[SceneImageManager] ✅ 씬 {scene_id} 합성 업데이트: {os.path.basename(image_path)}")

        return True

    def _update_session(self, scene_id: int, image_type: str, image_path: str):
        """세션 상태 업데이트 (즉시 UI 반영)"""

        # 개별 세션 키
        key = f"scene_{scene_id}_{image_type}_image"
        st.session_state[key] = image_path

        # composite_result 키도 업데이트 (일괄 합성에서 사용)
        if image_type == "composite":
            st.session_state[f"composite_result_{scene_id}"] = image_path

        # analyzed_scenes 업데이트
        if "analyzed_scenes" in st.session_state:
            for scene in st.session_state["analyzed_scenes"]:
                if scene.get("scene_id") == scene_id:
                    if image_type == "background":
                        scene["background_image"] = image_path
                    elif image_type == "composite":
                        scene["composite_image"] = image_path
                        scene["display_image"] = image_path
                    break

        # scenes 키도 업데이트 (일부 페이지에서 사용)
        if "scenes" in st.session_state:
            for scene in st.session_state["scenes"]:
                if scene.get("scene_id") == scene_id:
                    if image_type == "background":
                        scene["background_image"] = image_path
                    elif image_type == "composite":
                        scene["composite_image"] = image_path
                        scene["display_image"] = image_path
                    break

        # composited_images 딕셔너리도 업데이트
        if image_type == "composite":
            if "composited_images" not in st.session_state:
                st.session_state["composited_images"] = {}
            st.session_state["composited_images"][str(scene_id)] = {
                "path": image_path,
                "url": image_path,
                "updated_at": datetime.now().isoformat()
            }

    def _get_scene(self, scene_id: int) -> Optional[Dict]:
        """씬 ID로 씬 데이터 가져오기"""

        for scene in self.scenes_data:
            if scene.get("scene_id") == scene_id:
                return scene
        return None

    # ============================================================
    # ✅ 캐싱 메서드 (성능 최적화)
    # ============================================================

    def _get_cache_key(self) -> str:
        """캐시 키 생성 (프로젝트 경로 기반)"""
        return hashlib.md5(str(self.project_path).encode()).hexdigest()[:16]

    def sync_all_scenes_cached(self, force: bool = False) -> int:
        """
        캐싱된 씬 이미지 동기화 (v2.0 - 성능 최적화)

        - 캐시가 유효하면 즉시 반환 (파일 시스템 조회 없음!)
        - 캐시가 만료되었거나 force=True면 실제 동기화 실행
        - v2.0: 120초 TTL, 로그 최소화

        Returns:
            업데이트된 씬 수
        """
        cache_key = f"scene_sync_cache_{self._get_cache_key()}"
        cache_time_key = f"scene_sync_time_{self._get_cache_key()}"

        # 캐시 확인 (force가 아닐 때만)
        if not force:
            cached_result = st.session_state.get(cache_key)
            cached_time = st.session_state.get(cache_time_key)

            if cached_result is not None and cached_time:
                elapsed = (datetime.now() - cached_time).total_seconds()
                if elapsed < CACHE_TTL_SECONDS:
                    _debug_log(f"[SceneImageManager] ⚡ 캐시 사용 ({elapsed:.1f}초 전 데이터)")
                    return cached_result

        # 캐시 미스 또는 강제 갱신 → 실제 동기화
        _debug_log(f"[SceneImageManager] 🔄 실제 동기화 실행...")
        result = self.sync_all_scenes()

        # 캐시 저장
        st.session_state[cache_key] = result
        st.session_state[cache_time_key] = datetime.now()

        return result

    def invalidate_cache(self):
        """캐시 무효화 (이미지 생성 후 호출)"""
        cache_key = f"scene_sync_cache_{self._get_cache_key()}"
        cache_time_key = f"scene_sync_time_{self._get_cache_key()}"

        if cache_key in st.session_state:
            del st.session_state[cache_key]
        if cache_time_key in st.session_state:
            del st.session_state[cache_time_key]

        # scene_images_synced 플래그도 리셋
        if "scene_images_synced" in st.session_state:
            del st.session_state["scene_images_synced"]

        print("[SceneImageManager] 🗑️ 캐시 무효화됨")

    # ============================================================
    # 최신 이미지 조회 메서드
    # ============================================================

    def get_latest_background(self, scene_id: int) -> Optional[str]:
        """
        씬의 최신 배경 이미지 경로 반환
        - scenes.json 먼저 확인
        - 없으면 파일 시스템에서 최신 파일 검색
        """

        # 1. scenes.json에서 확인
        scene = self._get_scene(scene_id)
        if scene:
            saved_path = scene.get("background_image")
            if saved_path and os.path.exists(saved_path):
                return saved_path

        # 2. 파일 시스템에서 검색
        return self._find_latest_image(scene_id, "background")

    def get_latest_composite(self, scene_id: int) -> Optional[str]:
        """
        씬의 최신 합성 이미지 경로 반환
        """

        # 1. scenes.json에서 확인
        scene = self._get_scene(scene_id)
        if scene:
            saved_path = scene.get("composite_image") or scene.get("display_image")
            if saved_path and os.path.exists(saved_path):
                return saved_path

        # 2. 파일 시스템에서 검색
        return self._find_latest_image(scene_id, "composite")

    def get_display_image(self, scene_id: int) -> Optional[str]:
        """
        씬별 생성 탭에 표시할 이미지 반환
        - 합성 이미지 우선
        - 없으면 배경 이미지
        """

        # 합성 이미지 먼저
        composite = self.get_latest_composite(scene_id)
        if composite:
            return composite

        # 배경 이미지
        background = self.get_latest_background(scene_id)
        if background:
            return background

        return None

    def _find_latest_image(self, scene_id: int, image_type: str) -> Optional[str]:
        """
        파일 시스템에서 최신 이미지 검색

        Args:
            scene_id: 씬 ID
            image_type: "background" 또는 "composite"
        """

        # 검색 패턴들
        patterns = []

        if image_type == "background":
            patterns = [
                f"bg_scene_{scene_id:03d}_*.png",
                f"scene_{scene_id:03d}_bg*.png",
                f"scene_{scene_id}_bg*.png",
                f"scene_{scene_id:03d}_background*.png",
            ]
        elif image_type == "composite":
            patterns = [
                f"scene_{scene_id:03d}_composited*.png",
                f"scene_{scene_id:03d}_composite*.png",
                f"scene_{scene_id}_composite*.png",
                f"scene_{scene_id:03d}_final*.png",
                f"composite_scene_{scene_id}*.png",
            ]

        # 검색 디렉토리들
        search_dirs = [
            self.images_dir / "composited",
            self.images_dir / "backgrounds",
            self.images_dir / "scenes",
            self.images_dir,
        ]

        all_matches = []

        for search_dir in search_dirs:
            if not search_dir.exists():
                continue

            for pattern in patterns:
                matches = list(search_dir.glob(pattern))
                all_matches.extend(matches)

        if not all_matches:
            return None

        # 최신 파일 반환 (수정 시간 기준)
        latest = max(all_matches, key=lambda p: p.stat().st_mtime)

        _debug_log(f"[SceneImageManager] 🔍 씬 {scene_id} {image_type} 최신 파일: {latest.name}")

        return str(latest)

    # ============================================================
    # 일괄 동기화 메서드
    # ============================================================

    def sync_all_scenes(self) -> int:
        """
        모든 씬의 이미지 경로를 파일 시스템과 동기화
        - 갤러리의 최신 이미지를 씬 데이터에 반영
        """

        _debug_log(f"\n{'='*60}")
        _debug_log("[SceneImageManager] 전체 씬 이미지 동기화 시작")
        _debug_log(f"{'='*60}")

        updated_count = 0

        for scene in self.scenes_data:
            scene_id = scene.get("scene_id")

            if not scene_id:
                continue

            # 최신 배경 이미지 확인
            latest_bg = self._find_latest_image(scene_id, "background")
            current_bg = scene.get("background_image")

            if latest_bg and latest_bg != current_bg:
                scene["background_image"] = latest_bg
                scene["background_updated_at"] = datetime.now().isoformat()
                self._update_session(scene_id, "background", latest_bg)
                _debug_log(f"  씬 {scene_id}: 배경 업데이트 → {os.path.basename(latest_bg)}")
                updated_count += 1

            # 최신 합성 이미지 확인
            latest_comp = self._find_latest_image(scene_id, "composite")
            current_comp = scene.get("composite_image")

            if latest_comp and latest_comp != current_comp:
                scene["composite_image"] = latest_comp
                scene["display_image"] = latest_comp
                scene["composite_updated_at"] = datetime.now().isoformat()
                self._update_session(scene_id, "composite", latest_comp)
                _debug_log(f"  씬 {scene_id}: 합성 업데이트 → {os.path.basename(latest_comp)}")
                updated_count += 1

        if updated_count > 0:
            self._save_scenes()
            _debug_log(f"\n[SceneImageManager] ✅ {updated_count}개 이미지 경로 동기화됨")
        else:
            _debug_log(f"\n[SceneImageManager] ✅ 모든 이미지가 최신 상태")

        _debug_log(f"{'='*60}\n")

        return updated_count

    def reload_scenes(self):
        """씬 데이터 다시 로드"""
        self.scenes_data = self._load_scenes()


# ============================================================
# 싱글톤 인스턴스 관리
# ============================================================

_manager_instance: Optional[SceneImageManager] = None


def get_scene_image_manager(project_path: str = None) -> Optional[SceneImageManager]:
    """싱글톤 인스턴스 반환"""
    global _manager_instance

    if project_path:
        _manager_instance = SceneImageManager(project_path)
    elif _manager_instance is None:
        # 세션에서 프로젝트 경로 가져오기
        project_path = st.session_state.get("current_project_path")
        if not project_path:
            # current_project에서 시도
            current_project = st.session_state.get("current_project")
            if current_project:
                project_path = str(current_project)

        if project_path:
            _manager_instance = SceneImageManager(project_path)

    return _manager_instance


def reset_scene_image_manager():
    """매니저 인스턴스 리셋 (프로젝트 변경 시 사용)"""
    global _manager_instance
    _manager_instance = None


# ============================================================
# 헬퍼 함수
# ============================================================

def update_scene_background(scene_id: int, image_path: str, project_path: str = None) -> bool:
    """배경 이미지 업데이트 헬퍼"""
    manager = get_scene_image_manager(project_path)
    if manager:
        return manager.update_background_image(scene_id, image_path)
    return False


def update_scene_composite(scene_id: int, image_path: str, project_path: str = None) -> bool:
    """합성 이미지 업데이트 헬퍼"""
    manager = get_scene_image_manager(project_path)
    if manager:
        return manager.update_composite_image(scene_id, image_path)
    return False


def get_scene_display_image(scene_id: int, project_path: str = None) -> Optional[str]:
    """씬 표시 이미지 조회 헬퍼"""
    manager = get_scene_image_manager(project_path)
    if manager:
        return manager.get_display_image(scene_id)
    return None


def sync_scene_images(project_path: str = None) -> int:
    """전체 씬 이미지 동기화 헬퍼"""
    manager = get_scene_image_manager(project_path)
    if manager:
        return manager.sync_all_scenes()
    return 0


def sync_scene_images_cached(project_path: str = None, force: bool = False) -> int:
    """캐싱된 씬 이미지 동기화 헬퍼"""
    manager = get_scene_image_manager(project_path)
    if manager:
        return manager.sync_all_scenes_cached(force=force)
    return 0


def invalidate_scene_image_cache(project_path: str = None):
    """씬 이미지 캐시 무효화 헬퍼"""
    manager = get_scene_image_manager(project_path)
    if manager:
        manager.invalidate_cache()


# ============================================================
# ✅ Streamlit 캐시 기반 빠른 이미지 경로 조회
# ============================================================

@st.cache_data(ttl=60, show_spinner=False)
def get_scene_image_paths_fast(project_path: str) -> Dict:
    """
    씬 이미지 경로 빠른 조회 (Streamlit 캐시 사용)

    - 60초간 캐시 유지
    - 파일 시스템 조회 최소화

    Returns:
        {
            "backgrounds": {1: "path", 2: "path", ...},
            "composites": {1: "path", 2: "path", ...},
            "scenes": {1: "path", 2: "path", ...}
        }
    """
    import re

    result = {
        "backgrounds": {},
        "composites": {},
        "scenes": {}
    }

    images_path = Path(project_path) / "images"
    composited_path = images_path / "composited"
    backgrounds_path = images_path / "backgrounds"
    scenes_path = images_path / "scenes"

    if not images_path.exists():
        return result

    # ✅ 배경 이미지 (backgrounds 폴더 + images 루트)
    for search_path in [backgrounds_path, images_path]:
        if not search_path.exists():
            continue
        for img in search_path.glob("bg_scene_*.png"):
            match = re.search(r'bg_scene_(\d+)', img.name)
            if match:
                scene_num = int(match.group(1))
                # 최신 파일만 저장
                if scene_num not in result["backgrounds"]:
                    result["backgrounds"][scene_num] = str(img)
                else:
                    existing = Path(result["backgrounds"][scene_num])
                    if img.stat().st_mtime > existing.stat().st_mtime:
                        result["backgrounds"][scene_num] = str(img)

    # ✅ 합성 이미지 (composited 폴더 + images 루트)
    for search_path in [composited_path, images_path]:
        if not search_path.exists():
            continue
        for img in search_path.glob("scene_*_composited*.png"):
            match = re.search(r'scene_(\d+)_composited', img.name)
            if match:
                scene_num = int(match.group(1))
                if scene_num not in result["composites"]:
                    result["composites"][scene_num] = str(img)
                else:
                    existing = Path(result["composites"][scene_num])
                    if img.stat().st_mtime > existing.stat().st_mtime:
                        result["composites"][scene_num] = str(img)

    # ✅ scenes 폴더 이미지 (AI 매핑 jpg 포함)
    if scenes_path.exists():
        for ext in ["*.png", "*.jpg", "*.jpeg", "*.webp"]:
            for img in scenes_path.glob(ext):
                match = re.search(r'(\d+)', img.stem)
                if match:
                    scene_num = int(match.group(1))
                    # 이미 있으면 최신 파일 우선
                    if scene_num not in result["scenes"]:
                        result["scenes"][scene_num] = str(img)
                    else:
                        existing = Path(result["scenes"][scene_num])
                        if img.stat().st_mtime > existing.stat().st_mtime:
                            result["scenes"][scene_num] = str(img)

    _debug_log(f"[SceneImageManager] 📂 이미지 경로 캐시 생성: "
               f"배경 {len(result['backgrounds'])}개, "
               f"합성 {len(result['composites'])}개, "
               f"씬 {len(result['scenes'])}개")

    return result


def clear_image_path_cache():
    """이미지 경로 캐시 클리어"""
    get_scene_image_paths_fast.clear()
    print("[SceneImageManager] 🗑️ 이미지 경로 캐시 클리어됨")
