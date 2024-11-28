import sys

from fastapi import FastAPI, Response, Request
from pydantic import BaseModel
from time import perf_counter as timer

import jprochat
from util import get_aws_logger
import logging

app = FastAPI()

chatPath = "/jprochat"
jpro_chat = jprochat.JproChat()

logger = get_aws_logger("jprochat")

@app.get("/", status_code=500)
@app.post("/", status_code=500)
@app.put("/", status_code=500)
async def bad_request():
    headers = {"Server": "Unknown"}
    return Response(content="Go away", media_type="text", headers=headers)


@app.get("/chathealth", status_code=200)
async def bad_request():
    headers = {"Server": "Unknown"}
    return Response(content="ok", media_type="text", headers=headers)


class Chat(BaseModel):
    question: str


@app.get(chatPath + "/reload")
async def reload():
    logger.info("got reload request")
    jpro_chat.reload()
    return "ok"


@app.post(chatPath)
async def perform_chat(chat: Chat, request: Request):
    forwarded_for = request.headers.get("X-Forwarded-For")
    start_time = timer()
    answer = jpro_chat.chat(chat.question)
    end_time = timer()
    logger.info(f"Time taken to perform_chat: {end_time-start_time:.5f} seconds. \"{chat.question}\" gave answer \"{answer}\", from ip {forwarded_for}")
    return {"answer": answer}


@app.options(chatPath)
async def perform_options():
    return "ok"


class EndpointFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return record.getMessage().find("/chathealth") == -1

# Filter out /endpoint


def disable_other_loggers():
    logging.getLogger("uvicorn.access").addFilter(EndpointFilter())
    return


def mainfunc(args):
    import uvicorn
    port = 9432
    disable_other_loggers()
    logger.info(f"Booting up, listening port is set to {port}")
    uvicorn.run(app, host="0.0.0.0", port=port, server_header=False, date_header=False)
    logger.info("Server done")


if __name__ == "__main__":
    mainfunc(sys.argv)
