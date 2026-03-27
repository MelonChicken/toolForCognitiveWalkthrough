let isRecording = false;

function pad2(value) {
    return String(value).padStart(2, '0');
}

function formatTimestamp(tsMs) {
    const date = new Date(tsMs);
    return `${pad2(date.getFullYear() % 100)}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())} ${pad2(date.getHours())}:${pad2(date.getMinutes())}:${pad2(date.getSeconds())}`;
}

function getNavigationType() {
    const navEntry = performance.getEntriesByType('navigation')[0];
    if (navEntry && typeof navEntry.type === 'string') {
        return navEntry.type;
    }

    if (performance.navigation) {
        switch (performance.navigation.type) {
            case 1:
                return 'reload';
            case 2:
                return 'back_forward';
            default:
                return 'navigate';
        }
    }

    return 'navigate';
}

function emitPageEntry(extraData = {}) {
    logEvent('page_load', {
        navigationType: getNavigationType(),
        ...extraData
    });
}

// Ask Background if there's an active session on this tabId
function checkState() {
    chrome.runtime.sendMessage({ type: 'CHECK_ACTIVE' }, (res) => {
        if (chrome.runtime.lastError) return;
        if (res && res.active) {
            isRecording = true;
            emitPageEntry();
            attachListeners();
        }
    });
}

chrome.runtime.onMessage.addListener((msg) => {
    if (msg.type === 'START_RECORDING') {
        if (!isRecording) {
            isRecording = true;
            emitPageEntry();
            attachListeners();
        }
    } else if (msg.type === 'STOP_RECORDING') {
        if (isRecording) {
            logEvent('session_stop', {});
            removeListeners();
            isRecording = false;
        }
    }
});

// Synthetic page events
window.addEventListener('beforeunload', () => {
    if (isRecording) logEvent('page_unload', {});
});

window.addEventListener('pageshow', (event) => {
    if (isRecording && event.persisted) {
        emitPageEntry({
            pageTransition: 'pageshow',
            persisted: true
        });
    }
});

document.addEventListener('visibilitychange', () => {
    if (isRecording) logEvent('visibility_change', { visibilityState: document.visibilityState });
});

// Throttling state
let lastMouseMoveTime = 0;
let lastMouseMoveX = -1;
let lastMouseMoveY = -1;
let lastScrollTime = 0;

function handleEvent(e) {
    if (!isRecording) return;

    const now = Date.now();
    if (e.type === 'mousemove') {
        if (now - lastMouseMoveTime < 100) return;
        const dx = e.clientX - lastMouseMoveX;
        const dy = e.clientY - lastMouseMoveY;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < 10 && lastMouseMoveTime !== 0) return;
        lastMouseMoveTime = now;
        lastMouseMoveX = e.clientX;
        lastMouseMoveY = e.clientY;
    } else if (e.type === 'scroll') {
        if (now - lastScrollTime < 150) return;
        lastScrollTime = now;
    }

    const eventData = extractEventData(e);
    logEvent(e.type, eventData);
}

const trackedEvents = ['click', 'dblclick', 'contextmenu', 'mousemove', 'scroll', 'keydown', 'input', 'change', 'focus', 'blur'];

function attachListeners() {
    trackedEvents.forEach(type => window.addEventListener(type, handleEvent, true));
}

function removeListeners() {
    trackedEvents.forEach(type => window.removeEventListener(type, handleEvent, true));
}

function extractEventData(e) {
    const data = {};

    if (['click', 'dblclick', 'contextmenu', 'mousemove'].includes(e.type)) {
        data.x = e.clientX;
        data.y = e.clientY;
        data.pageX = e.pageX;
        data.pageY = e.pageY;
        data.button = e.button;
    } else if (['keydown'].includes(e.type)) {
        data.key = e.key;
        data.code = e.code;
        data.ctrlKey = e.ctrlKey;
        data.shiftKey = e.shiftKey;
        data.altKey = e.altKey;
        data.metaKey = e.metaKey;
    }

    if (e.target && e.target.tagName) {
        const t = e.target;
        data.tagName = t.tagName.toLowerCase();
        data.id = t.id || undefined;
        data.className = typeof t.className === 'string' ? t.className : undefined;
        data.text = getSafeText(t);
        data.ariaLabel = t.getAttribute('aria-label') || undefined;
        data.name = t.name || undefined;
        data.role = t.getAttribute('role') || undefined;
        data.href = t.href || undefined;
        data.selector = buildSelector(t);

        // Privacy policy masking for inputs
        if (data.tagName === 'input' || data.tagName === 'textarea') {
            const type = (t.type || 'text').toLowerCase();
            data.inputType = type;
            data.checked = t.checked;
            if (t.value !== undefined) {
                data.valueLength = t.value.length;
                const maskTypes = ['password', 'email', 'tel', 'search', 'text', 'url', 'number', 'date'];
                if (maskTypes.includes(type) || data.tagName === 'textarea') {
                    data.maskedValue = '*'.repeat(t.value.length);
                }
            }
        } else if (data.tagName === 'select') {
            data.inputType = 'select';
            if (t.options && t.selectedIndex >= 0) {
                data.selectedText = t.options[t.selectedIndex].text;
            }
        }
    }

    // Clean empty values
    Object.keys(data).forEach(k => data[k] === undefined && delete data[k]);
    return data;
}

function getSafeText(el) {
    if (el.tagName && ['input', 'textarea', 'select'].includes(el.tagName.toLowerCase())) return undefined;
    let text = el.innerText || el.textContent;
    if (!text) return undefined;
    text = text.trim();
    return text.length > 50 ? text.substring(0, 50) + '...' : text;
}

function buildSelector(el) {
    if (!el || !el.tagName) return '';
    if (el.id) return `#${el.id}`;
    if (el.dataset && el.dataset.testid) return `${el.tagName.toLowerCase()}[data-testid="${el.dataset.testid}"]`;
    if (el.getAttribute('aria-label')) return `${el.tagName.toLowerCase()}[aria-label="${el.getAttribute('aria-label')}"]`;
    if (el.name) return `${el.tagName.toLowerCase()}[name="${el.name}"]`;
    if (el.getAttribute('role')) return `${el.tagName.toLowerCase()}[role="${el.getAttribute('role')}"]`;

    let path = [];
    let current = el;
    while (current && current.nodeType === Node.ELEMENT_NODE && path.length < 3) {
        let selector = current.tagName.toLowerCase();
        if (current.id) {
            selector += `#${current.id}`;
            path.unshift(selector);
            break;
        } else if (current.className && typeof current.className === 'string') {
            let classes = current.className.trim().split(/\s+/).filter(c => c);
            if (classes.length > 0) {
                selector += `.${classes.join('.')}`;
            }
        }
        path.unshift(selector);
        current = current.parentNode;
    }
    return path.join(' > ');
}

function logEvent(type, extraData) {
    const now = Date.now();
    const event = {
        type,
        timestamp: formatTimestamp(now),
        timestampMs: now,
        url: window.location.href,
        title: document.title,
        viewportWidth: window.innerWidth,
        viewportHeight: window.innerHeight,
        scrollX: window.scrollX,
        scrollY: window.scrollY,
        ...extraData
    };
    chrome.runtime.sendMessage({ type: 'LOG_EVENT', event }).catch(() => {});
}

// Check state immediately upon injection
checkState();
