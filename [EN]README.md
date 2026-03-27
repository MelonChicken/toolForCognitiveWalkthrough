# Cognitive Walkthrough Logger

## 1. Project overview

This project is a Chrome Extension for local logging during Cognitive Walkthrough or usability study sessions. A researcher starts logging from the extension popup, the extension records interaction events from the currently active tab, and the popup can export the collected session as a JSON file.

The current implementation is a small, local-only MVP:

- It has no backend or remote sync.
- It stores session data in `chrome.storage.local`.
- It records only one session at a time.
- A session is tied to one Chrome tab ID.
- Logging continues across page navigations only when they happen in that same tab.
- Events from other tabs are ignored even if the extension is installed there.

High-level flow:

1. The popup starts a session with `participantId`, `taskId`, and `sessionId`.
2. The background service worker creates a session object and stores it locally.
3. The content script running in the tracked tab captures browser events and sends them to the background script.
4. The popup can stop the session, export the current session JSON, or clear the stored session.

Scope limitations based on the current code:

- No server-side storage or participant management.
- No multi-tab aggregation.
- No screenshot, DOM snapshot, network, or console logging.
- No replay UI.
- No attempt to infer user intent beyond the event metadata described below.

## 2. File structure and responsibilities

- `manifest.json`: Chrome Extension manifest (Manifest V3). Declares the popup, background service worker, content script, storage/tabs permissions, and `<all_urls>` host access.
- `background.js`: Session state manager. Starts/stops/clears a session, receives logged events from the content script, computes `index`, `elapsedMs`, and `delay`, updates `eventCount`, and saves the session to `chrome.storage.local`.
- `content.js`: Runs on every page at `document_start`. Detects whether the current tab has an active session, attaches event listeners, applies throttling for `mousemove` and `scroll`, extracts event metadata, masks text input values, and sends events to the background script.
- `popup.html`: Popup UI structure for entering IDs and controlling the logger.
- `popup.js`: Popup behavior. Reads current session state, starts/stops a session, exports JSON, clears stored data, and refreshes popup status once per second.
- `popup.css`: Basic popup styling only.
- `toolForCW.iml`: IDE project metadata; not used by the extension runtime.

## 3. How to load and run

### Load the unpacked extension in Chrome

1. Open Chrome and go to `chrome://extensions/`.
2. Enable **Developer mode**.
3. Click **Load unpacked**.
4. Select this project folder.

### Start a session

1. Open the target webpage in Chrome.
2. Make sure that tab is the active tab.
3. Open the extension popup.
4. Enter:
   - `Participant ID`
   - `Task ID`
   - `Session ID`
5. If `Session ID` is left blank, the popup generates one in the form `S<number>`.
6. Click **Start**.

What happens in code:

- The extension stores one session object in `chrome.storage.local` under the key `session`.
- The session is bound to the current active tab ID.
- A synthetic `session_start` event is created immediately.
- The content script in that tab begins logging and immediately sends a synthetic `page_load` event.

### Stop a session

1. Open the popup.
2. Click **Stop**.

What happens in code:

- `endTime` is written into the stored session.
- The content script is told to stop recording in that tab.
- The popup remains able to export or clear the stored session.

Important implementation note:

- The content script attempts to emit a `session_stop` event when stop is pressed, but the background script has already marked the session ended by then. Because ended sessions reject new events, `session_stop` is usually not saved in the exported JSON.

### Export JSON

1. Open the popup.
2. Click **Export JSON**.
3. Chrome downloads a file named:
   `cwlog_<participantId>_<taskId>_<sessionId>.json`

The exported file is the current session object from local storage.

### Clear a session

1. Open the popup.
2. Click **Clear Session**.
3. Confirm the browser prompt.

This removes the stored `session` object from `chrome.storage.local`. If the session was still active, the content script is also told to stop recording first.

## 4. Logging behavior

### Tab and page scope

- The logger records only events sent from the tab whose ID was active when **Start** was pressed.
- The content script is injected on all URLs, but events are accepted only from the tracked tab ID.
- If the user navigates within the same tab, logging can continue on the new page because the content script checks the background state on load.
- If the user switches to a different tab, events from that other tab are not added to the session.

### Persistence across navigation and service worker inactivity

- The current session is saved in `chrome.storage.local`.
- On service worker startup, `background.js` reloads `session` from storage.
- This means the session object can survive background worker inactivity.
- On page load in the tracked tab, the content script asks the background script whether that tab is still active for logging.

### Session state handling

The stored session object contains:

- Researcher-entered identifiers: `participantId`, `taskId`, `sessionId`
- Session metadata: `tabId`, `startTime`, `endTime`, `startedUrl`, `endedUrl`, `userAgent`
- Event summary: `eventCount`
- Event list: `events`

Session state rules in the current code:

- Only one session is stored at a time.
- `eventCount` is the current length of `events`.
- `startedUrl` is the tab URL when the session starts.
- `endedUrl` starts as the same URL, then updates whenever a later event contains a URL.
- A session is considered active only when `session` exists and `endTime` is still `null`.

### Storage used

- Chrome storage area: `chrome.storage.local`
- Storage key: `session`

### Throttling rules actually implemented

- `mousemove`:
  - ignored if less than `100 ms` since the last recorded mousemove
  - also ignored if the cursor moved less than `10` pixels total since the last recorded mousemove, except for the first recorded mousemove
- `scroll`:
  - ignored if less than `150 ms` since the last recorded scroll
- Other tracked events:
  - no throttling in the current code

## 5. Events collected

The extension currently records the following event types.

### Synthetic/session lifecycle events

- `session_start`: inserted by `background.js` immediately when a session starts
- `page_load`: emitted by `content.js` when logging becomes active on a page in the tracked tab
- `page_unload`: emitted from `beforeunload` while a tracked page is unloading
- `visibility_change`: emitted when `document.visibilityState` changes on the tracked page
- `session_stop`: implemented in `content.js`, but in normal stop flow it is not persisted because the session is ended before the event is accepted

### User interaction events

- `click`: mouse click
- `dblclick`: double-click
- `contextmenu`: context menu trigger, usually right-click
- `mousemove`: sampled cursor movement
- `scroll`: sampled page scroll event
- `keydown`: key press metadata
- `input`: form input event
- `change`: form change event
- `focus`: focus moved onto an element
- `blur`: focus moved away from an element

No other event types are implemented in the current files.

## 6. Collected metrics / fields

The exported JSON has two levels:

- Session-level fields on the root object
- Event-level fields inside `events[]`

### Session-level fields

| Field name | Datatype | Description / meaning | Example value | When it appears |
| --- | --- | --- | --- | --- |
| `participantId` | string | Researcher-entered participant identifier from the popup. Defaults to `"P1"` if left blank when starting. | `"P03"` | All sessions |
| `taskId` | string | Researcher-entered task identifier from the popup. Defaults to `"T1"` if left blank when starting. | `"CheckoutTask"` | All sessions |
| `sessionId` | string | Researcher-entered session identifier, or auto-generated in the popup as `"S" + random integer`. | `"S418233"` | All sessions |
| `tabId` | number | Chrome tab ID that the session is bound to. Only events from this tab are accepted. | `127` | All sessions |
| `startTime` | string | Session start time stored in human-readable `YY-MM-DD HH:MM:SS` format. | `"26-03-27 19:00:03"` | All sessions |
| `startTimeMs` | number | Unix milliseconds for the same instant as `startTime`. Used for calculations and ordering. | `1774605603757` | All sessions |
| `endTime` | string or `null` | Stop time stored in `YY-MM-DD HH:MM:SS` format, or `null` while the session is still active. | `"26-03-27 19:00:41"` | All sessions |
| `endTimeMs` | number or `null` | Unix milliseconds for the same instant as `endTime`, or `null` while active. | `1774605641042` | All sessions |
| `startedUrl` | string | URL of the active tab at session start. | `"https://example.com/login"` | All sessions |
| `endedUrl` | string | Last URL seen in accepted events. Initially equals `startedUrl`. | `"https://example.com/dashboard"` | All sessions |
| `userAgent` | string | Browser user agent string taken from the background worker context. | `"Mozilla/5.0 ..."` | All sessions |
| `eventCount` | number | Number of stored events. In code this is always `events.length`. | `42` | All sessions |
| `events` | array of objects | Ordered event records for the session. | `[ {...}, {...} ]` | All sessions |

### Event-level fields

| Field name | Datatype | Description / meaning | Example value | When it appears |
| --- | --- | --- | --- | --- |
| `index` | number | Zero-based event order within the session. Added in `background.js`. | `0` | All stored events |
| `type` | string | Event type name. | `"click"` | All stored events |
| `timestamp` | string | Event creation time stored in human-readable `YY-MM-DD HH:MM:SS` format. | `"26-03-27 19:00:04"` | All stored events |
| `timestampMs` | number | Unix milliseconds for the same instant as `timestamp`. Used for sorting and duration math. | `1774605604363` | All stored events |
| `elapsedMs` | number | Milliseconds since `session.startTimeMs`. Added in `background.js`. | `1217` | All stored events |
| `delay` | number | Milliseconds since the previous stored event. For the first event it is `0`. | `318` | All stored events |
| `url` | string | `window.location.href` at the moment of the event. | `"https://example.com/form"` | All stored events except the synthetic `session_start` event also has it from tab state |
| `title` | string | `document.title` for content-script events, or the tab title for `session_start`. | `"Example Form"` | All stored events |
| `viewportWidth` | number or `null` | Browser viewport width in CSS pixels. `session_start` sets this to `null`; content-script events use `window.innerWidth`. | `1440` | All events; `null` only for `session_start` |
| `viewportHeight` | number or `null` | Browser viewport height in CSS pixels. `session_start` sets this to `null`; content-script events use `window.innerHeight`. | `821` | All events; `null` only for `session_start` |
| `scrollX` | number or `null` | Horizontal scroll offset. `session_start` sets this to `null`; content-script events use `window.scrollX`. | `0` | All events; `null` only for `session_start` |
| `scrollY` | number or `null` | Vertical scroll offset. `session_start` sets this to `null`; content-script events use `window.scrollY`. | `640` | All events; `null` only for `session_start` |
| `x` | number | Mouse event `clientX`. | `512` | `click`, `dblclick`, `contextmenu`, `mousemove` |
| `y` | number | Mouse event `clientY`. | `284` | `click`, `dblclick`, `contextmenu`, `mousemove` |
| `pageX` | number | Mouse event `pageX`. | `512` | `click`, `dblclick`, `contextmenu`, `mousemove` |
| `pageY` | number | Mouse event `pageY`. | `924` | `click`, `dblclick`, `contextmenu`, `mousemove` |
| `button` | number | Mouse button code from the DOM event. Common values are `0` left, `1` middle, `2` right. | `0` | `click`, `dblclick`, `contextmenu`, `mousemove` |
| `key` | string | Keyboard key value. | `"Enter"` | `keydown` |
| `code` | string | Physical keyboard code. | `"Enter"` or `"KeyA"` | `keydown` |
| `ctrlKey` | boolean | Whether Control was pressed. | `false` | `keydown` |
| `shiftKey` | boolean | Whether Shift was pressed. | `true` | `keydown` |
| `altKey` | boolean | Whether Alt was pressed. | `false` | `keydown` |
| `metaKey` | boolean | Whether Meta/Command was pressed. | `false` | `keydown` |
| `tagName` | string | Lowercased target element tag name. | `"button"` | Events whose target has `tagName` |
| `id` | string | Target element `id` if present. | `"submit-btn"` | Events whose target element has an `id` |
| `className` | string | Target element `className` only when it is a string. | `"btn primary"` | Events whose target element has a string class name |
| `text` | string | Trimmed text from `innerText` or `textContent`, truncated to 50 characters plus `...` if longer. Not collected for `input`, `textarea`, or `select` elements. | `"Continue"` | Non-form targets with readable text |
| `ariaLabel` | string | Target element `aria-label` attribute. | `"Search"` | Targets with an `aria-label` |
| `name` | string | Target element `name` property. | `"email"` | Targets with a `name` |
| `role` | string | Target element `role` attribute. | `"button"` | Targets with a `role` |
| `href` | string | Target element `href` if present. | `"https://example.com/help"` | Link-like targets |
| `selector` | string | Heuristic selector string built from the target element. It prefers `#id`, then `data-testid`, `aria-label`, `name`, `role`, otherwise up to 3 DOM levels with tag/class names. | `"button[aria-label=\"Search\"]"` | Events whose target has `tagName` |
| `inputType` | string | Input type classification. For `input`/`textarea`, this is the lowercased `type` or `"text"` fallback. For `select`, it is `"select"`. | `"email"` | `input`, `change`, `focus`, `blur`, or other target-based events on form controls |
| `checked` | boolean | Checkbox/radio checked state from the element's `checked` property. For other input types it may still appear as `false` because the code copies `t.checked` directly. | `true` | Target is `input` or `textarea` |
| `valueLength` | number | Length of the current input value string. Raw text is not stored here, only its length. | `12` | Target is `input` or `textarea` and `value` exists |
| `maskedValue` | string | String of asterisks with the same length as the input value. Created for input types `password`, `email`, `tel`, `search`, `text`, `url`, `number`, `date`, and for all `textarea` values. | `"************"` | Masked `input`/`textarea` values only |
| `selectedText` | string | Visible text of the currently selected `<option>`. | `"United States"` | Target is `select` with a selected option |
| `visibilityState` | string | `document.visibilityState` at the time of the visibility change. | `"hidden"` | `visibility_change` |

Notes on field presence:

- Not every event has every field.
- Fields are omitted when the extraction code leaves them `undefined`.
- `session_start` is the only event that is created in the background script rather than the content script, so it has a smaller field set and `viewportWidth`, `viewportHeight`, `scrollX`, and `scrollY` are explicitly `null`.

## 7. Interpretation guide for researchers

### How to read timing fields

- `timestamp` is the human-readable event time string.
- `timestampMs` is the raw Unix-millisecond value for the same event time.
- `elapsedMs` is time since the session started. This is useful for reconstructing the participant timeline within the task.
- `delay` is the time gap from the immediately previous stored event. Large `delay` values can indicate pauses, reading time, hesitation, task planning, or idle time, but they do not by themselves explain why the participant paused.

### How to read page and navigation signals

- `page_load` indicates that logging became active on a page in the tracked tab.
- `page_unload` indicates that the tracked page began unloading.
- A sequence such as `page_unload` followed later by `page_load` usually means navigation or reload in the same tracked tab.
- `startedUrl` is the first page URL of the session.
- `endedUrl` is simply the last URL seen in accepted events, not necessarily a formal "final completed page."

### How to read target information

- `selector`, `tagName`, `id`, `className`, `text`, `ariaLabel`, `name`, `role`, and `href` help identify what the participant interacted with.
- These fields are best treated as heuristics for identifying interface targets.
- `selector` is not guaranteed to be unique or stable across builds.
- `text` may be truncated and is not collected for form fields.

### How to read mouse and scroll data

- `click`, `dblclick`, and `contextmenu` show explicit pointer actions on a target.
- `mousemove` is sampled, not continuous. Because of the `100 ms` / `10 px` filters, absence of a movement record does not mean the mouse was stationary.
- `scroll` is also sampled at `150 ms`, so it shows scrolling activity but not every intermediate browser scroll event.
- Coordinates (`x`, `y`, `pageX`, `pageY`) show pointer position at the sampled event time only.

### How to read keyboard and form data

- `keydown` records key metadata such as `key`, `code`, and modifier flags. It does not capture full text entry by itself.
- `input` and `change` indicate interaction with form controls.
- For text-like form fields, the implementation stores `valueLength` and `maskedValue`, not the raw entered value.
- `maskedValue` preserves only character count, not content.
- For `<select>`, the visible `selectedText` is stored.
- `checked` can help interpret checkbox/radio state changes, but because the code reads `t.checked` directly, non-checkable inputs may still show `false`. That should not be over-interpreted.

### How to read focus and visibility events

- `focus` and `blur` show which element gained or lost focus.
- These events can be noisy in complex web apps and should be interpreted cautiously.
- `visibility_change` reflects page visibility changes such as the page becoming hidden or visible, but it does not by itself tell you why that happened.

### What cannot be inferred reliably

- Exact participant intention or reasoning.
- Exact typed text for masked input types.
- Complete pointer trajectory between sampled `mousemove` events.
- Full DOM or application state at each moment.
- Behavior in other tabs or windows outside the tracked tab.

## 8. Privacy / data handling

The current implementation stores all session data locally in Chrome's `chrome.storage.local` until the researcher clears it or the extension data is removed.

Input handling in the current code:

- Raw values from `input` and `textarea` are not exported.
- For many text-like input types (`password`, `email`, `tel`, `search`, `text`, `url`, `number`, `date`) and for all `textarea` elements, the extension stores:
  - `valueLength`
  - `maskedValue` as asterisks of the same length
- For `<select>`, the extension stores the visible selected option text as `selectedText`.
- Non-form element text may be stored in `text`, truncated to at most 50 characters plus `...`.
- Link destinations may be stored in `href`.
- Page URLs and titles are stored for every event.

Privacy caveats:

- Even without raw typed text, URLs, titles, selected option text, visible element text, ARIA labels, names, roles, and hrefs may still contain sensitive information depending on the website.
- Because the extension runs on `<all_urls>`, researchers should use it only in environments where this level of page metadata collection is appropriate and consented.

## 9. Known limitations

These limitations are based on the current implementation, not an intended design.

- Single-session only: only one `session` object is stored at a time.
- Single-tab only: only the tab active at start time is logged.
- Same-tab navigation only: navigation can continue to be logged only within that same tab ID.
- `session_stop` is implemented but usually not persisted because the session is ended before the event is accepted.
- `page_load` is a synthetic event meaning "logging became active on this page," not a browser performance timing metric.
- `mousemove` and `scroll` are sampled, so the logs are incomplete by design.
- `selector` generation is heuristic and may be unstable across UI changes.
- `text` is truncated and may not uniquely identify an element.
- `focus` and `blur` may be noisy in modern web apps.
- No IME-specific handling is implemented for non-English text entry; keyboard logs are limited to `keydown` metadata.
- No raw text input is stored for text-like fields, so typed content cannot be reconstructed.
- The popup shows the current session state by polling once per second; this affects only the popup display, not event capture.
- No validation is enforced for researcher-entered IDs.

## 10. Example JSON structure

This example reflects the current exported structure and field naming. Not every field appears on every event.

```json
{
  "participantId": "P01",
  "taskId": "Task_1",
  "sessionId": "S418233",
  "tabId": 127,
  "startTime": 1768792054123,
  "endTime": 1768792120331,
  "startedUrl": "https://example.com/login",
  "endedUrl": "https://example.com/dashboard",
  "userAgent": "Mozilla/5.0 ...",
  "eventCount": 5,
  "events": [
    {
      "index": 0,
      "type": "session_start",
      "timestamp": 1768792054123,
      "elapsedMs": 0,
      "delay": 0,
      "url": "https://example.com/login",
      "title": "Example Login",
      "viewportWidth": null,
      "viewportHeight": null,
      "scrollX": null,
      "scrollY": null
    },
    {
      "index": 1,
      "type": "page_load",
      "timestamp": 1768792054300,
      "elapsedMs": 177,
      "delay": 177,
      "url": "https://example.com/login",
      "title": "Example Login",
      "viewportWidth": 1440,
      "viewportHeight": 821,
      "scrollX": 0,
      "scrollY": 0
    },
    {
      "index": 2,
      "type": "click",
      "timestamp": 1768792055340,
      "elapsedMs": 1217,
      "delay": 1040,
      "url": "https://example.com/login",
      "title": "Example Login",
      "viewportWidth": 1440,
      "viewportHeight": 821,
      "scrollX": 0,
      "scrollY": 0,
      "x": 512,
      "y": 284,
      "pageX": 512,
      "pageY": 284,
      "button": 0,
      "tagName": "button",
      "id": "submit-btn",
      "className": "btn primary",
      "text": "Sign in",
      "selector": "#submit-btn"
    },
    {
      "index": 3,
      "type": "input",
      "timestamp": 1768792056900,
      "elapsedMs": 2777,
      "delay": 1560,
      "url": "https://example.com/login",
      "title": "Example Login",
      "viewportWidth": 1440,
      "viewportHeight": 821,
      "scrollX": 0,
      "scrollY": 0,
      "tagName": "input",
      "name": "email",
      "selector": "input[name=\"email\"]",
      "inputType": "email",
      "checked": false,
      "valueLength": 12,
      "maskedValue": "************"
    },
    {
      "index": 4,
      "type": "visibility_change",
      "timestamp": 1768792059000,
      "elapsedMs": 4877,
      "delay": 2100,
      "url": "https://example.com/login",
      "title": "Example Login",
      "viewportWidth": 1440,
      "viewportHeight": 821,
      "scrollX": 0,
      "scrollY": 0,
      "visibilityState": "hidden"
    }
  ]
}
```

## Verification notes

This README was derived directly from the current code in:

- `manifest.json`
- `background.js`
- `content.js`
- `popup.js`
- `popup.html`
- `popup.css`

The event list, field names, throttling values, storage behavior, export structure, and the `session_stop` caveat were all checked against those files rather than inferred from an intended design.
