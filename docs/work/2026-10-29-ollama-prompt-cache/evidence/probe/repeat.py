"""Send the first prompt three times in a row and record each prefill time.

    python3 repeat.py <prompts.jsonl> <outdir>

Writes `<outdir>/repeat-samples.jsonl`, one line per send: `i`, `prompt_tokens`, `prompt_s`
(`prompt_eval_duration` in seconds). The request body is `run_arm.py`'s, so a repeat that is served
from the slot's context checkpoints shows as a short `prompt_s` while `prompt_tokens` stays the same
(before the fix: 0.05 s against 1.29 s). Run it right after `run_arm.py`, with the LLM still loaded.

citable: no.
"""

import json
import sys
from pathlib import Path

import run_arm


def main():
    prompts_path, outdir = sys.argv[1], sys.argv[2]
    Path(outdir).mkdir(parents=True, exist_ok=True)
    first = json.loads(Path(prompts_path).read_text().splitlines()[0])
    lines = []
    for i in (1, 2, 3):
        body = {
            "model": run_arm.MODEL,
            "prompt": first["prompt"],
            "stream": False,
            "think": False,
            "options": {"num_ctx": 8192},
        }
        r = run_arm.post("/api/generate", body)
        rec = {
            "i": i,
            "prompt_tokens": r.get("prompt_eval_count"),
            "prompt_s": r.get("prompt_eval_duration", 0) / 1e9,
        }
        lines.append(json.dumps(rec))
        print(
            f"[repeat] {i} prompt_tokens={rec['prompt_tokens']} prompt_s={rec['prompt_s']:.3f}"
        )
    (Path(outdir) / "repeat-samples.jsonl").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
