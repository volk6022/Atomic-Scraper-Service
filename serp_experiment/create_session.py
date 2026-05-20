"""Create a new Google session with solved captcha.

Usage:
    uv run python -m serp_experiment.create_session
    uv run python -m serp_experiment.create_session --proxy http://user:pass@host:port
    uv run python -m serp_experiment.create_session --proxy ... --notes "first session"

Сохраняет нативное Playwright `storage_state` (cookies + localStorage с
правильным origin'ом), а не сырые JSON-полотна — потом контекст восстанавливается
одним параметром `new_context(storage_state=...)`.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from playwright.async_api import async_playwright

from .proxy_forwarder import PlaywrightProxySource


MAX_SESSIONS = 10
MAX_AGE_MINUTES = 30

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


def _session_age(folder: Path) -> datetime | None:
    """Read created_at from metadata.json, return parsed datetime or None."""
    meta = folder / "metadata.json"
    if not meta.exists():
        return None
    try:
        data = json.loads(meta.read_text(encoding="utf-8"))
        created = data.get("created_at", "")
        if not created:
            return None
        return datetime.fromisoformat(created)
    except Exception:
        return None


def cleanup_old_sessions(sessions_dir: Path) -> None:
    """Remove sessions older than MAX_AGE_MINUTES; cap total at MAX_SESSIONS."""
    if not sessions_dir.exists():
        return

    folders = [f for f in sessions_dir.iterdir() if f.is_dir()]
    cutoff = datetime.now() - timedelta(minutes=MAX_AGE_MINUTES)

    # 1) drop broken or stale
    to_remove: list[Path] = []
    keepers: list[tuple[datetime, Path]] = []
    for folder in folders:
        age = _session_age(folder)
        if age is None or age < cutoff:
            to_remove.append(folder)
        else:
            keepers.append((age, folder))

    # 2) cap remaining at MAX_SESSIONS — drop oldest first
    keepers.sort(key=lambda t: t[0], reverse=True)  # newest first
    if len(keepers) > MAX_SESSIONS:
        for _, folder in keepers[MAX_SESSIONS:]:
            to_remove.append(folder)
        keepers = keepers[:MAX_SESSIONS]

    for folder in to_remove:
        try:
            shutil.rmtree(folder)
            print(f"Removed old session: {folder.name}")
        except Exception as e:
            print(f"Failed to remove {folder.name}: {e}")

    print(f"Sessions kept: {len(keepers)}/{MAX_SESSIONS} (max age {MAX_AGE_MINUTES} min)")


async def create_session(
    proxy_url: str | None,
    notes: str,
    sessions_dir: Path,
) -> None:
    cleanup_old_sessions(sessions_dir)

    session_id = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    session_dir = sessions_dir / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n=== Creating session: {session_id} ===")
    if proxy_url:
        print(f"Proxy: {proxy_url}")
    if notes:
        print(f"Notes: {notes}")

    async with PlaywrightProxySource(proxy_url) as pw_proxy:
        launch_kwargs: dict = {"headless": False}
        if pw_proxy:
            launch_kwargs["proxy"] = pw_proxy

        async with async_playwright() as p:
            browser = await p.chromium.launch(**launch_kwargs)
            try:
                context = await browser.new_context(
                    user_agent=USER_AGENT,
                    locale="en-US",
                    viewport={"width": 1920, "height": 1080},
                    extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
                )
                page = await context.new_page()

                print("\nNavigating to Google...")
                await page.goto("https://www.google.com", wait_until="domcontentloaded")

                print("\n" + "=" * 60)
                print("Solve the captcha / consent in the browser.")
                print("Optionally do a real search to warm up cookies.")
                print("When done, switch to this terminal and press Enter.")
                print("=" * 60 + "\n")

                # blocking input in async — fine for an interactive script
                await asyncio.to_thread(input, "Press Enter when ready: ")

                await page.wait_for_timeout(800)

                # screenshot for eyeballing
                screenshot = await page.screenshot()
                (session_dir / "screenshot.png").write_bytes(screenshot)
                print("Screenshot saved")

                # native Playwright storage state — atomic cookies + localStorage
                state_path = session_dir / "storage_state.json"
                await context.storage_state(path=str(state_path))
                state = json.loads(state_path.read_text(encoding="utf-8"))
                print(
                    f"storage_state saved: {len(state.get('cookies', []))} cookies, "
                    f"{len(state.get('origins', []))} origins"
                )

                metadata = {
                    "proxy_url": proxy_url,
                    "created_at": datetime.now().isoformat(),
                    "notes": notes,
                }
                (session_dir / "metadata.json").write_text(
                    json.dumps(metadata, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                print("Metadata saved")
                print(f"\nSession saved to: {session_dir}")

            finally:
                await browser.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a Google session with solved captcha"
    )
    parser.add_argument(
        "--proxy",
        type=str,
        default=None,
        help="Proxy URL (e.g., http://user:pass@host:port or socks5://...)",
    )
    parser.add_argument(
        "--notes",
        type=str,
        default="",
        help="Notes for this session",
    )
    parser.add_argument(
        "--dir",
        type=str,
        default=None,
        help="Sessions directory (default: <serp_experiment>/sessions)",
    )

    args = parser.parse_args()

    if args.dir:
        sessions_dir = Path(args.dir)
    else:
        sessions_dir = Path(__file__).resolve().parent / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)

    asyncio.run(create_session(args.proxy, args.notes, sessions_dir))


if __name__ == "__main__":
    main()
