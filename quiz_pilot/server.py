"""
Local Bridge Server for Quiz-Pilot.
Maintains live WebSocket connection with browser tabs and provides
Agent Bridge endpoints for Antigravity to scan and answer questions directly.
"""

import os
import json
import asyncio
from pathlib import Path
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

app = FastAPI(title="Quiz-Pilot Bridge Server", version="1.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

HUD_PATH = Path(__file__).parent / "hud" / "hud.js"

# Global state shared between active browser tabs and agent
active_websockets: List[WebSocket] = []
active_browser_ws: Optional[WebSocket] = None
latest_page_state: Dict[str, Any] = {
    "url": "",
    "title": "",
    "questions": [],
    "is_connected": False
}


class ClickRequest(BaseModel):
    q: int
    opt: int


class SolvePageRequest(BaseModel):
    answers: List[ClickRequest]
    click_next: bool = False


@app.get("/")
def index():
    return {
        "status": "online",
        "service": "Quiz-Pilot Agent Bridge Server",
        "browser_connected": len(active_websockets) > 0,
        "connected_tabs": len(active_websockets),
        "questions_count": len(latest_page_state.get("questions", [])),
        "url": latest_page_state.get("url", "")
    }


@app.get("/hud.js")
def get_hud_script():
    """Serves injectable HUD script."""
    if HUD_PATH.exists():
        return FileResponse(HUD_PATH, media_type="application/javascript")
    raise HTTPException(status_code=404, detail="HUD script not found.")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Live bidirectional channel with browser tabs."""
    global active_browser_ws, latest_page_state
    await websocket.accept()
    if websocket not in active_websockets:
        active_websockets.append(websocket)
    active_browser_ws = active_websockets[-1]
    latest_page_state["is_connected"] = True
    print(f"\n[Quiz-Pilot Bridge] Browser tab connected via WebSocket! (Active tabs: {len(active_websockets)})")

    try:
        while True:
            data_text = await websocket.receive_text()
            msg = json.loads(data_text)
            msg_type = msg.get("type")

            if msg_type == "page_state":
                latest_page_state["url"] = msg.get("url", "")
                latest_page_state["title"] = msg.get("title", "")
                latest_page_state["questions"] = msg.get("questions", [])
                print(f"[Quiz-Pilot Bridge] Received {len(latest_page_state['questions'])} question(s) from '{latest_page_state['title']}'")
            elif msg_type == "action_result":
                print(f"[Quiz-Pilot Bridge] Action result: {msg.get('action')} -> {msg.get('success')}")

    except WebSocketDisconnect:
        print("[Quiz-Pilot Bridge] Browser tab disconnected.")
    except Exception as e:
        print(f"[Quiz-Pilot Bridge] WebSocket error: {e}")
    finally:
        if websocket in active_websockets:
            active_websockets.remove(websocket)
        active_browser_ws = active_websockets[-1] if active_websockets else None
        latest_page_state["is_connected"] = len(active_websockets) > 0


# --- Agent Endpoints ---

@app.get("/api/agent/state")
def get_agent_state():
    """Agent calls this to get currently visible questions on screen."""
    return {
        "connected": len(active_websockets) > 0,
        "connected_tabs": len(active_websockets),
        "url": latest_page_state.get("url", ""),
        "title": latest_page_state.get("title", ""),
        "questions": latest_page_state.get("questions", [])
    }


@app.post("/api/agent/click")
async def agent_click_option(req: ClickRequest):
    """Agent clicks a specific option."""
    ws = active_websockets[-1] if active_websockets else None
    if not ws:
        raise HTTPException(status_code=503, detail="No browser tab connected via WebSocket.")

    await ws.send_text(json.dumps({
        "type": "click_option",
        "q": req.q,
        "opt": req.opt
    }))
    return {"status": "sent", "q": req.q, "opt": req.opt}


@app.post("/api/agent/solve-page")
async def agent_solve_page(req: SolvePageRequest):
    """Agent sends answers for all questions on current page at once."""
    ws = active_websockets[-1] if active_websockets else None
    if not ws:
        raise HTTPException(status_code=503, detail="No browser tab connected via WebSocket.")

    for item in req.answers:
        await ws.send_text(json.dumps({
            "type": "click_option",
            "q": item.q,
            "opt": item.opt
        }))
        await asyncio.sleep(0.3)

    if req.click_next:
        await asyncio.sleep(0.5)
        await ws.send_text(json.dumps({"type": "click_next"}))

    return {"status": "completed", "solved_count": len(req.answers), "next_clicked": req.click_next}


@app.post("/api/agent/next")
async def agent_click_next():
    """Agent advances to next question or page."""
    ws = active_websockets[-1] if active_websockets else None
    if not ws:
        raise HTTPException(status_code=503, detail="No browser tab connected via WebSocket.")

    await ws.send_text(json.dumps({"type": "click_next"}))
    return {"status": "sent", "action": "click_next"}


def start_server(host: str = "127.0.0.1", port: int = 8765):
    """Launches the Uvicorn web server."""
    import uvicorn
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    start_server()
