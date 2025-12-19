"""
프롬프트 템플릿 관리자

AI 분석에 사용되는 프롬프트 템플릿을 관리합니다.
사용자가 프롬프트를 커스터마이징할 수 있습니다.
"""
import json
from pathlib import Path
from typing import Dict, Optional, List
from dataclasses import dataclass, asdict
from datetime import datetime

# 디버그 모드
DEBUG = True

def _debug_log(message: str):
    """디버그 로그"""
    if DEBUG:
        print(f"[PromptTemplateManager] {message}")


@dataclass
class PromptTemplate:
    """프롬프트 템플릿"""
    id: str
    name: str
    description: str
    prompt: str
    category: str = "general"
    is_default: bool = True
    updated_at: str = ""

    def __post_init__(self):
        if not self.updated_at:
            self.updated_at = datetime.now().isoformat()


class PromptTemplateManager:
    """프롬프트 템플릿 관리자"""

    # 절대 경로로 설정 (프로젝트 루트 기준)
    _ROOT_DIR = Path(__file__).parent.parent.parent
    CONFIG_PATH = _ROOT_DIR / "data" / "config" / "prompt_templates.json"

    # 기본 프롬프트 템플릿
    DEFAULT_TEMPLATES = {
        "scene_analysis": PromptTemplate(
            id="scene_analysis",
            name="기본 씬 분석",
            category="scene_analysis",
            description="스크립트를 씬으로 분할하고 각 씬의 시각적 요소를 분석합니다.",
            prompt='''당신은 유튜브 인포그래픽 영상의 전문 연출가입니다.
다음 스크립트를 분석하여 씬(Scene) 단위로 분할하고, 각 씬과 캐릭터에 대한 상세 정보를 제공해주세요.

## 분석 기준
- 장면 전환이 필요한 시점에서 씬을 분할
- 하나의 씬은 5~15초 분량 (약 50~150자)
- 시각적으로 다른 장면이 필요할 때 새 씬으로 분할
- 같은 맥락이면 하나의 씬으로 유지

## 캐릭터 분석 (매우 중요!)
각 캐릭터에 대해 반드시 visual_prompt를 생성하세요.

### visual_prompt 작성 규칙:
- **반드시 영어로** 작성
- **50-100 단어**로 상세하게
- 다음 요소 포함: 인종/민족, 성별과 나이, 얼굴 특징, 헤어스타일, 체형, 의상, 액세서리

### visual_prompt 예시:
- 현대 언론인: "Middle Eastern man, late 50s, salt-and-pepper beard, glasses with thin metal frames, wearing dark gray business suit, professional journalist appearance"
- 왕족: "Saudi Arabian prince, 30s, clean-shaven, wearing traditional white thobe and red-checkered keffiyeh, authoritative posture"
- 고대인물: "Ancient Egyptian priest, shaved head, kohl-lined eyes, white linen robe, golden necklace"

## 출력 형식 (JSON)
{
    "scenes": [
        {
            "scene_id": 1,
            "script_text": "해당 씬의 스크립트 텍스트",
            "duration_estimate": 10,
            "direction_guide": "연출가이드: 어떤 장면으로 표현하면 좋을지 상세 설명",
            "visual_elements": ["배경", "주요 오브젝트", "분위기"],
            "characters": ["등장 캐릭터명"],
            "camera_suggestion": "카메라 앵글 제안 (전신, 상반신, 클로즈업 등)",
            "mood": "분위기 (밝음, 진지함, 긴장감 등)",
            "image_prompt_ko": "이미지 프롬프트 (한국어)",
            "image_prompt_en": "이미지 프롬프트 (영어, 상세하게)"
        }
    ],
    "characters": [
        {
            "name": "캐릭터명 (한글)",
            "name_en": "English Name",
            "role": "주연/조연/엑스트라",
            "description": "캐릭터 설명",
            "visual_prompt": "반드시 영어로 50-100단어 상세 외모 묘사"
        }
    ],
    "total_scenes": 씬 개수,
    "estimated_duration": 예상 총 길이(초)
}

## 중요 규칙
1. **모든 캐릭터에 visual_prompt 필수** - 절대 비워두지 마세요!
2. visual_prompt는 **반드시 영어**로 작성
3. JSON 형식으로만 응답 (마크다운 코드 블록 사용 금지)'''
        ),

        "character_extraction": PromptTemplate(
            id="character_extraction",
            name="캐릭터 추출 프롬프트",
            category="character_extraction",
            description="스크립트에서 캐릭터를 추출하고 상세한 비주얼 프롬프트를 생성합니다.",
            prompt='''당신은 영상 제작을 위한 캐릭터 분석가입니다.
다음 스크립트에서 등장하는 모든 인물/캐릭터를 추출하고, 각 캐릭터에 대해 **매우 구체적인 외모 묘사 프롬프트**를 생성해주세요.

## 중요: 프롬프트 작성 규칙

**반드시 포함할 내용 (구체적으로):**

1. 신체적 특징:
   - 인종과 성별
   - 정확한 나이 (예: "47 years old", "middle-aged" 같은 추상적 표현 금지)
   - 얼굴형 (oval, round, square, heart-shaped, long)
   - 눈 특징 (크기, 모양, 쌍꺼풀 유무 - 아시아인의 경우)
   - 코 유형 (straight, rounded, prominent)
   - 입/입술 묘사
   - 피부톤 (fair, medium, tan, dark)
   - 특이점 (점, 주름, 보조개 등)

2. 헤어스타일:
   - 길이 (very short, short, medium, long)
   - 색상 (jet black, dark brown, salt-and-pepper, white 등 구체적으로)
   - 스타일 (slicked back, parted, messy, curly, straight)
   - 헤어라인 (receding, widow's peak, full)
   - 남성의 경우 수염 (clean-shaven, stubble, mustache, beard)

3. 체형:
   - 키 인상 (tall, average, short)
   - 체격 (slim, lean, medium, athletic, stocky, heavy)
   - 자세

4. 의상 (매우 구체적으로):
   - 의류 종류와 스타일
   - 정확한 색상 (navy blue, charcoal gray, cream white - "blue"만 쓰지 말것)
   - 핏 (fitted, loose, tailored)
   - 액세서리 (안경 프레임 스타일과 색상, 시계, 장신구, 넥타이, 가방)
   - 신발 (보이는 경우)

5. 포즈/자세:
   - 몸 위치 (standing, sitting, walking)
   - 손 위치
   - 바라보는 방향

**절대 포함하지 말 것:**
- 아트 스타일 (flat, vector, 3D, anime 등) - 별도로 추가됨
- 배경 설명
- 성격 특성 (professional, friendly, serious 등)
- 감정 상태
- 추상적 특성 (trustworthy, confident 등)

## 출력 형식 (JSON 배열)
[
    {
        "name": "캐릭터명 (한글)",
        "name_en": "영문명",
        "role": "역할 (주연, 조연, 엑스트라)",
        "description": "캐릭터 설명 (한국어)",
        "era": "시대 (현대, 1990년대 등)",
        "nationality": "국적",
        "appearance": "외모 특징 요약 (한국어)",
        "character_prompt": "상세 영문 프롬프트"
    }
]

## character_prompt 예시:
"Korean man, 47 years old, short neat black hair with gray at temples and receding hairline, rectangular black-framed glasses, oval face with small monolid eyes and straight nose, clean-shaven, fair skin, medium athletic build, wearing charcoal gray two-piece suit with white dress shirt and burgundy silk tie, silver wristwatch, standing with hands clasped in front"

JSON 배열로만 응답해주세요.'''
        ),

        "image_prompt_generation": PromptTemplate(
            id="image_prompt_generation",
            name="이미지 프롬프트 생성",
            category="image_prompt_generation",
            description="씬 설명에서 이미지 생성용 프롬프트를 만듭니다.",
            prompt='''당신은 AI 이미지 생성 도구를 위한 프롬프트 전문가입니다.

주어진 씬 설명과 캐릭터 정보를 바탕으로 상세한 이미지 프롬프트를 작성해주세요.

## 가이드라인:
1. 주요 피사체로 시작
2. 구체적인 시각 디테일 포함
3. 구도와 프레이밍 설명
4. 필요시 조명 언급
5. 200단어 이내로 유지

## 포함하지 말 것:
- 아트 스타일 (별도로 추가됨)
- 네거티브 프롬프트
- 기술적 파라미터

단일 문단으로 프롬프트만 출력하세요.'''
        ),

        "scene_image_prompt": PromptTemplate(
            id="scene_image_prompt",
            name="씬 이미지 프롬프트",
            category="scene_image_prompt",
            description="개별 씬에 대한 이미지 프롬프트를 생성합니다.",
            prompt='''씬 설명을 바탕으로 이미지 생성 프롬프트를 작성하세요.

## 규칙:
- 영어로 작성
- 주요 요소부터 시작
- 배경과 분위기 포함
- 캐릭터가 있으면 동작/표정 포함
- 100-150 단어

## 제외:
- 아트 스타일 관련 표현
- 텍스트나 글자
- 기술적 용어

프롬프트만 출력하세요.'''
        ),
    }

    def __init__(self):
        _debug_log(f"초기화 시작")
        _debug_log(f"  설정 파일 경로: {self.CONFIG_PATH}")
        _debug_log(f"  설정 파일 존재: {self.CONFIG_PATH.exists()}")

        self.templates: Dict[str, PromptTemplate] = {}
        self._load_templates()

    def _load_templates(self):
        """템플릿 로드 (저장된 것 + 기본값)"""
        _debug_log("템플릿 로드 시작")

        # 기본 템플릿으로 시작
        for key, template in self.DEFAULT_TEMPLATES.items():
            self.templates[key] = PromptTemplate(
                id=template.id,
                name=template.name,
                category=template.category,
                description=template.description,
                prompt=template.prompt,
                is_default=template.is_default,
                updated_at=template.updated_at
            )

        _debug_log(f"  기본 템플릿 {len(self.templates)}개 로드됨")

        # 저장된 템플릿 덮어쓰기
        if self.CONFIG_PATH.exists():
            try:
                with open(self.CONFIG_PATH, "r", encoding="utf-8") as f:
                    saved = json.load(f)

                custom_count = 0
                for key, data in saved.items():
                    if key in self.templates:
                        is_default = data.get("is_default", True)
                        self.templates[key] = PromptTemplate(
                            id=key,
                            name=data.get("name", self.templates[key].name),
                            category=data.get("category", getattr(self.templates[key], 'category', 'general')),
                            description=data.get("description", self.templates[key].description),
                            prompt=data.get("prompt", self.templates[key].prompt),
                            is_default=is_default,
                            updated_at=data.get("updated_at", "")
                        )
                        if not is_default:
                            custom_count += 1
                            _debug_log(f"  ✏️ 커스텀 템플릿 로드됨: {key}")

                _debug_log(f"  저장된 템플릿에서 {custom_count}개 커스텀 로드됨")

            except Exception as e:
                _debug_log(f"❌ 템플릿 로드 실패: {e}")
        else:
            _debug_log("  저장된 템플릿 파일 없음 (기본값 사용)")

    def _save_templates(self):
        """템플릿 저장"""
        self.CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)

        data = {}
        for key, template in self.templates.items():
            data[key] = asdict(template)

        try:
            with open(self.CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            _debug_log(f"✅ 템플릿 저장됨: {self.CONFIG_PATH}")
        except Exception as e:
            _debug_log(f"❌ 템플릿 저장 실패: {e}")

    def get_template(self, template_id: str) -> Optional[PromptTemplate]:
        """템플릿 가져오기"""
        template = self.templates.get(template_id)
        if template:
            _debug_log(f"템플릿 '{template_id}' 반환 (기본값: {template.is_default})")
        else:
            _debug_log(f"⚠️ 템플릿 '{template_id}' 없음")
        return template

    def get_prompt(self, template_id: str) -> str:
        """프롬프트 텍스트만 가져오기"""
        template = self.templates.get(template_id)
        if template:
            _debug_log(f"프롬프트 '{template_id}' 반환 ({len(template.prompt)} 문자, 기본값: {template.is_default})")
            return template.prompt
        else:
            _debug_log(f"⚠️ 프롬프트 '{template_id}' 없음, 빈 문자열 반환")
            return ""

    def update_template(self, template_id: str, prompt: str, name: str = None, description: str = None) -> bool:
        """템플릿 업데이트"""
        if template_id not in self.templates:
            _debug_log(f"❌ 업데이트 실패: 템플릿 '{template_id}' 없음")
            return False

        template = self.templates[template_id]
        self.templates[template_id] = PromptTemplate(
            id=template_id,
            name=name if name else template.name,
            category=template.category,
            description=description if description else template.description,
            prompt=prompt,
            is_default=False,
            updated_at=datetime.now().isoformat()
        )

        _debug_log(f"✅ 템플릿 '{template_id}' 업데이트됨 ({len(prompt)} 문자)")
        self._save_templates()
        return True

    def reset_to_default(self, template_id: str) -> bool:
        """기본값으로 리셋"""
        if template_id not in self.DEFAULT_TEMPLATES:
            return False

        default = self.DEFAULT_TEMPLATES[template_id]
        self.templates[template_id] = PromptTemplate(
            id=default.id,
            name=default.name,
            category=default.category,
            description=default.description,
            prompt=default.prompt,
            is_default=True,
            updated_at=datetime.now().isoformat()
        )
        self._save_templates()
        return True

    def get_all_templates(self) -> Dict[str, PromptTemplate]:
        """모든 템플릿 가져오기"""
        return self.templates

    def get_template_list(self):
        """템플릿 목록 (UI 표시용)"""
        return [
            {
                "id": t.id,
                "name": t.name,
                "category": t.category,
                "description": t.description,
                "is_default": t.is_default,
                "updated_at": t.updated_at
            }
            for t in self.templates.values()
        ]

    def get_templates_by_category(self, category: str) -> List[PromptTemplate]:
        """카테고리별 템플릿 목록 반환"""
        return [t for t in self.templates.values() if t.category == category]

    def create_template(self, category: str, name: str, description: str, prompt: str) -> Optional[PromptTemplate]:
        """새 템플릿 생성"""
        import uuid
        new_id = f"{category}_{uuid.uuid4().hex[:8]}"
        
        template = PromptTemplate(
            id=new_id,
            name=name,
            category=category,
            description=description,
            prompt=prompt,
            is_default=False,
            updated_at=datetime.now().isoformat()
        )
        
        self.templates[new_id] = template
        self._save_templates()
        _debug_log(f"✅ 새 템플릿 생성됨: {name} ({new_id})")
        return template

    def delete_template(self, template_id: str) -> bool:
        """템플릿 삭제"""
        if template_id not in self.templates:
            return False
            
        if self.templates[template_id].is_default:
            _debug_log(f"❌ 삭제 불가: 기본 템플릿 ({template_id})")
            return False
            
        del self.templates[template_id]
        self._save_templates()
        _debug_log(f"🗑️ 템플릿 삭제됨: {template_id}")
        return True


# 싱글톤
_template_manager = None


def get_template_manager() -> PromptTemplateManager:
    """템플릿 매니저 싱글톤 가져오기"""
    global _template_manager
    if _template_manager is None:
        _debug_log("싱글톤 인스턴스 생성")
        _template_manager = PromptTemplateManager()
    return _template_manager


def reload_template_manager() -> PromptTemplateManager:
    """
    템플릿 매니저 강제 리로드

    UI에서 템플릿 저장 후 호출하여 즉시 적용되도록 함
    """
    global _template_manager
    _debug_log("🔄 싱글톤 인스턴스 강제 리로드")
    _template_manager = PromptTemplateManager()
    return _template_manager
