# -*- coding: utf-8 -*-
"""
AI 텍스트 전처리기 v2.0 - 2단계 처리 시스템

TTS 생성 전 숫자/날짜/영어를 목표 언어 발음으로 변환

2단계 처리:
1. 규칙 기반 전처리: 숫자, 날짜, 퍼센트 (정확하고 빠름)
2. AI 전처리: 영어 단어/약어 (문맥 이해 필요)

지원 언어:
- 한국어 (ko): 12월 24일 → 십이월 이십사일, GDP → 지디피
- 일본어 (ja): 12月24日 → 十二月二十四日, GDP → ジーディーピー
- 중국어 (zh): 12月24日 → 十二月二十四日, GDP → 吉迪皮

사용법:
    from utils.ai_text_preprocessor import preprocess_text_for_tts, preprocess_scenes_sync

    # 동기 함수 (Streamlit용)
    result = preprocess_text_sync(text, language="ko", model_id="...")

    # 씬 일괄 처리
    processed_scenes = preprocess_scenes_sync(scenes, language="ko", model_id="...")
"""

import os
import re
import asyncio
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass


# ============================================================
# 규칙 기반 전처리기 (숫자, 날짜, 퍼센트)
# ============================================================

class RuleBasedPreprocessor:
    """규칙 기반 텍스트 전처리기 (숫자, 날짜, 퍼센트)"""

    # 숫자 한글 변환 테이블
    DIGITS = ['', '일', '이', '삼', '사', '오', '육', '칠', '팔', '구']
    DIGITS_FULL = ['영', '일', '이', '삼', '사', '오', '육', '칠', '팔', '구']
    UNITS = ['', '십', '백', '천']
    LARGE_UNITS = ['', '만', '억', '조', '경']

    @classmethod
    def preprocess(cls, text: str, language: str = "ko") -> Tuple[str, List[Dict]]:
        """
        규칙 기반 전처리 실행

        Args:
            text: 원본 텍스트
            language: 목표 언어 (ko, ja, zh)

        Returns:
            (변환된 텍스트, 변경 목록)
        """
        if not text:
            return text, []

        if language != "ko":
            # 현재는 한국어만 지원
            return text, []

        original = text
        changes = []

        # 1. 콤마 포함 숫자 + 단위 (최우선!)
        # 1,480원대 → 천사백팔십원대
        text, new_changes = cls._convert_comma_numbers(text)
        changes.extend(new_changes)

        # 2. 연도 (1997년 → 천구백구십칠년)
        text, new_changes = cls._convert_years(text)
        changes.extend(new_changes)

        # 3. 월 (12월 → 십이월)
        text, new_changes = cls._convert_months(text)
        changes.extend(new_changes)

        # 4. 일 (24일 → 이십사일)
        text, new_changes = cls._convert_days(text)
        changes.extend(new_changes)

        # 5. 퍼센트 (4% → 사퍼센트, 2.5% → 이점오퍼센트)
        text, new_changes = cls._convert_percent(text)
        changes.extend(new_changes)

        # 6. 일반 숫자 + 단위 (30원 → 삼십원)
        text, new_changes = cls._convert_number_units(text)
        changes.extend(new_changes)

        # 7. 소수점 숫자 (3.14 → 삼점일사)
        text, new_changes = cls._convert_decimals(text)
        changes.extend(new_changes)

        return text, changes

    @classmethod
    def _convert_comma_numbers(cls, text: str) -> Tuple[str, List[Dict]]:
        """콤마 포함 숫자 + 단위 변환"""
        changes = []

        # 단위 패턴 (긴 것부터)
        units = (
            r'원대까지요|원대까지|원대를|원대에서|원대|'
            r'원까지|원이|원을|원에서|원|'
            r'억|조|만|명|개|번|차|회|배|위|등|'
            r'달러|엔|유로|위안'
        )

        pattern = rf'(\d{{1,3}}(?:,\d{{3}})+)({units})?'

        def replacer(match):
            num_str = match.group(1).replace(',', '')
            suffix = match.group(2) or ''
            try:
                num = int(num_str)
                korean = cls._number_to_korean(num)
                result = korean + suffix
                changes.append({
                    "original": match.group(0),
                    "converted": result,
                    "type": "comma_number"
                })
                return result
            except:
                return match.group(0)

        text = re.sub(pattern, replacer, text)
        return text, changes

    @classmethod
    def _convert_years(cls, text: str) -> Tuple[str, List[Dict]]:
        """연도 변환 (1997년 → 천구백구십칠년)"""
        changes = []

        def replacer(match):
            year = int(match.group(1))
            korean = cls._number_to_korean(year) + "년"
            changes.append({
                "original": match.group(0),
                "converted": korean,
                "type": "year"
            })
            return korean

        text = re.sub(r'(\d{4})년', replacer, text)
        return text, changes

    @classmethod
    def _convert_months(cls, text: str) -> Tuple[str, List[Dict]]:
        """월 변환 (12월 → 십이월)"""
        changes = []

        def replacer(match):
            month = int(match.group(1))
            korean = cls._number_to_korean(month) + "월"
            changes.append({
                "original": match.group(0),
                "converted": korean,
                "type": "month"
            })
            return korean

        text = re.sub(r'(\d{1,2})월', replacer, text)
        return text, changes

    @classmethod
    def _convert_days(cls, text: str) -> Tuple[str, List[Dict]]:
        """일 변환 (24일 → 이십사일)"""
        changes = []

        def replacer(match):
            day = int(match.group(1))
            korean = cls._number_to_korean(day) + "일"
            changes.append({
                "original": match.group(0),
                "converted": korean,
                "type": "day"
            })
            return korean

        # 숫자+일 패턴 (단, 이미 한글화된 ~월 뒤의 일은 제외하지 않음)
        text = re.sub(r'(\d{1,2})일', replacer, text)
        return text, changes

    @classmethod
    def _convert_percent(cls, text: str) -> Tuple[str, List[Dict]]:
        """퍼센트 변환 (4% → 사퍼센트, 2.5% → 이점오퍼센트)"""
        changes = []

        def replacer(match):
            num_str = match.group(1)
            if '.' in num_str:
                integer, decimal = num_str.split('.', 1)
                int_korean = cls._number_to_korean(int(integer)) if integer else ''
                dec_korean = ''.join([cls.DIGITS_FULL[int(d)] for d in decimal])
                result = f"{int_korean}점{dec_korean}퍼센트"
            else:
                result = cls._number_to_korean(int(num_str)) + "퍼센트"
            changes.append({
                "original": match.group(0),
                "converted": result,
                "type": "percent"
            })
            return result

        text = re.sub(r'(\d+\.?\d*)%', replacer, text)
        return text, changes

    @classmethod
    def _convert_number_units(cls, text: str) -> Tuple[str, List[Dict]]:
        """일반 숫자 + 단위 변환 (30원 → 삼십원)"""
        changes = []

        # 단위 목록 (긴 것부터)
        units = (
            r'원대까지요|원대까지|원대를|원대에서|원대|'
            r'원까지|원이|원을|원에서|원|'
            r'억|조|만|명|개|번|차|회|배|위|등|층|권|장|편|'
            r'시간|시|분|초|살|세|개월|'
            r'달러|엔|유로|위안|파운드'
        )

        pattern = rf'(\d+)({units})'

        def replacer(match):
            num = int(match.group(1))
            unit = match.group(2)
            korean = cls._number_to_korean(num) + unit
            changes.append({
                "original": match.group(0),
                "converted": korean,
                "type": "number_unit"
            })
            return korean

        text = re.sub(pattern, replacer, text)
        return text, changes

    @classmethod
    def _convert_decimals(cls, text: str) -> Tuple[str, List[Dict]]:
        """소수점 숫자 변환 (3.14 → 삼점일사)"""
        changes = []

        def replacer(match):
            num_str = match.group(1)
            integer, decimal = num_str.split('.', 1)
            int_korean = cls._number_to_korean(int(integer)) if integer else ''
            dec_korean = ''.join([cls.DIGITS_FULL[int(d)] for d in decimal])
            result = f"{int_korean}점{dec_korean}"
            changes.append({
                "original": match.group(0),
                "converted": result,
                "type": "decimal"
            })
            return result

        # 소수점 숫자 (단위가 없는 경우만)
        pattern = r'(?<![a-zA-Z가-힣])(\d+\.\d+)(?![a-zA-Z가-힣%])'
        text = re.sub(pattern, replacer, text)
        return text, changes

    @classmethod
    def _number_to_korean(cls, num: int) -> str:
        """숫자를 한글로 변환"""
        if num == 0:
            return '영'
        if num < 0:
            return '마이너스 ' + cls._number_to_korean(-num)

        result = []
        large_unit_idx = 0

        while num > 0:
            chunk = num % 10000
            if chunk > 0:
                chunk_korean = cls._four_digits_to_korean(chunk)
                if large_unit_idx > 0:
                    chunk_korean += cls.LARGE_UNITS[large_unit_idx]
                result.append(chunk_korean)
            num //= 10000
            large_unit_idx += 1

        return ''.join(reversed(result))

    @classmethod
    def _four_digits_to_korean(cls, num: int) -> str:
        """4자리 이하 숫자를 한글로 변환"""
        if num == 0:
            return ''

        result = []
        unit_idx = 0

        while num > 0:
            digit = num % 10
            if digit > 0:
                # 1은 단위 앞에서 생략 (십, 백, 천)
                if digit == 1 and unit_idx > 0:
                    result.append(cls.UNITS[unit_idx])
                else:
                    result.append(cls.DIGITS[digit] + cls.UNITS[unit_idx])
            num //= 10
            unit_idx += 1

        return ''.join(reversed(result))


# ============================================================
# AI 프로바이더
# ============================================================

try:
    from utils.ai_providers import (
        get_model, get_available_models, AIProvider, get_fallback_model
    )
except ImportError:
    # 폴백: 프로바이더 없이도 규칙 기반 전처리는 작동
    def get_model(model_id):
        return None
    def get_available_models():
        return {}
    def get_fallback_model():
        return None
    class AIProvider:
        ANTHROPIC = "anthropic"
        GOOGLE = "google"
        OPENAI = "openai"


# ============================================================
# 결과 데이터 클래스
# ============================================================

@dataclass
class PreprocessResult:
    """전처리 결과"""
    original_text: str
    processed_text: str
    language: str
    model_used: str
    changes: List[Dict]  # [{"original": "...", "converted": "...", "type": "..."}, ...]
    success: bool
    error: Optional[str] = None
    rule_changes: int = 0  # 규칙 기반 변경 수
    ai_changes: int = 0    # AI 변경 수


# ============================================================
# AI 텍스트 전처리기 (2단계 처리)
# ============================================================

class AITextPreprocessor:
    """AI 기반 TTS 텍스트 전처리기 (2단계 처리)"""

    # AI 프롬프트 (영어 변환 전용)
    PROMPTS = {
        "ko": """당신은 한국어 TTS 전처리 전문가입니다.
주어진 텍스트에서 **영어 단어와 약어만** 찾아 한국어 발음으로 변환해주세요.

⚠️ 중요: 숫자, 날짜, 한글은 이미 변환되어 있으므로 절대 건드리지 마세요!

변환 규칙:
1. 영어 약어 → 한글 발음: GDP → 지디피, IMF → 아이엠에프, BIS → 비아이에스, AI → 에이아이
2. 영어 단어 → 한글 외래어: Christmas → 크리스마스, smartphone → 스마트폰, YouTube → 유튜브
3. 고유명사 → 널리 알려진 한글: Tesla → 테슬라, iPhone → 아이폰, Netflix → 넷플릭스
4. 이미 한글인 부분은 절대 변경하지 마세요
5. 숫자나 한글 숫자(천사백팔십 등)는 절대 변경하지 마세요

출력:
- 변환된 전체 텍스트만 출력
- 설명이나 주석 없이 텍스트만 반환
- 원문의 줄바꿈과 형식 유지""",

        "ja": """あなたは日本語TTS前処理の専門家です。
与えられたテキストから**英語の単語と略語のみ**を見つけて、カタカナ発音に変換してください。

⚠️ 重要: 数字はすでに変換されているので、絶対に触らないでください！

変換ルール:
1. 英語略語 → カタカナ: GDP → ジーディーピー, AI → エーアイ
2. 英語単語 → カタカナ: Christmas → クリスマス, YouTube → ユーチューブ
3. 既に日本語の部分は絶対に変更しないでください

出力: 変換された全文のみ。説明なし。""",

        "zh": """你是中文TTS预处理专家。
请在给定的文本中**只找英语单词和缩写**，并将其转换为中文发音。

⚠️ 重要: 数字已经转换完成，请勿修改！

转换规则:
1. 英语缩写 → 中文发音: GDP → 吉迪皮, AI → 艾爱
2. 英语单词 → 中文外来语: Christmas → 圣诞节, YouTube → 油管

输出: 只输出转换后的完整文本。不添加任何说明。"""
    }

    def __init__(self):
        self._clients = {}

    def _get_client(self, provider):
        """프로바이더별 클라이언트 반환"""
        if provider not in self._clients:
            if provider == AIProvider.ANTHROPIC or provider == "anthropic":
                import anthropic
                self._clients[provider] = anthropic.Anthropic()
            elif provider == AIProvider.GOOGLE or provider == "google":
                import google.generativeai as genai
                api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
                genai.configure(api_key=api_key)
                self._clients[provider] = genai
            elif provider == AIProvider.OPENAI or provider == "openai":
                import openai
                self._clients[provider] = openai.OpenAI()
        return self._clients.get(provider)

    async def preprocess(
        self,
        text: str,
        language: str = "ko",
        model_id: Optional[str] = None
    ) -> PreprocessResult:
        """
        텍스트 전처리 (2단계: 규칙 → AI)

        Args:
            text: 원본 텍스트
            language: 목표 언어 (ko, ja, zh)
            model_id: AI 모델 ID (None이면 규칙 기반만 실행)

        Returns:
            PreprocessResult
        """
        if not text or not text.strip():
            return PreprocessResult(
                original_text=text,
                processed_text=text,
                language=language,
                model_used="",
                changes=[],
                success=True
            )

        original_text = text
        all_changes = []

        # ========================================
        # 1단계: 규칙 기반 전처리 (숫자, 날짜, 퍼센트)
        # ========================================
        text, rule_changes = RuleBasedPreprocessor.preprocess(text, language)
        all_changes.extend(rule_changes)
        rule_change_count = len(rule_changes)

        if rule_change_count > 0:
            print(f"  [규칙 기반] {rule_change_count}개 변환")

        # ========================================
        # 2단계: AI 전처리 (영어 단어/약어)
        # ========================================
        ai_change_count = 0

        # 영어가 있는지 확인
        has_english = bool(re.search(r'[A-Za-z]{2,}', text))

        if has_english and model_id:
            model_info = get_model(model_id)
            if model_info:
                try:
                    ai_result = await self._call_ai_for_english(
                        text=text,
                        language=language,
                        provider=model_info.provider,
                        model_id=model_id
                    )
                    if ai_result and ai_result != text:
                        # AI 변경 감지
                        ai_changes = self._detect_english_changes(text, ai_result)
                        all_changes.extend(ai_changes)
                        ai_change_count = len(ai_changes)
                        text = ai_result
                        if ai_change_count > 0:
                            print(f"  [AI] {ai_change_count}개 변환")
                except Exception as e:
                    print(f"  [AI] 오류: {e}")

        return PreprocessResult(
            original_text=original_text,
            processed_text=text,
            language=language,
            model_used=model_id or "",
            changes=all_changes,
            success=True,
            rule_changes=rule_change_count,
            ai_changes=ai_change_count
        )

    async def _call_ai_for_english(
        self,
        text: str,
        language: str,
        provider,
        model_id: str
    ) -> Optional[str]:
        """AI API 호출 (영어 변환용)"""
        client = self._get_client(provider)
        if not client:
            return None

        system_prompt = self.PROMPTS.get(language, self.PROMPTS["ko"])
        user_prompt = f"""다음 텍스트에서 영어만 한글 발음으로 변환해주세요.
숫자와 한글은 절대 변경하지 마세요.

원본:
{text}

변환 결과:"""

        try:
            if provider == AIProvider.ANTHROPIC or str(provider) == "AIProvider.ANTHROPIC":
                response = client.messages.create(
                    model=model_id,
                    max_tokens=4096,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}]
                )
                result = response.content[0].text.strip()

            elif provider == AIProvider.GOOGLE or str(provider) == "AIProvider.GOOGLE":
                full_prompt = f"{system_prompt}\n\n{user_prompt}"
                model = client.GenerativeModel(model_id)
                response = model.generate_content(full_prompt)
                result = response.text.strip()

            elif provider == AIProvider.OPENAI or str(provider) == "AIProvider.OPENAI":
                response = client.chat.completions.create(
                    model=model_id,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    max_tokens=4096
                )
                result = response.choices[0].message.content.strip()

            else:
                return None

            # 결과 검증: 길이가 너무 다르면 원본 유지
            if len(result) < len(text) * 0.5 or len(result) > len(text) * 2:
                print(f"  [AI] 결과 길이 이상, 원본 유지")
                return text

            return result

        except Exception as e:
            print(f"  [AI] API 오류: {e}")
            return None

    def _detect_english_changes(self, original: str, processed: str) -> List[Dict]:
        """영어 변환 감지"""
        changes = []

        # 원본에서 영어 단어 추출
        english_words = set(re.findall(r'[A-Za-z][A-Za-z0-9]*(?:\s+[A-Za-z][A-Za-z0-9]*)?', original))

        for word in english_words:
            if len(word) < 2:
                continue
            # 변환본에서 해당 단어가 없으면 변경된 것
            if word not in processed and word.lower() not in processed.lower():
                changes.append({
                    "original": word,
                    "converted": "(AI 변환)",
                    "type": "english"
                })

        return changes

    async def preprocess_scenes(
        self,
        scenes: List[Dict],
        language: str = "ko",
        model_id: Optional[str] = None,
        progress_callback=None
    ) -> List[Dict]:
        """
        씬 리스트 전처리 (2단계)

        Args:
            scenes: 씬 데이터 리스트 [{"scene_id": 1, "text": "..."}, ...]
            language: 목표 언어
            model_id: AI 모델 ID
            progress_callback: 진행 콜백 (scene_idx, total, result)

        Returns:
            전처리된 씬 리스트
        """
        total = len(scenes)
        results = []

        print(f"\n[AIPreprocessor] {total}개 씬 전처리 시작 (2단계: 규칙→AI)")
        print("=" * 60)

        for idx, scene in enumerate(scenes):
            text = scene.get("text", "")
            scene_id = scene.get("scene_id", idx + 1)

            print(f"\n[씬 {scene_id}] 원본: {text[:60]}...")

            result = await self.preprocess(text, language, model_id)

            # 씬 복사 + 전처리 결과 추가
            processed_scene = dict(scene)
            processed_scene["preprocessed_text"] = result.processed_text
            processed_scene["preprocess_changes"] = result.changes
            processed_scene["preprocess_success"] = result.success

            results.append(processed_scene)

            if progress_callback:
                progress_callback(idx + 1, total, result)

            total_changes = len(result.changes)
            if result.processed_text != text:
                print(f"  → 변환: {result.processed_text[:60]}...")
            print(f"[AIPreprocessor] 씬 {scene_id} 전처리 완료: {total_changes}개 변경")

        print("\n" + "=" * 60)
        total_changes = sum(len(s.get("preprocess_changes", [])) for s in results)
        changed_scenes = sum(1 for s in results if s.get("preprocess_changes"))
        print(f"[AIPreprocessor] 완료: {total}개 씬, {changed_scenes}개 변경됨, 총 {total_changes}개 항목")

        return results


# ============================================================
# 동기 래퍼 (Streamlit 호환)
# ============================================================

def preprocess_text_sync(
    text: str,
    language: str = "ko",
    model_id: Optional[str] = None
) -> PreprocessResult:
    """동기 방식 텍스트 전처리"""
    preprocessor = AITextPreprocessor()

    # 이벤트 루프 확인
    try:
        loop = asyncio.get_running_loop()
        # 이미 이벤트 루프가 있으면 새 스레드에서 실행
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(
                asyncio.run,
                preprocessor.preprocess(text, language, model_id)
            )
            return future.result()
    except RuntimeError:
        # 이벤트 루프가 없으면 직접 실행
        return asyncio.run(preprocessor.preprocess(text, language, model_id))


def preprocess_scenes_sync(
    scenes: List[Dict],
    language: str = "ko",
    model_id: Optional[str] = None,
    progress_callback=None
) -> List[Dict]:
    """동기 방식 씬 전처리"""
    preprocessor = AITextPreprocessor()

    try:
        loop = asyncio.get_running_loop()
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(
                asyncio.run,
                preprocessor.preprocess_scenes(scenes, language, model_id, progress_callback)
            )
            return future.result()
    except RuntimeError:
        return asyncio.run(
            preprocessor.preprocess_scenes(scenes, language, model_id, progress_callback)
        )


# ============================================================
# 간편 함수
# ============================================================

_preprocessor: Optional[AITextPreprocessor] = None


def get_preprocessor() -> AITextPreprocessor:
    """전처리기 싱글톤"""
    global _preprocessor
    if _preprocessor is None:
        _preprocessor = AITextPreprocessor()
    return _preprocessor


async def preprocess_text_for_tts(
    text: str,
    language: str = "ko",
    model_id: Optional[str] = None
) -> PreprocessResult:
    """
    TTS용 텍스트 전처리 (간편 함수)

    Args:
        text: 원본 텍스트
        language: 목표 언어 (ko, ja, zh)
        model_id: AI 모델 ID

    Returns:
        PreprocessResult
    """
    return await get_preprocessor().preprocess(text, language, model_id)


# ============================================================
# 테스트
# ============================================================

if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    print("=" * 60)
    print("규칙 기반 전처리 테스트")
    print("=" * 60)

    test_cases = [
        ("12월 24일, 크리스마스 이브 아침이었습니다.",
         "십이월 이십사일, 크리스마스 이브 아침이었습니다."),
        ("1,480원대를 맴돌던 환율이 갑자기 30원 넘게 떨어진 겁니다.",
         "천사백팔십원대를 맴돌던 환율이 갑자기 삼십원 넘게 떨어진 겁니다."),
        ("1,450원대까지요.",
         "천사백오십원대까지요."),
        ("1997년 외환위기",
         "천구백구십칠년 외환위기"),
        ("4% 성장률",
         "사퍼센트 성장률"),
        ("GDP가 1,968원까지 올랐습니다.",
         "GDP가 천구백육십팔원까지 올랐습니다."),
        ("2.5% 하락",
         "이점오퍼센트 하락"),
    ]

    passed = 0
    failed = 0

    for input_text, expected in test_cases:
        result, changes = RuleBasedPreprocessor.preprocess(input_text)

        if result == expected:
            print(f"✅ PASS: {input_text[:40]}...")
            print(f"   → {result[:50]}... ({len(changes)}개 변경)")
            passed += 1
        else:
            print(f"❌ FAIL: {input_text[:40]}...")
            print(f"   예상: {expected[:50]}...")
            print(f"   실제: {result[:50]}...")
            failed += 1
        print()

    print("=" * 60)
    print(f"결과: {passed}/{passed+failed} 통과")
