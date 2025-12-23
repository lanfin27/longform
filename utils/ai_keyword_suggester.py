# -*- coding: utf-8 -*-
"""
AI 기반 키워드 확장 모듈

지원 AI:
- Google Gemini (빠름, 기본)
- Anthropic Claude (정확함)

기능:
- 입력 키워드 → 관련 키워드 10-25개 추천
- 유튜브 검색에 최적화된 키워드 생성
- 카테고리별 분류 (직접관련, 유사어, 롱테일 등)
"""

import os
import json
import re
from typing import Dict, List, Optional


class AIKeywordSuggester:
    """AI 기반 키워드 확장기"""

    def __init__(self, api_provider: str = "gemini"):
        """
        Args:
            api_provider: "gemini" 또는 "claude"
        """
        self.api_provider = api_provider
        self.gemini_api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")

    def check_api_key(self) -> bool:
        """API 키 확인"""
        if self.api_provider == "gemini":
            return bool(self.gemini_api_key)
        elif self.api_provider == "claude":
            return bool(self.anthropic_api_key)
        return False

    def suggest_keywords(
        self,
        keyword: str,
        count: int = 15,
        context: str = "youtube"
    ) -> Dict:
        """
        키워드 확장 추천

        Args:
            keyword: 원본 키워드 (예: "연금")
            count: 추천할 키워드 수
            context: 컨텍스트 (youtube, blog, search 등)

        Returns:
            {
                "success": True/False,
                "original": "연금",
                "api_used": "gemini",
                "suggestions": [
                    {"keyword": "국민연금", "category": "직접_관련", "relevance": "high"},
                    ...
                ],
                "categories": {
                    "직접_관련": ["국민연금", "퇴직연금", ...],
                    "동의어_유사어": ["노후자금", ...],
                    ...
                },
                "total_count": 15
            }
        """
        if not keyword or not keyword.strip():
            return self._empty_result(keyword)

        if self.api_provider == "gemini":
            return self._suggest_with_gemini(keyword, count, context)
        elif self.api_provider == "claude":
            return self._suggest_with_claude(keyword, count, context)
        else:
            # 폴백: 기본 확장
            return self._fallback_suggestions(keyword)

    def _suggest_with_gemini(
        self,
        keyword: str,
        count: int,
        context: str
    ) -> Dict:
        """Gemini API로 키워드 추천"""

        if not self.gemini_api_key:
            print("[AIKeyword] Gemini API 키 없음, 폴백 사용")
            return self._fallback_suggestions(keyword)

        try:
            import google.generativeai as genai

            genai.configure(api_key=self.gemini_api_key)
            model = genai.GenerativeModel('gemini-1.5-flash')

            prompt = self._build_prompt(keyword, count, context)

            response = model.generate_content(prompt)
            text = response.text

            return self._parse_response(text, keyword, "gemini")

        except ImportError:
            print("[AIKeyword] google-generativeai 패키지가 설치되지 않음")
            return self._fallback_suggestions(keyword)
        except Exception as e:
            print(f"[AIKeyword] Gemini 오류: {e}")
            return self._fallback_suggestions(keyword)

    def _suggest_with_claude(
        self,
        keyword: str,
        count: int,
        context: str
    ) -> Dict:
        """Claude API로 키워드 추천"""

        if not self.anthropic_api_key:
            print("[AIKeyword] Anthropic API 키 없음, 폴백 사용")
            return self._fallback_suggestions(keyword)

        try:
            import anthropic

            client = anthropic.Anthropic(api_key=self.anthropic_api_key)

            prompt = self._build_prompt(keyword, count, context)

            message = client.messages.create(
                model="claude-3-haiku-20240307",  # 빠르고 저렴한 모델
                max_tokens=1024,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )

            text = message.content[0].text

            return self._parse_response(text, keyword, "claude")

        except ImportError:
            print("[AIKeyword] anthropic 패키지가 설치되지 않음")
            return self._fallback_suggestions(keyword)
        except Exception as e:
            print(f"[AIKeyword] Claude 오류: {e}")
            return self._fallback_suggestions(keyword)

    def _build_prompt(self, keyword: str, count: int, context: str) -> str:
        """AI 프롬프트 생성"""

        return f"""당신은 유튜브 키워드 분석 전문가입니다.

입력 키워드: "{keyword}"

이 키워드와 관련된 유튜브 검색 키워드를 {count}개 추천해주세요.

다음 카테고리별로 분류해서 JSON 형식으로 응답해주세요:

1. 직접_관련 (3-5개): 키워드가 직접 포함된 변형
   예: "{keyword}" → "{keyword} 추천", "{keyword} 방법"

2. 동의어_유사어 (3-5개): 같은 의미의 다른 표현
   예: "연금" → "노후자금", "퇴직금"

3. 관련_주제 (3-5개): 연관된 더 넓은 주제
   예: "연금" → "재테크", "노후준비", "은퇴설계"

4. 롱테일_키워드 (3-5개): 구체적인 검색 쿼리
   예: "연금" → "국민연금 수령나이 계산", "퇴직연금 IRP 추천"

5. 트렌드_키워드 (2-3개): 최근 이슈와 연결
   예: "연금" → "연금개혁", "국민연금 고갈"

응답 형식 (JSON만, 설명 없이):
{{
  "직접_관련": ["키워드1", "키워드2", ...],
  "동의어_유사어": ["키워드1", "키워드2", ...],
  "관련_주제": ["키워드1", "키워드2", ...],
  "롱테일_키워드": ["키워드1", "키워드2", ...],
  "트렌드_키워드": ["키워드1", "키워드2", ...]
}}"""

    def _parse_response(self, text: str, keyword: str, api_used: str) -> Dict:
        """AI 응답 파싱"""

        try:
            # JSON 블록 추출
            json_match = re.search(r'\{[\s\S]*\}', text)
            if json_match:
                categories = json.loads(json_match.group())
            else:
                print(f"[AIKeyword] JSON 파싱 실패: {text[:200]}")
                return self._fallback_suggestions(keyword)

            # 결과 정리
            all_keywords = []
            for cat_name, keywords in categories.items():
                if isinstance(keywords, list):
                    for kw in keywords:
                        if isinstance(kw, str) and kw.strip():
                            all_keywords.append({
                                "keyword": kw.strip(),
                                "category": cat_name,
                                "relevance": "high" if cat_name == "직접_관련" else "medium"
                            })

            return {
                "success": True,
                "original": keyword,
                "api_used": api_used,
                "suggestions": all_keywords,
                "categories": categories,
                "total_count": len(all_keywords)
            }

        except json.JSONDecodeError as e:
            print(f"[AIKeyword] JSON 디코딩 오류: {e}")
            return self._fallback_suggestions(keyword)
        except Exception as e:
            print(f"[AIKeyword] 응답 파싱 오류: {e}")
            return self._fallback_suggestions(keyword)

    def _fallback_suggestions(self, keyword: str) -> Dict:
        """폴백: 규칙 기반 키워드 확장"""

        # 기본 접미사/접두사
        suffixes = ["추천", "방법", "비교", "후기", "정리", "총정리", "꿀팁", "현실", "장단점"]
        prefixes = ["초보", "왕초보", "2024", "2025", "최신", "쉬운"]

        # 일반 관련 키워드 패턴
        general_related = {
            "연금": ["국민연금", "퇴직연금", "개인연금", "연금저축", "노후준비", "은퇴설계", "IRP", "연금보험"],
            "재테크": ["주식", "부동산", "예금", "적금", "ETF", "펀드", "코인", "투자"],
            "부동산": ["아파트", "전세", "월세", "청약", "분양", "갭투자", "부동산투자", "매매"],
            "일본": ["도쿄", "오사카", "교토", "일본여행", "일본어", "일본생활", "일본먹방", "일드"],
            "브이로그": ["일상", "vlog", "데일리", "하루", "브이로그카메라", "브이로그편집"],
            "먹방": ["맛집", "음식", "리뷰", "쿡방", "레시피", "혼밥", "야식"],
            "운동": ["헬스", "다이어트", "홈트", "피트니스", "근육", "체중감량", "식단"],
            "게임": ["공략", "리뷰", "스트리밍", "e스포츠", "신작", "모바일게임"],
        }

        suggestions = []
        categories = {
            "직접_관련": [],
            "동의어_유사어": [],
            "관련_주제": [],
            "롱테일_키워드": [],
            "트렌드_키워드": []
        }

        # 직접 관련 (접미사 조합)
        for suffix in suffixes[:4]:
            kw = f"{keyword} {suffix}"
            categories["직접_관련"].append(kw)
            suggestions.append({
                "keyword": kw,
                "category": "직접_관련",
                "relevance": "high"
            })

        # 접두사 조합
        for prefix in prefixes[:2]:
            kw = f"{prefix} {keyword}"
            categories["직접_관련"].append(kw)
            suggestions.append({
                "keyword": kw,
                "category": "직접_관련",
                "relevance": "high"
            })

        # 특정 키워드에 대한 관련 키워드
        keyword_lower = keyword.lower()
        for key, related in general_related.items():
            if key in keyword_lower or keyword_lower in key:
                for r in related[:4]:
                    if r not in [s["keyword"] for s in suggestions]:
                        categories["관련_주제"].append(r)
                        suggestions.append({
                            "keyword": r,
                            "category": "관련_주제",
                            "relevance": "medium"
                        })

        # 롱테일 키워드
        longtail = [
            f"{keyword} 시작하는 방법",
            f"{keyword} 초보자 가이드",
            f"{keyword} 하는법"
        ]
        for lt in longtail:
            categories["롱테일_키워드"].append(lt)
            suggestions.append({
                "keyword": lt,
                "category": "롱테일_키워드",
                "relevance": "medium"
            })

        return {
            "success": True,
            "original": keyword,
            "api_used": "fallback",
            "suggestions": suggestions,
            "categories": categories,
            "total_count": len(suggestions)
        }

    def _empty_result(self, keyword: str) -> Dict:
        """빈 결과 반환"""
        return {
            "success": False,
            "original": keyword,
            "api_used": None,
            "suggestions": [],
            "categories": {},
            "total_count": 0,
            "error": "키워드가 비어있습니다"
        }


# 싱글톤 인스턴스
_ai_keyword_suggester: Optional[AIKeywordSuggester] = None


def get_ai_keyword_suggester(api_provider: str = "gemini") -> AIKeywordSuggester:
    """AI 키워드 제안기 싱글톤 반환"""
    global _ai_keyword_suggester
    if _ai_keyword_suggester is None or _ai_keyword_suggester.api_provider != api_provider:
        _ai_keyword_suggester = AIKeywordSuggester(api_provider)
    return _ai_keyword_suggester
