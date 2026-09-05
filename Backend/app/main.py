from typing import Annotated

import uvicorn
from app.auth.dependencies import CurrentUser, get_current_user
from app.config import settings
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Document Copilot", version="0.1.0")

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
