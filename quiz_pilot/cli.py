"""
Unified CLI Entry Point for Quiz-Pilot with Agent-Driven Bridge.
"""

import sys
import os
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

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
