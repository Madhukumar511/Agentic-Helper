"""
Blackboard Learn LMS Adapter for Agentic-Helper.
Handles Blackboard question blocks (.takeQuestionDiv), option selections, and assessment submission.
"""

from typing import List, Dict, Any
from .base_adapter import BaseLMSAdapter

class BlackboardAdapter(BaseLMSAdapter):
    def detect(self) -> bool:
        url = getattr(self.page, "url", "")
        return "blackboard" in url or "bbcswebdav" in url

    def extract_questions(self) -> List[Dict[str, Any]]:
        return self.page.evaluate('''() => {
            let divs = Array.from(document.querySelectorAll('.takeQuestionDiv, .contentBox, div[id^="question_"]'));
            return divs.map((d, idx) => {
                let promptEl = d.querySelector('.vtbegenerated, .questionText');
                let prompt = promptEl ? promptEl.innerText.trim() : d.innerText.trim();
                
                let radios = Array.from(d.querySelectorAll('input[type="radio"]'));
                let checkboxes = Array.from(d.querySelectorAll('input[type="checkbox"]'));
                let txt = d.querySelector('input[type="text"], textarea');
                
                let qType = 'radio';
                if (txt) qType = 'text';
                else if (checkboxes.length > 0) qType = 'checkbox';
                
                let options = (radios.length > 0 ? radios : checkboxes).map(inp => {
                    let lbl = d.querySelector(`label[for="${inp.id}"]`) || inp.closest('label') || inp.parentElement;
                    return lbl ? lbl.innerText.trim() : '';
                }).filter(t => t.length > 0);
                
                let imgs = Array.from(d.querySelectorAll('img')).map(img => img.src);
                
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
            let divs = Array.from(document.querySelectorAll('.takeQuestionDiv, .contentBox, div[id^="question_"]'));
            if (idx >= divs.length) return false;
            let d = divs[idx];
            d.scrollIntoView({ behavior: 'smooth', block: 'center' });
            
            let radios = Array.from(d.querySelectorAll('input[type="radio"]'));
            let checkboxes = Array.from(d.querySelectorAll('input[type="checkbox"]'));
            let txt = d.querySelector('input[type="text"], textarea');
            
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
            let submitBtn = document.querySelector('#bottom_submitButtonRow input[type="submit"], input[value*="Save and Submit"]') ||
                            Array.from(document.querySelectorAll('input[type="submit"], button')).find(b =>
                                (b.innerText || b.value || '').toLowerCase().includes('save and submit')
                            );
            if (submitBtn) {
                submitBtn.scrollIntoView();
                submitBtn.click();
                return true;
            }
            return false;
        }''')

    def extract_feedback(self) -> Dict[str, Any]:
        return {"score_pct": 0.0, "passed": True, "feedback": {}}
