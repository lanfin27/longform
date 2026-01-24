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

    # ⭐ 기회 지수 (Opportunity Score) - 핵심 지표!
    opportunity_score: float = 0.0  # 평균조회수 / 구독자수
    opportunity_label: str = ""  # 기회 레벨 라벨

    # 키워드 관련성 지표
    relevance_score: int = 0  # 0-10 점수
    keyword_relevant: bool = False  # 키워드 직접 포함 여부
    relevance_reason: str = ""  # 관련성 이유

    def calculate_metrics(self):
        """성과 지표 계산"""
        if self.video_count > 0:
            self.avg_views_per_video = self.view_count / self.video_count
            self.subscribers_per_video = self.subscribers / self.video_count

        self.days_since_creation = (datetime.now() - self.created_at_dt).days

        # ⭐ 기회 지수 계산: 평균조회수 / 구독자수
        # 구독자가 적은데 조회수가 높다 = 알고리즘이 밀어주는 키워드
        if self.subscribers > 0:
            self.opportunity_score = self.avg_views_per_video / self.subscribers
        else:
            self.opportunity_score = self.avg_views_per_video  # 구독자 0이면 조회수 그대로

        # 기회 지수 레벨 판정
        if self.opportunity_score >= 100:
            self.opportunity_label = "🌟 황금기회"
        elif self.opportunity_score >= 50:
            self.opportunity_label = "✅ 좋은기회"
        elif self.opportunity_score >= 10:
            self.opportunity_label = "🟡 보통"
        else:
            self.opportunity_label = "🔴 포화"

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
            "thumbnail_url": self.thumbnail_url,
            "opportunity_score": round(self.opportunity_score, 2),
            "opportunity_label": self.opportunity_label,
            "relevance_score": self.relevance_score,
            "keyword_relevant": self.keyword_relevant,
            "relevance_reason": self.relevance_reason
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

    # ⭐ 시장 기회 지표 (Market Opportunity Metrics)
    avg_opportunity_score: float = 0.0  # 전체 채널 평균 기회 지수
    market_verdict: str = ""  # blue_ocean, growing, competitive, red_ocean
    market_verdict_label: str = ""  # 한글 라벨
    supply_index: float = 0.0  # 경쟁 강도 (월 평균 신규 채널 수)
    demand_index: float = 0.0  # 수요 지수 (평균 조회수 기반)

    # AI 인사이트
    ai_insight: str = ""

    def calculate_summary(self):
        """요약 통계 및 시장 기회 지표 계산"""
        if self.new_channels:
            self.avg_subscribers = sum(c.subscribers for c in self.new_channels) / len(self.new_channels)
            self.avg_video_count = sum(c.video_count for c in self.new_channels) / len(self.new_channels)
            self.avg_views = sum(c.view_count for c in self.new_channels) / len(self.new_channels)

            # ⭐ 시장 기회 지수 계산
            self._calculate_market_opportunity()

    def _calculate_market_opportunity(self):
        """시장 기회 지표 계산"""
        if not self.new_channels:
            return

        # 1. 평균 기회 지수 (관련 채널만 대상)
        relevant_channels = [c for c in self.new_channels if c.keyword_relevant]
        if relevant_channels:
            self.avg_opportunity_score = sum(c.opportunity_score for c in relevant_channels) / len(relevant_channels)
        else:
            # 관련 채널이 없으면 전체 채널 기준
            self.avg_opportunity_score = sum(c.opportunity_score for c in self.new_channels) / len(self.new_channels)

        # 2. 공급 지수 (경쟁 강도): 월 평균 신규 채널 수
        self.supply_index = self.new_channels_count / max(1, self.period_months)

        # 3. 수요 지수: 평균 조회수 기반 (로그 스케일 정규화)
        avg_views = sum(c.avg_views_per_video for c in self.new_channels) / len(self.new_channels)
        import math
        self.demand_index = math.log10(max(1, avg_views)) * 10  # 0~60 범위

        # 4. 시장 판정 (Market Verdict)
        # 기준: 기회지수 + 공급지수 조합
        if self.avg_opportunity_score >= 50:
            if self.supply_index < 3:
                self.market_verdict = "blue_ocean"
                self.market_verdict_label = "🔵 블루오션"
            else:
                self.market_verdict = "growing"
                self.market_verdict_label = "🟢 성장시장"
        elif self.avg_opportunity_score >= 10:
            if self.supply_index < 5:
                self.market_verdict = "growing"
                self.market_verdict_label = "🟢 성장시장"
            else:
                self.market_verdict = "competitive"
                self.market_verdict_label = "🟡 경쟁시장"
        else:
            if self.supply_index >= 5:
                self.market_verdict = "red_ocean"
                self.market_verdict_label = "🔴 레드오션"
            else:
                self.market_verdict = "competitive"
                self.market_verdict_label = "🟡 경쟁시장"

    def get_rising_stars(self, top_n: int = 5) -> List['NewChannel']:
        """기회 지수가 높은 상위 채널 (라이징 스타) 반환"""
        # 관련 채널 중에서 기회 지수 높은 순
        relevant = [c for c in self.new_channels if c.keyword_relevant]
        if not relevant:
            relevant = self.new_channels

        sorted_channels = sorted(relevant, key=lambda x: x.opportunity_score, reverse=True)
        return sorted_channels[:top_n]

    def get_golden_opportunities(self) -> List['NewChannel']:
        """황금 기회 채널들 (opportunity_score >= 100) 반환"""
        return [c for c in self.new_channels if c.opportunity_score >= 100 and c.keyword_relevant]


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

        # ⭐ 채널별 검색된 영상 매핑 (관련성 분석용)
        channel_videos_map = {}
        for video in all_videos:
            ch_id = video['snippet'].get('channelId')
            if ch_id:
                if ch_id not in channel_videos_map:
                    channel_videos_map[ch_id] = []
                channel_videos_map[ch_id].append({
                    'title': video['snippet'].get('title', ''),
                    'description': video['snippet'].get('description', '')
                })

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

        # 5. 채널 생성일 필터링 + 키워드 관련성 계산 (Step 4) - 핵심!
        update_progress("신규 채널 필터링 및 관련성 분석 중...")
        new_channels: List[NewChannel] = []
        monthly_counter = Counter()

        # 키워드 변형 준비 (관련성 검사용)
        keyword_lower = keyword.lower()
        keyword_variants = self._get_keyword_variants(keyword)

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

                    title = ch['snippet']['title']
                    description = ch['snippet'].get('description', '')

                    new_channel = NewChannel(
                        channel_id=ch['id'],
                        title=title,
                        description=description,
                        created_at=created_at.strftime('%Y-%m-%d'),
                        created_at_dt=created_at,
                        subscribers=subscribers,
                        video_count=video_count,
                        view_count=view_count,
                        thumbnail_url=ch['snippet']['thumbnails']['default']['url'],
                        channel_url=f"https://youtube.com/channel/{ch['id']}"
                    )

                    new_channel.calculate_metrics()

                    # ⭐ 키워드 관련성 계산 (핵심!) - 영상 정보 포함
                    channel_videos = channel_videos_map.get(ch['id'], [])
                    relevance_score, is_relevant, reason = self._calculate_keyword_relevance(
                        title, description, keyword_variants, channel_videos
                    )
                    new_channel.relevance_score = relevance_score
                    new_channel.keyword_relevant = is_relevant
                    new_channel.relevance_reason = reason

                    new_channels.append(new_channel)

                    # 월별 카운트
                    month_key = created_at.strftime('%Y-%m')
                    monthly_counter[month_key] += 1

            except Exception as e:
                print(f"[ChannelTrend] 채널 처리 오류: {e}")
                continue

        # 6. 결과 정렬 (관련성 높은 순 → 최신순)
        # 관련성 점수가 높은 채널이 먼저, 같으면 최신순
        new_channels.sort(key=lambda x: (-x.relevance_score, -x.created_at_dt.timestamp()))

        # 월별 트렌드 정렬
        monthly_trend = dict(sorted(monthly_counter.items()))

        # 관련성 통계 로깅
        relevant_count = len([c for c in new_channels if c.keyword_relevant])
        update_progress(f"신규 채널 {len(new_channels)}개 발견 (키워드 관련: {relevant_count}개)")

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
            "avg_opportunity_score": result.avg_opportunity_score,
            "market_verdict": result.market_verdict,
            "market_verdict_label": result.market_verdict_label,
            "supply_index": result.supply_index,
            "demand_index": result.demand_index,
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
                    growth_rate=ch_data.get("growth_rate", "보통"),
                    opportunity_score=ch_data.get("opportunity_score", 0.0),
                    opportunity_label=ch_data.get("opportunity_label", ""),
                    relevance_score=ch_data.get("relevance_score", 0),
                    keyword_relevant=ch_data.get("keyword_relevant", False),
                    relevance_reason=ch_data.get("relevance_reason", "")
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
            avg_opportunity_score=data.get("avg_opportunity_score", 0.0),
            market_verdict=data.get("market_verdict", ""),
            market_verdict_label=data.get("market_verdict_label", ""),
            supply_index=data.get("supply_index", 0.0),
            demand_index=data.get("demand_index", 0.0),
            ai_insight=data.get("ai_insight", "")
        )

        # 캐시 데이터에 시장 지표가 없으면 다시 계산
        if not result.market_verdict and result.new_channels:
            result._calculate_market_opportunity()

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

    def _get_keyword_variants(self, keyword: str) -> List[str]:
        """
        키워드의 다양한 변형 생성 (관련성 검사용)

        예: "브이로그" → ["브이로그", "vlog", "v-log", "일상", "데일리"]
        예: "일본" → ["일본", "japan", "japanese", "도쿄", "tokyo", ...]
        """
        keyword_lower = keyword.lower()
        variants = [keyword_lower]

        # 한글-영어 매핑 (확장된 버전)
        korean_english_map = {
            # === 국가/지역 ===
            "일본": ["japan", "japanese", "일본", "도쿄", "tokyo", "오사카", "osaka",
                    "교토", "kyoto", "후쿠오카", "fukuoka", "나고야", "nagoya",
                    "삿포로", "sapporo", "오키나와", "okinawa", "일드", "j-pop",
                    "jvlog", "일본여행", "일본생활", "일본일상", "재팬", "니혼"],
            "japan": ["japan", "japanese", "일본", "tokyo", "osaka", "kyoto"],
            "한국": ["korea", "korean", "한국", "서울", "seoul", "부산", "busan",
                    "k-pop", "kpop", "한류", "코리아"],
            "미국": ["usa", "america", "american", "미국", "뉴욕", "newyork", "la",
                    "los angeles", "미국생활", "미국일상"],
            "중국": ["china", "chinese", "중국", "베이징", "beijing", "상하이", "shanghai"],
            "유럽": ["europe", "european", "유럽", "프랑스", "france", "독일", "germany",
                    "이탈리아", "italy", "스페인", "spain", "영국", "uk", "london"],
            "동남아": ["southeast asia", "동남아", "태국", "thailand", "베트남", "vietnam",
                      "필리핀", "philippines", "인도네시아", "indonesia", "싱가포르", "singapore"],

            # === 콘텐츠 유형 ===
            "브이로그": ["vlog", "v-log", "v log", "브이로그", "일상", "데일리", "daily",
                       "일상기록", "일상브이로그", "vlogger", "브이로거"],
            "vlog": ["vlog", "v-log", "브이로그", "일상", "데일리", "daily", "vlogger"],
            "먹방": ["mukbang", "eating show", "먹방", "맛집", "음식", "food", "eating",
                    "foodie", "먹스타그램", "푸드", "맛집탐방", "먹방유튜버"],
            "리뷰": ["review", "리뷰", "언박싱", "unboxing", "사용기", "후기", "리뷰어"],
            "게임": ["game", "gaming", "게임", "겜", "플레이", "gameplay", "gamer",
                    "게이머", "스트리머", "streamer", "실황", "공략"],
            "쿠킹": ["cooking", "cook", "쿠킹", "요리", "레시피", "recipe", "chef",
                    "요리사", "쿡방", "요리법", "집밥"],
            "뷰티": ["beauty", "뷰티", "메이크업", "makeup", "화장", "스킨케어", "skincare",
                    "cosmetic", "화장품", "뷰티유튜버"],
            "여행": ["travel", "여행", "트래블", "trip", "투어", "tour", "관광", "tourism",
                    "여행기", "여행브이로그", "traveler", "해외여행", "국내여행"],
            "재테크": ["finance", "재테크", "투자", "주식", "부동산", "money", "stock",
                      "investment", "부업", "경제", "금융"],
            "운동": ["fitness", "workout", "운동", "헬스", "gym", "다이어트", "diet",
                    "exercise", "홈트", "홈트레이닝", "피트니스"],
            "공부": ["study", "공부", "스터디", "공스타그램", "studywithme", "학습",
                    "수험생", "공부법", "자기계발"],
            "육아": ["parenting", "육아", "아기", "baby", "키즈", "kids", "child",
                    "엄마", "아빠", "부모", "유아", "어린이"],
            "음악": ["music", "음악", "노래", "song", "singing", "cover", "커버",
                    "뮤직", "musician", "가수"],
            "패션": ["fashion", "패션", "옷", "outfit", "ootd", "스타일", "style",
                    "코디", "의류", "패션유튜버"],
            "테크": ["tech", "technology", "테크", "기술", "it", "gadget", "가젯",
                    "스마트폰", "전자기기", "리뷰"],
            "자동차": ["car", "auto", "자동차", "차량", "드라이브", "drive", "vehicle",
                      "카리뷰", "시승기"],
            "반려동물": ["pet", "반려동물", "강아지", "dog", "고양이", "cat", "애완동물",
                       "펫", "동물"],

            # === 재테크/금융 (신규 추가) ===
            "연말정산": ["연말정산", "세금", "tax", "세무", "절세", "소득공제", "세액공제",
                       "국세청", "홈택스", "세무사", "회계사", "연금", "보험", "급여",
                       "13월의월급", "환급", "신고", "원천징수", "근로소득"],
            "재테크": ["재테크", "finance", "투자", "investment", "주식", "stock", "부동산",
                      "real estate", "저축", "적금", "예금", "펀드", "etf", "배당",
                      "자산", "경제", "돈", "money", "부업", "파이프라인"],
            "세금": ["세금", "tax", "세무", "절세", "연말정산", "국세청", "홈택스",
                    "세무사", "회계", "신고", "납세", "종합소득세", "부가세"],
            "주식": ["주식", "stock", "투자", "investment", "배당", "etf", "증권",
                    "주린이", "주식투자", "차트", "매매", "종목", "코스피", "코스닥"],
            "부동산": ["부동산", "real estate", "아파트", "청약", "분양", "임대", "전세",
                      "월세", "매매", "갭투자", "투자", "재건축", "재개발"],
            "경제": ["경제", "economy", "금융", "finance", "시장", "market", "투자",
                    "돈", "money", "자산", "wealth"],
        }

        # 정확한 키워드 매칭
        if keyword_lower in korean_english_map:
            variants.extend(korean_english_map[keyword_lower])

        # 부분 매칭 (키워드가 더 긴 경우 - 예: "일본여행")
        for key, values in korean_english_map.items():
            if key in keyword_lower or keyword_lower in key:
                variants.extend(values)

        # 중복 제거하고 원본 키워드가 항상 첫 번째가 되도록
        unique_variants = list(set([v.lower() for v in variants]))
        if keyword_lower in unique_variants:
            unique_variants.remove(keyword_lower)
        return [keyword_lower] + unique_variants

    def _calculate_keyword_relevance(
        self,
        title: str,
        description: str,
        keyword_variants: List[str],
        channel_videos: List[Dict] = None
    ) -> Tuple[int, bool, str]:
        """
        채널의 키워드 관련성 점수 계산 (v2.0 - 영상 정보 활용)

        핵심 통찰: 키워드로 검색해서 나온 채널은 기본적으로 관련있음!

        Args:
            title: 채널명
            description: 채널 설명
            keyword_variants: 키워드 변형 목록
            channel_videos: 해당 채널에서 검색된 영상 목록 (관련성 판단에 활용)

        Returns:
            Tuple[int, bool, str]: (점수 0-10, 직접관련여부, 관련성 이유)
        """
        score = 0
        reasons = []

        title_lower = title.lower()
        desc_lower = description.lower() if description else ""

        # 원본 키워드 (첫 번째)
        main_keyword = keyword_variants[0] if keyword_variants else ""

        # ⭐ 0. 검색 결과에서 나온 채널 = 기본 관련성 있음 (+3점)
        # 키워드로 검색해서 나온 영상의 채널이므로 기본적으로 관련있다고 판단
        if channel_videos:
            score += 3
            reasons.append(f"키워드 검색 결과 채널")

            # 영상 제목에서 키워드 매칭 확인 (+2점)
            video_title_matched = False
            for video in channel_videos:
                video_title = video.get('title', '').lower()
                for variant in keyword_variants:
                    if variant in video_title:
                        if not video_title_matched:
                            score += 2
                            reasons.append(f"영상 제목에 '{variant}' 포함")
                            video_title_matched = True
                        break
                if video_title_matched:
                    break

        # 1. 채널명에 키워드 직접 포함 (가장 중요: 최대 +5점)
        title_match = False
        for variant in keyword_variants:
            if variant in title_lower:
                # 메인 키워드 매칭은 +5점, 관련 키워드는 +3점
                if variant == main_keyword:
                    score += 5
                elif not title_match:  # 첫 번째 관련 키워드만
                    score += 3
                title_match = True
                reasons.append(f"채널명에 '{variant}' 포함")
                break

        # 2. 설명에 키워드 포함 (최대 +3점)
        desc_matched = []
        for variant in keyword_variants:
            if variant in desc_lower and variant not in desc_matched:
                desc_matched.append(variant)

        if desc_matched:
            # 메인 키워드가 설명에 있으면 +3점, 관련 키워드는 개당 +1점 (최대 2점)
            if main_keyword in desc_matched:
                score += 3
                reasons.append(f"설명에 '{main_keyword}' 포함")
            else:
                score += min(len(desc_matched), 2)
                reasons.append(f"설명에 관련어 {len(desc_matched)}개 포함")

        # 3. 키워드가 채널 주제인지 판단 (테마 키워드 패턴)
        theme_keywords = {
            # 국가/지역 테마
            "일본": ["일본유튜버", "일본생활", "일본브이로그", "재일교포", "도쿄생활",
                    "일본먹방", "일본여행", "japan vlog", "일본일상", "in japan",
                    "japanese", "tokyo life", "일본이민", "일본취업"],
            "japan": ["japan vlog", "living in japan", "tokyo", "japanese life"],
            "한국": ["한국유튜버", "korean vlog", "korea life", "seoul", "한국생활"],
            "미국": ["미국유튜버", "미국생활", "usa vlog", "american life", "la생활"],

            # 콘텐츠 테마
            "브이로그": ["vlogger", "일상유튜버", "데일리", "daily life", "일상기록"],
            "vlog": ["vlogger", "daily life", "lifestyle", "day in my life"],
            "먹방": ["먹방러", "푸드크리에이터", "food creator", "eating show", "mukbanger"],
            "게임": ["게이머", "gamer", "streamer", "게임유튜버", "gaming channel"],
            "뷰티": ["뷰티크리에이터", "beauty creator", "makeup artist", "뷰티유튜버"],
            "여행": ["여행유튜버", "traveler", "travel vlog", "여행크리에이터"],
            "음악": ["musician", "singer", "cover artist", "음악유튜버"],
            "요리": ["chef", "cook", "cooking channel", "요리유튜버", "쿡방"],

            # ⭐ 재테크/금융 테마 (신규 추가)
            "연말정산": ["세무", "tax", "세금", "절세", "소득공제", "세액공제", "국세청", "홈택스",
                       "세무사", "회계사", "재테크", "연금", "보험", "급여", "월급", "소득"],
            "재테크": ["투자", "주식", "부동산", "금융", "저축", "적금", "예금", "펀드",
                      "etf", "배당", "자산", "경제", "돈", "money", "finance"],
            "세금": ["tax", "세무", "절세", "국세청", "홈택스", "세무사", "회계", "신고"],
            "주식": ["stock", "투자", "배당", "etf", "증권", "주린이", "주식투자"],
            "부동산": ["real estate", "아파트", "청약", "분양", "임대", "전세", "월세"],
        }

        if main_keyword in theme_keywords:
            for theme in theme_keywords[main_keyword]:
                theme_lower = theme.lower()
                if theme_lower in title_lower or theme_lower in desc_lower:
                    score += 2
                    reasons.append(f"'{theme}' 테마 발견")
                    break

        # 4. 전문 채널 패턴 보너스 (+1점)
        specialty_patterns = ["채널", "channel", "tv", "튜브", "tube", "유튜버", "youtuber", "크리에이터", "creator"]
        for pattern in specialty_patterns:
            if pattern in title_lower:
                # 키워드 + 채널명 패턴 (예: "일본채널", "japan tv")
                for variant in keyword_variants[:5]:  # 상위 5개 변형만 확인
                    if variant in title_lower:
                        score += 1
                        reasons.append(f"전문채널 패턴")
                        break
                break

        # 5. 관련 없는 패턴 감점 (스팸, 자동생성 등) - 단, 검색 결과 채널은 덜 감점
        spam_patterns = ["shorts", "쇼츠", "클립", "clip", "highlight", "하이라이트", "best moments"]
        if not title_match and not channel_videos:  # 채널명에 키워드 없고 검색 결과도 아닌 경우만 감점
            for pattern in spam_patterns:
                if pattern in title_lower:
                    score = max(0, score - 1)
                    reasons.append(f"'{pattern}' 패턴 감점")
                    break

        # 6. 최종 점수 정규화 (0-10)
        final_score = min(10, max(0, score))

        # ⭐ 키워드 직접 관련 여부 (검색 결과 채널이거나, 채널명에 포함되거나, 점수 3 이상)
        # 기존: title_match or final_score >= 4
        # 수정: 검색 결과에서 나온 채널은 기본적으로 관련있음
        is_relevant = bool(channel_videos) or title_match or final_score >= 3

        reason_str = ", ".join(reasons) if reasons else "관련성 낮음"

        return final_score, is_relevant, reason_str


# 팩토리 함수
def create_channel_trend_analyzer(api_key: str = None) -> ChannelTrendAnalyzer:
    """채널 트렌드 분석기 생성"""
    return ChannelTrendAnalyzer(api_key=api_key)
