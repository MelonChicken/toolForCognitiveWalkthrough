# Visualization Guide

이 폴더는 브라우저 로그 JSON을 분석하고 시각화 결과를 생성하는 전용 공간입니다.

## Files

- `visualize_log_pipeline.py`: 시각화 파이프라인 본체
- `__init__.py`: 패키지 인식용 파일

루트의 [visualize_log_pipeline.py](/C:/Users/osca0/Github/toolForCW/visualize_log_pipeline.py)는 기존 실행 호환성을 위한 래퍼입니다.

## Input

입력은 확장 프로그램에서 export한 세션 JSON 1개입니다.

- `events[]`가 있어야 합니다.
- 구형 시간 형식과 신형 시간 형식을 모두 읽습니다.
- `back_navigation` 이벤트가 있으면 뒤로가기 횟수에 반영됩니다.

## Metrics

페이지 방문 단위:

- `eventCount`
- `click_count`
- `scroll_count`
- `keyinput_count`
- `mousemove_count`
- `focus_blur_count`
- `duration_sec`
- `entry_type`

태스크 단위:

- `total_task_time_sec`
- `page_visit_count`
- `back_navigation_count`
- `total_event_count`

## Output

출력 디렉터리에 아래 파일이 생성됩니다.

CSV:

- `normalized_events.csv`
- `page_visits.csv`
- `page_metrics.csv`
- `task_metrics.csv`
- `transitions.csv`

Images:

- `task_summary.png`
- `page_metrics.png`
- `transition_graph.png`
- `timeline.png`

HTML:

- `report.html`

## Visualizations

`task_summary.png`

- 태스크 전체 수행 시간
- 전체 페이지 방문 수
- 뒤로가기 횟수
- 전체 상호작용 이벤트 수

`page_metrics.png`

- 페이지 방문별 `eventCount`
- 페이지 방문별 상호작용 분해
- 페이지 방문별 체류 시간

`transition_graph.png`

- 페이지 간 이동 관계
- 각 페이지의 누적 체류 시간
- `back_navigation` 포함 전이 타입

`timeline.png`

- 시간축 위 이벤트 분포
- `back_navigation` 포함 페이지 진입 이벤트
- 페이지 방문 span

## Run

루트에서 실행:
(경로와 파일 이름은 커스텀 가능합니다)
```bash
python visualize_log_pipeline.py --input log.json --out visualization/output
```

모듈 직접 실행:

```bash
python -m visualization.visualize_log_pipeline --input log.json --out visualization/output
```
혹은

```bash

cd visualization
python visualize_log_pipeline.py --input log.json --out output
```
## Notes

- `eventCount`는 상호작용 이벤트만 집계합니다. `page_load`, `back_navigation`, `page_unload`, `visibility_change`, `session_start` 같은 수명주기 이벤트는 제외합니다.
- `back_navigation`은 브라우저 history 이동 중 세션 히스토리 기준으로 이전 단계로 돌아간 경우만 계산합니다.
- 페이지 체류 시간은 페이지 진입부터 다음 이탈 또는 다음 페이지 진입 전까지로 계산합니다.
