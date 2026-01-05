"""
Video API 클라이언트 모듈
"""

from .base_client import BaseVideoAPIClient
from .fal_client import FalAIClient
from .replicate_client import ReplicateClient
from .pixverse_client import PixVerseClient

__all__ = [
    "BaseVideoAPIClient",
    "FalAIClient",
    "ReplicateClient",
    "PixVerseClient",
]

# 플랫폼 -> 클라이언트 매핑
CLIENT_MAP = {
    "fal_ai": FalAIClient,
    "replicate": ReplicateClient,
    "pixverse": PixVerseClient,
}


def get_client(platform: str) -> BaseVideoAPIClient:
    """플랫폼별 클라이언트 인스턴스 반환"""
    client_class = CLIENT_MAP.get(platform)
    if not client_class:
        raise ValueError(f"지원하지 않는 플랫폼: {platform}")
    return client_class()
