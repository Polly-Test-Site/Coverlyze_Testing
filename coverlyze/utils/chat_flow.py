from __future__ import annotations
import re

UMBRELLA_REQUIRED = [
    "auto_bi_limit","auto_pd_limit","home_liability_limit","num_drivers","num_teen_drivers",
    "has_pool_trampoline","has_dog","num_rental_properties","watercraft_over_25ft","prior_liability_losses_5y"
]

UMBRELLA_QUESTIONS = {
    "auto_bi_limit": "What are your auto bodily injury limits? (e.g., 100/300)",
    "auto_pd_limit": "What is your auto property damage limit? (e.g., 100000 or 250000)",
    "home_liability_limit": "What is your home liability limit? (e.g., 300000 or 500000)",
    "num_drivers": "How many licensed household drivers?",
    "num_teen_drivers": "How many teen drivers (under 20)?",
    "has_pool_trampoline": "Do you have a pool or trampoline? (yes/no)",
    "has_dog": "Do you have a dog? (yes/no)",
    "num_rental_properties": "How many rental properties, if any?",
    "watercraft_over_25ft": "Any watercraft over 25 ft? (yes/no)",
    "prior_liability_losses_5y": "Any liability claims in the last 5 years? (0/1/2+)"
}

def next_missing_slot(slots: dict):
    for k in UMBRELLA_REQUIRED:
        if not slots.get(k):
            return k
    return None


def estimate_umbrella_premium(slots: dict):
    base = 220
    if (slots.get("auto_bi_limit") or "").startswith(("25/", "50/")):
        base += 60
    try:
        teen = int(slots.get("num_teen_drivers", "0"))
        base += 40 * max(0, teen)
    except Exception:
        pass
    if str(slots.get("has_pool_trampoline", "")).lower().startswith("y"):
        base += 35
    if str(slots.get("has_dog", "")).lower().startswith("y"):
        base += 20
    try:
        rentals = int(slots.get("num_rental_properties", "0"))
        base += 25 * max(0, rentals)
    except Exception:
        pass
    if str(slots.get("watercraft_over_25ft", "")).lower().startswith("y"):
        base += 30
    losses = str(slots.get("prior_liability_losses_5y", "0")).strip().lower()
    if losses in ("1", "one"):
        base += 50
    elif losses in ("2", "2+", "two", "2 or more"):
        base += 120
    return round(base), round(base + 120)


def absorb_umbrella_answers_from_text(slots: dict, msg: str):
    if not msg:
        return slots
    m = re.search(r'\b(25/50|50/100|100/300|250/500|300/300|500/500)\b', msg or "")
    if m:
        slots.setdefault('auto_bi_limit', m.group(1))
    m = re.findall(r'\b(100000|250000|300000|500000)\b', msg or "")
    if m:
        if not slots.get('auto_pd_limit'):
            slots['auto_pd_limit'] = m[0]
        elif not slots.get('home_liability_limit'):
            slots['home_liability_limit'] = m[0]
    lm = (msg or "").lower()
    if 'pool' in lm or 'trampoline' in lm:
        slots['has_pool_trampoline'] = 'no' if 'no' in lm else 'yes'
    if 'dog' in lm:
        slots['has_dog'] = 'no' if 'no' in lm else 'yes'
    m = re.search(r'\b(\d+)\s+(teen|teenage)', lm)
    if m:
        slots['num_teen_drivers'] = m.group(1)
    m = re.search(r'\b(\d+)\s+(driver|drivers)\b', lm)
    if m:
        slots.setdefault('num_drivers', m.group(1))
    m = re.search(r'\b(\d+)\s+(rental|rentals|rental properties)\b', lm)
    if m:
        slots['num_rental_properties'] = m.group(1)
    if 'watercraft' in lm or 'boat' in lm:
        slots['watercraft_over_25ft'] = 'yes' if 'over 25' in lm else slots.get('watercraft_over_25ft', 'no')
    m = re.search(r'\b(0|1|2|2\+)\s+(loss|losses|claims)\b', lm)
    if m:
        slots['prior_liability_losses_5y'] = m.group(1)
    return slots
