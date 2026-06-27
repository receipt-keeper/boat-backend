from pydantic import ConfigDict, Field

from app.core.http.responses import AppBaseModel, CursorPaginationResponse
from app.modules.credits.domain import (
    CreditAction,
    CreditBalance,
    CreditReason,
    CreditTransaction,
)


class CreditsResponse(AppBaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "totalGrantedCount": 10,
                    "usedCount": 7,
                    "remainingCount": 3,
                }
            ]
        },
    )

    total_granted_count: int = Field(alias="totalGrantedCount", description="지금까지 받은 횟수.")
    used_count: int = Field(alias="usedCount", description="이미 사용한 횟수.")
    remaining_count: int = Field(alias="remainingCount", description="남은 횟수.")

    @classmethod
    def from_domain(cls, balance: CreditBalance) -> "CreditsResponse":
        return cls(
            totalGrantedCount=balance.total_granted_count,
            usedCount=balance.used_count,
            remainingCount=balance.remaining_count,
        )


class CreditTransactionResponse(AppBaseModel):
    reason: CreditReason = Field(description="크레딧이 바뀐 이유.")
    action: CreditAction = Field(description="크레딧 변화 방향. grant는 추가 지급을 뜻한다.")
    amount: int = Field(description="추가되거나 차감된 횟수.")
    created_at: str = Field(alias="createdAt", description="반영 시각.")

    @classmethod
    def from_domain(cls, transaction: CreditTransaction) -> "CreditTransactionResponse":
        return cls(
            reason=transaction.reason,
            action=transaction.action,
            amount=transaction.amount,
            createdAt=transaction.created_at.isoformat(),
        )


class CreditTransactionListQuery(AppBaseModel):
    model_config = ConfigDict(frozen=True)

    cursor: str | None = Field(
        default=None,
        description="다음 목록 조회용 커서. 첫 조회에서는 보내지 않는다.",
        min_length=1,
        max_length=200,
    )
    limit: int = Field(default=20, description="응답할 최대 내역 수.", ge=1, le=50)


class CreditTransactionsResponse(AppBaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "transactions": [
                        {
                            "reason": "quizReward",
                            "action": "grant",
                            "amount": 10,
                            "createdAt": "2026-06-26T00:00:00",
                        }
                    ],
                    "pagination": {
                        "nextCursor": None,
                        "hasNext": False,
                        "limit": 20,
                        "totalCount": 1,
                    },
                }
            ]
        },
    )

    transactions: list[CreditTransactionResponse] = Field(description="크레딧 지급/사용 내역.")
    pagination: CursorPaginationResponse = Field(description="커서 기반 목록 정보.")
