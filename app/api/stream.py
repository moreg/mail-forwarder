import asyncio
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from app.core.events import broadcaster

router = APIRouter(prefix="/stream", tags=["Realtime Stream"])

@router.get("")
async def sse_event_stream():
    """
    Server-Sent Events (SSE) 实时推送端点
    前端或外部客户端连接后，有新邮件或提取到新验证码时将实时推送到客户端。
    """
    queue = broadcaster.subscribe()

    async def event_generator():
        try:
            # Send initial ping
            yield "event: ping\ndata: connected\n\n"
            while True:
                try:
                    # Wait for next event or send heartbeat
                    payload = await asyncio.wait_for(queue.get(), timeout=20.0)
                    yield f"event: email_event\ndata: {payload}\n\n"
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            broadcaster.unsubscribe(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )
