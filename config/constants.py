"""
AI Longform YouTube Tool - Constants

상수 정의
"""

# === 프로젝트 상태 ===
PROJECT_STATUS = {
    "in_progress": "진행 중",
    "completed": "완료",
    "archived": "보관됨"
}

# === 워크플로우 단계 ===
WORKFLOW_STEPS = [
    {"id": 1, "name": "키워드 리서치", "icon": "📊"},
    {"id": 2, "name": "영상 리서치", "icon": "🔍"},
    {"id": 3, "name": "스크립트 생성", "icon": "📝"},
    {"id": 4, "name": "TTS 생성", "icon": "🎤"},
    {"id": 5, "name": "이미지 프롬프트", "icon": "🖼️"},
    {"id": 6, "name": "이미지 생성", "icon": "🎨"},
    {"id": 7, "name": "Vrew Export", "icon": "📦"},
]

# === 스크립트 섹션 마커 ===
SCRIPT_SECTION_MARKERS = [
    "[HOOK]",
    "[INTRO]",
    "[MAIN]",
    "[CTA]",
    "[OUTRO]",
]

# === 스크립트 톤 옵션 ===
SCRIPT_TONES = {
    "informative": "정보 전달형",
    "storytelling": "스토리텔링형",
    "tutorial": "튜토리얼형",
    "review": "리뷰형",
    "motivational": "동기부여형",
}

# === YouTube 검색 필터 ===
YOUTUBE_DURATION_OPTIONS = {
    "any": "전체",
    "short": "짧은 영상 (4분 미만)",
    "medium": "중간 영상 (4-20분)",
    "long": "긴 영상 (20분 이상)",
}

YOUTUBE_ORDER_OPTIONS = {
    "viewCount": "조회수 순",
    "date": "최신 순",
    "rating": "평점 순",
    "relevance": "관련성 순",
}

YOUTUBE_REGION_OPTIONS = {
    "KR": "한국",
    "JP": "일본",
    "US": "미국",
}

YOUTUBE_PERIOD_OPTIONS = {
    7: "최근 1주일",
    30: "최근 1개월",
    90: "최근 3개월",
    180: "최근 6개월",
    365: "최근 1년",
}

# === 이미지 스타일 프리픽스 ===
IMAGE_STYLE_PREFIXES = {
    "animation": "animation style, vibrant colors, clean lines, no text, no letters, no words",
    "realistic": "photorealistic, high quality, detailed, no text, no letters, no words",
    "minimal": "minimalist style, simple shapes, clean design, no text, no letters, no words",
    "illustration": "digital illustration, colorful, modern style, no text, no letters, no words",
}

# === 썸네일 설정 ===
THUMBNAIL_VERSIONS = ["A", "B", "C"]
THUMBNAIL_WIDTH = 1280
THUMBNAIL_HEIGHT = 720

# === 파일명 패턴 ===
SEGMENT_IMAGE_PATTERN = "{group_id:03d}_seg_{start:03d}-{end:03d}.png"

# === 캐시 유효 기간 (시간) ===
CACHE_DURATION_HOURS = {
    "search": 24,
    "videos": 24,
    "channels": 168,  # 7일
    "comments": 6,
}
