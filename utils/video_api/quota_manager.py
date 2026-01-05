"""
Video API 사용량 관리자
- 플랫폼별 잔액 관리
- 사용 내역 기록
- 일일/월간 통계
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List
import logging

from .config import (
    STATE_FILE, DATA_DIR,
    PLATFORM_CONFIGS, ALL_MODELS,
    get_api_key
)
from .models import (
    PlatformBalance, UsageStatistics, UsageRecord,
    APIQuotaStatus, APIState
)

logger = logging.getLogger(__name__)


class QuotaManager:
    """사용량 및 잔액 관리자"""

    _instance: Optional["QuotaManager"] = None

    def __new__(cls) -> "QuotaManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._initialized = True
        self._state: Optional[APIState] = None
        self._load_state()

    def _load_state(self):
        """상태 파일 로드"""
        try:
            if STATE_FILE.exists():
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._state = APIState.from_dict(data)
            else:
                self._state = APIState(last_updated=datetime.now().isoformat())
                self._initialize_defaults()
                self._save_state()
        except Exception as e:
            logger.error(f"상태 파일 로드 실패: {e}")
            self._state = APIState(last_updated=datetime.now().isoformat())
            self._initialize_defaults()

    def _initialize_defaults(self):
        """기본 잔액 초기화"""
        for platform, config in PLATFORM_CONFIGS.items():
            if platform not in self._state.platform_balances:
                balance_data = {
                    "platform": platform,
                    "display_name": config["display_name"],
                    "balance_usd": config.get("initial_credits_usd", 0),
                    "credits_remaining": config.get("initial_credits"),
                    "credits_daily_limit": config.get("daily_credits"),
                    "total_spent_usd": 0.0,
                    "total_videos_generated": 0,
                    "is_available": True,
                    "last_updated": datetime.now().isoformat()
                }
                self._state.platform_balances[platform] = balance_data

        # 레거시 quotas 초기화
        for platform, models in ALL_MODELS.items():
            for model_key, model in models.items():
                api_name = f"{platform}_{model_key}"
                if api_name not in self._state.quotas:
                    self._state.quotas[api_name] = {
                        "api_name": api_name,
                        "display_name": model.display_name,
                        "total_credits": 1000,
                        "used_credits": 0,
                        "remaining_credits": 1000,
                        "is_available": True,
                        "error_count": 0
                    }

    def _save_state(self):
        """상태 파일 저장"""
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            self._state.last_updated = datetime.now().isoformat()
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(self._state.to_dict(), f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"상태 파일 저장 실패: {e}")

    # ========================================
    # 플랫폼 잔액 관리
    # ========================================

    def get_platform_balance(self, platform: str) -> PlatformBalance:
        """플랫폼 잔액 조회"""
        balance_data = self._state.platform_balances.get(platform, {})

        if not balance_data:
            config = PLATFORM_CONFIGS.get(platform, {})
            return PlatformBalance(
                platform=platform,
                display_name=config.get("display_name", platform),
                is_available=False
            )

        return PlatformBalance(
            platform=platform,
            display_name=balance_data.get("display_name", platform),
            balance_usd=balance_data.get("balance_usd"),
            credits_remaining=balance_data.get("credits_remaining"),
            credits_daily_limit=balance_data.get("credits_daily_limit"),
            credits_used_today=balance_data.get("credits_used_today", 0),
            total_spent_usd=balance_data.get("total_spent_usd", 0),
            total_videos_generated=balance_data.get("total_videos_generated", 0),
            is_available=balance_data.get("is_available", True),
            last_updated=balance_data.get("last_updated", "")
        )

    def set_manual_balance(self, platform: str, balance_usd: float):
        """수동 잔액 설정 (USD 기반 플랫폼)"""
        if platform in self._state.platform_balances:
            self._state.platform_balances[platform]["balance_usd"] = balance_usd
            self._state.platform_balances[platform]["last_updated"] = datetime.now().isoformat()
            self._save_state()

    def set_manual_credits(self, platform: str, credits: int):
        """수동 크레딧 설정 (크레딧 기반 플랫폼)"""
        if platform in self._state.platform_balances:
            self._state.platform_balances[platform]["credits_remaining"] = credits
            self._state.platform_balances[platform]["last_updated"] = datetime.now().isoformat()
            self._save_state()

    # ========================================
    # 사용량 기록
    # ========================================

    def record_usage(
        self,
        platform: str,
        model_key: str,
        cost_usd: float = 0.0,
        credits: int = 0,
        success: bool = True,
        prompt: str = "",
        duration: int = 5,
        resolution: str = "720p",
        video_url: Optional[str] = None,
        error_message: Optional[str] = None
    ):
        """사용 기록 저장"""
        # 모델 정보 가져오기
        model = ALL_MODELS.get(platform, {}).get(model_key)
        model_display_name = model.display_name if model else model_key

        # 사용 기록 생성
        record = UsageRecord(
            timestamp=datetime.now().isoformat(),
            platform=platform,
            model_key=model_key,
            model_display_name=model_display_name,
            prompt=prompt[:100] if prompt else "",
            duration=duration,
            resolution=resolution,
            cost_usd=cost_usd,
            credits_used=credits,
            success=success,
            error_message=error_message,
            video_url=video_url
        )

        # 히스토리에 추가
        self._state.usage_history.append(record.to_dict())

        # 최근 500개만 유지
        if len(self._state.usage_history) > 500:
            self._state.usage_history = self._state.usage_history[-500:]

        # 통계 업데이트
        if success:
            self._state.total_videos_generated += 1

            # 플랫폼 잔액 업데이트
            if platform in self._state.platform_balances:
                balance = self._state.platform_balances[platform]
                balance["total_spent_usd"] = balance.get("total_spent_usd", 0) + cost_usd
                balance["total_videos_generated"] = balance.get("total_videos_generated", 0) + 1

                if balance.get("balance_usd") is not None:
                    balance["balance_usd"] = max(0, balance["balance_usd"] - cost_usd)

                if balance.get("credits_remaining") is not None and credits > 0:
                    balance["credits_remaining"] = max(0, balance["credits_remaining"] - credits)
                    balance["credits_used_today"] = balance.get("credits_used_today", 0) + credits

            # 일일/월간 통계 업데이트
            today = datetime.now().strftime("%Y-%m-%d")
            month = datetime.now().strftime("%Y-%m")

            if today not in self._state.daily_stats:
                self._state.daily_stats[today] = {"videos": 0, "cost_usd": 0.0}
            self._state.daily_stats[today]["videos"] += 1
            self._state.daily_stats[today]["cost_usd"] += cost_usd

            if month not in self._state.monthly_stats:
                self._state.monthly_stats[month] = {"videos": 0, "cost_usd": 0.0}
            self._state.monthly_stats[month]["videos"] += 1
            self._state.monthly_stats[month]["cost_usd"] += cost_usd

        self._save_state()

    # ========================================
    # 통계 조회
    # ========================================

    def get_usage_statistics(self) -> UsageStatistics:
        """사용량 통계 조회"""
        today = datetime.now().strftime("%Y-%m-%d")
        month = datetime.now().strftime("%Y-%m")

        today_stats = self._state.daily_stats.get(today, {"videos": 0, "cost_usd": 0.0})
        month_stats = self._state.monthly_stats.get(month, {"videos": 0, "cost_usd": 0.0})

        # 전체 통계 계산
        total_videos = sum(s.get("videos", 0) for s in self._state.daily_stats.values())
        total_cost = sum(s.get("cost_usd", 0) for s in self._state.daily_stats.values())

        return UsageStatistics(
            today_videos=today_stats.get("videos", 0),
            today_cost_usd=today_stats.get("cost_usd", 0.0),
            month_videos=month_stats.get("videos", 0),
            month_cost_usd=month_stats.get("cost_usd", 0.0),
            total_videos=total_videos,
            total_cost_usd=total_cost
        )

    def get_usage_history(self, period: str = "today") -> List[Dict[str, Any]]:
        """사용 내역 조회"""
        now = datetime.now()

        if period == "today":
            cutoff = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == "this_week" or period == "이번 주":
            cutoff = now - timedelta(days=7)
        elif period == "this_month" or period == "이번 달":
            cutoff = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            return self._state.usage_history

        result = []
        for record in self._state.usage_history:
            try:
                timestamp = datetime.fromisoformat(record.get("timestamp", ""))
                if timestamp >= cutoff:
                    result.append(record)
            except:
                continue

        return result

    def reset_usage_history(self):
        """사용 내역 초기화"""
        self._state.usage_history = []
        self._state.daily_stats = {}
        self._state.monthly_stats = {}
        self._state.total_videos_generated = 0
        self._save_state()

    # ========================================
    # 레거시 호환 메서드
    # ========================================

    def get_all_quotas(self) -> Dict[str, APIQuotaStatus]:
        """모든 API 할당량 조회 (레거시 호환)"""
        result = {}
        for api_name, quota_data in self._state.quotas.items():
            try:
                result[api_name] = APIQuotaStatus.from_dict(quota_data)
            except:
                continue
        return result

    def get_available_apis(
        self,
        min_credits: int = 1,
        commercial_use: bool = False,
        allow_watermark: bool = True
    ) -> List[str]:
        """사용 가능한 API 목록 (레거시 호환)"""
        available = []

        for platform, models in ALL_MODELS.items():
            # API 키 확인
            config = PLATFORM_CONFIGS.get(platform, {})
            if not get_api_key(config.get("env_key", "")):
                continue

            for model_key, model in models.items():
                api_name = f"{platform}_{model_key}"

                # 조건 필터링
                if not allow_watermark and model.watermark:
                    continue
                if commercial_use and not model.commercial_use:
                    continue

                available.append(api_name)

        return available

    def use_credits(self, api_name: str, credits: int):
        """크레딧 사용 (레거시 호환)"""
        if api_name in self._state.quotas:
            quota = self._state.quotas[api_name]
            quota["used_credits"] = quota.get("used_credits", 0) + credits
            quota["remaining_credits"] = max(0, quota.get("remaining_credits", 0) - credits)
            self._save_state()

    def record_error(self, api_name: str, error: str):
        """에러 기록 (레거시 호환)"""
        if api_name in self._state.quotas:
            quota = self._state.quotas[api_name]
            quota["error_count"] = quota.get("error_count", 0) + 1
            quota["last_error"] = error
            self._save_state()

    def reset_error_count(self, api_name: str):
        """에러 카운트 리셋 (레거시 호환)"""
        if api_name in self._state.quotas:
            self._state.quotas[api_name]["error_count"] = 0
            self._save_state()

    def add_generation_history(self, **kwargs):
        """생성 이력 추가 (레거시 호환)"""
        self._state.generation_history.append({
            **kwargs,
            "timestamp": datetime.now().isoformat()
        })
        if len(self._state.generation_history) > 100:
            self._state.generation_history = self._state.generation_history[-100:]
        self._save_state()

    def get_statistics(self) -> Dict[str, Any]:
        """통계 조회 (레거시 호환)"""
        stats = self.get_usage_statistics()
        return {
            "total_remaining_credits": sum(
                q.get("remaining_credits", 0)
                for q in self._state.quotas.values()
            ),
            "available_apis": len(self.get_available_apis()),
            "total_videos": stats.total_videos,
            "total_credits_used": sum(
                q.get("used_credits", 0)
                for q in self._state.quotas.values()
            ),
            "last_updated": self._state.last_updated
        }
