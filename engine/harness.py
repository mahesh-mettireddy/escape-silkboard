from typing import Dict, Optional, Tuple
from engine.guardrails import InputGuardrail, OutputGuardrail, TurnProposal
from engine.narrator import NarratorEngine
from engine.state import GameState


class GameHarness:
    """Deterministic game harness coordinating pre-LLM guardrails, Gemini narration, and post-LLM state enforcement."""

    @staticmethod
    def step(
        state: GameState,
        raw_action: str,
        api_key_override: Optional[str] = None,
    ) -> Tuple[GameState, Dict[str, object]]:
        if state.status != "playing":
            return state, {
                "model_used": "none",
                "tokens_saved": True,
                "api_status": "ok",
                "status_message": None,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
            }

        working_state = state.model_copy(deep=True)

        # Layer 1: Pre-LLM Zero-Token Input Guardrail
        is_valid, cleaned_text, block_reason = InputGuardrail.inspect(raw_action)
        if not is_valid:
            if block_reason == "prompt_injection":
                proposal = TurnProposal(
                    action_category="cheat_or_nonsense",
                    speaker_name="Auto Driver (Ramesh)",
                    spoken_response='"English, Hindi, or Kannada sir—what is this system prompt nonsense? Traffic police is watching, move!"',
                    scene_explanation=f"Your attempt to hack reality fails at {working_state.location_label}. Four minutes slip away in the rain (0 LLM tokens spent).",
                    time_delta_mins=4,
                    battery_drain=0,
                    cash_spent=0,
                    distance_delta_km=0.0,
                )
            elif block_reason == "god_mode_cheat":
                proposal = TurnProposal(
                    action_category="cheat_or_nonsense",
                    speaker_name="Traffic Constable",
                    spoken_response='"Helicopter? Sir, even ambulances can\'t move on this flyover today. Get back on the footpath!"',
                    scene_explanation=f"You stare at the rain clouds above {working_state.location_label} hoping for a miracle. A BMTC bus splashes puddle water on your shoes as 5 minutes pass.",
                    time_delta_mins=5,
                    battery_drain=0,
                    cash_spent=0,
                    distance_delta_km=0.0,
                )
            else:
                proposal = TurnProposal(
                    action_category="cheat_or_nonsense",
                    speaker_name="Auto Driver",
                    spoken_response='"What sir? Speak louder, diesel engine is roaring!"',
                    scene_explanation=f"Your words get drowned out by pressure horns at {working_state.location_label}. Three minutes tick off the clock.",
                    time_delta_mins=3,
                    battery_drain=0,
                    cash_spent=0,
                    distance_delta_km=0.0,
                )

            next_state = OutputGuardrail.enforce(working_state, proposal, cleaned_text or raw_action)
            next_state.last_turn_input_tokens = 0
            next_state.last_turn_output_tokens = 0
            next_state.last_turn_total_tokens = 0
            return next_state, {
                "model_used": "guardrail (0 tokens)",
                "tokens_saved": True,
                "block_reason": block_reason,
                "api_status": "guardrail_zero_token",
                "status_message": None,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
            }

        # Dead-phone fast-fail before calling LLM if battery is already 0% and user attempts UPI/Uber/Ola/Rapido/Calls
        if working_state.battery <= 0 and InputGuardrail.uses_phone_keywords(cleaned_text):
            dead_prop = TurnProposal(
                action_category="phone_call_or_app",
                speaker_name="Auto Driver",
                spoken_response='"Phone switched off, sir? No QR scan, no cab app here. Only cash works now."',
                scene_explanation="Your screen stays pitch-black at 0% battery.",
                time_delta_mins=5,
                battery_drain=0,
                cash_spent=0,
                requires_phone_or_upi=True,
                distance_delta_km=0.0,
            )
            next_state = OutputGuardrail.enforce(working_state, dead_prop, cleaned_text)
            return next_state, {
                "model_used": "guardrail (0 tokens)",
                "tokens_saved": True,
                "block_reason": "dead_phone",
                "api_status": "ok",
                "status_message": None,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
            }

        # Layer 2: LangChain + Gemini Structured Output (pure live API, no hardcoded story fallback)
        proposal, llm_meta = NarratorEngine.generate_proposal(
            working_state, cleaned_text, api_key_override=api_key_override
        )
        if proposal is None:
            # Do NOT advance turn or return fake hardcoded dialogue when API key is missing/exhausted
            return working_state, {
                "model_used": "none",
                "key_source": llm_meta.get("key_source", "unknown"),
                "api_status": llm_meta.get("api_status", "api_error"),
                "status_message": llm_meta.get("status_message"),
                "tokens_saved": False,
                "block_reason": None,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "estimated_cost_usd": working_state.estimated_cost_usd,
            }

        # Layer 3: Post-LLM Deterministic Clamp
        next_state = OutputGuardrail.enforce(working_state, proposal, cleaned_text)

        in_tok = int(llm_meta.get("input_tokens", 0))
        out_tok = int(llm_meta.get("output_tokens", 0))
        tot_tok = int(llm_meta.get("total_tokens", in_tok + out_tok))

        next_state.last_turn_input_tokens = in_tok
        next_state.last_turn_output_tokens = out_tok
        next_state.last_turn_total_tokens = tot_tok
        next_state.total_input_tokens += in_tok
        next_state.total_output_tokens += out_tok
        next_state.total_tokens += tot_tok

        return next_state, {
            "model_used": llm_meta.get("model_used", "gemini-2.5-flash"),
            "key_source": llm_meta.get("key_source", "unknown"),
            "api_status": llm_meta.get("api_status", "ok"),
            "status_message": llm_meta.get("status_message"),
            "tokens_saved": False,
            "block_reason": None,
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "total_tokens": tot_tok,
            "estimated_cost_usd": next_state.estimated_cost_usd,
        }
