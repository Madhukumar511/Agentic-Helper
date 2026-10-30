"""
Moodle LMS Adapter for Agentic-Helper.
Handles Moodle quiz blocks (.que), answer containers, pagination, and finish attempt screens.
"""

from typing import List, Dict, Any
from .base_adapter import BaseLMSAdapter

class MoodleAdapter(BaseLMSAdapter):
    def detect(self) -> bool:
        url = getattr(self.page, "url", "")
        return "moodle" in url or "mod/quiz" in url

    def extract_questions(self) -> List[Dict[str, Any]]:
        return self.page.evaluate('''() => {
            let ques = Array.from(document.querySelectorAll('.que'));
            return ques.map((q, idx) => {
                let textEl = q.querySelector('.qtext');
                let prompt = textEl ? textEl.innerText.trim() : q.innerText.trim();
                
                let radios = Array.from(q.querySelectorAll('input[type="radio"]'));
                let checkboxes = Array.from(q.querySelectorAll('input[type="checkbox"]'));
                let txt = q.querySelector('input[type="text"], textarea');
                
                let qType = 'radio';
                if (txt) qType = 'text';
                else if (checkboxes.length > 0) qType = 'checkbox';
                
                let options = (radios.length > 0 ? radios : checkboxes).map(inp => {
                    let lbl = q.querySelector(`label[for="${inp.id}"]`) || inp.closest('label') || inp.parentElement;
                    return lbl ? lbl.innerText.trim() : '';
                }).filter(t => t.length > 0);
                
                let imgs = Array.from(q.querySelectorAll('img')).map(img => img.src);
                
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
            let ques = Array.from(document.querySelectorAll('.que'));
            if (idx >= ques.length) return false;
            let q = ques[idx];
            q.scrollIntoView({ behavior: 'smooth', block: 'center' });
            
            let radios = Array.from(q.querySelectorAll('input[type="radio"]'));
            let checkboxes = Array.from(q.querySelectorAll('input[type="checkbox"]'));
            let txt = q.querySelector('input[type="text"], textarea');
            
            if (txt) {
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
            let finishBtn = document.querySelector('.mod_quiz-next-nav, input[value*="Finish attempt"]') ||
                            Array.from(document.querySelectorAll('input[type="submit"], button')).find(b =>
                                (b.innerText || b.value || '').toLowerCase().includes('finish attempt') ||
                                (b.innerText || b.value || '').toLowerCase().includes('submit all and finish')
                            );
            if (finishBtn) {
                finishBtn.scrollIntoView();
                finishBtn.click();
                return true;
            }
            return false;
        }''')

    def extract_feedback(self) -> Dict[str, Any]:
        return self.page.evaluate('''() => {
            let feedback = {};
            let gradeEl = document.querySelector('.feedback, .grade');
            let text = gradeEl ? gradeEl.innerText : document.body.innerText;
            let match = text.match(/(\\d+(?:\\.\\d+)?)%/);
            let score = match ? parseFloat(match[1]) : 0.0;
            return { "score_pct": score, "passed": score >= 80.0, "feedback": feedback };
        }''')
