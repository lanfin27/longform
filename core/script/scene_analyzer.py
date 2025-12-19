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


class SceneAnalyzer:
    """AI 기반 씬 분석기"""

    def __init__(self, provider: str = "anthropic"):
        """
        Args:
            provider: AI 제공자 ("anthropic", "google", "gemini", "openai")
        """
        debug_log(f"초기화 시작 (provider={provider})")

        self.provider = provider
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

            # 우선순위대로 모델 시도 (API 버전 변경에 대응)
            model_candidates = [
                "gemini-2.0-flash-exp",     # 최신 2.0 (무료, 빠름)
                "gemini-1.5-flash-latest",  # 1.5 최신
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
            debug_log(f"✅ Google Gemini 클라이언트 초기화 완료 ({self.gemini_model_name})")

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
                result_text = self._call_gemini(prompt)
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
        if "```json" in result_text:
            result_text = result_text.split("```json")[1].split("```")[0]
        elif "```" in result_text:
            result_text = result_text.split("```")[1].split("```")[0]

        try:
            result = json.loads(result_text.strip())
            debug_log(f"  JSON 파싱 성공: 씬 {len(result.get('scenes', []))}개, 캐릭터 {len(result.get('characters', []))}개")

            # === 캐릭터 데이터 정규화 ===
            raw_characters = result.get("characters", [])
            result["characters"] = self._normalize_characters(raw_characters)
            debug_log(f"  캐릭터 정규화 완료: {len(result['characters'])}개")

            # === visual_prompt가 비어있으면 자동 생성 ===
            result["characters"] = self._ensure_visual_prompts(result["characters"], script)
            debug_log(f"  visual_prompt 확인 완료")

            # === 씬 데이터 정규화 ===
            raw_scenes = result.get("scenes", [])
            result["scenes"] = self._normalize_scenes(raw_scenes)

        except json.JSONDecodeError as e:
            debug_log(f"  JSON 파싱 실패: {e}")
            debug_log(f"  파싱 시도한 텍스트: {result_text[:300]}...")
            # 파싱 실패 시 기본 구조 반환
            result = {
                "scenes": [],
                "characters": [],
                "total_scenes": 0,
                "estimated_duration": 0,
                "error": f"JSON 파싱 실패: {str(e)}",
                "raw_response": result_text[:500]
            }

        return result

    def _normalize_characters(self, raw_characters: list) -> list:
        """
        캐릭터 배열 정규화

        문자열 배열이면 딕셔너리 배열로 변환
        """
        if not raw_characters:
            return []

        normalized = []

        for char in raw_characters:
            if isinstance(char, str):
                # 문자열 → 딕셔너리로 변환
                normalized.append({
                    "name": char,
                    "name_ko": char,
                    "name_en": "",
                    "role": "등장인물",
                    "description": "",
                    "appearance": "",
                    "nationality": "",
                    "era": "",
                    "character_prompt": "",
                    "visual_prompt": ""
                })
            elif isinstance(char, dict):
                # 딕셔너리 → 필수 필드 확인 및 보완
                normalized.append({
                    "name": char.get("name", char.get("name_ko", "Unknown")),
                    "name_ko": char.get("name_ko", char.get("name", "")),
                    "name_en": char.get("name_en", ""),
                    "role": char.get("role", "등장인물"),
                    "description": char.get("description", ""),
                    "appearance": char.get("appearance", ""),
                    "nationality": char.get("nationality", ""),
                    "era": char.get("era", char.get("age_era", "")),
                    "character_prompt": char.get("character_prompt", char.get("visual_prompt", char.get("prompt", ""))),
                    "visual_prompt": char.get("visual_prompt", char.get("character_prompt", char.get("prompt", "")))
                })
            else:
                # 기타 → 문자열로 변환
                normalized.append({
                    "name": str(char),
                    "name_ko": str(char),
                    "name_en": "",
                    "role": "등장인물",
                    "description": "",
                    "appearance": "",
                    "nationality": "",
                    "era": "",
                    "character_prompt": "",
                    "visual_prompt": ""
                })

        return normalized

    def _normalize_scenes(self, raw_scenes: list) -> list:
        """
        씬 배열 정규화

        씬 내부의 characters 필드도 처리
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

            normalized.append(scene)

        return normalized

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
        """Google Gemini API 호출"""
        model_name = getattr(self, 'gemini_model_name', 'unknown')
        debug_log(f"  Gemini API 호출 중... (모델: {model_name})")
        debug_log(f"  프롬프트 길이: {len(prompt)} 문자")

        if not self.gemini_available or self.gemini_model is None:
            raise RuntimeError("""
Gemini를 사용할 수 없습니다.

다음을 확인하세요:
1. pip install google-generativeai
2. GOOGLE_API_KEY 또는 GEMINI_API_KEY 환경변수 설정
""")

        try:
            response = self.gemini_model.generate_content(
                prompt,
                generation_config={
                    "temperature": 0.2,
                    "max_output_tokens": 8192,
                }
            )

            # 응답 확인 - 여러 방법으로 텍스트 추출 시도
            if response is None:
                debug_log("❌ Gemini 응답 None")
                return ""

            # 방법 1: response.text 직접 접근
            if hasattr(response, 'text') and response.text:
                result = response.text
                debug_log(f"  응답 길이: {len(result)} 문자")
                return result

            # 방법 2: candidates에서 추출
            if hasattr(response, 'candidates') and response.candidates:
                candidate = response.candidates[0]
                if hasattr(candidate, 'content') and candidate.content:
                    parts = candidate.content.parts
                    if parts:
                        result = parts[0].text
                        debug_log(f"  응답 길이 (candidates): {len(result)} 문자")
                        return result

            # 방법 3: 프롬프트 피드백 확인 (차단된 경우)
            if hasattr(response, 'prompt_feedback'):
                feedback = response.prompt_feedback
                debug_log(f"⚠️ 프롬프트 피드백: {feedback}")
                if hasattr(feedback, 'block_reason') and feedback.block_reason:
                    debug_log(f"❌ 차단 이유: {feedback.block_reason}")

            debug_log("❌ Gemini 빈 응답 받음")
            return ""

        except Exception as e:
            error_msg = str(e)
            debug_log(f"Gemini API 호출 오류: {error_msg}")

            # 404 오류 시 더 자세한 안내
            if "404" in error_msg:
                debug_log(f"⚠️ 모델 '{model_name}'을(를) 찾을 수 없습니다.")
                debug_log("   앱을 재시작하여 다른 모델을 시도하세요.")

            raise

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
