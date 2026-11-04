import re
from typing import Literal, Optional, Tuple
from pydantic import BaseModel, Field

from engine.state import (
    TOTAL_AIRPORT_KM,
    DialogueEntry,
    GameState,
    landmark_for_km,
)

ALLOWED_GAIN_ITEMS = {
    "cutting chai",
    "plastic raincoat",
    "metro token",
    "bus ticket",
}


class TurnProposal(BaseModel):
    """Compact structured schema for Gemini 2.5 Flash."""

    action_category: Literal[
        "talk_or_haggle",
        "accept_deal_and_move",
        "transit_travel",
        "phone_call_or_app",
        "walk_or_run",
        "use_or_trade_item",
        "cheat_or_nonsense",
    ] = Field(description="talk_or_haggle if asking/negotiating (0km, ₹0). accept_deal_and_move or transit_travel when moving.")
    speaker_name: str = Field(default="Auto Driver", description="Who is speaking (e.g. Auto Driver, BMTC Conductor, Friend on Phone, Traffic Cop).")
    spoken_response: str = Field(default="", description="Direct quote from speaker (1-2 sharp sentences in the EXACT SAME language as the player's input).")
    scene_explanation: str = Field(default="", description="1-2 short sentences of physical action and current situation.")
    time_delta_mins: int = Field(default=8, ge=2, le=22, description="3-5m talk, 8-14m move/transit.")
    battery_drain: int = Field(default=2, ge=0, le=10, description="0-1% no phone, 2-3% transit, 4-6% call/maps/UPI/app.")
    cash_spent: int = Field(default=0, ge=0, le=2000, description="INR spent this turn (0 if only talking/asking).")
    requires_phone_or_upi: bool = Field(default=False, description="True if using phone call, Maps, Uber/Ola/Rapido, or UPI.")
    distance_delta_km: float = Field(default=0.0, ge=0.0, le=7.5, description="Km moved toward 38km airport (0.0 if talking, 0.2-2.0km jam, 4.0-6.5km good move).")
    new_location_label: Optional[str] = Field(default=None, description="Current street/landmark name.")
    new_transport_mode: Optional[str] = Field(default=None, description="Current transport mode.")
    updated_scene_context: str = Field(default="", description="Short summary of current offer/situation.")
    item_consumed: Optional[str] = Field(default=None, description="Inventory item used, else null.")
    item_gained: Optional[str] = Field(default=None, description="Item gained, else null.")
    narrative: Optional[str] = Field(default=None, description="Optional fallback narrative.")


INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions",
    r"system\s*prompt",
    r"you\s+are\s+now\s+a",
    r"set\s+(my\s+)?(cash|battery|time|clock)\s+to",
    r"give\s+me\s+\d+\s*(rupees|cash|rs|inr)",
    r"override\s+(state|rules|game)",
    r"admin\s+mode",
    r"developer\s+mode",
    r"win\s+immediately",
]

GOD_MODE_CHEAT_PATTERNS = [
    r"\b(helicopter|chopper|jetpack|teleport|time\s*machine|flying\s*car|magic\s*carpet|portal|private\s*jet|rocket|superman|fly\s+to\s+the\s+airport)\b",
]

PHONE_DEPENDENT_PATTERNS = [
    r"\b(uber|ola|rapido|namma\s*yatri|upi|gpay|google\s*pay|phonepe|paytm|maps|google\s*maps|call\s+|phone\s+call|book\s+online|cab\s+app)\b",
]


class InputGuardrail:
    """Pre-LLM sanitization & zero-token anti-cheat shield."""

    @staticmethod
    def inspect(raw_text: str) -> Tuple[bool, str, Optional[str]]:
        if not raw_text or not raw_text.strip():
            return False, "", "empty"

        cleaned = re.sub(r"\s+", " ", raw_text.strip())[:240]
        lower = cleaned.lower()

        for pat in INJECTION_PATTERNS:
            if re.search(pat, lower):
                return False, cleaned, "prompt_injection"

        for pat in GOD_MODE_CHEAT_PATTERNS:
            if re.search(pat, lower):
                return False, cleaned, "god_mode_cheat"

        alpha_chars = [c for c in lower if c.isalpha()]
        if len(alpha_chars) < 2 and not any(c.isdigit() for c in lower):
            return False, cleaned, "gibberish"

        return True, cleaned, None

    @staticmethod
    def uses_phone_keywords(text: str) -> bool:
        lower = text.lower()
        return any(re.search(pat, lower) for pat in PHONE_DEPENDENT_PATTERNS)


class OutputGuardrail:
    """Post-LLM deterministic verifier. Code owns the facts; the LLM owns the story."""

    @staticmethod
    def enforce(state: GameState, proposal: TurnProposal, player_text: str) -> GameState:
        next_state = state.model_copy(deep=True)
        rule_notices = []

        speaker_name = (proposal.speaker_name or "Auto Driver").strip()
        spoken_response = (proposal.spoken_response or "").strip()
        scene_explanation = (proposal.scene_explanation or "").strip()
        if not spoken_response and proposal.narrative:
            spoken_response = proposal.narrative.strip()
        if not scene_explanation and proposal.narrative and spoken_response != proposal.narrative.strip():
            scene_explanation = proposal.narrative.strip()

        explicit_phone_use = InputGuardrail.uses_phone_keywords(player_text) or proposal.requires_phone_or_upi

        # 1. Handle Cheat / Nonsense
        if proposal.action_category == "cheat_or_nonsense":
            t_delta = max(3, min(7, proposal.time_delta_mins))
            next_state.time_minutes += t_delta
            if next_state.battery > 0:
                next_state.battery = max(0, next_state.battery - 1)
            rule_notices.append(f"Fair Play Rule: Reality holds firm (+{t_delta}m lost, 0 km moved).")
            return OutputGuardrail._finalize(
                next_state, player_text, speaker_name, spoken_response, scene_explanation, rule_notices
            )

        # 2. Enforce Dead Phone Rule (0% Battery => No UPI, No Cab Apps, No Calls, No Maps)
        if state.battery <= 0 and (explicit_phone_use or proposal.action_category == "phone_call_or_app"):
            next_state.time_minutes += 5
            rule_notices.append("Dead Phone (0% Battery): No UPI, no cab apps, and no calls.")
            speaker_name = "Auto Driver"
            spoken_response = '"Phone switched off, sir? No QR scan, no Uber here. Cash idya? Only cash works now."'
            scene_explanation = (
                "Your screen stays pitch-black at 0% battery. You lose 5 minutes standing in the drizzle."
            )
            return OutputGuardrail._finalize(
                next_state, player_text, speaker_name, spoken_response, scene_explanation, rule_notices
            )

        # 3. Enforce Wallet Rule & 8-to-12 Turn Pacing Curve
        cash_spent = max(0, proposal.cash_spent)
        if proposal.action_category == "talk_or_haggle":
            cash_spent = 0
            km_delta = 0.0
            t_delta = max(2, min(6, proposal.time_delta_mins))
            b_drain = max(0, min(2, proposal.battery_drain))
        else:
            if cash_spent > state.cash:
                rule_notices.append(
                    f"Insufficient Money: Needed ₹{cash_spent}, but you only have ₹{state.cash}."
                )
                speaker_name = speaker_name or "Driver"
                spoken_response = (
                    f'"Sir, ₹{cash_spent} means ₹{cash_spent}! You only have ₹{state.cash} in your hand. '
                    'Give a proper offer or find a bus."'
                )
                scene_explanation = (
                    f"You tried to spend ₹{cash_spent} with only ₹{state.cash} left. The vehicle doesn't move an inch, costing you 4 wasted minutes."
                )
                cash_spent = 0
                km_delta = 0.0
                t_delta = 4
                b_drain = 1 if state.battery > 0 else 0
            else:
                next_state.cash -= cash_spent
                # Enforce 8-12 turn pacing: max 6.0 km per turn in city, max 7.5 km past Hebbal (>=26.5 km)
                max_hop = 7.5 if state.distance_km >= 26.5 else 6.0
                km_delta = max(0.0, min(max_hop, round(proposal.distance_delta_km, 2)))
                t_delta = max(4, min(20, proposal.time_delta_mins))
                b_drain = max(1, min(7, proposal.battery_drain))
                if explicit_phone_use:
                    b_drain = max(b_drain, 3)

        # 4. Apply Monotonic Time, Battery, & Distance
        next_state.time_minutes += t_delta
        next_state.battery = max(0, next_state.battery - b_drain)
        if state.battery > 0 and next_state.battery == 0:
            rule_notices.append("Phone just died (0%): UPI and cab apps are now offline!")

        prev_km = next_state.distance_km
        next_state.distance_km = min(TOTAL_AIRPORT_KM, round(prev_km + km_delta, 2))

        # 5. Inventory Conservation
        if proposal.item_consumed and km_delta >= 0:
            matched = next(
                (it for it in next_state.inventory if proposal.item_consumed.lower() in it.lower() or it.lower() in proposal.item_consumed.lower()),
                None,
            )
            if matched:
                next_state.inventory.remove(matched)
                rule_notices.append(f"Used: {matched}")

        if proposal.item_gained:
            g = proposal.item_gained.strip().lower()
            if g in ALLOWED_GAIN_ITEMS and g not in next_state.inventory and len(next_state.inventory) < 3:
                next_state.inventory.append(g)

        # 6. Update Location & Scene Context only when appropriate
        if proposal.new_location_label and km_delta > 0:
            next_state.location_label = proposal.new_location_label.strip()[:55]
        elif km_delta > 0:
            lm = landmark_for_km(next_state.distance_km)
            next_state.location_label = lm.name

        if proposal.new_transport_mode:
            next_state.transport_mode = proposal.new_transport_mode.strip()[:45]

        if proposal.updated_scene_context:
            next_state.active_scene_context = proposal.updated_scene_context.strip()[:200]

        return OutputGuardrail._finalize(
            next_state, player_text, speaker_name, spoken_response, scene_explanation, rule_notices
        )

    @staticmethod
    def _finalize(
        next_state: GameState,
        player_text: str,
        speaker_name: str,
        spoken_response: str,
        scene_explanation: str,
        rule_notices: list,
    ) -> GameState:
        if next_state.turn == 5 and next_state.weather == "light_drizzle":
            next_state.weather = "heavy_downpour"
        elif next_state.turn == 9 and next_state.weather == "heavy_downpour":
            next_state.weather = "light_drizzle"

        if next_state.distance_km >= TOTAL_AIRPORT_KM and next_state.time_minutes <= next_state.deadline_minutes:
            next_state.status = "won"
            next_state.location_label = "KIA Terminal 1 Check-In Counter"
            next_state.end_reason = (
                f"You reached the Kempegowda Airport check-in counter at {next_state.formatted_time} "
                f"on Turn {next_state.turn} with {next_state.minutes_remaining} minutes to spare!"
            )
        elif next_state.time_minutes > next_state.deadline_minutes:
            next_state.status = "lost"
            next_state.end_reason = (
                f"The clock passed 8:55 PM ({next_state.formatted_time}). Check-in for Flight FL 2047 has closed while you are at {next_state.location_label} ({next_state.distance_km:.1f} / 38 km)."
            )
        elif next_state.turn >= next_state.max_turns and next_state.distance_km < TOTAL_AIRPORT_KM:
            next_state.status = "lost"
            next_state.end_reason = (
                f"After 12 turns of battling Bengaluru traffic, you are still at {next_state.location_label} ({next_state.distance_km:.1f} / 38 km) as boarding closes."
            )
        elif (
            next_state.battery == 0
            and next_state.cash < 20
            and len(next_state.inventory) == 0
            and next_state.distance_km < 34.0
        ):
            next_state.status = "lost"
            next_state.end_reason = (
                f"Phone dead (0%), ₹{next_state.cash} left, empty bag, and stranded at {next_state.location_label} ({next_state.distance_km:.1f} km)."
            )

        entry = DialogueEntry(
            turn=next_state.turn,
            player=player_text,
            speaker_name=speaker_name,
            spoken_response=spoken_response,
            scene_explanation=scene_explanation,
            time_str=next_state.formatted_time,
            location_label=next_state.location_label,
        )
        next_state.dialogue_history = (next_state.dialogue_history + [entry])[-10:]
        next_state.turn += 1
        next_state.last_speaker_name = speaker_name
        next_state.last_spoken_response = spoken_response
        next_state.last_narrative = scene_explanation
        next_state.last_rule_notice = " • ".join(rule_notices) if rule_notices else None

        return next_state
