"""
AI Solver Module for Quiz-Pilot.
Analyzes quiz questions and generates accurate answers via Gemini, OpenAI/Ollama,
or local Agent Bridge pairing.
"""

import os
import re
import json
import tempfile
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger("quiz_pilot.ai_solver")


class AISolver:
    def __init__(self, api_key: Optional[str] = None, model_name: str = "gemini-2.5-flash"):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self.model_name = model_name
        self.client = None

        if self.api_key:
            try:
                from google import genai
                self.client = genai.Client(api_key=self.api_key)
                logger.info(f"Initialized Google GenAI client with model: {self.model_name}")
            except Exception as e:
                logger.warning(f"Failed to initialize Google GenAI client: {e}")

    def solve_question(self, question: Dict[str, Any]) -> Dict[str, Any]:
        """
        Solves a single question dict:
        {
            "text": "What is...",
            "type": "single_choice" | "multiple_choice",
            "options": [{"index": 0, "text": "A"}, ...]
        }
        Returns:
        {
            "selected_indices": [1],
            "confidence": 0.95,
            "explanation": "..."
        }
        """
        q_text = question.get("text", "")
        options = question.get("options", [])
        q_type = question.get("type", "single_choice")

        if not options:
            return {"selected_indices": [], "confidence": 0.0, "explanation": "No options provided."}

        formatted_opts = []
        for i, opt in enumerate(options):
            if isinstance(opt, dict):
                idx = opt.get("index", i)
                txt = opt.get("text", "")
            else:
                idx = i
                txt = str(opt)
            formatted_opts.append(f"[{idx}] {txt}")
        formatted_options = "\n".join(formatted_opts)

        prompt = f"""You are an expert academic tutor answering quiz questions with maximum accuracy.
Analyze the following question and options carefully:

Question:
{q_text}

Options:
{formatted_options}

Question Type: {q_type} (select only ONE option index if single_choice, or ALL that apply if multiple_choice).

Return ONLY valid JSON matching this schema:
{{
  "selected_indices": [0],
  "confidence": 0.98,
  "explanation": "Brief explanation of why this answer is correct."
}}
"""

        # 1. Try Gemini Client if configured
        if self.client:
            try:
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt
                )
                text = response.text
                return self._parse_json_response(text, len(options))
            except Exception as e:
                logger.error(f"Gemini API error: {e}. Falling back to bridge/heuristics.")

        # 2. Try OpenAI / Ollama compatible endpoint if OPENAI_API_KEY or OPENAI_BASE_URL exists
        openai_key = os.environ.get("OPENAI_API_KEY")
        openai_base = os.environ.get("OPENAI_BASE_URL", "http://localhost:11434/v1")
        if openai_key or os.environ.get("USE_OLLAMA"):
            try:
                import httpx
                headers = {"Authorization": f"Bearer {openai_key or 'ollama'}"}
                payload = {
                    "model": os.environ.get("OPENAI_MODEL", "llama3"),
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1
                }
                res = httpx.post(f"{openai_base}/chat/completions", headers=headers, json=payload, timeout=20.0)
                if res.status_code == 200:
                    data = res.json()
                    content = data["choices"][0]["message"]["content"]
                    return self._parse_json_response(content, len(options))
            except Exception as e:
                logger.error(f"OpenAI/Ollama error: {e}")

        # 3. Agent Bridge / Shared State Mode
        bridge_file = os.path.join(tempfile.gettempdir(), "quiz_pilot_bridge.json")
        logger.info(f"Writing question to bridge file for agent review: {bridge_file}")
        with open(bridge_file, "w") as f:
            json.dump({
                "status": "awaiting_answer",
                "question": question,
                "prompt": prompt
            }, f, indent=2)

        # Default fallback: pick first option if completely unattended without key
        return {
            "selected_indices": [0],
            "confidence": 0.5,
            "explanation": "Default selection (Configure GEMINI_API_KEY for 100% AI accuracy)."
        }

    def _parse_json_response(self, text: str, total_options: int) -> Dict[str, Any]:
        """Safely parses LLM JSON response even with markdown wrappers."""
        clean = text.strip()
        # Remove markdown code blocks if present
        clean = re.sub(r"^```(?:json)?\s*", "", clean, flags=re.MULTILINE)
        clean = re.sub(r"\s*```$", "", clean, flags=re.MULTILINE)
        
        try:
            data = json.loads(clean)
            indices = data.get("selected_indices", [])
            # Validate indices are integers within bounds
            valid_indices = [int(i) for i in indices if isinstance(i, (int, str)) and str(i).isdigit() and int(i) < total_options]
            if not valid_indices and total_options > 0:
                valid_indices = [0]
            
            return {
                "selected_indices": valid_indices,
                "confidence": float(data.get("confidence", 0.9)),
                "explanation": str(data.get("explanation", ""))
            }
        except Exception as e:
            logger.warning(f"JSON parsing error: {e} from text: {text}")
            # Fallback regex search for numbers
            matches = re.findall(r"\[([0-9,\s]+)\]", text)
            if matches:
                nums = [int(n.strip()) for n in matches[0].split(",") if n.strip().isdigit() and int(n.strip()) < total_options]
                if nums:
                    return {"selected_indices": nums, "confidence": 0.8, "explanation": "Extracted via regex."}

            return {"selected_indices": [0], "confidence": 0.5, "explanation": "Fallback parse."}
