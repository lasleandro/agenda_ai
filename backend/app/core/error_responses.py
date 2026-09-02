"""Safe, structured API errors for authentication flows."""

from fastapi.responses import JSONResponse


def error_response(status_code: int, code: str, message: str) -> JSONResponse:
    """Build the project's `{data, error}` response envelope."""
    return JSONResponse(
        status_code=status_code,
        content={"data": None, "error": {"code": code, "message": message}},
    )
