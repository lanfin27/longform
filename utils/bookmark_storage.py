# -*- coding: utf-8 -*-
"""
YouTube 영상/채널 보관함 모듈 v1.0

기능:
- 영상 보관/삭제
- 채널 보관/삭제
- 보관함 통계
- JSON 기반 영구 저장
"""

import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import DATA_DIR


class BookmarkStorage:
    """보관함 저장소"""

    def __init__(self, storage_dir: str = None):
        if storage_dir is None:
            storage_dir = DATA_DIR / "bookmarks"
        else:
            storage_dir = Path(storage_dir)

        self.storage_dir = storage_dir
        self.videos_file = storage_dir / "saved_videos.json"
        self.channels_file = storage_dir / "saved_channels.json"

        self._init_storage()

    def _init_storage(self):
        """저장소 초기화"""
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        for filepath in [self.videos_file, self.channels_file]:
            if not filepath.exists():
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump([], f)

    # ==================== 영상 보관 ====================

    def save_video(self, video: Dict) -> bool:
        """단일 영상 보관"""
        return self.save_videos([video]) > 0

    def save_videos(self, videos: List[Dict]) -> int:
        """영상 보관 (다건)"""
        existing = self._load_json(self.videos_file)
        existing_ids = {v['video_id'] for v in existing}

        new_count = 0
        for video in videos:
            video_id = video.get('video_id')
            if video_id and video_id not in existing_ids:
                video_copy = video.copy()
                video_copy['saved_at'] = datetime.now().isoformat()
                existing.append(video_copy)
                existing_ids.add(video_id)
                new_count += 1

        if new_count > 0:
            self._save_json(self.videos_file, existing)

        return new_count

    def get_saved_videos(self) -> List[Dict]:
        """저장된 영상 목록"""
        return self._load_json(self.videos_file)

    def get_video(self, video_id: str) -> Optional[Dict]:
        """특정 영상 조회"""
        videos = self.get_saved_videos()
        for v in videos:
            if v.get('video_id') == video_id:
                return v
        return None

    def is_video_saved(self, video_id: str) -> bool:
        """영상 저장 여부 확인"""
        videos = self.get_saved_videos()
        return any(v.get('video_id') == video_id for v in videos)

    def delete_video(self, video_id: str) -> bool:
        """영상 삭제"""
        videos = self._load_json(self.videos_file)
        filtered = [v for v in videos if v.get('video_id') != video_id]

        if len(filtered) < len(videos):
            self._save_json(self.videos_file, filtered)
            return True
        return False

    def delete_videos(self, video_ids: List[str]) -> int:
        """여러 영상 삭제"""
        videos = self._load_json(self.videos_file)
        ids_set = set(video_ids)
        filtered = [v for v in videos if v.get('video_id') not in ids_set]

        deleted = len(videos) - len(filtered)
        if deleted > 0:
            self._save_json(self.videos_file, filtered)
        return deleted

    def clear_videos(self):
        """모든 영상 삭제"""
        self._save_json(self.videos_file, [])

    # ==================== 채널 보관 ====================

    def save_channel(self, channel: Dict) -> bool:
        """단일 채널 보관"""
        return self.save_channels([channel]) > 0

    def save_channels(self, channels: List[Dict]) -> int:
        """채널 보관 (다건)"""
        existing = self._load_json(self.channels_file)
        existing_ids = {c['channel_id'] for c in existing if c.get('channel_id')}

        new_count = 0
        for channel in channels:
            channel_id = channel.get('channel_id')
            if channel_id and channel_id not in existing_ids:
                channel_copy = channel.copy()
                channel_copy['saved_at'] = datetime.now().isoformat()
                existing.append(channel_copy)
                existing_ids.add(channel_id)
                new_count += 1

        if new_count > 0:
            self._save_json(self.channels_file, existing)

        return new_count

    def get_saved_channels(self) -> List[Dict]:
        """저장된 채널 목록"""
        return self._load_json(self.channels_file)

    def get_channel(self, channel_id: str) -> Optional[Dict]:
        """특정 채널 조회"""
        channels = self.get_saved_channels()
        for c in channels:
            if c.get('channel_id') == channel_id:
                return c
        return None

    def is_channel_saved(self, channel_id: str) -> bool:
        """채널 저장 여부 확인"""
        channels = self.get_saved_channels()
        return any(c.get('channel_id') == channel_id for c in channels)

    def delete_channel(self, channel_id: str) -> bool:
        """채널 삭제"""
        channels = self._load_json(self.channels_file)
        filtered = [c for c in channels if c.get('channel_id') != channel_id]

        if len(filtered) < len(channels):
            self._save_json(self.channels_file, filtered)
            return True
        return False

    def delete_channels(self, channel_ids: List[str]) -> int:
        """여러 채널 삭제"""
        channels = self._load_json(self.channels_file)
        ids_set = set(channel_ids)
        filtered = [c for c in channels if c.get('channel_id') not in ids_set]

        deleted = len(channels) - len(filtered)
        if deleted > 0:
            self._save_json(self.channels_file, filtered)
        return deleted

    def clear_channels(self):
        """모든 채널 삭제"""
        self._save_json(self.channels_file, [])

    # ==================== 영상에서 채널 추출 ====================

    def save_channels_from_videos(self, videos: List[Dict]) -> int:
        """영상 목록에서 채널 정보 추출하여 저장"""
        channels = []
        seen = set()

        for video in videos:
            channel_id = video.get('channel_id')
            if channel_id and channel_id not in seen:
                seen.add(channel_id)
                channels.append({
                    'channel_id': channel_id,
                    'channel_title': video.get('channel_title', ''),
                    'channel_url': video.get('channel_url', ''),
                    'subscriber_count': video.get('subscriber_count', 0),
                    'thumbnail_url': video.get('channel_thumbnail_url', ''),
                })

        return self.save_channels(channels)

    # ==================== 유틸리티 ====================

    def _load_json(self, filepath: Path) -> List[Dict]:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except (json.JSONDecodeError, FileNotFoundError):
            return []

    def _save_json(self, filepath: Path, data: List[Dict]):
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def clear_all(self):
        """모든 보관함 초기화"""
        self._save_json(self.videos_file, [])
        self._save_json(self.channels_file, [])

    def get_stats(self) -> Dict:
        """보관함 통계"""
        videos = self.get_saved_videos()
        channels = self.get_saved_channels()

        stats = {
            'videos_count': len(videos),
            'channels_count': len(channels),
        }

        # 영상 통계
        if videos:
            total_views = sum(v.get('view_count', 0) for v in videos)
            stats['total_views'] = total_views
            stats['avg_views'] = total_views // len(videos)

        # 채널 통계
        if channels:
            total_subs = sum(c.get('subscriber_count', 0) for c in channels)
            stats['total_subscribers'] = total_subs
            stats['avg_subscribers'] = total_subs // len(channels)

        return stats

    def export_to_dict(self) -> Dict:
        """보관함 전체를 딕셔너리로 내보내기"""
        return {
            'videos': self.get_saved_videos(),
            'channels': self.get_saved_channels(),
            'exported_at': datetime.now().isoformat()
        }

    def import_from_dict(self, data: Dict) -> Dict:
        """딕셔너리에서 보관함 가져오기"""
        videos_count = 0
        channels_count = 0

        if 'videos' in data and isinstance(data['videos'], list):
            videos_count = self.save_videos(data['videos'])

        if 'channels' in data and isinstance(data['channels'], list):
            channels_count = self.save_channels(data['channels'])

        return {
            'videos_imported': videos_count,
            'channels_imported': channels_count
        }
