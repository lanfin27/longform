# -*- coding: utf-8 -*-
"""
utils/sync_manager.py
프로세스 간 데이터 동기화 관리
"""

import os
import json
import streamlit as st
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum


class ProcessType(Enum):
    """프로세스 타입"""
    SCENE_ANALYSIS = "scene_analysis"       # 씬 분석
    SCRIPT_GENERATION = "script_generation" # 스크립트 생성
    CHARACTER_MANAGEMENT = "character"      # 캐릭터 관리
    TTS_GENERATION = "tts_generation"       # TTS 생성
    IMAGE_PROMPT = "image_prompt"           # 이미지 프롬프트
    IMAGE_GENERATION = "image_generation"   # 이미지 생성
    VREW_EXPORT = "vrew_export"            # Vrew Export
    STORYBOARD = "storyboard"              # 스토리보드


class SyncManager:
    """프로세스 간 동기화 관리자"""

    # 세션 스테이트 키 매핑
    SESSION_KEYS = {
        ProcessType.SCENE_ANALYSIS: {
            "scenes": "scenes",
            "result": "scene_analysis_result",
            "characters": "scene_characters"
        },
        ProcessType.SCRIPT_GENERATION: {
            "scripts": "generated_scripts",
        },
        ProcessType.TTS_GENERATION: {
            "audio_files": "tts_audio_files",
            "audio_map": "scene_audio_map",
        },
        ProcessType.IMAGE_GENERATION: {
            "images": "generated_images",
            "image_map": "scene_image_map",
            "background_images": "background_images",
            "composited_images": "composited_images",
        },
        ProcessType.VREW_EXPORT: {
            "export_data": "vrew_export_data",
            "scenes": "vrew_scenes",
        },
        ProcessType.STORYBOARD: {
            "selections": "storyboard_selections",
            "scenes": "storyboard_scenes",
        }
    }

    # 프로세스 간 의존성 정의
    DEPENDENCIES = {
        ProcessType.SCRIPT_GENERATION: [ProcessType.SCENE_ANALYSIS],
        ProcessType.TTS_GENERATION: [ProcessType.SCRIPT_GENERATION],
        ProcessType.IMAGE_PROMPT: [ProcessType.SCENE_ANALYSIS, ProcessType.SCRIPT_GENERATION],
        ProcessType.IMAGE_GENERATION: [ProcessType.IMAGE_PROMPT],
        ProcessType.VREW_EXPORT: [ProcessType.TTS_GENERATION, ProcessType.IMAGE_GENERATION],
        ProcessType.STORYBOARD: [ProcessType.IMAGE_GENERATION]
    }

    def __init__(self, project_path: str = None, video_path: str = None):
        self.project_path = Path(project_path) if project_path else None
        self.video_path = Path(video_path) if video_path else None
        self.sync_log_path = self.video_path / "sync_log.json" if self.video_path else None

    # ============================================================
    # 동기화 상태 확인
    # ============================================================

    def get_sync_status(self) -> Dict[str, Dict]:
        """모든 프로세스의 동기화 상태 확인"""

        status = {}

        for process in ProcessType:
            status[process.value] = {
                "name": self._get_process_name(process),
                "has_data": self._has_process_data(process),
                "data_count": self._get_data_count(process),
                "last_updated": self._get_last_updated(process),
                "is_synced": self._is_synced_with_dependencies(process)
            }

        return status

    def _get_process_name(self, process: ProcessType) -> str:
        """프로세스 한글 이름"""
        names = {
            ProcessType.SCENE_ANALYSIS: "씬 분석",
            ProcessType.SCRIPT_GENERATION: "스크립트 생성",
            ProcessType.CHARACTER_MANAGEMENT: "캐릭터 관리",
            ProcessType.TTS_GENERATION: "TTS 생성",
            ProcessType.IMAGE_PROMPT: "이미지 프롬프트",
            ProcessType.IMAGE_GENERATION: "이미지 생성",
            ProcessType.VREW_EXPORT: "Vrew Export",
            ProcessType.STORYBOARD: "스토리보드"
        }
        return names.get(process, process.value)

    def _has_process_data(self, process: ProcessType) -> bool:
        """프로세스에 데이터가 있는지 확인"""

        keys = self.SESSION_KEYS.get(process, {})

        for key in keys.values():
            if st.session_state.get(key):
                return True

        return False

    def _get_data_count(self, process: ProcessType) -> int:
        """프로세스 데이터 개수"""

        keys = self.SESSION_KEYS.get(process, {})

        # 주요 데이터 키에서 개수 추출
        for data_key in ["scenes", "scripts", "audio_files", "images", "selections", "background_images", "composited_images"]:
            if data_key in keys:
                data = st.session_state.get(keys[data_key], [])
                if isinstance(data, list):
                    return len(data)
                elif isinstance(data, dict):
                    return len(data)

        return 0

    def _get_last_updated(self, process: ProcessType) -> Optional[str]:
        """마지막 업데이트 시간"""

        timestamp_key = f"{process.value}_last_updated"
        return st.session_state.get(timestamp_key)

    def _is_synced_with_dependencies(self, process: ProcessType) -> bool:
        """의존성과 동기화 상태 확인"""

        dependencies = self.DEPENDENCIES.get(process, [])

        if not dependencies:
            return True

        process_time = self._get_last_updated(process)
        if not process_time:
            return False

        for dep in dependencies:
            dep_time = self._get_last_updated(dep)
            if dep_time and dep_time > process_time:
                return False  # 의존성이 더 최신 → 동기화 필요

        return True

    # ============================================================
    # 데이터 동기화 실행
    # ============================================================

    def sync_to_vrew_export(self) -> Dict[str, Any]:
        """이미지 생성 + TTS → Vrew Export 동기화"""

        result = {
            "success": False,
            "synced_images": 0,
            "synced_audio": 0,
            "message": ""
        }

        try:
            # Vrew Export 데이터 가져오기 또는 생성
            vrew_scenes = st.session_state.get("vrew_scenes", [])

            if not vrew_scenes:
                # 씬 분석 데이터에서 생성
                analyzed_scenes = st.session_state.get("scenes", [])
                if analyzed_scenes:
                    vrew_scenes = [dict(s) if isinstance(s, dict) else s for s in analyzed_scenes]
                else:
                    result["message"] = "씬 데이터가 없습니다. 먼저 씬 분석을 실행하세요."
                    return result

            # 이미지 동기화
            image_map = st.session_state.get("scene_image_map", {})
            background_images = st.session_state.get("background_images", {})
            composited_images = st.session_state.get("composited_images", {})

            for idx, scene in enumerate(vrew_scenes):
                scene_num = scene.get("scene_id") or scene.get("scene_num") or scene.get("index", idx + 1)

                # 합성 이미지 우선
                if str(scene_num) in composited_images:
                    scene["image_path"] = composited_images[str(scene_num)]
                    result["synced_images"] += 1
                # 배경 이미지
                elif str(scene_num) in background_images:
                    scene["image_path"] = background_images[str(scene_num)]
                    result["synced_images"] += 1
                # 이미지 맵
                elif scene_num in image_map:
                    scene["image_path"] = image_map[scene_num]
                    result["synced_images"] += 1

            # TTS 동기화
            audio_map = st.session_state.get("scene_audio_map", {})

            for idx, scene in enumerate(vrew_scenes):
                scene_num = scene.get("scene_id") or scene.get("scene_num") or scene.get("index", idx + 1)

                if scene_num in audio_map:
                    scene["audio_path"] = audio_map[scene_num]
                    result["synced_audio"] += 1

            # 세션에 저장
            st.session_state["vrew_scenes"] = vrew_scenes
            st.session_state["vrew_export_last_updated"] = datetime.now().isoformat()

            result["success"] = True
            result["message"] = f"이미지 {result['synced_images']}개, 음성 {result['synced_audio']}개 동기화 완료"

            # 로그 저장
            self._save_sync_log("vrew_export", result)

        except Exception as e:
            result["message"] = f"동기화 오류: {str(e)}"

        return result

    def sync_to_storyboard(self) -> Dict[str, Any]:
        """이미지 생성 + 인포그래픽 + 동영상 → 스토리보드 동기화"""

        result = {
            "success": False,
            "synced_images": 0,
            "synced_infographics": 0,
            "synced_videos": 0,
            "message": ""
        }

        try:
            # 스토리보드 데이터 가져오기 또는 생성
            storyboard_scenes = st.session_state.get("storyboard_scenes", [])

            if not storyboard_scenes:
                analyzed_scenes = st.session_state.get("scenes", [])
                if analyzed_scenes:
                    storyboard_scenes = [dict(s) if isinstance(s, dict) else s for s in analyzed_scenes]
                else:
                    result["message"] = "씬 데이터가 없습니다."
                    return result

            # AI 이미지/배경 이미지 동기화
            background_images = st.session_state.get("background_images", {})
            composited_images = st.session_state.get("composited_images", {})

            for idx, scene in enumerate(storyboard_scenes):
                scene_num = scene.get("scene_id") or scene.get("scene_num") or scene.get("index", idx + 1)

                # 합성 이미지
                if str(scene_num) in composited_images:
                    scene["ai_image_path"] = composited_images[str(scene_num)]
                    result["synced_images"] += 1
                # 배경 이미지
                elif str(scene_num) in background_images:
                    scene["ai_image_path"] = background_images[str(scene_num)]
                    result["synced_images"] += 1

            # 인포그래픽 동기화
            infographic_map = st.session_state.get("scene_infographic_map", {})

            for idx, scene in enumerate(storyboard_scenes):
                scene_num = scene.get("scene_id") or scene.get("scene_num") or scene.get("index", idx + 1)

                if scene_num in infographic_map:
                    scene["infographic_path"] = infographic_map[scene_num]
                    result["synced_infographics"] += 1

            # 동영상 동기화
            video_map = st.session_state.get("scene_video_map", {})

            for idx, scene in enumerate(storyboard_scenes):
                scene_num = scene.get("scene_id") or scene.get("scene_num") or scene.get("index", idx + 1)

                if scene_num in video_map:
                    scene["video_path"] = video_map[scene_num]
                    result["synced_videos"] += 1

            # 세션에 저장
            st.session_state["storyboard_scenes"] = storyboard_scenes
            st.session_state["storyboard_last_updated"] = datetime.now().isoformat()

            result["success"] = True
            result["message"] = (
                f"이미지 {result['synced_images']}개, "
                f"인포그래픽 {result['synced_infographics']}개, "
                f"동영상 {result['synced_videos']}개 동기화 완료"
            )

            self._save_sync_log("storyboard", result)

        except Exception as e:
            result["message"] = f"동기화 오류: {str(e)}"

        return result

    def sync_scenes_to_all(self) -> Dict[str, Any]:
        """씬 분석 결과를 모든 프로세스에 동기화"""

        result = {
            "success": False,
            "synced_processes": [],
            "message": ""
        }

        try:
            scenes = st.session_state.get("scenes", [])

            if not scenes:
                result["message"] = "씬 분석 데이터가 없습니다."
                return result

            # 스크립트 생성에 동기화
            st.session_state["script_scenes"] = [dict(s) if isinstance(s, dict) else s for s in scenes]
            result["synced_processes"].append("스크립트 생성")

            # 이미지 프롬프트에 동기화
            st.session_state["prompt_scenes"] = [dict(s) if isinstance(s, dict) else s for s in scenes]
            result["synced_processes"].append("이미지 프롬프트")

            # 이미지 생성에 동기화
            st.session_state["image_gen_scenes"] = [dict(s) if isinstance(s, dict) else s for s in scenes]
            result["synced_processes"].append("이미지 생성")

            # 타임스탬프 업데이트
            st.session_state["scene_analysis_last_updated"] = datetime.now().isoformat()

            result["success"] = True
            result["message"] = f"{len(result['synced_processes'])}개 프로세스에 씬 데이터 동기화 완료"

        except Exception as e:
            result["message"] = f"동기화 오류: {str(e)}"

        return result

    def sync_images_from_folder(self, folder_path: str = None) -> Dict[str, Any]:
        """폴더에서 이미지 스캔하여 씬에 매핑"""

        result = {
            "success": False,
            "found_images": 0,
            "mapped_scenes": 0,
            "message": ""
        }

        try:
            if not folder_path:
                # 프로젝트 폴더에서 이미지 폴더 찾기
                if self.video_path:
                    folder_path = self.video_path / "images"
                elif self.project_path:
                    # 프로젝트 내 images 폴더들 스캔
                    possible_paths = [
                        self.project_path / "images",
                        self.project_path / "scene_images",
                        self.project_path / "composited",
                    ]
                    for p in possible_paths:
                        if p.exists():
                            folder_path = p
                            break

            if not folder_path or not Path(folder_path).exists():
                result["message"] = "이미지 폴더를 찾을 수 없습니다."
                return result

            folder = Path(folder_path)
            image_map = {}
            background_images = {}

            # 이미지 파일 스캔
            for ext in ['*.png', '*.jpg', '*.jpeg', '*.webp']:
                for img_path in folder.glob(ext):
                    result["found_images"] += 1

                    # 파일명에서 씬 번호 추출
                    import re
                    # 패턴: scene_001, scene001, composited_001, background_001 등
                    match = re.search(r'(?:scene|composited|background)[_\-]?(\d+)', img_path.stem, re.IGNORECASE)
                    if match:
                        scene_num = int(match.group(1))
                        image_map[scene_num] = str(img_path)
                        background_images[str(scene_num)] = str(img_path)
                        result["mapped_scenes"] += 1
                    else:
                        # 숫자만 있는 패턴 시도: 001.png, 1.png
                        match2 = re.search(r'^(\d+)', img_path.stem)
                        if match2:
                            scene_num = int(match2.group(1))
                            image_map[scene_num] = str(img_path)
                            background_images[str(scene_num)] = str(img_path)
                            result["mapped_scenes"] += 1

            # 세션에 저장
            if image_map:
                st.session_state["scene_image_map"] = image_map
                st.session_state["background_images"] = background_images
                st.session_state["image_generation_last_updated"] = datetime.now().isoformat()

            result["success"] = True
            result["message"] = f"{result['found_images']}개 이미지 발견, {result['mapped_scenes']}개 씬 매핑"

        except Exception as e:
            result["message"] = f"스캔 오류: {str(e)}"

        return result

    def sync_audio_from_folder(self, folder_path: str = None) -> Dict[str, Any]:
        """폴더에서 오디오 스캔하여 씬에 매핑"""

        result = {
            "success": False,
            "found_audio": 0,
            "mapped_scenes": 0,
            "message": ""
        }

        try:
            if not folder_path:
                if self.video_path:
                    folder_path = self.video_path / "audio"
                elif self.project_path:
                    possible_paths = [
                        self.project_path / "audio",
                        self.project_path / "tts",
                    ]
                    for p in possible_paths:
                        if p.exists():
                            folder_path = p
                            break

            if not folder_path or not Path(folder_path).exists():
                result["message"] = "오디오 폴더를 찾을 수 없습니다."
                return result

            folder = Path(folder_path)
            audio_map = {}

            # 오디오 파일 스캔
            for ext in ['*.mp3', '*.wav', '*.ogg', '*.m4a']:
                for audio_path in folder.glob(ext):
                    result["found_audio"] += 1

                    import re
                    match = re.search(r'(?:scene|tts)[_\-]?(\d+)', audio_path.stem, re.IGNORECASE)
                    if match:
                        scene_num = int(match.group(1))
                        audio_map[scene_num] = str(audio_path)
                        result["mapped_scenes"] += 1
                    else:
                        match2 = re.search(r'^(\d+)', audio_path.stem)
                        if match2:
                            scene_num = int(match2.group(1))
                            audio_map[scene_num] = str(audio_path)
                            result["mapped_scenes"] += 1

            if audio_map:
                st.session_state["scene_audio_map"] = audio_map
                st.session_state["tts_generation_last_updated"] = datetime.now().isoformat()

            result["success"] = True
            result["message"] = f"{result['found_audio']}개 오디오 발견, {result['mapped_scenes']}개 씬 매핑"

        except Exception as e:
            result["message"] = f"스캔 오류: {str(e)}"

        return result

    # ============================================================
    # 로그 관리
    # ============================================================

    def _save_sync_log(self, process: str, result: Dict):
        """동기화 로그 저장"""

        if not self.sync_log_path:
            return

        try:
            log = []
            if self.sync_log_path.exists():
                with open(self.sync_log_path, 'r', encoding='utf-8') as f:
                    log = json.load(f)

            log.append({
                "process": process,
                "timestamp": datetime.now().isoformat(),
                "result": result
            })

            # 최근 100개만 유지
            log = log[-100:]

            with open(self.sync_log_path, 'w', encoding='utf-8') as f:
                json.dump(log, f, ensure_ascii=False, indent=2)

        except Exception as e:
            print(f"[SyncManager] 로그 저장 실패: {e}")

    def get_sync_log(self, limit: int = 20) -> List[Dict]:
        """동기화 로그 조회"""

        if not self.sync_log_path or not self.sync_log_path.exists():
            return []

        try:
            with open(self.sync_log_path, 'r', encoding='utf-8') as f:
                log = json.load(f)
            return log[-limit:]
        except Exception:
            return []


# ============================================================
# 헬퍼 함수
# ============================================================

def get_sync_manager() -> SyncManager:
    """SyncManager 인스턴스 생성"""

    project_path = st.session_state.get("current_project_path")
    video_path = st.session_state.get("current_video_path")

    return SyncManager(project_path, video_path)


def auto_sync_on_process_complete(process: ProcessType):
    """프로세스 완료 시 자동 동기화"""

    manager = get_sync_manager()

    # 타임스탬프 업데이트
    st.session_state[f"{process.value}_last_updated"] = datetime.now().isoformat()

    # 의존하는 프로세스 자동 동기화
    if process == ProcessType.IMAGE_GENERATION:
        manager.sync_to_vrew_export()
        manager.sync_to_storyboard()

    elif process == ProcessType.SCENE_ANALYSIS:
        manager.sync_scenes_to_all()
