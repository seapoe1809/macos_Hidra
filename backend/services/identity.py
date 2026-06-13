"""Membership identity via SHA-256 of 2-of-3 personal fields.

Refactored from id_gen.py + id_checker.py. A member's ID is derived from any
two of {year_of_birth, last_name, city_of_birth}; presenting any matching pair
proves membership without revealing the underlying data.
"""

import hashlib
from itertools import combinations

FIELDS = ("year_of_birth", "last_name", "city_of_birth")


def _norm(value: str) -> str:
    return str(value).strip().lower()


def generate_ids(year_of_birth: str, last_name: str, city_of_birth: str) -> dict:
    """Return {combination_name: sha256_hash} for all three 2-combinations."""
    fields = {
        "year_of_birth": _norm(year_of_birth),
        "last_name": _norm(last_name),
        "city_of_birth": _norm(city_of_birth),
    }
    ids = {}
    for a, b in combinations(FIELDS, 2):
        combined = fields[a] + fields[b]
        ids[f"{a}_{b}"] = hashlib.sha256(combined.encode()).hexdigest()
    return ids


def check_ids(stored_ids: dict, **provided) -> dict:
    """Check provided fields against a member's stored ID hashes.

    `stored_ids` maps combination_name -> hash (as produced by generate_ids).
    `provided` is any subset of FIELDS. Success if >=1 pair matches.
    """
    results = {"success": False, "matches": [], "checked": []}

    fields = {k: _norm(v) for k, v in provided.items() if v and k in FIELDS}
    if len(fields) < 2:
        results["error"] = "Please provide at least 2 inputs"
        return results

    keys = list(fields.keys())
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            k1, k2 = keys[i], keys[j]
            combo = f"{k1}_{k2}"
            if combo in stored_ids:
                combined = fields[k1] + fields[k2]
            else:
                combo = f"{k2}_{k1}"
                combined = fields[k2] + fields[k1]

            hash_id = hashlib.sha256(combined.encode()).hexdigest()
            results["checked"].append({"combination": combo, "generated_hash": hash_id})
            if combo in stored_ids and hash_id == stored_ids[combo]:
                results["matches"].append(combo)

    results["success"] = bool(results["matches"])
    return results


# --- 2-of-4 identity (dashboard ID check) ----------------------------------
# Any two of these prove membership. Order here is canonical: a pair always
# concatenates its values in this order so the hash is identical whether the
# caller provides (last_name, year) or (year, last_name).
ID_FIELDS = ("npub", "year_of_birth", "last_name", "place_of_birth")


def _pair_hash(values: dict, a: str, b: str) -> tuple[str, str]:
    if ID_FIELDS.index(b) < ID_FIELDS.index(a):
        a, b = b, a
    combined = _norm(values[a]) + _norm(values[b])
    return f"{a}__{b}", hashlib.sha256(combined.encode()).hexdigest()


def identity_hashes(values: dict) -> dict:
    """Return {combo_name: sha256} for every pair of present ID_FIELDS.

    Used both to PRE-STORE a member's hashes (all four fields supplied -> 6
    combos) and to hash a check query (two fields -> 1 combo). Missing/empty
    fields are skipped, so the produced combos always align across both sides.
    """
    present = [f for f in ID_FIELDS if values.get(f) not in (None, "")]
    out = {}
    for a, b in combinations(present, 2):
        name, h = _pair_hash(values, a, b)
        out[name] = h
    return out
