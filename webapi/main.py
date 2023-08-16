from prometheus_fastapi_instrumentator import Instrumentator
from fastapi import FastAPI
import uvicorn
import logging

app = FastAPI()
instrumentator = Instrumentator().instrument(app)

@app.on_event("startup")
async def _startup():
    instrumentator.expose(app)

@app.get("/")
def read_root():
    logging.info('root path')
    return {"Hello": "World"}


@app.get("/items/{item_id}")
def read_item(item_id: int):
    logging.info(f'item_id: {item_id}')
    return {"item_id": item_id}

if __name__ == "__main__":
    uvicorn.run("main:app", port=5000, log_level="info", host="0.0.0.0")