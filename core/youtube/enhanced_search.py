"""
YouTube 영상 리서치 클라이언트 - 고도화 버전

롱폼/쇼츠 구분, 상세 채널 정보, 커스텀 필터링 지원

사용법:
    from core.youtube.enhanced_search import EnhancedYouTubeSearcher
    from core.youtube.data_models import SearchFilters

    searcher = EnhancedYouTubeSearcher()
    filters = SearchFilters(query="1인 창업", video_type="long_form")
    videos, api_calls = searcher.search_videos_enhanced(filters)
"""
import isodate
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config.settings import YOUTUBE_API_KEY
from core.youtube.cache import get_cache
from core.youtube.data_models import VideoInfo, ChannelInfo, SearchFilters


class EnhancedYouTubeSearcher:
    """YouTube 영상 리서치 클라이언트 - 고도화 버전"""

    def __init__(self, api_key: str = None):
        self.api_key = api_key or YOUTUBE_API_KEY
        if not self.api_key:
            raise ValueError("YouTube API 키가 필요합니다")

        self.youtube = build("youtube", "v3", developerKey=self.api_key)
        self.cache = get_cache()

        # 채널 정보 캐시 (세션 내 메모리 캐시)
        self._channel_cache: Dict[str, ChannelInfo] = {}

    def search_videos_enhanced(
        self,
        filters: SearchFilters,
        progress_callback=None
    ) -> Tuple[List[VideoInfo], int]:
        """
        고도화된 영상 검색

        Args:
            filters: 검색 필터
            progress_callback: 진행 상황 콜백 (current, total)

        Returns:
            (영상 목록, API 호출 수)
        """
        api_calls = 0
        videos = []

        try:
            # 검색 파라미터 구성
            search_params = {
                "part": "snippet",
                "q": filters.query,
                "type": "video",
                "maxResults": min(filters.max_results, 50),
                "regionCode": filters.region_code,
            }

            # 정렬
            if filters.sort_by:
                search_params["order"] = filters.sort_by

            # 기간 필터
            if filters.published_after:
                search_params["publishedAfter"] = filters.published_after
            if filters.published_before:
                search_params["publishedBefore"] = filters.published_before

            # 영상 길이 필터 (YouTube API 기본 옵션)
            if filters.video_type == "shorts":
                search_params["videoDuration"] = "short"  # 4분 이하
            elif filters.video_type == "long_form":
                search_params["videoDuration"] = "long"  # 20분 이상
            elif filters.min_duration and filters.min_duration >= 1200:
                search_params["videoDuration"] = "long"
            elif filters.max_duration and filters.max_duration <= 240:
                search_params["videoDuration"] = "short"

            # 캐시 확인
            cache_key = filters.to_cache_key()
            cached = self.cache.get("enhanced_search", cache_key)
            if cached:
                # 캐시된 데이터를 VideoInfo 객체로 변환
                for item in cached:
                    if isinstance(item, dict):
                        video = self._dict_to_video_info(item)
                        if video and self._apply_filters(video, filters):
                            videos.append(video)
                    elif isinstance(item, VideoInfo):
                        if self._apply_filters(item, filters):
                            videos.append(item)
                return videos, 0

            # 검색 실행
            search_response = self.youtube.search().list(**search_params).execute()
            api_calls += 1
            self.cache.log_api_call("search")

            video_ids = [item["id"]["videoId"] for item in search_response.get("items", [])]

            if not video_ids:
                return [], api_calls

            # 영상 상세 정보 조회
            videos_response = self.youtube.videos().list(
                part="snippet,statistics,contentDetails",
                id=",".join(video_ids)
            ).execute()
            api_calls += 1
            self.cache.log_api_call("videos")

            # 채널 ID 수집 (중복 제거)
            channel_ids = list(set(
                item["snippet"]["channelId"]
                for item in videos_response.get("items", [])
            ))

            # 채널 정보 조회
            channels_info = self._get_channels_info_batch(channel_ids)
            api_calls += 1

            # VideoInfo 객체 생성
            total = len(videos_response.get("items", []))

            for i, item in enumerate(videos_response.get("items", [])):
                if progress_callback:
                    progress_callback(i + 1, total)

                video = self._parse_video_item(item, channels_info)

                # 커스텀 필터 적용
                if self._apply_filters(video, filters):
                    videos.append(video)

            # 캐시 저장 (딕셔너리로 변환하여 저장)
            cache_data = [v.to_dict() for v in videos]
            self.cache.set("enhanced_search", cache_key, cache_data)

        except HttpError as e:
            raise Exception(f"YouTube API 오류: {e}")

        return videos, api_calls

    def _get_channels_info_batch(self, channel_ids: List[str]) -> Dict[str, ChannelInfo]:
        """채널 정보 일괄 조회 (캐시 활용)"""

        result = {}
        ids_to_fetch = []

        # 메모리 캐시 확인
        for cid in channel_ids:
            if cid in self._channel_cache:
                result[cid] = self._channel_cache[cid]
            else:
                # DB 캐시 확인
                cached = self.cache.get("channels", {"channel_id": cid})
                if cached:
                    channel = ChannelInfo(
                        channel_id=cached.get("channel_id", cid),
                        channel_name=cached.get("title", ""),
                        channel_url=f"https://www.youtube.com/channel/{cid}",
                        subscriber_count=cached.get("subscriber_count", 0),
                        total_video_count=cached.get("video_count", 0),
                        created_at=cached.get("published_at", ""),
                        description=cached.get("description", ""),
                        thumbnail_url=cached.get("thumbnail_url", ""),
                        total_view_count=cached.get("view_count", 0)
                    )
                    result[cid] = channel
                    self._channel_cache[cid] = channel
                else:
                    ids_to_fetch.append(cid)

        # API 호출
        if ids_to_fetch:
            try:
                # 50개씩 배치 처리
                for i in range(0, len(ids_to_fetch), 50):
                    batch = ids_to_fetch[i:i+50]

                    response = self.youtube.channels().list(
                        part="snippet,statistics",
                        id=",".join(batch)
                    ).execute()

                    self.cache.log_api_call("channels")

                    for item in response.get("items", []):
                        snippet = item.get("snippet", {})
                        stats = item.get("statistics", {})

                        channel = ChannelInfo(
                            channel_id=item["id"],
                            channel_name=snippet.get("title", ""),
                            channel_url=f"https://www.youtube.com/channel/{item['id']}",
                            subscriber_count=int(stats.get("subscriberCount", 0)),
                            total_video_count=int(stats.get("videoCount", 0)),
                            created_at=snippet.get("publishedAt", ""),
                            description=snippet.get("description", ""),
                            thumbnail_url=snippet.get("thumbnails", {}).get("default", {}).get("url", ""),
                            total_view_count=int(stats.get("viewCount", 0))
                        )

                        result[channel.channel_id] = channel
                        self._channel_cache[channel.channel_id] = channel

                        # DB 캐시 저장
                        self.cache.set("channels", {"channel_id": channel.channel_id}, {
                            "channel_id": channel.channel_id,
                            "title": channel.channel_name,
                            "subscriber_count": channel.subscriber_count,
                            "video_count": channel.total_video_count,
                            "view_count": channel.total_view_count,
                            "published_at": channel.created_at,
                            "description": channel.description,
                            "thumbnail_url": channel.thumbnail_url
                        })

            except HttpError as e:
                print(f"[YouTube API] 채널 조회 오류: {e}")

        return result

    def _parse_video_item(self, item: dict, channels: Dict[str, ChannelInfo]) -> VideoInfo:
        """YouTube API 응답을 VideoInfo로 변환"""

        snippet = item.get("snippet", {})
        statistics = item.get("statistics", {})
        content_details = item.get("contentDetails", {})

        # 영상 길이 파싱 (ISO 8601 -> 초)
        duration_iso = content_details.get("duration", "PT0S")
        duration_seconds = self._parse_duration(duration_iso)
        duration_formatted = self._format_duration(duration_seconds)

        # 영상 유형 판별 (60초 이하 = 쇼츠)
        video_type = "shorts" if duration_seconds <= 60 else "long_form"

        # 채널 정보
        channel_id = snippet.get("channelId", "")
        channel = channels.get(channel_id)

        return VideoInfo(
            video_id=item["id"],
            title=snippet.get("title", ""),
            video_url=f"https://www.youtube.com/watch?v={item['id']}",
            thumbnail_url=snippet.get("thumbnails", {}).get("high", {}).get("url", ""),

            channel_id=channel_id,
            channel_name=snippet.get("channelTitle", ""),
            channel_url=f"https://www.youtube.com/channel/{channel_id}",
            subscriber_count=channel.subscriber_count if channel else 0,
            channel_created_at=channel.created_at if channel else "",
            channel_total_videos=channel.total_video_count if channel else 0,

            view_count=int(statistics.get("viewCount", 0)),
            like_count=int(statistics.get("likeCount", 0)),
            comment_count=int(statistics.get("commentCount", 0)),

            published_at=snippet.get("publishedAt", ""),
            duration_seconds=duration_seconds,
            duration_formatted=duration_formatted,

            video_type=video_type,
            description=snippet.get("description", "")[:500],
            tags=snippet.get("tags", [])
        )

    def _dict_to_video_info(self, data: dict) -> Optional[VideoInfo]:
        """딕셔너리를 VideoInfo 객체로 변환"""
        try:
            return VideoInfo(
                video_id=data.get("video_id", ""),
                title=data.get("title", ""),
                video_url=data.get("video_url", ""),
                thumbnail_url=data.get("thumbnail_url", ""),
                channel_id=data.get("channel_id", ""),
                channel_name=data.get("channel_name", ""),
                channel_url=data.get("channel_url", ""),
                subscriber_count=data.get("subscriber_count", 0),
                channel_created_at=data.get("channel_created_at", ""),
                channel_total_videos=data.get("channel_total_videos", 0),
                view_count=data.get("view_count", 0),
                like_count=data.get("like_count", 0),
                comment_count=data.get("comment_count", 0),
                published_at=data.get("published_at", ""),
                duration_seconds=data.get("duration_seconds", 0),
                duration_formatted=data.get("duration_formatted", ""),
                video_type=data.get("video_type", "long_form"),
                description=data.get("description", ""),
                tags=data.get("tags", [])
            )
        except Exception:
            return None

    def _parse_duration(self, iso_duration: str) -> int:
        """ISO 8601 기간을 초로 변환"""
        try:
            return int(isodate.parse_duration(iso_duration).total_seconds())
        except:
            return 0

    def _format_duration(self, seconds: int) -> str:
        """초를 'HH:MM:SS' 또는 'MM:SS' 형식으로"""
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60

        if hours > 0:
            return f"{hours}:{minutes:02d}:{secs:02d}"
        return f"{minutes}:{secs:02d}"

    def _apply_filters(self, video: VideoInfo, filters: SearchFilters) -> bool:
        """커스텀 필터 적용"""

        # 영상 길이 필터
        if filters.min_duration and video.duration_seconds < filters.min_duration:
            return False
        if filters.max_duration and video.duration_seconds > filters.max_duration:
            return False

        # 영상 유형 필터
        if filters.video_type == "shorts" and video.video_type != "shorts":
            return False
        if filters.video_type == "long_form" and video.video_type != "long_form":
            return False

        # 조회수 필터
        if filters.min_views and video.view_count < filters.min_views:
            return False
        if filters.max_views and video.view_count > filters.max_views:
            return False

        # 구독자 필터
        if filters.min_subscribers and video.subscriber_count < filters.min_subscribers:
            return False
        if filters.max_subscribers and video.subscriber_count > filters.max_subscribers:
            return False

        return True

    def get_video_details(self, video_id: str) -> Optional[VideoInfo]:
        """단일 영상 상세 정보"""
        try:
            response = self.youtube.videos().list(
                part="snippet,statistics,contentDetails",
                id=video_id
            ).execute()

            self.cache.log_api_call("videos")

            if response.get("items"):
                item = response["items"][0]
                channels = self._get_channels_info_batch([item["snippet"]["channelId"]])
                return self._parse_video_item(item, channels)

        except HttpError as e:
            print(f"[YouTube API] 영상 조회 오류: {e}")

        return None

    def get_quota_info(self) -> Dict:
        """현재 할당량 정보 반환"""
        return self.cache.get_quota_stats()
