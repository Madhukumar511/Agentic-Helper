"""
Unified CLI Entry Point for Quiz-Pilot with Agent-Driven Bridge.
"""

import sys
import os
import shutil
import json
import argparse
import subprocess
import httpx
from rich.console import Console
from rich.table import Table

from quiz_pilot.cdp_client import CDPQuizClient
from quiz_pilot.server import start_server

console = Console()
BRIDGE_BASE = "http://127.0.0.1:8765"


def cmd_launch_brave(args):
    """Launches Brave with remote debugging enabled."""
    console.print("[bold cyan]Launching Brave with Remote Debugging (port 9222)...[/bold cyan]")
    brave_bin = "/opt/brave-bin/brave"
    if not os.path.exists(brave_bin):
        brave_bin = "brave"

    cmd = [
        brave_bin,
        f"--remote-debugging-port={args.port}",
        "--restore-last-session"
    ]
    try:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        console.print(f"[bold green]✓ Brave launched on port {args.port}![/bold green]")
    except Exception as e:
        console.print(f"[bold red]Failed to launch Brave: {e}[/bold red]")


def cmd_status(args):
    """Checks connection to browser tab via Bridge or CDP."""
    # 1. Try Bridge Server
    try:
        res = httpx.get(f"{BRIDGE_BASE}/api/agent/state", timeout=2.0)
        if res.status_code == 200:
            data = res.json()
            if data.get("connected"):
                console.print(f"[bold green]✓ Browser Tab Connected via Agent Bridge[/bold green]")
                console.print(f"Title: [bold white]{data.get('title')}[/bold white]")
                console.print(f"URL: [dim]{data.get('url')}[/dim]")
                console.print(f"Questions on screen: [bold cyan]{len(data.get('questions', []))}[/bold cyan]")
                return
    except Exception:
        pass

    # 2. Try CDP
    client = CDPQuizClient(cdp_url=f"http://127.0.0.1:{args.port}")
    if client.connect():
        tabs = client.list_tabs()
        client.close()
        console.print(f"[bold green]✓ Browser Connected via CDP (port {args.port})[/bold green]")
        console.print(f"Open tabs count: [bold cyan]{len(tabs)}[/bold cyan]")
        return

    console.print("[bold yellow]No active browser connection found.[/bold yellow]")
    console.print("Ensure `quiz-pilot server` is running and the snippet is pasted into Brave DevTools.")


def cmd_scan(args):
    """Scans and prints all questions and choices on the active quiz tab."""
    # 1. Try Bridge Server first
    try:
        res = httpx.get(f"{BRIDGE_BASE}/api/agent/state", timeout=3.0)
        if res.status_code == 200:
            data = res.json()
            if data.get("connected"):
                questions = data.get("questions", [])
                if not questions:
                    console.print("[yellow]No questions found on active page. Might be on loading or confirmation screen.[/yellow]")
                    return

                console.print(f"\n[bold green]=== Questions on Page ({len(questions)} total) ===[/bold green]")
                console.print(f"[dim]URL: {data.get('url')}[/dim]\n")

                if args.json:
                    print(json.dumps(questions, indent=2))
                    return

                for q in questions:
                    console.print(f"[bold cyan][Q{q['index']}][/bold cyan] [bold white]{q['text']}[/bold white]")
                    for opt in q.get("options", []):
                        checked_mark = " [green](Selected)[/green]" if opt.get("checked") else ""
                        console.print(f"   [[bold yellow]{opt['index']}[/bold yellow]] {opt['text']}{checked_mark}")
                    print()
                return
    except Exception:
        pass

    # 2. Try CDP fallback
    client = CDPQuizClient(cdp_url=f"http://127.0.0.1:{args.port}")
    if client.connect():
        client.select_tab()
        questions = client.scan_questions()
        client.close()

        if args.json:
            print(json.dumps(questions, indent=2))
            return

        for q in questions:
            console.print(f"[bold cyan][Q{q['index']}][/bold cyan] [bold white]{q['text']}[/bold white]")
            for opt in q.get("options", []):
                checked_mark = " [green](Selected)[/green]" if opt.get("checked") else ""
                console.print(f"   [[bold yellow]{opt['index']}[/bold yellow]] {opt['text']}{checked_mark}")
            print()
        return

    console.print("[bold red]Cannot connect to browser. Start `quiz-pilot server` or launch Brave with CDP.[/bold red]")


def cmd_answer(args):
    """Clicks a single option on the active browser tab."""
    # 1. Try Bridge Server
    try:
        res = httpx.post(f"{BRIDGE_BASE}/api/agent/click", json={"q": args.q, "opt": args.opt}, timeout=3.0)
        if res.status_code == 200:
            console.print(f"[bold green]✓ Clicked Question {args.q} -> Option {args.opt} via Bridge[/bold green]")
            return
    except Exception:
        pass

    # 2. Try CDP
    client = CDPQuizClient(cdp_url=f"http://127.0.0.1:{args.port}")
    if client.connect():
        client.select_tab()
        ok = client.click_option(args.q, args.opt)
        client.close()
        if ok:
            console.print(f"[bold green]✓ Clicked Question {args.q} -> Option {args.opt} via CDP[/bold green]")
        else:
            console.print(f"[bold red]Failed to click option via CDP[/bold red]")
        return

    console.print("[bold red]Cannot connect to browser.[/bold red]")


def cmd_solve_page(args):
    """Sends a batch of answers for all questions on the page and optionally clicks next."""
    try:
        answers_data = json.loads(args.answers)
    except Exception as e:
        console.print(f"[bold red]Invalid JSON for --answers: {e}[/bold red]")
        return

    # Normalize format: [{"q": 0, "opt": 1}, ...]
    normalized = []
    for item in answers_data:
        if isinstance(item, dict) and "q" in item and "opt" in item:
            normalized.append({"q": int(item["q"]), "opt": int(item["opt"])})

    # 1. Try Bridge Server
    try:
        res = httpx.post(
            f"{BRIDGE_BASE}/api/agent/solve-page",
            json={"answers": normalized, "click_next": args.next},
            timeout=10.0
        )
        if res.status_code == 200:
            console.print(f"[bold green]✓ Solved {len(normalized)} question(s) via Bridge![/bold green]")
            if args.next:
                console.print("[dim]Next page button clicked.[/dim]")
            return
    except Exception:
        pass

    # 2. Try CDP
    client = CDPQuizClient(cdp_url=f"http://127.0.0.1:{args.port}")
    if client.connect():
        client.select_tab()
        for item in normalized:
            client.click_option(item["q"], item["opt"])
        if args.next:
            client.click_next()
        client.close()
        console.print(f"[bold green]✓ Solved {len(normalized)} question(s) via CDP![/bold green]")
        return

    console.print("[bold red]Cannot connect to browser.[/bold red]")


def cmd_next(args):
    """Clicks Next Question or Next Page."""
    # 1. Try Bridge
    try:
        res = httpx.post(f"{BRIDGE_BASE}/api/agent/next", timeout=3.0)
        if res.status_code == 200:
            console.print("[bold green]✓ Clicked Next via Bridge[/bold green]")
            return
    except Exception:
        pass

    # 2. Try CDP
    client = CDPQuizClient(cdp_url=f"http://127.0.0.1:{args.port}")
    if client.connect():
        client.select_tab()
        res = client.click_next()
        client.close()
        if res.get("success"):
            console.print(f"[bold green]✓ Clicked Next via CDP ({res.get('clicked')})[/bold green]")
        else:
            console.print(f"[bold yellow]Next button not found: {res.get('error')}[/bold yellow]")
        return

    console.print("[bold red]Cannot connect to browser.[/bold red]")


def cmd_server(args):
    """Starts local bridge server."""
    start_server(host=args.host, port=args.port)


def cmd_hud_snippet(args):
    """Outputs snippet for browser console."""
    snippet = f"fetch('http://127.0.0.1:{args.port}/hud.js').then(r=>r.text()).then(eval);"
    console.print("\n[bold cyan]📋 In-Browser Console Snippet:[/bold cyan]")
    console.print("[dim]Open DevTools in Brave (Press F12 or Ctrl+Shift+I), paste into Console, and hit Enter:[/dim]\n")
    console.print(f"[bold green]{snippet}[/bold green]\n")


def cmd_list_tabs(args):
    """Lists all open tabs in browser via CDP."""
    client = CDPQuizClient(cdp_url=f"http://127.0.0.1:{args.port}")
    if not client.connect():
        console.print(f"[bold red]Cannot connect to browser at port {args.port}.[/bold red]")
        return

    tabs = client.list_tabs()
    client.close()

    if not tabs:
        console.print("[yellow]No open tabs found.[/yellow]")
        return

    table = Table(title="Active Browser Tabs", show_lines=True)
    table.add_column("Index", style="cyan", width=6)
    table.add_column("Title", style="bold white", width=45)
    table.add_column("URL", style="dim", overflow="fold")

    for t in tabs:
        table.add_row(str(t["index"]), t["title"][:45], t["url"])

    console.print(table)


def cmd_goto(args):
    """Navigates active tab to a URL."""
    client = CDPQuizClient(cdp_url=f"http://127.0.0.1:{args.port}")
    if client.connect():
        page = client.select_tab()
        if page:
            try:
                page.goto(args.url, wait_until="domcontentloaded", timeout=60000)
            except Exception as e:
                console.print(f"[yellow]Navigation notice: {e}[/yellow]")
            console.print(f"[bold green]✓ Current URL:[/bold green] {page.url}")
        client.close()


def cmd_screenshot(args):
    """Takes a screenshot of the active page for inspection."""
    client = CDPQuizClient(cdp_url=f"http://127.0.0.1:{args.port}")
    if client.connect():
        page = client.select_tab()
        if page:
            out_path = args.out or "/tmp/quiz_screenshot.png"
            page.screenshot(path=out_path)
            console.print(f"[bold green]✓ Screenshot saved to:[/bold green] {out_path}")
        client.close()


def cmd_clean(args):
    """Purges all temporary assessment cache, logs, submissions, and screenshots."""
    from quiz_pilot.attempt_protector import FastAttemptManager
    attempt_mgr = FastAttemptManager()
    attempt_mgr.purge_all()

    # Also wipe temporary solution submissions directory
    sub_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "submissions")
    if os.path.exists(sub_dir):
        shutil.rmtree(sub_dir, ignore_errors=True)

    console.print("[bold green]✓ Zero-Artifact Cleanup Complete: All temporary cache, submissions, and screenshots wiped![/bold green]")


def cmd_solve_all(args):
    """Solves and submits all open assessment tabs in parallel, or opens URLs and solves."""
    from quiz_pilot.tab_scheduler import solve_all_open_quizzes_sync, open_and_solve_parallel_sync, smart_multiworker_sync
    urls = getattr(args, "urls", [])
    if urls:
        console.print(f"[bold cyan]🚀 Opening {len(urls)} URLs in background tabs and running parallel workers (Max Concurrency: {args.concurrency})...[/bold cyan]")
        res = open_and_solve_parallel_sync(urls=urls, cdp_url=f"http://127.0.0.1:{args.port}", max_concurrency=args.concurrency)
    else:
        console.print(f"[bold cyan]🚀 Starting Smart Multi-Tab Worker Engine (Max Concurrency: {args.concurrency})...[/bold cyan]")
        res = smart_multiworker_sync(cdp_url=f"http://127.0.0.1:{args.port}", max_concurrency=args.concurrency)

    console.print(f"[bold green]✓ Completed multi-tab run: {res.get('passed_count', 0)}/{res.get('total_tabs', 0)} passed.[/bold green]")
    for r in res.get("results", []):
        status_color = "green" if r.get("passed") else "yellow"
        console.print(f"[{status_color}]Tab {r.get('tab_index')}: {r.get('title')} -> Score: {r.get('score_pct')}% ({r.get('status')})[/{status_color}]")


def cmd_inspect_task(args):
    """Scrapes active programming task specs, instructions, and starter code links."""
    from quiz_pilot.programming_solver import inspect_programming_task_sync
    res = inspect_programming_task_sync(cdp_url=f"http://127.0.0.1:{args.port}", tab_keyword=args.tab)
    if getattr(args, "json", False):
        console.print(json.dumps(res, indent=2))
    else:
        console.print(f"[bold green]Task:[/] {res.get('title')}")
        console.print(f"[bold cyan]Type:[/] {res.get('task_type')} | Has File Input: {res.get('has_file_input')}")
        starter_files = res.get('starter_files', [])
        if starter_files:
            console.print("[bold yellow]Starter Code Links:[/]")
            for f in starter_files:
                console.print(f" - {f.get('name')}: [dim]{f.get('url')}[/dim]")
        if res.get('latest_score') is not None:
            console.print(f"[bold magenta]Latest Score:[/] {res.get('latest_score')}%")


def cmd_submit_code(args):
    """Uploads solution code or archive to LMS autograder."""
    from quiz_pilot.programming_solver import submit_code_file_sync, poll_autograder_results_sync
    res = submit_code_file_sync(file_path=args.file, cdp_url=f"http://127.0.0.1:{args.port}", tab_keyword=args.tab)
    if not res.get("success"):
        console.print(f"[bold red]Submission Failed:[/] {res.get('error')}")
        return
    console.print(f"[bold green]✓ Solution attached & submitted:[/] {res.get('file_name')} ({res.get('file_size_bytes')} bytes)")
    if getattr(args, "wait", False):
        console.print("[bold cyan]Waiting for remote autograder results...[/bold cyan]")
        grade_res = poll_autograder_results_sync(cdp_url=f"http://127.0.0.1:{args.port}", tab_keyword=args.tab, timeout_sec=args.timeout)
        console.print(f"[bold green]Autograder Status:[/] {grade_res.get('status')} | Score: {grade_res.get('score_pct')}%")


def cmd_poll_grader(args):
    """Polls remote autograder output."""
    from quiz_pilot.programming_solver import poll_autograder_results_sync
    res = poll_autograder_results_sync(cdp_url=f"http://127.0.0.1:{args.port}", tab_keyword=args.tab, timeout_sec=args.timeout)
    console.print(f"[bold green]Autograder Status:[/] {res.get('status')} | Score: {res.get('score_pct')}%")
    if res.get("grader_output"):
        console.print("[bold white]Grader Output:[/bold white]")
        console.print(res.get("grader_output"))


def cmd_submit_peer(args):
    """Submits peer report PDF and optional video URL."""
    from playwright.sync_api import sync_playwright
    from quiz_pilot.peer_review_solver import PeerReviewManager
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{args.port}")
        from quiz_pilot.mcp_server import find_assessment_page
        page = find_assessment_page(browser, args.tab)
        if not page:
            console.print("[bold red]No assessment page found.[/bold red]")
            return
        prm = PeerReviewManager(page)
        res = prm.submit_peer_assignment(title=args.title, report_pdf_path=args.pdf, video_url=args.video or "")
        console.print(f"[bold green]✓ Peer Report Submitted:[/] {res.get('title')}")


def cmd_complete_reviews(args):
    """Completes required peer reviews."""
    from playwright.sync_api import sync_playwright
    from quiz_pilot.peer_review_solver import PeerReviewManager
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{args.port}")
        from quiz_pilot.mcp_server import find_assessment_page
        page = find_assessment_page(browser, args.tab)
        if not page:
            console.print("[bold red]No assessment page found.[/bold red]")
            return
        prm = PeerReviewManager(page)
        res = prm.complete_peer_reviews(count=args.count)
        console.print(f"[bold green]✓ Peer Reviews Finished:[/] Submitted: {res.get('reviews_submitted')}, Remaining: {res.get('reviews_remaining')}")


def cmd_crawl_syllabus(args):
    """Crawls course syllabus table and prints status."""
    import asyncio
    from playwright.async_api import async_playwright
    from quiz_pilot.syllabus_crawler import SyllabusCrawler

    async def _crawl():
        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(f"http://127.0.0.1:{args.port}")
            context = browser.contexts[0] if browser.contexts else await browser.new_context()
            page = context.pages[0] if context.pages else await context.new_page()
            if not page:
                console.print("[bold red]No browser page found.[/bold red]")
                return
            crawler = SyllabusCrawler(page=page)
            res = await crawler.crawl_course_assignments(args.course)
            console.print(f"[bold green]Course:[/] {res.get('course_slug')}")
            console.print(f"Total: {res.get('total_items')} | Completed: {res.get('completed_count')} | Pending: {res.get('pending_count')}")
            for it in res.get("execution_plan", []):
                console.print(f" - [{it.get('type')}] [bold white]{it.get('title')}[/] ({it.get('status')})")

    asyncio.run(_crawl())


def cmd_auto_course(args):
    """End-to-end autonomous course execution."""
    import asyncio
    from quiz_pilot.course_orchestrator import CourseOrchestrator
    orchestrator = CourseOrchestrator(cdp_url=f"http://127.0.0.1:{args.port}", max_concurrency=args.concurrency)
    console.print(f"[bold cyan]🚀 Starting Zero-Touch Course Auto-Pilot for: {args.course}...[/bold cyan]")
    res = asyncio.run(orchestrator.auto_complete_course(course_url=args.course, prefer_direct_api=not args.no_api))
    console.print(f"[bold green]✓ Course Run Completed:[/] Processed {res.get('total_processed', 0)} items.")




def main():
    parser = argparse.ArgumentParser(
        prog="quiz-pilot",
        description="Agent-Driven LMS Quiz Auto-Pilot (Canvas, Moodle, Blackboard, etc.)"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # goto
    p_goto = subparsers.add_parser("goto", help="Navigate to URL")
    p_goto.add_argument("url", type=str, help="Target URL")
    p_goto.add_argument("--port", type=int, default=9222)
    p_goto.set_defaults(func=cmd_goto)

    # screenshot
    p_shot = subparsers.add_parser("screenshot", help="Capture screenshot of active page")
    p_shot.add_argument("--out", type=str, default="/tmp/quiz_screenshot.png")
    p_shot.add_argument("--port", type=int, default=9222)
    p_shot.set_defaults(func=cmd_screenshot)

    # list-tabs
    p_tabs = subparsers.add_parser("list-tabs", help="List all open tabs in browser via CDP")
    p_tabs.add_argument("--port", type=int, default=9222)
    p_tabs.set_defaults(func=cmd_list_tabs)

    # status
    p_status = subparsers.add_parser("status", help="Check active browser tab connection")
    p_status.add_argument("--port", type=int, default=9222)
    p_status.set_defaults(func=cmd_status)

    # scan
    p_scan = subparsers.add_parser("scan", help="Scan and list all questions on the active quiz tab")
    p_scan.add_argument("--port", type=int, default=9222)
    p_scan.add_argument("--json", action="store_true", help="Output raw JSON")
    p_scan.set_defaults(func=cmd_scan)

    # answer
    p_ans = subparsers.add_parser("answer", help="Click an option for a question")
    p_ans.add_argument("--q", type=int, required=True, help="Question index")
    p_ans.add_argument("--opt", type=int, required=True, help="Option index")
    p_ans.add_argument("--port", type=int, default=9222)
    p_ans.set_defaults(func=cmd_answer)

    # solve-page
    p_solv = subparsers.add_parser("solve-page", help="Batch solve all questions on current page")
    p_solv.add_argument("--answers", type=str, required=True, help='JSON list, e.g. [{"q": 0, "opt": 1}]')
    p_solv.add_argument("--next", action="store_true", help="Click next button after solving")
    p_solv.add_argument("--port", type=int, default=9222)
    p_solv.set_defaults(func=cmd_solve_page)

    # next
    p_next = subparsers.add_parser("next", help="Click Next Question / Next Page button")
    p_next.add_argument("--port", type=int, default=9222)
    p_next.set_defaults(func=cmd_next)

    # server
    p_srv = subparsers.add_parser("server", help="Start local bridge server for In-Browser HUD")
    p_srv.add_argument("--host", type=str, default="127.0.0.1")
    p_srv.add_argument("--port", type=int, default=8765)
    p_srv.set_defaults(func=cmd_server)

    # launch-brave
    p_brave = subparsers.add_parser("launch-brave", help="Launch Brave with remote debugging on port 9222")
    p_brave.add_argument("--port", type=int, default=9222)
    p_brave.set_defaults(func=cmd_launch_brave)

    # hud-snippet
    p_snip = subparsers.add_parser("hud-snippet", help="Print JavaScript snippet for Brave console")
    p_snip.add_argument("--port", type=int, default=8765)
    p_snip.set_defaults(func=cmd_hud_snippet)

    # clean
    p_clean = subparsers.add_parser("clean", help="Purge all temporary assessment cache, logs, and screenshots")
    p_clean.set_defaults(func=cmd_clean)

    # solve-all
    p_sall = subparsers.add_parser("solve-all", aliases=["multiworker"], help="Concurrently solve open assessment tabs or open given URLs in parallel")
    p_sall.add_argument("urls", nargs="*", help="Optional list of course/quiz URLs to open in tabs and solve")
    p_sall.add_argument("--concurrency", type=int, default=4, help="Max parallel workers")
    p_sall.add_argument("--port", type=int, default=9222)
    p_sall.set_defaults(func=cmd_solve_all)

    # inspect-task
    p_itask = subparsers.add_parser("inspect-task", help="Inspect programming assignment instructions, links, and inputs")
    p_itask.add_argument("--tab", type=str, default=None, help="Tab keyword")
    p_itask.add_argument("--json", action="store_true", help="Output raw JSON")
    p_itask.add_argument("--port", type=int, default=9222)
    p_itask.set_defaults(func=cmd_inspect_task)

    # submit-code
    p_scode = subparsers.add_parser("submit-code", help="Upload and submit solution archive to LMS autograder")
    p_scode.add_argument("file", type=str, help="Path to code file or .zip archive")
    p_scode.add_argument("--tab", type=str, default=None, help="Tab keyword")
    p_scode.add_argument("--wait", action="store_true", help="Wait for remote autograder feedback")
    p_scode.add_argument("--timeout", type=int, default=120, help="Autograder wait timeout in seconds")
    p_scode.add_argument("--port", type=int, default=9222)
    p_scode.set_defaults(func=cmd_submit_code)

    # poll-grader
    p_pgrade = subparsers.add_parser("poll-grader", help="Poll autograder test results and score")
    p_pgrade.add_argument("--tab", type=str, default=None, help="Tab keyword")
    p_pgrade.add_argument("--timeout", type=int, default=120, help="Timeout in seconds")
    p_pgrade.add_argument("--port", type=int, default=9222)
    p_pgrade.set_defaults(func=cmd_poll_grader)

    # submit-peer
    p_speer = subparsers.add_parser("submit-peer", help="Upload and submit peer assignment report PDF and video link")
    p_speer.add_argument("--title", type=str, required=True, help="Project title")
    p_speer.add_argument("--pdf", type=str, required=True, help="Path to PDF report file")
    p_speer.add_argument("--video", type=str, default=None, help="Video demonstration URL")
    p_speer.add_argument("--tab", type=str, default=None, help="Tab keyword")
    p_speer.add_argument("--port", type=int, default=9222)
    p_speer.set_defaults(func=cmd_submit_peer)

    # complete-reviews
    p_crev = subparsers.add_parser("complete-reviews", help="Complete required peer reviews across rubric categories")
    p_crev.add_argument("--count", type=int, default=4, help="Number of reviews to complete")
    p_crev.add_argument("--tab", type=str, default=None, help="Tab keyword")
    p_crev.add_argument("--port", type=int, default=9222)
    p_crev.set_defaults(func=cmd_complete_reviews)

    # crawl-syllabus
    p_csyl = subparsers.add_parser("crawl-syllabus", help="Crawl course assignments table and extract pending task queue")
    p_csyl.add_argument("course", type=str, help="Course slug or URL")
    p_csyl.add_argument("--port", type=int, default=9222)
    p_csyl.set_defaults(func=cmd_crawl_syllabus)

    # auto-course
    p_acourse = subparsers.add_parser("auto-course", help="Autonomously crawl, solve, and submit an entire course")
    p_acourse.add_argument("course", type=str, help="Course slug or URL")
    p_acourse.add_argument("--concurrency", type=int, default=4, help="Max parallel workers")
    p_acourse.add_argument("--no-api", action="store_true", help="Disable direct REST API and use DOM only")
    p_acourse.add_argument("--port", type=int, default=9222)
    p_acourse.set_defaults(func=cmd_auto_course)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
