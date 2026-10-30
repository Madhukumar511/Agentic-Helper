"""
High-Speed Direct REST API Solver for Coursera.
Bypasses browser DOM rendering and React virtual DOM reconciliation by submitting
answers directly to Coursera's on-demand assessment endpoints using the authenticated CDP session.
Executes quiz attempts in ~300ms.
"""

import time
import httpx
from typing import Dict, Any, List, Optional

class CourseraDirectAPI:
    """Communicates directly with Coursera's OnDemand Assessment API."""

    def __init__(self, cauth_token: str = "", csrf_token: str = ""):
        self.cauth_token = cauth_token
        self.csrf_token = csrf_token
        self.base_url = "https://www.coursera.org/api"

    @classmethod
    async def from_page(cls, page) -> "CourseraDirectAPI":
        """Extracts authentication session tokens from active Playwright page/context."""
        context = page.context
        cookies = await context.cookies(["https://www.coursera.org"])
        cauth = ""
        csrf = ""
        for c in cookies:
            if c.get("name") == "CAUTH":
                cauth = c.get("value", "")
            elif c.get("name") == "CSRF3-Token":
                csrf = c.get("value", "")

        return cls(cauth_token=cauth, csrf_token=csrf)

    def _get_headers(self) -> Dict[str, str]:
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json; charset=UTF-8",
        }
        cookie_parts = []
        if self.cauth_token:
            cookie_parts.append(f"CAUTH={self.cauth_token}")
        if self.csrf_token:
            cookie_parts.append(f"CSRF3-Token={self.csrf_token}")
            headers["X-CSRF3-Token"] = self.csrf_token
            headers["X-Requested-With"] = "XMLHttpRequest"

        if cookie_parts:
            headers["Cookie"] = "; ".join(cookie_parts)

        return headers

    async def fetch_assessment(self, assessment_id: str) -> Dict[str, Any]:
        """Fetches assessment questions, options, and schemas directly via REST API."""
        url = f"{self.base_url}/onDemandAssessments.v1/{assessment_id}?includes=instructions,draft"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=self._get_headers())
            if resp.status_code == 200:
                return resp.json()
            return {"error": f"HTTP {resp.status_code}", "body": resp.text}

    async def submit_answers(
        self,
        assessment_id: str,
        answers: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Submits solved answers directly to Coursera's submission API.
        Sub-second roundtrip without React DOM lag.
        """
        url = f"{self.base_url}/onDemandSubmissions.v1"
        payload = {
            "assessmentId": assessment_id,
            "parts": answers,
            "submittedAt": int(time.time() * 1000)
        }
        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.post(url, headers=self._get_headers(), json=payload)
            if resp.status_code in (200, 201):
                return {"success": True, "data": resp.json()}
            return {"success": False, "status_code": resp.status_code, "body": resp.text}

    async def get_grade_feedback(self, submission_id: str) -> Dict[str, Any]:
        """Polls grade feedback directly via API."""
        url = f"{self.base_url}/onDemandSubmissions.v1/{submission_id}?includes=evaluation,feedback"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=self._get_headers())
            if resp.status_code == 200:
                return resp.json()
            return {"error": f"HTTP {resp.status_code}"}
