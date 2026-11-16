from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

import app.models as models
from app.core.database import engine
from app.routers.admin import router as admin_router
from app.routers.allocations import router as allocations_router
from app.routers.auth import router as auth_router


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    models.Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(lifespan=lifespan)
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(allocations_router)
