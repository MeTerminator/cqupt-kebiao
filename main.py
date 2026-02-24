from app.api import curriculum
from fastapi import FastAPI
import uvicorn

app = FastAPI()

# 导入路由
app.include_router(curriculum.router)

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)
