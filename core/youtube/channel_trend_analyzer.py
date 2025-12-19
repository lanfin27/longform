# -*- coding: utf-8 -*-
"""
채널 트렌드 분석기

역추적 로직을 사용하여 신규 채널 발굴 및 트렌드 분석
YouTube API는 채널 생성일 기준 검색이 안 되므로,
"최근 영상 검색 → 채널 ID 추출 → 채널 생성일 필터링" 방식 사용
"""
import os
import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from collections import Counter
from dateutil import parser
import hashlib

from googleapiclient.discovery import build

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config.settings import YOUTUBE_API_KEY
from core.youtube.cache import get_cache


@dataclass
class NewChannel:
    """신규 채널 정보"""
    channel_id: str
    title: str
    description: str
    created_at: str  # YYYY-MM-DD
    created_at_dt: datetime
    subscribers: int
    video_count: int
    view_count: int
    thumbnail_url: str
    channel_url: str

    # 계산 지표
    avg_views_per_video: float = 0.0
    subscribers_per_video: float = 0.0  # 영상당 구독자 효율
    days_since_creation: int = 0
    growth_rate: str = "보통"  # 급성장/보통/저조

    def calculate_metrics(self):
        """성과 지표 계산"""
        if self.video_count > 0:
            self.avg_views_per_video = self.view_count / self.video_count
            self.subscribers_per_video = self.subscribers / self.video_count

        self.days_since_creation = (datetime.now() - self.created_at_dt).days

        # 성장률 판정 (영상당 구독자 기준)
        if self.subscribers_per_video >= 100:
            self.growth_rate = "🚀 급성장"
        elif self.subscribers_per_video >= 30:
            self.growth_rate = "📈 양호"
        elif self.subscribers_per_video >= 10:
            self.growth_rate = "➡️ 보통"
        else:
            self.growth_rate = "📉 저조"

    def to_dict(self) -> dict:
        return {
            "channel_id": self.channel_id,
            "title": self.title,
            "description": self.description[:200] if self.description else "",
            "created_at": self.created_at,
            "subscribers": self.subscribers,
            "video_count": self.video_count,
            "view_count": self.view_count,
            "avg_views_per_video": round(self.avg_views_per_video, 1),
            "subscribers_per_video": round(self.subscribers_per_video, 1),
            "days_since_creation": self.days_since_creation,
            "growth_rate": self.growth_rate,
            "channel_url": self.channel_url,
            "thumbnail_url": self.thumbnail_url
        }


@dataclass
class TrendAnalysisResult:
    """트렌드 분석 결과"""
    keyword: str
    region: str
    period_months: int
    analysis_date: str

    total_videos_searched: int
    unique_channels_found: int
    new_channels_count: int

    new_channels: List[NewChannel] = field(default_factory=list)
    monthly_trend: Dict[str, int] = field(default_factory=dict)  # {"2024-01": 3, "2024-02": 5, ...}

    # 요약 통계
    avg_subscribers: float = 0.0
    avg_video_count: float = 0.0
    avg_views: float = 0.0

    # AI 인사이트
    ai_insight: str = ""

    def calculate_summary(self):
        """요약 통계 계산"""
        if self.new_channels:
            self.avg_subscribers = sum(c.subscribers for c in self.new_channels) / len(self.new_channels)
            self.avg_video_count = sum(c.video_count for c in self.new_channels) / len(self.new_channels)
            self.avg_views = sum(c.view_count for c in self.new_channels) / len(self.new_channels)


class ChannelTrendAnalyzer:
    """채널 트렌드 분석기"""

    def __init__(self, api_key: str = None, cache_dir: str = "data/cache/channel_trends"):
        """
        Args:
            api_key: YouTube API 키 (기본: 환경변수에서 로드)
            cache_dir: 캐시 디렉토리
        """
        self.api_key = api_key or YOUTUBE_API_KEY
        if not self.api_key:
            raise ValueError("YouTube API Key가 필요합니다. .env 파일을 확인하세요.")

        self.youtube = build('youtube', 'v3', developerKey=self.api_key)
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)

        self.cache_expiry_days = 7
        self._cache = get_cache()

    def _get_cache_key(self, keyword: str, region: str, months: int) -> str:
        """캐시 키 생성"""
        key_str = f"trend_{keyword}_{region}_{months}"
        return hashlib.md5(key_str.encode()).hexdigest()[:16]

    def _get_cached_result(self, cache_key: str) -> Optional[dict]:
        """캐시된 결과 조회"""
        cache_file = os.path.join(self.cache_dir, f"{cache_key}.json")

        if os.path.exists(cache_file):
            stat = os.stat(cache_file)
            age_days = (datetime.now().timestamp() - stat.st_mtime) / 86400

            if age_days < self.cache_expiry_days:
                try:
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        return json.load(f)
                except:
                    pass

        return None

    def _save_cache(self, cache_key: str, data: dict):
        """결과 캐싱"""
        cache_file = os.path.join(self.cache_dir, f"{cache_key}.json")
        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        except Exception as e:
            print(f"[ChannelTrend] 캐시 저장 오류: {e}")

    def analyze_channel_trend(
        self,
        keyword: str,
        region: str = "KR",
        months: int = 6,
        max_videos: int = 100,
        use_cache: bool = True,
        progress_callback=None
    ) -> TrendAnalysisResult:
        """
        채널 트렌드 분석 실행

        Args:
            keyword: 검색 키워드
            region: 국가 코드 (KR, JP, US 등)
            months: 분석 기간 (개월)
            max_videos: 최대 검색 영상 수
            use_cache: 캐시 사용 여부
            progress_callback: 진행 상황 콜백 함수

        Returns:
            TrendAnalysisResult
        """
        def update_progress(msg):
            if progress_callback:
                progress_callback(msg)
            print(f"[ChannelTrend] {msg}")

        # 캐시 확인
        cache_key = self._get_cache_key(keyword, region, months)
        if use_cache:
            cached = self._get_cached_result(cache_key)
            if cached:
                update_progress("캐시된 결과 사용")
                return self._dict_to_result(cached)

        # 1. 기준 날짜 설정
        cutoff_date = datetime.now() - timedelta(days=months * 30)
        published_after = cutoff_date.isoformat() + "Z"

        # 2. 최근 영상 검색 (Step 1)
        update_progress(f"키워드 '{keyword}' 영상 검색 중...")

        all_videos = []
        next_page_token = None

        while len(all_videos) < max_videos:
            try:
                search_response = self.youtube.search().list(
                    q=keyword,
                    part="snippet",
                    type="video",
                    order="date",  # 최신순
                    publishedAfter=published_after,
                    regionCode=region,
                    maxResults=min(50, max_videos - len(all_videos)),
                    pageToken=next_page_token
                ).execute()

                # 할당량 기록
                self._cache.log_api_call("search")

                all_videos.extend(search_response.get('items', []))
                next_page_token = search_response.get('nextPageToken')

                if not next_page_token:
                    break

            except Exception as e:
                update_progress(f"영상 검색 오류: {e}")
                break

        update_progress(f"총 {len(all_videos)}개 영상 검색됨")

        if not all_videos:
            return TrendAnalysisResult(
                keyword=keyword,
                region=region,
                period_months=months,
                analysis_date=datetime.now().strftime("%Y-%m-%d %H:%M"),
                total_videos_searched=0,
                unique_channels_found=0,
                new_channels_count=0,
                new_channels=[],
                monthly_trend={}
            )

        # 3. 채널 ID 추출 (Step 2)
        channel_ids = list(set([
            item['snippet']['channelId']
            for item in all_videos
            if 'channelId' in item['snippet']
        ]))

        update_progress(f"고유 채널 {len(channel_ids)}개 발견")

        # 4. 채널 상세 정보 조회 (Step 3)
        update_progress("채널 정보 조회 중...")
        all_channel_data = []

        for i in range(0, len(channel_ids), 50):
            batch_ids = channel_ids[i:i+50]

            try:
                channels_response = self.youtube.channels().list(
                    part="snippet,statistics",
                    id=",".join(batch_ids)
                ).execute()

                # 할당량 기록
                self._cache.log_api_call("channels")

                all_channel_data.extend(channels_response.get('items', []))

            except Exception as e:
                update_progress(f"채널 조회 오류: {e}")

        # 5. 채널 생성일 필터링 (Step 4) - 핵심!
        update_progress("신규 채널 필터링 중...")
        new_channels: List[NewChannel] = []
        monthly_counter = Counter()

        for ch in all_channel_data:
            try:
                # 채널 생성일 파싱
                created_at_str = ch['snippet']['publishedAt']
                created_at = parser.parse(created_at_str).replace(tzinfo=None)

                # 신규 채널 필터링 (기준일 이후 생성)
                if created_at > cutoff_date:
                    stats = ch.get('statistics', {})

                    # 비공개 통계 처리
                    subscribers = int(stats.get('subscriberCount', 0))
                    video_count = int(stats.get('videoCount', 0))
                    view_count = int(stats.get('viewCount', 0))

                    new_channel = NewChannel(
                        channel_id=ch['id'],
                        title=ch['snippet']['title'],
                        description=ch['snippet'].get('description', ''),
                        created_at=created_at.strftime('%Y-%m-%d'),
                        created_at_dt=created_at,
                        subscribers=subscribers,
                        video_count=video_count,
                        view_count=view_count,
                        thumbnail_url=ch['snippet']['thumbnails']['default']['url'],
                        channel_url=f"https://youtube.com/channel/{ch['id']}"
                    )

                    new_channel.calculate_metrics()
                    new_channels.append(new_channel)

                    # 월별 카운트
                    month_key = created_at.strftime('%Y-%m')
                    monthly_counter[month_key] += 1

            except Exception as e:
                print(f"[ChannelTrend] 채널 처리 오류: {e}")
                continue

        # 6. 결과 정렬 (최신순)
        new_channels.sort(key=lambda x: x.created_at_dt, reverse=True)

        # 월별 트렌드 정렬
        monthly_trend = dict(sorted(monthly_counter.items()))

        update_progress(f"신규 채널 {len(new_channels)}개 발견")

        # 7. 결과 생성
        result = TrendAnalysisResult(
            keyword=keyword,
            region=region,
            period_months=months,
            analysis_date=datetime.now().strftime("%Y-%m-%d %H:%M"),
            total_videos_searched=len(all_videos),
            unique_channels_found=len(channel_ids),
            new_channels_count=len(new_channels),
            new_channels=new_channels,
            monthly_trend=monthly_trend
        )

        result.calculate_summary()

        # 캐싱
        self._save_cache(cache_key, self._result_to_dict(result))

        return result

    def _result_to_dict(self, result: TrendAnalysisResult) -> dict:
        """결과를 딕셔너리로 변환 (캐싱용)"""
        return {
            "keyword": result.keyword,
            "region": result.region,
            "period_months": result.period_months,
            "analysis_date": result.analysis_date,
            "total_videos_searched": result.total_videos_searched,
            "unique_channels_found": result.unique_channels_found,
            "new_channels_count": result.new_channels_count,
            "new_channels": [c.to_dict() for c in result.new_channels],
            "monthly_trend": result.monthly_trend,
            "avg_subscribers": result.avg_subscribers,
            "avg_video_count": result.avg_video_count,
            "avg_views": result.avg_views,
            "ai_insight": result.ai_insight
        }

    def _dict_to_result(self, data: dict) -> TrendAnalysisResult:
        """딕셔너리를 결과 객체로 변환"""
        new_channels = []
        for ch_data in data.get("new_channels", []):
            try:
                ch = NewChannel(
                    channel_id=ch_data["channel_id"],
                    title=ch_data["title"],
                    description=ch_data.get("description", ""),
                    created_at=ch_data["created_at"],
                    created_at_dt=datetime.strptime(ch_data["created_at"], "%Y-%m-%d"),
                    subscribers=ch_data["subscribers"],
                    video_count=ch_data["video_count"],
                    view_count=ch_data["view_count"],
                    thumbnail_url=ch_data.get("thumbnail_url", ""),
                    channel_url=ch_data.get("channel_url", ""),
                    avg_views_per_video=ch_data.get("avg_views_per_video", 0),
                    subscribers_per_video=ch_data.get("subscribers_per_video", 0),
                    days_since_creation=ch_data.get("days_since_creation", 0),
                    growth_rate=ch_data.get("growth_rate", "보통")
                )
                new_channels.append(ch)
            except Exception as e:
                print(f"[ChannelTrend] 채널 데이터 파싱 오류: {e}")
                continue

        result = TrendAnalysisResult(
            keyword=data["keyword"],
            region=data["region"],
            period_months=data["period_months"],
            analysis_date=data["analysis_date"],
            total_videos_searched=data["total_videos_searched"],
            unique_channels_found=data["unique_channels_found"],
            new_channels_count=data["new_channels_count"],
            new_channels=new_channels,
            monthly_trend=data["monthly_trend"],
            avg_subscribers=data.get("avg_subscribers", 0),
            avg_video_count=data.get("avg_video_count", 0),
            avg_views=data.get("avg_views", 0),
            ai_insight=data.get("ai_insight", "")
        )

        return result

    def generate_ai_insight(
        self,
        result: TrendAnalysisResult,
        ai_client=None
    ) -> str:
        """
        AI를 사용하여 분석 인사이트 생성

        Args:
            result: 트렌드 분석 결과
            ai_client: AI 클라이언트 (Gemini 또는 Claude)
        """
        if not result.new_channels:
            return "분석 기간 내 신규 채널이 발견되지 않았습니다."

        # 프롬프트 구성
        channel_summaries = []
        for ch in result.new_channels[:10]:  # 상위 10개만
            channel_summaries.append(
                f"- {ch.title}: 구독자 {ch.subscribers:,}명, "
                f"영상 {ch.video_count}개, 평균조회수 {ch.avg_views_per_video:,.0f}"
            )

        prompt = f"""
다음은 '{result.keyword}' 키워드로 최근 {result.period_months}개월 내에 생성된 신규 YouTube 채널 분석 결과입니다.

## 분석 개요
- 분석 기간: 최근 {result.period_months}개월
- 검색된 영상 수: {result.total_videos_searched}개
- 발견된 신규 채널: {result.new_channels_count}개
- 평균 구독자: {result.avg_subscribers:,.0f}명
- 평균 영상 수: {result.avg_video_count:.1f}개

## 주요 신규 채널
{chr(10).join(channel_summaries)}

## 월별 채널 생성 추이
{json.dumps(result.monthly_trend, ensure_ascii=False)}

위 데이터를 바탕으로 다음을 분석해주세요:
1. 이 분야의 시장 진입 강도 (레드오션/블루오션 판단)
2. 신규 채널들의 공통적인 특징이나 전략
3. 신규 진입자에게 추천하는 차별화 전략

3-4문장으로 간결하게 요약해주세요.
"""

        if ai_client:
            try:
                # AI API 호출
                response = ai_client.generate_content(prompt)
                return response.text if hasattr(response, 'text') else str(response)
            except Exception as e:
                print(f"[ChannelTrend] AI 분석 오류: {e}")

        # AI 없을 경우 기본 분석
        return self._generate_basic_insight(result)

    def _generate_basic_insight(self, result: TrendAnalysisResult) -> str:
        """기본 인사이트 생성 (AI 없을 때)"""
        if result.new_channels_count == 0:
            return f"최근 {result.period_months}개월간 '{result.keyword}' 분야에 신규 채널이 거의 없습니다. 블루오션 가능성이 있습니다."

        # 월 평균 신규 채널 수
        monthly_avg = result.new_channels_count / result.period_months

        # 성장 채널 비율
        growing = len([c for c in result.new_channels if "급성장" in c.growth_rate or "양호" in c.growth_rate])
        growing_ratio = growing / result.new_channels_count * 100 if result.new_channels_count > 0 else 0

        insights = []

        # 진입 강도 판단
        if monthly_avg >= 5:
            insights.append(f"🔴 월 평균 {monthly_avg:.1f}개의 신규 채널이 생성되고 있어 경쟁이 치열한 레드오션입니다.")
        elif monthly_avg >= 2:
            insights.append(f"🟡 월 평균 {monthly_avg:.1f}개의 신규 채널이 생성되며 적당한 경쟁이 있습니다.")
        else:
            insights.append(f"🟢 월 평균 {monthly_avg:.1f}개의 신규 채널만 생성되어 진입 기회가 있습니다.")

        # 성장 가능성
        if growing_ratio >= 30:
            insights.append(f"신규 채널 중 {growing_ratio:.0f}%가 양호한 성장을 보여 시장 잠재력이 높습니다.")
        else:
            insights.append(f"신규 채널 중 {growing_ratio:.0f}%만 성장하고 있어 차별화 전략이 필요합니다.")

        # 추천
        if result.avg_subscribers > 1000:
            insights.append("평균 구독자가 높아 양질의 콘텐츠로 충분히 성장 가능한 분야입니다.")

        return " ".join(insights)


# 팩토리 함수
def create_channel_trend_analyzer(api_key: str = None) -> ChannelTrendAnalyzer:
    """채널 트렌드 분석기 생성"""
    return ChannelTrendAnalyzer(api_key=api_key)
