"""Error type and handlers. Every error response is JSON: {"error": {"code", "message", ...}}."""
from __future__ import annotations

import logging

import pymysql
from flask import Flask, jsonify
from werkzeug.exceptions import HTTPException

log = logging.getLogger(__name__)


class ApiError(Exception):
    def __init__(self, status: int, message: str, code: str | None = None, **details):
        super().__init__(message)
        self.status = status
        self.message = message
        self.code = code or {400: "bad_request", 401: "unauthorized", 403: "forbidden", 404: "not_found",
                             409: "conflict", 422: "unprocessable", 502: "bad_gateway"}.get(status, "error")
        self.details = details

    def to_response(self):
        body = {"code": self.code, "message": self.message}
        if self.details:
            body["details"] = self.details
        return jsonify({"error": body}), self.status


def not_found(what: str = "Resource") -> ApiError:
    return ApiError(404, f"{what} not found")


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(ApiError)
    def _api_error(err: ApiError):
        return err.to_response()

    @app.errorhandler(pymysql.err.IntegrityError)
    def _integrity(err):
        code = err.args[0] if err.args else None
        if code == 1062:
            return ApiError(409, "That record already exists", code="duplicate").to_response()
        if code in (1451, 1452):
            return ApiError(409, "The record is referenced by, or refers to, data that blocks this change",
                            code="foreign_key").to_response()
        log.exception("integrity error")
        return ApiError(400, "The data violates a database constraint", code="constraint").to_response()

    @app.errorhandler(pymysql.err.OperationalError)
    def _operational(err):
        code = err.args[0] if err.args else None
        if code == 3819:  # CHECK constraint violated
            return ApiError(400, "A value is outside its allowed range", code="check_constraint").to_response()
        if code == 1644:  # SIGNAL from a trigger
            return ApiError(409, str(err.args[1]), code="rule_violation").to_response()
        log.exception("database error")
        return ApiError(503, "The database is unavailable", code="database_unavailable").to_response()

    @app.errorhandler(HTTPException)
    def _http(err: HTTPException):
        return ApiError(err.code or 500, err.description or err.name).to_response()

    @app.errorhandler(Exception)
    def _unexpected(err: Exception):
        log.exception("unhandled error")
        return ApiError(500, "Something went wrong on the server", code="internal").to_response()
