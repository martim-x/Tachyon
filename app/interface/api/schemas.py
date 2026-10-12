from pydantic import BaseModel, ConfigDict, Field


class ErrorDetail(BaseModel):
    field: str
    issue: str


class ErrorContent(BaseModel):
    code: str
    message: str
    detail: list[ErrorDetail] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    error: ErrorContent

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Проверка данных не пройдена",
                    "detail": [
                        {
                            "field": "amount",
                            "issue": "Значение должно быть больше нуля",
                        }
                    ],
                }
            }
        }
    )
