"""Cookie-based authentication, activation, and password recovery routes."""

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies import require_authenticated, require_platform_admin
from app.core import error_codes
from app.core.error_responses import error_response
from app.core.security import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    SESSION_COOKIE_NAME,
    cookie_domain,
    cookie_samesite,
    cookie_secure,
    create_access_token,
)
from app.core.settings import get_int
from app.database import SessionLocal
from app.models import ImpersonationLog, Professional, User
from app.models.auth_action_token import ACCOUNT_ACTIVATION, PASSWORD_RESET
from app.models.professional import TENANT_STATUS_ACTIVE, TENANT_STATUS_ARCHIVED
from app.services.auth_emails import enqueue_auth_email
from app.services.auth_security import rate_limit_exceeded, record_auth_event
from app.services.operational_events import record_event
from app.services.auth_tokens import ActionTokenError, consume_action_token
from app.services.email_identity import InvalidEmailError, normalize_email
from app.services.password_policy import (
    PasswordPolicyError,
    hash_password,
    normalize_password,
    verify_password,
)
from app.services.tenant_features import COMMERCIAL_FINANCIALS, is_tenant_feature_enabled

router = APIRouter(prefix="/api/auth", tags=["auth"])
_DUMMY_PASSWORD_HASH = hash_password("not-a-real-login-password")


def get_db() -> Session:
    """Provide one database transaction context for an auth request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=128)


class PasswordRequest(BaseModel):
    password: str = Field(min_length=1, max_length=128)
    password_confirmation: str = Field(min_length=1, max_length=128)


class ActivateRequest(PasswordRequest):
    token: str = Field(min_length=20, max_length=512)


class ResetPasswordRequest(PasswordRequest):
    token: str = Field(min_length=20, max_length=512)


class ForgotPasswordRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)


class ImpersonateRequest(BaseModel):
    professional_id: uuid.UUID
    # Required to impersonate a suspended/archived tenant (otherwise 409).
    confirm: bool = False


def _source_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _issue_session_cookie(
    response: Response,
    *,
    user: User,
    professional_id: uuid.UUID | None,
    impersonating: bool = False,
) -> None:
    access_token = create_access_token(
        data={
            "sub": str(user.id),
            "professional_id": str(professional_id) if professional_id else None,
            "impersonating": impersonating,
            "auth_version": user.auth_version,
        }
    )
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=access_token,
        httponly=True,
        secure=cookie_secure(),
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
        domain=cookie_domain(),
        samesite=cookie_samesite(),
    )
    response.headers["Cache-Control"] = "no-store"


@router.post("/login")
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """Authenticate an active user without exposing account existence."""
    source_ip = _source_ip(request)
    try:
        email = normalize_email(body.email)
    except InvalidEmailError:
        email = body.email.strip().lower()

    if rate_limit_exceeded(
        db,
        event_type="login_failed",
        email=email,
        source_ip=source_ip,
        limit=get_int("AUTH_LOGIN_MAX_ATTEMPTS", 10),
        window=timedelta(minutes=get_int("AUTH_LOGIN_WINDOW_MINUTES", 15)),
    ):
        return error_response(429, error_codes.RATE_LIMITED, "Tente novamente mais tarde.")

    user = db.query(User).filter(User.email == email, User.status == "active").first()
    password_hash = user.hashed_password if user and user.hashed_password else _DUMMY_PASSWORD_HASH
    verified, needs_rehash = verify_password(normalize_password(body.password), password_hash)
    if user is None or not verified:
        record_auth_event(
            db,
            event_type="login_failed",
            user_id=user.id if user else None,
            email=email,
            source_ip=source_ip,
        )
        db.commit()
        return error_response(401, error_codes.INVALID_CREDENTIALS, "Email ou senha inválidos.")

    if user.role == "professional" and user.professional_id is not None:
        tenant = db.get(Professional, user.professional_id)
        if tenant is not None and tenant.status != TENANT_STATUS_ACTIVE:
            record_auth_event(
                db,
                event_type="login_blocked_tenant_inactive",
                user_id=user.id,
                email=user.email,
                source_ip=source_ip,
                metadata={"tenant_status": tenant.status},
            )
            db.commit()
            code = (
                error_codes.TENANT_ARCHIVED
                if tenant.status == TENANT_STATUS_ARCHIVED
                else error_codes.TENANT_SUSPENDED
            )
            return error_response(
                403, code, "Acesso indisponível no momento. Fale com o administrador."
            )

    if needs_rehash:
        user.hashed_password = hash_password(normalize_password(body.password))
    record_auth_event(
        db,
        event_type="login_succeeded",
        user_id=user.id,
        email=user.email,
        source_ip=source_ip,
    )
    db.commit()
    _issue_session_cookie(response, user=user, professional_id=user.professional_id)
    return {"email": user.email, "role": user.role}


@router.post("/forgot-password", status_code=202)
def forgot_password(
    body: ForgotPasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Queue reset mail without revealing account eligibility."""
    try:
        email = normalize_email(body.email)
    except InvalidEmailError:
        return error_response(422, error_codes.INVALID_EMAIL, "Informe um email válido.")

    source_ip = _source_ip(request)
    if rate_limit_exceeded(
        db,
        event_type="password_reset_requested",
        email=email,
        source_ip=source_ip,
        limit=get_int("AUTH_EMAIL_MAX_SENDS_PER_HOUR", 5),
        window=timedelta(hours=1),
    ):
        return error_response(429, error_codes.RATE_LIMITED, "Tente novamente mais tarde.")

    user = db.query(User).filter(User.email == email, User.status == "active").first()
    if user is not None:
        enqueue_auth_email(db, user=user, purpose=PASSWORD_RESET)
    record_auth_event(
        db,
        event_type="password_reset_requested",
        user_id=user.id if user else None,
        email=email,
        source_ip=source_ip,
    )
    db.commit()
    return {"message": "Se existir uma conta ativa para este email, você receberá instruções."}


@router.post("/activate")
def activate_account(
    body: ActivateRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Consume one activation link and establish the first account password."""
    if body.password != body.password_confirmation:
        return error_response(400, error_codes.PASSWORD_MISMATCH, "As senhas não coincidem.")
    try:
        consume_action_token(
            db,
            purpose=ACCOUNT_ACTIVATION,
            raw_token=body.token,
            password=body.password,
            source_ip=_source_ip(request),
        )
        db.commit()
    except PasswordPolicyError as exc:
        db.rollback()
        return error_response(400, exc.code, exc.message)
    except ActionTokenError:
        db.rollback()
        return error_response(
            400,
            error_codes.TOKEN_INVALID_OR_EXPIRED,
            "Este link é inválido ou expirou.",
        )
    return {"message": "Conta ativada. Agora você pode entrar."}


@router.post("/reset-password")
def reset_password(
    body: ResetPasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Consume a reset token, invalidate existing sessions, and notify the user."""
    if body.password != body.password_confirmation:
        return error_response(400, error_codes.PASSWORD_MISMATCH, "As senhas não coincidem.")
    try:
        user = consume_action_token(
            db,
            purpose=PASSWORD_RESET,
            raw_token=body.token,
            password=body.password,
            source_ip=_source_ip(request),
        )
        enqueue_auth_email(db, user=user, purpose="password_changed_notice")
        db.commit()
    except PasswordPolicyError as exc:
        db.rollback()
        return error_response(400, exc.code, exc.message)
    except ActionTokenError:
        db.rollback()
        return error_response(
            400,
            error_codes.TOKEN_INVALID_OR_EXPIRED,
            "Este link é inválido ou expirou.",
        )
    return {"message": "Senha redefinida. Entre novamente com a nova senha."}


@router.post("/logout")
def logout(response: Response):
    """Clear the current browser session cookie."""
    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/", domain=cookie_domain())
    response.headers["Cache-Control"] = "no-store"
    return {"message": "Successfully logged out"}


@router.get("/me")
def me(
    response: Response,
    user: dict = Depends(require_authenticated),
    db: Session = Depends(get_db),
):
    """Return the authoritative current identity and selected tenant context."""
    response.headers["Cache-Control"] = "no-store"
    professional_name = None
    features: list[str] = []
    if user["professional_id"] is not None:
        professional_id = uuid.UUID(user["professional_id"])
        professional = db.query(Professional).filter(Professional.id == professional_id).first()
        professional_name = professional.name if professional else None
        if is_tenant_feature_enabled(db, professional_id, COMMERCIAL_FINANCIALS):
            features.append(COMMERCIAL_FINANCIALS)
    return {**user, "professional_name": professional_name, "features": features}


@router.post("/impersonate")
def impersonate(
    body: ImpersonateRequest,
    response: Response,
    admin: dict = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    """Switch a platform-admin session to an auditable tenant context."""
    professional = db.query(Professional).filter(Professional.id == body.professional_id).first()
    if professional is None:
        return error_response(404, error_codes.TENANT_NOT_FOUND, "Tenant não encontrado.")
    admin_user = db.get(User, uuid.UUID(admin["user_id"]))
    if admin_user is None:
        return error_response(401, error_codes.SESSION_INVALID, "Sessão inválida.")

    tenant_inactive = professional.status != TENANT_STATUS_ACTIVE
    if tenant_inactive and not body.confirm:
        return error_response(
            409,
            error_codes.TENANT_INACTIVE_CONFIRM_REQUIRED,
            "Tenant inativo. Confirme para acessar mesmo assim.",
        )

    db.add(ImpersonationLog(admin_user_id=admin_user.id, professional_id=professional.id))
    if tenant_inactive:
        record_event(
            db,
            professional_id=professional.id,
            event_type="tenant.impersonated_while_inactive",
            occurred_at=datetime.now(timezone.utc),
            actor_type="platform_admin",
            actor_id=admin_user.id,
            source_channel="web",
            entity_type="professional",
            entity_id=professional.id,
            correlation_id=uuid.uuid4(),
            payload={"tenant_status": professional.status},
        )
    db.commit()
    _issue_session_cookie(
        response,
        user=admin_user,
        professional_id=professional.id,
        impersonating=True,
    )
    return {"professional_id": str(professional.id), "professional_name": professional.name}


@router.post("/stop-impersonating")
def stop_impersonating(
    response: Response,
    admin: dict = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    """Return a platform admin to its unscoped tenant-selection session."""
    admin_user = db.get(User, uuid.UUID(admin["user_id"]))
    if admin_user is None:
        return error_response(401, error_codes.SESSION_INVALID, "Sessão inválida.")
    _issue_session_cookie(response, user=admin_user, professional_id=None)
    return {"message": "Stopped impersonating"}
