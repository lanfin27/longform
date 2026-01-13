# -*- coding: utf-8 -*-
"""
프로젝트 초기화 관리자 (v1.0)

3단계 레벨의 프로젝트 초기화 기능:
1. 영상(Video) 초기화 - 특정 영상의 모든 산출물 삭제
2. 채널(Channel) 초기화 - 특정 채널의 모든 영상 삭제
3. 전체(All) 초기화 - 모든 프로젝트 삭제

삭제 모드:
- Hard Delete: 실제 파일 삭제 (복구 불가)
- Soft Delete: 숨김 처리 (복구 가능)
"""

import os
import shutil
import json
from pathlib import Path
from datetime import datetime
from typing import Literal, Optional, List, Dict, Any, Set
from enum import Enum


class DeleteMode(Enum):
    """삭제 모드"""
    HARD = "hard"  # 실제 삭제
    SOFT = "soft"  # 숨김 처리


class ProjectResetManager:
    """프로젝트 초기화 관리자"""

    HIDDEN_MARKER = ".longform_hidden"
    DELETED_MARKER = ".longform_deleted"

    def __init__(self, base_path: str = None):
        """
        Args:
            base_path: 데이터 기본 경로 (기본값: longform/data)
        """
        if base_path is None:
            # 기본 경로 설정
            self.base_path = Path(__file__).parent.parent / "data"
        else:
            self.base_path = Path(base_path)

        self.projects_path = self.base_path / "projects"
        self.images_path = self.base_path / "images"
        self.config_path = self.base_path / "config"
        self.cache_path = self.base_path / "cache"
        self.temp_path = self.base_path / "temp"
        self.settings_path = self.base_path / "settings"

        print(f"[ProjectResetManager] 초기화: {self.base_path}", flush=True)

    # ========================================
    # 프로젝트/채널/영상 조회
    # ========================================

    def get_all_projects(self) -> List[Dict[str, Any]]:
        """모든 프로젝트 목록 반환"""
        projects = []

        if not self.projects_path.exists():
            return projects

        for project_dir in self.projects_path.iterdir():
            if project_dir.is_dir() and not project_dir.name.startswith('.'):
                # 숨김 처리된 항목 제외
                if self._is_hidden(project_dir):
                    continue

                project_info = self._parse_project_name(project_dir.name)
                project_info['path'] = str(project_dir)
                project_info['size'] = self._get_size(project_dir)
                project_info['file_count'] = self._count_files(project_dir)

                # 영상 목록
                videos_path = project_dir / "videos"
                if videos_path.exists():
                    project_info['videos'] = [
                        v.name for v in videos_path.iterdir()
                        if v.is_dir() and not v.name.startswith('.') and not self._is_hidden(v)
                    ]
                else:
                    project_info['videos'] = []

                projects.append(project_info)

        return projects

    def get_all_channels(self) -> List[str]:
        """모든 채널 목록 반환"""
        channels = set()

        for project in self.get_all_projects():
            if project.get('channel'):
                channels.add(project['channel'])

        return sorted(list(channels))

    def get_channel_projects(self, channel_name: str) -> List[Dict[str, Any]]:
        """특정 채널의 프로젝트 목록"""
        return [
            p for p in self.get_all_projects()
            if p.get('channel') == channel_name
        ]

    def get_project_videos(self, project_id: str) -> List[Dict[str, Any]]:
        """특정 프로젝트의 영상 목록"""
        project_path = self.projects_path / project_id

        if not project_path.exists():
            return []

        videos = []
        videos_path = project_path / "videos"

        if videos_path.exists():
            for video_dir in videos_path.iterdir():
                if video_dir.is_dir() and not video_dir.name.startswith('.'):
                    if self._is_hidden(video_dir):
                        continue

                    videos.append({
                        'video_id': video_dir.name,
                        'path': str(video_dir),
                        'size': self._get_size(video_dir),
                        'file_count': self._count_files(video_dir),
                        'assets': self._get_video_asset_summary(video_dir)
                    })

        return videos

    def _parse_project_name(self, name: str) -> Dict[str, Any]:
        """프로젝트 이름에서 정보 추출 (예: 20251214_144057_시니어)"""
        parts = name.split('_')

        if len(parts) >= 3:
            # 타임스탬프_시간_채널명 형식
            try:
                date_str = parts[0]
                time_str = parts[1]
                channel = '_'.join(parts[2:])  # 채널명에 언더스코어가 있을 수 있음

                return {
                    'project_id': name,
                    'date': date_str,
                    'time': time_str,
                    'channel': channel,
                    'created': f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]} {time_str[:2]}:{time_str[2:4]}:{time_str[4:6]}"
                }
            except:
                pass

        return {
            'project_id': name,
            'date': '',
            'time': '',
            'channel': name,
            'created': ''
        }

    def _get_video_asset_summary(self, video_path: Path) -> Dict[str, int]:
        """영상 에셋 요약"""
        summary = {
            'analysis': 0,
            'images': 0,
            'audio': 0,
            'videos': 0,
            'scripts': 0,
            'other': 0
        }

        asset_dirs = {
            'analysis': video_path / 'analysis',
            'images': video_path / 'images',
            'audio': video_path / 'audio',
            'videos': video_path / 'videos',
            'scripts': video_path / 'scripts',
        }

        for key, path in asset_dirs.items():
            if path.exists():
                summary[key] = self._count_files(path)

        return summary

    # ========================================
    # 영상 프로젝트 초기화
    # ========================================

    def reset_video(
        self,
        project_id: str,
        video_id: str,
        mode: DeleteMode = DeleteMode.HARD,
        confirm: bool = False
    ) -> Dict[str, Any]:
        """
        영상 프로젝트 초기화

        Args:
            project_id: 프로젝트 ID (예: "20251214_144057_시니어")
            video_id: 영상 ID (예: "20251214_144057_시니어")
            mode: 삭제 모드 (HARD: 실제 삭제, SOFT: 숨김)
            confirm: 확인 여부 (True여야 실행)

        Returns:
            {
                'success': bool,
                'mode': str,
                'deleted_items': list,
                'total_size': int,
                'errors': list
            }
        """
        result = {
            'success': False,
            'mode': mode.value,
            'project_id': project_id,
            'video_id': video_id,
            'deleted_items': [],
            'total_size': 0,
            'errors': []
        }

        if not confirm:
            result['errors'].append("확인되지 않음. confirm=True 필요")
            return result

        video_path = self.projects_path / project_id / "videos" / video_id

        if not video_path.exists():
            result['errors'].append(f"영상 폴더를 찾을 수 없음: {video_path}")
            return result

        print(f"[영상 초기화] 시작: {project_id}/{video_id} (모드: {mode.value})", flush=True)

        # 삭제할 에셋 폴더들
        asset_folders = [
            'analysis',      # 씬 분석 데이터
            'images',        # 이미지 (backgrounds, characters)
            'audio',         # TTS 오디오
            'videos',        # 비디오 파일
            'output',        # 최종 출력물
            'export',        # 내보내기
            'infographics',  # 인포그래픽
            'prompts',       # 프롬프트
            'data',          # 데이터
            'presets',       # 프리셋
        ]

        for folder_name in asset_folders:
            folder_path = video_path / folder_name

            if folder_path.exists():
                try:
                    size = self._get_size(folder_path)

                    if mode == DeleteMode.HARD:
                        shutil.rmtree(str(folder_path))
                        print(f"[영상 초기화] 삭제: {folder_name} ({size / 1024:.1f} KB)", flush=True)
                    else:
                        self._soft_delete(folder_path)
                        print(f"[영상 초기화] 숨김: {folder_name}", flush=True)

                    result['deleted_items'].append(folder_name)
                    result['total_size'] += size

                except Exception as e:
                    result['errors'].append(f"{folder_name}: {str(e)}")
                    print(f"[영상 초기화] ❌ 오류: {folder_name}: {e}", flush=True)

        # JSON 파일들 삭제
        json_patterns = ['*.json', 'scenes/*.json']
        for pattern in json_patterns:
            for json_file in video_path.glob(pattern):
                if json_file.is_file() and not json_file.name.startswith('.'):
                    try:
                        size = json_file.stat().st_size

                        if mode == DeleteMode.HARD:
                            json_file.unlink()
                        else:
                            self._soft_delete(json_file)

                        result['deleted_items'].append(json_file.name)
                        result['total_size'] += size
                        print(f"[영상 초기화] {'삭제' if mode == DeleteMode.HARD else '숨김'}: {json_file.name}", flush=True)

                    except Exception as e:
                        result['errors'].append(f"{json_file.name}: {str(e)}")

        result['success'] = len(result['errors']) == 0
        print(f"[영상 초기화] 완료: {len(result['deleted_items'])}개 처리, {result['total_size'] / 1024 / 1024:.2f} MB", flush=True)

        return result

    # ========================================
    # 채널 프로젝트 초기화
    # ========================================

    def reset_channel(
        self,
        channel_name: str,
        mode: DeleteMode = DeleteMode.HARD,
        confirm: bool = False
    ) -> Dict[str, Any]:
        """
        채널 프로젝트 초기화 (해당 채널의 모든 프로젝트)

        Args:
            channel_name: 채널명
            mode: 삭제 모드
            confirm: 확인 여부
        """
        result = {
            'success': False,
            'mode': mode.value,
            'channel': channel_name,
            'projects_deleted': [],
            'videos_deleted': [],
            'total_size': 0,
            'errors': []
        }

        if not confirm:
            result['errors'].append("확인되지 않음")
            return result

        print(f"[채널 초기화] 시작: {channel_name} (모드: {mode.value})", flush=True)

        # 채널에 속한 모든 프로젝트 찾기
        projects = self.get_channel_projects(channel_name)

        if not projects:
            result['errors'].append(f"채널 '{channel_name}'에 프로젝트가 없음")
            return result

        print(f"[채널 초기화] {len(projects)}개 프로젝트 발견", flush=True)

        # 각 프로젝트 처리
        for project in projects:
            project_id = project['project_id']
            project_path = Path(project['path'])

            # 프로젝트 내 모든 영상 처리
            for video in project.get('videos', []):
                video_result = self.reset_video(
                    project_id=project_id,
                    video_id=video,
                    mode=mode,
                    confirm=True
                )

                if video_result['success']:
                    result['videos_deleted'].append(video)
                    result['total_size'] += video_result['total_size']
                else:
                    result['errors'].extend(video_result['errors'])

            # 프로젝트 폴더 자체 처리
            try:
                if mode == DeleteMode.HARD:
                    # 프로젝트 루트의 다른 폴더들도 삭제
                    for item in project_path.iterdir():
                        if item.is_dir() and item.name != 'videos':
                            size = self._get_size(item)
                            shutil.rmtree(str(item))
                            result['total_size'] += size
                        elif item.is_file():
                            result['total_size'] += item.stat().st_size
                            item.unlink()

                    # 빈 프로젝트 폴더 삭제
                    if not any(project_path.iterdir()):
                        project_path.rmdir()
                        print(f"[채널 초기화] 프로젝트 폴더 삭제: {project_id}", flush=True)
                else:
                    self._soft_delete(project_path)

                result['projects_deleted'].append(project_id)

            except Exception as e:
                result['errors'].append(f"프로젝트 {project_id}: {str(e)}")
                print(f"[채널 초기화] ❌ 프로젝트 처리 오류: {e}", flush=True)

        result['success'] = len(result['errors']) == 0
        print(f"[채널 초기화] 완료: {len(result['projects_deleted'])}개 프로젝트, {len(result['videos_deleted'])}개 영상", flush=True)

        return result

    # ========================================
    # 전체 초기화
    # ========================================

    def reset_all(
        self,
        mode: DeleteMode = DeleteMode.HARD,
        confirm: bool = False,
        keep_settings: bool = True,
        delete_cache: bool = True
    ) -> Dict[str, Any]:
        """
        전체 프로젝트 초기화 (모든 채널, 모든 프로젝트)

        Args:
            mode: 삭제 모드
            confirm: 확인 여부
            keep_settings: 설정 파일 유지 여부
            delete_cache: 캐시 삭제 여부
        """
        result = {
            'success': False,
            'mode': mode.value,
            'channels_deleted': [],
            'projects_deleted': [],
            'total_videos': 0,
            'total_size': 0,
            'errors': []
        }

        if not confirm:
            result['errors'].append("확인되지 않음")
            return result

        print(f"[전체 초기화] 시작 (모드: {mode.value})", flush=True)

        # 모든 채널 처리
        channels = self.get_all_channels()
        print(f"[전체 초기화] {len(channels)}개 채널 발견", flush=True)

        for channel in channels:
            channel_result = self.reset_channel(
                channel_name=channel,
                mode=mode,
                confirm=True
            )

            if channel_result['success']:
                result['channels_deleted'].append(channel)
                result['projects_deleted'].extend(channel_result['projects_deleted'])
                result['total_videos'] += len(channel_result['videos_deleted'])
                result['total_size'] += channel_result['total_size']
            else:
                result['errors'].extend(channel_result['errors'])

        # 캐시 삭제
        if delete_cache and mode == DeleteMode.HARD:
            cache_result = self._clear_cache()
            result['total_size'] += cache_result.get('size', 0)

        # 설정 초기화
        if not keep_settings and mode == DeleteMode.HARD:
            self._reset_settings()

        result['success'] = len(result['errors']) == 0
        print(f"[전체 초기화] 완료: {len(result['channels_deleted'])}개 채널, {result['total_videos']}개 영상, {result['total_size'] / 1024 / 1024:.2f} MB", flush=True)

        return result

    def _clear_cache(self) -> Dict[str, Any]:
        """캐시 삭제"""
        result = {'size': 0, 'deleted': []}

        cache_dirs = [
            self.cache_path,
            self.temp_path,
            self.images_path / "imagefx",
            self.images_path / "generated",
            self.images_path / "temp",
        ]

        for cache_dir in cache_dirs:
            if cache_dir.exists():
                try:
                    size = self._get_size(cache_dir)
                    shutil.rmtree(str(cache_dir))
                    result['size'] += size
                    result['deleted'].append(str(cache_dir))
                    print(f"[캐시 삭제] {cache_dir.name}: {size / 1024 / 1024:.2f} MB", flush=True)
                except Exception as e:
                    print(f"[캐시 삭제] ❌ 오류: {cache_dir}: {e}", flush=True)

        return result

    def _reset_settings(self):
        """설정 초기화"""
        settings_to_reset = [
            self.config_path / "last_project.json",
            self.config_path / "recent_projects.json",
            self.settings_path / "api_preferences.json",
        ]

        for settings_file in settings_to_reset:
            if settings_file.exists():
                try:
                    settings_file.unlink()
                    print(f"[설정 초기화] 삭제: {settings_file.name}", flush=True)
                except Exception as e:
                    print(f"[설정 초기화] ❌ 오류: {e}", flush=True)

    # ========================================
    # 소프트 삭제 / 복구
    # ========================================

    def _soft_delete(self, path: Path):
        """소프트 삭제 (숨김 처리)"""
        marker_path = path.parent / f"{path.name}{self.HIDDEN_MARKER}"

        marker_data = {
            'hidden_at': datetime.now().isoformat(),
            'original_path': str(path),
            'type': 'file' if path.is_file() else 'directory',
            'size': self._get_size(path) if path.exists() else 0
        }

        with open(marker_path, 'w', encoding='utf-8') as f:
            json.dump(marker_data, f, ensure_ascii=False, indent=2)

    def _is_hidden(self, path: Path) -> bool:
        """숨김 처리 여부 확인"""
        marker_path = path.parent / f"{path.name}{self.HIDDEN_MARKER}"
        return marker_path.exists()

    def restore_hidden(self, path: Path) -> bool:
        """숨김 해제 (복구)"""
        marker_path = path.parent / f"{path.name}{self.HIDDEN_MARKER}"

        if marker_path.exists():
            try:
                marker_path.unlink()
                print(f"[복구] 숨김 해제: {path.name}", flush=True)
                return True
            except Exception as e:
                print(f"[복구] ❌ 오류: {e}", flush=True)
                return False

        return False

    def get_hidden_items(self, base_path: Path = None) -> List[Dict[str, Any]]:
        """숨김 처리된 항목 목록"""
        if base_path is None:
            base_path = self.projects_path

        hidden_items = []

        if not base_path.exists():
            return hidden_items

        for marker in base_path.rglob(f"*{self.HIDDEN_MARKER}"):
            try:
                with open(marker, 'r', encoding='utf-8') as f:
                    marker_data = json.load(f)

                hidden_items.append({
                    'marker_path': str(marker),
                    'original_path': marker_data.get('original_path', ''),
                    'name': Path(marker_data.get('original_path', '')).name,
                    'type': marker_data.get('type', 'unknown'),
                    'hidden_at': marker_data.get('hidden_at', ''),
                    'size': marker_data.get('size', 0)
                })
            except Exception as e:
                print(f"[숨김 목록] 마커 읽기 오류: {marker}: {e}", flush=True)

        return hidden_items

    def restore_all_hidden(self) -> Dict[str, Any]:
        """모든 숨김 항목 복구"""
        result = {'restored': [], 'errors': []}

        hidden_items = self.get_hidden_items()

        for item in hidden_items:
            try:
                marker_path = Path(item['marker_path'])
                if marker_path.exists():
                    marker_path.unlink()
                    result['restored'].append(item['name'])
            except Exception as e:
                result['errors'].append(f"{item['name']}: {str(e)}")

        print(f"[전체 복구] {len(result['restored'])}개 복구됨", flush=True)
        return result

    # ========================================
    # 미리보기
    # ========================================

    def preview_reset(
        self,
        level: Literal['video', 'channel', 'all'],
        project_id: str = None,
        video_id: str = None,
        channel_name: str = None
    ) -> Dict[str, Any]:
        """
        초기화 미리보기 (삭제될 항목 목록)
        """
        preview = {
            'level': level,
            'items': [],
            'total_size': 0,
            'total_files': 0,
            'total_folders': 0
        }

        if level == 'video' and project_id and video_id:
            video_path = self.projects_path / project_id / "videos" / video_id

            if video_path.exists():
                for item in video_path.iterdir():
                    if item.name.startswith('.'):
                        continue

                    size = self._get_size(item)
                    file_count = self._count_files(item) if item.is_dir() else 1

                    preview['items'].append({
                        'name': item.name,
                        'type': 'directory' if item.is_dir() else 'file',
                        'size': size,
                        'file_count': file_count
                    })
                    preview['total_size'] += size
                    preview['total_files'] += file_count
                    if item.is_dir():
                        preview['total_folders'] += 1

        elif level == 'channel' and channel_name:
            projects = self.get_channel_projects(channel_name)

            for project in projects:
                project_size = project.get('size', 0)
                project_files = project.get('file_count', 0)

                preview['items'].append({
                    'name': project['project_id'],
                    'type': 'project',
                    'size': project_size,
                    'file_count': project_files,
                    'videos': len(project.get('videos', []))
                })
                preview['total_size'] += project_size
                preview['total_files'] += project_files
                preview['total_folders'] += 1

        elif level == 'all':
            for project in self.get_all_projects():
                project_size = project.get('size', 0)
                project_files = project.get('file_count', 0)

                preview['items'].append({
                    'name': project['project_id'],
                    'type': 'project',
                    'size': project_size,
                    'file_count': project_files,
                    'channel': project.get('channel', ''),
                    'videos': len(project.get('videos', []))
                })
                preview['total_size'] += project_size
                preview['total_files'] += project_files
                preview['total_folders'] += 1

        return preview

    # ========================================
    # 유틸리티
    # ========================================

    def _get_size(self, path: Path) -> int:
        """파일/폴더 크기 계산 (bytes)"""
        if not path.exists():
            return 0

        if path.is_file():
            return path.stat().st_size

        total = 0
        try:
            for f in path.rglob('*'):
                if f.is_file():
                    try:
                        total += f.stat().st_size
                    except:
                        pass
        except:
            pass

        return total

    def _count_files(self, path: Path) -> int:
        """폴더 내 파일 개수"""
        if not path.exists():
            return 0

        if path.is_file():
            return 1

        try:
            return sum(1 for f in path.rglob('*') if f.is_file())
        except:
            return 0

    def format_size(self, size_bytes: int) -> str:
        """크기 포맷팅"""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / 1024 / 1024:.2f} MB"
        else:
            return f"{size_bytes / 1024 / 1024 / 1024:.2f} GB"


# ========================================
# 전역 인스턴스 함수
# ========================================

_manager_instance = None


def get_reset_manager() -> ProjectResetManager:
    """ProjectResetManager 싱글톤 인스턴스 반환"""
    global _manager_instance

    if _manager_instance is None:
        _manager_instance = ProjectResetManager()

    return _manager_instance
