"""Unified LLM helper with retries, timeout, and JSON output."""
import json
import os
import time
from pathlib import Path

TIMEOUT = 30
MAX_RETRIES = 2


def _load_dotenv():
    for p in [Path(__file__).parent / ".env", Path.cwd() / ".env"]:
        if p.exists():
            for line in p.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv()


def _require_env(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        raise RuntimeError(f"Missing required env var: {name}. Set AGENT_MODEL and JUDGE_MODEL.")
    return val


def _get_client(model: str):
    use_openai = model.startswith("gpt-") or model.startswith("o1") or model.startswith("o3")
    if use_openai and os.environ.get("OPENAI_API_KEY"):
        import openai
        return "openai", openai.OpenAI()
    if os.environ.get("ANTHROPIC_API_KEY"):
        import anthropic
        return "anthropic", anthropic.Anthropic()
    if os.environ.get("OPENAI_API_KEY"):
        import openai
        return "openai", openai.OpenAI()
    raise RuntimeError("Set ANTHROPIC_API_KEY or OPENAI_API_KEY.")


def call_llm(messages: list[dict], model: str | None = None, json_mode: bool = True) -> str:
    model = model or _require_env("AGENT_MODEL")
    provider, client = _get_client(model)
    last_err = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            if provider == "anthropic":
                sys = [m["content"] for m in messages if m["role"] == "system"]
                chat = [m for m in messages if m["role"] != "system"]
                kwargs = {"model": model, "max_tokens": 4096, "messages": chat, "timeout": TIMEOUT}
                if sys:
                    suffix = "\nRespond with valid JSON only." if json_mode else ""
                    kwargs["system"] = sys[0] + suffix
                resp = client.messages.create(**kwargs)
                return resp.content[0].text
            sys = [m["content"] for m in messages if m["role"] == "system"]
            chat = [m for m in messages if m["role"] != "system"]
            msgs = ([{"role": "system", "content": sys[0]}] + chat) if sys else chat
            kwargs = {"model": model, "messages": msgs, "timeout": TIMEOUT}
            if not (model.startswith("gpt-5") or model.startswith("o1") or model.startswith("o3")):
                kwargs["temperature"] = 0
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}
            resp = client.chat.completions.create(**kwargs)
            return resp.choices[0].message.content
        except Exception as e:
            last_err = e
            if attempt < MAX_RETRIES:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"LLM call failed after {MAX_RETRIES + 1} attempts: {last_err}")


def parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    return json.loads(text)
