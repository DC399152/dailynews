from __future__ import annotations

from collections.abc import Generator
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.errors import APIError
from app.api.schemas import (
    AgentRunResponse,
    DigestResponse,
    SubscriptionResponse,
    SubscriptionUpsert,
    ToolCallResponse,
    UserCreate,
    UserResponse,
)
from app.db.models import AgentRun, Digest, RunStatus, Subscription, ToolCallRecord, User
from app.db.session import SessionFactory
from app.services.digest import DigestService

router = APIRouter(prefix="/api")


def get_session(request: Request) -> Generator[Session, None, None]:
    factory: SessionFactory = request.app.state.sessions
    with factory() as session:
        yield session


def get_digest_service(request: Request) -> DigestService:
    return request.app.state.digest_service


SessionDep = Annotated[Session, Depends(get_session)]
DigestServiceDep = Annotated[DigestService, Depends(get_digest_service)]


def require_user(session: Session, user_id: str) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise APIError(404, "user_not_found", f"User does not exist: {user_id}")
    return user


def run_response(run: AgentRun, digest_id: str | None = None) -> AgentRunResponse:
    if digest_id is None and run.digest is not None:
        digest_id = run.digest.id
    return AgentRunResponse(
        id=run.id,
        user_id=run.user_id,
        status=run.status,
        model=run.model,
        turn_count=run.turn_count,
        tool_call_count=run.tool_call_count,
        input_tokens=run.input_tokens,
        output_tokens=run.output_tokens,
        error_code=run.error_code,
        error_message=run.error_message,
        digest_id=digest_id,
        created_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
    )


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, session: SessionDep) -> User:
    user = User(
        id=payload.user_id,
        identity=payload.identity,
        email=payload.email,
        timezone=payload.timezone,
    )
    session.add(user)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise APIError(409, "user_conflict", "User ID or email already exists") from exc
    session.refresh(user)
    return user


@router.get("/users/{user_id}", response_model=UserResponse)
def get_user(user_id: str, session: SessionDep) -> User:
    return require_user(session, user_id)


@router.put("/users/{user_id}/subscription", response_model=SubscriptionResponse)
def upsert_subscription(
    user_id: str,
    payload: SubscriptionUpsert,
    session: SessionDep,
) -> Subscription:
    require_user(session, user_id)
    subscription = session.get(Subscription, user_id)
    if subscription is None:
        subscription = Subscription(user_id=user_id)
        session.add(subscription)
    subscription.topics = payload.topics
    subscription.keywords = payload.keywords
    subscription.excluded_keywords = payload.excluded_keywords
    subscription.delivery_time = payload.delivery_time
    subscription.enabled = payload.enabled
    session.commit()
    session.refresh(subscription)
    return subscription


@router.get("/users/{user_id}/subscription", response_model=SubscriptionResponse)
def get_subscription(user_id: str, session: SessionDep) -> Subscription:
    require_user(session, user_id)
    subscription = session.get(Subscription, user_id)
    if subscription is None:
        raise APIError(404, "subscription_not_found", "User has no subscription")
    return subscription


@router.post(
    "/users/{user_id}/digest-runs",
    response_model=AgentRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_digest_run(
    user_id: str,
    background_tasks: BackgroundTasks,
    session: SessionDep,
    service: DigestServiceDep,
) -> AgentRunResponse:
    require_user(session, user_id)
    subscription = session.get(Subscription, user_id)
    if subscription is None or not subscription.enabled:
        raise APIError(
            409,
            "subscription_unavailable",
            "An enabled subscription is required to start a digest",
        )
    existing = session.scalar(
        select(AgentRun).where(
            AgentRun.user_id == user_id,
            AgentRun.status.in_((RunStatus.PENDING, RunStatus.RUNNING)),
        )
    )
    if existing is not None:
        raise APIError(409, "run_already_active", "User already has an active digest run")

    run = AgentRun(
        user_id=user_id,
        status=RunStatus.PENDING,
        model=service.model_name,
    )
    session.add(run)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise APIError(409, "run_already_active", "User already has an active digest run") from exc
    session.refresh(run)
    response = run_response(run)
    background_tasks.add_task(service.execute_run, run.id)
    return response


@router.get("/runs/{run_id}", response_model=AgentRunResponse)
def get_run(run_id: str, session: SessionDep) -> AgentRunResponse:
    run = session.get(AgentRun, run_id)
    if run is None:
        raise APIError(404, "run_not_found", f"Run does not exist: {run_id}")
    return run_response(run)


@router.get("/runs/{run_id}/tool-calls", response_model=list[ToolCallResponse])
def list_tool_calls(
    run_id: str,
    session: SessionDep,
) -> list[ToolCallRecord]:
    if session.get(AgentRun, run_id) is None:
        raise APIError(404, "run_not_found", f"Run does not exist: {run_id}")
    return list(
        session.scalars(
            select(ToolCallRecord)
            .where(ToolCallRecord.run_id == run_id)
            .order_by(ToolCallRecord.sequence)
        )
    )


@router.get("/users/{user_id}/digests", response_model=list[DigestResponse])
def list_digests(user_id: str, session: SessionDep) -> list[Digest]:
    require_user(session, user_id)
    return list(
        session.scalars(
            select(Digest).where(Digest.user_id == user_id).order_by(Digest.created_at.desc())
        )
    )


@router.get("/digests/{digest_id}", response_model=DigestResponse)
def get_digest(digest_id: str, session: SessionDep) -> Digest:
    digest = session.get(Digest, digest_id)
    if digest is None:
        raise APIError(404, "digest_not_found", f"Digest does not exist: {digest_id}")
    return digest
