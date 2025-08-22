from __future__ import annotations
import re


def extract_dec_page_data(extracted_text: str) -> dict:
    data = {"policy_info": {}, "insured": {}, "vehicles": [], "drivers": []}
    t = (extracted_text or "")

    policy_number = re.search(r"Policy\s*#?:?\s*([A-Z0-9\-]+)", t, re.I)
    policy_term = re.search(r"Term:?.*?(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}).*?[-–—].*?(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", t, re.I | re.S)
    premium = re.search(r"(?:Full\s*Term\s*Premium|Premium):?\s*\$?([\d,]+\.?\d{0,2})", t, re.I)

    if policy_number:
        data["policy_info"]["policy_number"] = policy_number.group(1)
    if policy_term:
        data["policy_info"]["start_date"] = policy_term.group(1)
        data["policy_info"]["end_date"] = policy_term.group(2)
    if premium:
        data["policy_info"]["full_term_premium"] = premium.group(1)

    insured_name = re.search(r"(?:Name|Insured):?\s*([A-Z][A-Za-z\s,.'-]+?)(?:\n|Email|Address)", t, re.I)
    email = re.search(r"Email:?\s*([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[A-Za-z]{2,})", t, re.I)
    address = re.search(r"Address:?[\s\n]*(\d+.*?(?:[A-Z]{2}|Mass|MA)\s*\d{5})", t, re.I | re.S)

    data["insured"]["name"] = insured_name.group(1).strip() if insured_name else ""
    data["insured"]["email"] = email.group(1).strip() if email else ""
    data["insured"]["address"] = address.group(1).strip() if address else ""

    vehicle_blocks = re.findall(r"Veh\s*#?\s*\d+.*?:([\s\S]*?)(?=Veh\s*#?\s*\d+|Drivers?|$)", t, re.I)
    for vb in vehicle_blocks:
        year_make_model = re.search(r"(\d{4})[ ,]*([A-Z]+)[ ,]*([A-Za-z0-9\s/\-]+)", vb)
        vin = re.search(r"([A-HJ-NPR-Z0-9]{17})", vb)
        vehicle_premium = re.search(r"Vehicle\s*Premium:?:?\s*\$?([\d,]+\.?\d{0,2})", vb, re.I)
        bi = re.search(r"(?:Optional\s*)?bodily\s*injury[:\s]*(\d{1,3})[,\s]*(\d{1,3})", vb, re.I)
        coll = re.search(r"Collision[:\s]*(\d+)", vb, re.I)
        comp = re.search(r"Comprehensive[:\s]*(\d+)", vb, re.I)
        rental = re.search(r"(?:Rental|Car\s*Rental|Transportation)[:\s]*\$?(\d+)(?:/day)?(?:\s*for\s*(\d+)\s*days?)?", vb, re.I)
        roadside = re.search(r"(?:Roadside|Emergency\s*Road|Towing)[:\s]*(\$?\d+|Yes|No|Included|Declined)", vb, re.I)
        um = re.search(r"(?:Uninsured|UM)[:\s]*(\d{1,3})[,\s]*(\d{1,3})", vb, re.I)

        data["vehicles"].append({
            "year": year_make_model.group(1) if year_make_model else "",
            "make": year_make_model.group(2) if year_make_model else "",
            "model": year_make_model.group(3).strip() if year_make_model else "",
            "vin": vin.group(1) if vin else "",
            "vehicle_premium": vehicle_premium.group(1) if vehicle_premium else "",
            "bodily_injury": f"{bi.group(1)}/{bi.group(2)}" if bi else "",
            "collision_deductible": coll.group(1) if coll else "",
            "comprehensive_deductible": comp.group(1) if comp else "",
            "rental_coverage": (f"${rental.group(1)}/day for {rental.group(2) or '30'} days" if rental else ""),
            "roadside_assistance": roadside.group(1) if roadside else "",
            "uninsured_motorist": f"{um.group(1)}/{um.group(2)}" if um else "",
        })

    driver_blocks = re.findall(r"Driver\s*#?\s*(\d+)\s*([A-Z][A-Za-z\s]+)\s*(\d{1,2}/\d{1,2}/\d{4})", t, re.I)
    for db in driver_blocks:
        data["drivers"].append({"driver_number": db[0], "name": db[1].strip(), "dob": db[2]})
    return data


def parse_minimums_from_chunks(chunks: list[str]) -> dict:
    text = "\n".join(chunks or [])
    out = {}
    m = re.search(
        r"(?:state\s+minimum.*?\(bi\s*/\s*pd\).*?:\s*)\$?\s*([0-9,]+)\s*/\s*\$?\s*([0-9,]+)\s*/\s*\$?\s*([0-9,]+)",
        text, re.I | re.S)
    if m:
        clean = lambda x: int(re.sub(r"[^\d]", "", x))
        out["bi_per_person"] = clean(m.group(1))
        out["bi_per_accident"] = clean(m.group(2))
        out["pd"] = clean(m.group(3))
    if "pd" not in out:
        m2 = re.search(r"(?:part\s*4.*?property\s*damage).*?(?:limit[:\s]+)\$?\s*([0-9,]+)", text, re.I)
        if m2:
            out["pd"] = int(re.sub(r"[^\d]", "", m2.group(1)))
    return out
