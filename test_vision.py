"""
Standalone vision test — encode image → Groq vision → print raw response.
Run: python test_vision.py <path/to/image.jpg>
     python test_vision.py          (uses built-in test pattern if no file given)
"""

import base64
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from groq import Groq

load_dotenv()

MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

SYSTEM_PROMPT = "You are a plant pathologist with expertise in diagnosing plant diseases, pests, and care issues from photographs."

USER_PROMPT = """\
You are a plant pathologist. Given this photo:
1. Identify the species if not provided.
2. Diagnose the primary issue category:
   overwatering / underwatering / light / pest / nutrient / disease / healthy.
3. List visible symptoms.
Return JSON only — no markdown, no explanation:
{"species": "...", "issue_category": "...", "symptoms": ["..."], "confidence": 0.0}"""


def encode_image(path: str) -> tuple[str, str]:
    """Returns (base64_string, mime_type)."""
    ext = Path(path).suffix.lower()
    mime = {".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".png": "image/png", ".webp": "image/webp"}.get(ext, "image/jpeg")
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8"), mime


def build_prompt(species: str | None) -> str:
    if species:
        species_line = f'The plant species is "{species}". Skip identification; focus on diagnosis.'
    else:
        species_line = "Identify the species if possible."
    return f"""\
You are a plant pathologist. Given this photo:
1. {species_line}
2. Diagnose the primary issue category:
   overwatering / underwatering / light / pest / nutrient / disease / healthy.
3. List visible symptoms.
Return JSON only — no markdown, no explanation:
{{"species": "...", "issue_category": "...", "symptoms": ["..."], "confidence": 0.0}}"""


def call_groq_vision(image_path: str, species: str | None = None) -> dict:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY not set in environment / .env")

    client = Groq(api_key=api_key)
    b64, mime = encode_image(image_path)

    print(f"  model   : {MODEL}")
    print(f"  image   : {image_path}  ({Path(image_path).stat().st_size:,} bytes)")
    print(f"  mime    : {mime}")
    print(f"  species : {species or '(not provided — model will guess)'}\n")

    prompt = build_prompt(species)

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{b64}"},
                    },
                    {"type": "text", "text": prompt},
                ],
            },
        ],
        temperature=0.2,
        max_tokens=512,
    )

    return response


def main():
    if len(sys.argv) < 2:
        print("Usage: python test_vision.py <path/to/image.jpg> [species]")
        sys.exit(1)

    image_path = sys.argv[1]
    if not Path(image_path).exists():
        print(f"ERROR: file not found: {image_path}")
        sys.exit(1)

    species = sys.argv[2] if len(sys.argv) > 2 else None

    print("=== Groq Vision Call ===")
    response = call_groq_vision(image_path, species)

    raw_text = response.choices[0].message.content
    print("--- Raw response ---")
    print(raw_text)
    print()

    print("--- Usage ---")
    print(f"  prompt tokens     : {response.usage.prompt_tokens}")
    print(f"  completion tokens : {response.usage.completion_tokens}")
    print(f"  total tokens      : {response.usage.total_tokens}")
    print()

    print("--- Parsed JSON ---")
    try:
        parsed = json.loads(raw_text)
        print(json.dumps(parsed, indent=2))
    except json.JSONDecodeError:
        print("(response is not valid JSON — check the prompt or model output)")


if __name__ == "__main__":
    main()
