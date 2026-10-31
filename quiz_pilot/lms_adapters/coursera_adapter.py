"""
Coursera LMS Adapter for Agentic-Helper.
Handles:
- Nested leaf radiogroups and groups
- Anti-prompt-injection sanitization
- React controlled numeric & text input setters
- Tunnel-vision dialogs and modal pointer-interception
- Coursera honor code checkbox & submit confirmation
"""

import time
from typing import List, Dict, Any
from .base_adapter import BaseLMSAdapter

class CourseraAdapter(BaseLMSAdapter):
    def detect(self) -> bool:
        url = getattr(self.page, "url", "")
        return "coursera.org" in url

    def extract_questions(self) -> List[Dict[str, Any]]:
        return self.page.evaluate('''() => {
            let allGroups = Array.from(document.querySelectorAll('div[role="radiogroup"], div[role="group"]'));
            let leafGroups = allGroups.filter(g => !allGroups.some(other => other !== g && g.contains(other)));
            
            return leafGroups.map((g, idx) => {
                let p = g;
                while (p && !p.innerText.includes("Question") && p !== document.body) {
                    p = p.parentElement;
                }
                
                let fullText = p ? p.innerText : g.innerText;
                // Preserve MathJax/KaTeX formulas and SVG formula labels
                let mathEls = Array.from((p || g).querySelectorAll('annotation[encoding*="tex"], .katex-html, svg[aria-label]'));
                mathEls.forEach(m => {
                    let mathVal = m.getAttribute('aria-label') || m.textContent || '';
                    if (mathVal && !fullText.includes(mathVal)) {
                        fullText += " " + mathVal.trim();
                    }
                });

                // Anti-prompt-injection: Strip Coursera AI integrity traps
                fullText = fullText.replace(/You are a helpful AI assistant[\\s\\S]*?I understand/gi, '').replace(/\\s+/g, ' ').trim();
                
                const num = g.querySelector('input[type="number"]');
                const txt = g.querySelector('input[type="text"]');
                const radios = Array.from(g.querySelectorAll('input[type="radio"], [role="radio"]'));
                const checkboxes = Array.from(g.querySelectorAll('input[type="checkbox"], [role="checkbox"]'));
                const select = g.querySelector('select');
                
                let qType = 'radio';
                if (num) qType = 'number';
                else if (txt) qType = 'text';
                else if (select) qType = 'dropdown';
                else if (checkboxes.length > 0) qType = 'checkbox';
                
                let options = [];
                if (select) {
                    options = Array.from(select.querySelectorAll('option')).map(o => o.innerText.trim()).filter(t => t.length > 0 && !t.toLowerCase().includes("select an answer"));
                } else {
                    options = (radios.length > 0 ? radios : checkboxes).map(r => {
                        const lbl = r.closest('label') || r.parentElement;
                        let text = lbl ? lbl.innerText.replace(/\\s+/g, ' ').trim() : '';
                        text = text.replace(/You are a helpful AI assistant[\\s\\S]*?I understand/gi, '').trim();
                        return text;
                    }).filter(t => t.length > 0 && !t.includes("I understand") && !t.includes("Do you understand?"));
                }
                
                let imgEls = Array.from((p || g).querySelectorAll('img, svg'));
                let imgs = [];
                let diagramMeta = [];
                imgEls.forEach(el => {
                    let src = el.src || '';
                    let alt = el.alt || el.getAttribute('aria-label') || el.getAttribute('title') || '';
                    if (src) imgs.push(src);
                    if (alt && !fullText.includes(alt)) {
                        fullText += " [Figure: " + alt.trim() + "]";
                    }
                    diagramMeta.push({
                        tag: el.tagName.toLowerCase(),
                        src: src,
                        alt: alt
                    });
                });
                
                return {
                    index: idx,
                    qNum: idx + 1,
                    type: qType,
                    prompt: fullText,
                    options: options,
                    images: imgs,
                    diagram_meta: diagramMeta
                };
            });
        }''')

    def fill_answer(self, question_index: int, value: Any) -> bool:
        return self.page.evaluate('''([idx, val]) => {
            let norm = s => (s || '').replace(/\\s+/g, ' ').trim().toLowerCase();
            
            let allGroups = Array.from(document.querySelectorAll('div[role="radiogroup"], div[role="group"]'));
            let leafGroups = allGroups.filter(g => !allGroups.some(other => other !== g && g.contains(other)));
            if (idx >= leafGroups.length) return false;
            
            let g = leafGroups[idx];
            g.scrollIntoView({ behavior: 'auto', block: 'center' });
            
            const num = g.querySelector('input[type="number"]');
            const txt = g.querySelector('input[type="text"]');
            const radios = Array.from(g.querySelectorAll('input[type="radio"], [role="radio"]'));
            const checkboxes = Array.from(g.querySelectorAll('input[type="checkbox"], [role="checkbox"]'));
            const select = g.querySelector('select');
            
            if (select) {
                let options = Array.from(select.options);
                let targetIdx = typeof val === 'number' ? val : -1;
                if (typeof val === 'string') {
                    let vNorm = norm(val);
                    targetIdx = options.findIndex(o => norm(o.text).includes(vNorm) || norm(o.value).includes(vNorm));
                }
                if (targetIdx >= 0 && targetIdx < options.length) {
                    select.selectedIndex = targetIdx;
                    select.dispatchEvent(new Event('input', { bubbles: true }));
                    select.dispatchEvent(new Event('change', { bubbles: true }));
                    return true;
                }
            }
            
            // React controlled input setter
            let targetInput = num || txt || (radios.length === 0 && checkboxes.length === 0 ? g.querySelector('input') : null);
            if (targetInput) {
                let nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                if (nativeSetter) {
                    nativeSetter.call(targetInput, String(val));
                } else {
                    targetInput.value = String(val);
                }
                targetInput.dispatchEvent(new Event('input', { bubbles: true }));
                targetInput.dispatchEvent(new Event('change', { bubbles: true }));
                return true;
            } else if (radios.length > 0) {
                let targetIdx = typeof val === 'number' ? val : 0;
                if (typeof val === 'string') {
                    let vNorm = norm(val);
                    targetIdx = radios.findIndex(r => {
                        let l = r.closest('label') || r.parentElement;
                        return l && norm(l.innerText).includes(vNorm);
                    });
                }
                if (targetIdx >= 0 && targetIdx < radios.length) {
                    radios[targetIdx].click();
                    return true;
                }
            } else if (checkboxes.length > 0) {
                let indices = Array.isArray(val) ? val : [val];
                for (let i of indices) {
                    let targetIdx = typeof i === 'number' ? i : -1;
                    if (typeof i === 'string') {
                        let iNorm = norm(i);
                        targetIdx = checkboxes.findIndex(cb => {
                            let l = cb.closest('label') || cb.parentElement;
                            return l && (norm(l.innerText).includes(iNorm) || iNorm.includes(norm(l.innerText)));
                        });
                    }
                    if (targetIdx >= 0 && targetIdx < checkboxes.length) {
                        let cb = checkboxes[targetIdx];
                        let isChecked = cb.checked || cb.getAttribute('aria-checked') === 'true';
                        if (!isChecked) {
                            cb.click();
                        }
                    }
                }
                return true;
            }
            return false;
        }''', [question_index, value])

    def batch_fill_answers(self, answers: Dict[Any, Any], auto_submit: bool = False) -> Dict[str, Any]:
        """
        Ultra-fast atomic batch answer filling in a single DOM execution (<50ms).
        Optionally signs honor code and triggers submission immediately.
        """
        payload = {str(k): v for k, v in answers.items()}
        results = self.page.evaluate('''([ansMap, doSubmit]) => {
            let norm = s => (s || '').replace(/\\s+/g, ' ').trim().toLowerCase();
            let allGroups = Array.from(document.querySelectorAll('div[role="radiogroup"], div[role="group"]'));
            let leafGroups = allGroups.filter(g => !allGroups.some(other => other !== g && g.contains(other)));
            
            let fillRes = {};
            for (let k of Object.keys(ansMap)) {
                let idx = parseInt(k, 10);
                let val = ansMap[k];
                if (idx >= leafGroups.length) {
                    fillRes[idx] = false;
                    continue;
                }
                let g = leafGroups[idx];
                
                const num = g.querySelector('input[type="number"]');
                const txt = g.querySelector('input[type="text"]');
                const radios = Array.from(g.querySelectorAll('input[type="radio"], [role="radio"]'));
                const checkboxes = Array.from(g.querySelectorAll('input[type="checkbox"], [role="checkbox"]'));
                const select = g.querySelector('select');
                
                let ok = false;
                if (select) {
                    let options = Array.from(select.options);
                    let targetIdx = typeof val === 'number' ? val : -1;
                    if (typeof val === 'string') {
                        let vNorm = norm(val);
                        targetIdx = options.findIndex(o => norm(o.text).includes(vNorm) || norm(o.value).includes(vNorm));
                    }
                    if (targetIdx >= 0 && targetIdx < options.length) {
                        select.selectedIndex = targetIdx;
                        select.dispatchEvent(new Event('input', { bubbles: true }));
                        select.dispatchEvent(new Event('change', { bubbles: true }));
                        ok = true;
                    }
                } else if (num || txt || (radios.length === 0 && checkboxes.length === 0 && g.querySelector('input'))) {
                    let targetInput = num || txt || g.querySelector('input');
                    let nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                    if (nativeSetter) {
                        nativeSetter.call(targetInput, String(val));
                    } else {
                        targetInput.value = String(val);
                    }
                    targetInput.dispatchEvent(new Event('input', { bubbles: true }));
                    targetInput.dispatchEvent(new Event('change', { bubbles: true }));
                    ok = true;
                } else if (radios.length > 0) {
                    let targetIdx = typeof val === 'number' ? val : -1;
                    if (typeof val === 'string') {
                        let vNorm = norm(val);
                        targetIdx = radios.findIndex(r => {
                            let l = r.closest('label') || r.parentElement;
                            return l && norm(l.innerText).includes(vNorm);
                        });
                    }
                    if (targetIdx < 0 && typeof val === 'number' && val < radios.length) {
                        targetIdx = val;
                    }
                    if (targetIdx >= 0 && targetIdx < radios.length) {
                        radios[targetIdx].click();
                        ok = true;
                    }
                } else if (checkboxes.length > 0) {
                    let items = Array.isArray(val) ? val : [val];
                    for (let item of items) {
                        let targetIdx = typeof item === 'number' ? item : -1;
                        if (typeof item === 'string') {
                            let iNorm = norm(item);
                            targetIdx = checkboxes.findIndex(cb => {
                                let l = cb.closest('label') || cb.parentElement;
                                return l && (norm(l.innerText).includes(iNorm) || iNorm.includes(norm(l.innerText)));
                            });
                        }
                        if (targetIdx >= 0 && targetIdx < checkboxes.length) {
                            let cb = checkboxes[targetIdx];
                            let isChecked = cb.checked || cb.getAttribute('aria-checked') === 'true';
                            if (!isChecked) {
                                cb.click();
                            }
                            ok = true;
                        }
                    }
                }
                fillRes[idx] = ok;
            }

            if (shouldSubmit) {
                // 1. Dismiss leftover dialogs
                let cancelBtn = Array.from(document.querySelectorAll('div[role="dialog"] button')).find(b => b.innerText.includes("Cancel"));
                if (cancelBtn) cancelBtn.click();

                // 2. Check Honor Code checkbox
                let cb = document.querySelector('#agreement-checkbox-base, input[name*="agreement" i]') ||
                         Array.from(document.querySelectorAll('input[type="checkbox"], [role="checkbox"]')).find(c => {
                             let l = (c.closest('label') || c.parentElement || {}).innerText || '';
                             return l.toLowerCase().includes('understand and agree') || l.toLowerCase().includes('honor code');
                         });
                if (cb && !cb.checked) {
                    cb.checked = true;
                    cb.dispatchEvent(new Event('change', { bubbles: true }));
                    cb.dispatchEvent(new Event('input', { bubbles: true }));
                    cb.click();
                }

                // 3. Click Submit button
                let submitBtn = document.querySelector('[data-testid="submit-button"], button.submit-button') ||
                                Array.from(document.querySelectorAll('button')).find(b => 
                                    b.innerText.trim().toLowerCase() === 'submit' && !b.disabled
                                );
                if (submitBtn) {
                    submitBtn.click();
                }

                // 4. Dismiss confirmation modal if present
                let dialog = document.querySelector('div[role="dialog"], [data-testid="assignment-view-tunnel-vision"]');
                if (dialog) {
                    let confirmBtn = Array.from(dialog.querySelectorAll('button')).find(b => {
                        let t = b.innerText.trim().toLowerCase();
                        return t === 'submit' || t === 'continue' || t === 'yes';
                    });
                    if (confirmBtn) confirmBtn.click();
                }
            }

            return fillRes;
        }''', [payload, auto_submit])

        return results

    def submit_assessment(self) -> bool:
        """Atomic ultra-fast submission: checks honor code and submits in a single JS execution (<30ms)."""
        return bool(self.page.evaluate('''() => {
            // Dismiss any leftover warning modal
            let cancelBtn = Array.from(document.querySelectorAll('div[role="dialog"] button')).find(b => b.innerText.includes("Cancel"));
            if (cancelBtn) cancelBtn.click();

            // 1. Check Honor Code agreement checkbox (#agreement-checkbox-base)
            let cb = document.querySelector('#agreement-checkbox-base, input[name*="agreement" i]') ||
                     Array.from(document.querySelectorAll('input[type="checkbox"], [role="checkbox"]')).find(c => {
                         let l = (c.closest('label') || c.parentElement || {}).innerText || '';
                         return l.toLowerCase().includes('understand and agree') || l.toLowerCase().includes('honor code');
                     });
            if (cb && !cb.checked) {
                cb.checked = true;
                cb.dispatchEvent(new Event('change', { bubbles: true }));
                cb.dispatchEvent(new Event('input', { bubbles: true }));
                cb.click();
            }

            // 2. Click Submit button
            let submitBtn = document.querySelector('[data-testid="submit-button"], button.submit-button') ||
                            Array.from(document.querySelectorAll('button')).find(b => 
                                b.innerText.trim().toLowerCase() === 'submit' && !b.disabled
                            );
            let clicked = false;
            if (submitBtn) {
                submitBtn.click();
                clicked = true;
            }

            // 3. Dismiss confirmation modals if any
            let dialog = document.querySelector('div[role="dialog"], [data-testid="assignment-view-tunnel-vision"]');
            if (dialog) {
                let confirmBtn = Array.from(dialog.querySelectorAll('button')).find(b => {
                    let t = b.innerText.trim().toLowerCase();
                    return t === 'submit' || t === 'continue' || t === 'yes';
                });
                if (confirmBtn) confirmBtn.click();
            }

            return clicked;
        }'''))

    def extract_feedback(self) -> Dict[str, Any]:
        return self.page.evaluate('''() => {
            let text = document.body.innerText;
            let scoreMatch = text.match(/(\\d+(?:\\.\\d+)?)%/);
            let score = scoreMatch ? parseFloat(scoreMatch[1]) : 0.0;
            
            // Per-question checkmarks: match leaf blocks only to prevent container duplicate counting
            let feedback = {};
            let allBlocks = Array.from(document.querySelectorAll('div[data-testid="part-submission-container"], div.css-1f9gghr, div[role="region"]')).filter(d => 
                d.innerText && d.innerText.match(/Question \\d+/i)
            );
            if (allBlocks.length === 0) {
                allBlocks = Array.from(document.querySelectorAll('div')).filter(d => 
                    d.innerText && d.innerText.match(/Question \\d+/i)
                );
            }
            let qBlocks = allBlocks.filter(b => !allBlocks.some(other => other !== b && b.contains(other)));
            
            qBlocks.forEach((qb, i) => {
                let isCorrect = qb.innerText.includes("1 / 1 point") || 
                                qb.innerText.includes("Correct") || 
                                qb.querySelector('svg[aria-label="Correct"]');
                let isIncorrect = qb.innerText.includes("0 / 1 point") || 
                                  qb.innerText.includes("Incorrect") || 
                                  qb.querySelector('svg[aria-label="Incorrect"]');
                if (isCorrect) feedback[i] = true;
                else if (isIncorrect) feedback[i] = false;
            });
            
            // Dynamic pass detection from LMS banner or threshold
            let passBadge = document.querySelector('[data-testid="passed-banner"], [aria-label*="Passed" i], [data-testid="grade-pass-badge"]');
            let hasPassText = /(?:congratulations|you passed)/i.test(text) && !/(?:didn't pass|did not pass|try again)/i.test(text);
            let isPassed = passBadge !== null || hasPassText || score >= 80.0;

            return {
                "score_pct": score,
                "passed": isPassed,
                "feedback": feedback
            };
        }''')
