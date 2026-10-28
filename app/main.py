from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.api.chat import router as chat_router
from app.api.stt import router as stt_router
from app.rabbitmq.connection import rabbitmq_connection


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: keep single broker connection open for application lifetime
    await rabbitmq_connection.connect()
    yield
    # Shutdown: clean up broker channel and connection
    await rabbitmq_connection.close()


app = FastAPI(
    title="RN Robots Voice Assistant",
    version="1.0.0",
    lifespan=lifespan
)

# Register API Routers
app.include_router(chat_router)
app.include_router(stt_router)


@app.get("/health")
async def health():
    return {
        "service": "rn_voice_assistant",
        "status": "healthy"
    }


# Mount frontend static files
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
