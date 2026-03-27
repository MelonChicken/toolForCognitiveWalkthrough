# Cognitive Walkthrough Logger

## 1. 프로젝트 개요

이 프로젝트는 Cognitive Walkthrough 또는 사용성 연구 세션 동안 **로컬 환경에서 로그를 수집하기 위한 Chrome Extension**입니다. 연구자는 확장 프로그램 팝업에서 로깅을 시작하고, 확장 프로그램은 현재 활성 탭의 상호작용 이벤트를 기록하며, 팝업에서 수집된 세션을 JSON 파일로 내보낼 수 있습니다.

현재 구현은 작고 단순한 **로컬 전용 MVP**입니다.

* 백엔드나 원격 동기화 기능이 없습니다.
* 세션 데이터는 `chrome.storage.local`에 저장됩니다.
* 한 번에 하나의 세션만 기록합니다.
* 하나의 세션은 하나의 Chrome 탭 ID에 연결됩니다.
* 로깅은 **같은 탭 안에서 페이지 이동이 일어날 때만** 계속 유지됩니다.
* 확장 프로그램이 설치되어 있어도 다른 탭에서 발생한 이벤트는 무시됩니다.

상위 수준 동작 흐름은 다음과 같습니다.

1. 팝업에서 `participantId`, `taskId`, `sessionId`로 세션을 시작합니다.
2. background service worker가 세션 객체를 생성하고 로컬에 저장합니다.
3. 추적 중인 탭에서 실행 중인 content script가 브라우저 이벤트를 수집해 background script로 보냅니다.
4. 팝업에서 세션을 중지하거나, 현재 세션 JSON을 내보내거나, 저장된 세션을 삭제할 수 있습니다.

현재 코드 기준 범위 제한은 다음과 같습니다.

* 서버 측 저장 또는 참가자 관리 기능이 없습니다.
* 여러 탭의 데이터를 합산하지 않습니다.
* 스크린샷, DOM 스냅샷, 네트워크 로그, 콘솔 로그는 수집하지 않습니다.
* replay UI가 없습니다.
* 아래에 설명된 이벤트 메타데이터를 넘어 사용자의 의도를 추론하려고 하지 않습니다.

## 2. 파일 구조와 역할

* `manifest.json`: Chrome Extension 매니페스트(Manifest V3)입니다. 팝업, background service worker, content script, storage/tabs 권한, `<all_urls>` host access를 선언합니다.
* `background.js`: 세션 상태 관리자입니다. 세션 시작/중지/삭제를 처리하고, content script로부터 이벤트를 받아 `index`, `elapsedMs`, `delay`를 계산하며, `eventCount`를 업데이트하고 세션을 `chrome.storage.local`에 저장합니다.
* `content.js`: 각 페이지에서 `document_start` 시점에 실행됩니다. 현재 탭이 활성 세션에 해당하는지 확인하고, 이벤트 리스너를 붙이며, `mousemove`와 `scroll`에 대한 throttle을 적용하고, 이벤트 메타데이터를 추출하고, 텍스트 입력값을 마스킹한 뒤 background script로 전송합니다.
* `popup.html`: ID 입력과 로거 제어를 위한 팝업 UI 구조입니다.
* `popup.js`: 팝업 동작 로직입니다. 현재 세션 상태를 읽고, 세션 시작/중지, JSON export, 저장 데이터 삭제를 수행하며, 1초마다 팝업 상태를 갱신합니다.
* `popup.css`: 기본 팝업 스타일만 포함합니다.

## 3. 로드 및 실행 방법

먼저 git clone을 통해 저장합니다.
```bash
git clone https://github.com/MelonChicken/toolForCognitiveWalkthrough.git
```

### Chrome에 unpacked extension으로 로드하기

1. Chrome에서 `chrome://extensions/`로 이동합니다.
2. **개발자 모드(Developer mode)** 를 켭니다.
3. **압축해제된 확장 프로그램을 로드(Load unpacked)** 를 클릭합니다.
4. 이 프로젝트 폴더를 선택합니다.

### 세션 시작하기

1. Chrome에서 대상 웹페이지를 엽니다.
2. 해당 탭이 현재 활성 탭인지 확인합니다.
3. 확장 프로그램 팝업을 엽니다.
4. 다음 값을 입력합니다.

    * `Participant ID`
    * `Task ID`
    * `Session ID`
5. `Session ID`를 비워 두면 팝업이 `S<number>` 형태로 자동 생성합니다.
6. **Start**를 클릭합니다.

코드에서 일어나는 일:

* 확장 프로그램은 `chrome.storage.local`의 `session` 키 아래에 세션 객체 하나를 저장합니다.
* 세션은 현재 활성 탭 ID에 바인딩됩니다.
* `session_start`라는 synthetic event가 즉시 생성됩니다.
* 해당 탭의 content script가 로깅을 시작하고 즉시 `page_load` synthetic event를 보냅니다.

### 세션 중지하기

1. 팝업을 엽니다.
2. **Stop**을 클릭합니다.

코드에서 일어나는 일:

* `endTime`이 저장된 세션 객체에 기록됩니다.
* content script는 해당 탭에서 로깅을 중지하라는 신호를 받습니다.
* 팝업에서는 이후에도 현재 세션을 export하거나 clear할 수 있습니다.

중요한 구현상 주의점:

* content script는 Stop 버튼이 눌렸을 때 `session_stop` 이벤트를 기록하려고 시도합니다. 하지만 background script가 그 전에 이미 세션을 종료 상태로 표시합니다. 종료된 세션은 새로운 이벤트를 받지 않기 때문에, `session_stop`은 보통 export된 JSON에 저장되지 않습니다.

### JSON 내보내기

1. 팝업을 엽니다.
2. **Export JSON**을 클릭합니다.
3. Chrome이 다음 이름 형식으로 파일을 다운로드합니다.
   `cwlog_<participantId>_<taskId>_<sessionId>.json`

내보낸 파일은 로컬 스토리지에 저장된 현재 세션 객체입니다.

### 세션 삭제하기

1. 팝업을 엽니다.
2. **Clear Session**을 클릭합니다.
3. 브라우저 확인창에서 승인합니다.

이 동작은 `chrome.storage.local`에서 `session` 객체를 제거합니다. 세션이 아직 활성 상태였다면, 먼저 content script에 로깅을 중지하라고 전달한 뒤 삭제합니다.

## 4. 로깅 동작 방식

### 탭과 페이지 범위

* 로거는 **Start를 눌렀을 때 활성 상태였던 탭 ID**에서 전송된 이벤트만 기록합니다.
* content script는 모든 URL에 주입되지만, 실제로는 추적 중인 탭 ID에서 온 이벤트만 수락합니다.
* 사용자가 같은 탭 안에서 페이지 이동을 하면, 새 페이지에서 content script가 background 상태를 확인하기 때문에 로깅을 계속할 수 있습니다.
* 다른 탭으로 전환하면, 그 다른 탭의 이벤트는 세션에 추가되지 않습니다.

### 페이지 이동 및 service worker 비활성 이후의 지속성

* 현재 세션은 `chrome.storage.local`에 저장됩니다.
* service worker가 다시 시작될 때 `background.js`는 storage에서 `session`을 다시 불러옵니다.
* 따라서 세션 객체는 background worker가 잠시 비활성화되더라도 유지될 수 있습니다.
* 추적 중인 탭에서 페이지가 로드되면, content script는 background script에 해당 탭이 여전히 로깅 대상인지 확인합니다.

### 세션 상태 처리

저장되는 세션 객체에는 다음 정보가 포함됩니다.

* 연구자가 입력한 식별자: `participantId`, `taskId`, `sessionId`
* 세션 메타데이터: `tabId`, `startTime`, `endTime`, `startedUrl`, `endedUrl`, `userAgent`
* 이벤트 요약: `eventCount`
* 이벤트 목록: `events`

현재 코드의 세션 상태 규칙은 다음과 같습니다.

* 한 번에 하나의 세션만 저장됩니다.
* `eventCount`는 현재 `events` 배열 길이와 같습니다.
* `startedUrl`은 세션 시작 시점의 탭 URL입니다.
* `endedUrl`은 처음에는 `startedUrl`과 같고, 이후 수락된 이벤트가 가진 URL로 계속 갱신됩니다.
* 세션은 `session`이 존재하고 `endTime`이 아직 `null`일 때만 활성 상태로 간주됩니다.

### 사용되는 저장소

* Chrome storage 영역: `chrome.storage.local`
* storage key: `session`

### 실제 구현된 throttling 규칙

* `mousemove`

    * 마지막으로 기록된 mousemove 이후 `100 ms`보다 짧으면 무시됩니다.
    * 또한 첫 번째 기록된 mousemove를 제외하고, 마지막 기록 mousemove 대비 전체 이동 거리가 `10 px` 미만이면 무시됩니다.
* `scroll`

    * 마지막 기록된 scroll 이후 `150 ms`보다 짧으면 무시됩니다.
* 그 외 추적 이벤트

    * 현재 코드에서는 throttling이 없습니다.

## 5. 수집되는 이벤트 종류

확장 프로그램은 현재 다음 이벤트 타입을 기록합니다.

### Synthetic / 세션 생명주기 이벤트

* `session_start`: 세션 시작 직후 `background.js`가 삽입하는 이벤트
* `page_load`: 추적 중인 탭의 페이지에서 로깅이 활성화될 때 `content.js`가 생성하는 이벤트
* `page_unload`: 추적 중인 페이지가 unload되기 시작할 때 `beforeunload`에서 생성되는 이벤트
* `visibility_change`: 추적 중인 페이지에서 `document.visibilityState`가 변경될 때 생성되는 이벤트
* `session_stop`: `content.js`에 구현되어 있지만, 일반적인 stop 흐름에서는 세션이 먼저 종료되어 이 이벤트가 실제 JSON에 저장되지 않습니다.

### 사용자 상호작용 이벤트

* `click`: 마우스 클릭
* `dblclick`: 더블 클릭
* `contextmenu`: context menu 호출, 보통 우클릭
* `mousemove`: 샘플링된 커서 이동
* `scroll`: 샘플링된 페이지 스크롤
* `keydown`: 키 입력 메타데이터
* `input`: 폼 입력 이벤트
* `change`: 폼 변경 이벤트
* `focus`: 어떤 요소가 포커스를 얻음
* `blur`: 어떤 요소가 포커스를 잃음

현재 파일 기준으로 이 외 이벤트 타입은 구현되어 있지 않습니다.

## 6. 수집되는 지표 / 필드

export되는 JSON은 두 수준으로 구성됩니다.

* 최상위 root object의 세션 단위 필드
* `events[]` 내부의 이벤트 단위 필드

### 세션 단위 필드

| 필드명             | Datatype         | 설명 / 의미                                                   | 예시 값                              | 등장 시점 |
| --------------- | ---------------- | --------------------------------------------------------- | --------------------------------- | ----- |
| `participantId` | string           | 팝업에서 연구자가 입력한 참가자 식별자입니다. 비워 두면 시작 시 `"P1"`이 기본값으로 들어갑니다. | `"P03"`                           | 모든 세션 |
| `taskId`        | string           | 팝업에서 연구자가 입력한 과업 식별자입니다. 비워 두면 시작 시 `"T1"`이 기본값으로 들어갑니다.  | `"CheckoutTask"`                  | 모든 세션 |
| `sessionId`     | string           | 연구자가 입력한 세션 식별자 또는 팝업이 `"S" + 임의 정수` 형태로 자동 생성한 값입니다.     | `"S418233"`                       | 모든 세션 |
| `tabId`         | number           | 세션이 연결된 Chrome 탭 ID입니다. 이 탭에서 온 이벤트만 수락됩니다.               | `127`                             | 모든 세션 |
| `startTime`     | string           | 세션 시작 시각을 사람이 읽기 쉬운 `YY-MM-DD HH:MM:SS` 형식으로 저장한 값입니다. | `"26-03-27 19:00:03"`             | 모든 세션 |
| `startTimeMs`   | number           | `startTime`과 동일한 시각의 Unix 밀리초 값입니다. 계산과 정렬에 사용됩니다.        | `1774605603757`                   | 모든 세션 |
| `endTime`       | string 또는 `null` | Stop 버튼이 눌렸을 때의 시각을 `YY-MM-DD HH:MM:SS` 형식으로 저장한 값 또는, 세션이 아직 활성 상태라면 `null`입니다. | `"26-03-27 19:00:41"`             | 모든 세션 |
| `endTimeMs`     | number 또는 `null` | `endTime`과 동일한 시각의 Unix 밀리초 값 또는, 세션이 아직 활성 상태라면 `null`입니다. | `1774605641042`                   | 모든 세션 |
| `startedUrl`    | string           | 세션 시작 시 활성 탭의 URL입니다.                                     | `"https://example.com/login"`     | 모든 세션 |
| `endedUrl`      | string           | 수락된 이벤트들 중 마지막으로 확인된 URL입니다. 처음에는 `startedUrl`과 같습니다.     | `"https://example.com/dashboard"` | 모든 세션 |
| `userAgent`     | string           | background worker 컨텍스트에서 가져온 브라우저 user agent 문자열입니다.      | `"Mozilla/5.0 ..."`               | 모든 세션 |
| `eventCount`    | number           | 저장된 이벤트 수입니다. 코드상 항상 `events.length`와 같습니다.               | `42`                              | 모든 세션 |
| `events`        | object 배열        | 세션의 순서 있는 이벤트 기록 배열입니다.                                   | `[ {...}, {...} ]`                | 모든 세션 |

### 이벤트 단위 필드

| 필드명               | Datatype         | 설명 / 의미                                                                                                                             | 예시 값                              | 등장 시점                                                  |
| ----------------- | ---------------- | ----------------------------------------------------------------------------------------------------------------------------------- | --------------------------------- | ------------------------------------------------------ |
| `index`           | number           | 세션 내 0부터 시작하는 이벤트 순서 번호입니다. `background.js`에서 부여됩니다.                                                                                | `0`                               | 모든 저장 이벤트                                              |
| `type`            | string           | 이벤트 타입 이름입니다.                                                                                                                       | `"click"`                         | 모든 저장 이벤트                                              |
| `timestamp`       | string           | 이벤트 객체가 생성된 시각을 사람이 읽기 쉬운 `YY-MM-DD HH:MM:SS` 형식으로 저장한 값입니다.                                                                                  | `"26-03-27 19:00:04"`             | 모든 저장 이벤트                                              |
| `timestampMs`     | number           | `timestamp`와 동일한 시각의 Unix 밀리초 값입니다. 정렬, 경과시간 계산, 지연 계산에 사용됩니다.                                                                          | `1774605604363`                   | 모든 저장 이벤트                                              |
| `elapsedMs`       | number           | `session.startTimeMs` 이후 경과한 밀리초입니다. `background.js`에서 추가됩니다.                                                                     | `1217`                            | 모든 저장 이벤트                                              |
| `delay`           | number           | 직전 저장 이벤트와의 시간 간격(밀리초)입니다. 첫 이벤트는 `0`입니다.                                                                                           | `318`                             | 모든 저장 이벤트                                              |
| `url`             | string           | 이벤트 발생 시점의 `window.location.href`입니다.                                                                                               | `"https://example.com/form"`      | 모든 저장 이벤트. 단, synthetic `session_start`는 탭 상태에서 가져옵니다. |
| `title`           | string           | content-script 이벤트에서는 `document.title`, `session_start`에서는 탭 제목입니다.                                                                 | `"Example Form"`                  | 모든 저장 이벤트                                              |
| `viewportWidth`   | number 또는 `null` | CSS 픽셀 기준 브라우저 뷰포트 너비입니다. `session_start`는 `null`, content-script 이벤트는 `window.innerWidth`를 사용합니다.                                  | `1440`                            | 모든 이벤트, 단 `session_start`에서는 `null`                    |
| `viewportHeight`  | number 또는 `null` | CSS 픽셀 기준 브라우저 뷰포트 높이입니다. `session_start`는 `null`, content-script 이벤트는 `window.innerHeight`를 사용합니다.                                 | `821`                             | 모든 이벤트, 단 `session_start`에서는 `null`                    |
| `scrollX`         | number 또는 `null` | 가로 스크롤 오프셋입니다. `session_start`는 `null`, content-script 이벤트는 `window.scrollX`를 사용합니다.                                                | `0`                               | 모든 이벤트, 단 `session_start`에서는 `null`                    |
| `scrollY`         | number 또는 `null` | 세로 스크롤 오프셋입니다. `session_start`는 `null`, content-script 이벤트는 `window.scrollY`를 사용합니다.                                                | `640`                             | 모든 이벤트, 단 `session_start`에서는 `null`                    |
| `x`               | number           | 마우스 이벤트의 `clientX` 값입니다.                                                                                                            | `512`                             | `click`, `dblclick`, `contextmenu`, `mousemove`        |
| `y`               | number           | 마우스 이벤트의 `clientY` 값입니다.                                                                                                            | `284`                             | `click`, `dblclick`, `contextmenu`, `mousemove`        |
| `pageX`           | number           | 마우스 이벤트의 `pageX` 값입니다.                                                                                                              | `512`                             | `click`, `dblclick`, `contextmenu`, `mousemove`        |
| `pageY`           | number           | 마우스 이벤트의 `pageY` 값입니다.                                                                                                              | `924`                             | `click`, `dblclick`, `contextmenu`, `mousemove`        |
| `button`          | number           | DOM 이벤트의 마우스 버튼 코드입니다. 일반적으로 `0`은 좌클릭, `1`은 중간 버튼, `2`는 우클릭입니다.                                                                     | `0`                               | `click`, `dblclick`, `contextmenu`, `mousemove`        |
| `key`             | string           | 키보드 키 값입니다.                                                                                                                         | `"Enter"`                         | `keydown`                                              |
| `code`            | string           | 물리적 키보드 코드입니다.                                                                                                                      | `"Enter"` 또는 `"KeyA"`             | `keydown`                                              |
| `ctrlKey`         | boolean          | Control 키가 눌렸는지 여부입니다.                                                                                                              | `false`                           | `keydown`                                              |
| `shiftKey`        | boolean          | Shift 키가 눌렸는지 여부입니다.                                                                                                                | `true`                            | `keydown`                                              |
| `altKey`          | boolean          | Alt 키가 눌렸는지 여부입니다.                                                                                                                  | `false`                           | `keydown`                                              |
| `metaKey`         | boolean          | Meta/Command 키가 눌렸는지 여부입니다.                                                                                                         | `false`                           | `keydown`                                              |
| `tagName`         | string           | 타깃 요소의 소문자 태그 이름입니다.                                                                                                                | `"button"`                        | 타깃에 `tagName`이 있는 이벤트                                  |
| `id`              | string           | 타깃 요소의 `id`입니다.                                                                                                                     | `"submit-btn"`                    | 타깃 요소에 `id`가 있을 때                                      |
| `className`       | string           | 타깃 요소의 `className`이며, 문자열인 경우만 저장됩니다.                                                                                               | `"btn primary"`                   | 타깃 요소에 문자열 class name이 있을 때                            |
| `text`            | string           | `innerText` 또는 `textContent`를 trim한 값이며, 길면 50자까지 남기고 `...`를 붙입니다. `input`, `textarea`, `select` 요소에서는 수집하지 않습니다.                   | `"Continue"`                      | 읽을 수 있는 텍스트가 있는 비폼 요소                                  |
| `ariaLabel`       | string           | 타깃 요소의 `aria-label` 속성입니다.                                                                                                          | `"Search"`                        | `aria-label`이 있는 타깃                                    |
| `name`            | string           | 타깃 요소의 `name` 속성입니다.                                                                                                                | `"email"`                         | `name`이 있는 타깃                                          |
| `role`            | string           | 타깃 요소의 `role` 속성입니다.                                                                                                                | `"button"`                        | `role`이 있는 타깃                                          |
| `href`            | string           | 타깃 요소의 `href`입니다.                                                                                                                   | `"https://example.com/help"`      | 링크 성격의 타깃                                              |
| `selector`        | string           | 타깃 요소 기반의 휴리스틱 selector 문자열입니다. 우선순위는 `#id`, `data-testid`, `aria-label`, `name`, `role`, 그 외 최대 3단계 DOM 경로입니다.                     | `"button[aria-label=\"Search\"]"` | 타깃에 `tagName`이 있는 이벤트                                  |
| `inputType`       | string           | 입력 요소 타입 분류입니다. `input`/`textarea`는 소문자 `type` 또는 `"text"`, `select`는 `"select"`입니다.                                                | `"email"`                         | 폼 컨트롤을 대상으로 한 `input`, `change`, `focus`, `blur` 등     |
| `checked`         | boolean          | checkbox/radio의 checked 상태입니다. 다른 input type에서도 코드상 `t.checked`를 직접 복사하기 때문에 `false`가 나타날 수 있습니다.                                   | `true`                            | 타깃이 `input` 또는 `textarea`일 때                           |
| `valueLength`     | number           | 현재 입력값 문자열 길이입니다. 원문 대신 길이만 저장합니다.                                                                                                  | `12`                              | 타깃이 `input` 또는 `textarea`이고 `value`가 있을 때              |
| `maskedValue`     | string           | 입력값 길이와 동일한 개수의 `*`로 이루어진 문자열입니다. `password`, `email`, `tel`, `search`, `text`, `url`, `number`, `date`, 그리고 모든 `textarea`에서 생성됩니다. | `"************"`                  | 마스킹 대상 `input`/`textarea` 값일 때                         |
| `selectedText`    | string           | 현재 선택된 `<option>`의 표시 텍스트입니다.                                                                                                       | `"United States"`                 | 타깃이 `select`이고 선택 옵션이 있을 때                             |
| `visibilityState` | string           | visibility change 시점의 `document.visibilityState` 값입니다.                                                                              | `"hidden"`                        | `visibility_change`                                    |

필드 등장에 대한 주의:

* 모든 이벤트가 모든 필드를 가지는 것은 아닙니다.
* 추출 코드에서 `undefined`로 남는 필드는 JSON에 포함되지 않습니다.
* `session_start`는 content script가 아니라 background script에서 생성되는 유일한 이벤트이기 때문에 필드 수가 더 적고, `viewportWidth`, `viewportHeight`, `scrollX`, `scrollY`는 명시적으로 `null`입니다.

## 7. 연구자를 위한 해석 가이드

### 시간 관련 필드 해석

* `timestamp`는 사람이 읽기 쉬운 이벤트 시각 문자열입니다.
* `timestampMs`는 동일한 시각의 원시 Unix 밀리초 값입니다.
* `elapsedMs`는 세션 시작 이후 경과 시간입니다. 참가자의 과업 타임라인을 재구성할 때 유용합니다.
* `delay`는 직전 저장 이벤트와의 시간 간격입니다. 값이 크면 읽기, 망설임, 계획, 정지 시간을 의미할 수 있지만, 왜 멈췄는지를 이 값만으로 알 수는 없습니다.

### 페이지 및 이동 신호 해석

* `page_load`는 추적 중인 탭의 해당 페이지에서 로깅이 활성화되었음을 의미합니다.
* `page_unload`는 추적 중인 페이지가 unload되기 시작했음을 의미합니다.
* `page_unload` 뒤에 `page_load`가 나오면, 보통 같은 탭 안에서 페이지 이동 또는 새로고침이 일어났다고 볼 수 있습니다.
* `startedUrl`은 세션 첫 페이지 URL입니다.
* `endedUrl`은 마지막으로 관측된 URL일 뿐이며, 반드시 “최종 완료 페이지”를 뜻하지는 않습니다.

### 타깃 정보 해석

* `selector`, `tagName`, `id`, `className`, `text`, `ariaLabel`, `name`, `role`, `href`는 참가자가 무엇과 상호작용했는지 식별하는 데 도움을 줍니다.
* 이 값들은 UI 타깃을 추정하는 휴리스틱 정보로 보는 것이 적절합니다.
* `selector`는 항상 고유하거나 안정적이라고 보장되지 않습니다.
* `text`는 잘릴 수 있고, 폼 필드에서는 수집되지 않습니다.

### 마우스 및 스크롤 데이터 해석

* `click`, `dblclick`, `contextmenu`는 특정 타깃에 대한 명시적 포인터 행동입니다.
* `mousemove`는 연속 궤적이 아니라 샘플링된 값입니다. `100 ms` / `10 px` 필터 때문에 move 로그가 없다고 해서 마우스가 완전히 정지했다고 단정할 수는 없습니다.
* `scroll`도 `150 ms` 단위로 샘플링되므로, 스크롤 활동은 볼 수 있지만 모든 중간 브라우저 스크롤 이벤트를 담지는 않습니다.
* 좌표(`x`, `y`, `pageX`, `pageY`)는 해당 시점의 포인터 위치일 뿐입니다.

### 키보드 및 폼 데이터 해석

* `keydown`는 `key`, `code`, modifier flag 같은 키 메타데이터를 기록합니다. 이것만으로 전체 입력 문자열을 재구성할 수는 없습니다.
* `input`과 `change`는 폼 컨트롤과의 상호작용을 의미합니다.
* 텍스트형 입력 필드에서는 원문 대신 `valueLength`와 `maskedValue`만 저장됩니다.
* `maskedValue`는 글자 수만 보존하고 실제 내용은 보존하지 않습니다.
* `<select>`에서는 사람이 보는 선택 텍스트(`selectedText`)가 저장됩니다.
* `checked`는 checkbox/radio 상태 해석에 도움이 되지만, 코드상 모든 input/textarea에서 `t.checked`를 읽기 때문에 checkable하지 않은 input에서도 `false`가 나올 수 있습니다. 과도하게 해석하면 안 됩니다.

### focus 및 visibility 이벤트 해석

* `focus`와 `blur`는 어떤 요소가 포커스를 얻거나 잃었는지 보여줍니다.
* 현대 웹앱에서는 이 이벤트가 다소 noisy할 수 있으므로 신중히 해석해야 합니다.
* `visibility_change`는 페이지가 hidden/visible 상태로 바뀌었음을 보여주지만, 왜 그런 변화가 일어났는지는 직접 알려주지 않습니다.

### 신뢰성 있게 추론할 수 없는 것

* 참가자의 정확한 의도나 사고 과정
* 마스킹된 입력 필드의 실제 입력 내용
* 샘플링된 `mousemove` 사이의 정확한 커서 궤적
* 각 시점의 완전한 DOM 또는 애플리케이션 상태
* 추적 중인 탭 바깥, 다른 탭이나 창에서의 행동

## 8. 개인정보 / 데이터 처리

현재 구현은 세션 데이터를 연구자가 삭제하거나 확장 프로그램 데이터를 제거할 때까지 Chrome의 `chrome.storage.local`에 로컬 저장합니다.

현재 코드의 입력 처리 방식:

* `input` 및 `textarea`의 원본 입력값은 export되지 않습니다.
* 여러 텍스트형 입력 타입(`password`, `email`, `tel`, `search`, `text`, `url`, `number`, `date`)과 모든 `textarea`에 대해 다음만 저장합니다.

    * `valueLength`
    * 같은 길이의 `*`로 구성된 `maskedValue`
* `<select>`는 선택된 옵션의 보이는 텍스트를 `selectedText`로 저장합니다.
* 폼이 아닌 요소의 텍스트는 `text` 필드에 저장될 수 있으며, 최대 50자 + `...`로 잘립니다.
* 링크 목적지는 `href`로 저장될 수 있습니다.
* 페이지 URL과 제목은 모든 이벤트에 저장됩니다.

개인정보 관련 주의점:

* 원본 입력 텍스트가 없더라도, URL, title, 선택 옵션 텍스트, 보이는 요소 텍스트, ARIA label, name, role, href에는 민감한 정보가 포함될 수 있습니다.
* 확장 프로그램은 `<all_urls>`에서 동작하므로, 연구자는 이런 수준의 페이지 메타데이터 수집이 적절하고 동의된 환경에서만 사용해야 합니다.

## 9. 알려진 한계

이 한계들은 의도된 설계가 아니라, **현재 구현 기준**입니다.

* 단일 세션만 지원: 한 번에 `session` 객체 하나만 저장됩니다.
* 단일 탭만 지원: 시작 시점의 활성 탭만 기록합니다.
* 같은 탭 안 이동만 지원: 같은 탭 ID 안에서의 페이지 이동만 계속 기록할 수 있습니다.
* `session_stop`은 구현되어 있지만, 세션이 먼저 종료되어 실제 JSON에 저장되지 않는 경우가 대부분입니다.
* `page_load`는 브라우저 성능 타이밍 API가 아니라, “이 페이지에서 로깅이 활성화되었다”는 synthetic event입니다.
* `mousemove`와 `scroll`은 샘플링되므로, 로그는 의도적으로 불완전합니다.
* `selector` 생성은 휴리스틱 기반이라 UI가 바뀌면 불안정할 수 있습니다.
* `text`는 잘릴 수 있으며, 요소를 유일하게 식별하지 못할 수 있습니다.
* `focus`와 `blur`는 현대 웹앱에서 noisy할 수 있습니다.
* 비영어권 입력(IME)에 대한 별도 처리가 없어, 키보드 로그는 `keydown` 메타데이터 수준에 머뭅니다.
* 텍스트형 필드의 원문은 저장하지 않으므로, 실제 입력 내용을 복원할 수 없습니다.
* 팝업은 1초마다 polling하여 현재 상태를 보여주며, 이는 이벤트 수집에는 영향을 주지 않고 UI 표시에만 영향이 있습니다.
* 연구자가 입력하는 ID에 대한 검증은 없습니다.

## 10. 예시 JSON 구조

아래 예시는 현재 export 구조와 필드명을 반영한 것입니다. 모든 이벤트가 모든 필드를 가지는 것은 아닙니다.

```json
  {
  "participantId": "testForTimeExpression",
  "taskId": "Task01",
  "sessionId": "S823154",
  "tabId": 790767241,
  "startTime": "26-03-27 19:00:03",
  "startTimeMs": 1774605603757,
  "endTime": "26-03-27 19:00:41",
  "endTimeMs": 1774605641042,
  "startedUrl": "https://www.q-net.or.kr/man001.do?gSite=Q",
  "endedUrl": "https://www.q-net.or.kr/cst006.do?id=cst00602&gSite=Q&gId=",
  "userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
  "eventCount": 220,
  "events": [
    {
      "index": 0,
      "type": "session_start",
      "timestamp": "26-03-27 19:00:03",
      "timestampMs": 1774605603757,
      "elapsedMs": 0,
      "delay": 0,
      "url": "https://www.q-net.or.kr/man001.do?gSite=Q",
      "title": "Q-net 자격의모든것",
      "viewportWidth": null,
      "viewportHeight": null,
      "scrollX": null,
      "scrollY": null
    },
    {
      "type": "page_load",
      "timestamp": "26-03-27 19:00:03",
      "timestampMs": 1774605603758,
      "url": "https://www.q-net.or.kr/man001.do?gSite=Q",
      "title": "Q-net 자격의모든것",
      "viewportWidth": 1707,
      "viewportHeight": 932,
      "scrollX": 0,
      "scrollY": 0,
      "index": 1,
      "elapsedMs": 1,
      "delay": 1
    },
    {
      "type": "mousemove",
      "timestamp": "26-03-27 19:00:04",
      "timestampMs": 1774605604363,
      "url": "https://www.q-net.or.kr/man001.do?gSite=Q",
      "title": "Q-net 자격의모든것",
      "viewportWidth": 1707,
      "viewportHeight": 932,
      "scrollX": 0,
      "scrollY": 0,
      "x": 1578,
      "y": 222,
      "pageX": 1578,
      "pageY": 222,
      "button": 0,
      "tagName": "div",
      "id": "bbs_notice",
      "className": "mCont bg_W1",
      "text": "공지사항\n\n국가기술자격 응시자격서류 제출 유의사항 안내\n\n국가자격 인정신분증 범위 조정 안...",
      "selector": "#bbs_notice",
      "index": 2,
      "elapsedMs": 606,
      "delay": 605
    },
    {
      "type": "mousemove",
      "timestamp": "26-03-27 19:00:04",
      "timestampMs": 1774605604785,
      "url": "https://www.q-net.or.kr/man001.do?gSite=Q",
      "title": "Q-net 자격의모든것",
      "viewportWidth": 1707,
      "viewportHeight": 932,
      "scrollX": 0,
      "scrollY": 0,
      "x": 1581,
      "y": 211,
      "pageX": 1581,
      "pageY": 211,
      "button": 0,
      "tagName": "b",
      "className": "mTit2",
      "text": "공지사항",
      "selector": "div#bbs_notice > b.mTit2",
      "index": 3,
      "elapsedMs": 1028,
      "delay": 422
    },
    {
      "type": "mousemove",
      "timestamp": "26-03-27 19:00:04",
      "timestampMs": 1774605604914,
      "url": "https://www.q-net.or.kr/man001.do?gSite=Q",
      "title": "Q-net 자격의모든것",
      "viewportWidth": 1707,
      "viewportHeight": 932,
      "scrollX": 0,
      "scrollY": 0,
      "x": 1209,
      "y": 170,
      "pageX": 1209,
      "pageY": 170,
      "button": 0,
      "tagName": "div",
      "className": "mCont bg_G1 bg_ico03",
      "text": "자격증 신청\n\n국가기술자격\n\n바로가기",
      "selector": "div.second > div.second_cont > div.mCont.bg_G1.bg_ico03",
      "index": 4,
      "elapsedMs": 1157,
      "delay": 129
    },
    {
      "type": "mousemove",
      "timestamp": "26-03-27 19:00:05",
      "timestampMs": 1774605605018,
      "url": "https://www.q-net.or.kr/man001.do?gSite=Q",
      "title": "Q-net 자격의모든것",
      "viewportWidth": 1707,
      "viewportHeight": 932,
      "scrollX": 0,
      "scrollY": 0,
      "x": 714,
      "y": 223,
      "pageX": 714,
      "pageY": 223,
      "button": 0,
      "tagName": "div",
      "className": "mCont bg_B2 bg_ico02",
      "text": "시험 결과 보기\n\n시험결과는 60일간 확인 가능\n\n바로가기",
      "selector": "div.second > div.second_cont > div.mCont.bg_B2.bg_ico02",
      "index": 5,
      "elapsedMs": 1261,
      "delay": 104
    },
    {
      "type": "mousemove",
      "timestamp": "26-03-27 19:00:05",
      "timestampMs": 1774605605123,
      "url": "https://www.q-net.or.kr/man001.do?gSite=Q",
      "title": "Q-net 자격의모든것",
      "viewportWidth": 1707,
      "viewportHeight": 932,
      "scrollX": 0,
      "scrollY": 0,
      "x": 534,
      "y": 287,
      "pageX": 534,
      "pageY": 287,
      "button": 0,
      "tagName": "p",
      "className": "mbodytxt2 c_White",
      "text": "원서접수 초일, 접수시작 시간안내\n기술사, 기능장, 기사, 정기·상시 기능사 오전 10:0...",
      "selector": "div#choilText > div.mCont.bg_B1.bg_ico01 > p.mbodytxt2.c_White",
      "index": 6,
      "elapsedMs": 1366,
      "delay": 105
    },
    {
      "type": "mousemove",
      "timestamp": "26-03-27 19:00:05",
      "timestampMs": 1774605605267,
      "url": "https://www.q-net.or.kr/man001.do?gSite=Q",
      "title": "Q-net 자격의모든것",
      "viewportWidth": 1707,
      "viewportHeight": 932,
      "scrollX": 0,
      "scrollY": 0,
      "x": 461,
      "y": 319,
      "pageX": 461,
      "pageY": 319,
      "button": 0,
      "tagName": "p",
      "className": "mbodytxt2 c_White",
      "text": "원서접수 초일, 접수시작 시간안내\n기술사, 기능장, 기사, 정기·상시 기능사 오전 10:0...",
      "selector": "div#choilText > div.mCont.bg_B1.bg_ico01 > p.mbodytxt2.c_White",
      "index": 7,
      "elapsedMs": 1510,
      "delay": 144
    },
    {
      "type": "mousemove",
      "timestamp": "26-03-27 19:00:05",
      "timestampMs": 1774605605371,
      "url": "https://www.q-net.or.kr/man001.do?gSite=Q",
      "title": "Q-net 자격의모든것",
      "viewportWidth": 1707,
      "viewportHeight": 932,
      "scrollX": 0,
      "scrollY": 0,
      "x": 357,
      "y": 375,
      "pageX": 357,
      "pageY": 375,
      "button": 0,
      "tagName": "p",
      "className": "mbodytxt2 c_White",
      "text": "원서접수 초일, 접수시작 시간안내\n기술사, 기능장, 기사, 정기·상시 기능사 오전 10:0...",
      "selector": "div#choilText > div.mCont.bg_B1.bg_ico01 > p.mbodytxt2.c_White",
      "index": 8,
      "elapsedMs": 1614,
      "delay": 104
    },
    {
      "type": "mousemove",
      "timestamp": "26-03-27 19:00:05",
      "timestampMs": 1774605605477,
      "url": "https://www.q-net.or.kr/man001.do?gSite=Q",
      "title": "Q-net 자격의모든것",
      "viewportWidth": 1707,
      "viewportHeight": 932,
      "scrollX": 0,
      "scrollY": 0,
      "x": 163,
      "y": 447,
      "pageX": 163,
      "pageY": 447,
      "button": 0,
      "tagName": "span",
      "className": "",
      "text": "원서접수하기",
      "selector": "div.mCont.bg_B1.bg_ico01 > a.link.c_White > span",
      "index": 9,
      "elapsedMs": 1720,
      "delay": 106
    },
    {
      "type": "focus",
      "timestamp": "26-03-27 19:00:05",
      "timestampMs": 1774605605781,
      "url": "https://www.q-net.or.kr/man001.do?gSite=Q",
      "title": "Q-net 자격의모든것",
      "viewportWidth": 1707,
      "viewportHeight": 932,
      "scrollX": 0,
      "scrollY": 0,
      "index": 10,
      "elapsedMs": 2024,
      "delay": 304
    },
    {
      "type": "focus",
      "timestamp": "26-03-27 19:00:05",
      "timestampMs": 1774605605791,
      "url": "https://www.q-net.or.kr/man001.do?gSite=Q",
      "title": "Q-net 자격의모든것",
      "viewportWidth": 1707,
      "viewportHeight": 932,
      "scrollX": 0,
      "scrollY": 0,
      "tagName": "a",
      "className": "link c_White",
      "text": "원서접수하기",
      "href": "https://www.q-net.or.kr/rcv202.do?id=rcv20210&gSite=Q&gId=",
      "selector": "div#choilText > div.mCont.bg_B1.bg_ico01 > a.link.c_White",
      "index": 11,
      "elapsedMs": 2034,
      "delay": 10
    },
    {
      "type": "click",
      "timestamp": "26-03-27 19:00:05",
      "timestampMs": 1774605605874,
      "url": "https://www.q-net.or.kr/man001.do?gSite=Q",
      "title": "Q-net 자격의모든것",
      "viewportWidth": 1707,
      "viewportHeight": 932,
      "scrollX": 0,
      "scrollY": 0,
      "x": 161,
      "y": 447,
      "pageX": 161,
      "pageY": 447,
      "button": 0,
      "tagName": "span",
      "className": "",
      "text": "원서접수하기",
      "selector": "div.mCont.bg_B1.bg_ico01 > a.link.c_White > span",
      "index": 12,
      "elapsedMs": 2117,
      "delay": 83}
    ]
  }
```
