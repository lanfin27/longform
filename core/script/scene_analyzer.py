"""
씬 분석기 - 스크립트를 씬 단위로 분할하고 연출가이드 생성

주요 기능:
1. 스크립트 → 씬 자동 분할 (장면 전환 감지)
2. 각 씬의 연출가이드 생성
3. 등장 캐릭터 추출 (상세 외모 프롬프트 포함)
4. 씬별 이미지 프롬프트 생성
"""
import json
from pathlib import Path
from typing import List, Dict, Optional

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config.settings import ANTHROPIC_API_KEY, GOOGLE_API_KEY, GEMINI_API_KEY
from core.prompt.prompt_template_manager import get_template_manager

# 디버그 모드 (True로 설정하면 상세 로그 출력)
DEBUG = True

def debug_log(message: str):
    """디버그 로그 출력"""
    if DEBUG:
        print(f"[SceneAnalyzer] {message}")


# ============================================================
# 🔴 캐릭터 이름 유효성 검증용 상수 및 함수 (Problem 49)
# ============================================================

# 잘못된 캐릭터로 추출되면 안 되는 단어 목록
INVALID_CHARACTER_WORDS = {
    # 조사/어미가 붙은 패턴
    '의', '이', '가', '은', '는', '를', '을', '에서', '로', '으로',
    '에게', '한테', '께', '와', '과', '이다', '이고', '이며',

    # 일반 명사
    '회사', '기업', '브랜드', '제품', '서비스', '시장', '산업',
    '경쟁', '성장', '매출', '이익', '수익', '투자', '가치',
    '콘텐츠', '플랫폼', '사업', '전략', '비전', '목표',
    '회사의', '기업의', '브랜드의', '제품의', '서비스의',
    '브랜드이', '회사가', '기업이', '제품이',

    # 직책만 (이름 없이)
    '대표', '회장', '사장', '이사', '임원', '창업자', '설립자',
    'ceo', 'cfo', 'cto', 'coo',

    # 국가/지역
    '한국', '미국', '중국', '일본', '사우디', '유럽', '아시아',
    '사우디의', '한국의', '미국의', '중국의', '일본의',
    '사우디아라비아', '아라비아', '라비아',

    # 일반 동사/형용사 어근
    '하는', '이끄는', '만드는', '성장하는', '발전하는',
    '사실상', '실질적', '결국', '결과적',

    # 기타 잘못 추출되는 패턴
    '구강과', '경제마저', '자유보다', '라비아를', '누구도',
    '이번', '지난', '다음', '올해', '내년', '작년',
    '하나', '둘', '셋', '넷', '다섯',
}

# 알려진 캐릭터 IP 목록 (동물, 마스코트, 가상 캐릭터)
KNOWN_CHARACTER_IPS = {
    '아기상어': {'name_en': 'Baby Shark', 'category': '동물 캐릭터', 'owner': '더 핑크퐁 컴퍼니'},
    '베이비샤크': {'name_en': 'Baby Shark', 'category': '동물 캐릭터', 'owner': '더 핑크퐁 컴퍼니'},
    '핑크퐁': {'name_en': 'Pinkfong', 'category': '마스코트', 'owner': '더 핑크퐁 컴퍼니'},
    '뽀로로': {'name_en': 'Pororo', 'category': '동물 캐릭터', 'owner': '아이코닉스'},
    '라바': {'name_en': 'Larva', 'category': '동물 캐릭터', 'owner': 'TUBAn'},
    '펭수': {'name_en': 'Pengsoo', 'category': '동물 캐릭터', 'owner': 'EBS'},
    '올리': {'name_en': 'Ollie', 'category': '동물 캐릭터', 'owner': '더 핑크퐁 컴퍼니'},
    '호기': {'name_en': 'Hogi', 'category': '동물 캐릭터', 'owner': '더 핑크퐁 컴퍼니'},
    '피카츄': {'name_en': 'Pikachu', 'category': '동물 캐릭터', 'owner': 'Nintendo'},
    '헬로키티': {'name_en': 'Hello Kitty', 'category': '마스코트', 'owner': 'Sanrio'},
    '카카오프렌즈': {'name_en': 'Kakao Friends', 'category': '마스코트', 'owner': 'Kakao'},
    '라인프렌즈': {'name_en': 'Line Friends', 'category': '마스코트', 'owner': 'Line'},
    '로보카폴리': {'name_en': 'Robocar Poli', 'category': '로봇 캐릭터', 'owner': 'Roi Visual'},
    '타요': {'name_en': 'Tayo', 'category': '캐릭터', 'owner': 'Iconix'},
    '콩순이': {'name_en': 'Kongsuni', 'category': '캐릭터', 'owner': 'Young Toys'},
    '또봇': {'name_en': 'Tobot', 'category': '로봇 캐릭터', 'owner': 'Young Toys'},
}


def is_valid_person_name(name: str) -> bool:
    """
    유효한 인물(사람) 이름인지 검증

    Rules:
    1. 최소 2글자, 최대 10글자
    2. 금지 단어 목록에 없음
    3. 조사로 끝나지 않음
    4. 숫자만 있지 않음
    5. 한글 자음/모음만 있지 않음
    """
    import re

    if not name or len(name) < 2 or len(name) > 10:
        return False

    name_clean = name.strip()
    name_lower = name_clean.lower()

    # 금지 단어 체크
    if name_lower in INVALID_CHARACTER_WORDS:
        debug_log(f"    ❌ 금지 단어로 필터링: '{name}'")
        return False

    # 조사로 끝나는지 체크 (한글 2-4자 + 조사 패턴)
    particle_endings = ['의', '이', '가', '은', '는', '를', '을', '에', '로', '과', '와', '도']
    for particle in particle_endings:
        if name_clean.endswith(particle) and len(name_clean) > 2:
            # 예외: "손정의" 같은 실제 이름 (3글자 성+이름)
            # 이름 패턴: 보통 2-4글자이고 조사가 포함되면 안됨
            # "~의"로 끝나는 3글자 이름은 드물지만 허용 (손정의 등)
            if particle == '의' and len(name_clean) == 3 and re.match(r'^[가-힣]{3}$', name_clean):
                continue  # 허용
            debug_log(f"    ❌ 조사로 끝남: '{name}' (조사: {particle})")
            return False

    # 숫자만 있는지 체크
    if name_clean.isdigit():
        return False

    # 한글 자음/모음만 있는지 체크
    if re.match(r'^[ㄱ-ㅎㅏ-ㅣ]+$', name_clean):
        return False

    # 일반적인 2글자 동사/형용사 어근 필터
    common_verbs = {
        '하는', '되는', '있는', '없는', '같은', '다른', '모든', '각각',
        '새로', '다시', '매우', '정말', '아주', '더욱',
    }
    if name_lower in common_verbs:
        debug_log(f"    ❌ 일반 동사/형용사: '{name}'")
        return False

    # 한글 이름 패턴 확인 (2-4자 완성형 한글)
    if re.match(r'^[가-힣]{2,4}$', name_clean):
        return True

    # 영문 이름 패턴 (First Last)
    if re.match(r'^[A-Z][a-z]+(\s+[A-Z][a-z]+)+$', name_clean):
        return True

    # 아랍/외래 이름 패턴 (공백 포함 한글)
    if re.match(r'^[가-힣]+(\s+[가-힣]+)+$', name_clean):
        return True

    # 그 외 한글 포함 패턴 (5자 이상은 조심)
    if len(name_clean) <= 5 and re.search(r'[가-힣]', name_clean):
        return True

    debug_log(f"    ❌ 패턴 불일치: '{name}'")
    return False


class SceneAnalyzer:
    """AI 기반 씬 분석기"""

    def __init__(
        self,
        provider: str = "anthropic",
        model_name: str = None,
        max_output_tokens: int = None
    ):
        """
        Args:
            provider: AI 제공자 ("anthropic", "google", "gemini", "openai")
            model_name: 정확한 모델 ID (예: "gemini-2.0-flash-exp")
            max_output_tokens: 최대 출력 토큰 수 (None이면 모델 기본값)
        """
        debug_log(f"초기화 시작 (provider={provider}, model={model_name}, max_tokens={max_output_tokens})")

        self.provider = provider
        self.requested_model_name = model_name  # ⭐ 요청된 모델명 저장
        self.max_output_tokens = max_output_tokens or 65536  # ⭐ 기본값 64K
        self.template_manager = get_template_manager()
        self.client = None
        self.gemini_model = None
        self.gemini_available = False

        # 템플릿 매니저 확인
        scene_prompt = self.template_manager.get_prompt("scene_analysis")
        debug_log(f"scene_analysis 프롬프트 길이: {len(scene_prompt)} 문자")

        if not scene_prompt:
            debug_log("경고: scene_analysis 프롬프트가 비어있습니다!")

        # provider별 클라이언트 초기화
        if provider in ("google", "gemini"):
            self._init_gemini()
        elif provider == "anthropic":
            self._init_anthropic()
        elif provider == "openai":
            self._init_openai()
        else:
            # 기본값: Anthropic
            debug_log(f"알 수 없는 provider '{provider}', Anthropic으로 대체")
            self._init_anthropic()

    def _init_anthropic(self):
        """Anthropic 클라이언트 초기화"""
        from anthropic import Anthropic

        if not ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY가 필요합니다. API 관리 페이지에서 설정하세요.")

        self.client = Anthropic(api_key=ANTHROPIC_API_KEY)
        self.provider = "anthropic"
        debug_log("Anthropic 클라이언트 초기화 완료")

    def _init_gemini(self):
        """Google Gemini 클라이언트 초기화"""
        try:
            import google.generativeai as genai

            # API 키 확인 (GOOGLE_API_KEY 또는 GEMINI_API_KEY)
            api_key = GOOGLE_API_KEY or GEMINI_API_KEY
            if not api_key:
                error_msg = "GOOGLE_API_KEY 또는 GEMINI_API_KEY가 필요합니다. API 관리 페이지에서 설정하세요."
                debug_log(f"❌ {error_msg}")
                raise ValueError(error_msg)

            genai.configure(api_key=api_key)

            # ⭐ 요청된 모델명이 있으면 해당 모델 사용
            if self.requested_model_name:
                model_candidates = [self.requested_model_name]
                debug_log(f"📌 요청된 모델 사용: {self.requested_model_name}")
            else:
                # 우선순위대로 모델 시도 (API 버전 변경에 대응)
                model_candidates = [
                    "gemini-2.0-flash-exp",     # 최신 2.0 (무료, 빠름, 64K 출력)
                    "gemini-2.0-flash",         # 2.0 안정
                    "gemini-1.5-flash",         # 1.5 기본
                    "gemini-pro",               # Pro 기본
                ]

            self.gemini_model = None
            self.gemini_model_name = None

            for model_name in model_candidates:
                try:
                    debug_log(f"모델 '{model_name}' 시도 중...")
                    test_model = genai.GenerativeModel(model_name)

                    # 간단한 테스트 호출로 모델 유효성 확인
                    test_response = test_model.generate_content(
                        "Say OK",
                        generation_config={"max_output_tokens": 5}
                    )

                    if test_response and (test_response.text or
                        (hasattr(test_response, 'candidates') and test_response.candidates)):
                        self.gemini_model = test_model
                        self.gemini_model_name = model_name
                        debug_log(f"✅ 모델 '{model_name}' 사용 가능!")
                        break

                except Exception as model_error:
                    debug_log(f"❌ 모델 '{model_name}' 실패: {model_error}")
                    continue

            if self.gemini_model is None:
                raise RuntimeError("사용 가능한 Gemini 모델이 없습니다. API 키를 확인하세요.")

            self.provider = "google"
            self.gemini_available = True
            debug_log(f"✅ Google Gemini 클라이언트 초기화 완료")
            debug_log(f"   📌 모델: {self.gemini_model_name}")
            debug_log(f"   📌 최대 출력 토큰: {self.max_output_tokens:,}")

        except ImportError as e:
            error_msg = """
❌ google-generativeai 패키지가 설치되지 않았습니다.

설치 방법:
  pip install google-generativeai

설치 후 앱을 재시작하세요.
"""
            debug_log(error_msg)
            self.gemini_available = False
            raise ImportError(error_msg) from e

        except Exception as e:
            debug_log(f"❌ Gemini 초기화 실패: {e}")
            self.gemini_available = False
            raise

    def _init_openai(self):
        """OpenAI 클라이언트 초기화"""
        try:
            from openai import OpenAI
            import os

            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY가 필요합니다. API 관리 페이지에서 설정하세요.")

            self.client = OpenAI(api_key=api_key)
            self.provider = "openai"
            debug_log("OpenAI 클라이언트 초기화 완료")

        except ImportError as e:
            error_msg = "openai 패키지가 설치되지 않았습니다. pip install openai"
            debug_log(error_msg)
            raise ImportError(error_msg) from e

    def analyze_script(
        self,
        script: str,
        language: str = "ko",
        template_id: str = "scene_analysis"
    ) -> Dict:
        """
        스크립트를 분석하여 씬, 캐릭터, 연출가이드 추출

        Args:
            script: 전체 스크립트 텍스트
            language: 언어 코드
            template_id: 사용할 프롬프트 템플릿 ID

        Returns:
            {
                "scenes": [...],
                "characters": [...],
                "total_scenes": int,
                "estimated_duration": float
            }
        """
        debug_log(f"analyze_script 시작")
        debug_log(f"  스크립트 길이: {len(script)} 문자")
        debug_log(f"  언어: {language}, 템플릿 ID: {template_id}")

        # 스크립트 검증
        if not script or len(script.strip()) < 10:
            debug_log("오류: 스크립트가 비어있거나 너무 짧습니다")
            return {
                "scenes": [],
                "characters": [],
                "total_scenes": 0,
                "estimated_duration": 0,
                "error": "스크립트가 비어있거나 너무 짧습니다"
            }

        # 템플릿에서 프롬프트 가져오기
        template = self.template_manager.get_template(template_id)
        
        # 템플릿이 없으면 기본값 시도
        if not template and template_id != "scene_analysis":
             debug_log(f"경고: 템플릿 '{template_id}' 없음. 기본값 사용.")
             template = self.template_manager.get_template("scene_analysis")
             
        base_prompt = template.prompt if template else ""

        debug_log(f"  base_prompt 길이: {len(base_prompt)} 문자")
        debug_log(f"  사용 템플릿: {template.name if template else 'Unknown'} ({template_id})")
        debug_log(f"  커스텀 템플릿 사용: {not template.is_default if template else 'N/A'}")

        if not base_prompt:
            debug_log("오류: 프롬프트 템플릿이 비어있습니다")
            return {
                "scenes": [],
                "characters": [],
                "total_scenes": 0,
                "estimated_duration": 0,
                "error": "프롬프트 템플릿이 비어있습니다"
            }

        prompt = f"""{base_prompt}

## 스크립트
{script}

JSON 형식으로만 응답해주세요. 다른 텍스트는 포함하지 마세요."""

        debug_log(f"  최종 프롬프트 길이: {len(prompt)} 문자")
        debug_log(f"  provider: {self.provider}")

        try:
            # provider별 API 호출
            if self.provider == "google":
                # ⭐ finish_reason도 함께 받아서 MAX_TOKENS 시 이어서 생성
                result_text, finish_reason = self._call_gemini_with_status(prompt)

                # ⭐ MAX_TOKENS로 잘린 경우 이어서 생성
                if finish_reason == 2:
                    debug_log("  🔄 MAX_TOKENS 감지 → 이어서 생성 시작")
                    result_text = self._continue_gemini_generation(result_text, script)
            else:
                result_text = self._call_anthropic(prompt)

            debug_log(f"  API 응답 길이: {len(result_text)} 문자")
            debug_log(f"  응답 미리보기: {result_text[:200]}...")

        except Exception as e:
            debug_log(f"API 호출 오류: {e}")
            import traceback
            debug_log(traceback.format_exc())
            return {
                "scenes": [],
                "characters": [],
                "total_scenes": 0,
                "estimated_duration": 0,
                "error": f"API 호출 실패: {str(e)}"
            }

        # JSON 블록 추출
        json_str = result_text
        json_truncated = False

        if "```json" in json_str:
            start = json_str.find("```json") + 7
            end = json_str.rfind("```")
            if end > start:
                json_str = json_str[start:end].strip()
            else:
                # 닫는 ``` 없음 - 잘린 것
                json_str = json_str[start:].strip()
                json_truncated = True
                debug_log("  ⚠️ JSON 블록이 닫히지 않음 (잘림 의심)")
        elif "```" in json_str:
            start = json_str.find("```") + 3
            end = json_str.rfind("```")
            if end > start:
                json_str = json_str[start:end].strip()
            else:
                json_str = json_str[start:].strip()
                json_truncated = True

        try:
            result = json.loads(json_str)
            debug_log(f"  JSON 파싱 성공: 씬 {len(result.get('scenes', []))}개")
            debug_log(f"    persons: {len(result.get('persons', []))}명, characters: {len(result.get('characters', []))}개")

            # === 캐릭터 데이터 정규화 (v2.3: persons + characters 병합) ===
            raw_characters = result.get("characters", [])
            raw_persons = result.get("persons", [])  # v2.3 프롬프트
            result["characters"] = self._normalize_characters(raw_characters, raw_persons)
            debug_log(f"  캐릭터 정규화 완료: {len(result['characters'])}개 (필터링 후)")

            # 🔴 캐릭터가 없으면 씬에서 폴백 추출
            if not result["characters"]:
                debug_log("  ⚠️ 캐릭터가 비어있음! 씬에서 폴백 추출 시도...")
                result["characters"] = self._extract_characters_from_scenes(result.get("scenes", []), script)
                debug_log(f"  📌 폴백 추출 결과: {len(result['characters'])}명")

            # === visual_prompt가 비어있으면 자동 생성 ===
            result["characters"] = self._ensure_visual_prompts(result["characters"], script)
            debug_log(f"  visual_prompt 확인 완료")

            # === 씬 데이터 정규화 ===
            raw_scenes = result.get("scenes", [])
            result["scenes"] = self._normalize_scenes(raw_scenes)

        except json.JSONDecodeError as e:
            debug_log(f"  JSON 파싱 실패: {e}")
            debug_log(f"  파싱 시도한 텍스트 (처음 300자): {json_str[:300]}...")

            # ⭐ JSON 복구 시도
            debug_log("  JSON 복구 시도 중...")
            repaired_json = self._repair_truncated_json(json_str)

            try:
                result = json.loads(repaired_json)
                debug_log(f"  ✅ JSON 복구 성공! 씬 {len(result.get('scenes', []))}개")
                debug_log(f"    persons: {len(result.get('persons', []))}명, characters: {len(result.get('characters', []))}개")

                # 정규화 진행 (v2.3: persons + characters 병합)
                raw_characters = result.get("characters", [])
                raw_persons = result.get("persons", [])
                result["characters"] = self._normalize_characters(raw_characters, raw_persons)

                # 🔴 캐릭터가 없으면 씬에서 폴백 추출
                if not result["characters"]:
                    debug_log("  ⚠️ (복구 후) 캐릭터가 비어있음! 씬에서 폴백 추출 시도...")
                    result["characters"] = self._extract_characters_from_scenes(result.get("scenes", []), script)
                    debug_log(f"  📌 폴백 추출 결과: {len(result['characters'])}명")

                result["characters"] = self._ensure_visual_prompts(result["characters"], script)
                raw_scenes = result.get("scenes", [])
                result["scenes"] = self._normalize_scenes(raw_scenes)

            except json.JSONDecodeError as e2:
                debug_log(f"  ❌ JSON 복구 후에도 파싱 실패: {e2}")
                # 파싱 실패 시 기본 구조 반환
                result = {
                    "scenes": [],
                    "characters": [],
                    "total_scenes": 0,
                    "estimated_duration": 0,
                    "error": f"JSON 파싱 실패: {str(e)}",
                    "raw_response": json_str[:500]
                }

        # 🔴 스크립트 보존 검증 (Problem 51 해결)
        if result.get('scenes'):
            debug_log("  📋 스크립트 보존 검증 시작...")
            result = self._validate_script_preservation(script, result)

            # 검증 결과 로깅
            validation = result.get('_script_validation', {})
            if validation.get('warning_count', 0) > 0:
                debug_log(f"  ⚠️ AI가 {validation['warning_count']}개 씬의 스크립트를 변조함")
                if validation.get('modified_count', 0) > 0:
                    debug_log(f"     → {validation['modified_count']}개 자동 수정됨")

        return result

    def _normalize_characters(self, raw_characters: list, raw_persons: list = None) -> list:
        """
        캐릭터 배열 정규화 (v2.3 - Problem 49 개선)

        - 문자열 배열이면 딕셔너리 배열로 변환
        - persons 배열과 characters 배열 병합
        - 잘못된 이름 필터링
        """
        if not raw_characters and not raw_persons:
            return []

        normalized = []
        seen_names = set()

        # persons 배열 처리 (v2.3 프롬프트)
        if raw_persons:
            debug_log(f"  persons 배열 처리: {len(raw_persons)}명")
            for person in raw_persons:
                if isinstance(person, str):
                    name = person.strip()
                elif isinstance(person, dict):
                    name = person.get("name", person.get("name_ko", "")).strip()
                else:
                    continue

                # 🔴 유효성 검증
                if not name or name in seen_names:
                    continue
                if not is_valid_person_name(name):
                    debug_log(f"    ❌ 잘못된 인물 필터링: '{name}'")
                    continue

                seen_names.add(name)

                if isinstance(person, dict):
                    normalized.append({
                        "name": name,
                        "name_ko": person.get("name_ko", name),
                        "name_en": person.get("name_en", ""),
                        "type": "person",
                        "role": person.get("role", person.get("position", "등장인물")),
                        "company": person.get("company", ""),
                        "description": person.get("description", ""),
                        "appearance": person.get("appearance", ""),
                        "nationality": person.get("nationality", ""),
                        "era": person.get("era", person.get("age_era", "")),
                        "character_prompt": person.get("character_prompt", person.get("visual_prompt", "")),
                        "visual_prompt": person.get("visual_prompt", person.get("character_prompt", "")),
                        "appearance_scenes": person.get("appearance_scenes", [])
                    })
                else:
                    normalized.append({
                        "name": name,
                        "name_ko": name,
                        "name_en": "",
                        "type": "person",
                        "role": "등장인물",
                        "description": "",
                        "appearance": "",
                        "nationality": "",
                        "era": "",
                        "character_prompt": "",
                        "visual_prompt": "",
                        "appearance_scenes": []
                    })

        # characters 배열 처리 (캐릭터 IP 포함)
        for char in raw_characters:
            if isinstance(char, str):
                name = char.strip()
                char_type = "character_ip" if name in KNOWN_CHARACTER_IPS else "person"
            elif isinstance(char, dict):
                name = char.get("name", char.get("name_ko", "")).strip()
                char_type = char.get("type", "person")
            else:
                continue

            # 중복 체크
            if not name or name in seen_names:
                continue

            # 캐릭터 IP인지 확인
            is_character_ip = (
                name in KNOWN_CHARACTER_IPS or
                char_type == "character_ip" or
                (isinstance(char, dict) and char.get("category"))
            )

            # 인물이면 유효성 검증
            if not is_character_ip and not is_valid_person_name(name):
                debug_log(f"    ❌ 잘못된 캐릭터 필터링: '{name}'")
                continue

            seen_names.add(name)

            if isinstance(char, dict):
                normalized.append({
                    "name": name,
                    "name_ko": char.get("name_ko", name),
                    "name_en": char.get("name_en", ""),
                    "type": char_type,
                    "category": char.get("category", ""),
                    "owner_company": char.get("owner_company", ""),
                    "role": char.get("role", "캐릭터" if is_character_ip else "등장인물"),
                    "description": char.get("description", ""),
                    "appearance": char.get("appearance", ""),
                    "nationality": char.get("nationality", ""),
                    "era": char.get("era", char.get("age_era", "")),
                    "character_prompt": char.get("character_prompt", char.get("visual_prompt", char.get("prompt", ""))),
                    "visual_prompt": char.get("visual_prompt", char.get("character_prompt", char.get("prompt", ""))),
                    "appearance_scenes": char.get("appearance_scenes", [])
                })
            else:
                # 알려진 캐릭터 IP면 정보 추가
                if name in KNOWN_CHARACTER_IPS:
                    ip_info = KNOWN_CHARACTER_IPS[name]
                    normalized.append({
                        "name": name,
                        "name_ko": name,
                        "name_en": ip_info.get("name_en", ""),
                        "type": "character_ip",
                        "category": ip_info.get("category", ""),
                        "owner_company": ip_info.get("owner", ""),
                        "role": "캐릭터 IP",
                        "description": f"{ip_info.get('category', '')} - {ip_info.get('owner', '')}",
                        "appearance": "",
                        "nationality": "",
                        "era": "",
                        "character_prompt": "",
                        "visual_prompt": "",
                        "appearance_scenes": []
                    })
                else:
                    normalized.append({
                        "name": name,
                        "name_ko": name,
                        "name_en": "",
                        "type": "person",
                        "role": "등장인물",
                        "description": "",
                        "appearance": "",
                        "nationality": "",
                        "era": "",
                        "character_prompt": "",
                        "visual_prompt": "",
                        "appearance_scenes": []
                    })

        debug_log(f"  정규화 완료: {len(normalized)}개 (필터링 후)")
        return normalized

    def _extract_characters_from_scenes(self, scenes: list, script: str = "") -> list:
        """
        씬 데이터에서 인물 + 캐릭터 IP 폴백 추출 (Problem 49 개선)

        AI가 characters/persons 배열을 비워두거나 누락했을 때
        각 씬의 characters 필드와 스크립트에서 추출

        Args:
            scenes: 씬 배열
            script: 원본 스크립트 (추가 컨텍스트용)

        Returns:
            추출된 캐릭터 딕셔너리 배열 (persons + character_ips)
        """
        import re

        debug_log("  🔍 씬에서 캐릭터 폴백 추출 시작 (v2 - 개선된 필터링)...")

        # 씬에서 수집된 이름들
        person_names = set()
        person_scenes = {}  # 인물 → 등장 씬 목록

        # ============================================================
        # 1. 각 씬의 characters/persons 필드에서 추출
        # ============================================================
        for scene in scenes:
            scene_id = scene.get("scene_id", 0)

            # characters 필드
            for char in scene.get("characters", []):
                if isinstance(char, str) and char.strip():
                    name = char.strip()
                    if is_valid_person_name(name):
                        person_names.add(name)
                        if name not in person_scenes:
                            person_scenes[name] = []
                        person_scenes[name].append(scene_id)
                elif isinstance(char, dict):
                    name = char.get("name", char.get("name_ko", "")).strip()
                    if name and is_valid_person_name(name):
                        person_names.add(name)
                        if name not in person_scenes:
                            person_scenes[name] = []
                        person_scenes[name].append(scene_id)

            # persons 필드 (새 프롬프트 v2.3)
            for person in scene.get("persons", []):
                if isinstance(person, str) and person.strip():
                    name = person.strip()
                    if is_valid_person_name(name):
                        person_names.add(name)
                        if name not in person_scenes:
                            person_scenes[name] = []
                        person_scenes[name].append(scene_id)

        debug_log(f"    씬 필드에서 유효한 인물 {len(person_names)}명: {list(person_names)[:5]}")

        # ============================================================
        # 2. 스크립트에서 인물 이름 패턴 추출 (폴백)
        # ============================================================
        if not person_names and script:
            debug_log("    씬에서 인물 없음, 스크립트 패턴 분석 시도...")

            # 패턴 1: 한글 이름 + 직책 (예: "김민석 대표", "홍길동 CEO")
            pattern1 = r'([가-힣]{2,4})\s*(대표|회장|사장|이사|CEO|CFO|CTO|창업자|설립자|씨|님)'
            for match in re.finditer(pattern1, script):
                name = match.group(1).strip()
                if is_valid_person_name(name):
                    person_names.add(name)
                    debug_log(f"      ✅ 패턴1 추출: '{name}' (+ {match.group(2)})")

            # 패턴 2: 직책 + 한글 이름 (예: "대표 김민석", "창업자 홍길동")
            pattern2 = r'(대표|회장|사장|이사|CEO|창업자|설립자)\s+([가-힣]{2,4})(?=[이가은는을를\s,.])'
            for match in re.finditer(pattern2, script):
                name = match.group(2).strip()
                if is_valid_person_name(name):
                    person_names.add(name)
                    debug_log(f"      ✅ 패턴2 추출: '{name}' ({match.group(1)} +)")

            # 패턴 3: 외국 이름 (예: "Elon Musk", "Tim Cook")
            pattern3 = r'([A-Z][a-z]+)\s+([A-Z][a-z]+)'
            for match in re.finditer(pattern3, script):
                name = f"{match.group(1)} {match.group(2)}"
                person_names.add(name)
                debug_log(f"      ✅ 패턴3 추출: '{name}'")

            # 패턴 4: 아랍/외래 이름 (예: "무함마드 빈 살만", "자말 카슈끄지")
            pattern4 = r'([가-힣]{2,5})\s+([가-힣]{1,3})\s+([가-힣]{2,4})'
            for match in re.finditer(pattern4, script):
                name = f"{match.group(1)} {match.group(2)} {match.group(3)}"
                # 국가명 등 제외
                if not any(kw in name for kw in ['사우디', '아라비아', '대한민국']):
                    person_names.add(name)
                    debug_log(f"      ✅ 패턴4 추출: '{name}'")

            debug_log(f"    스크립트 패턴에서 {len(person_names)}명 발견: {list(person_names)[:5]}")

        # ============================================================
        # 3. 캐릭터 IP 추출 (동물, 마스코트 등)
        # ============================================================
        character_ips = []
        found_ips = set()

        # 알려진 캐릭터 IP 검색
        for ip_name, ip_info in KNOWN_CHARACTER_IPS.items():
            if ip_name in script and ip_name not in found_ips:
                found_ips.add(ip_name)
                # 등장 씬 찾기
                ip_scenes = []
                for scene in scenes:
                    scene_text = scene.get("script_text", "")
                    if ip_name in scene_text:
                        ip_scenes.append(scene.get("scene_id", 0))

                character_ips.append({
                    "name": ip_name,
                    "name_ko": ip_name,
                    "name_en": ip_info.get('name_en', ''),
                    "type": "character_ip",
                    "category": ip_info.get('category', '캐릭터'),
                    "owner_company": ip_info.get('owner', ''),
                    "role": "캐릭터 IP",
                    "description": f"{ip_info.get('category', '캐릭터')} - {ip_info.get('owner', '')}",
                    "visual_prompt": self._generate_character_ip_prompt(ip_name, ip_info),
                    "appearance_scenes": ip_scenes
                })
                debug_log(f"    ✅ 캐릭터 IP 발견: '{ip_name}' ({ip_info.get('category', '')})")

        # 패턴 기반 캐릭터 IP 추출 (~캐릭터, ~마스코트)
        ip_pattern = r'([가-힣a-zA-Z]{2,10})\s*(캐릭터|마스코트)'
        for match in re.finditer(ip_pattern, script):
            name = match.group(1).strip()
            if name not in found_ips and name not in INVALID_CHARACTER_WORDS:
                if len(name) >= 2 and not is_valid_person_name(name):  # 사람 이름 아닌 것만
                    found_ips.add(name)
                    character_ips.append({
                        "name": name,
                        "name_ko": name,
                        "name_en": "",
                        "type": "character_ip",
                        "category": match.group(2),
                        "role": match.group(2),
                        "description": f"스크립트에서 추출된 {match.group(2)}",
                        "visual_prompt": "",
                        "appearance_scenes": []
                    })
                    debug_log(f"    ✅ 패턴 캐릭터 IP: '{name}' ({match.group(2)})")

        debug_log(f"    캐릭터 IP 총 {len(character_ips)}개 발견")

        # ============================================================
        # 4. 인물 객체 생성
        # ============================================================
        characters = []

        for name in person_names:
            # 역할 추론
            role = "등장인물"
            name_context = script[:3000] if script else ""

            # 컨텍스트에서 역할 추론
            name_patterns = [
                (f"{name}\\s*대표", "대표"),
                (f"{name}\\s*CEO", "CEO"),
                (f"{name}\\s*회장", "회장"),
                (f"{name}\\s*창업", "창업자"),
                (f"{name}\\s*설립", "창업자"),
                (f"창업자\\s*{name}", "창업자"),
                (f"대표\\s*{name}", "대표"),
            ]
            for pattern, detected_role in name_patterns:
                if re.search(pattern, name_context, re.IGNORECASE):
                    role = detected_role
                    break

            char = {
                "name": name,
                "name_ko": name,
                "name_en": "",
                "type": "person",
                "role": role,
                "description": f"스크립트에서 추출된 인물: {name} ({role})",
                "appearance": "",
                "nationality": "",
                "era": "",
                "character_prompt": "",
                "visual_prompt": "",
                "appearance_scenes": person_scenes.get(name, [])
            }
            characters.append(char)

        # 캐릭터 IP도 characters 배열에 추가
        characters.extend(character_ips)

        debug_log(f"    최종 폴백: 인물 {len(person_names)}명 + 캐릭터 IP {len(character_ips)}개 = {len(characters)}개")
        return characters

    def _generate_character_ip_prompt(self, name: str, info: dict) -> str:
        """캐릭터 IP용 visual_prompt 생성"""
        category = info.get('category', '')
        name_en = info.get('name_en', name)

        prompts = {
            '아기상어': "Cute blue baby shark character, cartoon style, big round friendly eyes, small dorsal fin, happy wide smile, underwater ocean background with bubbles, bright vibrant blue and yellow colors, kawaii chibi aesthetic, no text, no letters, no words",
            '핑크퐁': "Cute pink fox mascot character, bright magenta and coral pink fur, big sparkling round eyes, small cute nose, friendly cheerful smile, fluffy tail, cartoon kawaii style, no text, no letters, no words",
            '뽀로로': "Cute little penguin character in aviator helmet and goggles, blue and white colors, round body, friendly eyes, cartoon style, no text, no letters, no words",
            '펭수': "Tall penguin character, EBS mascot, wearing blue hoodie, expressive eyes, quirky personality, cartoon style, no text, no letters, no words",
        }

        if name in prompts:
            return prompts[name]

        # 기본 템플릿
        if '동물' in category:
            return f"Cute {name_en} animal character, cartoon style, friendly expression, bright vibrant colors, kawaii aesthetic, no text, no letters, no words"
        elif '마스코트' in category:
            return f"Cute {name_en} mascot character, brand mascot style, friendly smile, bright colors, cartoon aesthetic, no text, no letters, no words"
        else:
            return f"{name_en} character, cartoon style, friendly appearance, no text, no letters, no words"

    def _normalize_scenes(self, raw_scenes: list) -> list:
        """
        씬 배열 정규화

        - 씬 내부의 characters 필드 처리
        - 비디오 프롬프트 기본값 생성
        - 글자 수 검증 로그
        """
        if not raw_scenes:
            return []

        normalized = []

        for scene in raw_scenes:
            if not isinstance(scene, dict):
                continue

            # 씬 내부의 characters도 문자열 배열일 수 있음
            scene_characters = scene.get("characters", [])

            # 캐릭터 이름만 문자열 배열로 정규화
            if scene_characters:
                if all(isinstance(c, str) for c in scene_characters):
                    # 이미 문자열 배열 - OK
                    pass
                elif scene_characters and isinstance(scene_characters[0], dict):
                    # 딕셔너리 배열 → 이름만 추출
                    scene["characters"] = [
                        c.get("name", c.get("name_ko", str(c)))
                        for c in scene_characters
                    ]

            # === 비디오 프롬프트 정규화 ===
            # video_prompt_character가 없거나 N/A면 기본값 생성
            video_char = scene.get("video_prompt_character", "")
            if not video_char or video_char == "N/A":
                scene["video_prompt_character"] = self._generate_default_video_prompt_character(scene)
                debug_log(f"  씬 {scene.get('scene_id', '?')}: video_prompt_character 자동 생성")

            # video_prompt_full이 없거나 N/A면 기본값 생성
            video_full = scene.get("video_prompt_full", "")
            if not video_full or video_full == "N/A":
                scene["video_prompt_full"] = self._generate_default_video_prompt_full(scene)
                debug_log(f"  씬 {scene.get('scene_id', '?')}: video_prompt_full 자동 생성")

            # === 글자 수 검증 ===
            script_text = scene.get("script_text", "")
            char_count = len(script_text)
            scene["char_count"] = char_count  # 글자 수 필드 추가

            if char_count > 250:
                debug_log(f"  ⚠️ 씬 {scene.get('scene_id', '?')}: 글자 수 {char_count}자 (권장 250자 초과)")

            normalized.append(scene)

        return normalized

    def _validate_script_preservation(self, original_script: str, analysis_result: dict) -> dict:
        """
        분석 결과의 script_text가 원본 스크립트에 실제로 존재하는지 검증

        🔴 핵심: AI가 창작한 문장을 감지하고 수정

        Args:
            original_script: 원본 스크립트
            analysis_result: 분석 결과

        Returns:
            검증/수정된 분석 결과
        """
        scenes = analysis_result.get('scenes', [])
        if not scenes or not original_script:
            return analysis_result

        # 원본 스크립트 정규화 (비교용)
        original_normalized = original_script.lower().replace('\n', ' ').replace('  ', ' ').strip()

        validated_scenes = []
        modified_count = 0
        warning_count = 0

        for scene in scenes:
            script_text = scene.get('script_text', '')

            if not script_text:
                validated_scenes.append(scene)
                continue

            # script_text 정규화
            script_normalized = script_text.lower().replace('\n', ' ').replace('  ', ' ').strip()

            # 원본에 존재하는지 확인 (부분 일치)
            if script_normalized in original_normalized:
                # ✅ 원본에 존재 - 그대로 사용
                validated_scenes.append(scene)
            else:
                # ❌ 원본에 없음 - AI가 창작한 문장
                scene_id = scene.get('scene_id', '?')
                debug_log(f"  ⚠️ 씬 {scene_id}: 원본에 없는 문장 감지!")
                debug_log(f"     AI 생성: {script_text[:80]}...")
                warning_count += 1

                # 유사한 문장 찾기 시도
                matched_text = self._find_similar_text_in_script(original_script, script_text)

                if matched_text:
                    debug_log(f"     → 유사 문장으로 대체: {matched_text[:80]}...")
                    scene['script_text'] = matched_text
                    scene['_was_corrected'] = True
                    scene['_original_ai_text'] = script_text
                    modified_count += 1
                else:
                    # 찾지 못하면 경고만 (빈 문장 방지)
                    debug_log(f"     → 유사 문장 없음, 원본 유지 (수동 확인 필요)")
                    scene['_verification_failed'] = True

                validated_scenes.append(scene)

        # 결과 업데이트
        analysis_result['scenes'] = validated_scenes

        # 검증 메타데이터 추가
        analysis_result['_script_validation'] = {
            'total_scenes': len(scenes),
            'modified_count': modified_count,
            'warning_count': warning_count,
            'all_verified': warning_count == 0
        }

        if modified_count > 0:
            debug_log(f"  ⚠️ {modified_count}개 씬의 script_text가 수정됨")
        if warning_count > 0:
            debug_log(f"  ⚠️ {warning_count}개 씬에서 원본에 없는 문장 감지됨")
        if warning_count == 0:
            debug_log(f"  ✅ 모든 씬의 script_text가 원본과 일치함")

        return analysis_result

    def _find_similar_text_in_script(self, original_script: str, target_text: str, threshold: float = 0.6) -> str:
        """
        원본 스크립트에서 target_text와 유사한 문장 찾기

        Args:
            original_script: 원본 스크립트
            target_text: 찾을 텍스트
            threshold: 유사도 임계값

        Returns:
            유사한 원본 문장 또는 빈 문자열
        """
        from difflib import SequenceMatcher
        import re

        # 원본을 문장 단위로 분할
        sentences = re.split(r'[.!?]\s*', original_script)
        sentences = [s.strip() for s in sentences if s.strip() and len(s.strip()) > 5]

        # 추가로 줄바꿈 단위 분할도 포함
        lines = original_script.split('\n')
        lines = [l.strip() for l in lines if l.strip() and len(l.strip()) > 10]

        all_candidates = list(set(sentences + lines))

        best_match = None
        best_ratio = 0

        target_lower = target_text.lower().strip()

        for candidate in all_candidates:
            candidate_lower = candidate.lower().strip()

            # 포함 관계 확인
            if target_lower in candidate_lower or candidate_lower in target_lower:
                return candidate

            # 유사도 계산
            ratio = SequenceMatcher(None, target_lower, candidate_lower).ratio()
            if ratio > best_ratio and ratio >= threshold:
                best_ratio = ratio
                best_match = candidate

        return best_match if best_match else ""

    def analyze_script_chunked(
        self,
        script: str,
        language: str = "ko",
        template_id: str = "scene_analysis",
        chunk_size: int = 2500
    ) -> Dict:
        """
        긴 스크립트를 청크로 나누어 분석

        MAX_TOKENS 문제를 근본적으로 해결하는 방법.
        스크립트가 chunk_size보다 작으면 일반 analyze_script 사용.

        Args:
            script: 전체 스크립트 텍스트
            language: 언어 코드
            template_id: 사용할 프롬프트 템플릿 ID
            chunk_size: 청크당 최대 글자 수

        Returns:
            통합된 분석 결과
        """
        # 짧은 스크립트는 일반 처리
        if len(script) < chunk_size:
            debug_log(f"  스크립트가 짧음 ({len(script)}자) - 일반 분석 사용")
            return self.analyze_script(script, language, template_id)

        debug_log(f"[SceneAnalyzer] 📄 긴 스크립트 감지 ({len(script)}자) - 청크 분할 처리")

        # 스크립트를 청크로 분할 (문장 단위)
        chunks = self._split_script_into_chunks(script, chunk_size)
        debug_log(f"  → {len(chunks)}개 청크로 분할")

        all_scenes = []
        all_persons = []
        all_characters = []
        all_companies = []
        scene_id_offset = 0

        for i, chunk in enumerate(chunks):
            debug_log(f"  🔄 청크 {i+1}/{len(chunks)} 분석 중... ({len(chunk)}자)")

            # 청크 분석
            chunk_result = self._analyze_single_chunk(
                chunk_text=chunk,
                chunk_index=i,
                total_chunks=len(chunks),
                language=language,
                template_id=template_id,
                full_script=script  # 원본 전달 (검증용)
            )

            if chunk_result and not chunk_result.get('error'):
                # 씬 ID 조정 및 병합
                for scene in chunk_result.get('scenes', []):
                    original_id = scene.get('scene_id', 0)
                    scene['scene_id'] = original_id + scene_id_offset
                    scene['_chunk_index'] = i
                    all_scenes.append(scene)

                scene_id_offset = len(all_scenes)

                # 인물/캐릭터/회사 병합 (중복 제거)
                for person in chunk_result.get('persons', []):
                    name = person.get('name', '')
                    if name and not any(p.get('name') == name for p in all_persons):
                        all_persons.append(person)

                for char in chunk_result.get('characters', []):
                    name = char.get('name', '')
                    if name and not any(c.get('name') == name for c in all_characters):
                        all_characters.append(char)

                for company in chunk_result.get('companies', []):
                    name = company.get('name', '')
                    if name and not any(c.get('name') == name for c in all_companies):
                        all_companies.append(company)

        # 최종 결과 조합
        final_result = {
            'metadata': {
                'processed_in_chunks': True,
                'total_chunks': len(chunks)
            },
            'scenes': all_scenes,
            'persons': all_persons,
            'characters': all_characters,
            'companies': all_companies,
            'summary': {
                'total_scenes': len(all_scenes),
                'total_persons': len(all_persons),
                'total_characters': len(all_characters),
                'total_companies': len(all_companies)
            }
        }

        # 🔴 최종 검증
        debug_log("  📋 청크 분석 결과 최종 검증...")
        final_result = self._validate_script_preservation(script, final_result)

        debug_log(f"  ✅ 청크 분석 완료: 씬 {len(all_scenes)}개, 캐릭터 {len(all_characters)}개")

        return final_result

    def _split_script_into_chunks(self, script: str, chunk_size: int = 2500) -> list:
        """
        스크립트를 문장 단위로 청크 분할

        문장 중간에서 끊기지 않도록 함.
        """
        import re

        # 문장 분할 (마침표, 물음표, 느낌표 후)
        sentences = re.split(r'(?<=[.!?])\s+', script)

        chunks = []
        current_chunk = ""

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            # 현재 청크에 문장 추가 가능 여부
            if len(current_chunk) + len(sentence) + 1 < chunk_size:
                current_chunk += (" " if current_chunk else "") + sentence
            else:
                # 현재 청크 저장
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = sentence

        # 마지막 청크
        if current_chunk:
            chunks.append(current_chunk.strip())

        return chunks

    def _analyze_single_chunk(
        self,
        chunk_text: str,
        chunk_index: int,
        total_chunks: int,
        language: str,
        template_id: str,
        full_script: str
    ) -> dict:
        """
        단일 청크 분석

        Args:
            chunk_text: 청크 텍스트
            chunk_index: 청크 인덱스
            total_chunks: 전체 청크 수
            language: 언어
            template_id: 템플릿 ID
            full_script: 전체 스크립트 (검증용)

        Returns:
            청크 분석 결과
        """
        # 청크용 프롬프트 (간소화 버전)
        chunk_prompt = f"""다음 스크립트 청크를 분석하세요. (청크 {chunk_index + 1}/{total_chunks})

🔴🔴🔴 [CRITICAL] 스크립트 원본 보존 절대 규칙 🔴🔴🔴

⚠️ 가장 중요한 규칙: script_text에는 아래 스크립트에 있는 문장만 사용하세요!

**🚫 절대 금지:**
- 스크립트에 없는 문장 만들기 ❌
- "구독과 좋아요 부탁드립니다" 같은 일반 아웃트로 추가 ❌
- 원본 문장을 다르게 바꾸기 ❌

=== 스크립트 청크 (이 내용만 사용!) ===
{chunk_text}
=== 스크립트 끝 ===

JSON 형식으로 응답하세요:
```json
{{
  "scenes": [
    {{
      "scene_id": 1,
      "script_text": "원본 스크립트 그대로 복사 (절대 수정 금지!)",
      "char_count": 100,
      "duration_estimate": 8,
      "persons": [],
      "characters": [],
      "mood": "분위기",
      "image_prompt_en": "..., no text, no letters"
    }}
  ],
  "persons": [],
  "characters": [],
  "companies": []
}}
```

⚠️ script_text에는 위 스크립트의 문장만 그대로 사용하세요.
⚠️ 스크립트에 없는 문장을 만들어내면 안됩니다!
JSON 형식으로만 응답해주세요."""

        try:
            if self.provider == "google":
                result_text, finish_reason = self._call_gemini_with_status(chunk_prompt)

                # MAX_TOKENS 처리
                if finish_reason == 2:
                    debug_log(f"    청크 {chunk_index + 1}: MAX_TOKENS - 이어서 생성")
                    result_text = self._continue_gemini_generation(result_text, chunk_text)
            else:
                result_text = self._call_anthropic(chunk_prompt)

            # JSON 파싱
            json_str = result_text
            if "```json" in json_str:
                start = json_str.find("```json") + 7
                end = json_str.rfind("```")
                json_str = json_str[start:end].strip() if end > start else json_str[start:].strip()
            elif "```" in json_str:
                start = json_str.find("```") + 3
                end = json_str.rfind("```")
                json_str = json_str[start:end].strip() if end > start else json_str[start:].strip()

            return json.loads(json_str)

        except Exception as e:
            debug_log(f"    청크 {chunk_index + 1} 분석 오류: {e}")
            return {'error': str(e), 'scenes': [], 'characters': []}

    def _repair_truncated_json(self, json_str: str) -> str:
        """
        잘린 JSON 복구 시도

        Gemini가 출력 토큰 제한으로 JSON을 완성하지 못한 경우,
        최대한 복구를 시도합니다.
        """

        # 1. 이미 유효한 JSON이면 그대로 반환
        try:
            json.loads(json_str)
            return json_str
        except:
            pass

        debug_log(f"  JSON 복구 시도 중... (길이: {len(json_str)})")

        repaired = json_str

        # 2. 열린 문자열 닫기 (Unterminated string 해결)
        in_string = False
        escape_next = False

        for char in repaired:
            if escape_next:
                escape_next = False
                continue
            if char == '\\':
                escape_next = True
                continue
            if char == '"':
                in_string = not in_string

        # 문자열이 열린 상태로 끝났으면 닫기
        if in_string:
            repaired = repaired + '"'
            debug_log("  열린 문자열 닫음")

        # 3. 마지막 완전한 씬/객체 찾기
        # scenes 배열 내에서 마지막 완전한 객체 위치 찾기
        last_complete = repaired.rfind('},')
        if last_complete == -1:
            last_complete = repaired.rfind('}')

        if last_complete > 0 and last_complete < len(repaired) - 1:
            # 마지막 완전한 객체까지만 사용
            repaired = repaired[:last_complete + 1]
            debug_log(f"  마지막 완전한 객체까지 자름 (위치: {last_complete})")

        # 4. 열린 배열/객체 닫기
        open_braces = repaired.count('{') - repaired.count('}')
        open_brackets = repaired.count('[') - repaired.count(']')

        # 배열 먼저 닫고, 객체 닫기
        if open_brackets > 0:
            repaired = repaired + (']' * open_brackets)
            debug_log(f"  ] {open_brackets}개 추가")
        if open_braces > 0:
            repaired = repaired + ('}' * open_braces)
            debug_log(f"  }} {open_braces}개 추가")

        # 5. 검증
        try:
            json.loads(repaired)
            debug_log("  ✅ JSON 복구 성공!")
            return repaired
        except json.JSONDecodeError as e:
            debug_log(f"  ❌ 1차 복구 실패: {e}")

        # 6. 더 공격적인 복구 - scenes 배열만 추출 시도
        return self._extract_partial_scenes(json_str)

    def _extract_partial_scenes(self, json_str: str) -> str:
        """
        부분적으로 씬만 추출하여 유효한 JSON 생성
        """
        import re

        debug_log("  부분 씬 추출 시도...")

        # scenes 배열 시작 위치 찾기
        scenes_start = json_str.find('"scenes"')
        if scenes_start == -1:
            debug_log("  scenes 배열을 찾을 수 없음")
            return '{"scenes": [], "characters": []}'

        # 각 씬 객체 추출 (정규식으로)
        # scene_id가 있는 객체 찾기
        scene_pattern = r'\{\s*"scene_id"\s*:\s*(\d+)[^}]*?"script_text"\s*:\s*"[^"]*"[^}]*?\}'

        scenes = []
        for match in re.finditer(scene_pattern, json_str, re.DOTALL):
            try:
                scene_str = match.group(0)
                # 완전한 객체인지 확인
                if scene_str.count('{') == scene_str.count('}'):
                    scene = json.loads(scene_str)
                    scenes.append(scene)
            except:
                continue

        if scenes:
            debug_log(f"  부분 추출 성공: {len(scenes)}개 씬 발견")
            return json.dumps({
                "scenes": scenes,
                "characters": []
            }, ensure_ascii=False)

        debug_log("  부분 추출 실패")
        return '{"scenes": [], "characters": []}'

    def _generate_default_video_prompt_character(self, scene: dict) -> str:
        """기본 캐릭터 비디오 프롬프트 생성"""
        mood = scene.get("mood", "neutral")

        mood_prompts = {
            "긴장감": "Serious expression, intense eye contact, measured breathing, subtle tension in facial muscles, mouth moving naturally while speaking",
            "긴장": "Serious expression, intense eye contact, measured breathing, subtle tension in facial muscles, mouth moving naturally while speaking",
            "슬픔": "Sorrowful expression, eyes glistening, slight trembling of lips, looking down occasionally, speaking softly",
            "분노": "Angry expression, furrowed brows, tight jaw, intense gaze, controlled breathing, emphatic speech",
            "기쁨": "Happy expression, warm smile, bright eyes, relaxed facial muscles, enthusiastic speaking",
            "진지함": "Serious focused expression, thoughtful eye movements, measured speaking pace, subtle nods",
            "설명적": "Engaged expression, eyebrows moving expressively, clear articulation, occasional hand gestures",
            "역사적": "Dignified expression, steady gaze, measured speaking, scholarly demeanor",
            "비판적": "Critical expression, raised eyebrow, intense gaze, deliberate speaking pace",
            "억압적": "Stern expression, tight-lipped, cold gaze, authoritative tone",
            "권위적": "Authoritative expression, confident posture, commanding voice, powerful presence"
        }

        return mood_prompts.get(mood, "Calm expression, natural eye blinks, subtle head movements, mouth moving naturally while speaking")

    def _generate_default_video_prompt_full(self, scene: dict) -> str:
        """기본 전체 비디오 프롬프트 생성"""
        camera = scene.get("camera_suggestion", "medium shot")
        mood = scene.get("mood", "neutral")

        # 카메라 움직임 매핑
        camera_motion = "steady shot"
        if "줌인" in camera or "zoom in" in camera.lower():
            camera_motion = "camera slowly zooms in"
        elif "줌아웃" in camera or "zoom out" in camera.lower():
            camera_motion = "camera slowly zooms out"
        elif "패닝" in camera or "pan" in camera.lower():
            camera_motion = "camera pans across the scene"
        elif "전환" in camera:
            camera_motion = "smooth transition"
        else:
            camera_motion = "camera holds steady with subtle movement"

        return f"{camera_motion}, character speaking with natural gestures, subtle background movement, atmospheric lighting matching {mood} mood"

    def _ensure_visual_prompts(self, characters: list, script: str = "") -> list:
        """
        visual_prompt가 비어있는 캐릭터에 대해 기본 프롬프트 생성

        Args:
            characters: 정규화된 캐릭터 리스트
            script: 컨텍스트용 스크립트

        Returns:
            visual_prompt가 채워진 캐릭터 리스트
        """
        if not characters:
            return characters

        script_lower = script[:1000].lower() if script else ""

        for char in characters:
            # visual_prompt와 character_prompt 모두 확인
            existing_prompt = char.get("visual_prompt") or char.get("character_prompt") or ""

            if not existing_prompt.strip():
                name = char.get("name", "")
                description = char.get("description", "")

                debug_log(f"  '{name}' visual_prompt 자동 생성 중...")
                char["visual_prompt"] = self._generate_fallback_visual_prompt(
                    name, description, script_lower
                )
                char["character_prompt"] = char["visual_prompt"]
                debug_log(f"    생성됨: {char['visual_prompt'][:60]}...")

        return characters

    def _generate_fallback_visual_prompt(self, name: str, description: str, script_context: str) -> str:
        """
        규칙 기반 폴백 visual_prompt 생성

        캐릭터 이름과 컨텍스트를 분석하여 기본 프롬프트 생성
        """
        prompt_parts = []

        # 모든 텍스트를 소문자로 변환하여 검색
        name_lower = name.lower()
        desc_lower = description.lower()
        context = f"{name_lower} {desc_lower} {script_context}"

        # === 중동/아랍 관련 ===
        arab_keywords = ["사우디", "아랍", "이슬람", "무함마드", "빈 살만", "왕세자", "왕가", "메카", "카슈크지", "khashoggi", "saudi", "arab"]
        if any(kw in context for kw in arab_keywords):
            if "왕세자" in name or "왕" in name or "빈 살만" in name or "prince" in name_lower:
                prompt_parts.append("Saudi Arabian royal figure, early 30s, clean-shaven with trimmed goatee, wearing traditional white thobe with gold-trimmed bisht cloak, red-checkered keffiyeh headpiece, authoritative posture")
            elif "카슈크지" in name or "khashoggi" in name_lower or "기자" in desc_lower or "언론" in desc_lower:
                prompt_parts.append("Middle Eastern man, late 50s, salt-and-pepper beard neatly trimmed, glasses with thin metal frames, wearing dark gray business suit, professional journalist appearance, serious expression")
            elif "순례" in name or "신도" in name:
                prompt_parts.append("Group of Muslim pilgrims, diverse ages, wearing white ihram garments, reverent expressions")
            else:
                prompt_parts.append("Middle Eastern person, traditional Arab appearance, dignified posture")

        # === 고대 이집트 ===
        elif any(kw in context for kw in ["이집트", "피라미드", "파라오", "egypt", "pharaoh", "pyramid"]):
            if "파라오" in name or "왕" in name or "pharaoh" in name_lower:
                prompt_parts.append("Ancient Egyptian pharaoh, golden headdress with cobra emblem, kohl-lined eyes, ceremonial regalia, powerful stance")
            elif "제사장" in name or "신관" in name or "priest" in name_lower:
                prompt_parts.append("Ancient Egyptian priest, shaved head, kohl-lined eyes, white linen robe, golden necklace, holding staff")
            else:
                prompt_parts.append("Ancient Egyptian figure, traditional ancient Egyptian attire, dignified appearance")

        # === 메소포타미아/수메르 ===
        elif any(kw in context for kw in ["메소포타미아", "수메르", "바빌론", "지구라트", "mesopotamia", "sumerian", "babylon"]):
            if "왕" in name or "king" in name_lower:
                prompt_parts.append("Ancient Mesopotamian king, long curled beard, conical crown, ornate robes, holding scepter")
            elif "제사장" in name or "신관" in name:
                prompt_parts.append("Ancient Mesopotamian priest, ceremonial robes, ritual headdress")
            else:
                prompt_parts.append("Ancient Mesopotamian figure, traditional Sumerian attire")

        # === 원시/선사시대 ===
        elif any(kw in context for kw in ["원시", "선사", "족장", "주술사", "부족", "primitive", "tribal", "shaman"]):
            if "족장" in name or "chief" in name_lower:
                prompt_parts.append("Primitive tribal chief, strong muscular build, animal hide clothing, bone necklace, commanding presence")
            elif "주술사" in name or "shaman" in name_lower:
                prompt_parts.append("Tribal shaman, mystical appearance, feathered headdress, ritual face paint, holding staff with animal skull")
            else:
                prompt_parts.append("Prehistoric human, primitive clothing, weathered appearance")

        # === 현대 인물 ===
        elif any(kw in context for kw in ["현대", "대통령", "정치", "기자", "언론", "modern", "president", "journalist"]):
            if "대통령" in name or "president" in name_lower:
                prompt_parts.append("Modern political leader, formal suit, confident posture, professional appearance")
            elif "기자" in name or "언론" in desc_lower:
                prompt_parts.append("Modern journalist, professional attire, press badge, determined expression")
            else:
                prompt_parts.append("Modern professional, business attire, contemporary appearance")

        # === 한국 관련 ===
        elif any(kw in context for kw in ["한국", "조선", "korean", "korea"]):
            if "왕" in name or "king" in name_lower:
                prompt_parts.append("Korean king, traditional royal hanbok with gold embroidery, royal crown, dignified appearance")
            else:
                prompt_parts.append("Korean person, traditional or modern Korean attire, dignified appearance")

        # === 집단/그룹 ===
        if any(kw in name for kw in ["들", "국민", "사람들", "군중", "집단"]):
            if not prompt_parts:
                prompt_parts.append("Group of people, diverse ages and appearances, unified expression")

        # === 기본값 ===
        if not prompt_parts:
            # 설명에서 힌트 추출
            if description:
                prompt_parts.append(f"Person characterized as {description[:80]}, appropriate historical or cultural attire")
            else:
                prompt_parts.append("Person in appropriate historical or cultural attire, neutral expression")

        return prompt_parts[0] if prompt_parts else "Person in appropriate attire"

    def _call_anthropic(self, prompt: str) -> str:
        """Anthropic API 호출"""
        debug_log("  Anthropic API 호출 중...")
        response = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=8000,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text

    def _call_gemini(self, prompt: str) -> str:
        """Google Gemini API 호출 (하위 호환용 래퍼)"""
        text, _ = self._call_gemini_with_status(prompt)
        return text

    def _call_gemini_with_status(self, prompt: str) -> tuple:
        """
        Google Gemini API 호출 (finish_reason 반환)

        Returns:
            (response_text, finish_reason)
            finish_reason: 1=STOP(정상), 2=MAX_TOKENS(잘림!), 3=SAFETY, etc.
        """
        model_name = getattr(self, 'gemini_model_name', 'unknown')
        max_tokens = getattr(self, 'max_output_tokens', 65536)
        debug_log(f"  Gemini API 호출 중...")
        debug_log(f"  📌 모델: {model_name}")
        debug_log(f"  📌 최대 출력 토큰: {max_tokens:,}")
        debug_log(f"  프롬프트 길이: {len(prompt)} 문자")

        if not self.gemini_available or self.gemini_model is None:
            raise RuntimeError("""
Gemini를 사용할 수 없습니다.

다음을 확인하세요:
1. pip install google-generativeai
2. GOOGLE_API_KEY 또는 GEMINI_API_KEY 환경변수 설정
""")

        try:
            # ⭐ 선택된 모델의 max_output_tokens 사용
            response = self.gemini_model.generate_content(
                prompt,
                generation_config={
                    "temperature": 0.2,
                    "max_output_tokens": max_tokens,  # ⭐ 모델별 설정 적용
                    "top_p": 0.95,
                }
            )

            # 응답 확인 - 여러 방법으로 텍스트 추출 시도
            if response is None:
                debug_log("❌ Gemini 응답 None")
                return "", 0

            # ⭐ 응답 종료 이유 확인 (숫자로 반환)
            finish_reason = 1  # 기본값: STOP (정상)
            finish_reason_names = {
                0: "FINISH_REASON_UNSPECIFIED",
                1: "STOP (정상)",
                2: "MAX_TOKENS (잘림!)",
                3: "SAFETY",
                4: "RECITATION",
                5: "OTHER"
            }

            if hasattr(response, 'candidates') and response.candidates:
                candidate = response.candidates[0]
                if hasattr(candidate, 'finish_reason'):
                    raw_reason = candidate.finish_reason
                    # Enum이면 값 추출, 아니면 그대로
                    if hasattr(raw_reason, 'value'):
                        finish_reason = raw_reason.value
                    elif isinstance(raw_reason, int):
                        finish_reason = raw_reason
                    else:
                        # 문자열인 경우 파싱
                        reason_str = str(raw_reason)
                        if "MAX_TOKENS" in reason_str or "2" in reason_str:
                            finish_reason = 2
                        elif "STOP" in reason_str or "1" in reason_str:
                            finish_reason = 1

                    reason_name = finish_reason_names.get(finish_reason, f"UNKNOWN({finish_reason})")
                    debug_log(f"  종료 이유: {finish_reason} ({reason_name})")

                    if finish_reason == 2:
                        debug_log("  ⚠️ 출력 토큰 제한으로 응답이 잘렸습니다!")

            # 방법 1: response.text 직접 접근
            if hasattr(response, 'text') and response.text:
                result = response.text
                debug_log(f"  응답 길이: {len(result)} 문자")
                return result, finish_reason

            # 방법 2: candidates에서 추출
            if hasattr(response, 'candidates') and response.candidates:
                candidate = response.candidates[0]
                if hasattr(candidate, 'content') and candidate.content:
                    parts = candidate.content.parts
                    if parts:
                        result = parts[0].text
                        debug_log(f"  응답 길이 (candidates): {len(result)} 문자")
                        return result, finish_reason

            # 방법 3: 프롬프트 피드백 확인 (차단된 경우)
            if hasattr(response, 'prompt_feedback'):
                feedback = response.prompt_feedback
                debug_log(f"⚠️ 프롬프트 피드백: {feedback}")
                if hasattr(feedback, 'block_reason') and feedback.block_reason:
                    debug_log(f"❌ 차단 이유: {feedback.block_reason}")

            debug_log("❌ Gemini 빈 응답 받음")
            return "", finish_reason

        except Exception as e:
            error_msg = str(e)
            debug_log(f"Gemini API 호출 오류: {error_msg}")

            # 404 오류 시 더 자세한 안내
            if "404" in error_msg:
                debug_log(f"⚠️ 모델 '{model_name}'을(를) 찾을 수 없습니다.")
                debug_log("   앱을 재시작하여 다른 모델을 시도하세요.")

            raise

    def _continue_gemini_generation(self, partial_response: str, original_script: str) -> str:
        """
        MAX_TOKENS로 잘린 응답을 이어서 생성

        Args:
            partial_response: 잘린 응답
            original_script: 원본 스크립트

        Returns:
            완성된 응답
        """
        debug_log("  🔄 이어서 생성 시작...")

        all_response = partial_response
        max_continuations = 3  # 최대 3번까지 이어서 생성

        # 🔴 원본 스크립트 마지막 부분 추출 (컨텍스트 유지용)
        script_ending = original_script[-2000:] if len(original_script) > 2000 else original_script

        for i in range(max_continuations):
            debug_log(f"  이어서 생성 {i+1}/{max_continuations}")

            # 🔴 개선된 이어서 생성 프롬프트 - 원본 스크립트 전체 포함 및 보존 규칙 강조
            continuation_prompt = f"""이전 JSON 응답이 토큰 제한으로 중간에 잘렸습니다.
이어서 JSON을 완성해주세요.

🔴🔴🔴 [CRITICAL] 스크립트 원본 보존 절대 규칙 🔴🔴🔴

⚠️ 가장 중요한 규칙: script_text에는 아래 원본 스크립트에 있는 문장만 사용하세요!

**🚫 절대 금지:**
- 스크립트에 없는 문장 만들기 ❌
- "구독과 좋아요 부탁드립니다" 같은 일반 아웃트로 추가 ❌
- "다음 영상에서 만나요" 같은 문장 추가 ❌
- 원본 문장을 다르게 바꾸기 ❌

**✅ 반드시:**
- 아래 원본 스크립트에 있는 문장만 script_text에 사용
- 원본 텍스트를 한 글자도 바꾸지 않고 그대로 복사

=== 원본 스크립트 전체 (이 내용만 사용!) ===
{original_script}
=== 원본 스크립트 끝 ===

=== 특히 스크립트 마지막 부분 (이 문장들로 마지막 씬을 만드세요!) ===
{script_ending}
=== 마지막 부분 끝 ===

=== 이전 응답의 마지막 부분 (여기서 이어서 작성) ===
{all_response[-2000:]}
=== 이전 응답 끝 ===

위 JSON을 이어서 완성해주세요:
1. 중복 없이 이어서 작성 (마지막 부분 바로 다음부터)
2. 남은 씬들을 모두 포함
3. 반드시 유효한 JSON으로 완성
4. 마지막에 }}로 JSON 닫기
5. 🔴 script_text에는 원본 스크립트에 있는 문장만 사용!

바로 이어서 작성 (```json 없이):"""

            continuation_text, finish_reason = self._call_gemini_with_status(continuation_prompt)

            if not continuation_text:
                debug_log("  ⚠️ 이어서 생성 응답 없음")
                break

            # 응답 병합
            all_response = self._smart_merge_responses(all_response, continuation_text)
            debug_log(f"  병합 후 길이: {len(all_response)} 문자")

            # 정상 종료면 중단
            if finish_reason == 1:
                debug_log("  ✅ 정상 종료 - 이어서 생성 완료")
                break

        return all_response

    def _smart_merge_responses(self, original: str, continuation: str) -> str:
        """응답 스마트 병합 (중복 제거)"""

        # continuation 정리
        continuation = continuation.strip()

        # ```json 블록 제거
        if "```json" in continuation:
            continuation = continuation.split("```json")[-1]
        if "```" in continuation:
            parts = continuation.split("```")
            continuation = parts[0] if parts else continuation

        continuation = continuation.strip()

        if not continuation:
            return original

        # original에서 마지막 불완전한 부분 찾기
        # 일반적으로 }, 또는 ] 이후가 완전한 위치
        last_complete_obj = original.rfind('},')
        last_complete_arr = original.rfind('],')
        last_complete = max(last_complete_obj, last_complete_arr)

        if last_complete > len(original) - 1000:
            # 마지막 완전한 요소까지만 사용
            original_clean = original[:last_complete + 2]  # }, 또는 ], 포함

            # continuation이 쉼표나 공백으로 시작하면 정리
            cont_clean = continuation.lstrip(', \n\t')

            # { 또는 "로 시작하면 새 요소
            if cont_clean.startswith('{') or cont_clean.startswith('"'):
                merged = original_clean + "\n" + cont_clean
            elif cont_clean.startswith(']') or cont_clean.startswith('}'):
                # 닫는 괄호면 그대로 붙이기
                merged = original_clean + cont_clean
            else:
                # 기타: 그냥 이어붙이기
                merged = original + continuation
        else:
            # 겹치는 부분 찾기 시도
            overlap_len = min(100, len(original), len(continuation))
            for i in range(overlap_len, 10, -5):
                search = original[-i:]
                pos = continuation.find(search)
                if pos != -1:
                    merged = original + continuation[pos + len(search):]
                    debug_log(f"  중복 {i}자 제거")
                    return merged

            # 겹치는 부분 없으면 그냥 이어붙이기
            merged = original + continuation

        return merged

    def extract_characters(self, script: str) -> List[Dict]:
        """스크립트에서 등장인물만 추출 (상세 외모 프롬프트 포함)"""
        debug_log("extract_characters 시작")
        debug_log(f"  스크립트 길이: {len(script)} 문자")

        # 스크립트 검증
        if not script or len(script.strip()) < 10:
            debug_log("오류: 스크립트가 비어있거나 너무 짧습니다")
            return []

        # 템플릿에서 캐릭터 추출 프롬프트 가져오기
        base_prompt = self.template_manager.get_prompt("character_extraction")
        debug_log(f"  base_prompt 길이: {len(base_prompt)} 문자")

        if not base_prompt:
            debug_log("오류: character_extraction 프롬프트 템플릿이 비어있습니다")
            return []

        prompt = f"""{base_prompt}

## 스크립트
{script}

JSON 배열로만 응답해주세요."""

        try:
            if self.provider == "google":
                result_text = self._call_gemini(prompt)
            else:
                result_text = self._call_anthropic(prompt)

            debug_log(f"  API 응답 길이: {len(result_text)} 문자")
        except Exception as e:
            debug_log(f"API 호출 오류: {e}")
            return []

        if "```json" in result_text:
            result_text = result_text.split("```json")[1].split("```")[0]
        elif "```" in result_text:
            result_text = result_text.split("```")[1].split("```")[0]

        try:
            characters = json.loads(result_text.strip())
            debug_log(f"  캐릭터 {len(characters)}명 추출됨")
        except json.JSONDecodeError as e:
            debug_log(f"  JSON 파싱 실패: {e}")
            characters = []

        return characters

    def generate_direction_guide(self, scene_text: str, characters: List[str] = None) -> Dict:
        """단일 씬에 대한 연출가이드 생성"""

        characters = characters or []

        prompt = f"""다음 씬에 대한 연출가이드를 생성해주세요.

## 씬 텍스트
{scene_text}

## 등장 캐릭터
{', '.join(characters) if characters else '없음'}

## 출력 형식 (JSON)
{{
    "direction_guide": "상세한 연출 설명",
    "visual_composition": "화면 구성 설명",
    "background": "배경 설명",
    "character_actions": "캐릭터 동작/표정",
    "mood_lighting": "분위기와 조명",
    "image_prompt_en": "영문 이미지 프롬프트 (FLUX용, 상세하게)"
}}

JSON으로만 응답해주세요."""

        response = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )

        result_text = response.content[0].text

        if "```json" in result_text:
            result_text = result_text.split("```json")[1].split("```")[0]

        try:
            guide = json.loads(result_text.strip())
        except json.JSONDecodeError:
            guide = {"direction_guide": "", "image_prompt_en": ""}

        return guide


def analyze_and_save(script_path: str, output_dir: str, language: str = "ko") -> Dict:
    """스크립트 파일을 분석하고 결과 저장"""

    script_path = Path(script_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 스크립트 로드
    script = script_path.read_text(encoding="utf-8")

    # 분석
    analyzer = SceneAnalyzer()
    result = analyzer.analyze_script(script, language)

    # 저장
    scenes_path = output_dir / "scenes.json"
    characters_path = output_dir / "characters.json"

    with open(scenes_path, "w", encoding="utf-8") as f:
        json.dump(result.get("scenes", []), f, ensure_ascii=False, indent=2)

    with open(characters_path, "w", encoding="utf-8") as f:
        json.dump(result.get("characters", []), f, ensure_ascii=False, indent=2)

    return result
