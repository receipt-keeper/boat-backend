import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import firebase_admin
from firebase_admin import auth, credentials
from firebase_admin import exceptions as firebase_exceptions

from app.core.config.settings import Settings
from app.core.domain.exceptions import ValidationError
from app.modules.auth.application.ports.external_identity_verifier import ExternalIdentityVerifier
from app.modules.auth.domain.exceptions import AuthenticationError
from app.modules.auth.domain.model import ExternalIdentity


@dataclass(frozen=True)
class FirebaseIdentityMapping:
    app_name: str
    project_id_option: str
    uid_claim: str
    subject_claim: str
    email_claim: str
    email_verified_claim: str
    name_claim: str
    namespace_claim: str
    sign_in_provider_claim: str
    # Maps raw Firebase sign_in_provider ("google.com") -> clean name ("google").
    # Keys are the allowlist; any raw value absent from the map is rejected.
    provider_normalization_map: dict[str, str]

    @classmethod
    def from_settings(cls, settings: Settings) -> "FirebaseIdentityMapping":
        return cls(
            app_name=settings.firebase_app_name,
            project_id_option=settings.firebase_project_id_option,
            uid_claim=settings.firebase_uid_claim,
            subject_claim=settings.firebase_subject_claim,
            email_claim=settings.firebase_email_claim,
            email_verified_claim=settings.firebase_email_verified_claim,
            name_claim=settings.firebase_name_claim,
            namespace_claim=settings.firebase_namespace_claim,
            sign_in_provider_claim=settings.firebase_sign_in_provider_claim,
            provider_normalization_map=settings.firebase_provider_normalization_map,
        )

    def subject_from(self, claims: Mapping[str, Any]) -> str | None:
        return self._string_claim(claims, self.uid_claim) or self._string_claim(
            claims,
            self.subject_claim,
        )

    def email_from(self, claims: Mapping[str, Any]) -> str | None:
        return self._string_claim(claims, self.email_claim)

    def email_verified_from(self, claims: Mapping[str, Any]) -> bool:
        return claims.get(self.email_verified_claim) is True

    def name_from(self, claims: Mapping[str, Any]) -> str | None:
        return self._string_claim(claims, self.name_claim)

    def raw_provider_from(self, claims: Mapping[str, Any]) -> str | None:
        """Return the raw Firebase sign_in_provider claim value (e.g. 'google.com')."""
        namespace_claim = claims.get(self.namespace_claim)
        if isinstance(namespace_claim, Mapping):
            provider = self._string_claim(namespace_claim, self.sign_in_provider_claim)
            if provider is not None:
                return provider
        return None

    def normalize_provider(self, raw_provider: str) -> str | None:
        """Map raw provider to clean name; return None if not in allowlist."""
        return self.provider_normalization_map.get(raw_provider)

    def _string_claim(self, claims: Mapping[str, Any], key: str) -> str | None:
        value = claims.get(key)
        if isinstance(value, str) and value:
            return value
        return None


class FirebaseExternalIdentityVerifier(ExternalIdentityVerifier):
    def __init__(
        self,
        *,
        app: firebase_admin.App,
        check_revoked: bool,
        identity_mapping: FirebaseIdentityMapping,
    ) -> None:
        self._app = app
        self._check_revoked = check_revoked
        self._identity_mapping = identity_mapping

    @classmethod
    def from_settings(cls, settings: Settings) -> "FirebaseExternalIdentityVerifier":
        identity_mapping = FirebaseIdentityMapping.from_settings(settings)
        try:
            app = firebase_admin.get_app(identity_mapping.app_name)
        except ValueError:
            credential = (
                credentials.Certificate(settings.firebase_credentials_path)
                if settings.firebase_credentials_path
                else credentials.ApplicationDefault()
            )
            options = None
            if settings.firebase_project_id:
                options = {identity_mapping.project_id_option: settings.firebase_project_id}
            app = firebase_admin.initialize_app(
                credential=credential,
                options=options,
                name=identity_mapping.app_name,
            )
        return cls(
            app=app,
            check_revoked=settings.firebase_check_revoked,
            identity_mapping=identity_mapping,
        )

    async def verify(self, provider_token: str) -> ExternalIdentity:
        try:
            claims = await asyncio.to_thread(
                auth.verify_id_token,
                provider_token,
                app=self._app,
                check_revoked=self._check_revoked,
            )
        except firebase_exceptions.FirebaseError as exc:
            raise AuthenticationError() from exc

        return self._to_external_identity(claims)

    def _to_external_identity(self, claims: Mapping[str, Any]) -> ExternalIdentity:
        subject = self._identity_mapping.subject_from(claims)
        if subject is None:
            raise AuthenticationError()
        raw_provider = self._identity_mapping.raw_provider_from(claims)
        if raw_provider is None:
            raise AuthenticationError()
        clean_provider = self._identity_mapping.normalize_provider(raw_provider)
        if clean_provider is None:
            raise AuthenticationError()

        email = self._identity_mapping.email_from(claims)
        normalized_email = None if email is None else email.strip().lower()
        try:
            return ExternalIdentity.create(
                issuer=clean_provider,
                subject=subject,
                email=email,
                name=self._identity_mapping.name_from(claims),
                provider=clean_provider,
                normalized_email=normalized_email,
                email_verified=self._identity_mapping.email_verified_from(claims),
            )
        except ValidationError as exc:
            raise AuthenticationError() from exc
