# -*- coding: utf-8 -*-
"""
스크립트 동기화 관리자

스크립트 생성 ↔ 씬 분석 간 데이터 동기화 문제 해결
- 통합 세션 키 사용
- 언어 설정 자동 동기화
- 캐시 자동 무효화
"""

import json
from pathlib import Path
from typing import Optional, Dict, Tuple
from datetime import datetime

try:
    import streamlit as st
    HAS_STREAMLIT = True
except ImportError:
    HAS_STREAMLIT = False


class ScriptSyncManager:
    """스크립트 동기화 관리자"""

    # 통합 세션 키
    SESSION_KEYS = {
        "content": "sync_script_content",        # 최신 스크립트 내용
        "language": "sync_script_language",      # 스크립트 언어
        "source": "sync_script_source",          # 소스 (manual, ai, file, srt)
        "updated_at": "sync_script_updated_at",  # 마지막 업데이트 시간
        "version": "sync_script_version",        # 버전 (변경 감지용)
    }

    # 무효화할 캐시 키들
    CACHE_KEYS_TO_INVALIDATE = [
        "scene_analysis_script",     # 씬 분석 스크립트 캐시
        "cached_script",             # 기타 캐시
        "analyzed_scenes",           # 분석 결과
        "scene_analysis_result",     # 분석 결과
        "scenes",                    # 씬 데이터
        "srt_scenes",                # SRT 씬 데이터
        "srt_source",                # SRT 소스 플래그
    ]

    # 언어 코드 맵
    LANGUAGES = {
        "ko": "한국어",
        "en": "영어",
        "ja": "일본어",
        "zh": "중국어"
    }

    def __init__(self, project_path: str = None):
        """
        Args:
            project_path: 프로젝트 경로
        """
        self.project_path = Path(project_path) if project_path else None

    @classmethod
    def save_script(
        cls,
        content: str,
        language: str = "ko",
        source: str = "manual",
        project_path: str = None
    ) -> bool:
        """
        스크립트 저장 (세션 + 파일)
        - 다른 페이지의 캐시 자동 무효화

        Args:
            content: 스크립트 내용
            language: 언어 코드
            source: 소스 (manual, ai, file, srt)
            project_path: 프로젝트 경로 (파일 저장용)

        Returns:
            성공 여부
        """
        if not HAS_STREAMLIT:
            print("[ScriptSyncManager] Streamlit not available")
            return False

        if not content or not content.strip():
            print("[ScriptSyncManager] Empty content, not saving")
            return False

        content = content.strip()
        now = datetime.now().isoformat()
        version = int(datetime.now().timestamp() * 1000)

        # 1. 세션에 저장
        st.session_state[cls.SESSION_KEYS["content"]] = content
        st.session_state[cls.SESSION_KEYS["language"]] = language
        st.session_state[cls.SESSION_KEYS["source"]] = source
        st.session_state[cls.SESSION_KEYS["updated_at"]] = now
        st.session_state[cls.SESSION_KEYS["version"]] = version

        print(f"[ScriptSyncManager] ✅ 세션에 저장됨")
        print(f"  - 언어: {cls.LANGUAGES.get(language, language)}")
        print(f"  - 글자 수: {len(content)}자")
        print(f"  - 소스: {source}")
        print(f"  - 버전: {version}")

        # 2. 캐시 무효화 (다른 페이지의 오래된 데이터 삭제)
        invalidated = cls._invalidate_caches()
        if invalidated:
            print(f"[ScriptSyncManager] 🗑️ 캐시 무효화: {invalidated}")

        # 3. 파일로도 저장 (선택적)
        if project_path:
            cls._save_to_file(content, language, project_path)

        return True

    @classmethod
    def load_script(cls, project_path: str = None) -> Tuple[Optional[str], str]:
        """
        스크립트 로드 (세션 우선)

        Args:
            project_path: 프로젝트 경로 (파일 폴백용)

        Returns:
            (스크립트 내용, 언어 코드)
        """
        if not HAS_STREAMLIT:
            return None, "ko"

        # 1. 세션에서 먼저 확인 (가장 최신)
        content = st.session_state.get(cls.SESSION_KEYS["content"])
        language = st.session_state.get(cls.SESSION_KEYS["language"], "ko")

        if content:
            print(f"[ScriptSyncManager] ✅ 세션에서 로드됨 ({len(content)}자, {language})")
            return content, language

        # 2. 세션에 없으면 파일에서 로드
        if project_path:
            content, language = cls._load_from_file(project_path)
            if content:
                # 세션에도 저장
                st.session_state[cls.SESSION_KEYS["content"]] = content
                st.session_state[cls.SESSION_KEYS["language"]] = language
                print(f"[ScriptSyncManager] ✅ 파일에서 로드됨 ({len(content)}자, {language})")
                return content, language

        return None, "ko"

    @classmethod
    def get_script_info(cls) -> Dict:
        """현재 스크립트 정보 반환"""
        if not HAS_STREAMLIT:
            return {"has_content": False}

        content = st.session_state.get(cls.SESSION_KEYS["content"], "")
        language = st.session_state.get(cls.SESSION_KEYS["language"], "ko")
        source = st.session_state.get(cls.SESSION_KEYS["source"], "unknown")
        updated_at = st.session_state.get(cls.SESSION_KEYS["updated_at"], "")
        version = st.session_state.get(cls.SESSION_KEYS["version"], 0)

        return {
            "has_content": bool(content),
            "char_count": len(content) if content else 0,
            "language": language,
            "language_name": cls.LANGUAGES.get(language, language),
            "source": source,
            "updated_at": updated_at,
            "version": version
        }

    @classmethod
    def is_script_updated(cls, last_known_version: int) -> bool:
        """
        스크립트가 업데이트되었는지 확인

        Args:
            last_known_version: 마지막으로 알고 있던 버전

        Returns:
            업데이트 여부
        """
        if not HAS_STREAMLIT:
            return False

        current_version = st.session_state.get(cls.SESSION_KEYS["version"], 0)
        return current_version > last_known_version

    @classmethod
    def _invalidate_caches(cls) -> list:
        """캐시 무효화"""
        if not HAS_STREAMLIT:
            return []

        invalidated = []
        for key in cls.CACHE_KEYS_TO_INVALIDATE:
            if key in st.session_state:
                del st.session_state[key]
                invalidated.append(key)

        return invalidated

    @classmethod
    def _save_to_file(cls, content: str, language: str, project_path: str):
        """파일로 저장"""
        try:
            project = Path(project_path)
            scripts_dir = project / "scripts"
            scripts_dir.mkdir(parents=True, exist_ok=True)

            # 메인 스크립트 파일
            script_file = scripts_dir / f"draft_{language}.txt"
            script_file.write_text(content, encoding="utf-8")

            # 메타데이터
            meta_file = scripts_dir / "sync_meta.json"
            meta = {
                "language": language,
                "char_count": len(content),
                "updated_at": datetime.now().isoformat()
            }
            meta_file.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

            print(f"[ScriptSyncManager] 📁 파일 저장: {script_file}")

        except Exception as e:
            print(f"[ScriptSyncManager] ❌ 파일 저장 실패: {e}")

    @classmethod
    def _load_from_file(cls, project_path: str) -> Tuple[Optional[str], str]:
        """파일에서 로드"""
        try:
            project = Path(project_path)
            scripts_dir = project / "scripts"

            # 메타데이터에서 언어 확인
            meta_file = scripts_dir / "sync_meta.json"
            language = "ko"

            if meta_file.exists():
                try:
                    meta = json.loads(meta_file.read_text(encoding="utf-8"))
                    language = meta.get("language", "ko")
                except:
                    pass

            # 언어별 스크립트 파일 찾기 (우선순위)
            possible_files = [
                scripts_dir / f"draft_{language}.txt",
                scripts_dir / f"final_{language}.txt",
                scripts_dir / "draft_ko.txt",
                scripts_dir / "final_ko.txt",
                scripts_dir / "draft_ja.txt",
                scripts_dir / "final_ja.txt",
            ]

            for script_file in possible_files:
                if script_file.exists():
                    content = script_file.read_text(encoding="utf-8").strip()
                    if content:
                        # 파일명에서 언어 추출
                        if "_ko" in script_file.name:
                            language = "ko"
                        elif "_ja" in script_file.name:
                            language = "ja"
                        elif "_en" in script_file.name:
                            language = "en"

                        return content, language

        except Exception as e:
            print(f"[ScriptSyncManager] ❌ 파일 로드 실패: {e}")

        return None, "ko"

    @classmethod
    def clear(cls):
        """스크립트 데이터 초기화"""
        if not HAS_STREAMLIT:
            return

        for key in cls.SESSION_KEYS.values():
            if key in st.session_state:
                del st.session_state[key]

        cls._invalidate_caches()
        print("[ScriptSyncManager] 🗑️ 초기화 완료")


# 헬퍼 함수들
def sync_save_script(content: str, language: str = "ko", source: str = "manual", project_path: str = None) -> bool:
    """스크립트 저장 헬퍼"""
    return ScriptSyncManager.save_script(content, language, source, project_path)


def sync_load_script(project_path: str = None) -> Tuple[Optional[str], str]:
    """스크립트 로드 헬퍼"""
    return ScriptSyncManager.load_script(project_path)


def get_synced_script_info() -> Dict:
    """스크립트 정보 헬퍼"""
    return ScriptSyncManager.get_script_info()
