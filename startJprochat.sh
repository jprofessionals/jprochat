#!/bin/bash

cd /home/ubuntu

# imports env variables CV_PARTNER_API_KEY, OPENAI_API_KEY, NEO4j_URL, NEO4j_UNAME, NEO4j_PW. LANGCHAIN_TRACING_V2,
# LANGCHAIN_API_KEY, LANGCHAIN_ENDPOINT, LANGCHAIN_PROJECT
source /etc/environment

source chat3/bin/activate && python3 main.py

