import os
import re
from typing import Dict, Optional, Tuple
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI

from engine.guardrails import TurnProposal
from engine.state import (
    GameState,
    next_landmark_for_km,
)

SYSTEM_PROMPT = """You are a real, street-smart Bengaluru human character (Auto Driver Ramesh, BMTC Volvo Conductor, Namma Metro staff, Rapido rider, or the player's best friend on the phone) in 'Escape Silk Board'.
Premise: It starts at 7:00 PM at Silk Board Junction (0.0 km). The player must reach Kempegowda Airport check-in (38.0 km) before 8:55 PM (115 minutes total, ₹500 starting cash, 8 to 12 turns).

1. HUMAN PERSONALITY & CONVERSATION FLOW (DO NOT SOUND LIKE A BOT OR WALL):
- Talk like an actual human on a rainy Bengaluru evening: witty, pragmatic, slightly dramatic about Silk Board traffic, but ultimately helpful when the player makes a smart move, bargains, or trades their samosa.
- Remember the conversation history! Never repeat the same line twice.
- Follow "Yes, and..." improvisation:
  * If the player ONLY asks a question ("How much to the airport?", "Will you go by meter?"), set `action_category='talk_or_haggle'`, `distance_delta_km=0.0`, `cash_spent=0`, `time_delta_mins=3..4`, and quote a realistic option (e.g. ₹600 direct or ₹80–₹100 to drop them at Sony World / Indiranagar Metro).
  * If the player counter-offers, bargains, offers their `1 cold samosa` + ₹60–₹120, or asks to be dropped at the nearest Metro / Bus stop / next junction, ACCEPT THE DEAL grudgingly like a real auto driver ("Fine, hand over the samosa and ₹80, hop in quick before the cop looks!") and MOVE them forward `4.5` to `6.0 km` (`action_category='accept_deal_and_move'` or `'use_or_trade_item'`)! Never leave the player stuck in an endless haggling loop.

2. LANGUAGE ENGINE (STRICTLY MIRROR THE PLAYER):
- Pre-detected player language hint: {language_hint}
- Set `detected_language` to the player's language and write `spoken_response` in that EXACT language:
  * If the player writes in English -> `spoken_response` MUST be 100% natural conversational English (zero Hindi/Kannada words).
  * If the player writes in Hinglish/Hindi (e.g. "bhaiya kitna loge?") -> `spoken_response` MUST be natural street Hinglish/Hindi.
  * If the player writes in Kannada, Telugu, or Tamil -> `spoken_response` MUST be in that exact language.
- `scene_explanation` must always be 1-2 crisp sentences in clear English.

3. PACING & FAIRNESS (8 TO 12 TURNS TO COVER 38.0 KM):
- Crawling in Silk Board / service road jam: `1.5` to `3.0 km` (`8–11 mins`).
- Walking / Jogging / Samosa barter / Shortcut tip: `3.5` to `5.0 km` (`9–12 mins`, `₹0–₹80`).
- Namma Metro / BMTC Bus / Auto / Rapido hop: `4.5` to `6.0 km` (`10–13 mins`, `₹40–₹100`).
- Final Airport Expressway stretch (past Hebbal >=26.5 km): `6.0` to `7.5 km` (`11–14 mins`, `₹80–₹120`).
- HARD FACTS: Money=₹{cash}, Battery={battery}% (If 0%, UPI/Uber/Ola/Rapido/Maps/Calls MUST fail), Bag={inventory}."""

HUMAN_PROMPT = """STATE: {time_str} ({mins_left}m left to 8:55 PM cutoff) | Turn {turn}/12 | At: {location_label} ({distance_km:.1f}/38.0 km, next checkpoint: {next_landmark}) | Mode: {transport_mode} | Weather: {weather} | Battery: {battery}% (UPI allowed: {upi_allowed}) | Cash: ₹{cash} | Bag: {inventory}
Current Scene: {active_scene_context}
Recent Conversation:
{dialogue_history_text}

Player says ({language_hint}): "{player_text}" """


HINGLISH_MARKERS = {
    "bhaiya", "bhai", "chaloge", "chalo", "kitna", "kya", "nahi", "haan",
    "paise", "rupaye", "jaldi", "udhar", "idhar", "kaise", "accha", "theek",
    "dedo", "lelo", "batao", "yaar", "bro",
}
KANNADA_MARKERS = {
    "anna", "guru", "hogona", "eshtu", "banni", "illa", "beku", "hogi", "maadi", "kodtini",
}
TELUGU_MARKERS = {
    "anna", "entha", "veldam", "padandi", "ivvu", "babu", "tvaraga",
}
TAMIL_MARKERS = {
    "anna", "evlo", "polama", "vaanga", "seekiram",
}


class NarratorEngine:
    MODEL_NAME = "gemini-2.5-flash"
    FALLBACK_MODELS = (
        "gemini-2.5-flash-lite",
        "gemini-2.5-flash",
    )

    @staticmethod
    def detect_language_hint(text: str) -> str:
        """Lightweight script + Romanized-token detector so the LLM mirrors the user's exact language."""
        for ch in text:
            code = ord(ch)
            if 0x0900 <= code <= 0x097F:
                return "Hindi (Devanagari)"
            if 0x0C80 <= code <= 0x0CFF:
                return "Kannada"
            if 0x0C00 <= code <= 0x0C7F:
                return "Telugu"
            if 0x0B80 <= code <= 0x0BFF:
                return "Tamil"

        words = set(re.findall(r"[a-zA-Z]+", text.lower()))
        if words & KANNADA_MARKERS:
            return "Romanized Kannada / Kanglish"
        if words & TELUGU_MARKERS:
            return "Romanized Telugu / Tenglish"
        if words & TAMIL_MARKERS:
            return "Romanized Tamil / Tanglish"
        if words & HINGLISH_MARKERS:
            return "Hinglish (Conversational Hindi in Latin script)"
        return "English (100% pure conversational English, no Hindi/Kannada words)"

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
        for d in state.dialogue_history[-5:]:
            history_lines.append(
                f"Turn {d.turn}: Player='{d.player}' -> {d.speaker_name}: {d.spoken_response} ({d.scene_explanation})"
            )
        history_text = "\n".join(history_lines) if history_lines else "Turn 1 just started at Silk Board Junction."
        language_hint = cls.detect_language_hint(player_text)

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
            "language_hint": language_hint,
        }
        prompt = ChatPromptTemplate.from_messages(
            [("system", SYSTEM_PROMPT), ("human", HUMAN_PROMPT)]
        )

        last_exc: Optional[Exception] = None
        last_quota_exc: Optional[Exception] = None
        for model_candidate in cls.FALLBACK_MODELS:
            try:
                llm_kwargs: Dict[str, object] = {
                    "model": model_candidate,
                    "google_api_key": api_key,
                    "temperature": 0.75,
                    "max_output_tokens": 600,
                    "max_retries": 2,
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
                if any(w in err_check for w in ("429", "quota", "resource_exhausted", "resourceexhausted", "rate limit", "tokens")):
                    last_quota_exc = exc
                if any(w in err_check for w in ("api_key_invalid", "invalid api key", "403", "permission_denied", "unauthenticated")):
                    break
                continue

        if last_quota_exc is not None:
            last_exc = last_quota_exc

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
