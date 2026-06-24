from uuid import uuid4

import pytest
from sqlalchemy import CheckConstraint, Index, UniqueConstraint

from app.core.db.base import Base
from app.core.domain.exceptions import ValidationError
from app.modules.auth.infrastructure.persistence import orm as auth_orm
from app.modules.users.domain import model as user_model
from app.modules.users.infrastructure.persistence import orm as users_orm


def test_prd_account_schema_tables_columns_and_constraints_are_declared() -> None:
    assert auth_orm.AuthSession.__tablename__ == "auth_sessions"
    assert users_orm.UserSettings.__tablename__ == "user_settings"
    assert users_orm.UserEntitlement.__tablename__ == "user_entitlements"
    assert users_orm.UserPushToken.__tablename__ == "user_push_tokens"

    metadata = Base.metadata

    assert {"auth_sessions", "user_settings", "user_entitlements", "user_push_tokens"}.issubset(
        metadata.tables
    )
    assert "profile_image_url" in metadata.tables["users"].columns
    assert "normalized_email" not in metadata.tables["users"].columns
    assert {"email", "normalized_email", "email_verified"}.issubset(
        metadata.tables["external_identities"].columns.keys()
    )
    assert "session_id" in metadata.tables["refresh_tokens"].columns

    users_indexes = metadata.tables["users"].indexes
    assert not any(_is_partial_unique_normalized_email_index(index) for index in users_indexes)

    entitlement_checks = [
        constraint
        for constraint in metadata.tables["user_entitlements"].constraints
        if isinstance(constraint, CheckConstraint)
    ]
    assert any(
        "free_analysis_tokens_remaining >= 0" in str(check.sqltext) for check in entitlement_checks
    )

    push_constraints = metadata.tables["user_push_tokens"].constraints
    assert any(_unique_columns(constraint) == ("fcm_token",) for constraint in push_constraints)
    assert any(
        _unique_columns(constraint) == ("user_id", "device_id") for constraint in push_constraints
    )


def test_prd_schema_has_no_future_bc_foreign_keys() -> None:
    future_bc_tables = {"devices", "receipts", "files"}
    discovered_targets = {
        foreign_key.column.table.name
        for table_name in (
            "users",
            "user_settings",
            "user_entitlements",
            "user_push_tokens",
            "user_credentials",
            "external_identities",
            "auth_sessions",
            "refresh_tokens",
        )
        for foreign_key in Base.metadata.tables[table_name].foreign_keys
    }

    assert discovered_targets.isdisjoint(future_bc_tables)


def test_users_profile_image_file_id_is_reference_state_without_database_fk() -> None:
    users_table = Base.metadata.tables["users"]

    assert "profile_image_file_id" in users_table.columns
    assert not any(
        foreign_key.parent.name == "profile_image_file_id"
        and foreign_key.column.table.name == "files"
        for foreign_key in users_table.foreign_keys
    )


def test_user_domain_uses_email_value_object_and_carries_profile_image_url() -> None:
    user = user_model.User.create(
        name="테스트 사용자",
        email="person@example.com",
        profile_image_url="https://example.com/profile.png",
    )

    assert user.email is not None
    assert user.email.value == "person@example.com"
    assert not hasattr(user, "normalized_email")
    assert user.profile_image_url == "https://example.com/profile.png"


def test_user_domain_rejects_invalid_email() -> None:
    with pytest.raises(ValidationError) as error:
        user_model.User.create(
            name="테스트 사용자",
            email="not-an-email",
        )

    assert [detail.field for detail in error.value.details] == ["email"]


def test_user_entitlement_rejects_negative_free_analysis_tokens() -> None:
    with pytest.raises(ValidationError) as error:
        user_model.UserEntitlement.create(
            user_id=uuid4(),
            free_analysis_tokens_remaining=-1,
        )

    assert [detail.field for detail in error.value.details] == ["freeAnalysisTokensRemaining"]


def _is_partial_unique_normalized_email_index(index: Index) -> bool:
    dialect_options = index.dialect_options["postgresql"]
    return (
        index.unique is True
        and tuple(column.name for column in index.columns) == ("normalized_email",)
        and dialect_options["where"] is not None
    )


def _unique_columns(constraint: object) -> tuple[str, ...]:
    if not isinstance(constraint, UniqueConstraint):
        return ()
    return tuple(column.name for column in constraint.columns)
