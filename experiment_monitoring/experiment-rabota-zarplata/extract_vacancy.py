"""Extract vacancy sample from zarplata HTML."""
import re, json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

html_path = 'C:/Users/bhunp/Documents/auto-monitor-ml-cv/repos/Atomic-Scraper-Service/experiment_monitoring/experiment-rabota-zarplata/samples/zarplata/playwright_search.html'
with open(html_path, encoding='utf-8') as f:
    html = f.read()

idx = html.find('"vacancies":[{')
if idx < 0:
    print("vacancies not found")
    sys.exit(1)

chunk = html[idx + len('"vacancies":') : idx + 10000]
start = chunk.find('[')

# Count brackets to find end of first object
depth = 0
in_str = False
esc = False
vac_count = 0
first_vac_end = None

chars = list(chunk[start:])
for i, c in enumerate(chars):
    if esc:
        esc = False
        continue
    if c == chr(92) and in_str:  # backslash
        esc = True
        continue
    if c == '"':
        in_str = not in_str
        continue
    if in_str:
        continue
    if c == '{':
        depth += 1
    elif c == '}':
        depth -= 1
        if depth == 0:
            vac_count += 1
            if vac_count == 1:
                first_vac_end = start + i + 1
                break

if first_vac_end is None:
    print("Could not find vacancy end")
    sys.exit(1)

vac_raw = chunk[start+1:first_vac_end]

# Extract key fields with regex
fields = {
    'vacancyId': r'"vacancyId"\s*:\s*(\d+)',
    'name': r'"name"\s*:\s*"([^"]+)"',
    'company_visibleName': r'"visibleName"\s*:\s*"([^"]+)"',
    'salary_from': r'"from"\s*:\s*(\d+)',
    'salary_to': r'"to"\s*:\s*(\d+)',
    'currencyCode': r'"currencyCode"\s*:\s*"([^"]+)"',
    'publicationTime_ts': r'"publicationTime"[^{]*"@timestamp"\s*:\s*(\d+)',
    'creationSite': r'"creationSite"\s*:\s*"([^"]+)"',
    'displayHost': r'"displayHost"\s*:\s*"([^"]+)"',
    'acceptTemporary': r'"acceptTemporary"\s*:\s*(true|false)',
}

result = {}
for field, pat in fields.items():
    m = re.search(pat, vac_raw)
    if m:
        result[field] = m.group(1)

print("First vacancy fields:")
for k, v in result.items():
    print(f"  {k}: {v}")

print()

# Look for area name
area_idx = vac_raw.find('"area"')
if area_idx >= 0:
    area_chunk = vac_raw[area_idx:area_idx+100]
    area_m = re.search(r'"name"\s*:\s*"([^"]+)"', area_chunk)
    if area_m:
        result['area_name'] = area_m.group(1)
        print(f"  area_name: {area_m.group(1)}")

# Save
out_path = 'C:/Users/bhunp/Documents/auto-monitor-ml-cv/repos/Atomic-Scraper-Service/experiment_monitoring/experiment-rabota-zarplata/samples/zarplata/vacancy_sample.json'
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
print(f"\nSaved to {out_path}")

# Also check how many vacancy IDs are in the page
ids = re.findall(r'"vacancyId"\s*:\s*(\d+)', html)
print(f"\nTotal vacancyId occurrences in HTML: {len(ids)}")
print("Sample IDs:", ids[:5])
