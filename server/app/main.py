from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import agent, chat, erp, health, knowledge, monitor, prompt, workflow
from app.core.config import settings

app = FastAPI(title="WorkMind AI API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(HTTPException)
async def http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"error": str(exc.detail)})


app.include_router(health.router, prefix="/health", tags=["health"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(knowledge.router, prefix="/api/knowledge", tags=["knowledge"])
app.include_router(agent.router, prefix="/api/agent", tags=["agent"])
app.include_router(workflow.router, prefix="/api/workflow", tags=["workflow"])
app.include_router(erp.router, prefix="/api/erp", tags=["erp"])
app.include_router(prompt.router, prefix="/api/prompt", tags=["prompt"])
app.include_router(monitor.router, prefix="/api/monitor", tags=["monitor"])
