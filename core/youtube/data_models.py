"""
YouTube 영상 리서치 데이터 모델
"""
from dataclasses import dataclass, asdict, field
from typing import Optional, List
from datetime import datetime


@dataclass
class ChannelInfo:
    """채널 정보"""
    channel_id: str
    channel_name: str
    channel_url: str
    subscriber_count: int
    total_video_count: int
    created_at: str  # 채널 개설일
    description: str = ""
    thumbnail_url: str = ""
    total_view_count: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class VideoInfo:
    """영상 정보"""
    video_id: str
    title: str
    video_url: str
    thumbnail_url: str

    # 채널 정보
    channel_id: str
    channel_name: str
    channel_url: str
    subscriber_count: int
    channel_created_at: str
    channel_total_videos: int

    # 영상 통계
    view_count: int
    like_count: int
    comment_count: int

    # 영상 메타데이터
    published_at: str  # 업로드일
    duration_seconds: int  # 영상 길이 (초)
    duration_formatted: str  # "10:30" 형식

    # 분류
    video_type: str  # "long_form", "shorts"
    category: str = ""
    tags: List[str] = field(default_factory=list)
    description: str = ""

    @property
    def views_per_subscriber(self) -> float:
        """구독자 대비 조회수 (효율성 지표)"""
        if self.subscriber_count > 0:
            return round(self.view_count / self.subscriber_count, 2)
        return 0.0

    @property
    def engagement_rate(self) -> float:
        """참여율 (좋아요+댓글 / 조회수)"""
        if self.view_count > 0:
            return round((self.like_count + self.comment_count) / self.view_count * 100, 2)
        return 0.0

    @property
    def days_since_upload(self) -> int:
        """업로드 후 경과 일수"""
        try:
            upload_date = datetime.fromisoformat(self.published_at.replace('Z', '+00:00'))
            return max(1, (datetime.now(upload_date.tzinfo) - upload_date).days)
        except:
            return 1

    @property
    def views_per_day(self) -> float:
        """일일 평균 조회수"""
        days = self.days_since_upload
        if days > 0:
            return round(self.view_count / days, 1)
        return float(self.view_count)

    @property
    def viral_score(self) -> float:
        """급등 점수 (일평균 조회수 + 참여율 기반)"""
        daily_score = min(self.views_per_day / 1000, 60)
        eng_score = min(self.engagement_rate * 10, 40)
        return round(daily_score + eng_score, 1)

    def to_dict(self) -> dict:
        """딕셔너리 변환 (계산된 지표 포함)"""
        data = asdict(self)
        data["views_per_subscriber"] = self.views_per_subscriber
        data["engagement_rate"] = self.engagement_rate
        data["days_since_upload"] = self.days_since_upload
        data["views_per_day"] = self.views_per_day
        data["viral_score"] = self.viral_score
        return data

    def to_excel_row(self) -> dict:
        """엑셀 행 데이터"""
        return {
            "영상 제목": self.title,
            "영상 URL": self.video_url,
            "영상 유형": "쇼츠" if self.video_type == "shorts" else "롱폼",
            "영상 길이": self.duration_formatted,
            "업로드일": self.published_at[:10] if self.published_at else "",
            "조회수": self.view_count,
            "좋아요": self.like_count,
            "댓글수": self.comment_count,
            "채널명": self.channel_name,
            "채널 URL": self.channel_url,
            "구독자수": self.subscriber_count,
            "채널 개설일": self.channel_created_at[:10] if self.channel_created_at else "",
            "채널 총 영상수": self.channel_total_videos,
            "구독자 대비 조회수": self.views_per_subscriber,
            "참여율(%)": self.engagement_rate,
            "업로드 후 일수": self.days_since_upload,
            "일일 평균 조회수": self.views_per_day,
            "급등 점수": self.viral_score,
        }


@dataclass
class SearchFilters:
    """검색 필터"""
    query: str
    video_type: str = "all"  # "all", "long_form", "shorts"

    # 영상 길이 (초)
    min_duration: Optional[int] = None
    max_duration: Optional[int] = None

    # 조회수
    min_views: Optional[int] = None
    max_views: Optional[int] = None

    # 구독자
    min_subscribers: Optional[int] = None
    max_subscribers: Optional[int] = None

    # 기간
    published_after: Optional[str] = None
    published_before: Optional[str] = None

    # 정렬
    sort_by: str = "relevance"  # "relevance", "viewCount", "date", "rating"

    # 지역/언어
    region_code: str = "KR"
    language: str = "ko"

    # 결과 수
    max_results: int = 50

    def to_cache_key(self) -> dict:
        """캐시 키용 딕셔너리"""
        return {
            "query": self.query,
            "video_type": self.video_type,
            "min_duration": self.min_duration,
            "max_duration": self.max_duration,
            "published_after": self.published_after,
            "sort_by": self.sort_by,
            "region_code": self.region_code,
            "max_results": self.max_results,
        }
