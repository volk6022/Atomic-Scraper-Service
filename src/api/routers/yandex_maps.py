from fastapi import APIRouter, Depends, HTTPException
from src.domain.models.requests import (
    YandexMapsExtractRequest,
    YandexMapsExtractResponse,
)
from src.actions.yandex_maps import YandexMapsExtractAction
from src.api.auth import get_api_key

router = APIRouter(dependencies=[Depends(get_api_key)])


@router.post("/extract", response_model=YandexMapsExtractResponse)
async def extract_businesses(request: YandexMapsExtractRequest):
    """
    Extract business data from Yandex Maps based on category and location.
    """
    try:
        action = YandexMapsExtractAction()

        businesses = await action.execute(
            category=request.category, center=request.center, radius=request.radius
        )

        return YandexMapsExtractResponse(
            businesses=[biz.model_dump() for biz in businesses],
            total=len(businesses),
            category=request.category,
            center=request.center,
            radius=request.radius,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
