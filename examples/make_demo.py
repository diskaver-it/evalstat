"""Writes demo_run.json: a promptfoo-shaped eval of 50 cases with a tempting result.

The headline is 62% against 68%, the kind of six-point jump that gets a prompt
merged. The pairing underneath it is 7 cases fixed, 4 cases broken, 39 unchanged,
which is a coin flip. Run this, then run evalstat on the output.
"""

import json
import os

CASES = [("both_pass", 27), ("candidate_fixed", 7), ("candidate_broke", 4), ("both_fail", 12)]


def rows():
    out = []
    test_idx = 0
    for kind, count in CASES:
        for _ in range(count):
            baseline = kind in ("both_pass", "candidate_broke")
            candidate = kind in ("both_pass", "candidate_fixed")
            for prompt_idx, passed in ((0, baseline), (1, candidate)):
                out.append(
                    {
                        "promptIdx": prompt_idx,
                        "testIdx": test_idx,
                        "promptId": "p%d" % prompt_idx,
                        "vars": {"question": "q%03d" % test_idx},
                        "success": passed,
                        "score": 1.0 if passed else 0.0,
                        "namedScores": {},
                        "latencyMs": 420,
                        "provider": {"id": "openai:gpt-demo", "label": "openai:gpt-demo"},
                        "prompt": {"raw": "prompt %d" % prompt_idx},
                    }
                )
            test_idx += 1
    return out


def main():
    doc = {
        "evalId": "demo",
        "results": {
            "version": 3,
            "timestamp": "2026-11-12T00:00:00Z",
            "results": rows(),
            "prompts": [{"label": "baseline prompt"}, {"label": "new prompt"}],
            "stats": {},
        },
        "config": {},
        "shareableUrl": None,
    }
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "demo_run.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1)
    print("wrote %s (%d rows)" % (path, len(doc["results"]["results"])))


if __name__ == "__main__":
    main()
