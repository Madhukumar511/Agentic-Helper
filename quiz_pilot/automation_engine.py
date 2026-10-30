"""
Automation Engine for Quiz-Pilot.
Drives question solving, safe clicking, jitter delays, and multi-page pagination.
"""

import time
import random
import logging
from typing import Optional, Dict, Any, Callable
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn

from quiz_pilot.cdp_client import CDPQuizClient
from quiz_pilot.ai_solver import AISolver

logger = logging.getLogger("quiz_pilot.engine")
console = Console()


class AutomationEngine:
    def __init__(
        self,
        client: CDPQuizClient,
        solver: AISolver,
        min_delay: float = 0.8,
        max_delay: float = 2.0,
        auto_submit: bool = False,
        max_questions: int = 5000,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None
    ):
        self.client = client
        self.solver = solver
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.auto_submit = auto_submit
        self.max_questions = max_questions
        self.progress_callback = progress_callback
        self.total_solved = 0
        self.is_running = False

    def _sleep_jitter(self):
        """Randomized human-like pause to avoid detection and race conditions."""
        delay = random.uniform(self.min_delay, self.max_delay)
        time.sleep(delay)

    def run_autopilot(self) -> Dict[str, Any]:
        """
        Main execution loop. Solves questions on current page,
        advances to next page, and repeats until quiz completion.
        """
        self.is_running = True
        page_num = 1
        consecutive_empty_pages = 0
        start_time = time.time()

        console.print(f"[bold cyan]🚀 Quiz-Pilot Auto-Pilot Engaged[/bold cyan]")
        console.print(f"[dim]Jitter Delay: {self.min_delay}s - {self.max_delay}s | Max Questions: {self.max_questions}[/dim]\n")

        try:
            while self.is_running and self.total_solved < self.max_questions:
                # 1. Scan questions on active page
                questions = self.client.scan_questions()

                if not questions:
                    consecutive_empty_pages += 1
                    # Check if we hit final submit screen
                    submit_info = self.client.check_submit_screen()
                    if submit_info.get("isSubmit"):
                        console.print(f"\n[bold green]🏁 Final quiz submit screen reached![/bold green] ({submit_info.get('label')})")
                        if self.auto_submit:
                            console.print("[yellow]Auto-submit enabled. Finalizing attempt...[/yellow]")
                            self.client.click_next()
                        else:
                            console.print("[bold yellow]⚠️ Auto-submit is OFF. Review answers in browser and submit when ready.[/bold yellow]")
                        break

                    if consecutive_empty_pages >= 3:
                        console.print("[bold yellow]No more questions detected across 3 attempts. Stopping loop.[/bold yellow]")
                        break
                    
                    time.sleep(1.5)
                    continue

                consecutive_empty_pages = 0
                console.print(f"[bold blue]📄 Page {page_num}: Found {len(questions)} question(s)[/bold blue]")

                # 2. Solve each question on this page
                for q in questions:
                    q_idx = q["index"]
                    q_text = q["text"][:70] + ("..." if len(q["text"]) > 70 else "")
                    
                    # Check if already answered
                    already_selected = any(opt.get("checked") for opt in q.get("options", []))
                    if already_selected:
                        console.print(f"  [dim]• Q{q_idx + 1}: Already answered. Skipping.[/dim]")
                        continue

                    # Solve via AI
                    solution = self.solver.solve_question(q)
                    selected_indices = solution.get("selected_indices", [0])
                    confidence = solution.get("confidence", 0.0)
                    explanation = solution.get("explanation", "")

                    # Click chosen option(s)
                    for opt_idx in selected_indices:
                        success = self.client.click_option(q_idx, opt_idx)
                        if success:
                            opt_label = q["options"][opt_idx]["text"][:40] if opt_idx < len(q["options"]) else f"#{opt_idx}"
                            conf_color = "green" if confidence >= 0.8 else "yellow"
                            console.print(
                                f"  [bold green]✓[/bold green] Q{q_idx + 1}: Selected [{opt_idx}] [bold]{opt_label}[/bold] "
                                f"([{conf_color}]{int(confidence * 100)}%[/{conf_color}])"
                            )
                        else:
                            console.print(f"  [bold red]✗[/bold red] Q{q_idx + 1}: Failed to click option {opt_idx}")

                    self.total_solved += 1
                    
                    if self.progress_callback:
                        self.progress_callback({
                            "question_text": q["text"],
                            "selected": selected_indices,
                            "confidence": confidence,
                            "explanation": explanation,
                            "total_solved": self.total_solved
                        })

                    # Safe anti-detection delay
                    self._sleep_jitter()

                # 3. Check for Next button to advance multi-page quizzes
                next_res = self.client.click_next()
                if next_res.get("success"):
                    console.print(f"[dim]Advancing to next page via '{next_res.get('clicked')}'...[/dim]")
                    self.client.wait_for_dom_settle(2.0)
                    page_num += 1
                else:
                    # Single page quiz or finished
                    console.print("[dim]No next page button found. Single-page quiz complete![/dim]")
                    break

        except KeyboardInterrupt:
            console.print("\n[bold yellow]Paused by user (Ctrl+C).[/bold yellow]")
        except Exception as e:
            console.print(f"\n[bold red]Error during autopilot execution: {e}[/bold red]")
            logger.exception("Engine failure")
        finally:
            self.is_running = False

        duration = round(time.time() - start_time, 1)
        console.print(f"\n[bold green]🎉 Auto-Pilot Finished:[/bold green] Solved [bold]{self.total_solved}[/bold] questions in [bold]{duration}s[/bold].")
        return {
            "total_solved": self.total_solved,
            "duration_sec": duration,
            "pages_processed": page_num
        }

    def stop(self):
        """Signals engine to stop execution gracefully."""
        self.is_running = False
