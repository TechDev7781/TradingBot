import logging

from fastapi import FastAPI

from src.api.router import router as webhooks_router
from src.config import settings
from src.telegram.service import TelegramService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

app = FastAPI(title="Снайпер 2026")
app.include_router(webhooks_router)


@app.on_event("startup")
async def _startup_telegram() -> None:
    await TelegramService.start_polling()


@app.on_event("shutdown")
async def _shutdown_telegram() -> None:
    await TelegramService.stop_polling()


@app.get("/")
async def root() -> dict[str, str]:
    return {"health": "OK"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )
