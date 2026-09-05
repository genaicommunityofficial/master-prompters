from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from app.schemas.schemas import AuthResponse, LoginPrepareResponse, QrLoginRequest, ParticipantInfo
from app.security.auth import get_current_participant
from app.services import auth_service
from app.services.auth_service import AuthError
from app.services.session_guard import ALREADY_SIGNED_IN_MSG
from app.services.qr_service import QrDecodeError, decode_qr_image

router = APIRouter(prefix="/api/auth", tags=["auth"])
_bearer = HTTPBearer(auto_error=False)


def _auth_http(exc: AuthError) -> HTTPException:
    detail = str(exc)
    code = 409 if detail == ALREADY_SIGNED_IN_MSG else 401
    return HTTPException(status_code=code, detail=detail)


def _login(competition_id: str, qr_message: str, registration_number: str) -> AuthResponse:
    try:
        result = auth_service.login_with_qr_message(
            qr_message=qr_message,
            competition_id=competition_id,
            registration_number=registration_number,
        )
    except AuthError as exc:
        raise _auth_http(exc) from exc
    return AuthResponse(
        token=result["token"],
        participant=ParticipantInfo(**result["participant"]),
    )


@router.post("/login/qr", response_model=AuthResponse)
async def login_with_qr_image(
    competition_id: str,
    registration_number: Annotated[str, Query(min_length=1, max_length=128)],
    image: Annotated[UploadFile, File(description="QR code image file")],
) -> AuthResponse:
    data = await image.read()
    if image.content_type and not str(image.content_type).startswith("image/"):
        raise HTTPException(status_code=400, detail="Please upload an image file.")
    try:
        qr_message = decode_qr_image(data)
    except QrDecodeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _login(competition_id, qr_message, registration_number)


@router.post("/login/message", response_model=AuthResponse)
async def login_with_qr_message(body: QrLoginRequest) -> AuthResponse:
    if not body.qr_message:
        raise HTTPException(status_code=400, detail="QR message is required.")
    if not body.registration_number:
        raise HTTPException(status_code=400, detail="Registration number is required.")
    return _login(body.competition_id, body.qr_message, body.registration_number)


class RegistrationNumberLoginRequest(BaseModel):
    registration_number: str
    competition_id: str


@router.post("/login/registration-number", response_model=LoginPrepareResponse)
async def registration_number_login(body: RegistrationNumberLoginRequest) -> LoginPrepareResponse:
    """Look up a registration number. Testers / admin extras sign in immediately."""
    if not body.registration_number.strip():
        raise HTTPException(status_code=400, detail="Registration number is required.")
    try:
        result = auth_service.login_with_registration_number(
            registration_number=body.registration_number,
            competition_id=body.competition_id,
        )
    except AuthError as exc:
        raise _auth_http(exc) from exc
    participant = result.get("participant")
    return LoginPrepareResponse(
        requires_qr=bool(result.get("requires_qr")),
        token=result.get("token"),
        participant=ParticipantInfo(**participant) if participant else None,
        display_name=result.get("display_name"),
    )


@router.post("/logout")
async def logout(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    payload: dict = Depends(get_current_participant),
) -> dict:
    token = credentials.credentials if credentials else ""
    try:
        auth_service.logout(payload["sub"], token)
    except AuthError as exc:
        raise _auth_http(exc) from exc
    return {"ok": True}


@router.get("/me", response_model=dict)
async def me(payload: dict = Depends(get_current_participant)) -> dict:
    return payload
