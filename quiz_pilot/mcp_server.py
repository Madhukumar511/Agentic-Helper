"""
Model Context Protocol (MCP) Server for Agentic-Helper.

Exposes native tools for Claude Desktop, Cursor, Antigravity, and AI Agents:
- extract_questions
- fill_answer
- solve_batch
- submit_assessment
- get_feedback
- solve_multicast
- solve_diagram
"""

import sys
import json
import asyncio
from typing import Dict, Any, List, Optional
from playwright.async_api import async_playwright

from quiz_pilot.lms_adapters import get_lms_adapter
from quiz_pilot.attempt_protector import FastAttemptManager
from quiz_pilot.graph_solvers import MulticastSimulator, LamportVectorClockSolver
from quiz_pilot.diagram_parser import LocalDiagramParser
from quiz_pilot.browser_launcher import launch_browser, is_browser_running

# Initialize helper engines
attempt_mgr = FastAttemptManager()
diagram_parser = LocalDiagramParser()

TOOLS = [
    {
        "name": "launch_browser",
        "description": "Launches Chrome, Edge, or Brave on remote debugging port 9222 and opens the course/assessment URL automatically.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Assessment or Course URL (default: https://www.coursera.org)",
                    "default": "https://www.coursera.org"
                },
                "port": {
                    "type": "integer",
                    "description": "CDP debugging port (default: 9222)",
                    "default": 9222
                }
            }
        }
    },
    {
        "name": "extract_questions",
        "description": "Extracts structured questions, options, types, and images from the active LMS/assessment browser page.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cdp_url": {
                    "type": "string",
                    "description": "Chrome DevTools Protocol URL (default: http://127.0.0.1:9222)",
                    "default": "http://127.0.0.1:9222"
                },
                "tab_keyword": {
                    "type": "string",
                    "description": "Optional keyword in URL or Title to pick a specific tab (e.g. 'coursera', 'quiz')"
                }
            }
        }
    },
    {
        "name": "fill_answer",
        "description": "Selects radio/checkbox option or fills numeric/text value for a specific question.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "question_index": {"type": "integer", "description": "0-based question index"},
                "value": {"description": "Option index (int), option text (str), array of indices, or numeric value"}
            },
            "required": ["question_index", "value"]
        }
    },
    {
        "name": "solve_batch",
        "description": "Fills multiple question answers in one fast batch execution.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "answers": {
                    "type": "object",
                    "description": "Map of question_index (int or str) to answer value"
                }
            },
            "required": ["answers"]
        }
    },
    {
        "name": "submit_assessment",
        "description": "Submits assessment. Enforces Attempt Budget Protector (blocks submission if confidence < threshold).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "predicted_confidence_pct": {
                    "type": "number",
                    "description": "Estimated confidence percentage (0-100)",
                    "default": 100.0
                },
                "force": {
                    "type": "boolean",
                    "description": "Bypass safety threshold check",
                    "default": False
                }
            }
        }
    },
    {
        "name": "get_feedback",
        "description": "Parses score percentage and per-question correctness from assessment results screen.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "solve_multicast",
        "description": "Simulates FIFO or Causal Multicast delivery with Vector Clocks. Returns sequence vectors and buffered count.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "mode": {"type": "string", "enum": ["fifo", "causal"], "description": "Ordering mode"},
                "num_processes": {"type": "integer", "default": 4},
                "multicasts": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "List of multicasts: [{'id': 'M1', 'src': 1}, ...]"
                },
                "arrivals": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "List of arrivals: [{'msg': 'M1', 'dst': 0}, ...]"
                }
            },
            "required": ["mode", "multicasts", "arrivals"]
        }
    },
    {
        "name": "solve_diagram",
        "description": "Parses space-time or distributed system diagram image into graph structure in milliseconds.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "image_path": {"type": "string", "description": "Absolute path to diagram image"}
            },
            "required": ["image_path"]
        }
    }
]


def find_assessment_page(browser, target_keyword: Optional[str] = None):
    """
    Finds the active assessment page across all browser contexts and tabs.
    Prioritizes:
    1. Explicit keyword match in title or URL.
    2. Any page whose URL or Title matches known LMS platforms (coursera, canvas, moodle, blackboard, etc.).
    3. The first available page.
    """
    all_pages = []
    for ctx in browser.contexts:
        for p in ctx.pages:
            all_pages.append(p)

    if not all_pages:
        return None

    if target_keyword:
        kw = target_keyword.lower()
        for p in all_pages:
            try:
                if kw in p.url.lower() or kw in p.title().lower():
                    return p
            except Exception:
                pass

    lms_keywords = [
        "coursera.org", "instructure.com", "canvas", "moodle",
        "blackboard", "forms.gle", "docs.google.com/forms",
        "assignment", "quiz", "exam", "assessment"
    ]
    for kw in lms_keywords:
        for p in all_pages:
            try:
                if kw in p.url.lower() or kw in p.title().lower():
                    return p
            except Exception:
                pass

    return all_pages[0]


async def handle_call_tool(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    if name == "launch_browser":
        target_url = arguments.get("url", "https://www.coursera.org")
        port = int(arguments.get("port", 9222))
        ok, msg = launch_browser(url=target_url, port=port)
        return {"content": [{"type": "text", "text": json.dumps({"success": ok, "message": msg}, indent=2)}]}

    cdp_url = arguments.get("cdp_url", "http://127.0.0.1:9222")

    if name == "solve_multicast":
        mode = arguments["mode"]
        n_proc = arguments.get("num_processes", 4)
        mcasts = arguments["multicasts"]
        arrs = arguments["arrivals"]
        sim = MulticastSimulator(n_proc)
        if mode == "causal":
            res = sim.simulate_causal(n_proc, mcasts, arrs)
        else:
            res = sim.simulate_fifo(n_proc, mcasts, arrs)
        return {"content": [{"type": "text", "text": json.dumps(res, indent=2)}]}

    if name == "solve_diagram":
        img_path = arguments["image_path"]
        parsed = diagram_parser.parse_spacetime_diagram(img_path)
        solved = diagram_parser.solve_fast_lamport(parsed)
        return {"content": [{"type": "text", "text": json.dumps({"parsed": parsed, "solution": solved}, indent=2)}]}

    # Browser tools via CDP
    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp(cdp_url)
        except Exception as e:
            return {"isError": True, "content": [{"type": "text", "text": f"CDP Connection failed: {e}. Ensure browser launched with --remote-debugging-port=9222"}]}

        page = find_assessment_page(browser, arguments.get("tab_keyword"))
        if not page:
            return {"isError": True, "content": [{"type": "text", "text": "No browser tabs open. Please open your quiz in the browser."}]}

        adapter = get_lms_adapter(page)

        if name == "extract_questions":
            questions = adapter.extract_questions()
            return {"content": [{"type": "text", "text": json.dumps(questions, indent=2)}]}

        elif name == "fill_answer":
            idx = arguments["question_index"]
            val = arguments["value"]
            ok = adapter.fill_answer(idx, val)
            return {"content": [{"type": "text", "text": json.dumps({"question_index": idx, "success": ok})}]}

        elif name == "solve_batch":
            answers = arguments["answers"]
            results = {}
            for q_idx, val in answers.items():
                ok = adapter.fill_answer(int(q_idx), val)
                results[q_idx] = ok
            return {"content": [{"type": "text", "text": json.dumps(results, indent=2)}]}

        elif name == "submit_assessment":
            conf = float(arguments.get("predicted_confidence_pct", 100.0))
            force = arguments.get("force", False)
            if not force:
                allowed, reason = attempt_mgr.verify_attempt_budget(conf)
                if not allowed:
                    return {"isError": True, "content": [{"type": "text", "text": reason}]}
            
            submitted = adapter.submit_assessment()
            return {"content": [{"type": "text", "text": json.dumps({"submitted": submitted})}]}

        elif name == "get_feedback":
            fb = adapter.extract_feedback()
            return {"content": [{"type": "text", "text": json.dumps(fb, indent=2)}]}

    return {"isError": True, "content": [{"type": "text", "text": f"Unknown tool: {name}"}]}


def run_mcp_server():
    """Runs stdio JSON-RPC MCP server loop."""
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            req = json.loads(line)
        except Exception:
            continue

        req_id = req.get("id")
        method = req.get("method")
        params = req.get("params", {})

        if method == "tools/list":
            resp = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": TOOLS}
            }
        elif method == "tools/call":
            tool_name = params.get("name")
            tool_args = params.get("arguments", {})
            try:
                res = asyncio.run(handle_call_tool(tool_name, tool_args))
                resp = {"jsonrpc": "2.0", "id": req_id, "result": res}
            except Exception as e:
                resp = {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32603, "message": str(e)}}
        elif method == "initialize":
            resp = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "agentic-helper", "version": "1.0.0"}
                }
            }
        else:
            resp = {"jsonrpc": "2.0", "id": req_id, "result": {}}

        sys.stdout.write(json.dumps(resp) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    run_mcp_server()
