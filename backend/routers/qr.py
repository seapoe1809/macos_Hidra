"""QR-code endpoint (design step 7: a QR of the key usable as ID)."""

import io

import qrcode
import qrcode.image.svg as svg
from fastapi import APIRouter, Query
from fastapi.responses import Response

router = APIRouter(prefix="/api/qr", tags=["qr"])


@router.get("")
def qr(data: str = Query(..., description="Text/key to encode")):
    """Return an SVG QR code for the given data (no PIL dependency)."""
    img = qrcode.make(data, image_factory=svg.SvgImage)
    buf = io.BytesIO()
    img.save(buf)
    return Response(content=buf.getvalue(), media_type="image/svg+xml")
