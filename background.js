let session = null;
let saveTimeout = null;

function pad2(value) {
    return String(value).padStart(2, '0');
}

function formatTimestamp(tsMs) {
    const date = new Date(tsMs);
    return `${pad2(date.getFullYear() % 100)}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())} ${pad2(date.getHours())}:${pad2(date.getMinutes())}:${pad2(date.getSeconds())}`;
}

function ensureNavigationState() {
    if (!session) return;

    if (!Array.isArray(session.navigationStack) || session.navigationStack.length === 0) {
        const seedUrl = session.endedUrl || session.startedUrl || '';
        session.navigationStack = seedUrl ? [seedUrl] : [];
    }

    if (typeof session.navigationIndex !== 'number') {
        session.navigationIndex = Math.max(0, session.navigationStack.length - 1);
    }

    if (session.navigationIndex >= session.navigationStack.length) {
        session.navigationIndex = Math.max(0, session.navigationStack.length - 1);
    }
}

function findHistoryIndex(url, currentIndex) {
    if (!session || !Array.isArray(session.navigationStack) || !url) return -1;

    for (let i = currentIndex - 1; i >= 0; i -= 1) {
        if (session.navigationStack[i] === url) return i;
    }

    for (let i = currentIndex + 1; i < session.navigationStack.length; i += 1) {
        if (session.navigationStack[i] === url) return i;
    }

    return -1;
}

function updateNavigationState(event) {
    if (!session || !event || !event.url) return;

    ensureNavigationState();
    const currentIndex = session.navigationIndex;
    const currentUrl = session.navigationStack[currentIndex];

    if (event.type === 'page_load' && event.navigationType === 'back_forward') {
        const matchedIndex = findHistoryIndex(event.url, currentIndex);
        if (matchedIndex >= 0) {
            event.historyTraversal = matchedIndex < currentIndex ? 'back' : 'forward';
            session.navigationIndex = matchedIndex;
            if (event.historyTraversal === 'back') {
                event.type = 'back_navigation';
            }
            return;
        }
    }

    if (event.type === 'page_load' || event.type === 'back_navigation') {
        if (currentUrl !== event.url) {
            session.navigationStack = session.navigationStack.slice(0, currentIndex + 1);
            session.navigationStack.push(event.url);
            session.navigationIndex = session.navigationStack.length - 1;
        }
    }
}

// Load existing session on startup to survive service worker inactivity
chrome.storage.local.get(['session'], (res) => {
    if (res.session) {
        session = res.session;
    }
});

// Debounce save to prevent throttling issues with high event volumes
function saveSession() {
    if (saveTimeout) clearTimeout(saveTimeout);
    saveTimeout = setTimeout(() => {
        if (session) {
            chrome.storage.local.set({ session });
        } else {
            chrome.storage.local.remove('session');
        }
    }, 250);
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (msg.type === 'GET_STATE') {
        sendResponse({ active: !!session && !session.endTime, session });

    } else if (msg.type === 'START') {
        chrome.tabs.query({active: true, currentWindow: true}, (tabs) => {
            if (!tabs[0]) {
                sendResponse({ success: false });
                return;
            }

            const startTime = Date.now();
            session = {
                participantId: msg.participantId,
                taskId: msg.taskId,
                sessionId: msg.sessionId,
                tabId: tabs[0].id,
                startTime: formatTimestamp(startTime),
                startTimeMs: startTime,
                endTime: null,
                endTimeMs: null,
                startedUrl: tabs[0].url,
                endedUrl: tabs[0].url,
                userAgent: navigator.userAgent,
                eventCount: 1,
                navigationStack: [tabs[0].url],
                navigationIndex: 0,
                events: []
            };

            // Inject the initial session_start event
            session.events.push({
                index: 0,
                type: 'session_start',
                timestamp: formatTimestamp(startTime),
                timestampMs: startTime,
                elapsedMs: 0,
                delay: 0,
                url: tabs[0].url,
                title: tabs[0].title || '',
                viewportWidth: null,
                viewportHeight: null,
                scrollX: null,
                scrollY: null
            });

            saveSession();
            chrome.tabs.sendMessage(tabs[0].id, { type: 'START_RECORDING' }).catch(() => {});
            sendResponse({ success: true });
        });
        return true; // async response indicating we'll call sendResponse later

    } else if (msg.type === 'STOP') {
        if (session && !session.endTime) {
            const endTime = Date.now();
            session.endTime = formatTimestamp(endTime);
            session.endTimeMs = endTime;
            saveSession();
            chrome.tabs.sendMessage(session.tabId, { type: 'STOP_RECORDING' }).catch(() => {});
        }
        sendResponse({ success: true });

    } else if (msg.type === 'CLEAR') {
        if (session && !session.endTime) {
            chrome.tabs.sendMessage(session.tabId, { type: 'STOP_RECORDING' }).catch(() => {});
        }
        session = null;
        saveSession();
        sendResponse({ success: true });

    } else if (msg.type === 'CHECK_ACTIVE') {
        const active = !!session && !session.endTime && sender.tab && sender.tab.id === session.tabId;
        sendResponse({ active });

    } else if (msg.type === 'LOG_EVENT') {
        if (session && !session.endTime && sender.tab && sender.tab.id === session.tabId) {
            const event = msg.event || {};
            updateNavigationState(event);
            event.index = session.events.length;
            const eventTs = event.timestampMs ?? event.timestamp;
            const sessionStartTs = session.startTimeMs ?? session.startTime;
            event.elapsedMs = eventTs - sessionStartTs;

            let delay = 0;
            if (session.events.length > 0) {
                const prevTs = session.events[session.events.length - 1].timestampMs ?? session.events[session.events.length - 1].timestamp;
                delay = eventTs - prevTs;
            }
            event.delay = delay;

            session.events.push(event);
            session.eventCount = session.events.length;
            if (event.url) {
                session.endedUrl = event.url;
            }

            saveSession();
        }
        sendResponse({ success: true });
    }
});
