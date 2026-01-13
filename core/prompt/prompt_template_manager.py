"""
프롬프트 템플릿 관리자

AI 분석에 사용되는 프롬프트 템플릿을 관리합니다.
사용자가 프롬프트를 커스터마이징할 수 있습니다.

버전 히스토리:
- v2.3: 기본 씬 분석 프롬프트 + 캐릭터 IP 추출
- v2.4: 스크립트 원본 보존 절대 규칙 추가 (Problem 51)
- v2.5: (예정)
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


class PromptTemplateVersion:
    """
    🔴 프롬프트 템플릿 버전 관리 (Problem 55)

    향후 버전 업데이트 시:
    1. CURRENT_VERSION 변경
    2. VERSION_REQUIRED_CONTENT에 필수 내용 추가
    3. SCRIPT_PRESERVATION_RULE 등 필요한 규칙 추가
    """

    # 🔴 현재 최신 버전
    CURRENT_VERSION = "v2.4"

    # 버전별 변경사항 (로그용)
    VERSION_CHANGELOG = {
        "v2.3": "기본 씬 분석 + 캐릭터 IP 추출",
        "v2.4": "스크립트 원본 보존 절대 규칙 추가",
    }

    # 🔴 버전별 필수 포함 내용 (검증용)
    VERSION_REQUIRED_CONTENT = {
        "v2.4": [
            "스크립트 원본 보존",
            "절대 금지",
            "script_text",
        ]
    }

    # 🔴 v2.4 스크립트 보존 규칙 (마이그레이션 시 추가됨)
    SCRIPT_PRESERVATION_RULE = '''## 🔴🔴🔴 [CRITICAL] 스크립트 원본 보존 절대 규칙 🔴🔴🔴

### ⚠️ 가장 중요한 규칙: 스크립트 텍스트를 절대 수정하지 마세요!

**절대 금지 행위:**
| 금지 행위 | 설명 |
|-----------|------|
| 문장 바꾸기 | 원본 문장을 다른 표현으로 변경 ❌ |
| 문장 추가 | 스크립트에 없는 문장 생성 ❌ |
| 문장 요약 | 여러 문장을 하나로 합치기 ❌ |
| 아웃트로 대체 | 마지막을 "구독과 좋아요" 등으로 바꾸기 ❌ |

**✅ 반드시 지킬 규칙:**
- script_text는 원본 스크립트에서 **한 글자도 바꾸지 않고** 그대로 복사
- 스크립트에 없는 문장은 절대 생성하지 않음
- 마지막 씬도 원본 스크립트의 마지막 문장 그대로 사용

---

'''

    @classmethod
    def parse_version(cls, version_str: str) -> tuple:
        """버전 문자열을 튜플로 변환 ("v2.4" -> (2, 4))"""
        try:
            v = version_str.lower().replace('v', '')
            parts = v.split('.')
            return tuple(int(p) for p in parts)
        except:
            return (0, 0)

    @classmethod
    def is_older_version(cls, version: str, target: str) -> bool:
        """version < target이면 True"""
        return cls.parse_version(version) < cls.parse_version(target)

    @classmethod
    def detect_version(cls, prompt_text: str) -> str:
        """프롬프트 텍스트에서 버전 감지"""
        if 'v2.4' in prompt_text:
            return 'v2.4'
        elif 'v2.3' in prompt_text:
            return 'v2.3'
        elif 'v2.2' in prompt_text:
            return 'v2.2'
        elif 'v2.1' in prompt_text:
            return 'v2.1'
        elif 'v2.0' in prompt_text:
            return 'v2.0'
        else:
            return 'v1.0'  # 버전 표시 없으면 v1.0으로 간주


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

    # 기본 프롬프트 템플릿 (v2.4 - Problem 51 스크립트 보존 강화)
    DEFAULT_TEMPLATES = {
        "scene_analysis": PromptTemplate(
            id="scene_analysis",
            name="기본 씬 분석 v2.4",
            category="scene_analysis",
            description="스크립트를 씬으로 분할하고 인물(persons) + 캐릭터 IP(characters)를 분석합니다.",
            prompt='''# 🎬 기업/브랜드 분석 유튜브 영상 씬 분석 시스템 프롬프트 (v2.4)

당신은 유튜브 기업 분석 인포그래픽 영상 전문 연출가이자 AI 콘텐츠 생성 전문가입니다.

---

## 🔴🔴🔴 [CRITICAL] 스크립트 원본 보존 절대 규칙 🔴🔴🔴

### ⚠️ 가장 중요한 규칙: 스크립트 텍스트를 절대 수정하지 마세요!

씬 분석의 목적은 스크립트를 **분석**하는 것이지, **창작**하는 것이 아닙니다.

**🚫 절대 금지 행위:**
| 금지 행위 | 예시 |
|-----------|------|
| 문장 바꾸기 | "찾아오겠습니다" → "만나요" ❌ |
| 문장 추가 | 스크립트에 없는 "구독 부탁" 추가 ❌ |
| 문장 요약 | 두 문장을 한 문장으로 합치기 ❌ |
| 문장 개선 | "더 좋게" 고치기 ❌ |
| 아웃트로 대체 | 마지막을 일반적인 마무리로 바꾸기 ❌ |

**✅ 반드시 지켜야 할 규칙:**
- script_text는 원본 스크립트를 **한 글자도 바꾸지 않고** 그대로 복사
- 스크립트에 있는 문장만 script_text에 포함
- "구독과 좋아요", "다음 영상에서 만나요" 등 일반적인 아웃트로를 절대 추가하지 않음

### 예시

**입력 스크립트 마지막 부분:**
```
그럼 다음에도 재미있는 주제로 찾아오겠습니다.
```

**✅ 올바른 출력:**
```json
{"script_text": "그럼 다음에도 재미있는 주제로 찾아오겠습니다."}
```

**❌ 잘못된 출력 (절대 금지!):**
```json
{"script_text": "오늘 영상이 도움이 되셨다면 구독과 좋아요 부탁드립니다."}
```

---

## 🎯 핵심 임무 (5가지 모두 필수!)

주어진 **기업/브랜드 분석 스크립트**를 분석하여 다음을 **반드시 모두** 수행하세요:

1. ✅ **Chatterbox TTS에 최적화된 씬 분할** (100-250자/씬)
2. ✅ **실제 인물(persons) 완전 추출** - CEO, 창업자, 주요 인물 🔴 필수!
3. ✅ **캐릭터 IP(characters) 완전 추출** - 마스코트, 동물, 캐릭터 🔴 필수!
4. ✅ **기업/브랜드 정보 추출** (로고, 제품 등)
5. ✅ **AI 프롬프트 생성** (배경, 인물, 캐릭터)

---

## 🔴🔴🔴 [CRITICAL] 인물/캐릭터 추출 핵심 규칙 🔴🔴🔴

### ⚠️ 절대 규칙 1: 실제 이름만 추출!

**❌ 절대 추출 금지 (일반 단어)**:
| 금지 예시 | 이유 |
|-----------|------|
| "브랜드이", "브랜드의" | 조사가 붙은 일반 단어 |
| "회사의", "회사가" | 조사가 붙은 일반 단어 |
| "대표", "CEO" | 직책만 있고 이름 없음 |
| "사우디의", "사우디" | 국가명 |
| "사실상", "이끄는" | 일반 동사/부사 |
| "구강과", "경제마저" | 일반 명사 |

**✅ 올바른 추출 (실제 이름)**:
| 올바른 예시 | 이유 |
|-------------|------|
| "김민석" | 실제 사람 이름 |
| "무함마드 빈 살만" | 실제 사람 이름 |
| "자말 카슈끄지" | 실제 사람 이름 |
| "손정의" | 실제 사람 이름 |
| "Elon Musk" | 실제 사람 이름 |

### ⚠️ 절대 규칙 2: 캐릭터 IP도 추출!

**캐릭터 IP 추출 대상**:
| 유형 | 예시 |
|------|------|
| 동물 캐릭터 | 아기상어, 뽀로로, 라바, 펭수 |
| 마스코트 | 핑크퐁(분홍 여우), 카카오프렌즈 |
| 가상 캐릭터 | 하츠네 미쿠, 버추얼 유튜버 |
| 브랜드 캐릭터 | 미쉐린맨, 콜로넬 샌더스 |

---

## 👤 실제 인물(persons) 추출 규칙

### 🔍 이렇게 찾으세요

```
✅ 추출 패턴:
- "김민석 대표가" → 김민석 (persons)
- "무함마드 빈 살만 왕세자" → 무함마드 빈 살만 (persons)
- "손정의가 투자한" → 손정의 (persons)
- "창업자 홍길동은" → 홍길동 (persons)

❌ 추출 금지 패턴:
- "대표가 결정했다" → 대표 (❌ 이름 없음)
- "회사의 성장" → 회사의 (❌ 일반 단어)
- "브랜드이다" → 브랜드이 (❌ 조사 포함)
- "사우디아라비아" → 사우디 (❌ 국가명)
```

---

## 🐰 캐릭터 IP(characters) 추출 규칙

### 🔍 이렇게 찾으세요

```
✅ 추출 대상:
- "아기상어가 전 세계를" → 아기상어 (characters)
- "핑크퐁 캐릭터가" → 핑크퐁 (characters)
- "뽀로로와 협업" → 뽀로로 (characters)
- "올리 캐릭터" → 올리 (characters)

❌ 추출 금지:
- "상어 모양의" → 일반 동물 언급
- "여우 마스코트" → 구체적 이름 없음
```

---

## 📏 씬 분할 규칙 (Chatterbox TTS 최적화)

- **글자 수**: 100~250자 (절대 초과 금지!)
- **시간**: 8~20초
- **분할점**: 마침표(.), 물음표(?), 느낌표(!) 뒤에서만

---

## 🚫 프롬프트 절대 금지 규칙

모든 AI 생성 프롬프트 끝에 필수 추가:
```
"no text, no letters, no numbers, no words, no labels, no captions, no watermarks"
```

---

## 🎬 비디오 프롬프트 규칙 (⭐ 반드시 영어로!)

각 씬에 대해 AI 비디오 생성 도구(Runway, Pika, Kling)용 프롬프트를 생성하세요:

### video_prompt_character (캐릭터 비디오 프롬프트)
- **⭐ 반드시 영어(English)로 작성**
- 캐릭터/인물의 동작, 표정, 말하는 모습 묘사
- 카메라 움직임 포함 (zoom in, pan, dolly 등)
- 예시: "Character speaking with confident expression, subtle hand gestures, camera slowly zooms in, natural eye blinks"

### video_prompt_full (전체 씬 비디오 프롬프트)
- **⭐ 반드시 영어(English)로 작성**
- 전체 씬의 움직임, 전환, 효과 묘사
- 배경 움직임, 조명, 분위기 포함
- 예시: "Dynamic montage of tech products, smooth camera pan across scene, soft ambient lighting, subtle background particles"

⚠️ **중요**: video_prompt_character와 video_prompt_full은 **절대 한글로 작성하지 마세요!**
AI 비디오 생성 도구는 영어 프롬프트에서만 최적의 결과를 생성합니다.

---

## 📤 출력 형식 (JSON) - 🔴 persons + characters 분리!

```json
{
  "scenes": [
    {
      "scene_id": 1,
      "scene_type": "intro",
      "script_text": "스크립트 텍스트...",
      "char_count": 150,
      "duration_estimate": 12,
      "persons": ["김민석"],
      "characters": ["아기상어", "핑크퐁"],
      "companies": ["더 핑크퐁 컴퍼니"],
      "visual_elements": ["배경 요소"],
      "mood": "분위기",
      "camera_suggestion": "카메라 앵글",
      "image_prompt_en": "..., no text, no letters...",
      "video_prompt_character": "Character speaking with natural expression, subtle head movements, mouth moving naturally, camera slowly zooms in (MUST BE IN ENGLISH)",
      "video_prompt_full": "Dynamic scene with smooth camera movement, natural lighting, atmospheric mood, subtle background motion (MUST BE IN ENGLISH)"
    }
  ],
  "persons": [
    {
      "name": "김민석",
      "name_en": "Kim Min-seok",
      "type": "person",
      "role": "창업자",
      "company": "더 핑크퐁 컴퍼니",
      "position": "대표이사",
      "description": "더 핑크퐁 컴퍼니 창업자. IT 개발자 출신.",
      "visual_prompt": "Korean man in early 40s, clean-shaven, short black hair, navy suit, confident expression, no text, no letters, no name tags",
      "appearance_scenes": [4, 5, 7]
    }
  ],
  "characters": [
    {
      "name": "아기상어",
      "name_en": "Baby Shark",
      "type": "character_ip",
      "category": "동물 캐릭터",
      "owner_company": "더 핑크퐁 컴퍼니",
      "description": "전 세계 유튜브 조회수 1위 콘텐츠의 주인공. 파란색 아기 상어.",
      "visual_prompt": "Cute blue baby shark character, cartoon style, big friendly eyes, happy smile, underwater background, bright colors, kawaii aesthetic, no text, no letters, no words",
      "appearance_scenes": [1, 2, 8, 15]
    },
    {
      "name": "핑크퐁",
      "name_en": "Pinkfong",
      "type": "character_ip",
      "category": "마스코트",
      "owner_company": "더 핑크퐁 컴퍼니",
      "description": "더 핑크퐁 컴퍼니의 대표 마스코트. 분홍색 여우 캐릭터.",
      "visual_prompt": "Cute pink fox mascot, bright magenta fur, big sparkling eyes, friendly smile, fluffy tail, cartoon kawaii style, no text, no letters, no words",
      "appearance_scenes": [1, 3, 20]
    }
  ],
  "companies": [
    {
      "name": "더 핑크퐁 컴퍼니",
      "name_en": "The Pinkfong Company",
      "type": "주요기업",
      "industry": "엔터테인먼트/콘텐츠",
      "description": "아기상어 IP 보유 글로벌 패밀리 엔터테인먼트 기업"
    }
  ],
  "summary": {
    "total_scenes": 27,
    "total_persons": 1,
    "total_characters": 2,
    "total_companies": 5,
    "estimated_duration": 257
  }
}
```

---

## ⚠️ 최종 검증 체크리스트

출력 전 반드시 확인:

### 🔴🔴🔴 script_text 원본 보존 체크 (가장 중요!)
- [ ] 각 씬의 script_text가 입력 스크립트에 **정확히** 존재하는가?
- [ ] 스크립트에 없는 문장을 만들어내지 않았는가?
- [ ] 마지막 씬의 script_text가 원본 스크립트의 마지막 부분과 일치하는가?
- [ ] "구독", "좋아요", "다음 영상에서 만나요" 같은 일반 아웃트로를 추가하지 않았는가?

### 🔴 persons 체크
- [ ] 실제 사람 이름만 있는가? ("김민석" ✅, "대표" ❌, "회사의" ❌)
- [ ] 조사(의, 이, 가, 은, 는)가 포함된 단어가 없는가?
- [ ] 국가명, 일반 명사가 없는가?

### 🔴 characters 체크
- [ ] 캐릭터 IP가 있다면 추출했는가? (아기상어, 핑크퐁 등)
- [ ] `category`가 올바른가? (동물 캐릭터, 마스코트 등)

### 씬 체크
- [ ] 각 씬의 `persons`, `characters` 배열이 올바른가?
- [ ] `char_count`가 100-250 범위인가?

### 프롬프트 체크
- [ ] 모든 이미지 프롬프트에 "no text, no letters" 있는가?

### 🔴 비디오 프롬프트 체크 (⭐ 영어 필수!)
- [ ] video_prompt_character가 **영어**로 작성되었는가? (한글 ❌)
- [ ] video_prompt_full이 **영어**로 작성되었는가? (한글 ❌)
- [ ] 카메라 움직임이 포함되어 있는가? (zoom, pan, dolly 등)

---

## 💡 예시: 핑크퐁 분석 스크립트

**입력 스크립트**:
```
2020년, 하나의 영상이 유튜브 역사를 새로 썼습니다. 누적 조회수 1위.
전 세계 244개국에 퍼진 이 콘텐츠의 주인공은 아기상어였습니다.
아기상어로 유명한 더 핑크퐁 컴퍼니는 김민석 대표가 2010년에 창업했습니다.
핑크퐁이라는 분홍 여우 마스코트와 함께 어린이 콘텐츠 시장을 평정했죠.
```

**올바른 출력**:
```json
{
  "persons": [
    {"name": "김민석", "role": "창업자", "type": "person"}
  ],
  "characters": [
    {"name": "아기상어", "category": "동물 캐릭터", "type": "character_ip"},
    {"name": "핑크퐁", "category": "마스코트", "type": "character_ip"}
  ]
}
```

**❌ 잘못된 출력 (금지!)**:
```json
{
  "persons": [
    {"name": "대표"},      // ❌ 이름 없음
    {"name": "회사의"},    // ❌ 일반 단어
    {"name": "브랜드이"}   // ❌ 조사 포함
  ]
}
```

---

**[END OF PROMPT v2.4 - 스크립트 보존 강화]**

JSON 형식으로만 응답해주세요. 마크다운 코드 블록을 사용하지 마세요.'''
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

        # ═══════════════════════════════════════════════════════════════════
        # SRT 직접 적용용 프롬프트 템플릿 (v1.0)
        # ═══════════════════════════════════════════════════════════════════

        "srt_scene_single": PromptTemplate(
            id="srt_scene_single",
            name="SRT 단일 씬 분석 프롬프트 v1.0",
            category="srt_scene_analysis",
            description="SRT 직접 적용 시 단일 씬에 대한 이미지/캐릭터/비디오 프롬프트를 생성합니다.",
            prompt='''# SRT 씬 분석 프롬프트 (v1.0)

다음 씬을 분석하고 JSON으로 응답해주세요.

## 씬 정보
- 씬 번호: {scene_id}
- 시간: {start_time} - {end_time}
- 나레이션: {narration}

## 출력 형식 (반드시 JSON만 출력)
{{
    "image_prompt": "한국어 이미지 프롬프트 (상세한 시각적 묘사)",
    "image_prompt_en": "English image prompt for FLUX (detailed visual description, cinematic style)",
    "character_prompt": "한국어 캐릭터 프롬프트 (인물이 있다면)",
    "character_prompt_en": "English character prompt (if characters present)",
    "direction_guide": "연출가이드 (카메라 앵글, 조명, 분위기 등)",
    "visual_elements": ["시각요소1", "시각요소2"],
    "mood": "분위기 (예: 밝은, 어두운, 긴장감 등)",
    "characters": [
        {{"name": "캐릭터명", "visual_prompt": "English visual description of character appearance..."}}
    ],
    "location": "배경 장소",
    "video_prompt_character": "Character animation description in ENGLISH for Kling/Runway",
    "video_prompt_full": "Full scene video description in ENGLISH for Kling/Runway"
}}

## ⚠️ 중요 규칙
1. characters 배열의 각 캐릭터에는 반드시 visual_prompt를 영문으로 포함
2. video_prompt_character와 video_prompt_full은 반드시 영어로 작성
3. 카메라 움직임 포함 (zoom, pan, dolly 등)

JSON으로만 응답해주세요. 추가 설명 없이 JSON만 출력하세요.'''
        ),

        "srt_scene_batch": PromptTemplate(
            id="srt_scene_batch",
            name="SRT 배치 씬 분석 프롬프트 v1.0",
            category="srt_scene_analysis",
            description="SRT 직접 적용 시 여러 씬을 배치로 분석하여 프롬프트를 생성합니다.",
            prompt='''# SRT 배치 씬 분석 프롬프트 (v1.0)

다음 씬들을 분석하고 JSON 배열로 응답해주세요.

## 각 씬에 대해 포함할 필드
- scene_id: 씬 번호
- image_prompt: 한국어 이미지 생성 프롬프트
- image_prompt_en: 영문 이미지 프롬프트 (FLUX용, 상세하게)
- character_prompt: 한국어 캐릭터 프롬프트
- character_prompt_en: 영문 캐릭터 프롬프트
- visual_elements: 시각 요소 리스트
- direction_guide: 연출 가이드
- video_prompt_character: Character animation description (ENGLISH)
- video_prompt_full: Full scene video description (ENGLISH)
- characters: 등장 캐릭터 리스트 (각 캐릭터에 name, visual_prompt 포함!)
- location: 배경 장소
- mood: 분위기

## ⚠️ 중요 규칙
1. characters 배열의 각 캐릭터에는 반드시 visual_prompt를 영문으로 포함
   예: {{"name": "자말 카슈크지", "visual_prompt": "Middle-aged Middle Eastern man, journalist, salt-and-pepper beard..."}}
2. video_prompt_character와 video_prompt_full은 반드시 영어로 작성
3. 카메라 움직임 포함 (zoom, pan, dolly 등)

=== 분석할 씬들 ===

{scenes_content}

=== 응답 형식 ===
JSON 배열만 반환하세요. 다른 텍스트 없이 순수 JSON만 출력하세요.
```json
[
  {{
    "scene_id": 1,
    "image_prompt": "...",
    "image_prompt_en": "...",
    "characters": [
      {{"name": "캐릭터명", "visual_prompt": "영문 외모 설명..."}}
    ],
    "video_prompt_character": "English character animation...",
    "video_prompt_full": "English full scene description...",
    ...
  }},
  ...
]
```'''
        ),
    }

    def __init__(self):
        _debug_log(f"초기화 시작")
        _debug_log(f"  설정 파일 경로: {self.CONFIG_PATH}")
        _debug_log(f"  설정 파일 존재: {self.CONFIG_PATH.exists()}")

        self.templates: Dict[str, PromptTemplate] = {}
        self._load_templates()

        # 🔴 v3.10: 자동 마이그레이션 실행 (Problem 55)
        self._auto_migrate_templates()

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

        # 저장된 템플릿 로드 (기본 템플릿 덮어쓰기 + 커스텀 템플릿 추가)
        if self.CONFIG_PATH.exists():
            try:
                with open(self.CONFIG_PATH, "r", encoding="utf-8") as f:
                    saved = json.load(f)

                _debug_log(f"  JSON 파일에서 {len(saved)}개 항목 발견")

                custom_count = 0
                for key, data in saved.items():
                    is_default = data.get("is_default", True)

                    # 기존 기본 템플릿 업데이트 또는 새 커스텀 템플릿 추가
                    if key in self.templates:
                        # 기본 템플릿 덮어쓰기 (수정된 경우)
                        existing = self.templates[key]
                        self.templates[key] = PromptTemplate(
                            id=key,
                            name=data.get("name", existing.name),
                            category=data.get("category", getattr(existing, 'category', 'general')),
                            description=data.get("description", existing.description),
                            prompt=data.get("prompt", existing.prompt),
                            is_default=is_default,
                            updated_at=data.get("updated_at", "")
                        )
                        if not is_default:
                            custom_count += 1
                            _debug_log(f"  ✏️ 기본 템플릿 수정됨: {key}")
                    else:
                        # 🔧 수정: 새 커스텀 템플릿 추가 (기본 템플릿에 없는 것도 로드!)
                        self.templates[key] = PromptTemplate(
                            id=key,
                            name=data.get("name", key),
                            category=data.get("category", "general"),
                            description=data.get("description", ""),
                            prompt=data.get("prompt", ""),
                            is_default=is_default,
                            updated_at=data.get("updated_at", "")
                        )
                        if not is_default:
                            custom_count += 1
                            _debug_log(f"  ✅ 커스텀 템플릿 로드됨: {key} (이름: {data.get('name', key)})")

                _debug_log(f"  저장된 템플릿에서 {custom_count}개 커스텀 로드됨")
                _debug_log(f"  총 템플릿 수: {len(self.templates)}")

            except Exception as e:
                _debug_log(f"❌ 템플릿 로드 실패: {e}")
                import traceback
                _debug_log(f"  상세 오류: {traceback.format_exc()}")
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

    # ==================== 🔴 v3.10: 자동 마이그레이션 시스템 (Problem 55) ====================

    def _auto_migrate_templates(self):
        """
        🔴 자동 마이그레이션: 구버전 템플릿을 최신 버전으로 업그레이드

        앱 시작 시 자동으로 실행되어:
        1. 모든 템플릿의 버전 확인
        2. 구버전(v2.3 등)이면 최신 버전(v2.4)으로 업그레이드
        3. 필수 내용 추가 (스크립트 보존 규칙 등)
        4. JSON 파일 자동 저장
        """
        current_version = PromptTemplateVersion.CURRENT_VERSION
        updated_count = 0
        migration_log = []

        _debug_log(f"🔄 자동 마이그레이션 시작 (현재 버전: {current_version})")

        for template_id, template in self.templates.items():
            prompt_text = template.prompt
            detected_version = PromptTemplateVersion.detect_version(prompt_text)

            # 버전이 낮으면 업그레이드
            if PromptTemplateVersion.is_older_version(detected_version, current_version):
                _debug_log(f"  🔄 마이그레이션 필요: {template.name} ({detected_version} → {current_version})")

                # 프롬프트 업그레이드
                upgraded_prompt = self._upgrade_prompt_content(
                    prompt_text,
                    detected_version,
                    current_version
                )

                # 템플릿 업데이트
                self.templates[template_id] = PromptTemplate(
                    id=template.id,
                    name=template.name,
                    category=template.category,
                    description=template.description,
                    prompt=upgraded_prompt,
                    is_default=template.is_default,
                    updated_at=datetime.now().isoformat()
                )

                migration_log.append({
                    'template_id': template_id,
                    'template_name': template.name,
                    'from_version': detected_version,
                    'to_version': current_version,
                })
                updated_count += 1

        if updated_count > 0:
            self._save_templates()
            _debug_log(f"✅ 마이그레이션 완료: {updated_count}개 템플릿 업그레이드됨")
            for log in migration_log:
                _debug_log(f"    - {log['template_name']}: {log['from_version']} → {log['to_version']}")
        else:
            _debug_log(f"✅ 모든 템플릿이 최신 버전입니다 ({current_version})")

    def _upgrade_prompt_content(self, prompt: str, from_version: str, to_version: str) -> str:
        """
        프롬프트 내용 업그레이드

        버전별 업그레이드 내용:
        - v2.3 → v2.4: 스크립트 보존 규칙 추가
        """
        upgraded = prompt

        # 버전 문자열 변경 (v2.3 → v2.4)
        if from_version in upgraded:
            upgraded = upgraded.replace(from_version, to_version)

        # v2.4 필수 내용 추가: 스크립트 보존 규칙
        if to_version == 'v2.4':
            if '스크립트 원본 보존' not in upgraded:
                # 프롬프트 시작 부분에 규칙 추가
                # 제목 뒤에 삽입
                if '---' in upgraded:
                    # 첫 번째 --- 뒤에 삽입
                    parts = upgraded.split('---', 1)
                    if len(parts) == 2:
                        upgraded = parts[0] + '---\n\n' + PromptTemplateVersion.SCRIPT_PRESERVATION_RULE + parts[1]
                else:
                    # --- 없으면 맨 앞에 추가
                    upgraded = PromptTemplateVersion.SCRIPT_PRESERVATION_RULE + '\n\n' + upgraded

                _debug_log(f"    → 스크립트 원본 보존 규칙 추가됨")

        return upgraded

    def verify_template_version(self, template_id: str) -> dict:
        """
        템플릿 버전 검증

        Returns:
            dict: {
                'template_id': str,
                'template_name': str,
                'detected_version': str,
                'expected_version': str,
                'is_latest': bool,
                'missing_features': list,
                'needs_migration': bool,
            }
        """
        template = self.templates.get(template_id)
        if not template:
            return {
                'template_id': template_id,
                'template_name': 'Unknown',
                'detected_version': 'unknown',
                'expected_version': PromptTemplateVersion.CURRENT_VERSION,
                'is_latest': False,
                'missing_features': [],
                'needs_migration': True,
            }

        prompt_text = template.prompt
        detected_version = PromptTemplateVersion.detect_version(prompt_text)
        expected_version = PromptTemplateVersion.CURRENT_VERSION

        # 필수 내용 확인
        missing_features = []
        required = PromptTemplateVersion.VERSION_REQUIRED_CONTENT.get(expected_version, [])

        for feature in required:
            if feature not in prompt_text:
                missing_features.append(feature)

        is_latest = (detected_version == expected_version) and len(missing_features) == 0

        return {
            'template_id': template_id,
            'template_name': template.name,
            'detected_version': detected_version,
            'expected_version': expected_version,
            'is_latest': is_latest,
            'missing_features': missing_features,
            'needs_migration': not is_latest,
        }

    def verify_all_templates(self) -> List[dict]:
        """모든 템플릿 버전 검증"""
        results = []
        for template_id in self.templates:
            result = self.verify_template_version(template_id)
            results.append(result)
        return results

    def force_migrate_all(self) -> dict:
        """
        모든 템플릿 강제 마이그레이션

        UI에서 "모든 템플릿 최신화" 버튼 클릭 시 호출
        """
        before_count = len(self.templates)
        migrated_count = 0
        current_version = PromptTemplateVersion.CURRENT_VERSION

        for template_id, template in self.templates.items():
            prompt_text = template.prompt
            detected_version = PromptTemplateVersion.detect_version(prompt_text)

            if detected_version != current_version:
                upgraded_prompt = self._upgrade_prompt_content(
                    prompt_text,
                    detected_version,
                    current_version
                )

                self.templates[template_id] = PromptTemplate(
                    id=template.id,
                    name=template.name,
                    category=template.category,
                    description=template.description,
                    prompt=upgraded_prompt,
                    is_default=template.is_default,
                    updated_at=datetime.now().isoformat()
                )
                migrated_count += 1

        if migrated_count > 0:
            self._save_templates()

        return {
            'total_templates': before_count,
            'migrated_count': migrated_count,
            'current_version': current_version,
        }

    # ==================== 마이그레이션 시스템 끝 ====================

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

    # ═══════════════════════════════════════════════════════════════════
    # SRT 분석 프롬프트 관련 헬퍼 메서드
    # ═══════════════════════════════════════════════════════════════════

    def get_srt_templates(self) -> List[PromptTemplate]:
        """SRT 분석 프롬프트 템플릿 목록 반환"""
        return self.get_templates_by_category("srt_scene_analysis")

    def get_srt_single_template(self) -> Optional[PromptTemplate]:
        """SRT 단일 씬 분석 프롬프트 반환 (기본값)"""
        return self.get_template("srt_scene_single")

    def get_srt_batch_template(self) -> Optional[PromptTemplate]:
        """SRT 배치 씬 분석 프롬프트 반환 (기본값)"""
        return self.get_template("srt_scene_batch")

    def get_srt_single_prompt(self) -> str:
        """SRT 단일 씬 분석 프롬프트 텍스트 반환"""
        return self.get_prompt("srt_scene_single")

    def get_srt_batch_prompt(self) -> str:
        """SRT 배치 씬 분석 프롬프트 텍스트 반환"""
        return self.get_prompt("srt_scene_batch")

    def create_srt_template(self, name: str, description: str, prompt: str) -> Optional[PromptTemplate]:
        """새 SRT 분석 프롬프트 템플릿 생성"""
        return self.create_template("srt_scene_analysis", name, description, prompt)

    # ═══════════════════════════════════════════════════════════════════

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
