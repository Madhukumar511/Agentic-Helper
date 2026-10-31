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
from quiz_pilot.tab_scheduler import AsyncTabScheduler
from quiz_pilot.programming_solver import ProgrammingAssignmentManager
from quiz_pilot.peer_review_solver import PeerReviewManager
from quiz_pilot.syllabus_crawler import SyllabusCrawler
from quiz_pilot.direct_api_solver import CourseraDirectAPI
from quiz_pilot.course_orchestrator import CourseOrchestrator

# Initialize helper engines
attempt_mgr = FastAttemptManager()
diagram_parser = LocalDiagramParser()
prog_manager = ProgrammingAssignmentManager()

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
        "description": "Fills multiple question answers in one ultra-fast atomic DOM execution (<50ms). Optionally marks and submits immediately.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "answers": {
                    "type": "object",
                    "description": "Map of question_index (int or str) to answer value"
                },
                "auto_submit": {
                    "type": "boolean",
                    "description": "Whether to tick honor code and submit immediately in the same call (default: false)",
                    "default": False
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
        "name": "record_quiz_analysis",
        "description": "Records quiz feedback, locks in verified correct options, eliminates wrong options, and updates quiz_analysis.md.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "quiz_id": {"type": "string", "description": "Assessment identifier or title"},
                "questions": {"type": "array", "description": "List of question objects"},
                "answers": {"type": "object", "description": "Map of question index to submitted answer"},
                "feedback": {"type": "object", "description": "Map of question index to boolean correctness (True/False)"},
                "score_pct": {"type": "number", "description": "Final score percentage (0-100)"},
                "attempt_num": {"type": "integer", "description": "Attempt sequence number (default: 1)", "default": 1}
            },
            "required": ["questions", "answers", "feedback"]
        }
    },
    {
        "name": "get_retry_answers",
        "description": "Retrieves answers for a quiz attempt by locking in verified correct choices from quiz_analysis.md and eliminating old wrong options.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "questions": {"type": "array", "description": "List of current question objects on screen"},
                "quiz_id": {"type": "string", "description": "Optional assessment identifier or title"}
            },
            "required": ["questions"]
        }
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
        "description": "Ultra-fast (<150ms) diagram & network topology solver. Supports local paths, remote HTTP/HTTPS URLs, and base64. Solves spacetime diagrams (Lamport/vector clocks, cuts), network topologies (Fat-Tree, Clos, Leaf-Spine), and matches against quiz options.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "image_path": {
                    "type": "string",
                    "description": "Local file path, HTTP/HTTPS URL, or base64 data URI of the diagram image"
                },
                "question_prompt": {
                    "type": "string",
                    "description": "Optional quiz question prompt text asking about the diagram"
                },
                "options": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of multiple choice option strings to match against"
                }
            },
            "required": ["image_path"]
        }
    },
    {
        "name": "inspect_all_tabs",
        "description": "Lists all open browser tabs and identifies which ones are active assessment or course pages.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cdp_url": {
                    "type": "string",
                    "description": "CDP URL (default: http://127.0.0.1:9222)",
                    "default": "http://127.0.0.1:9222"
                }
            }
        }
    },
    {
        "name": "solve_parallel_quizzes",
        "description": "Executes concurrent multi-tab quiz solving across all open assessment tabs using isolated async workers.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "max_concurrency": {
                    "type": "integer",
                    "description": "Maximum number of tabs to process in parallel (default: 4)",
                    "default": 4
                },
                "auto_submit": {
                    "type": "boolean",
                    "description": "Whether to automatically submit each quiz and verify grade (default: true)",
                    "default": True
                },
                "cdp_url": {
                    "type": "string",
                    "description": "CDP URL (default: http://127.0.0.1:9222)",
                    "default": "http://127.0.0.1:9222"
                }
            }
        }
    },
    {
        "name": "open_and_solve_parallel",
        "description": "Opens multiple course or assessment URLs into separate browser tabs and solves all of them concurrently in parallel.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "urls": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of course, module, or assessment URLs to open in tabs"
                },
                "max_concurrency": {
                    "type": "integer",
                    "description": "Maximum number of parallel workers (default: 4)",
                    "default": 4
                },
                "auto_submit": {
                    "type": "boolean",
                    "description": "Whether to automatically submit answers (default: true)",
                    "default": True
                },
                "cdp_url": {
                    "type": "string",
                    "description": "CDP URL (default: http://127.0.0.1:9222)",
                    "default": "http://127.0.0.1:9222"
                }
            },
            "required": ["urls"]
        }
    },
    {
        "name": "inspect_programming_task",
        "description": "Scrapes programming assignment instructions, starter code archive links (.zip, .py), upload inputs, and grading status.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tab_keyword": {
                    "type": "string",
                    "description": "Optional keyword in URL or Title to pick a specific tab (e.g. 'programming', 'mp1')"
                },
                "cdp_url": {
                    "type": "string",
                    "description": "CDP URL (default: http://127.0.0.1:9222)",
                    "default": "http://127.0.0.1:9222"
                }
            }
        }
    },
    {
        "name": "submit_code_file",
        "description": "Attaches a local solution file or archive (.zip, .tar.gz, .py) to the LMS file upload dropzone, ticks honor code, and submits.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute or relative path to the local solution file or .zip"
                },
                "tab_keyword": {
                    "type": "string",
                    "description": "Optional tab title/URL keyword"
                },
                "cdp_url": {
                    "type": "string",
                    "description": "CDP URL (default: http://127.0.0.1:9222)",
                    "default": "http://127.0.0.1:9222"
                }
            },
            "required": ["file_path"]
        }
    },
    {
        "name": "poll_autograder_results",
        "description": "Polls the LMS autograder results view until grading completes. Extracts score percentage, pass/fail state, and test case error logs.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "timeout_sec": {
                    "type": "integer",
                    "description": "Maximum seconds to wait for autograder completion (default: 120)",
                    "default": 120
                },
                "tab_keyword": {
                    "type": "string",
                    "description": "Optional tab keyword"
                },
                "cdp_url": {
                    "type": "string",
                    "description": "CDP URL (default: http://127.0.0.1:9222)",
                    "default": "http://127.0.0.1:9222"
                }
            }
        }
    },
    {
        "name": "submit_peer_assignment",
        "description": "Uploads and submits a peer-graded assignment report (PDF) and optional video URL on Coursera.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Project title"
                },
                "report_pdf_path": {
                    "type": "string",
                    "description": "Path to local PDF report file"
                },
                "video_url": {
                    "type": "string",
                    "description": "Optional video demonstration link (YouTube, Vimeo, etc.)"
                },
                "tab_keyword": {
                    "type": "string",
                    "description": "Optional tab keyword"
                },
                "cdp_url": {
                    "type": "string",
                    "description": "CDP URL (default: http://127.0.0.1:9222)",
                    "default": "http://127.0.0.1:9222"
                }
            },
            "required": ["title", "report_pdf_path"]
        }
    },
    {
        "name": "complete_peer_reviews",
        "description": "Fulfills required peer evaluations by selecting highest rubric ratings and providing constructive feedback until quota is completed.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "count": {
                    "type": "integer",
                    "description": "Number of peer reviews to complete (default: 4)",
                    "default": 4
                },
                "tab_keyword": {
                    "type": "string",
                    "description": "Optional tab keyword"
                },
                "cdp_url": {
                    "type": "string",
                    "description": "CDP URL (default: http://127.0.0.1:9222)",
                    "default": "http://127.0.0.1:9222"
                }
            }
        }
    },
    {
        "name": "auto_solve_current_assignment",
        "description": "Universal assessment solver that detects whether active page is a Quiz, Programming Assignment, or Peer Assignment, and automates completion.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tab_keyword": {
                    "type": "string",
                    "description": "Optional tab keyword"
                },
                "cdp_url": {
                    "type": "string",
                    "description": "CDP URL (default: http://127.0.0.1:9222)",
                    "default": "http://127.0.0.1:9222"
                }
            }
        }
    },
    {
        "name": "crawl_syllabus",
        "description": "Crawls course syllabus table and extracts complete status of all quizzes, programming tasks, and peer reviews, returning an execution plan.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "course_url": {
                    "type": "string",
                    "description": "Course URL or course slug (e.g. 'cloud-networking' or full Coursera URL)"
                },
                "cdp_url": {
                    "type": "string",
                    "description": "CDP URL (default: http://127.0.0.1:9222)",
                    "default": "http://127.0.0.1:9222"
                }
            },
            "required": ["course_url"]
        }
    },
    {
        "name": "auto_complete_entire_course",
        "description": "End-to-end autonomous course solver: discovers syllabus, solves quizzes via Direct API/DOM, submits peer reviews, and runs parallel workers without human interruption.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "course_url": {
                    "type": "string",
                    "description": "Course URL or slug to complete"
                },
                "max_concurrency": {
                    "type": "integer",
                    "description": "Maximum parallel tab workers (default: 4)",
                    "default": 4
                },
                "prefer_direct_api": {
                    "type": "boolean",
                    "description": "Whether to use sub-second Direct REST API submissions where supported",
                    "default": True
                },
                "cdp_url": {
                    "type": "string",
                    "description": "CDP URL (default: http://127.0.0.1:9222)",
                    "default": "http://127.0.0.1:9222"
                }
            },
            "required": ["course_url"]
        }
    },
    {
        "name": "auto_complete_specialization",
        "description": "Autonomously discovers all courses in a Specialization, slices the requested count (e.g. first 4), opens tabs, and completes them concurrently in parallel.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "specialization_url": {
                    "type": "string",
                    "description": "Specialization URL or slug (e.g. 'cloud-computing' or full URL)"
                },
                "max_courses": {
                    "type": "integer",
                    "description": "Number of initial courses to complete (e.g. 4 for first 4 courses)"
                },
                "max_concurrency": {
                    "type": "integer",
                    "description": "Max parallel workers (default: 4)",
                    "default": 4
                },
                "cdp_url": {
                    "type": "string",
                    "description": "CDP URL (default: http://127.0.0.1:9222)",
                    "default": "http://127.0.0.1:9222"
                }
            },
            "required": ["specialization_url"]
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
        q_prompt = arguments.get("question_prompt")
        opts = arguments.get("options")
        if q_prompt and opts:
            res = diagram_parser.solve_diagram_question(
                image_source=img_path,
                question_prompt=q_prompt,
                options=opts
            )
            return {"content": [{"type": "text", "text": json.dumps(res, indent=2)}]}
        else:
            parsed = diagram_parser.parse_spacetime_diagram(img_path)
            solved = diagram_parser.solve_fast_lamport(parsed)
            return {"content": [{"type": "text", "text": json.dumps({"parsed": parsed, "solution": solved}, indent=2)}]}

    if name == "inspect_all_tabs":
        scheduler = AsyncTabScheduler(cdp_url=cdp_url)
        tabs = await scheduler.inspect_all_tabs()
        return {"content": [{"type": "text", "text": json.dumps(tabs, indent=2)}]}

    if name == "solve_parallel_quizzes":
        concurrency = int(arguments.get("max_concurrency", 4))
        auto_sub = arguments.get("auto_submit", True)
        scheduler = AsyncTabScheduler(cdp_url=cdp_url, max_concurrency=concurrency)
        batch_results = await scheduler.smart_multiworker(auto_submit=auto_sub)
        return {"content": [{"type": "text", "text": json.dumps(batch_results, indent=2)}]}

    if name == "open_and_solve_parallel":
        urls = arguments["urls"]
        concurrency = int(arguments.get("max_concurrency", 4))
        auto_sub = arguments.get("auto_submit", True)
        scheduler = AsyncTabScheduler(cdp_url=cdp_url, max_concurrency=concurrency)
        batch_results = await scheduler.open_and_solve_parallel(urls=urls, auto_submit=auto_sub)
        return {"content": [{"type": "text", "text": json.dumps(batch_results, indent=2)}]}

    if name == "inspect_programming_task":
        tab_kw = arguments.get("tab_keyword")
        pm = ProgrammingAssignmentManager(cdp_url=cdp_url)
        res = await pm.extract_task_spec(tab_keyword=tab_kw)
        return {"content": [{"type": "text", "text": json.dumps(res, indent=2)}]}

    if name == "submit_code_file":
        f_path = arguments["file_path"]
        tab_kw = arguments.get("tab_keyword")
        pm = ProgrammingAssignmentManager(cdp_url=cdp_url)
        res = await pm.upload_and_submit(file_path=f_path, tab_keyword=tab_kw)
        return {"content": [{"type": "text", "text": json.dumps(res, indent=2)}]}

    if name == "poll_autograder_results":
        t_sec = int(arguments.get("timeout_sec", 120))
        tab_kw = arguments.get("tab_keyword")
        pm = ProgrammingAssignmentManager(cdp_url=cdp_url)
        res = await pm.poll_autograder_results(tab_keyword=tab_kw, timeout_sec=t_sec)
        return {"content": [{"type": "text", "text": json.dumps(res, indent=2)}]}

    if name == "submit_peer_assignment":
        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(cdp_url)
            page = find_assessment_page(browser, arguments.get("tab_keyword"))
            if not page:
                return {"isError": True, "content": [{"type": "text", "text": "No assessment page found."}]}
            prm = PeerReviewManager(page)
            res = prm.submit_peer_assignment(
                title=arguments["title"],
                report_pdf_path=arguments["report_pdf_path"],
                video_url=arguments.get("video_url", "")
            )
            return {"content": [{"type": "text", "text": json.dumps(res, indent=2)}]}

    if name == "complete_peer_reviews":
        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(cdp_url)
            page = find_assessment_page(browser, arguments.get("tab_keyword"))
            if not page:
                return {"isError": True, "content": [{"type": "text", "text": "No assessment page found."}]}
            prm = PeerReviewManager(page)
            cnt = int(arguments.get("count", 4))
            res = prm.complete_peer_reviews(count=cnt)
            return {"content": [{"type": "text", "text": json.dumps(res, indent=2)}]}

    if name == "auto_solve_current_assignment":
        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(cdp_url)
            page = find_assessment_page(browser, arguments.get("tab_keyword"))
            if not page:
                return {"isError": True, "content": [{"type": "text", "text": "No assessment page found."}]}
            
            url = page.url.lower()
            text = (await page.evaluate("() => document.body.innerText")).lower()

            if "/peer/" in url or "give-feedback" in url or "reviews" in text:
                prm = PeerReviewManager(page)
                t_info = prm.detect_peer_task(url, text)
                if t_info.get("mode") == "review":
                    res = prm.complete_peer_reviews(count=t_info.get("reviews_left") or 4)
                    return {"content": [{"type": "text", "text": json.dumps({"type": "peer_review", "result": res}, indent=2)}]}
                else:
                    return {"content": [{"type": "text", "text": json.dumps({"type": "peer_submission_ready", "info": t_info}, indent=2)}]}

            elif "programming" in url or "upload files and submit" in text:
                pm = ProgrammingAssignmentManager(cdp_url=cdp_url)
                spec = await pm.extract_task_spec(tab_keyword=arguments.get("tab_keyword"))
                return {"content": [{"type": "text", "text": json.dumps({"type": "programming_assignment", "spec": spec}, indent=2)}]}

            else:
                adapter = get_lms_adapter(page)
                questions = adapter.extract_questions()
                return {"content": [{"type": "text", "text": json.dumps({"type": "quiz", "questions_count": len(questions), "sample": questions[:2]}, indent=2)}]}

    if name == "crawl_syllabus":
        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(cdp_url)
            page = find_assessment_page(browser)
            if not page:
                return {"isError": True, "content": [{"type": "text", "text": "No assessment page found."}]}
            crawler = SyllabusCrawler(page=page)
            res = await crawler.crawl_course_assignments(arguments["course_url"])
            return {"content": [{"type": "text", "text": json.dumps(res, indent=2)}]}

    if name == "auto_complete_entire_course":
        concurrency = int(arguments.get("max_concurrency", 4))
        pref_direct = arguments.get("prefer_direct_api", True)
        orchestrator = CourseOrchestrator(cdp_url=cdp_url, max_concurrency=concurrency)
        res = await orchestrator.auto_complete_course(
            course_url=arguments["course_url"],
            prefer_direct_api=pref_direct
        )
        return {"content": [{"type": "text", "text": json.dumps(res, indent=2)}]}

    if name == "auto_complete_specialization":
        spec_url = arguments["specialization_url"]
        max_c = arguments.get("max_courses")
        concurrency = int(arguments.get("max_concurrency", 4))
        orchestrator = CourseOrchestrator(cdp_url=cdp_url, max_concurrency=concurrency)
        res = await orchestrator.auto_complete_specialization(
            spec_url=spec_url,
            max_courses=max_c
        )
        return {"content": [{"type": "text", "text": json.dumps(res, indent=2)}]}

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
            auto_sub = arguments.get("auto_submit", False)
            if hasattr(adapter, "batch_fill_answers"):
                results = adapter.batch_fill_answers(answers, auto_submit=auto_sub)
            else:
                results = {}
                for q_idx, val in answers.items():
                    results[str(q_idx)] = adapter.fill_answer(int(q_idx), val)
                if auto_sub:
                    adapter.submit_assessment()
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

        elif name == "record_quiz_analysis":
            qid = tool_args.get("quiz_id", "assessment")
            qs = tool_args.get("questions", [])
            ans = tool_args.get("answers", {})
            fb = tool_args.get("feedback", {})
            score = tool_args.get("score_pct")
            att = tool_args.get("attempt_num", 1)
            md = attempt_mgr.record_attempt(
                quiz_id=qid,
                attempt_num=att,
                questions=qs,
                answers=ans,
                feedback=fb,
                score_pct=score
            )
            return {"content": [{"type": "text", "text": md}]}

        elif name == "get_retry_answers":
            qs = tool_args.get("questions", [])
            qid = tool_args.get("quiz_id")
            answers = attempt_mgr.get_retry_answers(questions=qs, quiz_id=qid)
            return {"content": [{"type": "text", "text": json.dumps(answers, indent=2)}]}

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
