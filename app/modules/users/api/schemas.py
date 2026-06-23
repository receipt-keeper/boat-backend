from pydantic import ConfigDict, Field

from app.core.http.responses import AppBaseModel


class CurrentUserResponse(AppBaseModel):
    """내 정보 조회 응답. 앱이 필요한 사용자 정보만 노출한다."""

    model_config = ConfigDict(populate_by_name=True)

    email: str | None = Field(
        alias="email",
        description="대표 이메일.",
    )
    name: str | None = Field(
        alias="name",
        description="이름.",
    )
    nickname: str | None = Field(
        alias="nickname",
        description="닉네임.",
    )
    profile_image_url: str | None = Field(
        alias="profileImageUrl",
        description="프로필 이미지 URL.",
    )
    marketing_consent: bool = Field(
        alias="marketingConsent",
        description="마케팅 수신 동의 여부.",
    )
    free_analysis_tokens_remaining: int = Field(
        alias="freeAnalysisTokensRemaining",
        description="남은 무료 분석 토큰 수.",
        examples=[3],
    )


class UpdateCurrentUserRequest(AppBaseModel):
    """내 정보 수정 요청. 부분 수정이며 미전달 필드는 기존 값을 유지한다."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    marketing_consent: bool | None = Field(
        default=None,
        alias="marketingConsent",
        description="마케팅 수신 동의. 미전달(null) 시 기존 값을 유지한다.",
    )


class UpdateCurrentUserResponse(AppBaseModel):
    """내 정보 수정 응답. 실제 반영된 값."""

    model_config = ConfigDict(populate_by_name=True)

    marketing_consent: bool = Field(
        alias="marketingConsent",
        description="반영된 마케팅 수신 동의.",
    )
