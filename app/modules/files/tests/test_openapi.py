from app.core.config.settings import Settings
from app.main import create_app


def test_openapi_exposes_file_and_profile_image_paths_without_signed_url_contracts() -> None:
    schema = create_app(
        Settings(
            jwt_secret_key="x" * 48,
            jwt_issuer="boat-backend-test",
            jwt_audience="boat-api-test",
        )
    ).openapi()
    paths = schema["paths"]

    assert "/api/v1/files" in paths
    assert "/api/v1/files/{file_id}" in paths
    assert "/api/v1/files/{file_id}/content" in paths
    assert "/api/v1/users/{user_id}/profile-image" not in paths
    assert "/api/v1/users/me/profile-image" in paths
    assert {"post"}.issubset(paths["/api/v1/files"])
    assert {"get", "delete"}.issubset(paths["/api/v1/files/{file_id}"])
    assert {"get"}.issubset(paths["/api/v1/files/{file_id}/content"])
    assert "409" not in paths["/api/v1/files/{file_id}"]["delete"]["responses"]
    assert {"put", "delete"}.issubset(paths["/api/v1/users/me/profile-image"])
    assert not any("signed" in path or "ticket" in path or "presign" in path for path in paths)


def test_openapi_descriptions_are_app_developer_friendly() -> None:
    schema = create_app(
        Settings(
            jwt_secret_key="x" * 48,
            jwt_issuer="boat-backend-test",
            jwt_audience="boat-api-test",
        )
    ).openapi()
    paths = schema["paths"]
    descriptions = [
        paths["/api/v1/auth/login"]["post"]["description"],
        paths["/api/v1/auth/refresh"]["post"]["description"],
        paths["/api/v1/auth/logout"]["post"]["description"],
        paths["/api/v1/users/me"]["get"]["description"],
        paths["/api/v1/users/me/profile-image"]["put"]["description"],
        paths["/api/v1/users/me/profile-image"]["delete"]["description"],
        paths["/api/v1/users/me"]["delete"]["description"],
        paths["/api/v1/files"]["post"]["description"],
        paths["/api/v1/files/{file_id}"]["get"]["description"],
        paths["/api/v1/files/{file_id}/content"]["get"]["description"],
        paths["/api/v1/files/{file_id}"]["delete"]["description"],
    ]

    forbidden_terms = (
        "credential",
        "session",
        "external identity",
        "트랜잭션",
        "롤백",
        "응답 본문",
        "바이너리",
        "row",
        "DB",
        "opaque",
        "rotate",
        "revoke",
        "내가",
        "앱 화면",
        "때 사용",
    )

    assert not [
        term for description in descriptions for term in forbidden_terms if term in description
    ]
    assert "프로필 이미지" not in paths["/api/v1/files/{file_id}"]["delete"]["description"]


def test_openapi_response_schemas_include_examples() -> None:
    schema = create_app(
        Settings(
            jwt_secret_key="x" * 48,
            jwt_issuer="boat-backend-test",
            jwt_audience="boat-api-test",
        )
    ).openapi()
    schemas = schema["components"]["schemas"]

    for schema_name in (
        "AuthTokenResponse",
        "CurrentUserResponse",
        "ProfileImageResponse",
        "UploadedFileResponse",
        "UploadedFilesResponse",
        "FileMetadataResponse",
    ):
        assert schemas[schema_name]["examples"]


def test_openapi_request_schemas_include_examples() -> None:
    schema = create_app(
        Settings(
            jwt_secret_key="x" * 48,
            jwt_issuer="boat-backend-test",
            jwt_audience="boat-api-test",
        )
    ).openapi()
    schemas = schema["components"]["schemas"]

    for schema_name in (
        "LoginRequest",
        "RefreshTokenRequest",
        "SetProfileImageRequest",
    ):
        assert schemas[schema_name]["examples"]

    upload_request_body = schema["paths"]["/api/v1/files"]["post"]["requestBody"]
    multipart = upload_request_body["content"]["multipart/form-data"]
    assert multipart["examples"]

    upload_body_schema = schemas["Body_upload_file_api_v1_files_post"]
    assert (
        upload_body_schema["properties"]["files"]["items"]["contentMediaType"]
        == "application/octet-stream"
    )
    assert set(upload_body_schema["properties"]) == {"files"}
