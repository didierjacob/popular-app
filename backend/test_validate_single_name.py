"""
Local unit tests for candidate_detection.validate_single_name (Vague 4, sous-tâche 4).

Hits the real Wikipedia / Wikidata / WikiMedia APIs — run with network access:
    python3 test_validate_single_name.py

Covers: living human, deceased human, disambiguation page, non-existent name,
and a low-confidence (<65) case.
"""
import asyncio

from candidate_detection import validate_single_name

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"


def _check(label, res, expected):
    """expected: dict of key -> value OR key -> callable(value)->bool."""
    ok = True
    details = []
    for k, exp in expected.items():
        actual = res.get(k)
        good = exp(actual) if callable(exp) else actual == exp
        ok &= good
        details.append(f"    {'OK ' if good else '✗  '} {k}={actual!r}"
                       + ("" if good else f"  (expected {exp})"))
    print(f"[{PASS if ok else FAIL}] {label}")
    print(f"    valid={res.get('valid')} confidence={res.get('confidence')} "
          f"error_code={res.get('error_code')!r} wiki_langs={res.get('wiki_langs')}")
    for d in details:
        print(d)
    print()
    return ok


async def main():
    results = []

    # ── Case 1: living human ──
    r = await validate_single_name("Zendaya")
    results.append(_check("Case 1 — living human (Zendaya)", r, {
        "is_human": True,
        "is_deceased": False,
        "valid": True,
        "error_code": None,
        "confidence": lambda c: c >= 65,
    }))

    # ── Case 2: deceased human ──
    r = await validate_single_name("Albert Einstein")
    results.append(_check("Case 2 — deceased human (Albert Einstein)", r, {
        "is_human": True,
        "is_deceased": True,
        "valid": False,
        "error_code": "deceased",
    }))

    # ── Case 3: disambiguation page (not a single human) ──
    r = await validate_single_name("Mercury")
    results.append(_check("Case 3 — disambiguation page (Mercury)", r, {
        "is_human": False,
        "valid": False,
        "error_code": "wikipedia_not_found",
    }))

    # ── Case 4: non-existent name ──
    r = await validate_single_name("Xqzwhtfvbn Pqrstuvwxyz")
    results.append(_check("Case 4 — non-existent name", r, {
        "is_human": False,
        "valid": False,
        "error_code": "wikipedia_not_found",
    }))

    # ── Case 5: low-confidence living human (confidence 30-64) ──
    # An alive human with a thin Wikipedia footprint (EN page only) lands below 65.
    r = await validate_single_name("Jenny Odell")
    results.append(_check("Case 5 — low confidence <65 (Jenny Odell)", r, {
        "is_human": True,
        "is_deceased": False,
        "valid": False,
        "error_code": lambda e: e in ("low_confidence", "not_recognized"),
        "confidence": lambda c: c < 65,
    }))

    print("=" * 60)
    print(f"TOTAL: {sum(results)}/{len(results)} passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
