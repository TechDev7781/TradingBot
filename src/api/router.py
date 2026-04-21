from fastapi import APIRouter, BackgroundTasks, status

from src.schemas import NotificationSchema
from src.strategy.service import StrategyService

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


@router.post("", status_code=status.HTTP_200_OK)
async def receive_notification(
    schema: NotificationSchema,
    background_tasks: BackgroundTasks,
) -> None:
    background_tasks.add_task(StrategyService.check, schema)
