"""
YouTube 검색 모듈 (캐싱 적용)

캐싱이 적용되어 동일한 검색은 API를 호출하지 않습니다.

사용법:
    from core.youtube.search import YouTubeSearcher

    searcher = YouTubeSearcher()
    videos = searcher.search_videos(
        keyword="1인 창업",
        region_code="KR",
        max_results=30
    )
"""
from googleapiclient.discovery import build
from datetime import datetime, timedelta
import isodate
from typing import List, Dict, Optional

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config.settings import YOUTUBE_API_KEY
from core.youtube.cache import get_cache


class YouTubeSearcher:
    """
    YouTube 영상 검색 클래스

    특징:
    - SQLite 기반 캐싱 적용
    - 급등 점수(viral_score) 자동 계산
    - 일일 할당량 추적
    """

    def __init__(self, api_key: str = None):
        """
        Args:
            api_key: YouTube API 키 (기본: 환경변수에서 로드)
        """
        self.api_key = api_key or YOUTUBE_API_KEY
        if not self.api_key:
            raise ValueError("YouTube API Key가 필요합니다. .env 파일을 확인하세요.")

        self.youtube = build('youtube', 'v3', developerKey=self.api_key)
        self.cache = get_cache()

    def search_videos(
        self,
        keyword: str,
        region_code: str = "KR",
        published_after: datetime = None,
        max_results: int = 50,
        video_duration: str = "long",
        order: str = "viewCount"
    ) -> List[Dict]:
        """
        키워드로 영상 검색 (캐시 우선)

        Args:
            keyword: 검색 키워드
            region_code: 국가 코드 (KR, JP, US 등)
            published_after: 이 날짜 이후 업로드된 영상만
            max_results: 최대 결과 수 (최대 50)
            video_duration: 영상 길이 ("any", "short", "medium", "long")
            order: 정렬 순서 ("viewCount", "date", "rating", "relevance")

        Returns:
            영상 정보 딕셔너리 리스트
        """
        if published_after is None:
            published_after = datetime.now() - timedelta(days=30)

        # 캐시 키 파라미터
        cache_params = {
            "keyword": keyword,
            "region": region_code,
            "after": published_after.strftime("%Y-%m-%d"),
            "duration": video_duration,
            "order": order,
            "max": max_results
        }

        # 1. 캐시 확인
        cached = self.cache.get("search", cache_params)
        if cached:
            return cached

        # 2. API 호출
        try:
            response = self.youtube.search().list(
                q=keyword,
                part="snippet",
                type="video",
                regionCode=region_code,
                publishedAfter=published_after.isoformat() + "Z",
                maxResults=min(max_results, 50),
                videoDuration=video_duration,
                order=order
            ).execute()

            # 할당량 기록 (100포인트)
            self.cache.log_api_call("search")

        except Exception as e:
            raise Exception(f"YouTube 검색 실패: {str(e)}")

        # 3. 영상 ID 추출
        video_ids = [item["id"]["videoId"] for item in response.get("items", [])]

        if not video_ids:
            return []

        # 4. 영상 상세 정보 조회
        videos = self.get_video_details(video_ids)

        # 5. 급등 점수 계산
        for video in videos:
            video["viral_score"] = self._calculate_viral_score(video)

        # 6. 급등 점수순 정렬
        videos.sort(key=lambda x: x.get("viral_score", 0), reverse=True)

        # 7. 캐시 저장
        self.cache.set("search", cache_params, videos)

        return videos

    def get_video_details(self, video_ids: List[str]) -> List[Dict]:
        """
        영상 상세 정보 조회 (캐시 우선, 개별 캐싱)

        Args:
            video_ids: 영상 ID 리스트

        Returns:
            영상 상세 정보 딕셔너리 리스트
        """
        results = []
        uncached_ids = []

        # 1. 각 video_id별 캐시 확인
        for vid in video_ids:
            cached = self.cache.get("videos", {"video_id": vid})
            if cached:
                results.append(cached)
            else:
                uncached_ids.append(vid)

        # 2. 캐시 미스된 것만 API 호출
        if uncached_ids:
            # 50개씩 배치 처리 (API 제한)
            for i in range(0, len(uncached_ids), 50):
                batch = uncached_ids[i:i+50]

                try:
                    response = self.youtube.videos().list(
                        part="snippet,statistics,contentDetails",
                        id=",".join(batch)
                    ).execute()

                    # 할당량 기록 (배치당 1포인트)
                    self.cache.log_api_call("videos")

                except Exception as e:
                    raise Exception(f"영상 정보 조회 실패: {str(e)}")

                for item in response.get("items", []):
                    video_data = self._parse_video(item)
                    results.append(video_data)

                    # 개별 캐싱
                    self.cache.set("videos", {"video_id": item["id"]}, video_data)

        return results

    def get_channel_info(self, channel_id: str) -> Optional[Dict]:
        """
        채널 정보 조회 (캐시 우선)

        Args:
            channel_id: 채널 ID

        Returns:
            채널 정보 딕셔너리
        """
        # 캐시 확인
        cached = self.cache.get("channels", {"channel_id": channel_id})
        if cached:
            return cached

        try:
            response = self.youtube.channels().list(
                part="snippet,statistics",
                id=channel_id
            ).execute()

            self.cache.log_api_call("channels")

        except Exception as e:
            return None

        items = response.get("items", [])
        if not items:
            return None

        item = items[0]
        channel_data = {
            "channel_id": item["id"],
            "title": item["snippet"].get("title", ""),
            "description": item["snippet"].get("description", ""),
            "thumbnail_url": item["snippet"].get("thumbnails", {}).get("default", {}).get("url", ""),
            "subscriber_count": int(item["statistics"].get("subscriberCount", 0)),
            "video_count": int(item["statistics"].get("videoCount", 0)),
            "view_count": int(item["statistics"].get("viewCount", 0)),
        }

        # 캐시 저장
        self.cache.set("channels", {"channel_id": channel_id}, channel_data)

        return channel_data

    def _parse_video(self, item: Dict) -> Dict:
        """
        YouTube API 응답을 파싱하여 필요한 정보 추출

        Args:
            item: YouTube API 영상 아이템

        Returns:
            정제된 영상 정보 딕셔너리
        """
        snippet = item.get("snippet", {})
        stats = item.get("statistics", {})
        content = item.get("contentDetails", {})

        # 영상 길이 파싱
        duration_str = content.get("duration", "PT0S")
        try:
            duration_sec = int(isodate.parse_duration(duration_str).total_seconds())
        except:
            duration_sec = 0

        # 업로드 날짜 파싱
        published_str = snippet.get("publishedAt", "")
        try:
            pub_date = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
            days_since_upload = max(1, (datetime.now(pub_date.tzinfo) - pub_date).days)
        except:
            days_since_upload = 1

        # 통계 파싱
        view_count = int(stats.get("viewCount", 0))
        like_count = int(stats.get("likeCount", 0))
        comment_count = int(stats.get("commentCount", 0))

        # 일평균 조회수
        daily_views = view_count / days_since_upload

        # 인게이지먼트 비율
        engagement = ((like_count + comment_count) / max(view_count, 1)) * 100

        return {
            "video_id": item["id"],
            "title": snippet.get("title", ""),
            "description": snippet.get("description", "")[:500],  # 설명 500자 제한
            "channel_id": snippet.get("channelId", ""),
            "channel_title": snippet.get("channelTitle", ""),
            "published_at": published_str,
            "thumbnail_url": snippet.get("thumbnails", {}).get("high", {}).get("url", ""),
            "view_count": view_count,
            "like_count": like_count,
            "comment_count": comment_count,
            "duration_seconds": duration_sec,
            "duration_formatted": self._format_duration(duration_sec),
            "days_since_upload": days_since_upload,
            "daily_views": round(daily_views, 1),
            "engagement_rate": round(engagement, 2),
            "video_url": f"https://www.youtube.com/watch?v={item['id']}"
        }

    def _calculate_viral_score(self, video: Dict) -> float:
        """
        급등 점수 계산

        점수 산정 기준:
        - 일평균 조회수 (60%)
        - 인게이지먼트 비율 (40%)

        Args:
            video: 영상 정보 딕셔너리

        Returns:
            급등 점수 (0-100)
        """
        daily_views = video.get("daily_views", 0)
        engagement = video.get("engagement_rate", 0)

        # 일평균 조회수 점수 (1000뷰 = 1점, 최대 60점)
        daily_score = min(daily_views / 1000, 60)

        # 인게이지먼트 점수 (1% = 10점, 최대 40점)
        eng_score = min(engagement * 10, 40)

        return round(daily_score + eng_score, 1)

    def _format_duration(self, seconds: int) -> str:
        """
        초를 MM:SS 또는 HH:MM:SS 형식으로 변환

        Args:
            seconds: 초

        Returns:
            포맷된 문자열
        """
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60

        if hours > 0:
            return f"{hours}:{minutes:02d}:{secs:02d}"
        return f"{minutes}:{secs:02d}"

    def get_quota_info(self) -> Dict:
        """
        현재 할당량 정보 반환

        Returns:
            할당량 통계 딕셔너리
        """
        return self.cache.get_quota_stats()
