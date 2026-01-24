# 씬 분석 프롬프트 템플릿

## 입력 데이터 구조

```json
{
  "scene_number": 1,
  "script": "여러분, 삼성전자 하면 뭐가 떠오르세요?",
  "start_time": "00:00:00,000",
  "end_time": "00:00:03,500",
  "bundle_id": 1,
  "is_primary": true
}
```

## 출력 데이터 구조

```json
{
  "scene_number": 1,
  "script": "여러분, 삼성전자 하면 뭐가 떠오르세요?",
  "start_time": "00:00:00,000",
  "end_time": "00:00:03,500",
  "bundle_id": 1,
  "is_primary": true,

  "background_prompt_en": "Modern conference room with large presentation screen, warm ambient lighting, professional corporate atmosphere, glass windows overlooking city skyline, sleek minimalist furniture, 2D animation style, clean bold outlines",

  "character_prompt_en": "Professional Korean male presenter in business casual attire, confident stance, gesturing while speaking, friendly expression, mid-30s, 2D animated character style",

  "characters": ["진행자"],

  "visual_elements": "프레젠테이션 스크린, 회의실, 도시 전망",

  "scene_mood": "professional, engaging, informative",

  "korean_text_overlay": "삼성전자 하면?",

  "direction_guide": "진행자가 시청자에게 질문을 던지며 관심을 유도하는 장면"
}
```

## 분석 규칙

### 배경 프롬프트 (background_prompt_en)
1. 영어로 작성
2. 장소, 조명, 분위기, 색감 포함
3. **사람 묘사 절대 금지** - 배경만 묘사
4. "2D animation style" 포함
5. 80-150 단어 권장

### 캐릭터 프롬프트 (character_prompt_en)
1. 영어로 작성
2. 성별, 연령대, 복장, 표정, 포즈 포함
3. "2D animated character style" 포함
4. 50-100 단어 권장

### 캐릭터 목록 (characters)
1. 스크립트에서 화자 또는 언급된 인물 추출
2. 한국어 역할명 사용 (예: "진행자", "앵커", "전문가")
3. 배열 형태로 저장

### 시각 요소 (visual_elements)
1. 한국어로 작성
2. 화면에 보여야 할 주요 오브젝트 나열
3. 쉼표로 구분

### 씬 분위기 (scene_mood)
1. 영어로 작성
2. 2-3개의 형용사
3. 쉼표로 구분

## 묶음 처리 규칙

동일한 `bundle_id`를 가진 씬들:
1. 첫 번째 씬(`is_primary: true`)만 전체 분석
2. 나머지 씬들은 첫 번째 씬의 프롬프트 복사:
   - `background_prompt_en` 복사
   - `character_prompt_en` 복사
   - `characters` 복사
3. 개별 필드는 각 씬마다 생성:
   - `visual_elements`
   - `scene_mood`
   - `korean_text_overlay`
   - `direction_guide`
