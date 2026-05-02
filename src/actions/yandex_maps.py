import asyncio
import random
from typing import List, Dict, Optional

from src.domain.models.business_card import BusinessCard
from src.infrastructure.browser.user_agent_pool import UserAgentPool
from src.infrastructure.browser.pool_manager import BrowserPoolManager
from src.core.logging import get_logger

logger = get_logger(__name__)


class YandexMapsExtractAction:
    def __init__(self):
        self.pool_manager = BrowserPoolManager()
        self.user_agent_pool = UserAgentPool()
        self.max_scroll_attempts = 20
        self.scroll_delay = 1.5

    async def execute(
        self, category: str, center: Dict[str, float], radius: int
    ) -> List[BusinessCard]:
        user_agent = self.user_agent_pool.get_user_agent()
        logger.info(f"Starting Yandex Maps extraction for category: {category}")

        context = await self.pool_manager.create_context(
            user_agent=user_agent, stealth=True
        )

        page = await context.new_page()

        try:
            lat, lng = center["lat"], center["lng"]
            yandex_url = (
                f"https://yandex.ru/maps/?ll={lng}%2C{lat}"
                f"&spn={radius / 11132:.4f}%2C{radius / 11132:.4f}"
                f"&text={category}"
            )

            await page.goto(yandex_url, wait_until="networkidle", timeout=30000)

            await asyncio.sleep(random.uniform(1, 2))

            businesses = await self._extract_all_pages(page, category)

            logger.info(f"Extracted {len(businesses)} businesses")
            return businesses

        except Exception as e:
            logger.error(f"Yandex Maps extraction failed: {e}")
            raise
        finally:
            await context.close()

    async def _extract_all_pages(self, page, category: str) -> List[BusinessCard]:
        all_businesses = []
        seen_names = set()
        scroll_attempts = 0

        while scroll_attempts < self.max_scroll_attempts:
            businesses = await self._extract_page(page, category)

            for biz in businesses:
                if biz.name not in seen_names:
                    seen_names.add(biz.name)
                    all_businesses.append(biz)

            has_more = await self._scroll_down(page)
            if not has_more:
                break

            await asyncio.sleep(self.scroll_delay + random.uniform(0, 0.5))
            scroll_attempts += 1

        return all_businesses

    async def _extract_page(self, page, category: str) -> List[BusinessCard]:
        businesses = []

        try:
            await page.wait_for_selector(
                ".business-card, .search-list-view__serp-item, [data-name='BusinessCard']",
                timeout=5000,
            )
        except Exception:
            pass

        cards = await page.query_selector_all(
            ".business-card, .search-list-view__serp-item, [data-name='BusinessCard']"
        )

        for card in cards:
            try:
                business = await self._parse_business_card(card, category)
                if business and business.name:
                    businesses.append(business)
            except Exception as e:
                logger.debug(f"Failed to parse card: {e}")
                continue

        if not businesses:
            businesses = await self._fallback_extraction(page, category)

        return businesses

    async def _parse_business_card(self, card, category: str) -> Optional[BusinessCard]:
        try:
            name_elem = await card.query_selector(
                ".business-card__title, .search-business-snippet-view__title, [data-name='title']"
            )
            name = await name_elem.text_content() if name_elem else None

            address_elem = await card.query_selector(
                ".business-card__address, .search-business-snippet-view__address"
            )
            address = await address_elem.text_content() if address_elem else None

            if not name:
                return None

            phone = None
            phone_elem = await card.query_selector(
                ".business-card__phone, .search-business-snippet-view__phone"
            )
            if phone_elem:
                phone = await phone_elem.text_content()

            website = None
            website_elem = await card.query_selector(
                ".business-card__website a, .search-business-snippet-view__link"
            )
            if website_elem:
                href = await website_elem.get_attribute("href")
                if href and href.startswith("http"):
                    website = href

            geo = None
            geo_elem = await card.query_selector(
                ".business-card__coordinates, .search-business-snippet-view__coordinates"
            )
            if geo_elem:
                coord_text = await geo_elem.text_content()
                if coord_text:
                    coords = coord_text.replace(",", ".").split()
                    if len(coords) >= 2:
                        try:
                            geo = {"lat": float(coords[0]), "lng": float(coords[1])}
                        except ValueError:
                            pass

            return BusinessCard(
                name=name.strip() if name else "",
                address=address.strip() if address else "",
                phone=phone.strip() if phone else None,
                website=website,
                geo=geo,
                category=category,
            )
        except Exception as e:
            logger.debug(f"Failed to parse business card: {e}")
            return None

    async def _fallback_extraction(self, page, category: str) -> List[BusinessCard]:
        businesses = []

        try:
            content = await page.content()
            if "yandex" in content.lower():
                name_elems = await page.query_selector_all(
                    "a[class*='title'], .name, [class*='BusinessName']"
                )
                address_elems = await page.query_selector_all(
                    "address, .address, [class*='Address']"
                )

                for i, name_elem in enumerate(name_elems[:50]):
                    try:
                        name = await name_elem.text_content()
                        address = (
                            await address_elems[i].text_content()
                            if i < len(address_elems)
                            else None
                        )

                        if name and len(name.strip()) > 2:
                            businesses.append(
                                BusinessCard(
                                    name=name.strip(),
                                    address=address.strip() if address else "",
                                    category=category,
                                )
                            )
                    except Exception:
                        continue
        except Exception as e:
            logger.warning(f"Fallback extraction failed: {e}")

        return businesses

    async def _scroll_down(self, page) -> bool:
        try:
            before_height = await page.evaluate("document.body.scrollHeight")

            await page.evaluate("""
                window.scrollTo({
                    top: document.body.scrollHeight,
                    behavior: 'smooth'
                });
            """)

            await asyncio.sleep(1)

            after_height = await page.evaluate("document.body.scrollHeight")

            scroll_button = await page.query_selector(
                ".scroll-button, .yandex-maps__scroll-more, [class*='showMore']"
            )
            if scroll_button:
                await scroll_button.click()
                await asyncio.sleep(1)

            return after_height > before_height

        except Exception:
            return False
