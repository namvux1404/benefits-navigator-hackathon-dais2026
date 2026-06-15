from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import CLAUDE_MODEL  # noqa: E402


def main() -> int:
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        print("Claude smoke test: failure")
        print(f"Model: {CLAUDE_MODEL}")
        print("Reason: ANTHROPIC_API_KEY is not set")
        return 1

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=20,
            messages=[{"role": "user", "content": "Reply with exactly: ok"}],
        )
        text = "".join(
            block.text for block in response.content if getattr(block, "type", "") == "text"
        ).strip()
        if not text:
            raise RuntimeError("empty Claude response")
    except Exception as exc:
        print("Claude smoke test: failure")
        print(f"Model: {CLAUDE_MODEL}")
        print(f"Reason: {type(exc).__name__}")
        return 1

    print("Claude smoke test: success")
    print(f"Model: {CLAUDE_MODEL}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
