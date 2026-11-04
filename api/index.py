import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from engine.harness import GameHarness
from engine.state import ROUTE_LANDMARKS, TOTAL_AIRPORT_KM, create_initial_state, sign_state, verify_state

load_dotenv()

app = FastAPI(
    title="Escape Silk Board API",
    description="Deterministic Python + LangChain Game Harness for Escape Silk Board",
    version="2.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

PUBLIC_DIR = Path(__file__).resolve().parent.parent / "public"


class TurnRequest(BaseModel):
    action: str
    state: Dict[str, Any]
    signature: str
    api_key: Optional[str] = None


def _serialize_landmarks() -> List[Dict[str, Any]]:
    return [lm.model_dump() for lm in ROUTE_LANDMARKS]


def _has_server_api_key() -> bool:
    return bool(
        os.environ.get("GEMINI_API_KEY", "").strip()
        or os.environ.get("GOOGLE_API_KEY", "").strip()
    )


@app.get("/api/health")
@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "model": "gemini-2.5-flash",
        "has_server_key": _has_server_api_key(),
    }


@app.post("/api/start")
@app.post("/start")
def start_game():
    initial = create_initial_state()
    sig = sign_state(initial)
    has_key = _has_server_api_key()
    return {
        "state": initial.model_dump(),
        "formatted_time": initial.formatted_time,
        "minutes_remaining": initial.minutes_remaining,
        "upi_enabled": initial.upi_enabled,
        "estimated_cost_usd": initial.estimated_cost_usd,
        "signature": sig,
        "landmarks": _serialize_landmarks(),
        "total_km": TOTAL_AIRPORT_KM,
        "has_server_key": has_key,
    }


@app.post("/api/turn")
@app.post("/turn")
def play_turn(
    req: TurnRequest,
    x_gemini_key: Optional[str] = Header(default=None),
):
    try:
        prev_state = verify_state(req.state, req.signature)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))

    key_override = (req.api_key or x_gemini_key or "").strip() or None
    next_state, meta = GameHarness.step(
        prev_state,
        req.action,
        api_key_override=key_override,
    )
    new_sig = sign_state(next_state)

    deltas = {
        "time_delta": next_state.time_minutes - prev_state.time_minutes,
        "battery_delta": next_state.battery - prev_state.battery,
        "cash_delta": next_state.cash - prev_state.cash,
        "km_delta": round(next_state.distance_km - prev_state.distance_km, 2),
        "from_km": prev_state.distance_km,
        "to_km": next_state.distance_km,
    }

    return {
        "state": next_state.model_dump(),
        "formatted_time": next_state.formatted_time,
        "minutes_remaining": next_state.minutes_remaining,
        "upi_enabled": next_state.upi_enabled,
        "estimated_cost_usd": next_state.estimated_cost_usd,
        "signature": new_sig,
        "deltas": deltas,
        "meta": meta,
    }


@app.get("/")
def serve_index():
    return FileResponse(PUBLIC_DIR / "index.html")


@app.get("/styles.css")
def serve_styles():
    return FileResponse(PUBLIC_DIR / "styles.css", media_type="text/css")


@app.get("/app.js")
def serve_app_js():
    return FileResponse(PUBLIC_DIR / "app.js", media_type="application/javascript")


@app.api_route("/{full_path:path}", methods=["GET", "POST"])
def catch_all_debug(full_path: str):
    if full_path.endswith("health"):
        return health_check()
    if full_path.endswith("start"):
        return start_game()
    raise HTTPException(status_code=404, detail=f"Route not found: /{full_path}")

