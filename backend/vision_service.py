# OpenAI gpt-4o wrapper for plant image analysis.
# identify() detects the species, diagnose() finds what's wrong.
# Keep them as separate calls — combining them causes the model to bias
# its diagnosis based on its own species guess.

import base64
import io
import json
import os
import re
from pathlib import Path
from typing import TypedDict

from openai import OpenAI
from PIL import Image, ImageFilter

MODEL = "gpt-4o"

VALID_CATEGORIES = {
    "overwatering", "underwatering", "light",
    "pest", "nutrient", "disease", "healthy", "uncertain",
}

_SYSTEM = (
    "You are a plant pathologist. You receive a plant photograph and must return "
    "a single JSON object — no prose, no markdown, no explanation. "
    "Every field is required. Only describe what is literally visible in the image; "
    "never infer conditions you cannot see. If the photo quality or angle makes a "
    "confident call impossible, set issue_category to \"uncertain\"."
)

_SCHEMA_EXAMPLE = json.dumps({
    "species": {"value": "Monstera deliciosa", "confidence": 0.9},
    "distribution_analysis": "Where on the plant are the symptoms located? Are they discrete bordered spots or large diffuse patches? Uniform across the leaf face, or concentrated at tips/margins/one side?",
    "issue_category": "overwatering",
    "visible_symptoms": ["yellowing lower leaves", "mushy stem base"],
    "evidence": "Lower-left leaves show uniform chlorosis; stem base appears dark and water-soaked in the bottom-centre of the frame.",
    "confidence": 0.82,
}, indent=2)

_VALID_CATS = " | ".join(sorted(VALID_CATEGORIES))


class IdentifyResult(TypedDict):
    species:    str
    confidence: float


class DiagnosisResult(TypedDict):
    species:        str
    issue_category: str
    symptoms:       list[str]   # mapped from visible_symptoms
    evidence:       str
    confidence:     float


# species identification prompt

_ID_SYSTEM = (
    "You are a botanist. Look at this plant photograph and identify the species. "
    "Return a single JSON object — no prose, no markdown, no explanation. "
    "If the species cannot be determined, set value to null and confidence to 0."
)

_ID_SCHEMA = json.dumps(
    {"species": {"value": "Monstera deliciosa", "confidence": 0.9}},
    indent=2,
)


# diagnosis prompt and category rules

_CATEGORY_HINTS = """\
Category definitions (use exactly one):
  healthy      — no lesions, discoloration, or deformities; ALL visible leaves are turgid \
and uniformly colored. If the plant looks completely normal, choose healthy.
  light        — large bleached, tan, or papery patches on leaf surfaces WITHOUT defined \
lesion margins; OR etiolated stems stretching toward light. Sunburn on succulents (e.g. Aloe) \
appears as large uniform tan/brown discoloration across the exposed leaf face — choose light, \
NOT disease. Do NOT call "disease" unless discrete, bordered lesion spots are visible.
  overwatering — yellowing lower leaves, limp or translucent leaves, mushy or darkened stem \
base or leaf bases, waterlogged soil, or edema bumps. Leaf limpness or soft mushy tissue \
anywhere (not just the stem) is an overwatering signal.
  underwatering — uniform wilting with dry/crispy tissue throughout the plant; leaves curl \
inward or feel papery. Brown tips alone without overall wilting are NOT underwatering.
  disease      — discrete spots or lesions with clearly defined margins, blight, fungal \
mycelium, cankers, or localized rot clearly distinct from water-stress or sun-damage patterns. \
Do NOT choose disease for (a) large uniform bleached patches without lesion borders → light, \
(b) soft/limp/mushy tissue → overwatering, (c) isolated leaf-tip browning without wilting → nutrient.
  pest         — visible insects, webbing, sticky honeydew, stippling, or chewing damage.
  nutrient     — interveinal chlorosis (veins stay green, tissue between yellows); OR \
brown/necrotic leaf tips that are the ONLY symptom (no spots, no lesions, no wilting elsewhere \
on the plant — if any discrete spots or lesions exist on the same leaf, choose disease instead); \
OR purple undersides on otherwise fully normal leaves. \
Only use nutrient when the rest of the plant looks healthy and turgid.
  uncertain    — image quality, angle, or symptom pattern does not support a confident call.

Disambiguation rules — apply these BEFORE finalizing your category:
  • Brown leaf tips as the ONLY symptom + rest of plant turgid + no lesions anywhere → nutrient
  • Brown tips AND discrete spots/lesions elsewhere on the leaf → disease (NOT nutrient)
  • Large tan/bleached patches without lesion borders → light (NOT disease)
  • Limp or mushy leaves/bases even without stem rot → overwatering (NOT disease)
  • Spots with clear defined margins or mycelium present → disease (NOT overwatering or nutrient)\
"""


def _build_prompt(known_species: str | None) -> str:
    species_instruction = (
        f'Species is known: "{known_species}". Do not re-identify; focus on diagnosis.'
        if known_species
        else (
            'Identify the species. If you cannot determine it from the photo, '
            'set species.value to null and species.confidence to 0.'
        )
    )
    return (
        f"Task:\n"
        f"1. {species_instruction}\n"
        f"2. Fill distribution_analysis: describe WHERE symptoms appear (which leaves, "
        f"which regions), whether damage is discrete bordered spots or large diffuse patches, "
        f"and whether it is concentrated at tips/margins/one side or uniform across the leaf face.\n"
        f"3. Using your distribution_analysis, choose issue_category — exactly one of: {_VALID_CATS}\n\n"
        f"{_CATEGORY_HINTS}\n\n"
        f"4. List only visible_symptoms you can literally see in the pixels.\n"
        f"   Do not infer symptoms that are not visible.\n"
        f"5. In evidence, name the specific region or pixels that support your call\n"
        f"   (e.g. 'yellowing on lower-left leaf edges', 'white webbing on stem').\n"
        f"6. Set confidence (0.0–1.0) for your issue_category call.\n\n"
        f"Return exactly this JSON schema — no other text:\n"
        f"{_SCHEMA_EXAMPLE}"
    )


# parse and validate the model response

def _extract_json(raw: str) -> dict:
    """Parse JSON; strip accidental fences as a fallback."""
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            return json.loads(m.group())
        raise ValueError(f"No JSON found in model output:\n{raw!r}")


def _parse_float(val, default: float = 0.0) -> float:
    try:
        return round(max(0.0, min(1.0, float(val))), 3)
    except (TypeError, ValueError):
        return default


def _validate(data: dict) -> DiagnosisResult:
    # species — now a nested object
    species_obj = data.get("species") or {}
    if isinstance(species_obj, dict):
        species = str(species_obj.get("value") or "Unknown").strip() or "Unknown"
    else:
        species = str(species_obj).strip() or "Unknown"

    # issue_category — closed enum; anything outside → "uncertain"
    raw_cat = str(data.get("issue_category", "")).lower().strip()
    issue_category = raw_cat if raw_cat in VALID_CATEGORIES else "uncertain"

    # visible_symptoms — only what is literally in the frame
    raw_symptoms = data.get("visible_symptoms") or data.get("symptoms", [])
    symptoms = (
        [str(s).strip() for s in raw_symptoms if str(s).strip()]
        if isinstance(raw_symptoms, list)
        else [str(raw_symptoms).strip()]
    )
    if not symptoms:
        symptoms = ["no visible symptoms described"]

    # evidence — pixel-level reasoning anchor
    evidence = str(data.get("evidence") or "").strip()

    confidence = _parse_float(data.get("confidence", 0.0))

    return DiagnosisResult(
        species=species,
        issue_category=issue_category,
        symptoms=symptoms,
        evidence=evidence,
        confidence=confidence,
    )


# image preprocessing and base64 encoding

def _preprocess(img: Image.Image) -> Image.Image:
    # Crop out the border edges (pots, floor) and sharpen leaf detail before sending to the model.
    w, h = img.size
    margin_x = int(w * 0.075)
    margin_y = int(h * 0.075)
    img = img.crop((margin_x, margin_y, w - margin_x, h - margin_y))
    img = img.filter(ImageFilter.UnsharpMask(radius=1, percent=60, threshold=3))
    return img


def _encode(path: str) -> tuple[str, str]:
    img = Image.open(path).convert("RGB")
    img = _preprocess(img)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return base64.b64encode(buf.getvalue()).decode(), "image/jpeg"


# public functions

def identify(image_path: str) -> IdentifyResult:
    # Returns species name and confidence. Run this before diagnose() so the
    # diagnosis prompt already knows the species instead of guessing it.
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set in environment / .env")

    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    b64, mime = _encode(str(path))
    client = OpenAI(api_key=api_key)

    response = client.chat.completions.create(
        model=MODEL,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": _ID_SYSTEM},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                    {"type": "text", "text": f"Identify the plant species.\n\nReturn exactly this JSON schema — no other text:\n{_ID_SCHEMA}"},
                ],
            },
        ],
        temperature=0.2,
        max_tokens=150,
    )

    raw  = response.choices[0].message.content
    data = _extract_json(raw)

    species_obj = data.get("species") or {}
    if isinstance(species_obj, dict):
        species    = str(species_obj.get("value") or "Unknown").strip() or "Unknown"
        confidence = _parse_float(species_obj.get("confidence", 0.0))
    else:
        species    = str(species_obj).strip() or "Unknown"
        confidence = 0.0

    return IdentifyResult(species=species, confidence=confidence)


def diagnose(image_path: str, known_species: str | None = None) -> DiagnosisResult:
    # Sends the image to gpt-4o and returns issue category, symptoms, and confidence.
    # Pass known_species if you already ran identify() — otherwise the model guesses it.
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set in environment / .env")

    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    b64, mime = _encode(str(path))
    client = OpenAI(api_key=api_key)

    response = client.chat.completions.create(
        model=MODEL,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": _SYSTEM},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                    {"type": "text", "text": _build_prompt(known_species)},
                ],
            },
        ],
        temperature=0.2,
        max_tokens=600,
    )

    raw = response.choices[0].message.content
    data = _extract_json(raw)
    return _validate(data)
