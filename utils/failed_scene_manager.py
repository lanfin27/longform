# -*- coding: utf-8 -*-
"""
실패 씬 관리자 v1.0

이미지 생성 실패 씬 추적 및 재생성 관리

기능:
- 실패 씬 추가/조회/삭제
- 에러 유형별 분류
- 재시도 횟수 추적
- JSON 파일로 영구 저장
- 선택적/일괄 재생성 지원

사용법:
    from utils.failed_scene_manager import FailedSceneManager

    manager = FailedSceneManager(project_path)
    manager.add_failed_scene(scene_id, error, scene_data)
    failed_list = manager.get_unresolved_scenes()
"""

import os
import json
import traceback
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any


class FailedSceneManager:
    """실패 씬 추적 및 관리 클래스"""

    def __init__(self, project_path: str):
        """
        Args:
            project_path: 프로젝트 경로
        """
        self.project_path = Path(project_path)
        self.logs_dir = self.project_path / "logs"
        self.failed_scenes_path = self.logs_dir / "failed_scenes.json"
        self.failed_scenes: List[Dict] = []
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")

        # 로그 디렉토리 생성
        self.logs_dir.mkdir(parents=True, exist_ok=True)

        # 기존 실패 목록 로드
        self._load_failed_scenes()

        print(f"[FailedSceneManager] 초기화 완료 (프로젝트: {self.project_path.name})")

    def _load_failed_scenes(self):
        """기존 실패 씬 목록 로드"""
        if self.failed_scenes_path.exists():
            try:
                with open(self.failed_scenes_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.failed_scenes = data.get('failed_scenes', [])
                    if self.failed_scenes:
                        print(f"[FailedSceneManager] 기존 실패 씬 {len(self.failed_scenes)}개 로드됨")
            except Exception as e:
                print(f"[FailedSceneManager] 로드 실패: {e}")
                self.failed_scenes = []

    def _save_failed_scenes(self):
        """실패 씬 목록 저장"""
        data = {
            "project_path": str(self.project_path),
            "session_id": self.session_id,
            "total_failed": len(self.failed_scenes),
            "failed_scenes": self.failed_scenes,
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        try:
            with open(self.failed_scenes_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"[FailedSceneManager] 실패 씬 목록 저장됨: {len(self.failed_scenes)}개")
        except Exception as e:
            print(f"[FailedSceneManager] 저장 실패: {e}")

    def add_failed_scene(
        self,
        scene_id: int,
        error: Exception,
        scene_data: Dict = None,
        generation_type: str = "background",
        prompt: str = ""
    ):
        """
        실패 씬 추가

        Args:
            scene_id: 씬 ID
            error: 발생한 예외
            scene_data: 씬 데이터 (재생성에 필요)
            generation_type: 생성 유형 (background, composite, character 등)
            prompt: 사용된 프롬프트
        """
        # 중복 체크 (같은 씬이 이미 있으면 업데이트)
        existing_idx = None
        for idx, fs in enumerate(self.failed_scenes):
            if fs.get('scene_id') == scene_id and fs.get('generation_type') == generation_type:
                existing_idx = idx
                break

        # 에러 정보 추출
        error_type = type(error).__name__
        error_message = str(error)
        error_traceback = traceback.format_exc()

        # 에러 유형 분류
        error_category = self._classify_error(error_message)

        failed_info = {
            "scene_id": scene_id,
            "generation_type": generation_type,
            "error_type": error_type,
            "error_message": error_message,
            "error_category": error_category,
            "error_traceback": error_traceback,
            "prompt": prompt[:500] if prompt else "",  # 프롬프트 500자까지만
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "retry_count": 0,
            "scene_data": scene_data or {},
            "resolved": False
        }

        if existing_idx is not None:
            # 기존 항목 업데이트
            failed_info['retry_count'] = self.failed_scenes[existing_idx].get('retry_count', 0) + 1
            self.failed_scenes[existing_idx] = failed_info
            print(f"[FailedSceneManager] 씬 {scene_id} 실패 정보 업데이트 (재시도 {failed_info['retry_count']}회)")
        else:
            # 새 항목 추가
            self.failed_scenes.append(failed_info)
            print(f"[FailedSceneManager] 씬 {scene_id} 실패 추가: {error_type} ({error_category})")

        # 자동 저장
        self._save_failed_scenes()

    def _classify_error(self, error_message: str) -> str:
        """
        에러 메시지를 분류

        Returns:
            에러 카테고리 문자열
        """
        error_lower = error_message.lower()

        # 유명인 필터
        if any(kw in error_lower for kw in ['prominent_people', 'celebrity', 'public figure']):
            return "prominent_people_filter"

        # 인증 관련
        if any(kw in error_lower for kw in ['auth', 'cookie', 'expired', 'unauthorized', '401']):
            return "authentication"

        # Rate limit
        if any(kw in error_lower for kw in ['rate limit', '429', 'too many requests']):
            return "rate_limit"

        # 타임아웃
        if any(kw in error_lower for kw in ['timeout', 'timed out']):
            return "timeout"

        # 네트워크
        if any(kw in error_lower for kw in ['connection', 'network', 'socket']):
            return "network"

        # 파일 관련
        if any(kw in error_lower for kw in ['file not found', 'no such file', 'path', 'source image']):
            return "file_not_found"

        # 프롬프트 관련
        if any(kw in error_lower for kw in ['prompt', 'content policy']):
            return "prompt_issue"

        # 변수 에러 (current_prompt 등)
        if any(kw in error_lower for kw in ['unboundlocal', 'undefined', 'not defined']):
            return "code_error"

        return "unknown"

    def mark_resolved(self, scene_id: int, generation_type: str = "background"):
        """
        실패 씬을 해결됨으로 표시

        Args:
            scene_id: 씬 ID
            generation_type: 생성 유형
        """
        for fs in self.failed_scenes:
            if fs.get('scene_id') == scene_id and fs.get('generation_type') == generation_type:
                fs['resolved'] = True
                fs['resolved_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                print(f"[FailedSceneManager] 씬 {scene_id} 해결됨")
                break

        self._save_failed_scenes()

    def mark_multiple_resolved(self, scene_ids: List[int], generation_type: str = "background"):
        """여러 씬을 해결됨으로 표시"""
        for scene_id in scene_ids:
            for fs in self.failed_scenes:
                if fs.get('scene_id') == scene_id and fs.get('generation_type') == generation_type:
                    fs['resolved'] = True
                    fs['resolved_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    break

        print(f"[FailedSceneManager] {len(scene_ids)}개 씬 해결됨")
        self._save_failed_scenes()

    def remove_resolved(self):
        """해결된 씬들을 목록에서 제거"""
        before_count = len(self.failed_scenes)
        self.failed_scenes = [fs for fs in self.failed_scenes if not fs.get('resolved', False)]
        removed = before_count - len(self.failed_scenes)

        if removed > 0:
            print(f"[FailedSceneManager] 해결된 씬 {removed}개 제거됨")
            self._save_failed_scenes()

        return removed

    def get_unresolved_scenes(self) -> List[Dict]:
        """미해결 실패 씬 목록 반환"""
        return [fs for fs in self.failed_scenes if not fs.get('resolved', False)]

    def get_failed_scene_ids(self) -> List[int]:
        """미해결 실패 씬 ID 목록 반환"""
        return [fs['scene_id'] for fs in self.get_unresolved_scenes()]

    def get_scenes_by_category(self, category: str) -> List[Dict]:
        """특정 에러 카테고리의 실패 씬 반환"""
        return [
            fs for fs in self.get_unresolved_scenes()
            if fs.get('error_category') == category
        ]

    def get_retryable_scenes(self) -> List[Dict]:
        """재시도 가능한 씬 목록 (일시적 오류)"""
        retryable_categories = ['rate_limit', 'timeout', 'network']
        return [
            fs for fs in self.get_unresolved_scenes()
            if fs.get('error_category') in retryable_categories
        ]

    def clear_all(self):
        """모든 실패 씬 기록 삭제"""
        self.failed_scenes = []
        self._save_failed_scenes()
        print(f"[FailedSceneManager] 모든 실패 기록 삭제됨")

    def clear_resolved(self):
        """해결된 씬만 삭제"""
        return self.remove_resolved()

    def get_summary(self) -> Dict:
        """실패 씬 요약 정보"""
        unresolved = self.get_unresolved_scenes()

        # 에러 유형별 집계
        error_categories = {}
        error_types = {}

        for fs in unresolved:
            cat = fs.get('error_category', 'unknown')
            error_categories[cat] = error_categories.get(cat, 0) + 1

            err_type = fs.get('error_type', 'Unknown')
            error_types[err_type] = error_types.get(err_type, 0) + 1

        return {
            "total_failed": len(unresolved),
            "error_categories": error_categories,
            "error_types": error_types,
            "scene_ids": [fs['scene_id'] for fs in unresolved],
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

    def get_scene_data_for_retry(self, scene_id: int, generation_type: str = "background") -> Optional[Dict]:
        """재시도를 위한 씬 데이터 반환"""
        for fs in self.failed_scenes:
            if fs.get('scene_id') == scene_id and fs.get('generation_type') == generation_type:
                return fs.get('scene_data')
        return None

    def increment_retry_count(self, scene_id: int, generation_type: str = "background"):
        """재시도 횟수 증가"""
        for fs in self.failed_scenes:
            if fs.get('scene_id') == scene_id and fs.get('generation_type') == generation_type:
                fs['retry_count'] = fs.get('retry_count', 0) + 1
                fs['last_retry'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                break
        self._save_failed_scenes()


# ═══════════════════════════════════════════════════════════════════════════════
# 에러 카테고리별 아이콘 및 설명
# ═══════════════════════════════════════════════════════════════════════════════

ERROR_CATEGORY_INFO = {
    "prominent_people_filter": {
        "icon": "🚫",
        "label": "유명인 필터",
        "description": "프롬프트에 유명인/기업명이 포함되어 차단됨",
        "retryable": True,
        "solution": "프롬프트 일반화 후 재시도"
    },
    "authentication": {
        "icon": "🔐",
        "label": "인증 오류",
        "description": "API 쿠키/토큰이 만료됨",
        "retryable": False,
        "solution": "API 설정에서 쿠키 갱신 필요"
    },
    "rate_limit": {
        "icon": "⏱️",
        "label": "요청 제한",
        "description": "API 호출 횟수 초과",
        "retryable": True,
        "solution": "잠시 후 자동 재시도"
    },
    "timeout": {
        "icon": "⏰",
        "label": "시간 초과",
        "description": "API 응답 시간 초과",
        "retryable": True,
        "solution": "재시도로 해결 가능"
    },
    "network": {
        "icon": "🌐",
        "label": "네트워크",
        "description": "네트워크 연결 문제",
        "retryable": True,
        "solution": "네트워크 확인 후 재시도"
    },
    "file_not_found": {
        "icon": "📁",
        "label": "파일 없음",
        "description": "필요한 파일을 찾을 수 없음",
        "retryable": False,
        "solution": "누락된 파일 생성 필요"
    },
    "prompt_issue": {
        "icon": "📝",
        "label": "프롬프트 문제",
        "description": "프롬프트가 정책에 위배됨",
        "retryable": True,
        "solution": "프롬프트 수정 후 재시도"
    },
    "code_error": {
        "icon": "🐛",
        "label": "코드 오류",
        "description": "내부 코드 오류 발생",
        "retryable": False,
        "solution": "버그 수정 필요"
    },
    "unknown": {
        "icon": "❓",
        "label": "알 수 없음",
        "description": "분류되지 않은 오류",
        "retryable": True,
        "solution": "상세 로그 확인 필요"
    }
}


def get_error_category_info(category: str) -> Dict:
    """에러 카테고리 정보 반환"""
    return ERROR_CATEGORY_INFO.get(category, ERROR_CATEGORY_INFO["unknown"])


# ═══════════════════════════════════════════════════════════════════════════════
# 싱글톤 인스턴스 관리
# ═══════════════════════════════════════════════════════════════════════════════

_manager_instances: Dict[str, FailedSceneManager] = {}


def get_failed_scene_manager(project_path: str) -> FailedSceneManager:
    """
    프로젝트별 FailedSceneManager 싱글톤 반환

    Args:
        project_path: 프로젝트 경로

    Returns:
        FailedSceneManager 인스턴스
    """
    global _manager_instances

    # 경로 정규화
    normalized_path = str(Path(project_path).resolve())

    if normalized_path not in _manager_instances:
        _manager_instances[normalized_path] = FailedSceneManager(project_path)

    return _manager_instances[normalized_path]


def clear_manager_cache():
    """매니저 캐시 초기화"""
    global _manager_instances
    _manager_instances = {}
    print("[FailedSceneManager] 매니저 캐시 초기화됨")


# ═══════════════════════════════════════════════════════════════════════════════
# 테스트 코드
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("FailedSceneManager 테스트")
    print("=" * 60)

    # 테스트용 프로젝트 경로
    test_path = "./test_project"
    os.makedirs(test_path, exist_ok=True)

    # 매니저 생성
    manager = FailedSceneManager(test_path)

    # 테스트 실패 추가
    try:
        raise ValueError("PROMINENT_PEOPLE_FILTER_FAILED: 이재용")
    except Exception as e:
        manager.add_failed_scene(
            scene_id=1,
            error=e,
            scene_data={"narration": "테스트"},
            prompt="삼성 회장 이재용이 발표하는 모습"
        )

    try:
        raise TimeoutError("API timeout after 180s")
    except Exception as e:
        manager.add_failed_scene(
            scene_id=2,
            error=e,
            scene_data={"narration": "테스트2"}
        )

    # 요약 출력
    summary = manager.get_summary()
    print(f"\n📊 요약:")
    print(f"  총 실패: {summary['total_failed']}개")
    print(f"  에러 카테고리: {summary['error_categories']}")
    print(f"  씬 ID: {summary['scene_ids']}")

    # 정리
    import shutil
    shutil.rmtree(test_path, ignore_errors=True)
    print("\n✅ 테스트 완료")
