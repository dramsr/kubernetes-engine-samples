# Copyright 2024 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from langchain_google_vertexai import ChatVertexAI
from langchain.prompts import ChatPromptTemplate
from langchain_google_vertexai import VertexAIEmbeddings
from langchain.memory import ConversationBufferWindowMemory
from elasticsearch import Elasticsearch
from langchain_community.vectorstores.elasticsearch import ElasticsearchStore
import streamlit as st
import os

vertexAI = ChatVertexAI(model_name=os.getenv("VERTEX_AI_MODEL_NAME", "gemini-2.5-flash-preview-04-17"), streaming=True, convert_system_message_to_human=True)
prompt_template = ChatPromptTemplate.from_messages(
    [
        ("system", "You are a helpful assistant who helps in finding answers to questions using the provided context."),
        ("human", """
        The answer should be based on the text context given in "text_context" and the conversation history given in "conversation_history" along with its Caption: \n
        Base your response on the provided text context and the current conversation history to answer the query.
        Select the most relevant information from the context.
        Generate a draft response using the selected information. Remove duplicate content from the draft response.
        Generate your final response after adjusting it to increase accuracy and relevance.
        Now only show your final response!
        If you do not know the answer or context is not relevant, response with "I don't know".

        text_context:
        {context}

        conversation_history:
        {history}

        query:
        {query}
        """),
    ]
)

embedding_model = VertexAIEmbeddings("text-embedding-005")

client = Elasticsearch(
    [os.getenv("ES_URL")], 
    verify_certs=False, 
    ssl_show_warn=False,
    basic_auth=("elastic", os.getenv("PASSWORD"))
)
vector_search = ElasticsearchStore(
    index_name=os.getenv("INDEX_NAME"),
    es_connection=client,
    embedding=embedding_model
)

def format_docs(docs):
    return "\n\n".join([d.page_content for d in docs])

st.title("🤖 Chatbot")
if "messages" not in st.session_state:
    st.session_state["messages"] = [{"role": "ai", "content": "How can I help you?"}]

if "memory" not in st.session_state:
    st.session_state["memory"] = ConversationBufferWindowMemory(
        memory_key="history",
        ai_prefix="Bot",
        human_prefix="User",
        k=3,
    )

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.write(message["content"])

if chat_input := st.chat_input():
    with st.chat_message("human"):
        st.write(chat_input)
        st.session_state.messages.append({"role": "human", "content": chat_input})

    found_docs = vector_search.similarity_search(chat_input)
    context = format_docs(found_docs)

    prompt_value = prompt_template.format_messages(name="Bot", query=chat_input, context=context, history=st.session_state.memory.load_memory_variables({}))
    with st.chat_message("ai"):
        with st.spinner("Typing..."):
            content = ""
            with st.empty():
                for chunk in vertexAI.stream(prompt_value):
                    content += chunk.content
                    st.write(content)
            st.session_state.messages.append({"role": "ai", "content": content})

    st.session_state.memory.save_context({"input": chat_input}, {"output": content})

