"""Provider bridges: adapt external LLM/embedding services to LangChain.

Each backend lives in its own module here. The single entry point is
``langchain_module.base.get_llm`` / ``get_embeddings`` (the "switch"), which
dispatches to the right adapter based on ``LC_LLM_BACKEND``.

To add a provider: drop a new module in this folder exporting a LangChain
``BaseChatModel`` (and optionally ``Embeddings``), then add a case in
``base.py``. No need for many disconnected bridges — one dispatcher + pluggable
adapters.

The ProxyAPI adapter expects the GENERAL-PURPOSE ``proxyapi_module`` to live at
the PROJECT ROOT (not bundled inside langchain_module). It is imported directly;
there is intentionally NO copy inside this package.
"""
