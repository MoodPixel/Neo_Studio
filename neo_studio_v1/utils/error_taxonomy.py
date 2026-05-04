from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx


class NeoStudioError(Exception):
    status_code = 500
    default_message = 'Neo Studio request failed.'

    def __init__(self, message: str | None = None):
        super().__init__(message or self.default_message)


class ValidationError(NeoStudioError):
    status_code = 400
    default_message = 'Validation failed.'


class UnsupportedConfigError(ValidationError):
    default_message = 'Unsupported configuration.'


class NotFoundError(NeoStudioError):
    status_code = 404
    default_message = 'Requested item was not found.'


class BackendUnavailableError(NeoStudioError):
    status_code = 502
    default_message = 'Backend request failed.'


class BackendTimeoutError(NeoStudioError):
    status_code = 504
    default_message = 'Backend request timed out.'


class StorageOperationError(NeoStudioError):
    status_code = 500
    default_message = 'Storage operation failed.'


class DeveloperError(NeoStudioError):
    status_code = 500
    default_message = 'Unexpected internal error.'


@dataclass
class ExceptionDescriptor:
    status_code: int
    user_message: str
    log_level: str


def _clean_message(exc: BaseException) -> str:
    text = str(exc or '').strip()
    return text or exc.__class__.__name__


def describe_exception(exc: BaseException, *, default_message: str = 'Request failed.', default_status: int = 500) -> ExceptionDescriptor:
    message = _clean_message(exc)

    if isinstance(exc, NeoStudioError):
        return ExceptionDescriptor(status_code=int(exc.status_code), user_message=message, log_level='warning' if exc.status_code < 500 else 'error')
    if isinstance(exc, (json.JSONDecodeError, TypeError, ValueError)):
        return ExceptionDescriptor(status_code=400, user_message=message, log_level='warning')
    if isinstance(exc, FileNotFoundError):
        return ExceptionDescriptor(status_code=404, user_message=message or default_message, log_level='warning')
    if isinstance(exc, (TimeoutError, httpx.TimeoutException)):
        user_message = default_message if default_status >= 500 else message
        return ExceptionDescriptor(status_code=504, user_message=user_message, log_level='error')
    if isinstance(exc, (httpx.HTTPStatusError, httpx.RequestError, ConnectionError)):
        user_message = default_message if default_status >= 500 else message
        return ExceptionDescriptor(status_code=502, user_message=user_message, log_level='error')
    if isinstance(exc, (PermissionError, OSError)):
        user_message = default_message if default_status >= 500 else message
        return ExceptionDescriptor(status_code=500, user_message=user_message, log_level='error')

    status_code = default_status if default_status >= 500 else 500
    user_message = default_message if status_code >= 500 else message
    return ExceptionDescriptor(status_code=status_code, user_message=user_message, log_level='error')
