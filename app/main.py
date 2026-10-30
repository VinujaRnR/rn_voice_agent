from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.api.chat import router as chat_router
from app.api.stt import router as stt_router
from app.api.commands import router as commands_router
from app.api.devices import router as devices_router
from app.api.reminders import router as reminders_router
from app.api.tts import router as tts_router
from app.rabbitmq.connection import rabbitmq_connection
from app.rabbitmq.consumer import result_consumer
from app.tools.reminders import start_reminder_worker, stop_reminder_worker


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: keep single broker connection open, start result consumer and reminder worker
    await rabbitmq_connection.connect()
    await result_consumer.start()
    start_reminder_worker()
    yield
    # Shutdown: clean up worker, consumer, channel, and connection
    stop_reminder_worker()
    await result_consumer.stop()
    await rabbitmq_connection.close()


app = FastAPI(
    title="RN Robots Voice Assistant",
    version="1.0.0",
    lifespan=lifespan
)

# Register API Routers
app.include_router(chat_router)
app.include_router(stt_router)
app.include_router(commands_router)
app.include_router(devices_router)
app.include_router(reminders_router)
app.include_router(tts_router)


@app.get("/health")
async def health():
    return {
        "service": "rn_voice_assistant",
        "status": "healthy"
    }


# Mount frontend static files
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
