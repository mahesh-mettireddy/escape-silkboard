import os
from typing import Dict, Optional, Tuple
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI

from engine.guardrails import TurnProposal
from engine.state import (
    GameState,
    next_landmark_for_km,
)

SYSTEM_PROMPT = """You are the witty, deadpan Game Master of 'Escape Silk Board' (Bengaluru traffic survival).
Goal: Reach Kempegowda Airport check-in (38.0 km) from Silk Board (0.0 km) between 7:00 PM and 8:55 PM (115 mins budget, ₹500 total budget, 8 to 12 turns).

LANGUAGE RULE (STRICT):
- Detect the language of `Player:` and write `spoken_response` in that EXACT SAME language:
  * If `Player:` is in English -> `spoken_response` MUST be 100% in English (NO Hindi, NO Kannada words).
  * If `Player:` is in Hindi/Hinglish -> `spoken_response` MUST be in Hindi/Hinglish.
  * If `Player:` is in Kannada/Telugu/Tamil -> `spoken_response` MUST match that language.
- `scene_explanation` must always be in clear English.

TWO-PART OUTPUT:
- `speaker_name`: Who is speaking (e.g. "Auto Driver (Ramesh)", "BMTC Conductor", "Metro Staff", "Co-Passenger", "Friend on Call").
- `spoken_response` (MAIN): Direct spoken reply in quotes (1-2 punchy sentences matching the player's language).
- `scene_explanation` (SUBTEXT): 1-2 short English sentences of physical consequence & current situation.

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
    FALLBACK_MODELS = (
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-2.0-flash",
    )

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
    ) -> Tuple[Optional[TurnProposal], Dict[str, object]]:
        api_key, key_source = cls.resolve_api_key(api_key_override)

        if not api_key:
            return None, {
                "model_used": "none",
                "key_source": "no_key",
                "api_status": "no_key",
                "status_message": (
                    "No Gemini API key found on the server. Click '🔑 API Key' at the top to plug in your Gemini API key!"
                ),
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
            }

        next_lm = next_landmark_for_km(state.distance_km)
        next_lm_str = f"{next_lm.name} ({next_lm.km}km)" if next_lm else "Airport (38km)"

        history_lines = []
        for d in state.dialogue_history[-3:]:
            history_lines.append(
                f"T{d.turn}: P='{d.player}' -> {d.speaker_name}: {d.spoken_response}"
            )
        history_text = "\n".join(history_lines) if history_lines else "Start at Silk Board."

        prompt_vars = {
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
        prompt = ChatPromptTemplate.from_messages(
            [("system", SYSTEM_PROMPT), ("human", HUMAN_PROMPT)]
        )

        last_exc: Optional[Exception] = None
        for model_candidate in cls.FALLBACK_MODELS:
            try:
                llm_kwargs: Dict[str, object] = {
                    "model": model_candidate,
                    "google_api_key": api_key,
                    "temperature": 0.65,
                    "max_output_tokens": 600,
                    "max_retries": 0,
                }
                if model_candidate.startswith("gemini-2.5"):
                    llm_kwargs["thinking_budget"] = 0

                llm = ChatGoogleGenerativeAI(**llm_kwargs)
                structured_llm = llm.with_structured_output(TurnProposal, include_raw=True)
                chain = prompt | structured_llm
                res_dict = chain.invoke(prompt_vars)

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
                        "model_used": model_candidate,
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
                last_exc = exc
                err_check = str(exc).lower()
                if any(w in err_check for w in ("api_key_invalid", "invalid api key", "403", "permission_denied", "unauthenticated")):
                    break
                continue

        if last_exc is not None:
            exc = last_exc
            err_str = str(exc).lower()
            if (
                key_source == "user_key"
                and (
                    os.environ.get("GEMINI_API_KEY", "").strip()
                    or os.environ.get("GOOGLE_API_KEY", "").strip()
                )
            ):
                return cls.generate_proposal(state, player_text, api_key_override=None)

            if any(w in err_str for w in ("429", "quota", "resource_exhausted", "resourceexhausted", "rate limit", "tokens", "timed out", "timeout")):
                api_status = "quota_exhausted"
                msg = (
                    "The provided Gemini API key is out of free-tier tokens. "
                    "Click '🔑 API Key' at the top to add your own Gemini API key and continue your turn!"
                )
            elif any(w in err_str for w in ("api_key_invalid", "invalid api key", "403", "permission_denied", "unauthenticated")):
                api_status = "invalid_key"
                msg = (
                    "That Gemini API key was rejected by Google. "
                    "Click '🔑 API Key' at the top to check or replace it!"
                )
            else:
                api_status = "api_error"
                msg = f"Gemini API error ({type(exc).__name__}). Please try your move again or check your API key."

            return None, {
                "model_used": "none",
                "key_source": key_source,
                "api_status": api_status,
                "status_message": msg,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
            }

        return None, {
            "model_used": "none",
            "key_source": key_source,
            "api_status": "api_error",
            "status_message": "Gemini returned an empty response. Please try your move again.",
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        }
