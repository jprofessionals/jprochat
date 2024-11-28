import os
import socket
import re
from datetime import datetime
from time import perf_counter as timer

from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain.prompts import SystemMessagePromptTemplate, HumanMessagePromptTemplate, ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI
from langchain_community.graphs import Neo4jGraph
from langchain_community.vectorstores import Neo4jVector, FAISS
from langchain_core.runnables import RunnablePassthrough, RunnableParallel
import langchain

from chains import MyGraphCypherQAChain
import prompts
from util import resolve_openai_model_name, read_docs
from util import get_aws_logger

langchain.debug = False

url = os.environ['NEO4j_URL']
username = os.environ['NEO4j_UNAME']
password = os.environ['NEO4j_PW']

model_name = resolve_openai_model_name()

data_filename = "documents.json"
cv_filename = "cvs.json"

logger = get_aws_logger("jprochat")


def init_retriever():
    docs = read_docs(data_filename)

    logger.info(f"read {len(docs)} documents from from disk")

    cv_docs = read_docs(cv_filename)

    logger.info(f"read {len(cv_docs)} CV documents from from disk")

    docs.extend(cv_docs)

    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200, separators=[".", "\n"])
    splits = text_splitter.split_documents(docs)
    logger.info(f"The documents where split into {len(splits)} parts")

    db = FAISS.from_documents(splits, OpenAIEmbeddings())
    return db.as_retriever()

#    vectorstore = Chroma.from_documents(documents=splits, embedding=Embed4All('nomic-embed-text-v1.f16.gguf'))
#    GPT4AllEmbeddings(model_name="nomic‑embed‑text‑v1.5.f16.gguf"))  # document_embedding)
#    return vectorstore.as_retriever()


def init_vector_index():
    return Neo4jVector.from_existing_graph(
        OpenAIEmbeddings(),
        url=url,
        username=username,
        password=password,
        index_name='skills',
        node_label="skill",
        text_node_properties=['name', 'view_name'],
        embedding_node_property='embedding',
    )


def format_docs(docs_to_format):
    return "\n\n".join(doc.page_content for doc in docs_to_format)


messages = [
    SystemMessagePromptTemplate.from_template(prompts.general_system_template),
    HumanMessagePromptTemplate.from_template(prompts.general_user_template)
]
rag_prompt = ChatPromptTemplate.from_messages(messages)
get_neo_number_regexp = re.compile(r'^.*?(\d+).*$')


# some questions are not about skills, and the generated Cypher statement counts the number of skill instead, and
# returns a number that is higher than 1000. This "hack" detects these answers and changes them to a no answer response
def possibly_patch_neo_answer(neo_answer: str) -> str:
    match = get_neo_number_regexp.match(neo_answer)
    if match:
        val = match.groups()[len(match.groups())-1]
        if len(val) > 3:
            return "nei"
    return neo_answer


class JproChat:
    def __init__(self):
        self.graph = Neo4jGraph(url=url, username=username, password=password)
        self.retriever = init_retriever()
        self.llm = ChatOpenAI(temperature=0.1, model_name=model_name)
        self.rag_chain = (
            {"context": self.retriever | format_docs, "question": RunnablePassthrough()}
            | rag_prompt
            | self.llm
            | StrOutputParser()
        )
        self.vector_index = init_vector_index()
        self.neo_chain = MyGraphCypherQAChain(llm=self.llm, graph=self.graph)
        self.jpro_chain = RunnableParallel(rag=self.rag_chain, neo=self.neo_chain)

    def chat(self, question):
        question_lc = question.lower()
        logger.info(f"[INFO] starting to ask question {question_lc} at {datetime.now()}")
        start_time = timer()
        try:
            answer = self.jpro_chain.invoke(question_lc)
        except Exception as exp:
            logger.info(f"jpro_chain failed with {exp} answering {question_lc}")
            answer = {"rag": "", "neo": ""}
        end_time = timer()
        logger.info(f"[INFO] Time taken to generate answer: {end_time-start_time:.5f} seconds.")
        rag_answer = answer['rag'] if answer['rag'] else ""
        neo_answer = answer['neo']['response'] if (answer['neo']) else ""
        neo_answer = possibly_patch_neo_answer(neo_answer)

        logger.info(f"rag_answer = {rag_answer}")
        logger.info(f"neo_answer = {neo_answer}")
        if len(neo_answer) > 4 and not neo_answer.lower().startswith("nei"):
            logger.info(f"choosing neo answer {neo_answer}")
            return neo_answer
        if rag_answer and not rag_answer.lower().startswith("nei"):
            logger.info(f"choosing RAG answer {rag_answer}")
            return rag_answer
        logger.info(f"choosing default answer {rag_answer}")
        return "Beklager, jeg kan ikke svare på dette spørsmålet. Ta kontakt med jPro på telefon 906 83 146 for en hyggelig samtale"

    def reload(self):
        self.retriever = init_retriever()


# rag_svar = rag_chain.invoke("Hvem kan java?")
# print(f"rag_svar = {rag_svar}")

# svar = neo_chain.invoke({"question": "hvor mange kan java?"})
# print(svar)

#svar = rag_chain.invoke("hvem kan java?")
#print(svar)


# svar = jpro_chain.invoke("hvem kan subversion?")
#svar = jpro_chain.invoke("hvor mange av dere kan php?")
#print(svar)

jproChat = JproChat()

#svar = jproChat.chat("hvem kan Java?")
#print(f"fikk svar {svar}")
#print ("********************")
#svar = jproChat.chat("hvor mange kan Java?")
#print(f"fikk svar {svar}")
#print ("********************")
#svar = jproChat.chat("hvilken kompetanse har dere?")
#print(f"fikk svar {svar}")

questions = [
    "hva kan JPro",
    "har dere erfaring med prosjekter med integrasjoner?",
    "har dere erfaring med prosjekter innen media ?",
    "hvor mange av dere kan PHP?",
    "hvor mye koster dere?",
    "Hvem kan PHP?",
    "hvor mange seniorkonsulenter i jpro har erfaring med azure?",
    "media",
    "Hvor mange jobber hos dere"
]

if "Link" == socket.gethostname():
    for question in questions:
        print(f"******************** {question}")
        svar = jproChat.chat(question)
        print(f"fikk svar {svar}")

