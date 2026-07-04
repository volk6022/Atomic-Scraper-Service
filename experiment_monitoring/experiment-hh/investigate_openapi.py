"""
investigate_openapi.py — parse the OpenAPI spec to find:
1. What /vacancies requires (auth? geo? special headers?)
2. Valid order_by values for /vacancies
3. Full field list for /vacancies/{id}
4. Whether contacts field exists
5. Read the 403 error type definition
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx
import yaml  # available via pyyaml

SAMPLES_DIR = Path(__file__).parent / "samples"
SAMPLES_DIR.mkdir(exist_ok=True)


def main():
    print("=== Fetching OpenAPI spec ===")
    with httpx.Client(timeout=30.0, follow_redirects=True,
                      headers={"User-Agent": "HHVerify/1.0", "Accept": "application/x-yaml"}) as c:
        resp = c.get("https://api.hh.ru/openapi/specification/public")
    print(f"Status: {resp.status_code}, size: {len(resp.text)} chars")

    spec = yaml.safe_load(resp.text)

    # Save full spec
    spec_path = SAMPLES_DIR / "openapi_spec_full.json"
    import datetime
    def default_serial(obj):
        if isinstance(obj, (datetime.date, datetime.datetime)):
            return obj.isoformat()
        raise TypeError(f"Not serializable: {type(obj)}")
    spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2, default=default_serial), encoding="utf-8")
    print(f"Saved full spec to {spec_path.name}")

    paths = spec.get("paths", {})

    # Check /vacancies
    print("\n=== /vacancies endpoint ===")
    vac_path = paths.get("/vacancies", {})
    vac_get = vac_path.get("get", {})
    print(f"  Summary: {vac_get.get('summary')}")
    print(f"  Security: {vac_get.get('security')}")

    # Parameters
    params = vac_get.get("parameters", [])
    print(f"  Parameters count: {len(params)}")
    param_names = []
    for p in params:
        name = p.get("name", "?")
        required = p.get("required", False)
        loc = p.get("in", "?")
        schema = p.get("schema", {})
        enum = schema.get("enum", [])
        param_names.append(name)
        if name in ["order_by", "date_from", "date_to", "per_page", "page", "text",
                    "professional_role", "area", "search_field", "period"]:
            print(f"    {name} (in={loc}, required={required}, enum={enum})")

    print(f"\n  All param names: {sorted(param_names)}")

    # Responses
    responses = vac_get.get("responses", {})
    print(f"  Response codes: {list(responses.keys())}")
    if "403" in responses:
        print(f"  403 response: {responses['403']}")

    # /vacancies/{vacancy_id}
    print("\n=== /vacancies/{vacancyId} endpoint ===")
    single_vac = paths.get("/vacancies/{vacancyId}", {})
    single_get = single_vac.get("get", {})
    print(f"  Summary: {single_get.get('summary')}")
    print(f"  Security: {single_get.get('security')}")
    responses2 = single_get.get("responses", {})
    print(f"  Response codes: {list(responses2.keys())}")
    if "403" in responses2:
        print(f"  403 response: {responses2['403']}")

    # Get response schema for 200
    r200 = responses2.get("200", {})
    content = r200.get("content", {})
    app_json = content.get("application/json", {})
    schema_ref = app_json.get("schema", {})
    print(f"  200 schema ref: {schema_ref}")

    # /employers/{employerId}
    print("\n=== /employers/{employerId} endpoint ===")
    emp_path = paths.get("/employers/{employerId}", {})
    emp_get = emp_path.get("get", {})
    print(f"  Summary: {emp_get.get('summary')}")
    print(f"  Security: {emp_get.get('security')}")
    emp_resp = emp_get.get("responses", {})
    print(f"  Response codes: {list(emp_resp.keys())}")

    # Resolve schema refs for vacancy detail
    print("\n=== Resolving VacancyFull schema fields ===")
    components = spec.get("components", {})
    schemas = components.get("schemas", {})

    def resolve_ref(ref: str) -> dict:
        parts = ref.lstrip("#/").split("/")
        obj = spec
        for p in parts:
            obj = obj.get(p, {})
        return obj

    def get_schema_fields(schema_name: str, depth: int = 0) -> list[str]:
        if depth > 2:
            return []
        s = schemas.get(schema_name, {})
        props = s.get("properties", {})
        if not props and "$ref" in s:
            ref_name = s["$ref"].split("/")[-1]
            return get_schema_fields(ref_name, depth + 1)
        return list(props.keys())

    # Find the vacancy full schema
    for schema_name in ["VacancyFull", "VacancyDetails", "Vacancy", "VacancyComplete"]:
        if schema_name in schemas:
            fields = get_schema_fields(schema_name)
            print(f"  Schema {schema_name} fields: {sorted(fields)}")

    # Look for contacts in any vacancy schema
    print("\n  Searching for 'contact' in vacancy schemas...")
    for sname, sval in schemas.items():
        if "vacancy" in sname.lower() or "Vacancy" in sname:
            props = sval.get("properties", {})
            if "contacts" in props or "contact" in props:
                print(f"    Schema '{sname}' has contacts/contact field")

    # Check for 'forbidden' error definition
    print("\n=== Forbidden error definition ===")
    for sname, sval in schemas.items():
        if "forbidden" in sname.lower() or "403" in sname:
            print(f"  Schema: {sname}: {sval}")

    # Save a trimmed version of relevant parts
    relevant = {
        "vacancies_get_params": [
            {"name": p.get("name"), "required": p.get("required"), "in": p.get("in"),
             "enum": p.get("schema", {}).get("enum", [])}
            for p in params
        ],
        "vacancies_response_codes": list(responses.keys()),
        "vacancy_single_response_codes": list(responses2.keys()),
        "vacancy_search_order_from_dictionaries": ["publication_time", "salary_desc", "salary_asc", "relevance", "distance"],
    }
    (SAMPLES_DIR / "00_openapi_vacancies_analysis.json").write_text(
        json.dumps(relevant, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nSaved 00_openapi_vacancies_analysis.json")

    print("\n=== Done ===")


if __name__ == "__main__":
    main()
