import requests
import time
import json
import re
import os
from time import perf_counter as timer
import tempfile
from pypdf import PdfReader
from langchain_core.documents import Document
from pathlib import Path
from openai import OpenAI
from neo4j import GraphDatabase
from string import Template
from util import get_aws_logger
from util import resolve_openai_model_name
import logging

cv_partner_api_key = os.environ['CV_PARTNER_API_KEY']
base_url = 'https://jpro.cvpartner.com/api/'
cv_output_path = tempfile.TemporaryDirectory()
json_output_path = str(Path.home())
parsed_cv_file = f"parsedCV.dat"

url = os.environ['NEO4j_URL']
username = os.environ['NEO4j_UNAME']
password = os.environ['NEO4j_PW']
auth = (username, password)

logger = get_aws_logger("fetch_cvs")

logger.info("Starting to fetch CVs")

session = requests.Session()
session.headers.update({'Authorization': f'Bearer {cv_partner_api_key}'})
session.headers.update({'Content-Type': 'application/json'})


class Developer:
    def __init__(self, name, skills):
        self.name = name
        self.skills = set(skills)


def read_parsed_cv_file():
    r = []
    with open(parsed_cv_file, 'r') as fi:
        lines = fi.readlines()
        for line in lines:
            parts = line.split(":")
            skills = parts[1].split(",")
            r.append(Developer(parts[0], skills))
    return r


start_time = timer()
openai_client = OpenAI()

response = session.get(f'{base_url}v1/countries')
if response.status_code != 200:
    logger.error(f'Failed to retrieve countries: {response}')
    raise Exception(f'Failed to retrieve countries: {response}')

body = response.json()

office_ids = []
company = body[0]
for office in company['offices']:
    office_ids.append(office['id'])

logger.info(f"found the following office ids: {office_ids}")
office_ids_str = ', '.join(['"{}"'.format(value) for value in office_ids])

search_param = f"""
{{
  "office_ids": [{office_ids_str}],
  "offset": 0,
  "size": 100
}}
"""

response = session.post(f'{base_url}v4/search', data=search_param)
if response.status_code != 200:
    logger.error(f'Failed to retrieve users: {response}')
    raise Exception(f'Failed to retrieve users: {response}')

body = response.json()
cvs = body['cvs']


def pdf_to_text(cv_filename) -> str:
    reader = PdfReader(f"{cv_filename}")
    text = ""
    for page in reader.pages:
        text += page.extract_text() + "\n"
    return text


def download_cv(username, the_user_id, the_cv_id) -> str:
    resp = requests.get(
        f"{base_url}v1/cvs/download/{the_user_id}/{the_cv_id}/no/pdf",
        headers={'Authorization': f'Bearer {cv_partner_api_key}'}
    )
    if resp.status_code != 200:
        logger.error(f'Failed to download CV for {username}: {resp}')
        raise Exception(f'Failed to download CV for {username}: {resp}')
    cv_filename = f"{cv_output_path.name}/{username}.pdf"
    with open(cv_filename, "wb") as out:
        out.write(resp.content)
    return cv_filename


documents = []
for cv in cvs:
    name = cv['cv']['name']
    is_deactivated = cv['cv']['is_deactivated']
    if is_deactivated:
        logger.info(f"user {name} is deactivated")
        continue
    user_id = cv['cv']['user_id']
    cv_id = cv['cv']['id']

    logger.info(f"downloading cv for {name}")
    filename = download_cv(name, user_id, cv_id)
    cv_text = pdf_to_text(filename)
    parsed_doc = Document(
        page_content=cv_text,
        metadata={
            'source': filename,
            'title': f"{name} CV",
            'description': f"{name} CV contents",
            'language': 'no'
        }
    )
    documents.append(parsed_doc)

    time.sleep(7)  # cv partner has a rate limit of max 10 requests pr minute

json_str = json.dumps(documents, default=lambda x: x.__dict__)
with open(f"{json_output_path}/cvs.json", "w") as out_file:
    out_file.write(json_str)

end_time = timer()
logger.info(f"Have completed download of {len(documents)} CVs. It took {end_time - start_time:.5f} seconds.")

cv_output_path.cleanup()

# update neo4j

logger.info("Updating neo4j with the CVs")

model_name = resolve_openai_model_name()
logger.info(f"using openai model name {model_name}")

cv_regexp = re.compile("^\\s*(.+)\\s*:\\s*(.+)\\s*$")


def process_gpt(file_prompt, system_msg):
    completion = openai_client.chat.completions.create(
        model=model_name,
        max_tokens=2048,
        temperature=0.0,
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": file_prompt}
        ]
    )
    #    dumper.dump(completion)
    cv_result = completion.choices[0].message.content if completion.choices[0].message.content else ""
    match = cv_regexp.match(cv_result)
    if match:
        return Developer(match.group(1), [x.strip() for x in match.group(2).split(',')])
    else:
        logger.warning(f"Failed to parse cv result from gpt: {cv_result}")
        return []


def extract_entitites_relashionships(docs, prompt_template):
    system_msg = "You are a helpful IT-project and account management who extracts information from documents"
    logger.info(f"runing pipeline for {len(docs)} documents")
    ret = []
    for doc in docs:
        title = doc.metadata["title"]
        # doc['metadata']['title']
        logger.info(f"extracting name and skills for {title}")
        try:
            cv_text = doc.page_content
            prompt = Template(prompt_template).substitute(cvtext=cv_text)
            result = process_gpt(prompt, system_msg)
            ret.append(result)
        except Exception as e:
            logger.warning(f"Error processing {title}: {e}")

    return ret




cv_prompt_template = """
From the CV below, extract the following Entities & relationships described in the mentioned format 
0. ALWAYS FINISH THE OUTPUT. Never send partial responses
1. First, look for the name of the person for this CV.

2. Next find all skills this user has. They may be listed as "Språk", "Verktøy", "Rammeverk", "Opensource", "Middleware", "Servere", "Database" and/or "Operativsystem".

3. The output should be a plain string and look like this: Ola Nordman: Java, Spring, Linux

CV:
$cvtext
"""

start_time = timer()

results = extract_entitites_relashionships(documents, cv_prompt_template)
results = [x for x in results if x]

end_time = timer()
logger.info(f"Time taken to analyze {len(results)} CVs: {end_time - start_time:.5f} seconds.")

with open(parsed_cv_file, 'w') as f:
    for entry in results:
        f.write(f"{entry.name}:{','.join(entry.skills)}\n")

# results = read_parsed_cv_file()

logger.info(f"Saved {len(results)} objects")

keywords = {}
for entry in results:
    for skill in entry.skills:
        skill_lc = skill.lower()
        if skill_lc not in keywords:
            keywords[skill_lc] = skill

logger.info(f"has {len(keywords.keys())} skills")
s = set(keywords.keys())
logger.info(f"has {len(s)} skills")

driver = GraphDatabase.driver(url, auth=auth)
driver.verify_connectivity()

# delete all old data in neo4j
driver.execute_query("MATCH (n) OPTIONAL MATCH (n)-[r]-() WITH n,r LIMIT 50000 DELETE n,r RETURN count(n) as deletedNodesCount")
driver.execute_query("DROP INDEX skills IF EXISTS")

for key, value in keywords.items():
    driver.execute_query("CREATE (n:skill) SET n.view_name = $view_name, n.name = $name RETURN n", {"view_name": value, "name": key})
#    driver.execute_query("""CREATE (n:skill) SET n.view_name = '" + value + "', n.name = '" + key + "' RETURN n""")

for entry in results:
    logger.info(entry.name)
#    driver.execute_query("CREATE (Person:Developer{name: '" + entry.name + "'})", {"name": entry.name}, database_="neo4j")
    driver.execute_query("CREATE (Person:Developer{name: $name })", {"name": entry.name}, database_="neo4j")

    for skill in entry.skills:
        skill_lc = skill.lower()
        driver.execute_query(f"""
MATCH (d:Developer)
where d.name = $dname
MATCH (s:skill)
where s.name = $sname
MERGE (d)-[:KNOWS]->(s)
            """, {"dname": entry.name, "sname": skill_lc}, database_="neo4j")

response = requests.get("http://localhost:9432/jprochat/reload")
if response.status_code != 200:
    logger.info("Failed to reload CVs")

logger.info("Done importing jpro CVs")
