# API Middleware - Detailed Component Documentation

> **Complete technical documentation for API middleware**  
> This document provides comprehensive details for developers working with API middleware in CartPilot.

## Table of Contents

1. [Overview](#overview)
2. [Architecture & Design](#architecture--design)
3. [Middleware Components](#middleware-components)
4. [API Reference](#api-reference)
5. [Configuration](#configuration)
6. [Error Handling](#error-handling)
7. [Code Examples](#code-examples)

---

## Overview

### Purpose

API middleware provides cross-cutting concerns for the CartPilot API: API key authentication, request ID correlation, error handling, and request logging.

**Location**: `cartpilot-api/app/api/middleware.py`  
**Lines of Code**: ~256 lines  
**Dependencies**: FastAPI, structlog, settings

### Responsibilities

- **Authentication**: API key authentication for protected endpoints
- **Request Correlation**: Generate and propagate request IDs
- **Error Handling**: Consistent error responses
- **Request Logging**: Log request/response details

### Key Metrics

- **Middleware Classes**: 3 (RequestIdMiddleware, ApiKeyMiddleware, ErrorHandlerMiddleware)
- **Public Paths**: 6 paths excluded from authentication
- **Error Response Format**: Standardized JSON error format

---

## Architecture & Design

### Middleware Stack

```
Request Flow:
┌─────────────────────────────────────────┐
│  ErrorHandlerMiddleware (outermost)      │  ← Catches all errors
├─────────────────────────────────────────┤
│  ApiKeyMiddleware                        │  ← Authentication
├─────────────────────────────────────────┤
│  RequestIdMiddleware (innermost)        │  ← Correlation ID
├─────────────────────────────────────────┤
│  FastAPI Route Handlers                  │
└─────────────────────────────────────────┘
```

**Execution Order**: Middleware added in reverse order (last added = first executed)

### Design Patterns

1. **Middleware Pattern**: Chain of responsibility for request processing
2. **Decorator Pattern**: Middleware wraps request handlers
3. **Singleton Pattern**: Settings accessed via singleton

---

## Middleware Components

### RequestIdMiddleware

**Location**: Lines 28-84

**Purpose**: Add request ID for correlation across services.

**Functionality**:
- Generates or extracts request ID from `X-Request-ID` header
- Stores in `request.state.request_id` for handler access
- Adds to response headers
- Binds to log context for structured logging
- Logs request completion with duration

**Implementation**:
```python
class RequestIdMiddleware(BaseHTTPMiddleware):
    HEADER_NAME = "X-Request-ID"
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Get or generate request ID
        request_id = request.headers.get(self.HEADER_NAME) or str(uuid4())
        
        # Store in request state
        request.state.request_id = request_id
        
        # Add to log context
        structlog.contextvars.bind_contextvars(request_id=request_id)
        
        # Time the request
        start_time = time.perf_counter()
        
        try:
            response = await call_next(request)
        finally:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.info("Request completed", ...)
            structlog.contextvars.unbind_contextvars("request_id")
        
        # Add to response headers
        response.headers[self.HEADER_NAME] = request_id
        return response
```

**Features**:
- Request ID generation (UUID4)
- Request timing
- Structured logging
- Context cleanup

### ApiKeyMiddleware

**Location**: Lines 103-186

**Purpose**: API key authentication for protected endpoints.

**Functionality**:
- Validates `Authorization: Bearer <api_key>` header
- Skips authentication for public paths
- Validates API key against settings
- Returns 401 on authentication failure

**Public Paths** (Lines 93-100):
```python
PUBLIC_PATHS = {
    "/health",
    "/ready",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/webhooks/merchant",  # Webhooks use HMAC signature instead
}
```

**Implementation**:
```python
class ApiKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip auth for public paths
        path = request.url.path.rstrip("/")
        if path in PUBLIC_PATHS or path.startswith("/docs") or path.startswith("/redoc"):
            return await call_next(request)
        
        # Get Authorization header
        auth_header = request.headers.get("Authorization")
        
        if not auth_header:
            return JSONResponse(
                status_code=401,
                content={"error_code": "UNAUTHORIZED", "message": "Missing Authorization header"}
            )
        
        # Validate Bearer token format
        parts = auth_header.split(" ", 1)
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return JSONResponse(
                status_code=401,
                content={"error_code": "UNAUTHORIZED", "message": "Invalid Authorization header format"}
            )
        
        api_key = parts[1]
        
        # Validate API key
        if api_key != settings.cartpilot_api_key:
            return JSONResponse(
                status_code=401,
                content={"error_code": "INVALID_API_KEY", "message": "Invalid API key"}
            )
        
        # Store authenticated status
        request.state.authenticated = True
        
        return await call_next(request)
```

**Error Responses**:
- `UNAUTHORIZED`: Missing Authorization header
- `UNAUTHORIZED`: Invalid Authorization format
- `INVALID_API_KEY`: Invalid API key

**Security**:
- Constant-time comparison (future enhancement)
- WWW-Authenticate header in responses

### ErrorHandlerMiddleware

**Location**: Lines 194-232

**Purpose**: Consistent error handling for unhandled exceptions.

**Functionality**:
- Catches all unhandled exceptions
- Returns standardized error response
- Logs exception details
- Includes request ID in error response

**Implementation**:
```python
class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        try:
            return await call_next(request)
        except Exception as e:
            request_id = getattr(request.state, "request_id", None)
            
            logger.exception(
                "Unhandled exception",
                path=request.url.path,
                method=request.method,
                error=str(e),
            )
            
            return JSONResponse(
                status_code=500,
                content={
                    "error_code": "INTERNAL_ERROR",
                    "message": "An internal error occurred",
                    "details": [],
                    "request_id": request_id,
                },
            )
```

**Error Response Format**:
```json
{
    "error_code": "INTERNAL_ERROR",
    "message": "An internal error occurred",
    "details": [],
    "request_id": "uuid-here"
}
```

---

## API Reference

### setup_middleware

**Method**: `def setup_middleware(app: FastAPI) -> None`

**Purpose**: Configure all middleware for the application.

**Location**: Lines 240-255

**Usage**:
```python
from app.api.middleware import setup_middleware
from fastapi import FastAPI

app = FastAPI()
setup_middleware(app)
```

**Middleware Order**:
1. ErrorHandlerMiddleware (outermost - catches all errors)
2. ApiKeyMiddleware (authentication)
3. RequestIdMiddleware (innermost - for handlers)

**Implementation**:
```python
def setup_middleware(app: FastAPI) -> None:
    # Error handling (outermost - catches all errors)
    app.add_middleware(ErrorHandlerMiddleware)
    
    # API key authentication
    app.add_middleware(ApiKeyMiddleware)
    
    # Request ID correlation (innermost for handlers)
    app.add_middleware(RequestIdMiddleware)
```

---

## Configuration

### Settings

**API Key**: `settings.cartpilot_api_key` (from environment variable `CARTPILOT_API_KEY`)

**Public Paths**: Defined in `PUBLIC_PATHS` constant

**Request ID Header**: `X-Request-ID` (configurable via `RequestIdMiddleware.HEADER_NAME`)

### Environment Variables

```bash
CARTPILOT_API_KEY=your-api-key-here
```

---

## Error Handling

### Authentication Errors

**Missing Authorization Header**:
```json
{
    "error_code": "UNAUTHORIZED",
    "message": "Missing Authorization header",
    "details": []
}
```

**Invalid Authorization Format**:
```json
{
    "error_code": "UNAUTHORIZED",
    "message": "Invalid Authorization header format. Use 'Bearer <api_key>'",
    "details": []
}
```

**Invalid API Key**:
```json
{
    "error_code": "INVALID_API_KEY",
    "message": "Invalid API key",
    "details": []
}
```

### Internal Errors

**Unhandled Exception**:
```json
{
    "error_code": "INTERNAL_ERROR",
    "message": "An internal error occurred",
    "details": [],
    "request_id": "uuid-here"
}
```

---

## Code Examples

### Accessing Request ID in Handlers

```python
from fastapi import Request

@app.get("/orders/{order_id}")
async def get_order(order_id: str, request: Request):
    request_id = request.state.request_id
    logger.info("Getting order", order_id=order_id, request_id=request_id)
    # ... handler logic
```

### Checking Authentication Status

```python
@app.post("/protected")
async def protected_endpoint(request: Request):
    if not getattr(request.state, "authenticated", False):
        raise HTTPException(status_code=401, detail="Not authenticated")
    # ... handler logic
```

### Custom Error Handling

```python
from fastapi import HTTPException

@app.get("/items/{item_id}")
async def get_item(item_id: str):
    try:
        item = get_item_from_db(item_id)
    except ItemNotFoundError:
        raise HTTPException(
            status_code=404,
            detail={
                "error_code": "ITEM_NOT_FOUND",
                "message": f"Item {item_id} not found"
            }
        )
    return item
```

### Client Request with API Key

```python
import httpx

headers = {
    "Authorization": "Bearer your-api-key-here",
    "X-Request-ID": "client-request-id-123"
}

async with httpx.AsyncClient() as client:
    response = await client.get(
        "https://api.cartpilot.com/orders/order-123",
        headers=headers
    )
    
    # Response includes X-Request-ID header for correlation
    request_id = response.headers.get("X-Request-ID")
```

### Public Endpoint (No Auth Required)

```python
@app.get("/health")
async def health_check():
    return {"status": "healthy"}
```

---

## Summary

This detailed documentation covers API middleware components, authentication, request correlation, error handling, and usage examples for developers working with the API layer in CartPilot.
