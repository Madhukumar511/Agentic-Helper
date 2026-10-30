// ==UserScript==
// @name         Quiz-Pilot AI HUD
// @namespace    https://github.com/atomic/quiz-pilot
// @version      1.0.0
// @description  AI-powered LMS Quiz Auto-Pilot with Floating HUD for Canvas, Moodle, Blackboard, and Coursera.
// @author       Antigravity
// @match        *://*/*quiz*
// @match        *://*/*exam*
// @match        *://*/*test*
// @match        *://*/*assessment*
// @match        *://*.instructure.com/*
// @match        *://*moodle*/*
// @match        *://*blackboard*/*
// @match        *://*.coursera.org/*
// @grant        GM_xmlhttpRequest
// @run-at       document-end
// ==/UserScript==

// Injects the Quiz-Pilot HUD directly into matching LMS pages
(function() {
    'use strict';
    const script = document.createElement('script');
    script.src = 'http://127.0.0.1:8765/hud.js';
    script.onload = () => console.log('[Quiz-Pilot Userscript] HUD script injected.');
    script.onerror = () => {
        // Fallback: If server isn't running, alert the user
        console.warn('[Quiz-Pilot Userscript] Could not reach http://127.0.0.1:8765. Make sure `quiz-pilot server` is running.');
    };
    document.head.appendChild(script);
})();
