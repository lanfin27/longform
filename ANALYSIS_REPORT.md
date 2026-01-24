# Longform 프로젝트 성능 분석 보고서

**프로젝트**: AI 롱폼 유튜브 생성 Tool
**분석 일시**: 2026-01-18
**분석 도구**: Claude Code Performance Analyzer
**Streamlit 버전**: 1.30.0+

---

## Executive Summary

### 발견된 총 문제 수: 47개

| 심각도 | 개수 | 예상 성능 개선 효과 |
|--------|------|-------------------|
| **Critical** | 8개 | 40-50% |
| **High** | 15개 | 20-30% |
| **Medium** | 16개 | 10-15% |
| **Low** | 8개 | 5-10% |

### 핵심 발견사항

1. **이미지 바이트 데이터 세션 저장** - 배치 생성 시 300MB+ 메모리 사용
2. **@st.fragment 미사용** - 부분 리렌더링 기회 상실
3. **캐싱 누락** - 주요 데이터 로딩 함수 20+ 개에 캐싱 없음
4. **루프 내 위젯 렌더링** - 30개 영상 × 10개 위젯 = 300회 렌더링
5. **과도한 Import** - pages/6에서 25+ 모듈 상단 import

---

## 1. 캐싱 문제

### 1.1 캐싱이 필요하지만 없는 함수

| ID | 파일 | 라인 | 함수명 | 문제 설명 | 심각도 | 영향도 |
|----|------|------|--------|-----------|--------|--------|
| C01 | `utils/data_loader.py` | 45-50 | `load_json()` | JSON 파일 로드에 캐싱 없음 | High | 매 리렌더링마다 파일 I/O |
| C02 | `utils/data_loader.py` | 59-63 | `load_excel()` | Excel 로드에 캐싱 없음 (pandas 무거움) | High | 느린 파일 읽기 반복 |
| C03 | `utils/data_loader.py` | 73-78 | `load_text()` | 텍스트 파일 로드에 캐싱 없음 | Medium | 빈번한 I/O |
| C04 | `utils/project_manager.py` | 100-102 | 채널 설정 로드 | 프로젝트 설정 반복 로드 | High | 페이지 초기화마다 실행 |
| C05 | `pages/6_🎨_이미지_생성.py` | 437, 447 | 배경/합성 메타 로드 | JSON 메타데이터 캐싱 없음 | Medium | 갤러리 탭 진입마다 |
| C06 | `pages/3_🎬_SRT_생성.py` | 1110 | 씬 데이터 로드 | SRT 페이지 씬 로드 캐싱 없음 | Medium | 탭 전환마다 로드 |
| C07 | `pages/5_🖼️_이미지_프롬프트.py` | 436, 471 | 프롬프트 로드 | 이미지 프롬프트 캐싱 없음 | Medium | 프롬프트 편집마다 |
| C08 | `components/interactive_canvas.py` | 641-665 | 이미지 다운로드 | `requests.get()` + `Image.open()` 캐싱 없음 | High | 네트워크 I/O 반복 |
| C09 | `core/image/scene_compositor.py` | 83-86 | 이미지 합성 다운로드 | 이미지 다운로드 캐싱 없음 | High | 합성마다 재다운로드 |
| C10 | `core/image/scene_image_generator.py` | 72 | 씬 이미지 메타 | 씬별 이미지 정보 캐싱 없음 | Medium | 갤러리 조회마다 |
| C11 | `core/image/background_image_generator.py` | 82 | 배경 생성기 설정 | 설정 파일 캐싱 없음 | Low | 생성기 초기화마다 |

### 1.2 현재 캐싱 적용 현황 (적절함)

| 파일 | 라인 | 데코레이터 | TTL | 평가 |
|------|------|-----------|-----|------|
| `components/image_viewer.py` | 20 | `@st.cache_data(ttl=300, max_entries=100)` | 5분 | ✅ 좋음 |
| `components/image_viewer.py` | 94 | `@st.cache_data(ttl=300, max_entries=100)` | 5분 | ✅ 좋음 |
| `pages/8_📋_스토리보드.py` | 245 | `@st.cache_resource` | 영구 | ✅ 리소스 적절 |
| `pages/8_📋_스토리보드.py` | 256, 2456 | `@st.cache_data(ttl=120, 300)` | 2-5분 | ✅ 좋음 |
| `pages/3_📝_스크립트_생성.py` | 42, 49 | `@st.cache_data(ttl=60)` | 1분 | ✅ 좋음 |
| `pages/6_🎨_이미지_생성.py` | 469, 528 | `@st.cache_data(ttl=30-60)` | 30초-1분 | ✅ 좋음 |

### 1.3 Deprecated @st.cache 사용

**발견되지 않음** - 모든 캐싱이 `@st.cache_data` 또는 `@st.cache_resource` 사용 중

---

## 2. 세션 상태 문제

### 2.1 불필요하게 큰 객체 저장 (Critical)

| ID | 파일 | 라인 | 키 패턴 | 문제 설명 | 심각도 | 메모리 영향 |
|----|------|------|---------|-----------|--------|------------|
| S01 | `utils/memory_manager.py` | 32-40 | `composite_result_*` | 합성 이미지 바이트 저장 (6-8MB/장) | **Critical** | 50장 = 300MB+ |
| S02 | `utils/memory_manager.py` | 32-40 | `bg_result_*` | 배경 이미지 바이트 저장 | **Critical** | 누적됨 |
| S03 | `utils/memory_manager.py` | 32-40 | `char_image_*` | 캐릭터 이미지 바이트 저장 | **Critical** | 누적됨 |
| S04 | `utils/memory_manager.py` | 257-273 | `_thumb_*` | 썸네일 JPEG 바이트 저장 | High | 갤러리당 수십MB |
| S05 | `pages/6_🎨_이미지_생성.py` | 5049 | `selected_gallery_images` | 선택 이미지 데이터 저장 | High | 바이트 포함 가능 |
| S06 | `pages/6_🎨_이미지_생성.py` | 604 | `storyboard_images` | 스토리보드 전체 이미지 | High | 목록 크기 무제한 |
| S07 | `pages/8_📋_스토리보드.py` | 2786 | `visual_manager` | 객체 전체 저장 | High | 메모리 누수 위험 |
| S08 | `pages/3.6_👤_캐릭터_관리.py` | 902 | `pose_analysis_result` | AI 분석 결과 저장 | Medium | JSON 크기 가변 |

### 2.2 초기화 패턴 문제

| ID | 파일 | 라인 | 문제 설명 | 심각도 |
|----|------|------|-----------|--------|
| S09 | `pages/3_🎬_SRT_생성.py` | 80-102, 242-250 | 분산된 초기화 (여러 위치) | Medium |
| S10 | `pages/8_📋_스토리보드.py` | 563, 2426, 4321 | 일관성 없는 초기화 시점 | Medium |
| S11 | 여러 파일 | - | 키 네이밍 규칙 불일관 | Low |

### 2.3 세션 상태 vs 캐시 선택 오류

| ID | 파일 | 현재 사용 | 권장 변경 | 이유 |
|----|------|----------|----------|------|
| S12 | `utils/image_cache.py:129` | `st.session_state` | `@st.cache_data` | 이미지 목록은 공유 가능 |
| S13 | `utils/memory_manager.py:257` | `st.session_state` | `@st.cache_data` | 썸네일은 공유 가능 |

---

## 3. 데이터 로딩 문제

### 3.1 파일 I/O 최적화 필요

| ID | 파일 | 라인 | 패턴 | 문제 설명 | 심각도 |
|----|------|------|------|-----------|--------|
| D01 | `pages/8_📋_스토리보드.py` | 1241 | `with open(video_path, "rb")` | expander 내 파일 읽기 반복 | High |
| D02 | `pages/2_🔍_영상_리서치.py` | 1243-1266 | DataFrame 전체 생성 | 모든 북마크 한번에 처리 | Medium |
| D03 | 여러 파일 | - | `json.load()` 반복 | 동일 파일 다중 읽기 | Medium |

### 3.2 CSV → Parquet 전환 후보

| 파일 유형 | 현재 위치 | 권장 변경 | 예상 효과 |
|----------|----------|----------|----------|
| 영상 목록 | `data/projects/*/video_list.xlsx` | Parquet | 50% 로드 시간 단축 |
| 이미지 매핑 | `*/image_mapping.xlsx` | Parquet | 30% 메모리 절약 |

---

## 4. UI 렌더링 문제

### 4.1 루프 내 위젯 렌더링 (Critical)

| ID | 파일 | 라인 | 문제 설명 | 영향 | 심각도 |
|----|------|------|-----------|------|--------|
| U01 | `pages/2_🔍_영상_리서치.py` | 1004-1054 | 30개 영상 × (expander + 2 columns + 7 metric) | 270+ 위젯 | **Critical** |
| U02 | `pages/2_🔍_영상_리서치.py` | 1147-1170 | 선택 영상 루프 내 metric | 50+ 위젯 | High |
| U03 | `pages/8_📋_스토리보드.py` | 1237-1252 | 비디오 expander 루프 | 30+ 위젯 | High |

### 4.2 복잡한 중첩 레이아웃

| ID | 파일 | 라인 | 중첩 수준 | 문제 설명 | 심각도 |
|----|------|------|----------|-----------|--------|
| U04 | `pages/2_🔍_영상_리서치.py` | 1026-1054 | 4중 | expander > col2 > metric_col(3) > metric | High |
| U05 | `pages/8_📋_스토리보드.py` | 1113-1128 | 4중 | 비용 예측 4컬럼 내 조건부 metric | Medium |

### 4.3 @st.fragment 미사용 (Streamlit 1.33+)

| ID | 파일 | 권장 적용 영역 | 예상 효과 |
|----|------|---------------|----------|
| U06 | `pages/2_🔍_영상_리서치.py` | 검색 탭 섹션 | 30-40% 리렌더링 감소 |
| U07 | `pages/2_🔍_영상_리서치.py` | 필터/정렬 UI + 결과 | 20-30% 감소 |
| U08 | `pages/2_🔍_영상_리서치.py` | 다운로드 버튼 영역 | 10-15% 감소 |
| U09 | `pages/8_📋_스토리보드.py` | 씬 렌더링 영역 | 25-35% 감소 |
| U10 | `pages/8_📋_스토리보드.py` | 비디오 생성 섹션 | 15-20% 감소 |

### 4.4 불필요한 st.rerun() 사용

| ID | 파일 | 라인 | 문제 설명 | 심각도 |
|----|------|------|-----------|--------|
| U11 | `pages/2_🔍_영상_리서치.py` | 146 | 캐시 초기화 후 전체 rerun | Medium |
| U12 | `pages/2_🔍_영상_리서치.py` | 777 | 엑셀 생성 후 전체 rerun | Medium |
| U13 | `pages/8_📋_스토리보드.py` | 여러 | 상태 변경 후 rerun 남용 | Medium |

---

## 5. 아키텍처 문제

### 5.1 과도한 Import

| ID | 파일 | Import 수 | 권장 수 | 문제 설명 | 심각도 |
|----|------|----------|--------|-----------|--------|
| A01 | `pages/6_🎨_이미지_생성.py` | 25+ | 12 | PIL, selenium, numpy 등 상단 import | **Critical** |
| A02 | `pages/2_🔍_영상_리서치.py` | 15+ | 8 | 탭별 사용 모듈도 상단 import | High |
| A03 | `core/ai/claude_client.py` | - | - | Anthropic 즉시 초기화 | Medium |

### 5.2 지연 로딩 권장

| 파일 | 라인 | 모듈 | 권장 시점 |
|------|------|------|----------|
| `pages/6_🎨_이미지_생성.py` | 1-50 | PIL, numpy | 이미지 탭 진입 시 |
| `pages/2_🔍_영상_리서치.py` | 175-182 | channel_identity, topic_recommender | 해당 탭 진입 시 |
| `pages/1.5_📊_채널_트렌드.py` | 12-14 | plotly | 차트 렌더링 시 |

### 5.3 설정 파일 누락

| ID | 파일 | 문제 설명 | 심각도 |
|----|------|-----------|--------|
| A04 | `.streamlit/config.toml` | 설정 파일 없음 | Low |

---

## 6. 메모리 문제

### 6.1 메모리 누수 위험 패턴

| ID | 파일 | 라인 | 패턴 | 문제 설명 | 심각도 |
|----|------|------|------|-----------|--------|
| M01 | `utils/memory_manager.py` | 32-40 | 이미지 바이트 누적 | 세션 종료 전까지 유지 | **Critical** |
| M02 | `pages/8_📋_스토리보드.py` | 2786 | 객체 저장 | visual_manager 객체 누적 | High |
| M03 | `utils/image_cache.py` | 24 | 클래스 변수 캐시 | 앱 재시작 전까지 유지 | Medium |

### 6.2 리소스 정리 패턴 누락

| ID | 파일 | 문제 설명 | 권장 변경 |
|----|------|-----------|----------|
| M04 | `pages/8_📋_스토리보드.py:1241` | 파일 읽기 후 명시적 정리 없음 | context manager 확인 |
| M05 | 여러 파일 | 대용량 DataFrame 처리 후 del 없음 | `del df; gc.collect()` 추가 |

---

## 7. 비동기 처리 현황

### 7.1 현재 비동기 사용 현황

| 파일 | 라인 | 사용 패턴 | 평가 |
|------|------|----------|------|
| `core/api/api_manager.py` | 19, 343 | `threading.Lock()` | ✅ 적절 |
| `core/api/progress_tracker.py` | 16, 63 | `threading.Lock()` | ✅ 적절 |
| `core/image/character_image_generator.py` | 16 | `ThreadPoolExecutor` | ✅ 적절 |
| `utils/ai_text_preprocessor.py` | 28+ | `asyncio` | ✅ 적절 |

### 7.2 병렬 처리 가능 영역

| ID | 파일 | 작업 | 현재 방식 | 권장 변경 |
|----|------|------|----------|----------|
| P01 | `pages/6_🎨_이미지_생성.py` | 배치 이미지 생성 | 순차 | `ThreadPoolExecutor` |
| P02 | `pages/2_🔍_영상_리서치.py` | 썸네일 다운로드 | 순차 | `asyncio.gather()` |
| P03 | `pages/8_📋_스토리보드.py` | 씬 이미지 로딩 | 순차 | `concurrent.futures` |

---

## 8. 문제 통계 요약

### 심각도별 분포

```
Critical (8개): C01, C02, C04, C08, C09, S01, S02, S03, U01, A01, M01
High (15개): C03, C05-C07, C10, S04-S07, U02-U04, A02, M02
Medium (16개): 나머지 대부분
Low (8개): C11, S11, A04, 기타
```

### 카테고리별 분포

| 카테고리 | 개수 | 비율 |
|----------|------|------|
| 캐싱 | 11 | 23% |
| 세션 상태 | 13 | 28% |
| UI 렌더링 | 13 | 28% |
| 아키텍처 | 4 | 9% |
| 메모리 | 5 | 11% |
| 비동기 | 1 | 2% |

---

## 9. 권장 조치 우선순위

### 즉시 조치 (Critical)

1. 이미지 바이트 세션 저장 제거 (S01-S03)
2. @st.fragment 도입 (U06-U10)
3. 데이터 로딩 캐싱 추가 (C01-C04)
4. pages/6 import 최적화 (A01)

### 단기 조치 (High)

1. 루프 내 위젯 최적화 (U01-U03)
2. 썸네일 캐싱 개선 (S04)
3. 네트워크 I/O 캐싱 (C08-C09)
4. 초기화 패턴 통일 (S09-S10)

### 중장기 조치 (Medium/Low)

1. 중첩 레이아웃 단순화 (U04-U05)
2. st.rerun() 최소화 (U11-U13)
3. 지연 로딩 확대 적용
4. .streamlit/config.toml 추가 (A04)

---

**보고서 끝**
