from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from bs4 import BeautifulSoup
from langchain_core.documents import Document
import json
from shutil import which
from util import get_aws_logger
import logging

chromium_path = which('chromium.chromedriver')

service = Service(executable_path=chromium_path)
options = Options()
options.add_argument('--headless')
options.add_argument('--no-sandbox')
# options.set_capability("goog:loggingPrefs", {'performance': 'ALL'})

browser = webdriver.Chrome(service=service, options=options)

logger = get_aws_logger("fetch_articles")


def get_page(url_to_crawl):
    browser.get(url_to_crawl)
#    logs = browser.get_log('performance')
#    for log in logs:
#        print(f"got log: {log}")
    html_source = browser.page_source
    relative_links = set()
#    with open(f"1.html", "w") as out_file2:
#        out_file2.write(html_source)

    soup = BeautifulSoup(html_source, "html.parser")
    for link in soup.findAll('a'):
        url = link.get('href')
        if url.startswith('/'):
            relative_links.add(url)
    title = soup.find('title').string
    description = soup.find("meta", attrs={'name': 'description'})
    description = description["content"]

    [s.extract() for s in soup(['style', 'script', '[document]', 'head', 'title', 'form', 'iframe', 'footer'])]
    # kill all script and style elements
    for script in soup(["script", "style"]):
        script.extract()  # rip it out

    for consent_popup in soup.select('div[id*="ppms_cm_consent_popup"]'):
        consent_popup.extract()

    for link in soup.findAll('a', href=True):
        link.extract()

#    # get text
    text = soup.body.get_text()
#    body_text = text
    # break into lines and remove leading and trailing space on each
    lines = (line.strip() for line in text.splitlines())
    # break multi-headlines into a line each
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
    # drop blank lines
    body_text = '\n'.join(chunk for chunk in chunks if chunk)

    parsed_doc = Document(
        page_content=body_text,
        metadata={
            'source': url_to_crawl,
            'title': title,
            'description': description,
            'language': 'no'
        }
    )
    return parsed_doc, relative_links


URL_PREFIX = "https://www.jpro.no"
visited_urls = set()
documents = []


def crawl(url_to_crawl):
    real_url = f"{URL_PREFIX}{url_to_crawl}" if url_to_crawl.startswith("/") else url_to_crawl
    print(f"scanning {real_url}")
    doc_read, links = get_page(real_url)
    documents.append(doc_read)
    visited_urls.add(url_to_crawl)
    if real_url == f"{URL_PREFIX}/":
        visited_urls.add("/")
    for link in links:
        link = link[:link.index("#")] if "#" in link else link
        if link not in visited_urls:
            crawl(link)


logger.info("starting to fetch articles")

crawl("/")

logger.info(f"crawled {len(documents)} documents. Dumping them to disk")

json_str = json.dumps(documents, default=lambda x: x.__dict__)
with open("documents.json", "w") as out_file:
    out_file.write(json_str)


mydocs = []
parsed = json.loads(json_str)
for doc in parsed:
    metadata = doc["metadata"]
    mydocs.append(Document(
        page_content=doc['page_content'],
        metadata={
            'source': metadata["source"],
            'title': metadata["title"],
            'description': metadata["description"],
            'language': metadata["language"]
        }
    ))

logger.info(f"parsed {len(mydocs)} documents from disk. Done")

response = requests.get("http://localhost:9432/jprochat/reload")
if response.status_code != 200:
    logger.info("Failed to reload articles")

browser.quit()
