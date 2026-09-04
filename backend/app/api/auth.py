from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from app.schemas.schemas import AuthResponse, QrLoginRequest, ParticipantInfo
from app.security.auth import get_current_participant
from app.services import auth_service
from app.services.auth_service import AuthError
from app.services.qr_service import QrDecodeError, decode_qr_image

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _login(competition_id: str, qr_message: str) -> AuthResponse:
    result = auth_service.login_with_qr_message(qr_message=qr_message, competition_id=competition_id)
    return AuthResponse(
        token=result["token"],
        participant=ParticipantInfo(**result["participant"]),
    )


@router.post("/login/qr", response_model=AuthResponse)
async def login_with_qr_image(
    competition_id: str,
    image: Annotated[UploadFile, File(description="QR code image file")],
) -> AuthResponse:
    data = await image.read()
    if image.content_type and not str(image.content_type).startswith("image/"):
        raise HTTPException(status_code=400, detail="Please upload an image file.")
    try:
        qr_message = decode_qr_image(data)
    except QrDecodeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _login(competition_id, qr_message)


@router.post("/login/message", response_model=AuthResponse)
async def login_with_qr_message(body: QrLoginRequest) -> AuthResponse:
    if not body.qr_message:
        raise HTTPException(status_code=400, detail="QR message is required.")
    return _login(body.competition_id, body.qr_message)


class TestLoginRequest(BaseModel):
    identifier: str  # email, reg number, or display name
    competition_id: str


class RegistrationNumberLoginRequest(BaseModel):
    registration_number: str
    competition_id: str


@router.post("/login/registration-number", response_model=AuthResponse)
async def registration_number_login(body: RegistrationNumberLoginRequest) -> AuthResponse:
    """Production login using an official registration number."""
    if not body.registration_number.strip():
        raise HTTPException(status_code=400, detail="Registration number is required.")
    try:
        result = auth_service.login_with_registration_number(
            registration_number=body.registration_number,
            competition_id=body.competition_id,
        )
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return AuthResponse(
        token=result["token"],
        participant=ParticipantInfo(**result["participant"]),
    )


@router.post("/login/test", response_model=AuthResponse)
async def test_login(body: TestLoginRequest) -> AuthResponse:
    """Development-only fallback login: accepts email, registration number, or display name."""
    try:
        result = auth_service.login_with_test(
            identifier=body.identifier,
            competition_id=body.competition_id,
        )
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return AuthResponse(
        token=result["token"],
        participant=ParticipantInfo(**result["participant"]),
    )


@router.get("/me", response_model=dict)
async def me(payload: dict = Depends(get_current_participant)) -> dict:
    return payload
