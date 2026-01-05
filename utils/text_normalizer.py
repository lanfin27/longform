# -*- coding: utf-8 -*-
"""
한국어 TTS 텍스트 정규화기 (longform 프로젝트용)

Chatter 서버 정규화기 보완:
1. 콤마 포함 숫자 + 한글 단위 (1,968원 → 천구백육십팔원)
2. 영어 약어 → 한글 발음 (GDP → 지디피)
3. 퍼센트 처리 (4% → 사퍼센트)

사용:
    from utils.text_normalizer import normalize_for_tts
    normalized_text = normalize_for_tts("GDP가 1,968원입니다")
"""

import re
from typing import Optional


class KoreanTTSNormalizer:
    """한국어 TTS 전처리 정규화기"""

    # 숫자 변환 테이블
    DIGITS = ['영', '일', '이', '삼', '사', '오', '육', '칠', '팔', '구']
    UNITS = ['', '십', '백', '천']
    LARGE_UNITS = ['', '만', '억', '조', '경']

    # 영어 약어 → 한글 발음 사전 (Chatter 보완)
    ENGLISH_TO_KOREAN = {
        # 경제/금융 (Chatter에 없는 항목들)
        "BIS": "비아이에스",
        "FED": "연준",
        "FOMC": "에프오엠씨",
        "ETF": "이티에프",
        "S&P": "에스앤피",
        "MSCI": "엠에스씨아이",
        "CPI": "소비자물가지수",
        "PPI": "생산자물가지수",
        "USD": "달러",
        "KRW": "원",
        "JPY": "엔",
        "EUR": "유로",
        "CNY": "위안",
        "GBP": "파운드",
        "IPO": "아이피오",
        "M&A": "엠앤에이",
        "ROE": "알오이",
        "ROA": "알오에이",
        "PER": "피이알",
        "PBR": "피비알",
        "EPS": "이피에스",
        "KOSPI": "코스피",
        "KOSDAQ": "코스닥",
        "NASDAQ": "나스닥",
        "NYSE": "뉴욕증권거래소",
        "DOW": "다우",
        "WTI": "더블유티아이",
        "OPEC": "오펙",
        "FTA": "에프티에이",
        "WTO": "더블유티오",
        "PPP": "피피피",
        "GNP": "지엔피",
        "GDP": "지디피",

        # IT/기술 (Chatter 보완)
        "LLM": "엘엘엠",
        "GPT": "지피티",
        "ChatGPT": "챗지피티",
        "Claude": "클로드",
        "Gemini": "제미나이",
        "OpenAI": "오픈에이아이",
        "AGI": "에이지아이",
        "ML": "엠엘",
        "DL": "디엘",
        "NLP": "엔엘피",
        "CV": "씨브이",
        "BERT": "버트",
        "TTS": "티티에스",
        "STT": "에스티티",
        "OCR": "오씨알",
        "SDK": "에스디케이",
        "IDE": "아이디이",
        "OS": "오에스",
        "iOS": "아이오에스",
        "macOS": "맥오에스",
        "Linux": "리눅스",
        "Windows": "윈도우",
        "AWS": "에이더블유에스",
        "GCP": "지씨피",
        "Azure": "애저",
        "CDN": "씨디엔",
        "DNS": "디엔에스",
        "SSL": "에스에스엘",
        "HTTPS": "에이치티티피에스",
        "HTTP": "에이치티티피",
        "FTP": "에프티피",
        "SSH": "에스에스에이치",

        # 교육/시험
        "SAT": "에스에이티",
        "TOEFL": "토플",
        "TOEIC": "토익",
        "IELTS": "아이엘츠",
        "GRE": "지알이",
        "GMAT": "지매트",
        "MBA": "엠비에이",
        "PhD": "피에이치디",
        "MS": "엠에스",
        "BS": "비에스",

        # 기타
        "FAQ": "에프에이큐",
        "DIY": "디아이와이",
        "ASAP": "에이에스에이피",
        "MVP": "엠브이피",
        "MRI": "엠알아이",
        "CT": "씨티",
        "EKG": "이케이지",
        "HIV": "에이치아이브이",
        "AIDS": "에이즈",
        "COVID": "코로나",
        "PCR": "피씨알",
        "SNS": "에스엔에스",
        "DM": "디엠",
        "PM": "피엠",
        "CEO": "씨이오",
        "CFO": "씨에프오",
        "CTO": "씨티오",
        "COO": "씨오오",
        "CMO": "씨엠오",

        # 시간/단위
        "vs": "대",
        "VS": "대",
        "v.s.": "대",
        "etc": "등",
        "No.": "넘버",
        "No": "넘버",
    }

    # 알파벳 → 한글 발음
    ALPHABET_TO_KOREAN = {
        'A': '에이', 'B': '비', 'C': '씨', 'D': '디', 'E': '이',
        'F': '에프', 'G': '지', 'H': '에이치', 'I': '아이', 'J': '제이',
        'K': '케이', 'L': '엘', 'M': '엠', 'N': '엔', 'O': '오',
        'P': '피', 'Q': '큐', 'R': '알', 'S': '에스', 'T': '티',
        'U': '유', 'V': '브이', 'W': '더블유', 'X': '엑스', 'Y': '와이',
        'Z': '제트'
    }

    # 한글 단위 (Chatter가 처리 못하는 것들)
    KOREAN_UNITS = {
        '원': '원',
        '달러': '달러',
        '엔': '엔',
        '유로': '유로',
        '위안': '위안',
        '파운드': '파운드',
        '억': '억',
        '조': '조',
        '만': '만',
        '경': '경',
        '개': '개',
        '명': '명',
        '번': '번',
        '차': '차',
        '회': '회',
        '배': '배',
        '위': '위',
        '등': '등',
        '층': '층',
        '살': '살',
        '세': '세',
        '년': '년',
        '월': '월',
        '일': '일',
        '시': '시',
        '분': '분',
        '초': '초',
        '개월': '개월',
    }

    def __init__(self):
        print("[KoreanTTSNormalizer] 초기화")

    def normalize(self, text: str) -> str:
        """
        TTS용 텍스트 정규화

        처리 순서:
        1. 영어 약어/단어 → 한글 발음
        2. 콤마 포함 숫자 + 한글 단위 → 한글
        3. 퍼센트 처리
        4. 남은 대문자 약어 처리
        """
        if not text:
            return text

        original = text

        # 1. 영어 약어 → 한글 (긴 것부터)
        text = self._convert_english(text)

        # 2. 콤마 포함 숫자 + 한글 단위 (핵심!)
        text = self._convert_number_with_korean_unit(text)

        # 3. 퍼센트 처리
        text = self._convert_percent(text)

        # 4. 소수점 숫자 처리
        text = self._convert_decimal(text)

        # 5. 남은 대문자 약어
        text = self._convert_remaining_uppercase(text)

        # 6. 연속 공백 정리
        text = re.sub(r'\s+', ' ', text).strip()

        if original != text:
            print(f"[Normalize] {original[:60]}... → {text[:60]}...")

        return text

    def _convert_english(self, text: str) -> str:
        """영어 약어/단어 → 한글 발음"""
        # 긴 것부터 처리 (ChatGPT before GPT)
        for eng, kor in sorted(self.ENGLISH_TO_KOREAN.items(), key=lambda x: -len(x[0])):
            # 단어 경계 고려 (정확한 매칭)
            pattern = r'(?<![a-zA-Z])' + re.escape(eng) + r'(?![a-zA-Z])'
            text = re.sub(pattern, kor, text, flags=re.IGNORECASE)
        return text

    def _convert_number_with_korean_unit(self, text: str) -> str:
        """
        콤마 포함 숫자 + 한글 단위 → 한글

        핵심: Chatter 서버가 처리 못하는 케이스 처리
        예: 1,968원 → 천구백육십팔원
        """
        # 긴 단위부터 처리 (개월 before 월)
        for unit in sorted(self.KOREAN_UNITS.keys(), key=lambda x: -len(x)):
            # 패턴: 숫자(콤마포함) + 단위
            pattern = rf'(\d{{1,3}}(?:,\d{{3}})*){unit}'

            def replacer(match):
                num_str = match.group(1).replace(',', '')
                try:
                    num = int(num_str)
                    korean_num = self._number_to_korean(num)
                    return korean_num + unit
                except:
                    return match.group(0)

            text = re.sub(pattern, replacer, text)

        return text

    def _convert_percent(self, text: str) -> str:
        """퍼센트 변환 (4% → 사퍼센트)"""
        def replacer(match):
            num_str = match.group(1)
            if '.' in num_str:
                # 소수점 있는 경우
                integer, decimal = num_str.split('.', 1)
                int_korean = self._number_to_korean(int(integer)) if integer else ''
                dec_korean = ''.join([self.DIGITS[int(d)] for d in decimal])
                return f"{int_korean}점{dec_korean}퍼센트"
            else:
                return self._number_to_korean(int(num_str)) + "퍼센트"

        pattern = r'(\d+\.?\d*)%'
        text = re.sub(pattern, replacer, text)
        return text

    def _convert_decimal(self, text: str) -> str:
        """소수점 숫자 변환 (3.14 → 삼점일사)"""
        def replacer(match):
            num_str = match.group(1)
            integer, decimal = num_str.split('.', 1)
            int_korean = self._number_to_korean(int(integer)) if integer else ''
            dec_korean = ''.join([self.DIGITS[int(d)] for d in decimal])
            return f"{int_korean}점{dec_korean}"

        # 소수점 숫자 (단위가 없는 경우만)
        pattern = r'(?<![a-zA-Z가-힣])(\d+\.\d+)(?![a-zA-Z가-힣%])'
        text = re.sub(pattern, replacer, text)
        return text

    def _convert_remaining_uppercase(self, text: str) -> str:
        """남은 대문자 약어 변환 (ABC → 에이비씨)"""
        def replacer(match):
            word = match.group(0)
            # 2~5글자 대문자만 변환
            if 2 <= len(word) <= 5:
                return ''.join([self.ALPHABET_TO_KOREAN.get(c, c) for c in word])
            return word

        # 대문자 2~5개 연속
        pattern = r'\b[A-Z]{2,5}\b'
        text = re.sub(pattern, replacer, text)
        return text

    def _number_to_korean(self, num: int) -> str:
        """숫자를 한글로 변환"""
        if num == 0:
            return '영'

        if num < 0:
            return '마이너스 ' + self._number_to_korean(-num)

        result = []
        chunk_idx = 0

        while num > 0:
            chunk = num % 10000
            if chunk > 0:
                chunk_korean = self._chunk_to_korean(chunk)
                if chunk_idx > 0:
                    chunk_korean += self.LARGE_UNITS[chunk_idx]
                result.append(chunk_korean)
            num //= 10000
            chunk_idx += 1

        return ''.join(reversed(result))

    def _chunk_to_korean(self, n: int) -> str:
        """4자리 이하 숫자를 한글로 변환"""
        if n == 0:
            return ''

        result = []
        unit_idx = 0

        while n > 0:
            digit = n % 10
            if digit > 0:
                # 일십, 일백, 일천 대신 십, 백, 천 사용
                if digit == 1 and unit_idx > 0:
                    result.append(self.UNITS[unit_idx])
                else:
                    result.append(self.DIGITS[digit] + self.UNITS[unit_idx])
            n //= 10
            unit_idx += 1

        return ''.join(reversed(result))


# ============================================================
# 싱글톤 및 간편 함수
# ============================================================

_normalizer: Optional[KoreanTTSNormalizer] = None


def get_normalizer() -> KoreanTTSNormalizer:
    """정규화기 싱글톤"""
    global _normalizer
    if _normalizer is None:
        _normalizer = KoreanTTSNormalizer()
    return _normalizer


def normalize_for_tts(text: str) -> str:
    """
    TTS용 텍스트 정규화 (간편 함수)

    Args:
        text: 원본 텍스트

    Returns:
        정규화된 텍스트

    Examples:
        >>> normalize_for_tts("GDP가 1,968원입니다")
        '지디피가 천구백육십팔원입니다'
        >>> normalize_for_tts("4% 성장률")
        '사퍼센트 성장률'
    """
    return get_normalizer().normalize(text)


# ============================================================
# 테스트
# ============================================================

if __name__ == "__main__":
    test_cases = [
        # 콤마 포함 숫자
        ("환율이 1,968원까지 올랐습니다.", "환율이 천구백육십팔원까지 올랐습니다."),
        ("1,450원에서 1,570원까지", "천사백오십원에서 천오백칠십원까지"),
        ("4,200억 원 규모", "사천이백억 원 규모"),

        # 퍼센트
        ("4% 성장률", "사퍼센트 성장률"),
        ("2.5% 하락", "이점오퍼센트 하락"),

        # 영어 약어
        ("GDP 대비 채무", "지디피 대비 채무"),
        ("BIS 기준 자본비율", "비아이에스 기준 자본비율"),
        ("IMF 구제금융", "아이엠에프 구제금융"),
        ("FED가 금리를", "연준가 금리를"),

        # 복합
        ("GDP가 1,968원", "지디피가 천구백육십팔원"),
        ("42개월째 상승", "사십이개월째 상승"),
    ]

    normalizer = KoreanTTSNormalizer()

    print("=" * 60)
    print("KoreanTTSNormalizer Test")
    print("=" * 60)

    passed = 0
    failed = 0

    for input_text, expected in test_cases:
        result = normalizer.normalize(input_text)
        if expected in result or result == expected:
            print(f"✅ PASS: '{input_text}' → '{result}'")
            passed += 1
        else:
            print(f"❌ FAIL: '{input_text}'")
            print(f"   결과: '{result}'")
            print(f"   기대: '{expected}'")
            failed += 1

    print(f"\n결과: {passed}/{passed+failed} 통과")
