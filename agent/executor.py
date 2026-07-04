import re
import sys
import threading
from pathlib import Path
from typing import Callable

from google import genai
from google.genai import types

from agent.planner       import create_plan, replan
from agent.error_handler import analyze_error, generate_fix, ErrorDecision
from agent.tools         import call_tool as _call_tool
from core.persona        import get_client, get_api_key as _get_api_key, VOICE_STYLE


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR        = get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"


_PLACEHOLDER_RE = re.compile(r"\{\{\s*step\s*(\d+)\s*\}\}", re.IGNORECASE)


def _resolve_placeholders(value, step_results: dict):
    """Replace {{stepN}} references anywhere in a param structure with that
    step's result. Walks strings, dicts and lists recursively."""
    if isinstance(value, str):
        def _sub(m):
            n = int(m.group(1))
            res = step_results.get(n, step_results.get(str(n)))
            return str(res) if res is not None else m.group(0)
        return _PLACEHOLDER_RE.sub(_sub, value)
    if isinstance(value, dict):
        return {k: _resolve_placeholders(v, step_results) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_placeholders(v, step_results) for v in value]
    return value


def _inject_context(params: dict, tool: str, step_results: dict, goal: str = "") -> dict:
    if not step_results:
        return params

    params = dict(params)

    if tool == "file_controller" and params.get("action") in ("write", "create_file"):
        content = params.get("content", "")
        if not content or len(content) < 50:
            all_results = [
                v for v in step_results.values()
                if v and len(v) > 100 and v not in ("Done.", "Completed.")
            ]
            if all_results:
                combined = "\n\n---\n\n".join(all_results)
                translated = _translate_to_goal_language(combined, goal)
                params["content"] = translated
                print(f"[Executor] 💉 Injected + translated content")

    return params


def _detect_language(text: str) -> str:
    client = get_client()
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=(
                f"What language is this text written in? "
                f"Reply with ONLY the language name in English (e.g. Turkish, English, French).\n\n"
                f"Text: {text[:200]}"
            ),
        )
        return response.text.strip()
    except Exception:
        return "English"


def _translate_to_goal_language(content: str, goal: str) -> str:
    if not goal:
        return content
    try:
        client = get_client()
        target_lang = _detect_language(goal)
        print(f"[Executor] 🌐 Translating to: {target_lang}")

        prompt = (
            f"You are a professional translator. "
            f"Translate the following text into {target_lang}.\n"
            f"IMPORTANT:\n"
            f"- Translate EVERYTHING, leave nothing in English\n"
            f"- Keep all facts, numbers, and data intact\n"
            f"- Keep the structure and formatting\n"
            f"- Output ONLY the translated text, nothing else\n\n"
            f"Text to translate:\n{content[:4000]}"
        )
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        translated = response.text.strip()
        print(f"[Executor] ✅ Translation done ({target_lang})")
        return translated
    except Exception as e:
        print(f"[Executor] ⚠️ Translation failed: {e}")
        return content


class AgentExecutor:

    MAX_REPLAN_ATTEMPTS = 2

    def execute(
        self,
        goal:        str,
        speak:       Callable | None        = None,
        cancel_flag: threading.Event | None = None,
    ) -> str:
        """Run a goal to completion.

        Claude is the primary engine — a real agentic tool-use loop that sees
        each tool's actual result before deciding the next step (see
        agent/claude_agent.py). If no Anthropic key is configured, or the very
        first call to Claude fails (before any tool with side effects has
        run), this transparently falls back to the original Gemini
        plan-then-execute engine below so Moses keeps working either way.
        """
        try:
            from agent.claude_agent import run as claude_run, is_configured, ClaudeUnavailableError
        except ImportError as e:
            print(f"[Executor] ⚠️ anthropic SDK not installed ({e}) — using legacy planner")
        else:
            if is_configured():
                try:
                    return claude_run(goal, speak=speak, cancel_flag=cancel_flag)
                except ClaudeUnavailableError as e:
                    print(f"[Executor] ⚠️ Claude unavailable ({e}) — falling back to legacy planner")

        return self._execute_legacy(goal, speak=speak, cancel_flag=cancel_flag)

    def _execute_legacy(
        self,
        goal:        str,
        speak:       Callable | None        = None,
        cancel_flag: threading.Event | None = None,
    ) -> str:
        print(f"\n[Executor] 🎯 Goal (legacy planner): {goal}")

        replan_attempts = 0
        completed_steps = []
        step_results    = {}
        plan            = create_plan(goal)

        while True:
            steps = plan.get("steps", [])

            if not steps:
                msg = "I couldn't map out a way to do that one."
                if speak: speak(msg)
                return msg

            success      = True
            failed_step  = None
            failed_error = ""

            for step in steps:
                if cancel_flag and cancel_flag.is_set():
                    if speak: speak("Cancelled that one.")
                    return "Task cancelled."

                step_num = step.get("step", "?")
                tool     = step.get("tool", "generated_code")
                desc     = step.get("description", "")
                params   = step.get("parameters", {})

                params = _resolve_placeholders(params, step_results)
                params = _inject_context(params, tool, step_results, goal=goal)

                print(f"\n[Executor] ▶️ Step {step_num}: [{tool}] {desc}")

                attempt = 1
                step_ok = False

                while attempt <= 3:
                    if cancel_flag and cancel_flag.is_set():
                        break
                    try:
                        result = _call_tool(tool, params, speak)
                        step_results[step_num] = result
                        completed_steps.append(step)
                        print(f"[Executor] ✅ Step {step_num} done: {str(result)[:100]}")
                        step_ok = True
                        break

                    except Exception as e:
                        error_msg = str(e)
                        print(f"[Executor] ❌ Step {step_num} attempt {attempt} failed: {error_msg}")

                        recovery = analyze_error(step, error_msg, attempt=attempt)
                        decision = recovery["decision"]
                        user_msg = recovery.get("user_message", "")

                        if speak and user_msg:
                            speak(user_msg)

                        if decision == ErrorDecision.RETRY:
                            attempt += 1
                            import time; time.sleep(2)
                            continue

                        elif decision == ErrorDecision.SKIP:
                            print(f"[Executor] ⏭️ Skipping step {step_num}")
                            completed_steps.append(step)
                            step_ok = True
                            break

                        elif decision == ErrorDecision.ABORT:
                            msg = f"Had to stop on this one. {recovery.get('reason', '')}".strip()
                            if speak: speak(msg)
                            return msg

                        else:
                            fix_suggestion = recovery.get("fix_suggestion", "")
                            if fix_suggestion and tool != "generated_code":
                                try:
                                    fixed_step = generate_fix(step, error_msg, fix_suggestion)
                                    if speak: speak("Let me try this another way.")
                                    res = _call_tool(
                                        fixed_step["tool"],
                                        fixed_step["parameters"],
                                        speak
                                    )
                                    step_results[step_num] = res
                                    completed_steps.append(step)
                                    step_ok = True
                                    break
                                except Exception as fix_err:
                                    print(f"[Executor] ⚠️ Fix failed: {fix_err}")

                            failed_step  = step
                            failed_error = error_msg
                            success      = False
                            break

                if not step_ok and not failed_step:
                    failed_step  = step
                    failed_error = "Max retries exceeded"
                    success      = False

                if not success:
                    break

            if success:
                return self._summarize(goal, completed_steps, speak)

            if replan_attempts >= self.MAX_REPLAN_ATTEMPTS:
                msg = "I couldn't get that one across the line, even after switching it up."
                if speak: speak(msg)
                return msg

            if speak: speak("Let me switch up my approach.")

            replan_attempts += 1
            plan = replan(goal, completed_steps, failed_step, failed_error)

    def _summarize(self, goal: str, completed_steps: list, speak: Callable | None) -> str:
        fallback = f"Handled it — {len(completed_steps)} steps done for: {goal[:60]}."
        try:
            client    = get_client()
            steps_str = "\n".join(f"- {s.get('description', '')}" for s in completed_steps)
            prompt    = (
                f'User goal: "{goal}"\n'
                f"Completed steps:\n{steps_str}\n\n"
                "Write a single natural sentence telling the user what got done.\n"
                f"{VOICE_STYLE}"
            )
            response = client.models.generate_content(
                model="gemini-2.5-flash-lite",
                contents=prompt,
            )
            summary  = response.text.strip()
            self._remember(goal, summary)
            if speak: speak(summary)
            return summary
        except Exception:
            if speak: speak(fallback)
            return fallback

    @staticmethod
    def _remember(goal: str, summary: str) -> None:
        try:
            from memory.memory_manager import record_episode
            record_episode(f"Completed a task: {goal[:120]} — {summary[:200]}")
        except Exception as e:
            print(f"[Executor] ⚠️ Could not record episode: {e}")
