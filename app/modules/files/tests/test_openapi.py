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
    assert {"put", "delete"}.issubset(paths["/api/v1/users/me/profile-image"])
    assert not any("signed" in path or "ticket" in path or "presign" in path for path in paths)
