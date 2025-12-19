"""
YouTube API 캐싱 시스템

⚠️ Critical: API 할당량(10,000포인트/일) 절약을 위해 반드시 캐싱 사용

캐싱 정책:
- search().list: 100포인트, 24시간 캐시
- videos().list: 1포인트, 24시간 캐시
- channels().list: 1포인트, 7일 캐시
- commentThreads().list: 1포인트, 6시간 캐시

사용법:
    from core.youtube.cache import get_cache

    cache = get_cache()

    # 캐시 확인
    cached = cache.get("search", {"keyword": "...", "region": "KR"})
    if cached:
        return cached

    # API 호출 후 캐시 저장
    result = youtube.search().list(...).execute()
    cache.set("search", {"keyword": "...", "region": "KR"}, result)
    cache.log_api_call("search")  # 할당량 추적
"""
import sqlite3
import json
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Any, Dict

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config.settings import CACHE_DIR, YOUTUBE_DAILY_QUOTA
from config.constants import CACHE_DURATION_HOURS


class YouTubeCache:
    """
    YouTube API 응답을 로컬에 캐싱하여 할당량 절약

    ⚠️ 중요: 동일한 요청은 캐시에서 먼저 조회하고,
    캐시가 유효하면 API를 호출하지 않습니다.
    """

    # 캐시 유효 기간
    CACHE_DURATIONS = {
        "search": timedelta(hours=CACHE_DURATION_HOURS.get("search", 24)),
        "videos": timedelta(hours=CACHE_DURATION_HOURS.get("videos", 24)),
        "channels": timedelta(hours=CACHE_DURATION_HOURS.get("channels", 168)),
        "comments": timedelta(hours=CACHE_DURATION_HOURS.get("comments", 6)),
    }

    # API 호출 비용 (포인트)
    API_COSTS = {
        "search": 100,
        "videos": 1,
        "channels": 1,
        "comments": 1,
    }

    def __init__(self, cache_dir: Path = None):
        """
        Args:
            cache_dir: 캐시 디렉토리 경로 (기본: data/cache)
        """
        self.cache_dir = cache_dir or CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.cache_dir / "youtube_cache.db"
        self._init_db()

    def _init_db(self):
        """캐시 DB 초기화"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 캐시 테이블
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cache (
                cache_key TEXT PRIMARY KEY,
                cache_type TEXT NOT NULL,
                data TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL
            )
        """)

        # 할당량 로그 테이블
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS quota_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                api_type TEXT NOT NULL,
                cost INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 만료된 캐시 자동 정리
        cursor.execute("""
            DELETE FROM cache WHERE expires_at < datetime('now')
        """)

        conn.commit()
        conn.close()

    def _generate_cache_key(self, cache_type: str, params: Dict) -> str:
        """캐시 키 생성"""
        params_str = json.dumps(params, sort_keys=True)
        hash_str = hashlib.md5(params_str.encode()).hexdigest()[:16]
        return f"{cache_type}_{hash_str}"

    def get(self, cache_type: str, params: Dict) -> Optional[Any]:
        """
        캐시에서 데이터 조회

        Args:
            cache_type: 캐시 타입 ("search", "videos", "channels", "comments")
            params: 캐시 키 생성용 파라미터

        Returns:
            캐시 데이터 또는 None (캐시 미스 또는 만료)
        """
        cache_key = self._generate_cache_key(cache_type, params)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT data FROM cache
            WHERE cache_key = ? AND cache_type = ? AND expires_at > datetime('now')
        """, (cache_key, cache_type))

        row = cursor.fetchone()
        conn.close()

        if row:
            return json.loads(row[0])
        return None

    def set(self, cache_type: str, params: Dict, data: Any):
        """
        캐시에 데이터 저장

        Args:
            cache_type: 캐시 타입
            params: 캐시 키 생성용 파라미터
            data: 저장할 데이터
        """
        cache_key = self._generate_cache_key(cache_type, params)
        duration = self.CACHE_DURATIONS.get(cache_type, timedelta(hours=24))
        expires_at = datetime.now() + duration

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT OR REPLACE INTO cache (cache_key, cache_type, data, expires_at)
            VALUES (?, ?, ?, ?)
        """, (cache_key, cache_type, json.dumps(data, ensure_ascii=False), expires_at))

        conn.commit()
        conn.close()

    def log_api_call(self, cache_type: str):
        """
        API 호출 기록 (할당량 추적)

        Args:
            cache_type: API 타입
        """
        cost = self.API_COSTS.get(cache_type, 1)
        today = datetime.now().strftime("%Y-%m-%d")

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO quota_log (date, api_type, cost)
            VALUES (?, ?, ?)
        """, (today, cache_type, cost))

        conn.commit()
        conn.close()

    def get_quota_used_today(self) -> int:
        """
        오늘 사용한 할당량 조회

        Returns:
            사용된 포인트 합계
        """
        today = datetime.now().strftime("%Y-%m-%d")

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT COALESCE(SUM(cost), 0) FROM quota_log WHERE date = ?
        """, (today,))

        result = cursor.fetchone()
        conn.close()

        return result[0] if result else 0

    def get_quota_remaining(self) -> int:
        """
        남은 할당량 조회

        Returns:
            남은 포인트
        """
        used = self.get_quota_used_today()
        return max(0, YOUTUBE_DAILY_QUOTA - used)

    def get_quota_stats(self) -> Dict:
        """
        할당량 통계 조회

        Returns:
            {
                "daily_limit": 10000,
                "used_today": 500,
                "remaining": 9500,
                "usage_percent": 5.0
            }
        """
        used = self.get_quota_used_today()
        return {
            "daily_limit": YOUTUBE_DAILY_QUOTA,
            "used_today": used,
            "remaining": max(0, YOUTUBE_DAILY_QUOTA - used),
            "usage_percent": round((used / YOUTUBE_DAILY_QUOTA) * 100, 1)
        }

    def get_cache_stats(self) -> Dict:
        """
        캐시 통계 조회

        Returns:
            {
                "search": 10,
                "videos": 50,
                "channels": 5,
                "comments": 20
            }
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT cache_type, COUNT(*) as count
            FROM cache
            WHERE expires_at > datetime('now')
            GROUP BY cache_type
        """)

        stats = {row[0]: row[1] for row in cursor.fetchall()}
        conn.close()

        return stats

    def get_api_call_history(self, days: int = 7) -> list:
        """
        API 호출 히스토리 조회

        Args:
            days: 조회 기간 (일)

        Returns:
            일별 호출 통계 리스트
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT date, api_type, SUM(cost) as total_cost
            FROM quota_log
            WHERE date >= date('now', ?)
            GROUP BY date, api_type
            ORDER BY date DESC
        """, (f"-{days} days",))

        results = cursor.fetchall()
        conn.close()

        history = []
        for row in results:
            history.append({
                "date": row[0],
                "api_type": row[1],
                "cost": row[2]
            })

        return history

    def clear_expired(self):
        """만료된 캐시 삭제"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("DELETE FROM cache WHERE expires_at < datetime('now')")
        deleted = cursor.rowcount

        conn.commit()
        conn.close()

        return deleted

    def clear_all(self):
        """모든 캐시 삭제"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("DELETE FROM cache")

        conn.commit()
        conn.close()

    def clear_quota_log(self):
        """할당량 로그 초기화 (주의: 테스트용)"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("DELETE FROM quota_log")

        conn.commit()
        conn.close()


# === 싱글톤 인스턴스 ===
_cache_instance: Optional[YouTubeCache] = None


def get_cache() -> YouTubeCache:
    """
    캐시 싱글톤 인스턴스 반환

    Returns:
        YouTubeCache 인스턴스
    """
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = YouTubeCache()
    return _cache_instance


def reset_cache():
    """캐시 인스턴스 리셋 (테스트용)"""
    global _cache_instance
    _cache_instance = None
