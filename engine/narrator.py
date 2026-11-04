import os
from typing import Dict, Optional, Tuple
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI

from engine.guardrails import InputGuardrail, TurnProposal
from engine.state import (
    TOTAL_AIRPORT_KM,
    GameState,
    landmark_for_km,
    next_landmark_for_km,
)

SYSTEM_PROMPT = """You are the witty, deadpan Game Master of 'Escape Silk Board' (Bengaluru traffic survival).
Goal: Reach Kempegowda Airport check-in (38.0 km) from Silk Board (0.0 km) between 7:00 PM and 8:55 PM (115 mins budget, ₹500 total budget, 8 to 12 turns).

TWO-PART OUTPUT:
- `speaker_name`: Who is speaking (e.g. "Auto Driver (Ramesh)", "BMTC Conductor", "Metro Staff", "Co-Passenger", "Friend on Call").
- `spoken_response` (MAIN): Direct spoken reply in quotes (1-2 punchy sentences, authentic Bengaluru tone).
- `scene_explanation` (SUBTEXT): 1-2 short sentences of physical consequence & current situation.

PACING & FAIRNESS RULES (A full game takes 8 to 12 turns to cover 38.0 km):
1. TALKING vs MOVING: Asking a question or checking fare (`"airport chaloge? meter se"`, `"how much?"`) MUST set `action_category='talk_or_haggle'`, `distance_delta_km=0.0`, `cash_spent=0`, `time_delta_mins=3..5`. Quote a fare and wait for their reply.
2. MOVING (4.0 to 6.0 km per city turn so a full run takes 8–12 turns):
   - Crawling in Silk Board / service road jam: `0.5` to `2.5 km` (`8–11 mins`).
   - Walking / Jogging / Samosa barter / Shortcut tip: `3.0` to `4.5 km` (`9–12 mins`, `₹0–₹80`).
   - Namma Metro / BMTC Bus / Auto / Rapido hop: `4.5` to `6.0 km` (`10–13 mins`, `₹40–₹100`).
   - Final Airport Expressway stretch (past Hebbal >=26.5 km): `6.0` to `7.5 km` (`11–14 mins`, `₹80–₹120`).
3. HARD FACTS: Money=₹{cash}, Battery={battery}% (If 0%, UPI/Uber/Ola/Rapido/Maps/Calls MUST fail), Bag={inventory}."""

HUMAN_PROMPT = """STATE: {time_str} ({mins_left}m left) | Turn {turn}/12 | At: {location_label} ({distance_km:.1f}/38km, next: {next_landmark}) | Mode: {transport_mode} | Weather: {weather} | Batt: {battery}% (UPI:{upi_allowed}) | Cash: ₹{cash} | Bag: {inventory}
Scene: {active_scene_context}
Recent:
{dialogue_history_text}
Player: "{player_text}" """


class NarratorEngine:
    MODEL_NAME = "gemini-2.5-flash"

    @classmethod
    def resolve_api_key(cls, api_key_override: Optional[str] = None) -> Tuple[Optional[str], str]:
        user_key = (api_key_override or "").strip()
        if user_key:
            return user_key, "user_key"
        server_key = (
            os.environ.get("GEMINI_API_KEY", "").strip()
            or os.environ.get("GOOGLE_API_KEY", "").strip()
        )
        if server_key:
            return server_key, "server_key"
        return None, "no_key"

    @classmethod
    def generate_proposal(
        cls,
        state: GameState,
        player_text: str,
        api_key_override: Optional[str] = None,
    ) -> Tuple[TurnProposal, Dict[str, object]]:
        api_key, key_source = cls.resolve_api_key(api_key_override)

        if not api_key:
            fallback = cls._fallback_proposal(state, player_text)
            return fallback, {
                "model_used": "local-fallback",
                "key_source": "no_key",
                "api_status": "no_key",
                "status_message": (
                    "No Gemini API key found on the server. Even Silk Board autos don't move for free—click '🔑 API Key' at the top to plug in your key!"
                ),
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
            }

        try:
            llm = ChatGoogleGenerativeAI(
                model=cls.MODEL_NAME,
                google_api_key=api_key,
                temperature=0.65,
                thinking_budget=0,
                max_output_tokens=600,
                max_retries=1,
            )
            structured_llm = llm.with_structured_output(TurnProposal, include_raw=True)
            prompt = ChatPromptTemplate.from_messages(
                [("system", SYSTEM_PROMPT), ("human", HUMAN_PROMPT)]
            )
            chain = prompt | structured_llm

            next_lm = next_landmark_for_km(state.distance_km)
            next_lm_str = f"{next_lm.name} ({next_lm.km}km)" if next_lm else "Airport (38km)"

            history_lines = []
            for d in state.dialogue_history[-3:]:
                history_lines.append(
                    f"T{d.turn}: P='{d.player}' -> {d.speaker_name}: {d.spoken_response}"
                )
            history_text = "\n".join(history_lines) if history_lines else "Start at Silk Board."

            res_dict = chain.invoke(
                {
                    "cash": state.cash,
                    "battery": state.battery,
                    "distance_km": state.distance_km,
                    "inventory": ", ".join(state.inventory) if state.inventory else "Empty",
                    "time_str": state.formatted_time,
                    "mins_left": state.minutes_remaining,
                    "turn": state.turn,
                    "location_label": state.location_label,
                    "next_landmark": next_lm_str,
                    "transport_mode": state.transport_mode,
                    "weather": state.weather,
                    "upi_allowed": state.upi_enabled,
                    "active_scene_context": state.active_scene_context,
                    "dialogue_history_text": history_text,
                    "player_text": player_text,
                }
            )

            parsed: Optional[TurnProposal] = res_dict.get("parsed") if isinstance(res_dict, dict) else res_dict
            raw_msg = res_dict.get("raw") if isinstance(res_dict, dict) else None

            in_tok, out_tok, tot_tok = 0, 0, 0
            if raw_msg is not None and getattr(raw_msg, "usage_metadata", None):
                usage = raw_msg.usage_metadata
                in_tok = int(usage.get("input_tokens", 0))
                out_tok = int(usage.get("output_tokens", 0))
                tot_tok = int(usage.get("total_tokens", in_tok + out_tok))

            if parsed is not None:
                return parsed, {
                    "model_used": cls.MODEL_NAME,
                    "key_source": key_source,
                    "api_status": "ok",
                    "status_message": None,
                    "input_tokens": in_tok,
                    "output_tokens": out_tok,
                    "total_tokens": tot_tok,
                }
            parse_err = res_dict.get("parsing_error") if isinstance(res_dict, dict) else None
            if parse_err is not None:
                raise ValueError(f"Structured output parsing error: {parse_err}")
        except Exception as exc:
            err_str = str(exc).lower()
            if (
                key_source == "user_key"
                and (
                    os.environ.get("GEMINI_API_KEY", "").strip()
                    or os.environ.get("GOOGLE_API_KEY", "").strip()
                )
            ):
                # User had a stale/exhausted key saved in browser localStorage; transparently retry with the server key!
                return cls.generate_proposal(state, player_text, api_key_override=None)

            if any(w in err_str for w in ("429", "quota", "resource_exhausted", "resourceexhausted", "rate limit", "tokens", "timed out", "timeout")):
                api_status = "quota_exhausted"
                msg = (
                    "The provided Gemini API key hit its free-tier rate/token limit (stuck at Silk Board like everything else). "
                    "Wait 15s or click '🔑 API Key' at the top to drop in a fresh key!"
                )
            elif any(w in err_str for w in ("api_key_invalid", "invalid api key", "403", "permission_denied", "unauthenticated")):
                api_status = "invalid_key"
                msg = (
                    "That Gemini API key was rejected by Google's traffic police. "
                    "Click '🔑 API Key' at the top to check or replace it!"
                )
            else:
                api_status = "api_error"
                msg = f"Gemini hiccup ({type(exc).__name__}: {str(exc)[:90]})—used backup street narrator for this turn."

            fallback = cls._fallback_proposal(state, player_text)
            return fallback, {
                "model_used": f"fallback ({api_status})",
                "key_source": key_source,
                "api_status": api_status,
                "status_message": msg,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
            }

        fallback = cls._fallback_proposal(state, player_text)
        return fallback, {
            "model_used": "local-fallback",
            "key_source": key_source,
            "api_status": "ok",
            "status_message": None,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        }

    @classmethod
    def _fallback_proposal(cls, state: GameState, player_text: str) -> TurnProposal:
        lower = player_text.lower()
        uses_phone = InputGuardrail.uses_phone_keywords(player_text)

        is_just_asking = (
            "meter" in lower
            or "chaloge" in lower
            or "how much" in lower
            or "kitna" in lower
            or lower.startswith(("ask ", "talk ", "say ", "hello", "hi", "hey", "bhaiya", "anna"))
            and not any(w in lower for w in ("offer", "give", "pay", "deal", "samosa", "board", "hop", "take"))
        )
        if is_just_asking:
            return TurnProposal(
                action_category="talk_or_haggle",
                speaker_name="Auto Driver (Ramesh)",
                spoken_response='"Meter? Sir, the meter is also stuck at Silk Board. ₹650 direct to the airport, or ₹120 to drop you at Sony World."',
                scene_explanation=f"He looks at you, then the traffic, then the rain without starting his engine. He wants ₹650; you have ₹{state.cash}.",
                time_delta_mins=4,
                battery_drain=0,
                cash_spent=0,
                requires_phone_or_upi=False,
                distance_delta_km=0.0,
                new_location_label=state.location_label,
                new_transport_mode=state.transport_mode,
                updated_scene_context="Auto driver wants ₹650 to airport or ₹120 to Sony World. Waiting for your counter-offer.",
            )

        if "samosa" in lower and any("samosa" in it.lower() for it in state.inventory):
            offer_cost = 80 if state.cash >= 80 else state.cash
            hop_km = 5.5
            new_km = min(TOTAL_AIRPORT_KM, state.distance_km + hop_km)
            lm = landmark_for_km(new_km)
            return TurnProposal(
                action_category="use_or_trade_item",
                speaker_name="Auto Driver (Ramesh)",
                spoken_response=f'"Cold samosa plus ₹{offer_cost}? Deal! Sit fast before the traffic cop blows his whistle!"',
                scene_explanation=f"He pockets the foil-wrapped samosa with real respect and threads through a narrow slip lane, covering {hop_km} km to {lm.name} in 11 minutes.",
                time_delta_mins=11,
                battery_drain=1,
                cash_spent=offer_cost,
                requires_phone_or_upi=False,
                distance_delta_km=hop_km,
                new_location_label=lm.name,
                new_transport_mode="In an auto",
                updated_scene_context=f"Reached {lm.name} after trading the samosa.",
                item_consumed="1 cold samosa",
            )

        if any(w in lower for w in ("call", "friend", "shortcut", "maps", "google")):
            return TurnProposal(
                action_category="phone_call_or_app",
                speaker_name="Friend on Phone (Karthik)",
                spoken_response='"Bro, take the service road, left at the temple, then catch the Metro at Indiranagar—hello?!"',
                scene_explanation="The call drops at one bar of signal, and you edge 2.5 km down the crowded service road in 9 minutes.",
                time_delta_mins=9,
                battery_drain=4,
                cash_spent=0,
                requires_phone_or_upi=True,
                distance_delta_km=2.5,
                new_location_label=state.location_label + " (Service Road)",
                new_transport_mode=state.transport_mode,
                updated_scene_context="Cleared 2.5 km on the service road after your friend's call dropped.",
            )

        if any(w in lower for w in ("metro", "purple line", "train", "token")):
            fare = 50
            hop_km = 5.5
            new_km = min(TOTAL_AIRPORT_KM, state.distance_km + hop_km)
            lm = landmark_for_km(new_km)
            return TurnProposal(
                action_category="transit_travel",
                speaker_name="Namma Metro Announcer",
                spoken_response=f'"Doors closing! ₹{fare} token—next interchange moving fast!"',
                scene_explanation=f"You tap your ₹{fare} token and glide above the gridlocked roads, covering {hop_km} km to {lm.name} in 11 minutes.",
                time_delta_mins=11,
                battery_drain=1,
                cash_spent=fare,
                requires_phone_or_upi=uses_phone,
                distance_delta_km=hop_km,
                new_location_label=lm.name,
                new_transport_mode="Namma Metro",
                updated_scene_context=f"Stepped out at {lm.name} ({new_km:.1f} / 38.0 km).",
            )

        if any(w in lower for w in ("bus", "vayu vajra", "kia", "bmtc", "shuttle", "expressway")):
            fare = 80
            hop_km = 6.5 if state.distance_km >= 26.5 else 5.5
            new_km = min(TOTAL_AIRPORT_KM, state.distance_km + hop_km)
            lm = landmark_for_km(new_km)
            return TurnProposal(
                action_category="transit_travel",
                speaker_name="BMTC Vayu Vajra Conductor",
                spoken_response=f'"KIA-8 Airport Express! ₹{fare} stage ticket—hold the rail, driver is taking the flyover ramp!"',
                scene_explanation=f"The green Volvo bus pushes through the corridor, covering {hop_km} km to {lm.name} in 12 minutes.",
                time_delta_mins=12,
                battery_drain=2,
                cash_spent=fare,
                requires_phone_or_upi=uses_phone,
                distance_delta_km=hop_km,
                new_location_label=lm.name,
                new_transport_mode="KIA Vayu Vajra Bus",
                updated_scene_context=f"At {lm.name} ({new_km:.1f} / 38.0 km).",
            )

        if any(w in lower for w in ("walk", "run", "sprint", "foot")):
            hop_km = 3.0
            new_km = min(TOTAL_AIRPORT_KM, state.distance_km + hop_km)
            lm = landmark_for_km(new_km)
            return TurnProposal(
                action_category="walk_or_run",
                speaker_name="Stranded Commuter",
                spoken_response='"Sprinting with a duffle bag in the rain? Respect, boss—you\'re beating every car on this road!"',
                scene_explanation=f"You hoist your bag and jog {hop_km} km along the wet pavement, reaching {lm.name} in 12 minutes.",
                time_delta_mins=12,
                battery_drain=1,
                cash_spent=0,
                requires_phone_or_upi=False,
                distance_delta_km=hop_km,
                new_location_label=lm.name,
                new_transport_mode="On foot",
                updated_scene_context=f"Reached {lm.name} on foot.",
            )

        fare = 700 if ("650" in lower or "700" in lower or "1000" in lower) else 70
        hop_km = 6.5 if state.distance_km >= 26.5 else 5.5
        new_km = min(TOTAL_AIRPORT_KM, state.distance_km + hop_km)
        lm = landmark_for_km(new_km)
        return TurnProposal(
            action_category="accept_deal_and_move",
            speaker_name="Driver",
            spoken_response=f'"Alright, ₹{fare} for this leg. Hold tight, I\'m cutting through the gap before the signal turns red!"',
            scene_explanation=f"You lock in the ride for ₹{fare} and weave through traffic, covering {hop_km} km in 11 minutes to reach {lm.name}.",
            time_delta_mins=11,
            battery_drain=3 if uses_phone else 1,
            cash_spent=fare,
            requires_phone_or_upi=uses_phone,
            distance_delta_km=hop_km,
            new_location_label=lm.name,
            new_transport_mode="In transit",
            updated_scene_context=f"At {lm.name} ({new_km:.1f} / 38.0 km).",
        )
