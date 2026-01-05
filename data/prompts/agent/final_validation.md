# 최종 SRT 검증 에이전트

## 역할
SRT 자막과 원문 스크립트를 최종 비교하여 남은 오타를 모두 수정합니다.

## 입력 데이터
- `input/srt_scenes.json`: 교정된 SRT 씬 리스트
- `input/original_script.txt`: 원문 스크립트

## 작업 절차

### Step 1: 전체 텍스트 추출
SRT의 모든 텍스트를 하나로 연결:
```
씬1 텍스트 + 씬2 텍스트 + ... + 씬N 텍스트
```

### Step 2: 원문과 문장 매칭
각 SRT 씬을 원문의 가장 유사한 부분과 매칭:
- 유사도 95% 이상: 정상
- 유사도 95% 미만: 교정 필요

### Step 3: 불일치 교정
유사도가 낮은 씬들을 교정:
- 원문 기준으로 수정
- 단어 단위로 비교하여 차이점 찾기

### Step 4: 최종 SRT 생성
`output/final_srt.json` 파일로 저장:
```json
{
  "final_corrections": [
    {
      "scene_id": 45,
      "original_srt": "사업뿐만 큼 돈을 버는",
      "corrected": "사업부만큼 돈을 버는",
      "similarity_before": 0.87,
      "similarity_after": 1.0
    }
  ],
  "total_final_corrections": 15,
  "final_scenes": [...]
}
```

## 규칙
1. 모든 씬을 원문과 비교
2. 유사도 95% 미만은 반드시 교정
3. 원문에 없는 내용 추가 X
4. 최종 오타 0개 목표

## 시작
작업을 수행하고 결과를 저장하세요.
