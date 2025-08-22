from __future__ import annotations
import re
from typing import Optional

US_STATES = {
    "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA","KS","KY","LA","ME","MD","MA","MI",
    "MN","MS","MO","MT","NE","NV","NH","NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT",
    "VT","VA","WA","WV","WI","WY","DC"
}

def infer_state(user_profile: dict, session_obj: dict) -> Optional[str]:
    st = (user_profile or {}).get("state")
    if isinstance(st, str) and st.upper() in US_STATES:
        return st.upper()

    addr = ((session_obj.get("extracted_data") or {}).get("insured") or {}).get("address", "") or ""
    text = session_obj.get("extracted_text", "") or ""

    m = re.search(r"\b([A-Z]{2})\s+\d{5}(?:-\d{4})?\b", str(addr).upper())
    if m and m.group(1) in US_STATES:
        return m.group(1)

    m = re.search(r"[,\s]([A-Z]{2})\s+\d{5}(?:-\d{4})?", str(text).upper())
    if m and m.group(1) in US_STATES:
        return m.group(1)

    return None


def infer_state_debug(user_profile: dict, session_obj: dict):
    """Return (state, debug_info_str)."""
    debug = []
    st = (user_profile or {}).get("state")
    if isinstance(st, str) and st.upper() in US_STATES:
        debug.append(f"Found in profile: {st}")
        return st.upper(), "; ".join(debug)
    else:
        debug.append(f"Profile state: {st} (not valid)")

    addr = ((session_obj.get("extracted_data") or {}).get("insured") or {}).get("address", "") or ""
    if addr:
        debug.append(f"Address: {addr}")
    m = re.search(r"\b([A-Z]{2})\s+\d{5}(?:-\d{4})?\b", str(addr).upper())
    if m and m.group(1) in US_STATES:
        debug.append(f"Found in address: {m.group(1)}")
        return m.group(1), "; ".join(debug)

    text = session_obj.get("extracted_text", "") or ""
    if text:
        m = re.search(r"[,\s]([A-Z]{2})\s+\d{5}(?:-\d{4})?", str(text).upper())
        if m and m.group(1) in US_STATES:
            debug.append(f"Found in text: {m.group(1)}")
            return m.group(1), "; ".join(debug)

    debug.append("No state found")
    return None, "; ".join(debug)
