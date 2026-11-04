import hashlib
import hmac
import os
from typing import List, Literal, Optional
from pydantic import BaseModel, Field

STATE_SECRET = os.environ.get("STATE_HMAC_SECRET", "esc-silk-board-futurelab-2026-hmac-key")
TOTAL_AIRPORT_KM = 38.0

# Gemini 2.5 Flash official pricing per 1M tokens (non-thinking output)
INPUT_COST_PER_M = 0.15
OUTPUT_COST_PER_M = 0.60


class Landmark(BaseModel):
    id: str
    name: str
    km: float
    description: str


ROUTE_LANDMARKS: List[Landmark] = [
    Landmark(
        id="silk_board",
        name="Silk Board Junction",
        km=0.0,
        description="Under the concrete flyover ramp, surrounded by honking autos and rain puddles.",
    ),
    Landmark(
        id="koramangala_hsr",
        name="Sony World / ORR Flyover",
        km=5.5,
        description="Signal gridlock where Inner Ring Road and Outer Ring Road traffic fight for inches.",
    ),
    Landmark(
        id="indiranagar_domlur",
        name="Indiranagar / Trinity Metro",
        km=12.0,
        description="Purple Line viaduct humming overhead while cabs crowd the wet 100ft Road slip lane.",
    ),
    Landmark(
        id="mekhri_circle",
        name="Mekhri Circle Underpass",
        km=20.0,
        description="The great northern funnel where city roads merge toward Bellary Road.",
    ),
    Landmark(
        id="hebbal_flyover",
        name="Hebbal Flyover Bottleneck",
        km=26.5,
        description="Five lanes of buses, trucks, and airport cabs squeezing onto the elevated highway.",
    ),
    Landmark(
        id="sadahalli_toll",
        name="Sadahalli Airport Toll",
        km=33.5,
        description="FASTag booms beeping under floodlights with low-flying jets visible through the mist.",
    ),
    Landmark(
        id="kia_terminal",
        name="Kempegowda Int'l Airport (Check-In)",
        km=38.0,
        description="Terminal 1 departure curb and the glowing check-in counters for Flight FL 2047.",
    ),
]


class DialogueEntry(BaseModel):
    turn: int
    player: str
    speaker_name: str
    spoken_response: str
    scene_explanation: str
    time_str: str
    location_label: str


class GameState(BaseModel):
    time_minutes: int = 1140          # 7:00 PM (19 * 60)
    deadline_minutes: int = 1255      # 8:55 PM (20 * 60 + 55)
    flight_minutes: int = 1300        # 9:40 PM (21 * 60 + 40)
    battery: int = 32                 # 0..100%
    cash: int = 500                   # Total money available (₹500)
    inventory: List[str] = Field(default_factory=lambda: ["1 cold samosa"])
    distance_km: float = 0.0          # 0.0 km (Silk Board) -> 38.0 km (Airport)
    location_label: str = "Silk Board Junction"
    transport_mode: str = "Standing by the curb"
    turn: int = 1
    max_turns: int = 12
    weather: Literal["humid_evening", "light_drizzle", "heavy_downpour"] = "light_drizzle"
    status: Literal["playing", "won", "lost"] = "playing"
    end_reason: Optional[str] = None
    active_scene_context: str = (
        "At Silk Board flyover pillar at 7:00 PM. Three autos parked nearby; "
        "none go by meter. Green airport bus trapped two lanes over."
    )
    dialogue_history: List[DialogueEntry] = Field(default_factory=list)
    last_speaker_name: str = "Auto Driver (Ramesh)"
    last_spoken_response: str = (
        '"Airport? Look at the signal, boss—even the rain is stuck at Silk Board. '
        'Tell me fast if you want to get in, or keep standing."'
    )
    last_narrative: str = (
        "It's 7:00 PM at Silk Board Junction. Check-in for Flight FL 2047 closes at 8:55 PM. "
        "You have ₹500, 32% battery, and 1 cold samosa in your bag. Three autos are idling by the wet curb."
    )
    last_rule_notice: Optional[str] = None

    # Real token utilization telemetry from Gemini usage_metadata
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_tokens: int = 0
    last_turn_input_tokens: int = 0
    last_turn_output_tokens: int = 0
    last_turn_total_tokens: int = 0

    @property
    def upi_enabled(self) -> bool:
        return self.battery > 0

    @property
    def minutes_remaining(self) -> int:
        return self.deadline_minutes - self.time_minutes

    @property
    def formatted_time(self) -> str:
        return format_clock(self.time_minutes)

    @property
    def estimated_cost_usd(self) -> float:
        in_cost = (self.total_input_tokens / 1_000_000) * INPUT_COST_PER_M
        out_cost = (self.total_output_tokens / 1_000_000) * OUTPUT_COST_PER_M
        return round(in_cost + out_cost, 6)


def format_clock(total_minutes: int) -> str:
    h = (total_minutes // 60) % 24
    m = total_minutes % 60
    period = "PM" if h >= 12 else "AM"
    h12 = h % 12 or 12
    return f"{h12}:{m:02d} {period}"


def landmark_for_km(km: float) -> Landmark:
    current = ROUTE_LANDMARKS[0]
    for lm in ROUTE_LANDMARKS:
        if km >= lm.km:
            current = lm
        else:
            break
    return current


def next_landmark_for_km(km: float) -> Optional[Landmark]:
    for lm in ROUTE_LANDMARKS:
        if lm.km > km:
            return lm
    return None


def create_initial_state() -> GameState:
    return GameState()


def sign_state(state: GameState) -> str:
    payload = state.model_dump_json()
    return hmac.new(STATE_SECRET.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_state(state_dict: dict, signature: str) -> GameState:
    state = GameState.model_validate(state_dict)
    expected = sign_state(state)
    if not hmac.compare_digest(expected, signature or ""):
        raise ValueError("State signature mismatch — tampering detected.")
    return state
