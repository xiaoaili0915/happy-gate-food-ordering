import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.database import ensure_schema
from app.routers import kitchen, menu, orders, restaurant
from app.services.timeout import timeout_loop

ensure_schema()

templates = Jinja2Templates(directory="app/templates")


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(timeout_loop())
    yield
    task.cancel()


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(menu.router)
app.include_router(orders.router)
app.include_router(kitchen.router)
app.include_router(restaurant.router)
