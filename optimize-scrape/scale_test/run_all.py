"""Run every per-site scale test SEQUENTIALLY (so we never exceed the 20-conn
proxy cap) and print a combined summary table.

Usage: python run_all.py [n_requests] [concurrency]   (defaults 100, 6)
"""
import asyncio
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import run_site  # noqa: E402

# NB: t.me excluded from the batch — Telegram is unreachable from this host when
# traffic isn't routed through the VPN (even via proxy). Run site_tme.py separately
# from a VPN-enabled machine. The httpx /s/ method itself is already proven valid.
SITES = [
    ("hh.ru", "site_hh"),
    ("prodoctorov.ru", "site_prodoctorov"),
    ("rusprofile.ru", "site_rusprofile"),
    ("zoon.ru", "site_zoon"),
    ("rubrikator.org", "site_rubrikator"),
    ("orgzz.ru", "site_orgzz"),
    ("spravker.ru", "site_spravker"),
    ("vk.com", "site_vk"),
    ("2gis.ru", "site_2gis"),
]


async def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 100
    conc = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 6
    # neutralise argv so run_site's own CLI-override doesn't re-read it
    sys.argv = sys.argv[:1]
    summaries = []
    for site, mod_name in SITES:
        mod = importlib.import_module(mod_name)
        try:
            s = await run_site(site, mod.rewrite, mod.validate, n_requests=n, concurrency=conc)
            summaries.append(s)
        except Exception as e:  # noqa: BLE001
            print(f"[{site}] FAILED: {e}")
            summaries.append({"site": site, "error": str(e)})

    print("\n\n===================== COMBINED =====================")
    hdr = f"{'site':16}{'req_ok':>8}{'content':>9}{'MB/100':>8}{'avg_KB':>8}{'p95_KB':>8}{'att':>6}{'lat_s':>7}"
    print(hdr)
    for s in summaries:
        if "error" in s:
            print(f"{s['site']:16}  ERROR: {s['error'][:50]}")
            continue
        print(f"{s['site']:16}"
              f"{s['request_success_rate']*100:>7.0f}%"
              f"{s['content_success_rate']*100:>8.0f}%"
              f"{s['total_wire_mb']:>8.2f}"
              f"{s['avg_bytes_per_ok']/1024:>8.1f}"
              f"{s['p95_bytes_ok']/1024:>8.1f}"
              f"{s['avg_attempts']:>6.1f}"
              f"{s['avg_latency_s']:>7.1f}")


if __name__ == "__main__":
    asyncio.run(main())
