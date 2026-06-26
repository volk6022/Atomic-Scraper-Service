"""
get_ml_roles.py — Get IT professional roles properly.
"""
import httpx, json
from pathlib import Path

SAMPLES_DIR = Path(__file__).parent / "samples"

with httpx.Client(timeout=15.0, headers={"User-Agent": "HHMonitor/1.0"}) as c:
    r = c.get("https://api.hh.ru/professional_roles")
    data = r.json()

cats = data.get("categories", [])
roles = []
for cat in cats:
    for role in cat.get("roles", []):
        roles.append({"id": role["id"], "name": role["name"], "category": cat.get("name")})

# Find IT category roles
it_roles = [r for r in roles if r["category"] == "Информационные технологии"]
print(f"IT roles ({len(it_roles)}):")
for r in it_roles:
    print(f"  id={r['id']}: {r['name']}")

# Filter by ML/DS/AI keywords
ml_kw = ["data", "ml", "machine", "vision", "deep", "neural", "ai", "искусств",
          "нейронн", "аналитик данн", "data scientist", "nlp", "алгоритм"]
ml_it_roles = [r for r in it_roles if any(kw in r["name"].lower() for kw in ml_kw)]
print(f"\nML/DS/AI IT roles ({len(ml_it_roles)}):")
for r in ml_it_roles:
    print(f"  id={r['id']}: {r['name']}")

# Save properly
(SAMPLES_DIR / "06_professional_roles_ml.json").write_text(
    json.dumps({
        "total_roles": len(roles),
        "it_category_roles": it_roles,
        "ml_relevant_it_roles": ml_it_roles,
    }, ensure_ascii=False, indent=2),
    encoding="utf-8"
)
print(f"\nSaved professional_roles_ml.json")
