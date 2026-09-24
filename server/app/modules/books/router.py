from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request

from app.core.errors import HttpError

from .schemas import BOOK_STATUSES, STATUS_MESSAGE, BookStatus, CreateBookIn, UpdateStatusIn
from .service import BookService

router = APIRouter(prefix="/books", tags=["books"])


def get_service(request: Request) -> BookService:
    service: BookService = request.app.state.book_service
    return service


def list_query(status: str | None = None) -> BookStatus | None:
    """Validate ?status=. Unknown query params are ignored (contract 2.4)."""
    if status is None:
        return None
    if status not in BOOK_STATUSES:
        raise HttpError(
            400, "VALIDATION_ERROR", "Invalid query parameters", [{"path": "status", "message": STATUS_MESSAGE}]
        )
    return status  # type: ignore[return-value]


Service = Annotated[BookService, Depends(get_service)]
StatusFilter = Annotated[BookStatus | None, Depends(list_query)]


# NOTE: /stats is registered before /{book_id} so "stats" is never treated as an id.
@router.get("/stats")
def book_stats(service: Service) -> dict[str, Any]:
    return {"data": service.stats()}


@router.get("")
def list_books(status: StatusFilter, service: Service) -> dict[str, Any]:
    return {"data": service.list(status)}


@router.post("", status_code=201)
def create_book(body: CreateBookIn, service: Service) -> dict[str, Any]:
    return {"data": service.create(body)}


@router.patch("/{book_id}")
def update_book_status(book_id: str, body: UpdateStatusIn, service: Service) -> dict[str, Any]:
    return {"data": service.update_status(book_id, body.status)}
