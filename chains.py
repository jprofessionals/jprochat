from langchain.chains.base import Chain
from langchain.prompts import BasePromptTemplate
from langchain_community.graphs import Neo4jGraph
from langchain_core.language_models import BaseLanguageModel
from typing import Any, Dict, List
from langchain.prompts import PromptTemplate

import prompts


class MyGraphCypherQAChain(Chain):
    """
    The original GraphCypherQAChain messes up in our case, so we roll our own.
    """
    llm: BaseLanguageModel = None
    graph: Neo4jGraph = None
    cypher_chain: Chain = None
    answer_chain: Chain = None
    prompt: BasePromptTemplate = None
    answer_prompt: BasePromptTemplate = None
    output_key: str = "response"

    def __init__(self, llm, graph, **kwargs):
        super().__init__(**kwargs)
        self.llm = llm
        self.graph = graph
        self.prompt = PromptTemplate.from_template(prompts.cypher_prompt_template)
        self.cypher_chain = self.prompt | self.llm
        self.answer_prompt = PromptTemplate.from_template(prompts.neo_llm_prompt_template)
        self.answer_chain = self.answer_prompt | self.llm

    @property
    def input_keys(self) -> List[str]:
        return self.prompt.input_variables

    @property
    def output_keys(self) -> List[str]:
        return [self.output_key]

# good query: MATCH (d:Developer)-[:KNOWS]->(s:skill {name: 'azure'}) RETURN COUNT(d) AS value
# bad query:  MATCH (d:Developer)-[:KNOWS]->(s:skill) RETURN COUNT(s) AS value
    def _call(self, inputs: Dict[str, Any], **kwargs) -> Dict[str, str]:
        response = self.cypher_chain.invoke(inputs)
        query = response.content.replace("\n", " ") if response and response.content else ""
        if query.lower() == "nei":
            return {self.output_key: "nei"}
        if "MATCH" not in query:
            raise RuntimeError(f"Got an invalid/missing cypher statement from the llm: {response}:{query}")
        if "name:" not in query:
            return {self.output_key: "nei"}
        updated_query = query[query.find('MATCH'):].removesuffix("```")
        print(f"db query = '{updated_query}'")
        data = self.graph.query(updated_query)
        data_string = str(data)
        if len(data_string) > 5000:
            return {self.output_key: "nei"}
        inputs['context'] = str(data)
        response = self.answer_chain.invoke(inputs)
        answer = response.content.replace("\n", " ") if response and response.content else ""
        return {self.output_key: answer}
