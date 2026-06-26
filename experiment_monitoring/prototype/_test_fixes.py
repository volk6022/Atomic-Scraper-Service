"""Quick verification of both bug fixes."""
import sys, io, json
sys.path.insert(0, r"C:\Users\bhunp\Documents\auto-monitor-ml-cv\repos\Atomic-Scraper-Service\experiment_monitoring\prototype")

from monitor_proto import detail_zarplata, detail_fl, norm

print("=" * 60)
print("BUG FIX 1: zarplata description")
print("=" * 60)
# Use 134162056 which had description="" in the last e2e run
item_zp = norm("zarplata", "134162056", "Специалист по ведению базы данных",
               "https://www.zarplata.ru/vacancy/134162056")
result_zp = detail_zarplata(item_zp)
print(f"  title:       {result_zp.get('title','')!r}")
print(f"  company:     {result_zp.get('company','')!r}")
print(f"  amount:      {result_zp.get('amount','')!r}")
desc = result_zp.get('description','')
print(f"  desc_len:    {len(desc)}")
print(f"  desc[:200]:  {desc[:200]!r}")
print(f"  PASS: {len(desc) > 50}")

print()
print("=" * 60)
print("BUG FIX 2: fl budget")
print("=" * 60)
# 5510268 has budget 7000 RUB per RSS title & LD+JSON
# RSS title (as it arrives from ET, entities decoded): "Разработка ЛК партнёрской программы  (Бюджет: 7 000  ₽)"
item_fl = norm("fl", "5510268", "Разработка ЛК партнёрской программы  (Бюджет: 7 000  ₽)",
               "https://www.fl.ru/projects/5510268/razrabotka-lk-partnrskoy-programmyi-.html")
result_fl = detail_fl(item_fl)
print(f"  title:   {result_fl.get('title','')!r}")
print(f"  amount:  {result_fl.get('amount')!r}")
print(f"  PASS:    {result_fl.get('amount') is not None}")

# Also test 5510256 (budget 6000 RUB)
item_fl2 = norm("fl", "5510256", "Верстка лендинга для услуги (адаптив, HTML/React) (Бюджет: 6 000  ₽)",
                "https://www.fl.ru/projects/5510256/verstka-lendinga-dlya-uslugi-adaptiv-html-react.html")
result_fl2 = detail_fl(item_fl2)
print(f"\n  [5510256] title:   {result_fl2.get('title','')!r}")
print(f"  [5510256] amount:  {result_fl2.get('amount')!r}")
print(f"  PASS:              {result_fl2.get('amount') is not None}")
