"""langchain_module — reusable LangChain toolkit with a pluggable LLM backend.

Public entry points (no heavy imports at module load, so the package can be
imported even before langchain is installed):

    from langchain_module import get_llm, get_embeddings
    llm = get_llm()                       # backend from LC_LLM_BACKEND (default proxyapi)
    embeddings = get_embeddings()

Area modules are imported explicitly to keep the top-level light:

    from langchain_module.llms import complete
    from langchain_module.rag import ask_langchain_docs
    from langchain_module.langchain_client import LangChainClient

The ProxyAPI connection is provided by the project's shared ``proxyapi_module``
(expected at the project root, NOT bundled here). The bridge that adapts it to
LangChain lives in ``langchain_module.bridges.proxyapi``.
"""

from .base import get_llm, get_embeddings

__all__ = ["get_llm", "get_embeddings"]
