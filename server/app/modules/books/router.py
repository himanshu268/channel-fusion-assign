from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request

from .schemas import CreateBookIn, UpdateStatusIn
from .service import BookService

router = APIRouter(prefix="/books", tags=["books"])


def get_service(request: Request) -> BookService:
    service: BookService = request.app.state.book_service
    return service


# NOTE: /stats is registered before /{book_id} so "stats" is never treated as an id.
@router.get("/stats")
def book_stats(service: BookService = Depends(get_service)) -> dict[str, Any]:
    return {"data": service.stats()}


@router.get("")
def list_books(service: BookService = Depends(get_service)) -> dict[str, Any]:
    return {"data": service.list()}


@router.post("", status_code=201)
def create_book(body: CreateBookIn, service: BookService = Depends(get_service)) -> dict[str, Any]:
    return {"data": service.create(body)}


@router.patch("/{book_id}")
def update_book_status(
    book_id: str, body: UpdateStatusIn, service: BookService = Depends(get_service)
) -> dict[str, Any]:
    return {"data": service.update_status(book_id, body.status)}
