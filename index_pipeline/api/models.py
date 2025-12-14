"""
Pydantic models for API requests and responses
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict


class S3Config(BaseModel):
    """S3 configuration for input documents"""
    use_s3: bool = Field(default=True, description="Enable S3 integration (REQUIRED - pipeline only works with S3)")
    aws_region: str = Field(default="us-east-1", description="AWS region")
    input_bucket: str = Field(default="", description="S3 bucket for input JSON documents")
    input_prefix: str = Field(default="docs/", description="S3 prefix for input files")
    output_bucket: str = Field(default="", description="S3 bucket for exports")
    output_prefix: str = Field(default="knowledge_graph/", description="S3 prefix for outputs")
    max_files: int = Field(default=0, description="Maximum files to process (0 = all)")


class Neo4jConfig(BaseModel):
    """Neo4j database configuration"""
    uri: str = Field(default="bolt://localhost:7687", description="Neo4j URI")
    username: str = Field(default="neo4j", description="Neo4j username")
    password: str = Field(..., description="Neo4j password")
    database: str = Field(default="neo4j", description="Neo4j database name")


class LLMConfig(BaseModel):
    """LLM Gateway configuration"""
    model_name: str = Field(default="llama3.2:latest", description="LLM model name")
    api_url: str = Field(default="http://localhost:11434/api/generate", description="LLM API endpoint")
    api_key: str = Field(default="", description="API key for authentication")
    response_format: str = Field(default="ollama", description="Response format (ollama, openai, anthropic, custom)")
    custom_response_parser: str = Field(default="", description="JSON path for custom response parsing")
    temperature: float = Field(default=0.1, description="Temperature for generation")
    max_tokens: int = Field(default=2048, description="Maximum tokens to generate")
    custom_headers: Dict[str, str] = Field(default={}, description="Custom HTTP headers")


class EmbeddingConfig(BaseModel):
    """Embedding Gateway configuration"""
    model_name: str = Field(default="nomic-embed-text", description="Embedding model name")
    api_url: str = Field(default="http://localhost:11434/api/embeddings", description="Embedding API endpoint")
    api_key: str = Field(default="", description="API key for authentication")
    response_format: str = Field(default="ollama", description="Response format (ollama, openai, custom)")
    custom_response_parser: str = Field(default="", description="JSON path for custom response parsing")
    custom_headers: Dict[str, str] = Field(default={}, description="Custom HTTP headers")


class ProcessingConfig(BaseModel):
    """Processing parameters"""
    docs_folder: str = Field(default="sample_docs", description="Local documents folder")
    chunk_size: int = Field(default=512, description="Text chunk size")
    chunk_overlap: int = Field(default=50, description="Chunk overlap")
    max_triplets_per_chunk: int = Field(default=10, description="Max relationships per chunk")
    prompt_template: str = Field(default="default", description="Prompt template name (default, enhanced, business, research)")
    store_chunk_embeddings: bool = Field(default=True, description="Generate and store chunk embeddings for DOC_SEARCH mode")
    store_entity_embeddings: bool = Field(default=True, description="Generate and store entity embeddings for MCP server local_search")


class ExtractionPromptConfig(BaseModel):
    """Custom extraction prompt configuration"""
    custom_prompt: str = Field(default="", description="Custom extraction prompt (overrides template)")


class SchemaConfig(BaseModel):
    """JSON schema configuration for flexible document parsing"""
    document_id_field: str = Field(default="id", description="JSON field to use as document ID")
    content_fields: List[str] = Field(default=["content"], description="JSON fields to extract text from for graph building")
    metadata_fields: List[str] = Field(default=["subject", "author", "category", "tags"], description="JSON fields to preserve as metadata")


class FullConfig(BaseModel):
    """Complete configuration"""
    s3: S3Config
    neo4j: Neo4jConfig
    llm: LLMConfig
    embedding: EmbeddingConfig
    processing: ProcessingConfig
    schema_config: SchemaConfig = Field(alias="schema")
    extraction_prompt: ExtractionPromptConfig

    class Config:
        populate_by_name = True


class BuildGraphRequest(BaseModel):
    clear_first: bool = Field(default=False, description="Clear existing graph")


class QueryRequest(BaseModel):
    query: str = Field(..., description="Cypher query to execute")
    limit: int = Field(default=10, description="Maximum results")


class CreateVectorIndexRequest(BaseModel):
    entity_dimension: Optional[int] = Field(default=None, description="Dimension for entity vector index (auto-detect if not provided)")
    chunk_dimension: Optional[int] = Field(default=None, description="Dimension for chunk vector index (auto-detect if not provided)")
