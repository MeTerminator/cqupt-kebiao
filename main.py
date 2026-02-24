from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.core.redis import redis_client
from app.api import curriculum
import uvicorn


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时
    yield
    # 关闭时
    await redis_client.close()

app = FastAPI(lifespan=lifespan)

# 导入路由
app.include_router(curriculum.router)

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)
