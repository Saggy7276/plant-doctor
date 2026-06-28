"""
eval_llm.py — Ground-truth evaluation of identify() and diagnose().

Three tests:
  1. species   — identify() vs data/species/ folder labels
  2. disease   — diagnose(oracle species) vs data/disease/ folder labels
  3. pipeline  — identify() → diagnose(predicted species) vs data/disease/ labels
                 (measures how species-ID errors cascade into diagnosis errors)

Usage:
    python eval_llm.py                          # run all three tests, 5 images/class
    python eval_llm.py --mode species           # only species test
    python eval_llm.py --mode disease           # only oracle disease test
    python eval_llm.py --mode pipeline          # only full-pipeline test
    python eval_llm.py --samples 3             # 3 images per class instead of 5
    python eval_llm.py --out my_results/       # custom output directory

Results are written to CSV files in --out (default: eval_results/).
"""

import argparse
import csv
import os
import random
import sys
import time
from collections import defaultdict
from pathlib import Path

# ── path setup ─────────────────────────────────────────────────────────────────

ROOT_DIR    = Path(__file__).parent
BACKEND_DIR = ROOT_DIR / "backend"
for _p in (str(BACKEND_DIR),):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Load .env before importing vision_service (needs OPENAI_API_KEY)
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT_DIR / ".env")
except ImportError:
    pass  # rely on env var already being set

from vision_service import identify, diagnose  # noqa: E402

# ── config ─────────────────────────────────────────────────────────────────────

DATA_DIR    = ROOT_DIR / "data"
SPECIES_DIR = DATA_DIR / "species"
DISEASE_DIR = DATA_DIR / "disease"

DEFAULT_SAMPLES = 5
RANDOM_SEED     = 42
API_DELAY       = 1.5   # seconds between API calls (avoid rate-limit 429s)

# ── ground truth tables ────────────────────────────────────────────────────────

# Maps folder name → (oracle_species_string, valid_issue_category)
# issue_category must be one of: overwatering | underwatering | light |
#   pest | nutrient | disease | healthy | uncertain
DISEASE_CLASS_GT: dict[str, tuple[str, str]] = {
    "Aloe_Anthracnose":                   ("Aloe vera",    "disease"),
    "Aloe_Healthy":                       ("Aloe vera",    "healthy"),
    "Aloe_LeafSpot":                      ("Aloe vera",    "disease"),
    "Aloe_Rust":                          ("Aloe vera",    "disease"),
    "Aloe_Sunburn":                       ("Aloe vera",    "light"),
    "Cactus_Dactylopius_Opuntia":         ("Cactus",       "pest"),
    "Cactus_Healthy":                     ("Cactus",       "healthy"),
    # Wilt symptoms are visually indistinguishable from overwatering (wilting, drooping).
    "Money_Plant_Bacterial_wilt_disease": ("Money Plant",  "overwatering"),
    "Money_Plant_Healthy":                ("Money Plant",  "healthy"),
    "Money_Plant_Manganese_Toxicity":     ("Money Plant",  "nutrient"),
    "Snake_Plant_Anthracnose":            ("Snake Plant",  "disease"),
    "Snake_Plant_Healthy":                ("Snake Plant",  "healthy"),
    # Withering is visually caused by overwatering OR underwatering — not a discrete disease symptom.
    "Snake_Plant_Leaf_Withering":         ("Snake Plant",  "overwatering"),
    "Spider_Plant_Fungal_leaf_spot":      ("Spider Plant", "disease"),
    "Spider_Plant_Healthy":               ("Spider Plant", "healthy"),
    "Spider_Plant_Leaf_Tip_Necrosis":     ("Spider Plant", "nutrient"),
}

# Maps folder name → accepted lowercase substrings in the model's species prediction.
# The model passes if ANY alias is a substring of normalize(predicted).
SPECIES_ALIASES: dict[str, list[str]] = {
    "Alovera": [
        "aloe vera", "aloe", "aloe barbadensis", "alovera",
    ],
    "Begonia (Begonia spp.)": [
        "begonia",
    ],
    "Orchid": [
        "orchid", "phalaenopsis", "dendrobium", "cattleya", "orchidaceae",
    ],
    "Prayer Plant (Maranta leuconeura)": [
        "prayer plant", "maranta", "leuconeura",
    ],
    "Rattlesnake Plant (Calathea lancifolia)": [
        "rattlesnake plant", "calathea", "lancifolia", "goeppertia",
    ],
    "Rubber Plant (Ficus elastica)": [
        "rubber plant", "ficus", "elastica", "rubber fig", "rubber tree",
    ],
    "Sago Palm (Cycas revoluta)": [
        "sago palm", "sago", "cycas", "revoluta",
    ],
    "Schefflera": [
        "schefflera", "umbrella plant", "umbrella tree",
    ],
    "Snake plant (Sanseviera)": [
        "snake plant", "sansevieria", "sanseviera", "dracaena trifasciata",
        "mother-in-law",
    ],
    "Tulip": [
        "tulip", "tulipa",
    ],
}


# ── helpers ────────────────────────────────────────────────────────────────────

def sample_images(folder: Path, n: int, seed: int = RANDOM_SEED) -> list[Path]:
    """
    Return up to n non-augmented images from folder.
    Skips files whose names start with "Augmented_" (CNN training artifacts, not real photos).
    Prefers JPG/JPEG; falls back to PNG to fill the quota if needed.
    """
    def _collect(exts: list[str]) -> list[Path]:
        found: list[Path] = []
        seen: set[str] = set()
        for ext in exts:
            for p in sorted(folder.glob(f"*{ext}")):
                if p.name.lower().startswith("augmented_"):
                    continue
                key = p.name.lower()
                if key not in seen:
                    seen.add(key)
                    found.append(p)
        return found

    jpgs = _collect([".jpg", ".jpeg", ".JPG", ".JPEG"])
    rng  = random.Random(seed)

    if len(jpgs) >= n:
        return rng.sample(jpgs, n)

    pngs  = _collect([".png", ".PNG"])
    pool  = jpgs + [p for p in pngs if p not in jpgs]
    return rng.sample(pool, min(n, len(pool)))


def species_match(predicted: str, folder_name: str) -> bool:
    pred_lower = predicted.lower()
    for alias in SPECIES_ALIASES.get(folder_name, []):
        if alias in pred_lower:
            return True
    return False


def _bar(correct: int, total: int, width: int = 20) -> str:
    frac  = correct / total if total else 0
    filled = int(frac * width)
    return f"[{'█' * filled}{'░' * (width - filled)}] {correct}/{total} ({frac:.0%})"


# ── test 1: species ────────────────────────────────────────────────────────────

def eval_species(n: int, out_dir: Path) -> None:
    print("\n" + "=" * 65)
    print("TEST 1 — Species Identification  (identify)")
    print("=" * 65)

    rows: list[dict] = []
    class_stats: dict[str, dict] = {}

    for class_dir in sorted(SPECIES_DIR.iterdir()):
        if not class_dir.is_dir():
            continue
        folder_name = class_dir.name
        images      = sample_images(class_dir, n)
        if not images:
            print(f"\n  [SKIP] {folder_name} — no images")
            continue

        print(f"\n  {folder_name}  ({len(images)} images)")
        correct = 0

        for img in images:
            try:
                result    = identify(str(img))
                predicted = result["species"]
                conf      = result["confidence"]
                match     = species_match(predicted, folder_name)
                correct  += match

                mark = "✓" if match else "✗"
                print(f"    {mark} {img.name:<30s}  '{predicted}'  conf={conf:.2f}")
                rows.append({
                    "class":             folder_name,
                    "image":             img.name,
                    "predicted_species": predicted,
                    "confidence":        conf,
                    "match":             match,
                })
            except Exception as exc:
                print(f"    ! {img.name}  ERROR: {exc}")
                rows.append({
                    "class":             folder_name,
                    "image":             img.name,
                    "predicted_species": f"ERROR: {exc}",
                    "confidence":        0.0,
                    "match":             False,
                })
            time.sleep(API_DELAY)

        class_stats[folder_name] = {"correct": correct, "total": len(images)}

    # ── write CSV ──────────────────────────────────────────────────────────────
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "species_results.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["class", "image", "predicted_species", "confidence", "match"])
        writer.writeheader()
        writer.writerows(rows)

    # ── print summary ──────────────────────────────────────────────────────────
    print("\n  ── Per-class accuracy ──────────────────────────────────")
    total_c = total_t = 0
    for cls, s in sorted(class_stats.items()):
        print(f"  {cls:<45s} {_bar(s['correct'], s['total'])}")
        total_c += s["correct"]; total_t += s["total"]
    print(f"\n  {'Overall':<45s} {_bar(total_c, total_t)}")

    # Hallucination summary: high-conf wrong predictions
    hall = [r for r in rows if not r["match"] and isinstance(r["confidence"], float) and r["confidence"] >= 0.7]
    print(f"\n  High-confidence wrong predictions (conf ≥ 0.70): {len(hall)}")
    for h in hall:
        print(f"    {h['class']}/{h['image']}  predicted='{h['predicted_species']}'  conf={h['confidence']:.2f}")

    print(f"\n  CSV  →  {csv_path}")


# ── test 2 & 3: disease (oracle) and pipeline ──────────────────────────────────

def eval_disease(n: int, out_dir: Path, pipeline: bool) -> None:
    test_num = 3 if pipeline else 2
    label    = (
        "Full Pipeline  (identify → diagnose with predicted species)"
        if pipeline else
        "Disease Classification  (diagnose, oracle species from folder name)"
    )
    mode = "pipeline" if pipeline else "disease"

    print("\n" + "=" * 65)
    print(f"TEST {test_num} — {label}")
    print("=" * 65)

    rows:       list[dict]             = []
    class_stats: dict[str, dict]       = {}
    confusion:  dict[tuple, int]       = defaultdict(int)
    hall:       list[dict]             = []

    for class_dir in sorted(DISEASE_DIR.iterdir()):
        if not class_dir.is_dir():
            continue
        folder_name = class_dir.name
        if folder_name not in DISEASE_CLASS_GT:
            print(f"\n  [SKIP] {folder_name} — not in ground-truth table")
            continue

        oracle_species, gt_category = DISEASE_CLASS_GT[folder_name]
        images = sample_images(class_dir, n)
        if not images:
            print(f"\n  [SKIP] {folder_name} — no images")
            continue

        print(f"\n  {folder_name}")
        print(f"    gt_species='{oracle_species}'  gt_category='{gt_category}'")
        correct = 0

        for img in images:
            try:
                # ── step 1: species identification ─────────────────────────────
                if pipeline:
                    id_result  = identify(str(img))
                    id_species = id_result["species"]
                    id_conf    = id_result["confidence"]
                    known      = id_species if id_species.lower() != "unknown" else None
                    time.sleep(API_DELAY)
                else:
                    id_species = oracle_species
                    id_conf    = None
                    known      = oracle_species

                # ── step 2: diagnosis ──────────────────────────────────────────
                result       = diagnose(str(img), known_species=known)
                pred_cat     = result["issue_category"]
                pred_conf    = result["confidence"]
                match        = pred_cat == gt_category
                correct     += match
                confusion[(gt_category, pred_cat)] += 1

                if not match and pred_conf >= 0.7:
                    hall.append({
                        "class":      folder_name,
                        "image":      img.name,
                        "gt":         gt_category,
                        "predicted":  pred_cat,
                        "confidence": pred_conf,
                        "id_species": id_species,
                    })

                mark     = "✓" if match else "✗"
                id_note  = f"  id='{id_species}' ({id_conf:.2f})" if pipeline else ""
                print(f"    {mark} {img.name:<30s}  '{pred_cat}'  conf={pred_conf:.2f}{id_note}")

                rows.append({
                    "class":              folder_name,
                    "image":              img.name,
                    "gt_species":         oracle_species,
                    "gt_category":        gt_category,
                    "identified_species": id_species,
                    "id_confidence":      id_conf if id_conf is not None else "",
                    "predicted_category": pred_cat,
                    "diag_confidence":    pred_conf,
                    "match":              match,
                })
            except Exception as exc:
                print(f"    ! {img.name}  ERROR: {exc}")
                rows.append({
                    "class":              folder_name,
                    "image":              img.name,
                    "gt_species":         oracle_species,
                    "gt_category":        gt_category,
                    "identified_species": "",
                    "id_confidence":      "",
                    "predicted_category": f"ERROR: {exc}",
                    "diag_confidence":    0.0,
                    "match":              False,
                })
            time.sleep(API_DELAY)

        class_stats[folder_name] = {"correct": correct, "total": len(images), "gt": gt_category}

    # ── write CSV ──────────────────────────────────────────────────────────────
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / f"{mode}_results.csv"
    fieldnames = [
        "class", "image", "gt_species", "gt_category",
        "identified_species", "id_confidence",
        "predicted_category", "diag_confidence", "match",
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    # ── per-class accuracy ─────────────────────────────────────────────────────
    print("\n  ── Per-class accuracy ──────────────────────────────────")
    total_c = total_t = 0
    for cls, s in sorted(class_stats.items()):
        label_str = f"{cls}  (gt={s['gt']})"
        print(f"  {label_str:<55s} {_bar(s['correct'], s['total'])}")
        total_c += s["correct"]; total_t += s["total"]
    print(f"\n  {'Overall':<55s} {_bar(total_c, total_t)}")

    # ── confusion matrix ───────────────────────────────────────────────────────
    all_cats = sorted({gt for gt, _ in confusion} | {pr for _, pr in confusion})
    print("\n  ── Confusion matrix  (rows = ground truth, cols = predicted) ──")
    col_w = 14
    header = f"  {'':22s}" + "".join(f"{c:{col_w}s}" for c in all_cats)
    print(header)
    print("  " + "-" * (22 + col_w * len(all_cats)))
    for gt in all_cats:
        row = f"  {gt:22s}" + "".join(
            f"{confusion.get((gt, pr), 0):{col_w}d}" for pr in all_cats
        )
        print(row)

    # ── hallucinations ─────────────────────────────────────────────────────────
    print(f"\n  ── High-confidence wrong predictions (conf ≥ 0.70): {len(hall)} ──")
    if hall:
        for h in hall:
            id_note = f"  id='{h['id_species']}'" if pipeline else ""
            print(f"    {h['class']}/{h['image']}")
            print(f"      gt='{h['gt']}'  predicted='{h['predicted']}'  conf={h['confidence']:.2f}{id_note}")
    else:
        print("    None")

    print(f"\n  CSV  →  {csv_path}")


# ── entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate LLM plant classification against labeled ground truth",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--mode", choices=["species", "disease", "pipeline", "all"], default="all",
        help="Which test(s) to run (default: all)",
    )
    parser.add_argument(
        "--samples", type=int, default=DEFAULT_SAMPLES, metavar="N",
        help=f"Images per class (default: {DEFAULT_SAMPLES}; use fewer to keep API cost low)",
    )
    parser.add_argument(
        "--out", default="eval_results", metavar="DIR",
        help="Output directory for CSV files (default: eval_results/)",
    )
    args = parser.parse_args()

    if not os.getenv("OPENAI_API_KEY"):
        sys.exit("ERROR: OPENAI_API_KEY not set. Export it or add it to .env")

    out = Path(args.out)
    n   = args.samples

    if args.mode in ("species", "all"):
        eval_species(n, out)

    if args.mode in ("disease", "all"):
        eval_disease(n, out, pipeline=False)

    if args.mode in ("pipeline", "all"):
        eval_disease(n, out, pipeline=True)

    print("\n\nAll done. Results in", out.resolve())


if __name__ == "__main__":
    main()
