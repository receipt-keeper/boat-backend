import pytest
from sqlalchemy import Index

from app.core.db.base import Base
from app.core.domain.exceptions import ValidationError
from app.modules.auth.infrastructure.persistence import orm as auth_orm
from app.modules.users.domain import model as user_model
from app.modules.users.infrastructure.persistence import orm as users_orm


def test_prd_account_schema_tables_columns_and_constraints_are_declared() -> None:
    assert auth_orm.AuthSession.__tablename__ == "auth_sessions"
    assert users_orm.UserSettings.__tablename__ == "user_settings"

    metadata = Base.metadata

    assert {"auth_sessions", "user_settings"}.issubset(metadata.tables)
    assert "user_entitlements" not in metadata.tables
    assert "user_push_tokens" not in metadata.tables
    assert "notification_enabled" not in metadata.tables["user_settings"].columns
    assert "marketing_consent" not in metadata.tables["user_settings"].columns
    assert "profile_image_url" in metadata.tables["users"].columns
    assert "normalized_email" not in metadata.tables["users"].columns
    assert {"email", "normalized_email", "email_verified"}.issubset(
        metadata.tables["external_identities"].columns.keys()
    )
    assert "session_id" in metadata.tables["refresh_tokens"].columns

    users_indexes = metadata.tables["users"].indexes
    assert not any(_is_partial_unique_normalized_email_index(index) for index in users_indexes)

    external_identity_indexes = metadata.tables["external_identities"].indexes
    assert any(
        _is_verified_external_identity_email_index(index) for index in external_identity_indexes
    )


def test_prd_schema_has_no_future_bc_foreign_keys() -> None:
    future_bc_tables = {"receipts", "files"}
    discovered_targets = {
        foreign_key.column.table.name
        for table_name in (
            "users",
            "user_settings",
            "user_credentials",
            "external_identities",
            "auth_sessions",
            "refresh_tokens",
        )
        for foreign_key in Base.metadata.tables[table_name].foreign_keys
    }

    assert discovered_targets.isdisjoint(future_bc_tables)


def test_users_profile_image_uses_url_as_single_persistence_field() -> None:
    users_table = Base.metadata.tables["users"]

    assert "profile_image_url" in users_table.columns
    assert "profile_image_file_id" not in users_table.columns


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


def _is_partial_unique_normalized_email_index(index: Index) -> bool:
    dialect_options = index.dialect_options["postgresql"]
    return (
        index.unique is True
        and tuple(column.name for column in index.columns) == ("normalized_email",)
        and dialect_options["where"] is not None
    )


def _is_verified_external_identity_email_index(index: Index) -> bool:
    dialect_options = index.dialect_options["postgresql"]
    return (
        index.name == "ix_external_identities_verified_normalized_email"
        and index.unique is False
        and tuple(column.name for column in index.columns) == ("normalized_email",)
        and str(dialect_options["where"])
        == "email_verified IS TRUE AND normalized_email IS NOT NULL"
    )
