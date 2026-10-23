"""Evidence HTTP boundary."""

from app.application import evidence as use_cases
from fastapi import APIRouter
from fastapi import Depends, HTTPException, Response
from app.db import Document, SessionLocal
from app.security import authorized, current_user
from app.storage import original_key, store, fitz_open_original
from app.api.dependencies import REVIEW, WRITE
from app.api.contracts import VisualBoxReview

router = APIRouter(tags=["evidence"])


@router.get("/api/location-learning")
def location_learning_history(document_type: str = "", user=Depends(current_user)):
    return use_cases.location_learning_history(document_type=document_type, user=user)


@router.post("/api/location-learning/{sample_id}/disable")
def disable_location_learning(sample_id: str, user=Depends(REVIEW)):
    return use_cases.disable_location_learning(sample_id=sample_id, user=user)


@router.post("/api/documents/{doc_id}/visual-box", status_code=202)
def review_visual_box(doc_id: str, data: VisualBoxReview, user=Depends(REVIEW)):
    return use_cases.review_visual_box(doc_id=doc_id, data=data, user=user)


@router.post("/api/documents/{doc_id}/field-evidence", status_code=202)
def refresh_field_evidence(doc_id: str, user=Depends(WRITE)):
    return use_cases.refresh_field_evidence(doc_id=doc_id, user=user)


@router.get("/api/documents/{doc_id}/pages/{page_number}")
def document_page(doc_id: str, page_number: int, user=Depends(current_user)):
    import fitz

    with SessionLocal() as db:
        d = authorized(db, Document, doc_id, user)
    with fitz_open_original(store().read(original_key(d))) as pdf:
        if page_number < 1 or page_number > len(pdf):
            raise HTTPException(404, "Page not found.")
        page = pdf[page_number - 1]
        scale = min(4, 3200 / max(page.rect.width, page.rect.height))
        image = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False).tobytes(
            "png"
        )
    return Response(
        image, media_type="image/png", headers={"Cache-Control": "no-store"}
    )


@router.get("/api/documents/{doc_id}/evidence/{revision}/{image_id}")
def document_evidence(
    doc_id: str, revision: str, image_id: str, user=Depends(current_user)
):
    with SessionLocal() as db:
        d = authorized(db, Document, doc_id, user)
        from app.field_evidence import evidence_images

        items = evidence_images(d.validation)
        item = next(
            (
                e
                for e in items
                if e.get("available")
                and e.get("revision") == revision
                and e.get("storage_key", "").endswith(
                    "/" + revision + "-" + image_id + ".png"
                )
            ),
            None,
        )
        if not item:
            raise HTTPException(
                404, "Evidence not available for this extraction revision."
            )
    return Response(
        store().read(item["storage_key"]),
        media_type="image/png",
        headers={"Cache-Control": "no-store"},
    )
