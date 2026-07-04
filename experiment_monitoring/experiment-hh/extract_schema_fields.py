"""
extract_schema_fields.py — Extract actual field definitions from the openapi spec.
Focus on:
1. What triggers the /vacancies 403/captcha
2. Full field list for vacancy search response items and single vacancy
3. contacts field presence and conditions
4. employer fields
5. order_by enum values (from spec, not just dictionaries)
6. search_field enum values
7. 2000-result cap documentation
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SAMPLES_DIR = Path(__file__).parent / "samples"
spec_path = SAMPLES_DIR / "openapi_spec_full.json"
spec = json.loads(spec_path.read_text(encoding="utf-8"))

paths = spec.get("paths", {})
components = spec.get("components", {})
schemas = components.get("schemas", {})


def resolve(ref_or_schema: dict, depth: int = 0) -> dict:
    if depth > 5:
        return {}
    if "$ref" in ref_or_schema:
        name = ref_or_schema["$ref"].split("/")[-1]
        return resolve(schemas.get(name, {}), depth + 1)
    return ref_or_schema


def get_props(schema_name: str, depth: int = 0) -> dict:
    if depth > 4:
        return {}
    s = schemas.get(schema_name, {})
    props = {}
    # Direct properties
    props.update(s.get("properties", {}))
    # allOf
    for sub in s.get("allOf", []):
        sub_resolved = resolve(sub)
        if sub_resolved:
            props.update(sub_resolved.get("properties", {}))
            # recurse into allOf's allOf
            for sub2 in sub_resolved.get("allOf", []):
                sub2r = resolve(sub2)
                if sub2r:
                    props.update(sub2r.get("properties", {}))
    return props


# 1. /vacancies GET parameters — find order_by and search_field enums
print("=== /vacancies GET parameters ===")
vac_get = paths.get("/vacancies", {}).get("get", {})
params = vac_get.get("parameters", [])
for p in params:
    pname = p.get("name", "?")
    if pname in ["order_by", "search_field", "per_page", "date_from", "date_to", "period"]:
        schema = p.get("schema", {})
        resolved_schema = resolve(schema)
        print(f"  {pname}: enum={resolved_schema.get('enum', [])}, type={resolved_schema.get('type')}, description={str(p.get('description', ''))[:200]}")

# 2. Look for the max result cap in /vacancies description or parameters
print("\n=== /vacancies description / x-description ===")
desc = vac_get.get("description", "")
if "2000" in desc or "лимит" in desc.lower() or "limit" in desc.lower():
    print(f"  Found limit in description: ...{desc[max(0, desc.find('2000')-100):desc.find('2000')+200]}...")
else:
    print(f"  Description snippet: {desc[:300]}")

# Look in per_page param description
for p in params:
    if p.get("name") == "per_page":
        print(f"  per_page description: {p.get('description', '')[:300]}")
    if p.get("name") == "page":
        print(f"  page description: {p.get('description', '')[:300]}")

# 3. Vacancy search response schema
print("\n=== /vacancies 200 response schema ===")
resp200 = vac_get.get("responses", {}).get("200", {})
content = resp200.get("content", {}).get("application/json", {})
resp_schema = resolve(content.get("schema", {}))
print(f"  Response schema properties: {list(resp_schema.get('properties', {}).keys())}")

# Get items schema
items_schema_ref = resp_schema.get("properties", {}).get("items", {})
items_schema = resolve(items_schema_ref)
if "items" in items_schema:
    item_schema = resolve(items_schema["items"])
    print(f"  Item schema type: {item_schema.get('type')}")
    if "$ref" in items_schema.get("items", {}):
        item_schema_name = items_schema["items"]["$ref"].split("/")[-1]
        print(f"  Item schema name: {item_schema_name}")
        item_props = get_props(item_schema_name)
        print(f"  Item fields: {sorted(item_props.keys())}")

# 4. Single vacancy schema — /vacancies/{vacancyId}
print("\n=== /vacancies/{vacancyId} response schema ===")
single_path = paths.get("/vacancies/{vacancyId}", {})
single_get = single_path.get("get", {})
single_resp200 = single_get.get("responses", {}).get("200", {})
single_content = single_resp200.get("content", {}).get("application/json", {})
single_schema_ref = single_content.get("schema", {})
if single_schema_ref:
    single_schema_name = single_schema_ref.get("$ref", "").split("/")[-1]
    print(f"  Schema ref: {single_schema_name}")
    if single_schema_name:
        single_props = get_props(single_schema_name)
        print(f"  Fields: {sorted(single_props.keys())}")

# If the above is empty, find VacanciesVacancyConditions
print("\n=== VacanciesVacancyConditions (contacts check) ===")
conds = schemas.get("VacanciesVacancyConditions", {})
props_conds = get_props("VacanciesVacancyConditions")
if "contacts" in props_conds:
    contacts_schema = resolve(props_conds["contacts"])
    print(f"  contacts field: {contacts_schema}")
if "description" in props_conds:
    print(f"  description field present: yes")

# 5. VacancyCommonFields
print("\n=== VacancyCommonFields ===")
vcf_props = get_props("VacancyCommonFields")
print(f"  fields: {sorted(vcf_props.keys())}")
if "contacts" in vcf_props:
    print(f"  contacts schema: {resolve(vcf_props['contacts'])}")
if "key_skills" in vcf_props:
    print(f"  key_skills schema: {resolve(vcf_props['key_skills'])}")

# 6. VacanciesStandardVacancyFields
print("\n=== VacanciesStandardVacancyFields ===")
vsvf_props = get_props("VacanciesStandardVacancyFields")
print(f"  fields: {sorted(vsvf_props.keys())}")

# 7. Employer endpoint schema
print("\n=== /employers/{employerId} 200 schema ===")
emp_path = paths.get("/employers/{employerId}", {})
emp_get = emp_path.get("get", {})
emp_resp200 = emp_get.get("responses", {}).get("200", {})
emp_content = emp_resp200.get("content", {}).get("application/json", {})
emp_schema_ref = emp_content.get("schema", {})
if emp_schema_ref:
    emp_schema_name = emp_schema_ref.get("$ref", "").split("/")[-1]
    print(f"  Schema: {emp_schema_name}")
    if emp_schema_name:
        emp_props = get_props(emp_schema_name)
        print(f"  Fields: {sorted(emp_props.keys())}")
else:
    # find EmployerFull or similar
    for sname in schemas:
        if "employer" in sname.lower() and "full" in sname.lower():
            print(f"  Found schema: {sname}")
            p = get_props(sname)
            print(f"  Fields: {sorted(p.keys())[:30]}")
            break

# 8. Captcha / forbidden on /vacancies — read the 400 and 403 schemas
print("\n=== /vacancies 400 response (captcha) ===")
resp400 = vac_get.get("responses", {}).get("400", {})
print(f"  400: {str(resp400)[:300]}")

print("\n=== ErrorsCommonCaptchaErrors schema ===")
captcha_schema = schemas.get("ErrorsCommonCaptchaErrors", {})
print(f"  {str(captcha_schema)[:400]}")
captcha_error = schemas.get("ErrorsCommonCaptchaError", {})
print(f"  ErrorsCommonCaptchaError: {str(captcha_error)[:400]}")

# 9. Check if there's geo-restriction or anonymous-access info
print("\n=== Anonymous access documentation ===")
# Search for "anonymous" or "anonymous" or "без авторизации" in /vacancies description
for keyword in ["anonymous", "без авторизации", "без токена", "captcha", "капча", "ddos"]:
    if keyword.lower() in str(vac_get).lower():
        # find position
        full_str = str(vac_get).lower()
        idx = full_str.find(keyword.lower())
        print(f"  Found '{keyword}' in /vacancies spec at position {idx}: ...{str(vac_get)[max(0,idx-50):idx+100]}...")

print("\n=== Done ===")
