"""
커스텀 예외 클래스
"""


class VideoAPIError(Exception):
    """Video API 기본 예외"""
    pass


class QuotaExceededError(VideoAPIError):
    """크레딧 소진 예외"""
    def __init__(self, api_name: str, remaining: int = 0):
        self.api_name = api_name
        self.remaining = remaining
        super().__init__(f"{api_name} 크레딧 소진 (남은 크레딧: {remaining})")


class APINotAvailableError(VideoAPIError):
    """API 사용 불가 예외"""
    def __init__(self, api_name: str, reason: str = ""):
        self.api_name = api_name
        self.reason = reason
        super().__init__(f"{api_name} 사용 불가: {reason}")


class NoAvailableAPIError(VideoAPIError):
    """모든 API 사용 불가 예외"""
    def __init__(self, message: str = "사용 가능한 API가 없습니다"):
        super().__init__(message)


class APIKeyMissingError(VideoAPIError):
    """API 키 누락 예외"""
    def __init__(self, api_name: str, env_key: str):
        self.api_name = api_name
        self.env_key = env_key
        super().__init__(f"{api_name} API 키가 설정되지 않음: {env_key}")


class VideoGenerationError(VideoAPIError):
    """영상 생성 실패 예외"""
    def __init__(self, api_name: str, message: str):
        self.api_name = api_name
        super().__init__(f"{api_name} 영상 생성 실패: {message}")


class RateLimitError(VideoAPIError):
    """Rate Limit 초과 예외"""
    def __init__(self, api_name: str, retry_after: int = 0):
        self.api_name = api_name
        self.retry_after = retry_after
        super().__init__(f"{api_name} Rate Limit 초과 (재시도: {retry_after}초 후)")


class TimeoutError(VideoAPIError):
    """타임아웃 예외"""
    def __init__(self, api_name: str, timeout: int):
        self.api_name = api_name
        self.timeout = timeout
        super().__init__(f"{api_name} 요청 타임아웃 ({timeout}초)")
