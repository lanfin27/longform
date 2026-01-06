# -*- coding: utf-8 -*-
"""
프롬프트 정제기 (v1.0)

기능:
- 이미지 생성 시 텍스트 관련 키워드 제거
- 한글/중국어/일본어 텍스트 생성 방지
- 프롬프트 클린업 및 강화
"""

import re
from typing import List, Tuple

# ============================================================
# 텍스트 관련 키워드 (제거 대상)
# ============================================================

TEXT_KEYWORDS = [
    # 영어 텍스트 관련
    "text", "word", "words", "letter", "letters", "writing", "written",
    "sign", "signs", "signage", "billboard", "poster", "banner",
    "label", "labels", "title", "subtitle", "caption", "headline",
    "typography", "font", "fonts", "logo", "logos", "brand", "branding",
    "slogan", "message", "quote", "quotation",

    # 한글 관련
    "korean text", "korean writing", "korean letters", "korean words",
    "hangul", "한글", "한국어", "글씨", "문자", "글자",

    # 일본어 관련
    "japanese text", "japanese writing", "kanji", "hiragana", "katakana",
    "日本語", "漢字", "ひらがな", "カタカナ",

    # 중국어 관련
    "chinese text", "chinese writing", "chinese characters", "mandarin",
    "中文", "汉字", "漢字", "繁體", "简体",

    # 기타 아시아 언어
    "asian text", "cjk", "script",

    # 표지판/라벨 관련
    "store sign", "shop sign", "street sign", "road sign",
    "neon sign", "price tag", "name tag", "watermark",
    "stamp", "seal", "inscription",

    # 책/문서 관련
    "book title", "book cover", "newspaper", "magazine",
    "document", "note", "notes", "memo",
]

# 정규식 패턴 (대소문자 무시)
TEXT_PATTERNS = [
    r'\btext\b',
    r'\bword[s]?\b',
    r'\bletter[s]?\b',
    r'\bsign[s]?\b',
    r'\blogo[s]?\b',
    r'\blabel[s]?\b',
    r'\bwriting\b',
    r'\btitle[s]?\b',
    r'\bcaption[s]?\b',
    r'korean\s+\w+',  # korean text, korean writing 등
    r'japanese\s+\w+',
    r'chinese\s+\w+',
    r'asian\s+\w+',
    r'\bhangul\b',
    r'\bkanji\b',
    r'\bhiragana\b',
    r'\bkatakana\b',
]


# ============================================================
# 강력한 텍스트 차단 프롬프트
# ============================================================

# 포지티브 프롬프트에 추가할 텍스트 차단 지시
TEXT_BLOCKING_POSITIVE = (
    "IMPORTANT: All surfaces must be completely blank with no text, signs, or writing of any kind. "
    "Clean surfaces without any letters, numbers, symbols, or markings. "
    "No visible text or typography anywhere in the image."
)

# 네거티브 프롬프트에 추가할 텍스트 차단
TEXT_BLOCKING_NEGATIVE = (
    "text, words, letters, writing, typography, signs, signage, logos, labels, "
    "captions, titles, subtitles, banners, posters, billboards, watermarks, "
    "Korean text, Japanese text, Chinese text, hangul, kanji, hiragana, katakana, "
    "CJK characters, Asian script, any script, inscriptions, stamps, seals, "
    "store signs, street signs, neon signs, price tags, name tags, "
    "book covers, newspaper, magazine, documents, notes, memos"
)


# ============================================================
# 프롬프트 정제 함수
# ============================================================

def sanitize_scene_prompt(prompt: str, remove_text_keywords: bool = True) -> str:
    """
    씬 프롬프트에서 텍스트 관련 키워드 제거

    Args:
        prompt: 원본 프롬프트
        remove_text_keywords: 텍스트 관련 키워드 제거 여부

    Returns:
        정제된 프롬프트
    """
    if not prompt:
        return ""

    result = prompt

    if remove_text_keywords:
        # 정규식 패턴으로 제거
        for pattern in TEXT_PATTERNS:
            result = re.sub(pattern, '', result, flags=re.IGNORECASE)

        # 키워드 직접 제거
        for keyword in TEXT_KEYWORDS:
            # 단어 경계 기반 제거 (대소문자 무시)
            pattern = r'\b' + re.escape(keyword) + r'\b'
            result = re.sub(pattern, '', result, flags=re.IGNORECASE)

    # 중복 공백/콤마 정리
    result = re.sub(r',\s*,', ',', result)  # 연속 콤마
    result = re.sub(r'\s+', ' ', result)  # 중복 공백
    result = re.sub(r',\s*$', '', result)  # 끝의 콤마
    result = re.sub(r'^\s*,', '', result)  # 시작의 콤마
    result = result.strip()

    return result


def enhance_prompt_for_no_text(
    positive_prompt: str,
    negative_prompt: str = "",
    sanitize_keywords: bool = True
) -> Tuple[str, str]:
    """
    프롬프트에 텍스트 차단 지시 추가

    Args:
        positive_prompt: 포지티브 프롬프트
        negative_prompt: 네거티브 프롬프트 (옵션)
        sanitize_keywords: 기존 텍스트 키워드 제거 여부

    Returns:
        (enhanced_positive, enhanced_negative)
    """
    # 포지티브 프롬프트 정제 및 강화
    if sanitize_keywords:
        clean_positive = sanitize_scene_prompt(positive_prompt)
    else:
        clean_positive = positive_prompt

    # 텍스트 차단 지시 추가 (맨 앞에)
    enhanced_positive = f"{TEXT_BLOCKING_POSITIVE}, {clean_positive}"

    # 네거티브 프롬프트 강화
    if negative_prompt:
        enhanced_negative = f"{TEXT_BLOCKING_NEGATIVE}, {negative_prompt}"
    else:
        enhanced_negative = TEXT_BLOCKING_NEGATIVE

    return enhanced_positive, enhanced_negative


def get_text_blocking_suffix() -> str:
    """
    스타일 suffix에 추가할 텍스트 차단 문구
    """
    return ", blank surfaces, no text, no signs, no writing, clean image without any text or symbols"


def get_text_blocking_negative() -> str:
    """
    네거티브 프롬프트용 텍스트 차단 문구
    """
    return TEXT_BLOCKING_NEGATIVE


# ============================================================
# 헬퍼 함수
# ============================================================

def contains_text_keywords(prompt: str) -> List[str]:
    """
    프롬프트에 포함된 텍스트 관련 키워드 목록 반환

    Args:
        prompt: 검사할 프롬프트

    Returns:
        발견된 키워드 목록
    """
    found = []

    for keyword in TEXT_KEYWORDS:
        pattern = r'\b' + re.escape(keyword) + r'\b'
        if re.search(pattern, prompt, flags=re.IGNORECASE):
            found.append(keyword)

    return found


def is_prompt_text_safe(prompt: str) -> bool:
    """
    프롬프트에 텍스트 관련 키워드가 없는지 확인

    Args:
        prompt: 검사할 프롬프트

    Returns:
        True if safe (no text keywords)
    """
    return len(contains_text_keywords(prompt)) == 0


# ============================================================
# 테스트
# ============================================================

if __name__ == "__main__":
    # 테스트
    test_prompts = [
        "A cafe with Korean text on the sign, coffee cups on table",
        "City street with shop signs and billboards",
        "Book cover with title and author name",
        "Simple landscape with mountains",
    ]

    print("=== 프롬프트 정제 테스트 ===\n")

    for prompt in test_prompts:
        print(f"원본: {prompt}")

        found = contains_text_keywords(prompt)
        if found:
            print(f"발견된 키워드: {found}")

        sanitized = sanitize_scene_prompt(prompt)
        print(f"정제됨: {sanitized}")

        enhanced_pos, enhanced_neg = enhance_prompt_for_no_text(prompt)
        print(f"강화된 포지티브: {enhanced_pos[:100]}...")
        print(f"강화된 네거티브: {enhanced_neg[:80]}...")
        print()
