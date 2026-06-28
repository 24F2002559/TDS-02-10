import time
import uuid
from collections import defaultdict
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

app = FastAPI()

# ========== CONFIGURATION ==========
RATE_LIMIT = 15          # requests per window
WINDOW_SEC = 10
ALLOWED_ORIGINS = {
    "https://app-c06sod.example.com",   # your assigned origin
    "https://exam.sanand.workers.dev",  # exam page origin
    "https://tools-in-data-science.pages.dev"  # possible exam page variant
}
MY_EMAIL = "your-email@example.com"   # <-- REPLACE WITH YOUR REAL EMAIL

# In‑memory rate limiter buckets: client_id -> list of timestamps
rate_buckets = defaultdict(list)

# ==================== MIDDLEWARE 1: Request Context ====================
# Added first → it's the innermost layer, wraps the actual endpoint.
@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    # Read or generate request_id
    req_id = request.headers.get("X-Request-ID")
    if not req_id:
        req_id = str(uuid.uuid4())
    
    # Store it in request.state so the endpoint can use it
    request.state.request_id = req_id
    
    response = await call_next(request)
    
    # Always set the X-Request-ID response header
    response.headers["X-Request-ID"] = req_id
    return response

# ==================== MIDDLEWARE 2: Rate Limiter ====================
# Added second → runs before the route, can return 429.
@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    # Only rate‑limit the /ping endpoint (but it's fine to apply globally)
    if request.url.path == "/ping":
        client_id = request.headers.get("X-Client-Id")
        if client_id:
            now = time.time()
            bucket = rate_buckets[client_id]
            # Remove expired timestamps
            while bucket and bucket[0] < now - WINDOW_SEC:
                bucket.pop(0)
            
            if len(bucket) >= RATE_LIMIT:
                retry_after = int(bucket[0] + WINDOW_SEC - now) + 1
                resp = JSONResponse(
                    status_code=429,
                    content={"detail": "Too many requests"},
                    headers={"Retry-After": str(retry_after)}
                )
                # Add CORS headers manually so the browser can see the 429
                origin = request.headers.get("origin")
                if origin in ALLOWED_ORIGINS:
                    resp.headers["Access-Control-Allow-Origin"] = origin
                resp.headers["Access-Control-Expose-Headers"] = "Retry-After"
                return resp
            
            bucket.append(now)
    
    return await call_next(request)

# ==================== MIDDLEWARE 3: CORS (outermost) ====================
# Added last → it runs before every request and after every response,
# adding the proper CORS headers only for allowed origins.
@app.middleware("http")
async def cors_middleware(request: Request, call_next):
    origin = request.headers.get("origin")
    
    # Handle preflight (OPTIONS) requests
    if request.method == "OPTIONS":
        response = JSONResponse(content={})
        if origin in ALLOWED_ORIGINS:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "*"
            response.headers["Access-Control-Expose-Headers"] = "Retry-After, X-Request-ID"
        return response
    
    # For normal requests
    response = await call_next(request)
    if origin in ALLOWED_ORIGINS:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Expose-Headers"] = "Retry-After, X-Request-ID"
    return response

# ==================== ENDPOINT ====================
@app.get("/ping")
async def ping(request: Request):
    # request_id was put in state by the request_context middleware
    req_id = request.state.request_id
    return {
        "email": MY_EMAIL,
        "request_id": req_id
    }
