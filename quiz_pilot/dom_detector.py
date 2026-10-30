"""
DOM Detector & Interaction Scripts for Quiz-Pilot.
Works across Canvas, Moodle, Blackboard, Coursera, and Generic LMS forms.
"""

DETECTION_SCRIPT = r"""
(() => {
    function cleanText(txt) {
        if (!txt) return "";
        return txt.replace(/\s+/g, ' ').trim();
    }

    function isVisible(elem) {
        if (!elem) return false;
        const style = window.getComputedStyle(elem);
        return style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0';
    }

    const platformDetectors = [
        // 1. Canvas LMS
        () => {
            const qElements = Array.from(document.querySelectorAll('.question.quiz_question, .display_question, .quiz_question'));
            if (qElements.length === 0) return null;

            return qElements.filter(isVisible).map((qEl, qIdx) => {
                const textEl = qEl.querySelector('.question_text') || qEl.querySelector('.text');
                const qText = cleanText(textEl ? textEl.innerText : qEl.innerText);
                const answersContainer = qEl.querySelector('.answers, .answers_wrapper') || qEl;
                
                const answerEls = Array.from(answersContainer.querySelectorAll('.answer, .answer_label'));
                const isMulti = qEl.querySelectorAll('input[type="checkbox"]').length > 0;
                
                const options = answerEls.map((aEl, optIdx) => {
                    const input = aEl.querySelector('input[type="radio"], input[type="checkbox"]');
                    const label = aEl.querySelector('label, .answer_label, .answer_text') || aEl;
                    const optText = cleanText(label.innerText);
                    const isChecked = input ? input.checked : aEl.classList.contains('selected');
                    
                    // Mark unique tracking ID on element
                    aEl.setAttribute('data-qp-q', qIdx);
                    aEl.setAttribute('data-qp-opt', optIdx);
                    if (input) input.setAttribute('data-qp-input', `${qIdx}-${optIdx}`);

                    return {
                        index: optIdx,
                        text: optText,
                        checked: isChecked,
                        selector: `[data-qp-opt="${optIdx}"][data-qp-q="${qIdx}"]`
                    };
                }).filter(o => o.text.length > 0);

                return {
                    id: qEl.id || `canvas-q-${qIdx}`,
                    platform: 'canvas',
                    index: qIdx,
                    text: qText,
                    type: isMulti ? 'multiple_choice' : 'single_choice',
                    options: options
                };
            });
        },

        // 2. Moodle
        () => {
            const qElements = Array.from(document.querySelectorAll('.que.multichoice, .que.truefalse, .que.multianswer, .que'));
            if (qElements.length === 0) return null;

            return qElements.filter(isVisible).map((qEl, qIdx) => {
                const textEl = qEl.querySelector('.qtext, .formulation .qtext');
                const qText = cleanText(textEl ? textEl.innerText : '');
                const answerContainer = qEl.querySelector('.answer');
                if (!answerContainer) return null;

                const answerRows = Array.from(answerContainer.querySelectorAll('div[class*="r"], .r0, .r1, .d-flex'));
                const isMulti = qEl.classList.contains('multianswer') || qEl.querySelectorAll('input[type="checkbox"]').length > 0;

                const options = answerRows.map((row, optIdx) => {
                    const input = row.querySelector('input[type="radio"], input[type="checkbox"]');
                    const label = row.querySelector('label, .flex-fill') || row;
                    const optText = cleanText(label.innerText);
                    const isChecked = input ? input.checked : false;

                    row.setAttribute('data-qp-q', qIdx);
                    row.setAttribute('data-qp-opt', optIdx);
                    if (input) input.setAttribute('data-qp-input', `${qIdx}-${optIdx}`);

                    return {
                        index: optIdx,
                        text: optText,
                        checked: isChecked,
                        selector: `[data-qp-opt="${optIdx}"][data-qp-q="${qIdx}"]`
                    };
                }).filter(o => o.text.length > 0);

                return {
                    id: qEl.id || `moodle-q-${qIdx}`,
                    platform: 'moodle',
                    index: qIdx,
                    text: qText,
                    type: isMulti ? 'multiple_choice' : 'single_choice',
                    options: options
                };
            }).filter(Boolean);
        },

        // 3. Coursera
        () => {
            const qElements = Array.from(document.querySelectorAll(
                'div[data-testid="quiz-question"], div.rc-Formulation, .c-question, div[class*="QuestionContainer"], div[aria-label*="Question"], section[aria-labelledby*="question"]'
            ));
            if (qElements.length === 0) return null;

            return qElements.filter(isVisible).map((qEl, qIdx) => {
                const textEl = qEl.querySelector('div[class*="QuestionBody"], .rc-Formulation, div[data-testid="legend"], h3, h4, p') || qEl;
                const qText = cleanText(textEl ? textEl.innerText : '');
                
                const optionEls = Array.from(qEl.querySelectorAll(
                    'label[data-testid="option-label"], div[role="radio"], div[role="checkbox"], .rc-Option, label[class*="option"], div[class*="OptionContainer"]'
                ));
                const inputs = Array.from(qEl.querySelectorAll('input[type="radio"], input[type="checkbox"]'));
                const isMulti = qEl.querySelectorAll('input[type="checkbox"], div[role="checkbox"]').length > 0;

                const candidates = optionEls.length > 0 ? optionEls : inputs;
                const options = candidates.map((optEl, optIdx) => {
                    const input = optEl.tagName === 'INPUT' ? optEl : optEl.querySelector('input[type="radio"], input[type="checkbox"]');
                    const optText = cleanText(optEl.innerText || (input ? input.value : ''));
                    const isChecked = input ? input.checked : (optEl.getAttribute('aria-checked') === 'true' || optEl.classList.contains('selected'));

                    optEl.setAttribute('data-qp-q', qIdx);
                    optEl.setAttribute('data-qp-opt', optIdx);
                    if (input) input.setAttribute('data-qp-input', `${qIdx}-${optIdx}`);

                    return {
                        index: optIdx,
                        text: optText,
                        checked: isChecked,
                        selector: `[data-qp-opt="${optIdx}"][data-qp-q="${qIdx}"]`
                    };
                }).filter(o => o.text.length > 0);

                return {
                    id: qEl.id || `coursera-q-${qIdx}`,
                    platform: 'coursera',
                    index: qIdx,
                    text: qText,
                    type: isMulti ? 'multiple_choice' : 'single_choice',
                    options: options
                };
            }).filter(Boolean);
        },

        // 4. Blackboard
        () => {
            const qElements = Array.from(document.querySelectorAll('.takeQuestionDiv, div[data-role="question-container"]'));
            if (qElements.length === 0) return null;

            return qElements.filter(isVisible).map((qEl, qIdx) => {
                const textEl = qEl.querySelector('.vtbegenerated, .question-text');
                const qText = cleanText(textEl ? textEl.innerText : '');
                const inputs = Array.from(qEl.querySelectorAll('input[type="radio"], input[type="checkbox"]'));
                const isMulti = qEl.querySelectorAll('input[type="checkbox"]').length > 0;

                const options = inputs.map((input, optIdx) => {
                    let label = null;
                    if (input.id) label = qEl.querySelector(`label[for="${input.id}"]`);
                    if (!label) label = input.closest('label') || input.parentElement;
                    const optText = cleanText(label ? label.innerText : '');
                    
                    input.setAttribute('data-qp-input', `${qIdx}-${optIdx}`);
                    if (label) {
                        label.setAttribute('data-qp-q', qIdx);
                        label.setAttribute('data-qp-opt', optIdx);
                    }

                    return {
                        index: optIdx,
                        text: optText,
                        checked: input.checked,
                        selector: `input[data-qp-input="${qIdx}-${optIdx}"]`
                    };
                }).filter(o => o.text.length > 0);

                return {
                    id: qEl.id || `bb-q-${qIdx}`,
                    platform: 'blackboard',
                    index: qIdx,
                    text: qText,
                    type: isMulti ? 'multiple_choice' : 'single_choice',
                    options: options
                };
            });
        },

        // 4. Universal Fallback
        () => {
            const groups = new Map();
            const allRadios = Array.from(document.querySelectorAll('input[type="radio"], input[type="checkbox"]')).filter(isVisible);
            
            for (const input of allRadios) {
                const name = input.name || input.getAttribute('name') || input.closest('fieldset, form, div')?.id || 'default_group';
                if (!groups.has(name)) groups.set(name, []);
                groups.get(name).push(input);
            }

            const questions = [];
            let qIdx = 0;

            for (const [name, inputs] of groups.entries()) {
                if (inputs.length < 2) continue; // single checkbox is usually a terms agreement

                const firstInput = inputs[0];
                const container = firstInput.closest('fieldset, .question, .form-group, tr, div') || firstInput.parentElement;
                
                // Search for question text upwards
                let header = container.querySelector('legend, h1, h2, h3, h4, h5, h6, .question-title, p');
                let qText = cleanText(header ? header.innerText : '');
                
                if (!qText && container.previousElementSibling) {
                    qText = cleanText(container.previousElementSibling.innerText);
                }
                if (!qText) qText = `Question ${qIdx + 1} (${name})`;

                const isMulti = inputs.some(i => i.type === 'checkbox');
                const options = inputs.map((input, optIdx) => {
                    let label = null;
                    if (input.id) label = document.querySelector(`label[for="${input.id}"]`);
                    if (!label) label = input.closest('label') || input.parentElement;
                    const optText = cleanText(label ? label.innerText : input.value || `Option ${optIdx + 1}`);

                    input.setAttribute('data-qp-input', `${qIdx}-${optIdx}`);
                    if (label) {
                        label.setAttribute('data-qp-q', qIdx);
                        label.setAttribute('data-qp-opt', optIdx);
                    }

                    return {
                        index: optIdx,
                        text: optText,
                        checked: input.checked,
                        selector: `input[data-qp-input="${qIdx}-${optIdx}"]`
                    };
                });

                questions.push({
                    id: `gen-q-${qIdx}`,
                    platform: 'generic',
                    index: qIdx,
                    text: qText,
                    type: isMulti ? 'multiple_choice' : 'single_choice',
                    options: options
                });
                qIdx++;
            }

            return questions.length > 0 ? questions : null;
        }
    ];

    for (const detector of platformDetectors) {
        try {
            const result = detector();
            if (result && result.length > 0) {
                return result;
            }
        } catch (e) {
            console.warn('[Quiz-Pilot] Detector error:', e);
        }
    }

    return [];
})();
"""

SELECT_OPTION_SCRIPT = r"""
((qIdx, optIdx) => {
    try {
        const input = document.querySelector(`input[data-qp-input="${qIdx}-${optIdx}"]`);
        const label = document.querySelector(`[data-qp-q="${qIdx}"][data-qp-opt="${optIdx}"]`);
        const target = label || input;

        if (!target) {
            return { success: false, error: `Option ${optIdx} for question ${qIdx} not found.` };
        }

        // Scroll smoothly to center
        target.scrollIntoView({ behavior: 'smooth', block: 'center' });

        // Fire realistic pointer/mouse event sequence
        const eventNames = ['mouseenter', 'mouseover', 'mousedown', 'pointerdown', 'mouseup', 'pointerup', 'click'];
        for (const name of eventNames) {
            target.dispatchEvent(new MouseEvent(name, { bubbles: true, cancelable: true, view: window }));
        }

        if (input) {
            input.checked = true;
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.dispatchEvent(new Event('change', { bubbles: true }));
        }

        return { success: true };
    } catch (err) {
        return { success: false, error: err.toString() };
    }
})
"""

NAVIGATE_NEXT_SCRIPT = r"""
(() => {
    try {
        // Potential next selectors across Canvas, Moodle, Blackboard, Coursera, Google Forms
        const nextSelectors = [
            'button.next-question',
            '#submit_quiz_form button.next-question',
            'button.next-button',
            'input.mod_quiz-next-nav',
            'input[name="next"]',
            'input[name="bottom_SaveAndNext"]',
            'input[name="bottom_Next"]',
            'button[aria-label="Next Question"]',
            'button[aria-label="Next"]',
            'button:not([disabled])',
            'input[type="submit"]:not([disabled])',
            'a.next',
            'a.btn-next'
        ];

        // Specific text matches for "Next", "Continue", "Next Page"
        const buttons = Array.from(document.querySelectorAll('button, input[type="submit"], input[type="button"], a.btn'));
        for (const btn of buttons) {
            const txt = (btn.innerText || btn.value || '').trim().toLowerCase();
            if (txt.includes('next') || txt === 'continue' || txt === 'next page' || txt === 'save & next') {
                btn.scrollIntoView({ behavior: 'smooth', block: 'center' });
                btn.click();
                return { success: true, clicked: txt };
            }
        }

        for (const sel of nextSelectors) {
            const el = document.querySelector(sel);
            if (el && el.offsetParent !== null) { // visible
                el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                el.click();
                return { success: true, clicked: sel };
            }
        }

        return { success: false, error: "No next button detected. Might be on final page or single-page quiz." };
    } catch (err) {
        return { success: false, error: err.toString() };
    }
})();
"""

IS_SUBMIT_SCREEN_SCRIPT = r"""
(() => {
    const buttons = Array.from(document.querySelectorAll('button, input[type="submit"], input[type="button"]'));
    for (const btn of buttons) {
        const txt = (btn.innerText || btn.value || '').trim().toLowerCase();
        if (txt.includes('submit quiz') || txt.includes('finish attempt') || txt.includes('submit exam') || txt.includes('submit assessment')) {
            return { isSubmit: true, label: txt };
        }
    }
    return { isSubmit: false };
})();
"""
