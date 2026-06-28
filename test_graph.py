"""
End-to-end pause/resume test for the plant-doctor LangGraph agent.

Usage:
    python test_graph.py <image_path> [species]

What happens:
    1. Graph runs: identify → diagnose → ask_clarifying_questions
    2. Graph pauses at interrupt() and prints the questions
    3. Script reads your answers from stdin
    4. Graph resumes: prescribe_care_plan → END
    5. Final care plan is printed
"""

import json
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, str(Path(__file__).parent / "agent"))
from graph import plant_graph, PlantAgentState   # noqa: E402
from langgraph.types import Command              # noqa: E402


def run(image_path: str, species: str = "") -> None:
    if not Path(image_path).exists():
        print(f"ERROR: file not found — {image_path}")
        sys.exit(1)

    thread_id = str(uuid.uuid4())
    config    = {"configurable": {"thread_id": thread_id}}

    initial: PlantAgentState = {
        "plant_id":             "",
        "species":              species,
        "image_path":           image_path,
        "diagnosis":            {},
        "clarifying_questions": [],
        "user_answers":         "",
        "care_plan":            "",
        "phase":                "identify",
    }

    print(f"\n{'='*60}")
    print(f"  Image   : {image_path}")
    print(f"  Species : {species or '(model will identify)'}")
    print(f"  Thread  : {thread_id}")
    print(f"{'='*60}\n")

    # ── RUN 1: identify → diagnose → ask_clarifying_questions (pauses) ────────
    print("--- Phase 1: identify + diagnose + generate questions ---\n")
    result = plant_graph.invoke(initial, config=config)

    # When interrupted, invoke() returns the state at the interruption point
    interrupts = result.get("__interrupt__", [])
    if not interrupts:
        # No interrupt hit — graph ran fully (shouldn't happen in normal flow)
        _print_final(result)
        return

    interrupt_value = interrupts[0].value
    questions: list[str] = interrupt_value.get("questions", [])

    print("\n--- PAUSED — Clarifying Questions ---")
    for i, q in enumerate(questions, 1):
        print(f"  {i}. {q}")

    print("\nType your answers (one block of text, press Enter twice when done):")
    lines = []
    while True:
        line = input()
        if line == "" and lines and lines[-1] == "":
            break
        lines.append(line)
    user_answers = "\n".join(lines).strip()

    # ── RUN 2: resume → prescribe_care_plan → END ─────────────────────────────
    print("\n--- Phase 2: resuming → prescribe care plan ---\n")
    final = plant_graph.invoke(Command(resume=user_answers), config=config)

    _print_final(final)


def _print_final(state: dict) -> None:
    print(f"\n{'='*60}")
    print("  FINAL STATE")
    print(f"{'='*60}")
    print(f"  phase   : {state.get('phase')}")
    print(f"  species : {state.get('species')}")
    print(f"\n  diagnosis:")
    print(json.dumps(state.get("diagnosis", {}), indent=4))
    print(f"\n  clarifying questions:")
    for q in state.get("clarifying_questions", []):
        print(f"    - {q}")
    print(f"\n  user answers:\n    {state.get('user_answers', '').replace(chr(10), chr(10)+'    ')}")
    print(f"\n  care plan:\n")
    print(state.get("care_plan", "(none)"))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)
    run(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "")
