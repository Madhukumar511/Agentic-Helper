/**
 * Quiz-Pilot In-Browser HUD & Agent WebSocket Bridge
 * Connects directly to the Antigravity Agent over ws://127.0.0.1:8765/ws
 */

(() => {
    if (window.__QUIZ_PILOT_LOADED__) {
        console.log('[Quiz-Pilot] HUD already active.');
        return;
    }
    window.__QUIZ_PILOT_LOADED__ = true;

    const WS_URL = 'ws://127.0.0.1:8765/ws';
    let ws = null;
    let solvedCount = 0;

    // Create floating Agent HUD
    const container = document.createElement('div');
    container.id = 'quiz-pilot-hud';
    container.style.cssText = `
        position: fixed;
        bottom: 24px;
        right: 24px;
        z-index: 9999999;
        background: rgba(15, 23, 42, 0.95);
        backdrop-filter: blur(12px);
        border: 1px solid rgba(56, 189, 248, 0.3);
        border-radius: 14px;
        padding: 16px 20px;
        color: #f1f5f9;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        font-size: 13px;
        box-shadow: 0 16px 40px rgba(0, 0, 0, 0.5);
        width: 330px;
        user-select: none;
        transition: all 0.3s ease;
    `;

    container.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 8px;">
            <div style="font-weight: 700; font-size: 14px; color: #38bdf8; display: flex; align-items: center; gap: 8px;">
                <span>🤖 Antigravity Pilot</span>
                <span id="qp-status-badge" style="font-size: 10px; background: #ea580c; color: white; padding: 2px 8px; border-radius: 999px;">CONNECTING</span>
            </div>
            <button id="qp-close-btn" style="background: none; border: none; color: #94a3b8; font-size: 18px; cursor: pointer;">✕</button>
        </div>

        <div style="margin-bottom: 12px; line-height: 1.5;">
            <div style="display: flex; justify-content: space-between; color: #94a3b8; font-size: 12px;">
                <span>Agent Solved: <strong id="qp-count" style="color: #4ade80;">0</strong></span>
                <span id="qp-page-badge" style="color: #cbd5e1;">Scanning...</span>
            </div>
            <div id="qp-status-text" style="color: #93c5fd; margin-top: 6px; font-size: 12px; height: 36px; overflow: hidden; text-overflow: ellipsis; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;">
                Connecting to Antigravity agent...
            </div>
        </div>

        <div style="display: flex; gap: 8px;">
            <button id="qp-rescan-btn" style="flex: 1; background: rgba(56, 189, 248, 0.15); border: 1px solid #38bdf8; color: #38bdf8; padding: 6px 12px; border-radius: 8px; font-weight: 600; cursor: pointer; font-size: 12px;">
                🔄 Sync with Agent
            </button>
        </div>
    `;

    document.body.appendChild(container);

    const countEl = document.getElementById('qp-count');
    const pageBadgeEl = document.getElementById('qp-page-badge');
    const statusTextEl = document.getElementById('qp-status-text');
    const statusBadgeEl = document.getElementById('qp-status-badge');
    const rescanBtn = document.getElementById('qp-rescan-btn');
    const closeBtn = document.getElementById('qp-close-btn');

    closeBtn.onclick = () => container.remove();

    function setStatus(badge, badgeBg, text) {
        statusBadgeEl.innerText = badge;
        statusBadgeEl.style.background = badgeBg;
        statusTextEl.innerText = text;
    }

    // Question extraction logic
    function scanQuestions() {
        const questions = [];

        // 1. Canvas LMS
        const canvasEls = document.querySelectorAll('.question.quiz_question, .display_question');
        if (canvasEls.length > 0) {
            canvasEls.forEach((qEl, qIdx) => {
                const textEl = qEl.querySelector('.question_text') || qEl;
                const optEls = qEl.querySelectorAll('.answer, .answer_label');
                const options = Array.from(optEls).map((a, optIdx) => {
                    const input = a.querySelector('input[type="radio"], input[type="checkbox"]');
                    const label = a.querySelector('label, .answer_label, .answer_text') || a;
                    a.setAttribute('data-qp-q', qIdx);
                    a.setAttribute('data-qp-opt', optIdx);
                    if (input) input.setAttribute('data-qp-input', `${qIdx}-${optIdx}`);

                    return {
                        index: optIdx,
                        text: (label.innerText || '').trim(),
                        checked: input ? input.checked : false
                    };
                }).filter(o => o.text.length > 0);

                questions.push({
                    index: qIdx,
                    text: (textEl.innerText || '').trim(),
                    options: options
                });
            });
            return questions;
        }

        // 2. Moodle
        const moodleEls = document.querySelectorAll('.que.multichoice, .que.truefalse, .que');
        if (moodleEls.length > 0) {
            moodleEls.forEach((qEl, qIdx) => {
                const textEl = qEl.querySelector('.qtext');
                const optRows = qEl.querySelectorAll('.answer > div, .answer .r0, .answer .r1');
                const options = Array.from(optRows).map((row, optIdx) => {
                    const input = row.querySelector('input[type="radio"], input[type="checkbox"]');
                    const label = row.querySelector('label, .flex-fill') || row;
                    row.setAttribute('data-qp-q', qIdx);
                    row.setAttribute('data-qp-opt', optIdx);
                    if (input) input.setAttribute('data-qp-input', `${qIdx}-${optIdx}`);

                    return {
                        index: optIdx,
                        text: (label.innerText || '').trim(),
                        checked: input ? input.checked : false
                    };
                }).filter(o => o.text.length > 0);

                questions.push({
                    index: qIdx,
                    text: (textEl ? textEl.innerText : '').trim(),
                    options: options
                });
            });
            return questions;
        }

        // 3. Generic radio group detection
        const radioGroups = {};
        document.querySelectorAll('input[type="radio"], input[type="checkbox"]').forEach(input => {
            const name = input.name || 'default_group';
            if (!radioGroups[name]) radioGroups[name] = [];
            radioGroups[name].push(input);
        });

        let genIdx = 0;
        for (const [name, inputs] of Object.entries(radioGroups)) {
            if (inputs.length < 2) continue;
            const container = inputs[0].closest('fieldset, .form-group, tr, div') || inputs[0].parentElement;
            let title = container.querySelector('legend, h1, h2, h3, h4, h5, p')?.innerText || `Question ${genIdx + 1}`;
            
            const options = inputs.map((inp, optIdx) => {
                const label = document.querySelector(`label[for="${inp.id}"]`) || inp.closest('label') || inp.parentElement;
                inp.setAttribute('data-qp-input', `${genIdx}-${optIdx}`);
                if (label) {
                    label.setAttribute('data-qp-q', genIdx);
                    label.setAttribute('data-qp-opt', optIdx);
                }

                return {
                    index: optIdx,
                    text: (label ? label.innerText : inp.value || `Option ${optIdx + 1}`).trim(),
                    checked: inp.checked
                };
            });

            questions.push({
                index: genIdx++,
                text: title.trim(),
                options: options
            });
        }

        return questions;
    }

    function clickOptionSafely(qIdx, optIdx) {
        const input = document.querySelector(`input[data-qp-input="${qIdx}-${optIdx}"]`);
        const label = document.querySelector(`[data-qp-q="${qIdx}"][data-qp-opt="${optIdx}"]`);
        const target = label || input;

        if (!target) return false;

        target.scrollIntoView({ behavior: 'smooth', block: 'center' });
        ['mouseenter', 'mousedown', 'mouseup', 'click'].forEach(evt => {
            target.dispatchEvent(new MouseEvent(evt, { bubbles: true, cancelable: true, view: window }));
        });

        if (input) {
            input.checked = true;
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.dispatchEvent(new Event('change', { bubbles: true }));
        }

        // Visual flash highlight
        target.style.transition = 'background 0.3s';
        const origBg = target.style.backgroundColor;
        target.style.backgroundColor = 'rgba(74, 222, 128, 0.35)';
        setTimeout(() => target.style.backgroundColor = origBg, 1200);

        solvedCount++;
        countEl.innerText = solvedCount;
        return true;
    }

    function clickNextPage() {
        const buttons = Array.from(document.querySelectorAll('button, input[type="submit"], input[type="button"], a.btn'));
        for (const btn of buttons) {
            const txt = (btn.innerText || btn.value || '').trim().toLowerCase();
            if (txt.includes('next') || txt === 'continue' || txt === 'next page') {
                btn.scrollIntoView({ behavior: 'smooth', block: 'center' });
                btn.click();
                return true;
            }
        }
        return false;
    }

    function sendCurrentState() {
        if (!ws || ws.readyState !== WebSocket.OPEN) return;
        const questions = scanQuestions();
        pageBadgeEl.innerText = `${questions.length} Question(s)`;
        ws.send(JSON.stringify({
            type: 'page_state',
            url: window.location.href,
            title: document.title,
            questions: questions
        }));
        setStatus('CONNECTED', '#10b981', `Ready. Sent ${questions.length} question(s) to Agent.`);
    }

    function connectWebSocket() {
        ws = new WebSocket(WS_URL);

        ws.onopen = () => {
            setStatus('CONNECTED', '#10b981', 'Connected to Antigravity Agent!');
            sendCurrentState();
        };

        ws.onmessage = (event) => {
            try {
                const msg = JSON.parse(event.data);
                if (msg.type === 'click_option') {
                    setStatus('CLICKING', '#3b82f6', `Agent clicked Q${msg.q + 1} -> Option ${msg.opt}`);
                    const ok = clickOptionSafely(msg.q, msg.opt);
                    ws.send(JSON.stringify({ type: 'action_result', action: 'click_option', success: ok }));
                } else if (msg.type === 'click_next') {
                    setStatus('NAVIGATING', '#8b5cf6', 'Agent clicked Next Page...');
                    const ok = clickNextPage();
                    ws.send(JSON.stringify({ type: 'action_result', action: 'click_next', success: ok }));
                    setTimeout(sendCurrentState, 1500);
                }
            } catch (err) {
                console.error('[Quiz-Pilot] Error processing ws message:', err);
            }
        };

        ws.onclose = () => {
            setStatus('DISCONNECTED', '#ef4444', 'Agent disconnected. Retrying in 3s...');
            setTimeout(connectWebSocket, 3000);
        };

        ws.onerror = (e) => {
            setStatus('ERROR', '#dc2626', 'Cannot reach agent on port 8765.');
        };
    }

    rescanBtn.onclick = () => {
        sendCurrentState();
    };

    // Auto-detect dynamic SPA changes
    const observer = new MutationObserver(() => {
        // Debounced sync on major DOM changes
        clearTimeout(window.__qp_sync_timer);
        window.__qp_sync_timer = setTimeout(sendCurrentState, 1200);
    });
    observer.observe(document.body, { childList: true, subtree: true });

    connectWebSocket();
})();
