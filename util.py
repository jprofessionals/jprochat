import json
from langchain_core.documents import Document
import logging
from cloudwatch import cloudwatch
from openai import OpenAI


def get_aws_logger(logger_name: str, log_group_name: str = "jprochat") -> logging.Logger:
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(logger_name)

    formatter = logging.Formatter('%(asctime)s : %(levelname)s - %(message)s')
    handler = cloudwatch.CloudwatchHandler(log_group=log_group_name)

    handler.setFormatter(formatter)
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    return logger


def read_docs(filename) -> [Document]:
    with open(filename, 'r') as file:
        json_str = file.read()

    docs = []
    parsed = json.loads(json_str)
    for doc in parsed:
        metadata = doc["metadata"]
        docs.append(Document(
            page_content=doc['page_content'],
            metadata={
                'source': metadata["source"],
                'title': metadata["title"],
                'description': metadata["description"],
                'language': metadata["language"]
            }
        ))
    return docs


logger = get_aws_logger("jprochat")


def resolve_openai_model_name() -> str:
    client = OpenAI()
    models = client.models.list()

    candidates = list(map(lambda n: n.id, list(filter(lambda x: x.id.__contains__("4o"), models))))
    bylength = sorted(candidates, key=len)

    model_name = next((s for s in bylength if s.__contains__("mini")), "")
    if not model_name:
        model_name = bylength[0]

    logger.info(f"using chatgpt model: {model_name}")
    return model_name


# logger.info(dict(foo="bar", details={}))
