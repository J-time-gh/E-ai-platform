from fastapi import FastAPI

from app.api.routes import agent, chat, documents, health, search
from app.core.config import settings

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="企业级大模型 AI 应用平台：RAG + Agent + LLM Gateway",
)

app.include_router(health.router)
app.include_router(chat.router)
app.include_router(documents.router)
app.include_router(search.router)
app.include_router(agent.router)


@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    return {"message": f"Welcome to {settings.app_name}", "docs": "/docs"}
