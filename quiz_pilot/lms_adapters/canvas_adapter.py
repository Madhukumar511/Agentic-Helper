"""
Canvas LMS Adapter for Agentic-Helper.
Handles Canvas question holders, radio options, essay/numeric boxes, and submit modals.
"""

from typing import List, Dict, Any
from .base_adapter import BaseLMSAdapter

class CanvasAdapter(BaseLMSAdapter):
    def detect(self) -> bool:
        url = getattr(self.page, "url", "")
        return "instructure.com" in url or "canvas" in url

    def extract_questions(self) -> List[Dict[str, Any]]:
        return self.page.evaluate('''() => {
            let qHolders = Array.from(document.querySelectorAll('.quiz_question, .question_holder'));
            return qHolders.map((qh, idx) => {
                let promptElem = qh.querySelector('.question_text');
                let prompt = promptElem ? promptElem.innerText.trim() : qh.innerText.trim();
                
                let radios = Array.from(qh.querySelectorAll('input[type="radio"]'));
                let checkboxes = Array.from(qh.querySelectorAll('input[type="checkbox"]'));
                let num = qh.querySelector('input.numerical_question_input, input[type="number"]');
                let txt = qh.querySelector('input.text_question_input, input[type="text"]');
                
                let qType = 'radio';
                if (num) qType = 'number';
                else if (txt) qType = 'text';
                else if (checkboxes.length > 0) qType = 'checkbox';
                
                let options = (radios.length > 0 ? radios : checkboxes).map(inp => {
                    let lbl = qh.querySelector(`label[for="${inp.id}"]`) || inp.closest('label') || inp.parentElement;
                    return lbl ? lbl.innerText.trim() : '';
                }).filter(t => t.length > 0);
                
                let imgs = Array.from(qh.querySelectorAll('img')).map(img => img.src);
                
                return {
                    index: idx,
                    qNum: idx + 1,
                    type: qType,
                    prompt: prompt,
                    options: options,
                    images: imgs
                };
            });
        }''')

    def fill_answer(self, question_index: int, value: Any) -> bool:
        return self.page.evaluate('''([idx, val]) => {
            let qHolders = Array.from(document.querySelectorAll('.quiz_question, .question_holder'));
            if (idx >= qHolders.length) return false;
            let qh = qHolders[idx];
            qh.scrollIntoView({ behavior: 'smooth', block: 'center' });
            
            let num = qh.querySelector('input.numerical_question_input, input[type="number"]');
            let txt = qh.querySelector('input.text_question_input, input[type="text"]');
            let radios = Array.from(qh.querySelectorAll('input[type="radio"]'));
            let checkboxes = Array.from(qh.querySelectorAll('input[type="checkbox"]'));
            
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
                if (targetIdx >= 0 && targetIdx < radios.length) {
                    radios[targetIdx].click();
                    return true;
                }
            } else if (checkboxes.length > 0) {
                let indices = Array.isArray(val) ? val : [val];
                for (let i of indices) {
                    if (typeof i === 'number' && i < checkboxes.length) {
                        if (!checkboxes[i].checked) checkboxes[i].click();
                    }
                }
                return true;
            }
            return false;
        }''', [question_index, value])

    def submit_assessment(self) -> bool:
        return self.page.evaluate('''() => {
            let submitBtn = document.querySelector('#submit_quiz_button') ||
                            Array.from(document.querySelectorAll('button, input[type="submit"]')).find(b =>
                                (b.innerText || b.value || '').toLowerCase().includes('submit quiz')
                            );
            if (submitBtn) {
                submitBtn.scrollIntoView();
                submitBtn.click();
                return true;
            }
            return false;
        }''')

    def extract_feedback(self) -> Dict[str, Any]:
        return self.page.evaluate('''() => {
            let scoreEl = document.querySelector('.score_value, .quiz_score');
            let score = scoreEl ? parseFloat(scoreEl.innerText) : 0.0;
            return { "score_pct": score, "passed": score >= 80.0, "feedback": {} };
        }''')
