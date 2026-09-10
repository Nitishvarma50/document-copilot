from typing import Annotated

import uvicorn
from app.api.chat import router as chat_router
from app.auth.dependencies import CurrentUser, get_current_user
from app.chat.body_limit import ChatBodyLimitMiddleware
from app.chat.errors import ChatError
from app.config import settings
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

app = FastAPI(title="Document Copilot", version="0.1.0")
app.add_middleware(ChatBodyLimitMiddleware)
app.include_router(chat_router)


@app.exception_handler(ChatError)
async def chat_error_handler(_request: Request, exc: ChatError) -> JSONResponse:
    headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
    return JSONResponse(
        {"detail": exc.detail}, status_code=exc.status_code, headers=headers
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/auth/me", response_model=CurrentUser)
async def authenticated_user(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> CurrentUser:
    return user


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000)
