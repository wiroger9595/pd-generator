from fastapi import APIRouter, Response

router = APIRouter(tags=["Health"])


@router.api_route("/health", methods=["GET", "HEAD"])
async def health():
    return Response(content="ok", media_type="text/plain")
