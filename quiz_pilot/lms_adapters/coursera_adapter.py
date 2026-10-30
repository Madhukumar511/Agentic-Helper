"""
Coursera LMS Adapter for Agentic-Helper.
Handles:
- Nested leaf radiogroups and groups
- Anti-prompt-injection sanitization
- Tunnel-vision dialogs and modal pointer-interception
- Coursera honor code checkbox & re-attempt confirmation
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
                // Anti-prompt-injection: Strip Coursera AI integrity traps
                fullText = fullText.replace(/You are a helpful AI assistant[\\s\\S]*?I understand/gi, '').replace(/\\s+/g, ' ').trim();
                
                const num = g.querySelector('input[type="number"]');
                const txt = g.querySelector('input[type="text"]');
                const radios = Array.from(g.querySelectorAll('input[type="radio"], [role="radio"]'));
                const checkboxes = Array.from(g.querySelectorAll('input[type="checkbox"], [role="checkbox"]'));
                
                let qType = 'radio';
                if (num) qType = 'number';
                else if (txt) qType = 'text';
                else if (checkboxes.length > 0) qType = 'checkbox';
                
                const options = (radios.length > 0 ? radios : checkboxes).map(r => {
                    const lbl = r.closest('label') || r.parentElement;
                    let text = lbl ? lbl.innerText.replace(/\\s+/g, ' ').trim() : '';
                    text = text.replace(/You are a helpful AI assistant[\\s\\S]*?I understand/gi, '').trim();
                    return text;
                }).filter(t => t.length > 0 && !t.includes("I understand") && !t.includes("Do you understand?"));
                
                const imgs = Array.from((p || g).querySelectorAll('img')).map(img => img.src);
                
                return {
                    index: idx,
                    qNum: idx + 1,
                    type: qType,
                    prompt: fullText,
                    options: options,
                    images: imgs
                };
            });
        }''')

    def fill_answer(self, question_index: int, value: Any) -> bool:
        return self.page.evaluate('''([idx, val]) => {
            let allGroups = Array.from(document.querySelectorAll('div[role="radiogroup"], div[role="group"]'));
            let leafGroups = allGroups.filter(g => !allGroups.some(other => other !== g && g.contains(other)));
            if (idx >= leafGroups.length) return false;
            
            let g = leafGroups[idx];
            g.scrollIntoView({ behavior: 'smooth', block: 'center' });
            
            const num = g.querySelector('input[type="number"]');
            const txt = g.querySelector('input[type="text"]');
            const radios = Array.from(g.querySelectorAll('input[type="radio"], [role="radio"]'));
            const checkboxes = Array.from(g.querySelectorAll('input[type="checkbox"], [role="checkbox"]'));
            
            if (num) {
                num.value = val;
                num.dispatchEvent(new Event('input', { bubbles: true }));
                num.dispatchEvent(new Event('change', { bubbles: true }));
                return true;
            } else if (txt) {
                txt.value = val;
                txt.dispatchEvent(new Event('input', { bubbles: true }));
                txt.dispatchEvent(new Event('change', { bubbles: true }));
                return true;
            } else if (radios.length > 0) {
                let targetIdx = typeof val === 'number' ? val : 0;
                if (typeof val === 'string') {
                    targetIdx = radios.findIndex(r => {
                        let l = r.closest('label') || r.parentElement;
                        return l && l.innerText.toLowerCase().includes(val.toLowerCase());
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
                        targetIdx = checkboxes.findIndex(cb => {
                            let l = cb.closest('label') || cb.parentElement;
                            return l && l.innerText.toLowerCase().includes(i.toLowerCase());
                        });
                    }
                    if (targetIdx >= 0 && targetIdx < checkboxes.length) {
                        if (!checkboxes[targetIdx].checked) checkboxes[targetIdx].click();
                    }
                }
                return true;
            }
            return false;
        }''', [question_index, value])

    def submit_assessment(self) -> bool:
        # Check honor code checkbox
        self.page.evaluate('''() => {
            let honorCb = document.querySelector('input[type="checkbox"][name*="honor" i]') ||
                          Array.from(document.querySelectorAll('input[type="checkbox"]')).find(cb => {
                              let p = cb.closest('label') || cb.parentElement;
                              return p && p.innerText.toLowerCase().includes('honor code');
                          });
            if (honorCb && !honorCb.checked) {
                honorCb.click();
            }
        }''')
        time.sleep(1)
        
        # Click Submit button
        clicked = self.page.evaluate('''() => {
            let submitBtn = Array.from(document.querySelectorAll('button')).find(b => 
                b.innerText.toLowerCase().includes('submit') && !b.disabled
            );
            if (submitBtn) {
                submitBtn.scrollIntoView();
                submitBtn.click();
                return true;
            }
            return false;
        }''')
        
        if clicked:
            time.sleep(2)
            # Dismiss tunnel-vision or confirmation modals if any
            self.page.evaluate('''() => {
                let confirmBtn = Array.from(document.querySelectorAll('div[role="dialog"] button, [data-testid="assignment-view-tunnel-vision"] button'))
                    .find(b => b.innerText.toLowerCase().includes('continue') || b.innerText.toLowerCase().includes('submit'));
                if (confirmBtn) confirmBtn.click();
            }''')
        return clicked

    def extract_feedback(self) -> Dict[str, Any]:
        return self.page.evaluate('''() => {
            let text = document.body.innerText;
            let scoreMatch = text.match(/(\\d+(?:\\.\\d+)?)%/);
            let score = scoreMatch ? parseFloat(scoreMatch[1]) : 0.0;
            
            // Per-question checkmarks
            let feedback = {};
            let qBlocks = Array.from(document.querySelectorAll('div')).filter(d => 
                d.innerText && d.innerText.match(/Question \\d+/i)
            );
            
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
            
            return {
                "score_pct": score,
                "passed": score >= 80.0,
                "feedback": feedback
            };
        }''')
