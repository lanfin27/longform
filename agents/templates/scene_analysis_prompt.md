# 씬 분석 프롬프트 템플릿 (v2.0 - 16개 전체 필드)

## 입력 데이터 구조

```json
{
  "scene_id": 47,
  "scene_number": 47,
  "script_text": "당시 이재용 부회장이었는데,",
  "start_time": "00:01:43,878",
  "end_time": "00:01:45,878",
  "bundle_id": 2,
  "is_bundle_primary": true
}
```

## 🔴 출력 데이터 구조 (16개 필드 필수!)

```json
{
  "scene_id": 47,
  "scene_number": 47,
  "script_text": "당시 이재용 부회장이었는데,",
  "start_time": "00:01:43,878",
  "end_time": "00:01:45,878",
  "bundle_id": 2,
  "is_bundle_primary": true,

  "image_prompt": "이재용 부회장이 스피커가 아닌 자동차의 미래를 보는 모습, 날카로운 눈빛, 미래지향적인 자동차 디자인",

  "image_prompt_en": "Lee Jae-yong (then Vice Chairman) gazing intently at a futuristic car interior, sharp focus on his determined expression and visionary gaze, sleek modern automotive design with advanced technology integration, subtle Harman logo on dashboard display, sense of foresight and strategic thinking, confident and forward-looking posture, luxurious and technologically advanced car cabin, no text, no letters, no words, no writing, no numbers, no speech bubbles, no readable text, brand logos are acceptable",

  "background_prompt": "미래지향적인 자동차 내부 디자인, 첨단 기술, Harman 로고",

  "background_prompt_en": "Futuristic car interior with advanced dashboard display, Harman audio system integration, sleek modern automotive design, ambient lighting, no text, no letters, no words, no writing, no numbers, no speech bubbles, no readable text, brand logos are acceptable",

  "character_prompt": "날카로운 눈빛의 이재용 부회장",

  "character_prompt_en": "Lee Jae-yong, then Vice Chairman, with a sharp, determined expression and visionary gaze",

  "image_prompt_korean_text": "Lee Jae-yong gazing at futuristic car interior, visionary gaze, sleek automotive design, headline text in Korean reading \"스피커가 아닌\" at the top in handwritten pen script style with casual brush strokes, subtitle text in Korean reading \"자동차의 미래를 보다\" in the upper area in informal handwritten font style, all Korean text in natural hand-drawn pen calligraphy style with slight irregularity, text positioned harmoniously within the upper 70% of the image avoiding the bottom subtitle area",

  "korean_text": "Lee Jae-yong gazing at futuristic car interior, visionary gaze, sleek automotive design, headline text in Korean reading \"스피커가 아닌\" at the top in handwritten pen script style with casual brush strokes, subtitle text in Korean reading \"자동차의 미래를 보다\" in the upper area in informal handwritten font style, all Korean text in natural hand-drawn pen calligraphy style with slight irregularity, text positioned harmoniously within the upper 70% of the image avoiding the bottom subtitle area",

  "visual_elements": ["이재용", "미래 자동차", "Harman 로고", "첨단 기술"],

  "direction_guide": "이재용 부회장의 날카로운 눈빛과 미래를 보는 비전을 강조, 자동차 디자인에 Harman 로고를 자연스럽게 통합",

  "camera_suggestion": "Close-up, slow push in",

  "video_prompt_character": "Close up of Lee Jae-yong's face with a determined expression",

  "video_prompt_full": "Camera focuses on Lee Jae-yong's face in a sleek car interior, then pans across the futuristic dashboard",

  "characters": [
    {
      "name": "이재용",
      "visual_prompt": "Lee Jae-yong, then Vice Chairman, with a sharp, determined expression and visionary gaze"
    }
  ],

  "location": "미래 자동차 내부",

  "mood": "결단력 있고 미래지향적인"
}
```

---

## 📋 필드별 규칙

### 1. image_prompt (한글)
- 한글로 작성
- 씬의 핵심 시각적 컨셉 요약
- 30-50자 권장

### 2. image_prompt_en (영어) ⭐ 가장 중요
- **영어로 작성**
- 상세하고 구체적인 시각적 묘사
- 80-150 단어
- **끝에 반드시 추가**: `no text, no letters, no words, no writing, no numbers, no speech bubbles, no readable text, brand logos are acceptable`

### 3. background_prompt (한글)
- 한글로 작성
- 배경/장소 핵심 요소만

### 4. background_prompt_en (영어)
- **영어로 작성**
- **사람/캐릭터 묘사 절대 금지** - 순수 배경만!
- 텍스트 금지 문구 포함

### 5. character_prompt (한글)
- 한글로 작성
- 캐릭터가 없으면 빈 문자열 ""

### 6. character_prompt_en (영어)
- 영어로 작성
- 성별, 연령대, 복장, 표정, 포즈 포함
- 캐릭터가 없으면 빈 문자열 ""

### 7. image_prompt_korean_text (영어)
- **영어로 작성**하되 **한글 텍스트를 따옴표 안에 포함**
- 텍스트 위치: 이미지 상단 70% 영역
- 스타일: handwritten pen script, casual brush strokes

### 8. korean_text (영어)
- `image_prompt_korean_text`와 동일한 값

### 9. visual_elements (배열)
- 한글 배열
- 씬에 포함될 주요 시각 요소

### 10. direction_guide (한글)
- 한글로 작성
- 연출 의도와 핵심 포인트

### 11. camera_suggestion (영어)
- 영어로 작성
- 카메라 앵글/움직임 제안
- 없으면 빈 문자열 ""

### 12. video_prompt_character (영어)
- 영어로 작성
- 캐릭터 중심 비디오 묘사
- 캐릭터가 없으면 빈 문자열 ""

### 13. video_prompt_full (영어)
- 영어로 작성
- 전체 씬의 비디오 시퀀스 묘사
- 카메라 움직임 포함

### 14. characters (배열)
- 캐릭터가 없으면 빈 배열 `[]`
- `name`: 한글
- `visual_prompt`: 영어

### 15. location (한글)
- 한글로 작성
- 씬의 장소/배경 위치

### 16. mood (한글)
- 한글로 작성
- 씬의 전체적인 분위기

---

## 묶음 처리 규칙

동일한 `bundle_id`를 가진 씬들:
1. 첫 번째 씬(`is_bundle_primary: true`)만 전체 분석
2. 나머지 씬들은 첫 번째 씬의 **모든 16개 필드** 복사

---

## 🚫 텍스트 금지 문구 (영어 프롬프트 끝에 추가)

```
no text, no letters, no words, no writing, no numbers, no speech bubbles, no readable text, brand logos are acceptable
```
