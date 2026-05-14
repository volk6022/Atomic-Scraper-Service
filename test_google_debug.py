import asyncio
from urllib.parse import parse_qs, urlparse
from src.infrastructure.browser.pool_manager import pool_manager


async def test():
    context = await pool_manager.create_context(headless=True, stealth=True)
    page = await context.new_page()

    await page.set_viewport_size({"width": 1920, "height": 1080})

    search_url = "https://www.google.com/search?q=artificial%20intelligence&num=20"
    await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(3)

    output = []
    results = []
    seen_urls = set()

    # Get all links on the page
    all_links = await page.locator("a").all()

    for idx, link in enumerate(all_links):
        try:
            href = await link.get_attribute("href") or ""

            # Skip internal Google links and empty hrefs
            if not href or "google" in href.lower() or not href.startswith("http"):
                continue

            # Skip duplicates
            if href in seen_urls:
                continue
            seen_urls.add(href)

            # Try to find title - could be in the link text or parent
            title = (await link.text_content() or "").strip()

            # Sometimes the title is in a nearby element
            if not title or len(title) < 5:
                try:
                    parent = link.locator("xpath=..").first
                    title = (await parent.text_content() or "").strip()[:100]
                except:
                    pass

            # Clean up title - remove extra whitespace and truncate
            if title:
                title = " ".join(title.split())[:150]

            # Try to find snippet - look for sibling or parent elements
            snippet = ""
            try:
                # Try to find snippet in nearby elements
                parent = link.locator("xpath=..").first
                # Look for text that might be a snippet
                parent_text = await parent.text_content() or ""
                if title and title in parent_text:
                    snippet = parent_text.replace(title, "").strip()[:200]
                    snippet = " ".join(snippet.split())
            except:
                pass

            if title and len(title) > 5:
                results.append(
                    {
                        "title": title,
                        "link": href[:200],  # Limit URL length
                        "snippet": snippet[:200],
                        "position": len(results) + 1,
                    }
                )
        except Exception as e:
            continue

    output.append(f"=== Extracted {len(results)} results ===")
    for r in results[:10]:
        output.append(f"Position {r['position']}: {r['title'][:60]}")
        output.append(f"  Link: {r['link'][:70]}")
        output.append(f"  Snippet: {r['snippet'][:80]}")
        output.append("")

    await context.close()

    with open("debug_output.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(output))
    print(f"Extracted {len(results)} results")


asyncio.run(test())
