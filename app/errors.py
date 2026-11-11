"""统一错误类型与错误码。

响应体固定为 {"error": {"code": "...", "message": "...", "field"?: "..."}}
"""
from __future__ import annotations


class ApiError(Exception):
    status = 400
    code = "invalid_request"

    def __init__(self, message: str, *, code: str | None = None, status: int | None = None,
                 field: str | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if status:
            self.status = status
        self.field = field

    def payload(self) -> dict:
        err = {"code": self.code, "message": self.message}
        if self.field:
            err["field"] = self.field
        return {"error": err}


def invalid(message: str, field: str | None = None) -> ApiError:
    return ApiError(message, code="invalid_request", status=400, field=field)


def unauthenticated(message: str = "请先登录") -> ApiError:
    return ApiError(message, code="unauthenticated", status=401)


def forbidden(message: str = "无权执行该操作") -> ApiError:
    return ApiError(message, code="forbidden", status=403)


def pending_approval(message: str = "账号正在等待班委审批") -> ApiError:
    return ApiError(message, code="pending_approval", status=403)


def not_found(message: str = "资源不存在") -> ApiError:
    return ApiError(message, code="not_found", status=404)


def conflict(message: str, field: str | None = None) -> ApiError:
    return ApiError(message, code="conflict", status=409, field=field)


def rule_violation(message: str, field: str | None = None) -> ApiError:
    return ApiError(message, code="rule_violation", status=422, field=field)


def rate_limited(message: str = "尝试过于频繁，请稍后再试") -> ApiError:
    return ApiError(message, code="rate_limited", status=429)


def too_large(message: str = "请求体过大") -> ApiError:
    return ApiError(message, code="payload_too_large", status=413)


def internal(message: str = "服务端内部错误") -> ApiError:
    return ApiError(message, code="internal_error", status=500)
