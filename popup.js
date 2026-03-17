document.addEventListener('DOMContentLoaded', () => {
    const elements = {
        participantId: document.getElementById('participantId'),
        taskId: document.getElementById('taskId'),
        sessionId: document.getElementById('sessionId'),
        startBtn: document.getElementById('startBtn'),
        stopBtn: document.getElementById('stopBtn'),
        exportBtn: document.getElementById('exportBtn'),
        clearBtn: document.getElementById('clearBtn'),
        statusText: document.getElementById('statusText'),
        eventCount: document.getElementById('eventCount'),
        currentUrl: document.getElementById('currentUrl')
    };

    function updateStatus() {
        chrome.runtime.sendMessage({ type: 'GET_STATE' }, (res) => {
            if (chrome.runtime.lastError || !res) return;
            const { active, session } = res;

            if (active) {
                elements.statusText.textContent = 'Logging ON';
                elements.statusText.style.color = '#4caf50';
                elements.startBtn.disabled = true;
                elements.stopBtn.disabled = false;

                elements.participantId.disabled = true;
                elements.taskId.disabled = true;
                elements.sessionId.disabled = true;
            } else {
                elements.statusText.textContent = 'Logging OFF';
                elements.statusText.style.color = '#f44336';
                elements.startBtn.disabled = false;
                elements.stopBtn.disabled = true;

                elements.participantId.disabled = false;
                elements.taskId.disabled = false;
                elements.sessionId.disabled = false;
            }

            if (session) {
                elements.participantId.value = session.participantId || '';
                elements.taskId.value = session.taskId || '';
                elements.sessionId.value = session.sessionId || '';

                elements.eventCount.textContent = `Events: ${session.eventCount || 0}`;
                elements.currentUrl.textContent = `Tab: ${session.tabId} | URL: ${session.endedUrl || session.startedUrl || ''}`;

                elements.exportBtn.disabled = false;
                elements.clearBtn.disabled = false;
            } else {
                elements.eventCount.textContent = 'Events: 0';
                elements.currentUrl.textContent = 'No active session data';
                elements.exportBtn.disabled = true;
                elements.clearBtn.disabled = true;
            }
        });
    }

    elements.startBtn.addEventListener('click', () => {
        const participantId = elements.participantId.value || 'P1';
        const taskId = elements.taskId.value || 'T1';
        let sessionId = elements.sessionId.value;
        if (!sessionId) {
            sessionId = 'S' + Math.floor(Math.random() * 1000000);
            elements.sessionId.value = sessionId;
        }

        chrome.runtime.sendMessage({
            type: 'START',
            participantId,
            taskId,
            sessionId
        }, () => {
            updateStatus();
        });
    });

    elements.stopBtn.addEventListener('click', () => {
        chrome.runtime.sendMessage({ type: 'STOP' }, () => {
            updateStatus();
        });
    });

    elements.clearBtn.addEventListener('click', () => {
        if (confirm('Are you sure you want to clear session data?')) {
            chrome.runtime.sendMessage({ type: 'CLEAR' }, () => {
                elements.participantId.value = '';
                elements.taskId.value = '';
                elements.sessionId.value = '';
                updateStatus();
            });
        }
    });

    elements.exportBtn.addEventListener('click', () => {
        chrome.runtime.sendMessage({ type: 'GET_STATE' }, (res) => {
            if (res && res.session) {
                const payload = JSON.stringify(res.session, null, 2);
                const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(payload);
                const a = document.createElement('a');
                a.href = dataStr;
                a.download = `cwlog_${res.session.participantId}_${res.session.taskId}_${res.session.sessionId}.json`;
                document.body.appendChild(a);
                a.click();
                a.remove();
            }
        });
    });

    updateStatus();
    setInterval(updateStatus, 1000);
});
