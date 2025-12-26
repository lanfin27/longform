# -*- coding: utf-8 -*-
"""
YouTube API 서비스 모듈 (완전판) v2.0

기능:
- 페이지네이션 지원 (최대 200개 결과)
- 한국어 필터링
- 채널 정보 조회
- 성과 지표 계산 (전일 기여도, 시간도 비율, 참여율)

v2.0 추가:
- 검색 범위 필터링 (제목만, 제목+설명, 채널명 포함, 전체)
"""

# 검색 범위 옵션
SEARCH_SCOPE_OPTIONS = {
    "제목만 검색": "title_only",
    "제목 + 설명": "title_description",
    "채널명 포함": "include_channel",
    "전체": "all"
}

import requests
import re
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import YOUTUBE_API_KEY


class YouTubeService:
    """YouTube API 서비스 클래스"""

    BASE_URL = "https://www.googleapis.com/youtube/v3"

    # 업로드 날짜 옵션
    UPLOAD_DATE_OPTIONS = {
        "전체": None,
        "오늘": 1,
        "이번 주": 7,
        "이번 달": 30,
        "3개월": 90,
        "올해": 365
    }

    # 영상 길이 옵션
    DURATION_OPTIONS = {
        "전체": "any",
        "4분 미만 (쇼츠)": "short",
        "4-20분 (표준)": "medium",
        "20분 초과 (롱폼)": "long"
    }

    # 정렬 옵션
    SORT_OPTIONS = {
        "관련성": "relevance",
        "조회수 높은순": "viewCount",
        "업로드 날짜순": "date",
        "평점순": "rating"
    }

    # 국가 코드
    COUNTRY_OPTIONS = {
        "한국": "KR",
        "미국": "US",
        "일본": "JP",
        "베트남": "VN",
        "영국": "GB",
        "캐나다": "CA",
        "독일": "DE",
        "프랑스": "FR",
        "인도": "IN",
        "인도네시아": "ID",
        "브라질": "BR",
        "멕시코": "MX",
        "태국": "TH",
        "대만": "TW",
        "홍콩": "HK"
    }

    def __init__(self, api_key: str = None):
        self.api_key = api_key or YOUTUBE_API_KEY
        if not self.api_key:
            raise ValueError("YouTube API 키가 필요합니다")
        self.session = requests.Session()
        self._channel_cache = {}  # 채널 정보 캐시

    # ==================== 검색 API ====================

    def search_videos(
        self,
        query: str,
        upload_date: str = "이번 주",
        duration: str = "전체",
        order: str = "조회수 높은순",
        country: str = "한국",
        max_results: int = 200,
        filter_korean: bool = True,
        progress_callback=None
    ) -> Tuple[List[Dict], dict]:
        """
        영상 검색 (페이지네이션 포함)

        Args:
            query: 검색 키워드
            upload_date: 업로드 기간
            duration: 영상 길이
            order: 정렬 방식
            country: 국가
            max_results: 최대 결과 수 (최대 200)
            filter_korean: 한국어 영상만 필터링
            progress_callback: 진행 콜백 (current, total, message)

        Returns:
            (videos, stats) - 영상 목록과 검색 통계
        """

        # 파라미터 변환
        duration_param = self.DURATION_OPTIONS.get(duration, "any")
        order_param = self.SORT_OPTIONS.get(order, "viewCount")
        region_code = self.COUNTRY_OPTIONS.get(country, "KR")

        # 업로드 날짜 계산
        published_after = None
        days = self.UPLOAD_DATE_OPTIONS.get(upload_date)
        if days:
            published_after = datetime.utcnow() - timedelta(days=days)

        # 검색 실행 (페이지네이션)
        all_video_ids = []
        next_page_token = None
        page_count = 0
        max_pages = min((max_results // 50) + 1, 4)  # 최대 4페이지 (200개)

        stats = {
            'query': query,
            'total_api_results': 0,
            'pages_fetched': 0,
            'videos_before_filter': 0,
            'videos_after_filter': 0,
            'api_calls': 0
        }

        print(f"\n{'='*60}")
        print(f"[YouTubeService] 검색: '{query}'")
        print(f"   지역: {country} ({region_code})")
        print(f"   기간: {upload_date}")
        print(f"   길이: {duration}")
        print(f"   정렬: {order}")
        print(f"   최대 결과: {max_results}개")
        print(f"{'='*60}")

        while page_count < max_pages and len(all_video_ids) < max_results:
            params = {
                'part': 'snippet',
                'q': query,
                'type': 'video',
                'regionCode': region_code,
                'relevanceLanguage': 'ko',  # 한국어 우선
                'maxResults': 50,
                'order': order_param,
                'key': self.api_key,
            }

            if duration_param != 'any':
                params['videoDuration'] = duration_param

            if published_after:
                params['publishedAfter'] = published_after.strftime('%Y-%m-%dT%H:%M:%SZ')

            if next_page_token:
                params['pageToken'] = next_page_token

            try:
                response = self.session.get(
                    f"{self.BASE_URL}/search",
                    params=params,
                    timeout=30
                )
                response.raise_for_status()
                data = response.json()
                stats['api_calls'] += 1

                items = data.get('items', [])

                if page_count == 0:
                    stats['total_api_results'] = data.get('pageInfo', {}).get('totalResults', 0)

                if not items:
                    break

                for item in items:
                    video_id = item.get('id', {}).get('videoId')
                    if video_id:
                        all_video_ids.append(video_id)

                print(f"   페이지 {page_count + 1}: {len(items)}개 (누적: {len(all_video_ids)}개)")

                if progress_callback:
                    progress_callback(
                        len(all_video_ids),
                        max_results,
                        f"검색 중... 페이지 {page_count + 1}"
                    )

                next_page_token = data.get('nextPageToken')
                if not next_page_token:
                    break

                page_count += 1
                time.sleep(0.2)

            except Exception as e:
                print(f"[YouTubeService] 검색 오류: {e}")
                break

        stats['pages_fetched'] = page_count + 1
        stats['videos_before_filter'] = len(all_video_ids)

        # 상세 정보 조회
        videos = []
        if all_video_ids:
            videos, detail_calls = self.get_videos_details(
                all_video_ids[:max_results],
                progress_callback
            )
            stats['api_calls'] += detail_calls

        # 한국어 필터링
        if filter_korean and videos:
            videos = self._filter_korean_videos(videos)

        stats['videos_after_filter'] = len(videos)

        print(f"\n[YouTubeService] 검색 완료:")
        print(f"   API 전체 결과: {stats['total_api_results']:,}개")
        print(f"   가져온 페이지: {stats['pages_fetched']}개")
        print(f"   필터 전: {stats['videos_before_filter']}개")
        print(f"   필터 후: {stats['videos_after_filter']}개")
        print(f"   API 호출: {stats['api_calls']}회")
        print(f"{'='*60}\n")

        return videos, stats

    def get_videos_details(
        self,
        video_ids: List[str],
        progress_callback=None
    ) -> Tuple[List[Dict], int]:
        """비디오 상세 정보 일괄 조회"""

        all_videos = []
        api_calls = 0

        # 50개씩 배치 처리
        for i in range(0, len(video_ids), 50):
            batch_ids = video_ids[i:i + 50]

            params = {
                'part': 'snippet,statistics,contentDetails',
                'id': ','.join(batch_ids),
                'key': self.api_key,
            }

            try:
                response = self.session.get(
                    f"{self.BASE_URL}/videos",
                    params=params,
                    timeout=30
                )
                response.raise_for_status()
                data = response.json()
                api_calls += 1

                for item in data.get('items', []):
                    video = self._parse_video_item(item)
                    all_videos.append(video)

                if progress_callback:
                    progress_callback(
                        len(all_videos),
                        len(video_ids),
                        f"상세 정보 조회 중... {len(all_videos)}/{len(video_ids)}"
                    )

                time.sleep(0.1)

            except Exception as e:
                print(f"[YouTubeService] 상세 정보 조회 오류: {e}")

        # 채널 구독자 수 추가
        channel_calls = self._add_channel_subscribers(all_videos)
        api_calls += channel_calls

        # 성과 지표 계산
        self._calculate_metrics(all_videos)

        return all_videos, api_calls

    def _parse_video_item(self, item: dict) -> dict:
        """비디오 아이템 파싱"""

        snippet = item.get('snippet', {})
        statistics = item.get('statistics', {})
        content_details = item.get('contentDetails', {})

        duration_seconds = self._parse_duration(content_details.get('duration', 'PT0S'))

        return {
            'video_id': item['id'],
            'title': snippet.get('title', ''),
            'description': snippet.get('description', '')[:200],
            'channel_id': snippet.get('channelId', ''),
            'channel_title': snippet.get('channelTitle', ''),
            'thumbnail_url': snippet.get('thumbnails', {}).get('high', {}).get('url', ''),
            'published_at': snippet.get('publishedAt', ''),
            'default_language': snippet.get('defaultLanguage', ''),
            'default_audio_language': snippet.get('defaultAudioLanguage', ''),

            # 통계
            'view_count': int(statistics.get('viewCount', 0)),
            'like_count': int(statistics.get('likeCount', 0)),
            'comment_count': int(statistics.get('commentCount', 0)),

            # 길이
            'duration': content_details.get('duration', 'PT0S'),
            'duration_seconds': duration_seconds,
            'duration_formatted': self._format_duration(content_details.get('duration', 'PT0S')),

            # 영상 유형
            'video_type': 'shorts' if duration_seconds <= 60 else 'long_form',

            # URL
            'video_url': f"https://www.youtube.com/watch?v={item['id']}",
            'channel_url': f"https://www.youtube.com/channel/{snippet.get('channelId', '')}",
        }

    def _filter_korean_videos(self, videos: List[Dict]) -> List[Dict]:
        """한국어 영상 필터링"""

        korean_videos = []

        for video in videos:
            is_korean = False

            # 1. 언어 메타데이터
            audio_lang = video.get('default_audio_language', '')
            default_lang = video.get('default_language', '')

            if audio_lang.startswith('ko') or default_lang.startswith('ko'):
                is_korean = True

            # 2. 제목에 한글 포함
            if self._has_korean(video.get('title', '')):
                is_korean = True

            # 3. 채널명에 한글 포함
            if self._has_korean(video.get('channel_title', '')):
                is_korean = True

            if is_korean:
                korean_videos.append(video)

        return korean_videos

    @staticmethod
    def _has_korean(text: str) -> bool:
        """한글 포함 여부 확인"""
        return bool(re.search('[가-힣ㄱ-ㅎㅏ-ㅣ]', text))

    @staticmethod
    def _parse_duration(duration: str) -> int:
        """ISO 8601 duration을 초 단위로 변환"""
        match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', duration)
        if not match:
            return 0

        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        seconds = int(match.group(3) or 0)

        return hours * 3600 + minutes * 60 + seconds

    @staticmethod
    def _format_duration(duration: str) -> str:
        """ISO 8601 duration을 HH:MM:SS로 변환"""
        match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', duration)
        if not match:
            return "0:00"

        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        seconds = int(match.group(3) or 0)

        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes}:{seconds:02d}"

    # ==================== 채널 API ====================

    def get_channel_details(self, channel_id: str) -> Dict:
        """채널 상세 정보 조회"""

        # 캐시 확인
        if channel_id in self._channel_cache:
            return self._channel_cache[channel_id]

        params = {
            'part': 'snippet,statistics',
            'id': channel_id,
            'key': self.api_key,
        }

        try:
            response = self.session.get(
                f"{self.BASE_URL}/channels",
                params=params,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()

            if data.get('items'):
                item = data['items'][0]
                channel = {
                    'channel_id': channel_id,
                    'channel_title': item['snippet']['title'],
                    'description': item['snippet'].get('description', '')[:200],
                    'thumbnail_url': item['snippet']['thumbnails'].get('default', {}).get('url', ''),
                    'subscriber_count': int(item['statistics'].get('subscriberCount', 0)),
                    'video_count': int(item['statistics'].get('videoCount', 0)),
                    'view_count': int(item['statistics'].get('viewCount', 0)),
                    'channel_url': f"https://www.youtube.com/channel/{channel_id}",
                    'published_at': item['snippet'].get('publishedAt', ''),
                }

                # 캐시 저장
                self._channel_cache[channel_id] = channel

                return channel

        except Exception as e:
            print(f"[YouTubeService] 채널 정보 조회 오류 ({channel_id}): {e}")

        return {}

    def get_channels_details(self, channel_ids: List[str]) -> Tuple[List[Dict], int]:
        """여러 채널 정보 일괄 조회"""

        channels = []
        api_calls = 0

        # 캐시에 없는 채널만 조회
        uncached_ids = [cid for cid in channel_ids if cid not in self._channel_cache]

        # 50개씩 배치 처리
        for i in range(0, len(uncached_ids), 50):
            batch_ids = uncached_ids[i:i + 50]

            params = {
                'part': 'snippet,statistics',
                'id': ','.join(batch_ids),
                'key': self.api_key,
            }

            try:
                response = self.session.get(
                    f"{self.BASE_URL}/channels",
                    params=params,
                    timeout=30
                )
                response.raise_for_status()
                data = response.json()
                api_calls += 1

                for item in data.get('items', []):
                    channel_id = item['id']
                    channel = {
                        'channel_id': channel_id,
                        'channel_title': item['snippet']['title'],
                        'subscriber_count': int(item['statistics'].get('subscriberCount', 0)),
                        'video_count': int(item['statistics'].get('videoCount', 0)),
                        'view_count': int(item['statistics'].get('viewCount', 0)),
                    }
                    self._channel_cache[channel_id] = channel

                time.sleep(0.1)

            except Exception as e:
                print(f"[YouTubeService] 채널 일괄 조회 오류: {e}")

        # 결과 수집
        for cid in channel_ids:
            if cid in self._channel_cache:
                channels.append(self._channel_cache[cid])

        return channels, api_calls

    def _add_channel_subscribers(self, videos: List[Dict]) -> int:
        """비디오 목록에 채널 구독자 수 추가"""

        # 고유 채널 ID 수집
        channel_ids = list(set(v.get('channel_id', '') for v in videos if v.get('channel_id')))

        # 채널 정보 조회
        _, api_calls = self.get_channels_details(channel_ids)

        # 구독자 수 추가
        for video in videos:
            channel_id = video.get('channel_id', '')
            if channel_id in self._channel_cache:
                video['subscriber_count'] = self._channel_cache[channel_id].get('subscriber_count', 0)
            else:
                video['subscriber_count'] = 0

        return api_calls

    def search_channel_videos(
        self,
        channel_id: str,
        max_results: int = 50,
        order: str = "date"
    ) -> List[Dict]:
        """특정 채널의 영상 검색"""

        params = {
            'part': 'snippet',
            'channelId': channel_id,
            'type': 'video',
            'order': order,
            'maxResults': min(max_results, 50),
            'key': self.api_key,
        }

        try:
            response = self.session.get(
                f"{self.BASE_URL}/search",
                params=params,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()

            video_ids = [item['id']['videoId'] for item in data.get('items', [])]

            if video_ids:
                videos, _ = self.get_videos_details(video_ids)
                return videos

        except Exception as e:
            print(f"[YouTubeService] 채널 영상 검색 오류: {e}")

        return []

    # ==================== 성과 지표 계산 ====================

    def _calculate_metrics(self, videos: List[Dict]):
        """성과 지표 계산"""

        now = datetime.utcnow()

        for video in videos:
            try:
                # 업로드 후 경과 시간 (시간)
                published_at = video.get('published_at', '')
                if published_at:
                    pub_date = datetime.fromisoformat(published_at.replace('Z', '+00:00'))
                    hours_since = (now - pub_date.replace(tzinfo=None)).total_seconds() / 3600
                    video['hours_since_upload'] = max(hours_since, 1)

                    # 업로드 후 일수
                    video['days_since_upload'] = round(hours_since / 24, 1)
                else:
                    video['hours_since_upload'] = 1
                    video['days_since_upload'] = 0

                # 시간당 조회수 (시간도 비율)
                view_count = video.get('view_count', 0)
                video['views_per_hour'] = round(view_count / video['hours_since_upload'], 2)

                # 일일 평균 조회수
                if video['days_since_upload'] > 0:
                    video['daily_views'] = round(view_count / video['days_since_upload'], 0)
                else:
                    video['daily_views'] = view_count

                # 전일 기여도 (최근 24시간 조회수 비중 추정)
                daily_views = video['views_per_hour'] * 24
                if view_count > 0:
                    video['daily_contribution'] = min(round((daily_views / view_count) * 100, 2), 100)
                else:
                    video['daily_contribution'] = 0

                # 참여율
                engagement = video.get('like_count', 0) + video.get('comment_count', 0)
                if view_count > 0:
                    video['engagement_rate'] = round((engagement / view_count) * 100, 2)
                else:
                    video['engagement_rate'] = 0

                # 구독자 대비 조회수
                subscriber_count = video.get('subscriber_count', 0)
                if subscriber_count > 0:
                    video['views_per_subscriber'] = round(view_count / subscriber_count, 2)
                else:
                    video['views_per_subscriber'] = 0

            except Exception as e:
                print(f"[YouTubeService] 지표 계산 오류 ({video.get('video_id')}): {e}")
                video['hours_since_upload'] = 0
                video['days_since_upload'] = 0
                video['views_per_hour'] = 0
                video['daily_views'] = 0
                video['daily_contribution'] = 0
                video['engagement_rate'] = 0
                video['views_per_subscriber'] = 0

    # ==================== 유틸리티 ====================

    @staticmethod
    def format_number(num: int) -> str:
        """숫자 포맷팅 (1000 -> 1천, 10000 -> 1만)"""
        if num >= 100000000:
            return f"{num/100000000:.1f}억"
        elif num >= 10000:
            return f"{num/10000:.1f}만"
        elif num >= 1000:
            return f"{num/1000:.1f}천"
        return str(num)

    @staticmethod
    def format_date(iso_date: str) -> str:
        """ISO 날짜를 한국어 형식으로"""
        try:
            dt = datetime.fromisoformat(iso_date.replace('Z', '+00:00'))
            return dt.strftime('%Y-%m-%d %H:%M')
        except:
            return iso_date[:10] if len(iso_date) >= 10 else iso_date

    def test_api_key(self) -> Tuple[bool, str]:
        """API 키 유효성 테스트"""

        params = {
            'part': 'snippet',
            'q': 'test',
            'type': 'video',
            'maxResults': 1,
            'key': self.api_key,
        }

        try:
            response = self.session.get(
                f"{self.BASE_URL}/search",
                params=params,
                timeout=10
            )

            if response.status_code == 200:
                return True, "API 키 유효"
            elif response.status_code == 403:
                error_data = response.json()
                error_msg = error_data.get('error', {}).get('message', 'API 키 무효 또는 할당량 초과')
                return False, error_msg
            else:
                return False, f"API 오류: {response.status_code}"

        except Exception as e:
            return False, f"연결 오류: {e}"

    def to_excel_format(self, video: Dict) -> Dict:
        """영상을 Excel 내보내기 형식으로 변환"""
        return {
            '영상 제목': video.get('title', ''),
            '영상 URL': video.get('video_url', ''),
            '영상 유형': '쇼츠' if video.get('video_type') == 'shorts' else '롱폼',
            '영상 길이': video.get('duration_formatted', ''),
            '업로드일': self.format_date(video.get('published_at', '')),
            '조회수': video.get('view_count', 0),
            '좋아요': video.get('like_count', 0),
            '댓글수': video.get('comment_count', 0),
            '채널명': video.get('channel_title', ''),
            '채널 URL': video.get('channel_url', ''),
            '구독자수': video.get('subscriber_count', 0),
            '구독자 대비 조회수': video.get('views_per_subscriber', 0),
            '참여율(%)': video.get('engagement_rate', 0),
            '업로드 후 일수': video.get('days_since_upload', 0),
            '일일 평균 조회수': video.get('daily_views', 0),
            '시간당 조회수': video.get('views_per_hour', 0),
            '전일 기여도(%)': video.get('daily_contribution', 0),
        }


# ============================================================
# 검색 범위 필터링 함수 (v2.0)
# ============================================================

def filter_videos_by_search_scope(
    videos: List[Dict],
    query: str,
    scope: str = "title_only"
) -> List[Dict]:
    """
    검색 범위에 따라 비디오 필터링

    이 함수는 YouTube API 검색 후 결과를 필터링합니다.
    YouTube API는 검색 범위를 직접 지정할 수 없으므로,
    검색 결과를 가져온 후 필터링하는 방식으로 구현합니다.

    Args:
        videos: 검색된 비디오 목록
        query: 검색 키워드
        scope: 검색 범위
            - title_only: 제목에만 키워드 포함 (채널명만 매칭되면 제외)
            - title_description: 제목 또는 설명에 키워드 포함
            - include_channel: 채널명에도 키워드 포함 허용 (기존 방식)
            - all: 모든 결과 반환

    Returns:
        필터링된 비디오 목록

    Example:
        검색어: "회계사"
        - "김희연회계사" 채널의 "오늘의 뉴스" 영상 → 제목에 '회계사' 없음
          - title_only: ❌ 제외
          - include_channel: ✅ 포함

        - "경제 채널"의 "회계사 되는 법" 영상 → 제목에 '회계사' 있음
          - title_only: ✅ 포함
          - include_channel: ✅ 포함
    """

    if scope == "all" or scope == "include_channel":
        # 기존 방식: 모든 결과 반환
        return videos

    if not query or not query.strip():
        return videos

    query_lower = query.lower().strip()
    # 여러 단어로 분리 (공백 또는 쉼표)
    query_parts = [p.strip() for p in re.split(r'[\s,]+', query_lower) if p.strip()]

    if not query_parts:
        return videos

    filtered = []
    excluded_count = 0

    for video in videos:
        # 각 필드 추출
        title = (video.get('title', '') or '').lower()
        description = (video.get('description', '') or '').lower()
        channel = (video.get('channel_title', '') or video.get('channel_name', '') or '').lower()

        # 키워드 매칭 확인 (모든 키워드가 해당 필드에 있는지)
        title_match = any(part in title for part in query_parts)
        desc_match = any(part in description for part in query_parts)
        channel_match = any(part in channel for part in query_parts)

        # 검색 범위에 따른 필터링
        if scope == "title_only":
            # 제목에 키워드가 있어야 포함
            # 채널명에만 있고 제목에 없으면 제외
            if title_match:
                filtered.append(video)
            elif channel_match and not title_match:
                # 채널명에만 키워드 있음 → 제외
                excluded_count += 1
                print(f"  ⛔ 제외 (채널명만 매칭): {video.get('title', '')[:40]}... [채널: {channel[:20]}]")
            else:
                # 어디에도 키워드 없음 → 제외 (이 경우는 거의 없음)
                excluded_count += 1

        elif scope == "title_description":
            # 제목 또는 설명에 키워드가 있어야 포함
            if title_match or desc_match:
                filtered.append(video)
            elif channel_match and not (title_match or desc_match):
                # 채널명에만 키워드 있음 → 제외
                excluded_count += 1
                print(f"  ⛔ 제외 (채널명만 매칭): {video.get('title', '')[:40]}... [채널: {channel[:20]}]")
            else:
                excluded_count += 1

    print(f"\n📊 검색 범위 필터링 결과:")
    print(f"   - 검색 범위: {scope}")
    print(f"   - 검색어: '{query}'")
    print(f"   - 원본: {len(videos)}개")
    print(f"   - 필터링 후: {len(filtered)}개")
    print(f"   - 제외됨: {excluded_count}개")

    return filtered


def get_search_scope_description(scope: str) -> str:
    """검색 범위 설명 반환"""
    descriptions = {
        "title_only": "ℹ️ 영상 제목에 키워드가 포함된 영상만 검색합니다. 채널명에만 키워드가 있는 경우 제외됩니다.",
        "title_description": "ℹ️ 제목 또는 설명에 키워드가 있는 영상을 검색합니다.",
        "include_channel": "⚠️ 채널명에 키워드가 있으면 내용과 무관하게 검색됩니다. (기존 방식)",
        "all": "모든 필드에서 키워드를 검색합니다."
    }
    return descriptions.get(scope, "")
