# -*- coding: utf-8 -*-
"""
API 에러 처리 유틸리티 v1.0

Anthropic API 및 기타 LLM API의 에러를 감지하고 처리

주요 기능:
- API 에러 타입 분류 (크레딧 부족, 속도 제한, 인증 실패 등)
- 사용자 친화적 에러 메시지 생성
- 폴백 가능 여부 판단
- 권장 조치 제안

작성: 2026-01
"""

from enum import Enum
from dataclasses import dataclass
from typing import Optional, Dict, Any, Tuple
import re


class APIErrorType(Enum):
    """API 에러 타입"""

    # Anthropic 특정 에러
    CREDIT_INSUFFICIENT = "credit_insufficient"      # 크레딧 부족
    RATE_LIMIT = "rate_limit"                        # 속도 제한
    AUTHENTICATION = "authentication"                # 인증 실패
    INVALID_API_KEY = "invalid_api_key"              # 잘못된 API 키
    MODEL_NOT_FOUND = "model_not_found"              # 모델 없음
    OVERLOADED = "overloaded"                        # 서버 과부하

    # 일반 에러
    TIMEOUT = "timeout"                              # 시간 초과
    NETWORK = "network"                              # 네트워크 오류
    SERVER_ERROR = "server_error"                    # 서버 오류 (5xx)
    INVALID_REQUEST = "invalid_request"              # 잘못된 요청
    CONTENT_FILTER = "content_filter"                # 콘텐츠 필터
    CONTEXT_LENGTH = "context_length"                # 컨텍스트 길이 초과

    # 알 수 없음
    UNKNOWN = "unknown"


@dataclass
class APIError:
    """API 에러 정보"""

    error_type: APIErrorType
    message: str
    original_error: Optional[str] = None
    status_code: Optional[int] = None
    request_id: Optional[str] = None
    provider: str = "unknown"

    # 복구 가능 여부
    recoverable: bool = False

    # 권장 조치
    recommended_action: str = ""

    # 대체 가능 여부
    fallback_available: bool = False

    # 대기 시간 (속도 제한 시)
    retry_after_seconds: Optional[int] = None


# ═══════════════════════════════════════════════════════════════════════════════
# 에러 파싱 함수
# ═══════════════════════════════════════════════════════════════════════════════

def parse_anthropic_error(error_message: str, status_code: int = None) -> APIError:
    """
    Anthropic API 에러 파싱

    Args:
        error_message: 에러 메시지 문자열
        status_code: HTTP 상태 코드

    Returns:
        APIError 객체
    """

    error_lower = error_message.lower()

    # ─────────────────────────────────────────────────────────────
    # 크레딧 부족 (가장 중요!)
    # ─────────────────────────────────────────────────────────────

    if 'credit balance is too low' in error_lower or 'insufficient_quota' in error_lower or 'billing' in error_lower:
        return APIError(
            error_type=APIErrorType.CREDIT_INSUFFICIENT,
            message="Anthropic API 크레딧이 부족합니다.",
            original_error=error_message,
            status_code=status_code or 400,
            provider="anthropic",
            recoverable=False,
            recommended_action="Anthropic 콘솔에서 크레딧을 충전하거나, Gemini 모델로 전환하세요.",
            fallback_available=True
        )

    # ─────────────────────────────────────────────────────────────
    # 속도 제한
    # ─────────────────────────────────────────────────────────────

    if 'rate_limit' in error_lower or 'too many requests' in error_lower or 'rate limit' in error_lower:
        # retry-after 추출 시도
        retry_match = re.search(r'retry.?after[:\s]*(\d+)', error_lower)
        retry_after = int(retry_match.group(1)) if retry_match else 30

        return APIError(
            error_type=APIErrorType.RATE_LIMIT,
            message="API 요청 속도 제한에 도달했습니다.",
            original_error=error_message,
            status_code=status_code or 429,
            provider="anthropic",
            recoverable=True,
            recommended_action=f"{retry_after}초 후 다시 시도하거나, 요청 간격을 늘리세요.",
            fallback_available=True,
            retry_after_seconds=retry_after
        )

    # ─────────────────────────────────────────────────────────────
    # 서버 과부하
    # ─────────────────────────────────────────────────────────────

    if 'overloaded' in error_lower or 'capacity' in error_lower:
        return APIError(
            error_type=APIErrorType.OVERLOADED,
            message="Anthropic API 서버가 과부하 상태입니다.",
            original_error=error_message,
            status_code=status_code or 529,
            provider="anthropic",
            recoverable=True,
            recommended_action="잠시 후 다시 시도하세요. 문제가 지속되면 Gemini로 전환하세요.",
            fallback_available=True,
            retry_after_seconds=60
        )

    # ─────────────────────────────────────────────────────────────
    # 인증 오류
    # ─────────────────────────────────────────────────────────────

    if 'authentication' in error_lower or 'invalid api key' in error_lower or 'unauthorized' in error_lower or 'invalid_api_key' in error_lower:
        return APIError(
            error_type=APIErrorType.AUTHENTICATION,
            message="API 키 인증에 실패했습니다.",
            original_error=error_message,
            status_code=status_code or 401,
            provider="anthropic",
            recoverable=False,
            recommended_action="API 키를 확인하고 다시 설정하세요. (.env 파일의 ANTHROPIC_API_KEY)",
            fallback_available=True
        )

    # ─────────────────────────────────────────────────────────────
    # 컨텍스트 길이 초과
    # ─────────────────────────────────────────────────────────────

    if 'context_length' in error_lower or 'too many tokens' in error_lower or 'maximum context' in error_lower or 'token limit' in error_lower:
        return APIError(
            error_type=APIErrorType.CONTEXT_LENGTH,
            message="입력이 너무 깁니다 (컨텍스트 길이 초과).",
            original_error=error_message,
            status_code=status_code or 400,
            provider="anthropic",
            recoverable=True,
            recommended_action="스크립트를 더 작은 단위로 나누거나, 프롬프트를 짧게 수정하세요.",
            fallback_available=False  # 다른 모델도 같은 문제 발생 가능
        )

    # ─────────────────────────────────────────────────────────────
    # 콘텐츠 필터
    # ─────────────────────────────────────────────────────────────

    if 'content' in error_lower and ('safety' in error_lower or 'filter' in error_lower or 'policy' in error_lower):
        return APIError(
            error_type=APIErrorType.CONTENT_FILTER,
            message="콘텐츠 안전 필터에 의해 차단되었습니다.",
            original_error=error_message,
            status_code=status_code or 400,
            provider="anthropic",
            recoverable=False,
            recommended_action="스크립트 내용을 검토하고 문제가 되는 부분을 수정하세요.",
            fallback_available=True
        )

    # ─────────────────────────────────────────────────────────────
    # 서버 오류 (5xx)
    # ─────────────────────────────────────────────────────────────

    if status_code and status_code >= 500:
        return APIError(
            error_type=APIErrorType.SERVER_ERROR,
            message="API 서버 오류가 발생했습니다.",
            original_error=error_message,
            status_code=status_code,
            provider="anthropic",
            recoverable=True,
            recommended_action="잠시 후 다시 시도하세요. 문제가 지속되면 Anthropic 상태 페이지를 확인하세요.",
            fallback_available=True,
            retry_after_seconds=30
        )

    # ─────────────────────────────────────────────────────────────
    # 네트워크/타임아웃 오류
    # ─────────────────────────────────────────────────────────────

    if 'timeout' in error_lower or 'timed out' in error_lower:
        return APIError(
            error_type=APIErrorType.TIMEOUT,
            message="API 요청 시간이 초과되었습니다.",
            original_error=error_message,
            status_code=status_code,
            provider="anthropic",
            recoverable=True,
            recommended_action="네트워크 연결을 확인하고 다시 시도하세요.",
            fallback_available=True,
            retry_after_seconds=10
        )

    if 'connection' in error_lower or 'network' in error_lower:
        return APIError(
            error_type=APIErrorType.NETWORK,
            message="네트워크 연결 오류가 발생했습니다.",
            original_error=error_message,
            status_code=status_code,
            provider="anthropic",
            recoverable=True,
            recommended_action="인터넷 연결을 확인하고 다시 시도하세요.",
            fallback_available=True
        )

    # ─────────────────────────────────────────────────────────────
    # 기본: 알 수 없는 에러
    # ─────────────────────────────────────────────────────────────

    return APIError(
        error_type=APIErrorType.UNKNOWN,
        message=f"API 오류가 발생했습니다.",
        original_error=error_message,
        status_code=status_code,
        provider="anthropic",
        recoverable=False,
        recommended_action="에러 메시지를 확인하고 문제를 해결하세요.",
        fallback_available=True
    )


def parse_google_error(error_message: str, status_code: int = None) -> APIError:
    """
    Google/Gemini API 에러 파싱

    Args:
        error_message: 에러 메시지 문자열
        status_code: HTTP 상태 코드

    Returns:
        APIError 객체
    """

    error_lower = error_message.lower()

    # 할당량 초과
    if 'quota' in error_lower or 'resource exhausted' in error_lower:
        return APIError(
            error_type=APIErrorType.RATE_LIMIT,
            message="Google API 할당량이 초과되었습니다.",
            original_error=error_message,
            status_code=status_code or 429,
            provider="google",
            recoverable=True,
            recommended_action="잠시 후 다시 시도하거나, Claude 모델로 전환하세요.",
            fallback_available=True,
            retry_after_seconds=60
        )

    # API 키 오류
    if 'api key' in error_lower or 'invalid' in error_lower and 'key' in error_lower:
        return APIError(
            error_type=APIErrorType.AUTHENTICATION,
            message="Google API 키가 유효하지 않습니다.",
            original_error=error_message,
            status_code=status_code or 401,
            provider="google",
            recoverable=False,
            recommended_action="API 키를 확인하세요. (.env 파일의 GOOGLE_API_KEY 또는 GEMINI_API_KEY)",
            fallback_available=True
        )

    # 안전 필터
    if 'safety' in error_lower or 'blocked' in error_lower:
        return APIError(
            error_type=APIErrorType.CONTENT_FILTER,
            message="Gemini 안전 필터에 의해 차단되었습니다.",
            original_error=error_message,
            status_code=status_code,
            provider="google",
            recoverable=False,
            recommended_action="스크립트 내용을 검토하세요. Claude로 전환을 시도해볼 수 있습니다.",
            fallback_available=True
        )

    # 기본
    return APIError(
        error_type=APIErrorType.UNKNOWN,
        message="Google API 오류가 발생했습니다.",
        original_error=error_message,
        status_code=status_code,
        provider="google",
        recoverable=False,
        recommended_action="에러 메시지를 확인하세요.",
        fallback_available=True
    )


def extract_error_from_exception(exception: Exception, provider: str = None) -> APIError:
    """
    Exception 객체에서 에러 정보 추출

    Args:
        exception: 발생한 예외
        provider: API 제공자 ("anthropic", "google" 등)

    Returns:
        APIError 객체
    """

    error_str = str(exception)
    exception_type = type(exception).__name__

    # 상태 코드 추출 시도
    status_code = None
    status_match = re.search(r'Error code: (\d+)', error_str)
    if status_match:
        status_code = int(status_match.group(1))

    # status_code 속성 확인
    if hasattr(exception, 'status_code'):
        status_code = exception.status_code

    # request_id 추출 시도
    request_id = None
    request_match = re.search(r"'request_id':\s*'([^']+)'", error_str)
    if request_match:
        request_id = request_match.group(1)

    # provider 자동 감지
    if provider is None:
        if 'anthropic' in error_str.lower() or 'claude' in exception_type.lower():
            provider = "anthropic"
        elif 'google' in error_str.lower() or 'gemini' in error_str.lower():
            provider = "google"
        else:
            provider = "anthropic"  # 기본값

    # provider별 파싱
    if provider == "google":
        api_error = parse_google_error(error_str, status_code)
    else:
        api_error = parse_anthropic_error(error_str, status_code)

    api_error.request_id = request_id

    return api_error


# ═══════════════════════════════════════════════════════════════════════════════
# 사용자 메시지 생성
# ═══════════════════════════════════════════════════════════════════════════════

def get_error_display_message(api_error: APIError, include_action: bool = True, include_fallback: bool = True) -> str:
    """
    사용자에게 표시할 에러 메시지 생성

    Args:
        api_error: APIError 객체
        include_action: 권장 조치 포함 여부
        include_fallback: 폴백 안내 포함 여부

    Returns:
        표시용 메시지 문자열
    """

    # 에러 타입별 아이콘
    icons = {
        APIErrorType.CREDIT_INSUFFICIENT: "💳",
        APIErrorType.RATE_LIMIT: "⏱️",
        APIErrorType.AUTHENTICATION: "🔑",
        APIErrorType.CONTEXT_LENGTH: "📏",
        APIErrorType.SERVER_ERROR: "🖥️",
        APIErrorType.NETWORK: "🌐",
        APIErrorType.TIMEOUT: "⏰",
        APIErrorType.CONTENT_FILTER: "🚫",
        APIErrorType.OVERLOADED: "📈",
        APIErrorType.UNKNOWN: "❓"
    }

    icon = icons.get(api_error.error_type, "❌")

    message = f"{icon} **{api_error.message}**"

    if include_action and api_error.recommended_action:
        message += f"\n\n💡 **권장 조치**: {api_error.recommended_action}"

    if include_fallback and api_error.fallback_available:
        fallback_provider = "Gemini" if api_error.provider == "anthropic" else "Claude"
        message += f"\n\n🔄 **{fallback_provider}** 모델로 전환하여 시도할 수 있습니다."

    return message


def get_error_short_message(api_error: APIError) -> str:
    """
    짧은 에러 메시지 (로그/콘솔용)

    Args:
        api_error: APIError 객체

    Returns:
        짧은 메시지 문자열
    """

    type_names = {
        APIErrorType.CREDIT_INSUFFICIENT: "크레딧 부족",
        APIErrorType.RATE_LIMIT: "속도 제한",
        APIErrorType.AUTHENTICATION: "인증 실패",
        APIErrorType.CONTEXT_LENGTH: "입력 초과",
        APIErrorType.SERVER_ERROR: "서버 오류",
        APIErrorType.NETWORK: "네트워크 오류",
        APIErrorType.TIMEOUT: "시간 초과",
        APIErrorType.CONTENT_FILTER: "콘텐츠 차단",
        APIErrorType.OVERLOADED: "서버 과부하",
        APIErrorType.UNKNOWN: "알 수 없는 오류"
    }

    type_name = type_names.get(api_error.error_type, "오류")
    return f"[{api_error.provider.upper()}] {type_name}"


# ═══════════════════════════════════════════════════════════════════════════════
# 에러 타입 체크 헬퍼
# ═══════════════════════════════════════════════════════════════════════════════

def is_credit_error(api_error: APIError) -> bool:
    """크레딧 부족 에러인지 확인"""
    return api_error.error_type == APIErrorType.CREDIT_INSUFFICIENT


def is_recoverable_error(api_error: APIError) -> bool:
    """복구 가능한 에러인지 확인 (재시도 가능)"""
    return api_error.recoverable


def is_fallback_recommended(api_error: APIError) -> bool:
    """폴백 권장 에러인지 확인"""
    return api_error.fallback_available and not api_error.recoverable


def should_retry_with_delay(api_error: APIError) -> Tuple[bool, int]:
    """
    재시도 권장 여부 및 대기 시간 반환

    Returns:
        (재시도 권장 여부, 대기 시간 초)
    """
    if api_error.error_type in [APIErrorType.RATE_LIMIT, APIErrorType.OVERLOADED, APIErrorType.SERVER_ERROR]:
        delay = api_error.retry_after_seconds or 30
        return True, delay

    if api_error.error_type == APIErrorType.TIMEOUT:
        return True, 10

    return False, 0


# ═══════════════════════════════════════════════════════════════════════════════
# API 상태 확인
# ═══════════════════════════════════════════════════════════════════════════════

def check_anthropic_api_status(api_key: str = None) -> Tuple[bool, Optional[APIError]]:
    """
    Anthropic API 상태 확인 (간단한 요청으로 테스트)

    Args:
        api_key: API 키 (없으면 환경변수 사용)

    Returns:
        (정상 여부, 에러 정보 또는 None)
    """
    try:
        from anthropic import Anthropic
        import os

        key = api_key or os.getenv("ANTHROPIC_API_KEY", "")
        if not key:
            return False, APIError(
                error_type=APIErrorType.AUTHENTICATION,
                message="Anthropic API 키가 설정되지 않았습니다.",
                provider="anthropic",
                recommended_action=".env 파일에 ANTHROPIC_API_KEY를 설정하세요.",
                fallback_available=True
            )

        client = Anthropic(api_key=key)

        # 최소 요청으로 테스트 (가장 저렴한 모델 사용)
        response = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=10,
            messages=[{"role": "user", "content": "Hi"}]
        )

        return True, None

    except Exception as e:
        api_error = extract_error_from_exception(e, provider="anthropic")
        return False, api_error


def check_google_api_status(api_key: str = None) -> Tuple[bool, Optional[APIError]]:
    """
    Google/Gemini API 상태 확인

    Args:
        api_key: API 키 (없으면 환경변수 사용)

    Returns:
        (정상 여부, 에러 정보 또는 None)
    """
    try:
        import google.generativeai as genai
        import os

        key = api_key or os.getenv("GOOGLE_API_KEY", "") or os.getenv("GEMINI_API_KEY", "")
        if not key:
            return False, APIError(
                error_type=APIErrorType.AUTHENTICATION,
                message="Google API 키가 설정되지 않았습니다.",
                provider="google",
                recommended_action=".env 파일에 GOOGLE_API_KEY 또는 GEMINI_API_KEY를 설정하세요.",
                fallback_available=True
            )

        genai.configure(api_key=key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content("Hi", generation_config={"max_output_tokens": 10})

        return True, None

    except Exception as e:
        api_error = extract_error_from_exception(e, provider="google")
        return False, api_error


# ═══════════════════════════════════════════════════════════════════════════════
# 내보내기
# ═══════════════════════════════════════════════════════════════════════════════

__all__ = [
    'APIErrorType',
    'APIError',
    'parse_anthropic_error',
    'parse_google_error',
    'extract_error_from_exception',
    'get_error_display_message',
    'get_error_short_message',
    'is_credit_error',
    'is_recoverable_error',
    'is_fallback_recommended',
    'should_retry_with_delay',
    'check_anthropic_api_status',
    'check_google_api_status'
]
