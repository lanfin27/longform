# -*- coding: utf-8 -*-
"""
utils/youtube_channel_filter.py
YouTube 채널 생성일 기반 필터링 유틸리티

기존 YouTubeService의 채널 캐시를 활용하여
채널 생성일 기준으로 비디오 결과를 필터링

작성: 2025-01
"""

from datetime import datetime, timezone
from typing import List, Dict, Set, Optional, Tuple
import streamlit as st


class YouTubeChannelFilter:
    """YouTube 채널 생성일 필터링"""

    def __init__(self, youtube_service):
        """
        Args:
            youtube_service: YouTubeService 인스턴스
        """
        self.youtube = youtube_service
        self._additional_cache: Dict[str, Dict] = {}

    def get_channel_published_at(self, channel_id: str) -> Optional[datetime]:
        """
        채널 생성일 조회

        Args:
            channel_id: 채널 ID

        Returns:
            채널 생성일 (datetime) 또는 None
        """
        # YouTubeService 캐시에서 먼저 확인
        if hasattr(self.youtube, '_channel_cache') and channel_id in self.youtube._channel_cache:
            channel_info = self.youtube._channel_cache[channel_id]
            published_at_str = channel_info.get('published_at', '')

            if published_at_str:
                return self._parse_datetime(published_at_str)

        # 추가 캐시 확인
        if channel_id in self._additional_cache:
            return self._additional_cache[channel_id].get('published_at')

        # 없으면 API 조회
        channel_info = self.youtube.get_channel_details(channel_id)

        if channel_info:
            published_at_str = channel_info.get('published_at', '')
            if published_at_str:
                published_at = self._parse_datetime(published_at_str)
                self._additional_cache[channel_id] = {
                    'published_at': published_at,
                    **channel_info
                }
                return published_at

        return None

    def _parse_datetime(self, dt_str: str) -> Optional[datetime]:
        """날짜 문자열 파싱"""
        if not dt_str:
            return None

        try:
            # ISO 형식 파싱
            if 'Z' in dt_str:
                dt_str = dt_str.replace('Z', '+00:00')
            return datetime.fromisoformat(dt_str)
        except:
            pass

        # 다른 형식 시도
        formats = [
            '%Y-%m-%dT%H:%M:%S.%fZ',
            '%Y-%m-%dT%H:%M:%SZ',
            '%Y-%m-%dT%H:%M:%S',
            '%Y-%m-%d'
        ]

        for fmt in formats:
            try:
                return datetime.strptime(dt_str, fmt)
            except:
                continue

        return None

    def get_channels_published_at_batch(
        self,
        channel_ids: List[str]
    ) -> Dict[str, Optional[datetime]]:
        """
        채널 생성일 일괄 조회

        Args:
            channel_ids: 채널 ID 리스트

        Returns:
            {channel_id: published_at, ...}
        """
        result = {}

        # 캐시에서 먼저 조회
        uncached_ids = []

        for cid in channel_ids:
            # YouTubeService 캐시 확인
            if hasattr(self.youtube, '_channel_cache') and cid in self.youtube._channel_cache:
                published_at_str = self.youtube._channel_cache[cid].get('published_at', '')
                result[cid] = self._parse_datetime(published_at_str)
            # 추가 캐시 확인
            elif cid in self._additional_cache:
                result[cid] = self._additional_cache[cid].get('published_at')
            else:
                uncached_ids.append(cid)

        # 캐시에 없는 것들 일괄 조회
        if uncached_ids:
            channels, _ = self.youtube.get_channels_details(uncached_ids)

            for channel in channels:
                cid = channel.get('channel_id', '')
                published_at_str = channel.get('published_at', '')
                published_at = self._parse_datetime(published_at_str)

                result[cid] = published_at
                self._additional_cache[cid] = {
                    'published_at': published_at,
                    **channel
                }

        return result

    def filter_videos_by_channel_age(
        self,
        videos: List[Dict],
        min_date: Optional[datetime] = None,
        max_date: Optional[datetime] = None,
        progress_callback=None
    ) -> Tuple[List[Dict], Dict]:
        """
        채널 생성일 기준으로 비디오 필터링

        Args:
            videos: 비디오 목록 (dict 또는 객체)
            min_date: 채널 최소 생성일 (이 날짜 이후 생성된 채널만)
            max_date: 채널 최대 생성일 (이 날짜 이전 생성된 채널만)
            progress_callback: 진행률 콜백 (current, total)

        Returns:
            (filtered_videos, stats)
            stats: {
                "total": int,
                "filtered": int,
                "excluded": int,
                "no_info": int
            }
        """
        if not min_date and not max_date:
            return videos, {"total": len(videos), "filtered": len(videos), "excluded": 0, "no_info": 0}

        # 채널 ID 추출
        channel_ids = []
        for v in videos:
            if isinstance(v, dict):
                cid = v.get('channel_id', '')
            else:
                cid = getattr(v, 'channel_id', '')

            if cid and cid not in channel_ids:
                channel_ids.append(cid)

        # 채널 생성일 일괄 조회
        channels_published = self.get_channels_published_at_batch(channel_ids)

        # 필터링
        filtered_videos = []
        excluded_count = 0
        no_info_count = 0

        for idx, video in enumerate(videos):
            if progress_callback:
                progress_callback(idx + 1, len(videos))

            # 채널 ID 추출
            if isinstance(video, dict):
                channel_id = video.get('channel_id', '')
            else:
                channel_id = getattr(video, 'channel_id', '')

            if not channel_id:
                no_info_count += 1
                continue

            published_at = channels_published.get(channel_id)

            if not published_at:
                no_info_count += 1
                continue

            # 타임존 처리
            if min_date and min_date.tzinfo is None and published_at.tzinfo:
                min_date = min_date.replace(tzinfo=published_at.tzinfo)
            if max_date and max_date.tzinfo is None and published_at.tzinfo:
                max_date = max_date.replace(tzinfo=published_at.tzinfo)

            # naive datetime으로 통일
            if published_at.tzinfo:
                published_at_naive = published_at.replace(tzinfo=None)
            else:
                published_at_naive = published_at

            if min_date:
                min_date_naive = min_date.replace(tzinfo=None) if min_date.tzinfo else min_date
                if published_at_naive < min_date_naive:
                    excluded_count += 1
                    continue

            if max_date:
                max_date_naive = max_date.replace(tzinfo=None) if max_date.tzinfo else max_date
                if published_at_naive > max_date_naive:
                    excluded_count += 1
                    continue

            # 채널 정보를 비디오에 추가
            if isinstance(video, dict):
                video['_channel_published_at'] = published_at
            else:
                video._channel_published_at = published_at

            filtered_videos.append(video)

        stats = {
            "total": len(videos),
            "filtered": len(filtered_videos),
            "excluded": excluded_count,
            "no_info": no_info_count
        }

        print(f"[ChannelFilter] 채널 생성일 필터: {stats['total']} → {stats['filtered']}개 "
              f"(제외: {stats['excluded']}, 정보없음: {stats['no_info']})")

        return filtered_videos, stats


def apply_channel_age_filter(
    videos: List[Dict],
    filter_config: Dict,
    youtube_service
) -> Tuple[List[Dict], Dict]:
    """
    채널 생성일 필터 적용 (간편 함수)

    Args:
        videos: 비디오 목록
        filter_config: render_channel_age_filter()의 반환값
            {
                "enabled": bool,
                "min_date": datetime or None,
                "max_date": datetime or None,
                "preset": str or None
            }
        youtube_service: YouTubeService 인스턴스

    Returns:
        (filtered_videos, stats)
    """
    if not filter_config.get('enabled'):
        return videos, {"total": len(videos), "filtered": len(videos), "excluded": 0, "no_info": 0}

    channel_filter = YouTubeChannelFilter(youtube_service)

    return channel_filter.filter_videos_by_channel_age(
        videos=videos,
        min_date=filter_config.get('min_date'),
        max_date=filter_config.get('max_date')
    )


def render_channel_filter_result(stats: Dict, preset: Optional[str] = None):
    """
    채널 필터 결과 표시

    Args:
        stats: filter_videos_by_channel_age()의 stats
        preset: 사용된 프리셋 이름
    """
    from components.channel_age_filter import CHANNEL_AGE_PRESETS

    if stats['excluded'] > 0 or stats['no_info'] > 0:
        preset_label = ""
        if preset and preset in CHANNEL_AGE_PRESETS:
            preset_label = f" ({CHANNEL_AGE_PRESETS[preset]['label']})"

        st.info(
            f"📅 채널 생성일 필터{preset_label}: "
            f"**{stats['filtered']}개** 결과 "
            f"(제외: {stats['excluded']}개, 정보없음: {stats['no_info']}개)"
        )


# 내보내기
__all__ = [
    'YouTubeChannelFilter',
    'apply_channel_age_filter',
    'render_channel_filter_result'
]
