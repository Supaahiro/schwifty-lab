
from typing import Callable
from langchain_core.documents import Document
from langchain_core.vectorstores import VectorStoreRetriever
from langchain_core.embeddings import Embeddings
from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma

import chromadb
import hashlib
import os


def build_embeddings(
    embedding_provider: str,
    embedding_name: str,
    embedding_base_url: str | None = None,
    embedding_api_key_env: str = "OPENAI_API_KEY",
) -> Embeddings:
    """
    Constructs an embeddings model from a provider name and model name.

    Args:
      embedding_provider (str): Provider to use: 'openai' or 'huggingface'.
      embedding_name (str): Name of the embedding model.
      embedding_base_url (str | None): Optional base URL for OpenAI-compatible local servers.
      embedding_api_key_env (str): Environment variable name holding the API key (openai only).

    Returns:
      Embeddings: A LangChain-compatible embeddings instance.

    Raises:
      ValueError: If the embedding provider is not supported.
    """

    if embedding_provider == "openai":
        from langchain_openai import OpenAIEmbeddings
        kwargs: dict = {"model": embedding_name}
        if embedding_base_url:
            kwargs["base_url"] = embedding_base_url
        api_key = os.getenv(embedding_api_key_env)
        if api_key:
            kwargs["openai_api_key"] = api_key
        return OpenAIEmbeddings(**kwargs)

    if embedding_provider == "huggingface":
        from langchain_huggingface import HuggingFaceEmbeddings
        return HuggingFaceEmbeddings(model_name=embedding_name)

    raise ValueError(
        f"Unknown embedding provider '{embedding_provider}'. Supported: 'openai', 'huggingface'."
    )


def vbd_load_documents(path: str, glob: str, chunk_size=1000, chunk_overlap=200) -> list[Document]:
    """
    Loads and splits documents from a specified folder using a glob pattern.

    Args:
      path (str): Path to the folder containing documents.
      glob (str): Glob pattern to match document files.
      chunk_size (int): Maximum size of each document chunk.
      chunk_overlap (int): Number of characters overlapping between chunks.

    Returns:
      list[Document]: A list of document chunks after splitting.

    Raises:
      FileNotFoundError: If the specified folder does not exist.
    """

    if not os.path.exists(path):
        raise FileNotFoundError(f"Markdown folder not found: {path}")

    md_loader = DirectoryLoader(
        path,
        glob=glob,
        loader_cls=TextLoader,
        show_progress=False,
    )
    try:
        md_docs = md_loader.load()
    except Exception as e:
        print(f"Error loading documents for {path}: {e}")
        raise

    docs_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    docs_chunks = docs_splitter.split_documents(md_docs)

    return docs_chunks


def vdb_builder(
    embeddings: Embeddings,
    path: str,
    glob: str,
    db_path: str,
    collection_name: str,
    recreate: bool,
) -> Callable[[], VectorStoreRetriever]:
    """
    Creates a builder closure that initialises or updates a ChromaDB vector store
    collection with embedded document chunks, and returns a retriever for similarity search.

    Args:
      embeddings (Embeddings): A LangChain-compatible embeddings instance (injected).
      path (str): Path to the source documents directory.
      glob (str): Glob pattern for document discovery.
      db_path (str): Path to the persistent ChromaDB database.
      collection_name (str): Name of the ChromaDB collection.
      recreate (bool): If True, resets the database before building the collection.

    Returns:
      Callable[[], VectorStoreRetriever]: A factory that returns a retriever when called.
    """

    def _builder_function() -> VectorStoreRetriever:
        docs_chunks = vbd_load_documents(path, glob)

        client = chromadb.PersistentClient(
            path=db_path, settings=chromadb.config.Settings(allow_reset=True))
        if recreate:
            client.reset()
            print(f"Reset ChromaDB at {db_path}")

        collection = client.get_or_create_collection(
            name=collection_name, embedding_function=None)

        doc_contents = [doc.page_content if hasattr(doc, "page_content") else str(doc) for doc in docs_chunks]
        doc_ids = []
        for i, doc in enumerate(docs_chunks):
            doc_id = doc.metadata.get("source", "")
            if not doc_id:
                doc_id = f"Unknown Source [{hashlib.sha256(doc_contents[i].encode('utf-8')).hexdigest()}]"
            doc_ids.append(doc_id)
        doc_metadatas = [doc.metadata for doc in docs_chunks]
        embeddings_list = embeddings.embed_documents(doc_contents)
        collection.upsert(
            ids=doc_ids,
            documents=doc_contents,
            embeddings=embeddings_list,
            metadatas=doc_metadatas,
        )
        print(f"ChromaDB collection '{collection_name}' updated with {len(docs_chunks)} documents.")

        retriever = VectorStoreRetriever(
            vectorstore=Chroma(
                collection_name=collection_name,
                embedding_function=embeddings,
                client=client,
            ),
            search_type="similarity",
            # K is the amount of chunks to return (usually between 3 and 5 is good)
            search_kwargs={"k": 5},
        )

        return retriever

    return _builder_function
