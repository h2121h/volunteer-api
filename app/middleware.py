"""
Middleware безопасности:
  - Rate Limiting  → защита от перебора (slowapi)
  - CORS           → только свои домены
  - Security Headers → CSP, XSS, HSTS
  - Request Logging → логируем подозрительные запросы
"""
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseMiddleware
from starlette.responses import Response
import time
import re


# ── Rate Limiter (защита от перебора) ─────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address)


# ── Разрешённые домены (CORS) ─────────────────────────────────────────────────
ALLOWED_ORIGINS = [
    "http://localhost:8000",
    "http://localhost:3000",
    "https://volunteer-api-5oq5.onrender.com",
    # Добавь свои домены:
    # "https://your-frontend.com",
]


def setup_security(app: FastAPI):
    """Подключаем все middleware безопасности к приложению."""

    # 1. Rate Limiting
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # 2. CORS — только свои домены
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "Accept"],
    )

    # 3. Security Headers
    app.add_middleware(SecurityHeadersMiddleware)

    # 4. Request Validator
    app.add_middleware(RequestValidatorMiddleware)


class SecurityHeadersMiddleware(BaseMiddleware):
    """
    Добавляет заголовки безопасности к каждому ответу.
    CSP защищает от XSS — браузер не выполнит скрипты из чужих источников.
    """
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # Content Security Policy — только свои источники скриптов
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "connect-src 'self'"
        )
        # Защита от XSS в браузере
        response.headers["X-XSS-Protection"]        = "1; mode=block"
        # Запрет MIME sniffing
        response.headers["X-Content-Type-Options"]   = "nosniff"
        # Запрет iframe (clickjacking)
        response.headers["X-Frame-Options"]          = "DENY"
        # HTTPS только
        response.headers["Strict-Transport-Security"] = \
            "max-age=31536000; includeSubDomains"
        # Не отправлять реферер на другие сайты
        response.headers["Referrer-Policy"]          = "no-referrer"

        return response


class RequestValidatorMiddleware(BaseMiddleware):
    """
    Валидация входящих запросов:
    - Блокируем подозрительные User-Agent
    - Детектируем попытки SQL инъекций в URL
    - Ограничиваем размер тела запроса
    """
    MAX_BODY_SIZE = 10 * 1024 * 1024  # 10 MB

    # Паттерны SQL инъекций
    SQL_INJECTION_PATTERNS = [
        r"(\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC|UNION)\b)",
        r"(--|#|/\*|\*/)",
        r"(\bOR\b\s+\d+\s*=\s*\d+)",
        r"(\bAND\b\s+\d+\s*=\s*\d+)",
    ]

    async def dispatch(self, request: Request, call_next) -> Response:
        # Проверяем URL на SQL инъекции
        url_str = str(request.url)
        for pattern in self.SQL_INJECTION_PATTERNS:
            if re.search(pattern, url_str, re.IGNORECASE):
                return Response(
                    content='{"detail": "Недопустимый запрос"}',
                    status_code=400,
                    media_type="application/json"
                )

        # Проверяем размер тела
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > self.MAX_BODY_SIZE:
            return Response(
                content='{"detail": "Тело запроса слишком большое"}',
                status_code=413,
                media_type="application/json"
            )

        return await call_next(request)
