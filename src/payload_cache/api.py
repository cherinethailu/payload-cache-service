"""HTTP endpoints."""

import uuid
from collections.abc import Iterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlmodel import Session

from payload_cache.schemas import PayloadCreate, PayloadCreated, PayloadRead
from payload_cache.service import PayloadService

router = APIRouter()


def get_session(request: Request) -> Iterator[Session]:
    with Session(request.app.state.engine) as session:
        yield session


def get_service(
    request: Request, session: Annotated[Session, Depends(get_session)]
) -> PayloadService:
    return PayloadService(session, request.app.state.transformer)


ServiceDep = Annotated[PayloadService, Depends(get_service)]


@router.post(
    "/payload",
    response_model=PayloadCreated,
    status_code=status.HTTP_201_CREATED,
    responses={status.HTTP_200_OK: {"model": PayloadCreated, "description": "Already exists"}},
)
def create_payload(body: PayloadCreate, response: Response, service: ServiceDep) -> PayloadCreated:
    payload, created = service.create_payload(body.list_1, body.list_2)
    if not created:
        response.status_code = status.HTTP_200_OK
        return PayloadCreated(id=payload.id, message="Payload already exists")
    return PayloadCreated(id=payload.id, message="Payload created")


@router.get("/payload/{payload_id}", response_model=PayloadRead)
def read_payload(payload_id: uuid.UUID, service: ServiceDep) -> PayloadRead:
    payload = service.get_payload(payload_id)
    if payload is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Payload not found")
    return PayloadRead(output=payload.output)


@router.get("/health", include_in_schema=False)
def health() -> dict[str, str]:
    return {"status": "ok"}
