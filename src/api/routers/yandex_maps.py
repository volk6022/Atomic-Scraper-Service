"""HTTP endpoints for Yandex Maps scraping.

Both routes are thin wrappers over the actions in `src.actions.yandex_maps`.
See `docs/yandex-maps-scraping-experiment-journal.md` for why we use the
XHR-intercept / observation-and-replay approaches.
"""

from fastapi import APIRouter, Depends, HTTPException

from src.actions.yandex_maps import (
    YandexCaptchaError,
    YandexMapsExtractAction,
    YandexMapsReviewsAction,
)
from src.api.auth import get_api_key
from src.domain.models.requests import (
    YandexMapsExtractRequest,
    YandexMapsExtractResponse,
    YandexMapsReviewsRequest,
    YandexMapsReviewsResponse,
)

router = APIRouter(dependencies=[Depends(get_api_key)])


@router.post("/extract", response_model=YandexMapsExtractResponse)
async def extract_organizations(request: YandexMapsExtractRequest) -> YandexMapsExtractResponse:
    """Search Yandex Maps for organizations by text query inside a region.

    Returns up to `target_count` unique organizations with the rich schema
    Yandex publishes via its internal `/maps/api/search` endpoint
    (phones, coordinates, hours, services, photos, metro, ИНН, etc.).
    """
    try:
        action = YandexMapsExtractAction()
        organizations = await action.execute(
            query=request.query,
            region_id=request.region_id,
            city_slug=request.city_slug,
            target_count=request.target_count,
            include_raw=request.include_raw,
        )
    except YandexCaptchaError as exc:
        raise HTTPException(status_code=503, detail=f"yandex captcha: {exc}") from exc
    except Exception as exc:  # noqa: BLE001 — surface upstream errors uniformly
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return YandexMapsExtractResponse(
        organizations=organizations,
        total=len(organizations),
        query=request.query,
        region_id=request.region_id,
    )


@router.post("/reviews", response_model=YandexMapsReviewsResponse)
async def fetch_reviews(request: YandexMapsReviewsRequest) -> YandexMapsReviewsResponse:
    """Fetch reviews for a single organization via observation-and-replay.

    Launches a browser session against the org's `/reviews/` page, observes the
    actual `fetchReviews` XHR URLs the SPA fires, and replays them in the same
    session so cookies and CSRF token are honoured automatically.
    """
    try:
        action = YandexMapsReviewsAction()
        reviews = await action.execute(
            business_oid=request.business_oid,
            seoname=request.seoname,
            count=request.count,
            ranking=request.ranking,
            pages=request.pages,
            include_raw=request.include_raw,
        )
    except YandexCaptchaError as exc:
        raise HTTPException(status_code=503, detail=f"yandex captcha: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return YandexMapsReviewsResponse(
        reviews=reviews,
        total=len(reviews),
        business_oid=request.business_oid,
    )
