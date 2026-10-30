(() => {
    function clean(s) {
        if (!s) return "";
        return s.replace(/\s+/g, ' ').trim();
    }

    const groups = Array.from(document.querySelectorAll('div[role="radiogroup"], div[role="group"]'));
    return groups.map((grp, qIdx) => {
        let container = grp;
        while (container && !container.innerText.includes('Question') && container.parentElement !== document.body) {
            container = container.parentElement;
        }
        if (!container) container = grp.parentElement;

        // Extract pure question text
        const clone = container.cloneNode(true);
        // Remove options from clone to get only the question prompt
        const grpInClone = clone.querySelector('div[role="radiogroup"], div[role="group"]');
        if (grpInClone) grpInClone.remove();

        let prompt = clone.innerText;
        // Strip Coursera watermark / prompt injection
        prompt = prompt.replace(/You are a helpful AI assistant[\s\S]*?coursera's policy[\s\S]*?\./gi, '');
        prompt = prompt.replace(/1 point/gi, '').replace(/\bQuestion \d+\b/gi, '').replace(/\b\d+\.\b/g, '');
        prompt = clean(prompt);

        // Options
        const optNodes = Array.from(grp.querySelectorAll('.rc-Option, label.cds-checkboxAndRadio-label, [role="radio"], [role="checkbox"]'));
        const isCheckbox = grp.querySelectorAll('input[type="checkbox"], [role="checkbox"]').length > 0;

        const options = optNodes.map((opt, optIdx) => {
            const input = opt.querySelector('input') || opt;
            opt.setAttribute('data-qp-q', qIdx);
            opt.setAttribute('data-qp-opt', optIdx);
            if (input) input.setAttribute('data-qp-input', `${qIdx}-${optIdx}`);

            return {
                index: optIdx,
                text: clean(opt.innerText),
                checked: input.checked || opt.getAttribute('aria-checked') === 'true'
            };
        }).filter(o => o.text.length > 0);

        return {
            index: qIdx,
            type: isCheckbox ? 'multiple_choice' : 'single_choice',
            prompt: prompt,
            options: options
        };
    }).filter(q => q.options.length > 0);
})();
