# -*- coding: utf-8 -*-
"""
YouTube 채널 검색 모듈

기능:
- URL로 채널 검색 (@handle, /channel/, /c/, /user/)
- 채널 ID로 검색
- 채널명으로 검색
- 채널 상세 정보 조회
- 채널 영상 목록 조회
"""

import os
import re
from typing import Dict, List, Optional
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import YOUTUBE_API_KEY


class YouTubeChannelSearcher:
    """YouTube 채널 검색기"""

    def __init__(self, api_key: str = None):
        """
        Args:
            api_key: YouTube API 키 (없으면 환경변수에서 로드)
        """
        self.api_key = api_key or YOUTUBE_API_KEY
        if not self.api_key:
            raise ValueError("YOUTUBE_API_KEY가 설정되지 않았습니다.")

        self.youtube = build('youtube', 'v3', developerKey=self.api_key)

    def search_channel(
        self,
        query: str,
        search_type: str = "auto"
    ) -> Optional[Dict]:
        """
        채널 검색

        Args:
            query: 검색어 (URL, 채널ID, 채널명)
            search_type: "url", "id", "name", "auto"

        Returns:
            채널 정보 딕셔너리
        """
        if not query or not query.strip():
            return None

        query = query.strip()

        if search_type == "auto":
            search_type = self._detect_query_type(query)

        print(f"[ChannelSearcher] 검색 타입: {search_type}, 쿼리: {query[:50]}")

        if search_type == "url":
            return self._search_by_url(query)
        elif search_type == "id":
            return self._search_by_id(query)
        elif search_type == "name":
            return self._search_by_name(query)
        else:
            return None

    def _detect_query_type(self, query: str) -> str:
        """쿼리 타입 자동 감지"""

        # URL 패턴
        if "youtube.com" in query or "youtu.be" in query:
            return "url"

        # 채널 ID 패턴 (UC로 시작하는 24자)
        if re.match(r'^UC[\w-]{22}$', query):
            return "id"

        # 그 외는 채널명으로 검색
        return "name"

    def _search_by_url(self, url: str) -> Optional[Dict]:
        """URL로 채널 검색"""

        # 채널 ID 추출 시도
        channel_id = self._extract_channel_id_from_url(url)
        if channel_id:
            return self._search_by_id(channel_id)

        # @handle 형식인 경우
        handle = self._extract_handle_from_url(url)
        if handle:
            return self._search_by_handle(handle)

        # custom URL (/c/ 형식)
        custom = self._extract_custom_url(url)
        if custom:
            return self._search_by_name(custom)

        return None

    def _extract_channel_id_from_url(self, url: str) -> Optional[str]:
        """URL에서 채널 ID 추출"""

        # /channel/UC... 형식
        match = re.search(r'youtube\.com/channel/(UC[\w-]{22})', url)
        if match:
            return match.group(1)

        return None

    def _extract_handle_from_url(self, url: str) -> Optional[str]:
        """URL에서 @handle 추출"""

        match = re.search(r'youtube\.com/@([\w.-]+)', url)
        if match:
            return match.group(1)
        return None

    def _extract_custom_url(self, url: str) -> Optional[str]:
        """URL에서 custom URL 추출 (/c/, /user/)"""

        patterns = [
            r'youtube\.com/c/([\w-]+)',
            r'youtube\.com/user/([\w-]+)',
        ]

        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)

        return None

    def _search_by_handle(self, handle: str) -> Optional[Dict]:
        """@handle로 채널 검색"""

        try:
            # handle로 검색
            response = self.youtube.search().list(
                part='snippet',
                q=f"@{handle}",
                type='channel',
                maxResults=5
            ).execute()

            if response.get('items'):
                # 정확한 handle 매칭 찾기
                for item in response['items']:
                    channel_id = item['snippet']['channelId']
                    # 채널 상세 정보 조회
                    channel_info = self._search_by_id(channel_id)
                    if channel_info:
                        # customUrl 확인
                        return channel_info

                # 첫 번째 결과 반환
                channel_id = response['items'][0]['snippet']['channelId']
                return self._search_by_id(channel_id)

        except HttpError as e:
            print(f"[ChannelSearcher] Handle 검색 오류: {e}")

        return None

    def _search_by_id(self, channel_id: str) -> Optional[Dict]:
        """채널 ID로 검색"""

        try:
            response = self.youtube.channels().list(
                part='snippet,statistics,contentDetails,brandingSettings',
                id=channel_id
            ).execute()

            if response.get('items'):
                return self._parse_channel_info(response['items'][0])

        except HttpError as e:
            print(f"[ChannelSearcher] ID 검색 오류: {e}")

        return None

    def _search_by_name(self, name: str) -> Optional[Dict]:
        """채널명으로 검색"""

        try:
            response = self.youtube.search().list(
                part='snippet',
                q=name,
                type='channel',
                maxResults=5
            ).execute()

            if response.get('items'):
                # 첫 번째 결과의 상세 정보 조회
                channel_id = response['items'][0]['snippet']['channelId']
                return self._search_by_id(channel_id)

        except HttpError as e:
            print(f"[ChannelSearcher] 이름 검색 오류: {e}")

        return None

    def _parse_channel_info(self, item: Dict) -> Dict:
        """채널 정보 파싱"""

        snippet = item.get('snippet', {})
        statistics = item.get('statistics', {})
        content_details = item.get('contentDetails', {})
        branding = item.get('brandingSettings', {}).get('channel', {})

        # 숨겨진 구독자 수 처리
        subscriber_count = statistics.get('subscriberCount', '0')
        if statistics.get('hiddenSubscriberCount'):
            subscriber_count = '비공개'
        else:
            try:
                subscriber_count = int(subscriber_count)
            except ValueError:
                subscriber_count = 0

        return {
            "channel_id": item['id'],
            "channel_name": snippet.get('title', ''),
            "channel_url": f"https://www.youtube.com/channel/{item['id']}",
            "custom_url": snippet.get('customUrl', ''),
            "description": snippet.get('description', ''),
            "thumbnail_url": snippet.get('thumbnails', {}).get('high', {}).get('url', ''),
            "created_at": snippet.get('publishedAt', ''),
            "country": snippet.get('country', ''),
            "subscriber_count": subscriber_count,
            "video_count": int(statistics.get('videoCount', 0)),
            "view_count": int(statistics.get('viewCount', 0)),
            "uploads_playlist_id": content_details.get('relatedPlaylists', {}).get('uploads', ''),
            "keywords": branding.get('keywords', '')
        }

    def get_channel_videos(
        self,
        channel_id: str,
        max_results: int = None,
        published_after: str = None
    ) -> List[Dict]:
        """
        채널의 영상 목록 조회

        Args:
            channel_id: 채널 ID
            max_results: 최대 결과 수 (None이면 전체)
            published_after: 이 날짜 이후 영상만 (ISO 8601)

        Returns:
            영상 목록
        """

        # 먼저 채널 정보에서 uploads playlist ID 가져오기
        channel_info = self._search_by_id(channel_id)
        if not channel_info:
            print(f"[ChannelSearcher] 채널을 찾을 수 없음: {channel_id}")
            return []

        uploads_playlist_id = channel_info.get('uploads_playlist_id')
        if not uploads_playlist_id:
            print(f"[ChannelSearcher] 업로드 플레이리스트를 찾을 수 없음")
            return []

        videos = []
        next_page_token = None

        while True:
            try:
                response = self.youtube.playlistItems().list(
                    part='snippet,contentDetails',
                    playlistId=uploads_playlist_id,
                    maxResults=50,
                    pageToken=next_page_token
                ).execute()

                for item in response.get('items', []):
                    video_id = item['contentDetails']['videoId']
                    snippet = item['snippet']

                    # 날짜 필터
                    published_at = snippet.get('publishedAt', '')
                    if published_after and published_at < published_after:
                        continue

                    videos.append({
                        "video_id": video_id,
                        "title": snippet.get('title', ''),
                        "description": snippet.get('description', '')[:200],
                        "published_at": published_at,
                        "thumbnail_url": snippet.get('thumbnails', {}).get('medium', {}).get('url', '')
                    })

                    if max_results and len(videos) >= max_results:
                        return videos

                next_page_token = response.get('nextPageToken')
                if not next_page_token:
                    break

                print(f"[ChannelSearcher] {len(videos)}개 영상 로드됨...")

            except HttpError as e:
                print(f"[ChannelSearcher] 영상 목록 조회 오류: {e}")
                break

        print(f"[ChannelSearcher] 총 {len(videos)}개 영상 발견")
        return videos

    def get_video_details(self, video_ids: List[str]) -> List[Dict]:
        """영상 상세 정보 조회 (배치)"""

        details = []

        # 50개씩 배치 처리
        for i in range(0, len(video_ids), 50):
            batch = video_ids[i:i+50]

            try:
                response = self.youtube.videos().list(
                    part='snippet,contentDetails,statistics',
                    id=','.join(batch)
                ).execute()

                for item in response.get('items', []):
                    details.append({
                        "video_id": item['id'],
                        "title": item['snippet']['title'],
                        "duration": item['contentDetails']['duration'],
                        "view_count": int(item['statistics'].get('viewCount', 0)),
                        "like_count": int(item['statistics'].get('likeCount', 0)),
                        "comment_count": int(item['statistics'].get('commentCount', 0)),
                        "has_captions": item['contentDetails'].get('caption') == 'true'
                    })

            except HttpError as e:
                print(f"[ChannelSearcher] 영상 상세 조회 오류: {e}")

        return details

    def search_channels_by_keyword(
        self,
        keyword: str,
        max_results: int = 10
    ) -> List[Dict]:
        """
        키워드로 여러 채널 검색

        Args:
            keyword: 검색 키워드
            max_results: 최대 결과 수

        Returns:
            채널 정보 목록
        """

        try:
            response = self.youtube.search().list(
                part='snippet',
                q=keyword,
                type='channel',
                maxResults=min(max_results, 50)
            ).execute()

            channels = []
            for item in response.get('items', []):
                channel_id = item['snippet']['channelId']
                channel_info = self._search_by_id(channel_id)
                if channel_info:
                    channels.append(channel_info)

            return channels

        except HttpError as e:
            print(f"[ChannelSearcher] 키워드 검색 오류: {e}")
            return []


def get_channel_searcher(api_key: str = None) -> YouTubeChannelSearcher:
    """채널 검색기 인스턴스 생성"""
    return YouTubeChannelSearcher(api_key)
