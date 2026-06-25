# Design Document: AWS Bedrock Integration with Datadog LLM Observability

## Overview

This design specifies the integration of AWS Bedrock foundation models into the AIOps backend system, replacing the current mocked implementation with a production-ready client that uses boto3 to invoke real AWS Bedrock models. The integration incorporates Datadog LLM Observability through ddtrace span decorators, following patterns established in the DDStarter hackathon pack.

### Goals

- Replace mocked `BedrockClient` with real AWS Bedrock runtime client using boto3
- Instrument all LLM calls with Datadog LLM Observability using `@llm`, `@workflow`, `@tool`, and `@task` decorators
- Provide reusable utility modules based on DDStarter patterns for future LLM workflows
- Create test endpoints to verify AWS Bedrock connectivity and Datadog tracing
- Update configuration system to support AWS credentials and Datadog API keys

### Non-Goals

- Implementing streaming response handling (deferred to future iteration)
- Creating a full MCP agent workflow (basic MCP client provided, but not integrated into main flows)
- Cost optimization or caching strategies
- Fine-tuning or custom model deployment

### Key Technical Decisions

**Decision 1: Use Amazon Nova Pro as Default Model**

The requirements specify `amazon.nova-pro-v1:0` as the default model. Nova Pro is AWS's multimodal foundation model optimized for:
- Complex reasoning tasks (incident root cause analysis)
- Structured output generation
- Cost-effective performance for production workloads

Alternative models (Claude, Titan) can be configured via `BEDROCK_MODEL_ID` environment variable.

**Decision 2: Agentless LLM Observability Mode**

We enable Datadog LLMObs in agentless mode (`agentless_enabled=True`), which:
- Sends traces directly to Datadog API without requiring local Datadog Agent
- Simplifies deployment and reduces infrastructure dependencies
- Uses `DD_API_KEY` for authentication

This matches the DDStarter pattern and is appropriate for the AIOps backend architecture.

**Decision 3: Span Decorator Strategy**

Following DDStarter patterns, we use:
- `@workflow`: Root span for multi-step LLM operations (e.g., incident investigation)
- `@llm`: LLM invocation spans (Bedrock model calls)
- `@tool`: External tool calls (MCP server, data fetching)
- `@task`: Data processing steps (prompt construction, response parsing)

This creates a hierarchical trace structure visible in Datadog APM.

**Decision 4: Response Parsing for Nova Models**

Amazon Nova models return responses in the structure:
```json
{
  "output": {
    "message": {
      "content": [
        {"text": "response text"},
        {"toolUse": {...}}
      ]
    }
  },
  "stopReason": "end_turn" | "tool_use"
}
```

We extract text from `content[].text` blocks and preserve `toolUse` blocks for future agentic workflows.

## Architecture

### Component Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI Application                      │
│                         (main.py)                           │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │         LLMObs Initialization (startup)              │  │
│  │  - Enable agentless mode with DD_API_KEY            │  │
│  │  - Set ml_app from DD_LLMOBS_ML_APP                 │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              Test Endpoints                          │  │
│  │  /api/test/bedrock-health                           │  │
│  │  /api/test/bedrock-diagnostics                      │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │           BedrockClient                              │  │
│  │  - generate_incident_rca (@llm)                     │  │
│  │  - run_chat_turn (@llm)                             │  │
│  │  - _invoke_model (boto3 bedrock-runtime)           │  │
│  │  - _parse_response (extract text from Nova format)  │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │        DDStarter Utility Modules                     │  │
│  │  - basic_bedrock_call.py                            │  │
│  │  - traced_pipeline.py                               │  │
│  │  - mcp_client.py                                    │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                          │
        ┌─────────────────┴─────────────────┐
        │                                   │
        ▼                                   ▼
┌───────────────────┐            ┌──────────────────┐
│   AWS Bedrock     │            │  Datadog LLMObs  │
│  (boto3 client)   │            │   (agentless)    │
│                   │            │                  │
│ - invoke_model    │            │ - Trace spans    │
│ - Nova Pro model  │            │ - Token metrics  │
└───────────────────┘            │ - Error tracking │
                                 └──────────────────┘
```

### Integration Points

1. **Configuration Layer** (`app/core/config.py`)
   - Loads AWS credentials (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION)
   - Loads Datadog API keys (DD_API_KEY, DD_APP_KEY, DD_LLMOBS_ML_APP)
   - Provides BEDROCK_MODEL_ID with default "amazon.nova-pro-v1:0"

2. **Application Startup** (`app/main.py`)
   - Initialize LLMObs on startup event
   - Flush LLMObs traces on shutdown event

3. **Bedrock Client** (`app/integrations/bedrock/client.py`)
   - Replace mocked implementation with boto3 bedrock-runtime client
   - Decorate LLM methods with `@llm` for tracing
   - Annotate spans with input/output data

4. **Test Endpoints** (`app/api/endpoints/test.py` - new file)
   - POST /api/test/bedrock-health: Verify Bedrock connectivity
   - GET /api/test/bedrock-diagnostics: Check configuration status

## Components and Interfaces

### 1. Configuration System

**File:** `app/core/config.py`

**Updated Settings Class:**
```python
class Settings(BaseSettings):
    # Existing
    DATABASE_URL: str
    
    # AWS Bedrock Configuration
    AWS_ACCESS_KEY_ID: str = Field(default="")
    AWS_SECRET_ACCESS_KEY: str = Field(default="")
    AWS_REGION: str = Field(default="us-east-1")
    BEDROCK_MODEL_ID: str = Field(default="amazon.nova-pro-v1:0")
    
    # Datadog Configuration
    DD_API_KEY: str = Field(default="")
    DD_APP_KEY: str = Field(default="")
    DD_LLMOBS_ML_APP: str = Field(default="aiops-backend")
    DD_SITE: str = Field(default="datadoghq.com")
```

**Interface:**
- `settings.AWS_REGION` → Used to initialize boto3 client
- `settings.BEDROCK_MODEL_ID` → Model identifier for invoke_model calls
- `settings.DD_API_KEY` → Authentication for LLMObs.enable()
- `settings.DD_LLMOBS_ML_APP` → Application name in Datadog traces

### 2. BedrockClient

**File:** `app/integrations/bedrock/client.py`

**Class Interface:**
```python
class BedrockClient(BaseBedrockClient):
    def __init__(self):
        """Initialize boto3 bedrock-runtime client with AWS credentials"""
        
    @llm(model_name="nova-pro", model_provider="bedrock")
    def generate_incident_rca(
        self, 
        service_metrics: Dict[str, Any], 
        service_logs: List[Dict[str, Any]], 
        query: str
    ) -> Dict[str, Any]:
        """
        Generate root cause analysis for an incident.
        
        Args:
            service_metrics: Performance metrics (CPU, memory, latency)
            service_logs: Recent error logs
            query: User's investigation query
            
        Returns:
            Dict with summary, root_cause, and recommendations
        """
        
    @llm(model_name="nova-pro", model_provider="bedrock")
    def run_chat_turn(
        self, 
        history: List[Dict[str, str]], 
        message: str
    ) -> str:
        """
        Execute one turn of conversational chat.
        
        Args:
            history: List of {role, content} message objects
            message: New user message
            
        Returns:
            Assistant's text response
        """
        
    def _invoke_model(
        self, 
        messages: List[Dict], 
        max_tokens: int = 1024
    ) -> Dict:
        """
        Low-level Bedrock invocation using boto3.
        
        Args:
            messages: Nova-format messages [{"role": "user", "content": [...]}]
            max_tokens: Maximum tokens to generate
            
        Returns:
            Raw Bedrock response dict
        """
        
    def _parse_response(self, response: Dict) -> str:
        """
        Extract text content from Nova response structure.
        
        Args:
            response: Raw Bedrock response
            
        Returns:
            Concatenated text from all text content blocks
        """
```

**Implementation Notes:**

- boto3 client initialization uses environment variable authentication (AWS SDK automatically reads AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY)
- `@llm` decorator captures input prompts and output responses automatically when using `LLMObs.annotate()`
- Response parsing handles Nova's content array structure, extracting `{"text": "..."}` blocks
- Error handling wraps boto3 exceptions (ClientError, NoCredentialsError) with descriptive messages

### 3. DDStarter Utility Modules

**Location:** `app/utils/ddstarter/`

#### a) basic_bedrock_call.py

Minimal example demonstrating traced Bedrock invocation:

```python
def ask_bedrock(prompt: str, model_id: str = None) -> str:
    """
    Simple traced Bedrock call for quick testing.
    
    Args:
        prompt: Text prompt
        model_id: Optional override for BEDROCK_MODEL_ID
        
    Returns:
        Model response text
    """
```

#### b) traced_pipeline.py

Demonstrates full workflow with nested spans:

```python
@workflow
def run_investigation_pipeline(query: str) -> Dict:
    """Root workflow span for multi-step investigation"""
    
@tool
def fetch_datadog_metrics(service: str) -> Dict:
    """Tool span for external data fetching"""
    
@llm(model_name="nova-pro", model_provider="bedrock")
def analyze_data(context: str, query: str) -> str:
    """LLM span for Bedrock analysis"""
    
@task
def format_results(raw_response: str) -> Dict:
    """Task span for post-processing"""
```

#### c) mcp_client.py

MCP client for Datadog tool execution:

```python
class DatadogMCPClient:
    def __init__(self, api_key: str, app_key: str):
        """Initialize MCP client with Datadog credentials"""
        
    def initialize(self) -> None:
        """Send MCP initialize handshake"""
        
    def list_tools(self) -> List[Dict]:
        """Retrieve available Datadog MCP tools"""
        
    @tool
    def call_tool(self, name: str, arguments: Dict) -> str:
        """Execute MCP tool and return result (traced)"""
```

### 4. Test Endpoints

**File:** `app/api/endpoints/test.py` (new)

#### POST /api/test/bedrock-health

**Request Schema:**
```python
class BedrockHealthRequest(BaseModel):
    prompt: str = Field(default="Hello, respond with OK if you can read this.")
    model_id: Optional[str] = None
```

**Response Schema:**
```python
class BedrockHealthResponse(BaseModel):
    status: str  # "success" | "error"
    model_id: str
    response_text: Optional[str]
    response_time_ms: float
    error: Optional[str]
```

**Behavior:**
- Invokes Bedrock with test prompt
- Measures elapsed time
- Returns 200 on success, 500 on failure
- Traces call in Datadog LLMObs

#### GET /api/test/bedrock-diagnostics

**Response Schema:**
```python
class DiagnosticsResponse(BaseModel):
    status: str  # "healthy" | "degraded"
    aws_configured: bool
    datadog_configured: bool
    llmobs_enabled: bool
    configuration: Dict[str, str]
```

**Behavior:**
- Checks if AWS credentials are set (non-empty AWS_ACCESS_KEY_ID)
- Checks if Datadog keys are set (non-empty DD_API_KEY)
- Returns configuration values (region, model_id, ml_app)
- Returns 200 if all checks pass, 503 if any check fails

### 5. Application Lifecycle Hooks

**File:** `app/main.py`

**Startup Event:**
```python
@app.on_event("startup")
async def startup_event():
    """Initialize Datadog LLM Observability"""
    if settings.DD_API_KEY:
        LLMObs.enable(
            ml_app=settings.DD_LLMOBS_ML_APP,
            agentless_enabled=True,
            api_key=settings.DD_API_KEY,
            site=settings.DD_SITE
        )
        logger.info("Datadog LLM Observability enabled")
```

**Shutdown Event:**
```python
@app.on_event("shutdown")
async def shutdown_event():
    """Flush Datadog traces before exit"""
    if settings.DD_API_KEY:
        LLMObs.flush()
        logger.info("Datadog LLM Observability flushed")
```

## Data Models

### Bedrock Request Format (Nova)

```python
BedrockRequestBody = {
    "messages": [
        {
            "role": "user" | "assistant",
            "content": [
                {"text": str},
                {"toolUse": {...}}  # Optional
            ]
        }
    ],
    "inferenceConfig": {
        "max_new_tokens": int,
        "temperature": float,  # Optional
        "topP": float         # Optional
    },
    "toolConfig": {  # Optional, for tool calling
        "tools": [
            {
                "toolSpec": {
                    "name": str,
                    "description": str,
                    "inputSchema": {"json": {...}}
                }
            }
        ]
    }
}
```

### Bedrock Response Format (Nova)

```python
BedrockResponse = {
    "output": {
        "message": {
            "role": "assistant",
            "content": [
                {"text": str},
                {"toolUse": {
                    "toolUseId": str,
                    "name": str,
                    "input": dict
                }}
            ]
        }
    },
    "stopReason": "end_turn" | "tool_use" | "max_tokens",
    "usage": {
        "inputTokens": int,
        "outputTokens": int,
        "totalTokens": int
    }
}
```

### LLMObs Span Annotation Format

```python
# Input annotation for @llm spans
LLMObs.annotate(
    input_data=[
        {"role": "user", "content": "prompt text"},
        {"role": "assistant", "content": "previous response"}
    ]
)

# Output annotation for @llm spans
LLMObs.annotate(
    output_data=[
        {"role": "assistant", "content": "model response"}
    ]
)

# Tags for additional metadata
LLMObs.annotate(
    tags={
        "model.temperature": "0.7",
        "model.tokens.input": "150",
        "model.tokens.output": "300"
    }
)
```

### Environment Configuration Model

```python
# Required in .env
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=secret...
AWS_REGION=us-east-1
BEDROCK_MODEL_ID=amazon.nova-pro-v1:0

DD_API_KEY=abc123...
DD_APP_KEY=def456...
DD_LLMOBS_ML_APP=aiops-backend
DD_SITE=datadoghq.com
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

```

### Component Interaction Flow

#### Chat Message Flow

1. User sends message from frontend to `/api/chat/sessions/{id}/messages`
2. Endpoint persists user message to database
3. Endpoint retrieves conversation history from database
4. Endpoint invokes `BedrockClient.run_chat_turn()` with history and new message
5. BedrockClient constructs AWS Bedrock API payload with messages array
6. BedrockClient invokes AWS Bedrock (traced with @llm decorator)
7. Response is parsed and returned to endpoint
8. Assistant message is persisted to database
9. Response sent back to frontend

#### Test Endpoint Flow

1. Test client POSTs to `/api/test/bedrock-health` with test prompt
2. Endpoint invokes BedrockClient with provided prompt
3. Bedrock call is timed and traced
4. Success/failure response with metadata returned to client

### Key Design Decisions

**Decision 1: Use Amazon Nova Pro as default model**
- Rationale: Nova Pro provides good balance of performance and cost
- Alternative considered: Claude 3, but Nova is AWS-native and simpler to start with
- Impact: Model ID is configurable via environment variable for flexibility

**Decision 2: Agentless Datadog LLM Observability**
- Rationale: Simplifies deployment, no need to run Datadog agent
- Alternative considered: Agent-based observability, but adds infrastructure complexity
- Impact: Requires DD_API_KEY to be configured, but reduces deployment dependencies

**Decision 3: Separate utility modules following DDStarter patterns**
- Rationale: Promotes code reuse and consistency with proven patterns
- Alternative considered: Inline all tracing logic, but reduces maintainability
- Impact: Creates additional modules but improves testability and clarity

**Decision 4: Add model selection to chat interface**
- Rationale: Allows users to choose between different model capabilities
- Alternative considered: Fixed model only, but limits flexibility
- Impact: Requires frontend dropdown and backend parameter handling


## Components and Interfaces

### BedrockClient (Core Integration)

**Location:** `app/integrations/bedrock/client.py`

**Purpose:** Primary interface to AWS Bedrock, replacing mocked implementation with real API calls.

**Key Methods:**

```python
class BedrockClient:
    def __init__(self, region: str = None, model_id: str = None):
        """Initialize boto3 bedrock-runtime client with credentials from config."""
        
    @llm(model_name='nova-pro', model_provider='bedrock')
    def run_chat_turn(
        self, 
        history: List[Dict[str, str]], 
        message: str,
        model_id: str = None
    ) -> str:
        """
        Execute a single chat turn with Bedrock.
        
        Args:
            history: Conversation history [{"role": "user|assistant", "content": "..."}]
            message: New user message
            model_id: Optional override for model selection
            
        Returns:
            Model response text
            
        Raises:
            BedrockInvocationError: If AWS call fails
        """
        
    @llm(model_name='nova-pro', model_provider='bedrock')
    def generate_incident_rca(
        self, 
        service_metrics: Dict[str, Any], 
        service_logs: List[Dict[str, Any]], 
        query: str
    ) -> Dict[str, Any]:
        """
        Generate incident root cause analysis using Bedrock.
        
        Args:
            service_metrics: Metrics data for the service
            service_logs: Log entries related to incident
            query: User's investigation query
            
        Returns:
            Structured RCA response with summary, root_cause, and recommendations
        """
```

**Dependencies:**
- `boto3`: AWS SDK for Python
- `ddtrace.llmobs.decorators`: @llm decorator for tracing
- `app.core.config.settings`: Configuration access

**Error Handling:**
- Wraps AWS ClientError exceptions in custom BedrockInvocationError
- Includes original error message and type for debugging
- Logs errors with context before re-raising


### Response Parser

**Location:** `app/integrations/bedrock/parser.py`

**Purpose:** Extract text content from AWS Bedrock response structures.

**Key Functions:**

```python
def extract_text_from_content(content: List[Dict[str, Any]]) -> str:
    """
    Extract text from Bedrock response content blocks.
    
    Args:
        content: Response content array from output.message.content
        
    Returns:
        Concatenated text from all text blocks
        
    Example:
        content = [{"text": "Hello"}, {"text": " world"}]
        result = "Hello world"
    """
    
def parse_bedrock_response(response_body: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parse full Bedrock response into structured format.
    
    Args:
        response_body: JSON response from invoke_model
        
    Returns:
        {
            "text": str,
            "stop_reason": str,
            "usage": dict (if available)
        }
    """
```

### Configuration Extensions

**Location:** `app/core/config.py`

**New Fields Added to Settings Class:**

```python
class Settings(BaseSettings):
    # Existing fields...
    DATABASE_URL: str
    
    # AWS Bedrock Configuration
    AWS_ACCESS_KEY_ID: str = Field(default="")
    AWS_SECRET_ACCESS_KEY: str = Field(default="")
    AWS_REGION: str = Field(default="us-east-1")
    BEDROCK_MODEL_ID: str = Field(default="amazon.nova-pro-v1:0")
    
    # Datadog LLM Observability Configuration
    DD_API_KEY: str = Field(default="")
    DD_APP_KEY: str = Field(default="")
    DD_LLMOBS_ML_APP: str = Field(default="aiops-backend")
    DD_SITE: str = Field(default="datadoghq.com")
```

**Environment Variables Required:**
- AWS_ACCESS_KEY_ID
- AWS_SECRET_ACCESS_KEY
- AWS_REGION
- DD_API_KEY
- DD_APP_KEY
- DD_LLMOBS_ML_APP


### DDStarter Utility Modules

**Location:** `app/utils/ddstarter/`

These modules encapsulate reusable patterns from the DDStarter hackathon pack.

#### basic_bedrock.py

```python
from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import llm
import boto3
import json

@llm(model_name='nova-pro', model_provider='bedrock')
def invoke_bedrock_simple(prompt: str, model_id: str, region: str) -> str:
    """
    Simple Bedrock invocation with tracing.
    Pattern from basic-bedrock-call.py
    """
```

#### traced_workflow.py

```python
from ddtrace.llmobs.decorators import workflow, llm, tool, task

@workflow
def execute_traced_pipeline(prompt: str, context: str) -> str:
    """
    Execute multi-step traced workflow.
    Pattern from bedrock-decorator-example.py
    """

@tool
def fetch_context(prompt: str) -> str:
    """Tool span for context retrieval."""

@task
def process_llm_result(response: str) -> str:
    """Task span for post-processing."""
```

#### mcp_integration.py

```python
class DatadogMCPClient:
    """
    MCP client for Datadog tool integration.
    Pattern from bedrock-mcp-agent.py
    """
    
    def __init__(self, api_key: str, app_key: str):
        """Initialize MCP client with Datadog credentials."""
        
    def initialize(self) -> None:
        """Send initialize request to MCP server."""
        
    def list_tools(self) -> List[Dict[str, Any]]:
        """Retrieve available MCP tools."""
        
    def call_tool(self, name: str, arguments: Dict[str, Any]) -> str:
        """Execute MCP tool and return result."""
```


### Chat API Endpoint Updates

**Location:** `app/api/endpoints/chat.py`

**Updated Endpoint:**

```python
@router.post("/sessions/{id}/messages", response_model=ChatMessageOut)
def create_chat_message(
    id: uuid.UUID, 
    message_in: ChatMessageCreate, 
    model_id: Optional[str] = None,
    db: Session = Depends(get_db)
) -> ChatMessageOut:
    """
    Create new chat message and get Bedrock response.
    
    Flow:
    1. Persist user message to database
    2. Retrieve conversation history
    3. Invoke BedrockClient with history and new message
    4. Persist assistant response to database
    5. Return assistant message
    
    Args:
        id: Chat session UUID
        message_in: User message content
        model_id: Optional Bedrock model ID override
        db: Database session
        
    Returns:
        Assistant's response message
        
    Raises:
        HTTPException 404: Session not found
        HTTPException 500: Bedrock invocation failed
    """
```

**Error Handling:**
- Catch BedrockInvocationError and return 500 with error details
- Validate session exists before processing
- Rollback database transaction on failure

### Test Endpoints

**Location:** `app/api/endpoints/test.py` (new file)

**Endpoints:**

```python
@router.post("/bedrock-health")
def test_bedrock_health(
    prompt: str = Body(..., embed=True),
    model_id: Optional[str] = Body(None, embed=True)
) -> Dict[str, Any]:
    """
    Test AWS Bedrock connectivity.
    
    Returns:
        {
            "status": "success" | "error",
            "model_id": str,
            "response": str (if success),
            "response_time_ms": float,
            "error": str (if error)
        }
    """

@router.get("/bedrock-diagnostics")
def get_bedrock_diagnostics() -> Dict[str, Any]:
    """
    Check Bedrock and Datadog configuration status.
    
    Returns:
        {
            "aws_configured": bool,
            "datadog_configured": bool,
            "llmobs_enabled": bool,
            "region": str,
            "model_id": str,
            "ml_app": str
        }
    """
```


### Application Startup Integration

**Location:** `app/main.py`

**Lifecycle Hooks:**

```python
from ddtrace.llmobs import LLMObs
from app.core.config import settings

@app.on_event("startup")
async def startup_event():
    """Initialize LLM Observability on application startup."""
    if settings.DD_API_KEY and settings.DD_LLMOBS_ML_APP:
        LLMObs.enable(
            ml_app=settings.DD_LLMOBS_ML_APP,
            agentless_enabled=True,
            api_key=settings.DD_API_KEY,
            site=settings.DD_SITE
        )
        logger.info("Datadog LLM Observability enabled")
    else:
        logger.warning("Datadog LLM Observability not configured")

@app.on_event("shutdown")
async def shutdown_event():
    """Flush remaining traces on application shutdown."""
    try:
        LLMObs.flush()
        logger.info("Flushed LLM Observability traces")
    except Exception as e:
        logger.error(f"Error flushing LLMObs traces: {e}")
```

### Frontend Integration (Chat Interface)

**Location:** Frontend chat component (out of scope for backend design, but interface specified)

**API Contract Updates:**

The chat endpoint will accept an optional `model_id` parameter in the request body:

```json
POST /api/chat/sessions/{id}/messages
{
  "content": "User message here",
  "model_id": "amazon.nova-pro-v1:0"
}
```

**Supported Model IDs:**
- `amazon.nova-pro-v1:0` (default)
- `amazon.nova-lite-v1:0`
- `amazon.nova-micro-v1:0`
- `anthropic.claude-3-sonnet-20240229-v1:0`
- `anthropic.claude-3-haiku-20240307-v1:0`

Frontend should provide a dropdown selector that sets this parameter. If not provided, the default from configuration is used.


### Property 1: Nova Response Text Extraction

*For any* Nova-formatted Bedrock response containing one or more content blocks, the response parser SHALL extract and concatenate all text from content blocks with type "text", preserving order and ignoring non-text blocks.

**Validates: Requirements 1.4, 8.1, 8.2**

### Property 2: Tool Use Block Preservation

*For any* Nova response containing mixed text and toolUse content blocks, the parser SHALL distinguish between text content and tool invocation data, preserving tool use information separately from extracted text.

**Validates: Requirements 8.3**

### Property 3: Incident RCA Prompt Construction

*For any* combination of service metrics (CPU, memory, latency), service logs (errors, warnings), and investigation query, the generate_incident_rca method SHALL construct a structured prompt that includes all provided metrics, all provided logs, and the complete query text in a format suitable for root cause analysis.

**Validates: Requirements 1.2, 9.3**

### Property 4: Chat Message Format Conversion

*For any* conversation history containing one or more messages with role and content fields, the run_chat_turn method SHALL convert the history into Nova message format with each message containing a role ("user" or "assistant") and content array with text blocks, preserving message order and content.

**Validates: Requirements 1.3, 9.4**

### Property 5: Span Annotation Completeness

*For any* LLM invocation with input data (prompt or messages) and output data (model response), the @llm decorated method SHALL annotate the span with both input_data and output_data in Datadog-compatible format before the span closes.

**Validates: Requirements 3.4, 3.5**

### Property 6: Conditional Token Metadata Annotation

*For any* Bedrock response, if the response contains usage data with inputTokens, outputTokens, and totalTokens fields, the client SHALL annotate the span with token count tags; if usage data is absent, the client SHALL complete without error and without token tags.

**Validates: Requirements 9.5**

## Error Handling

### AWS Bedrock Errors

**NoCredentialsError:**
- Raised when AWS_ACCESS_KEY_ID or AWS_SECRET_ACCESS_KEY are missing or invalid
- Wrapped in custom exception: `BedrockConfigurationError("AWS credentials not configured")`
- Logged at ERROR level with guidance to check .env file

**ClientError:**
- Raised by boto3 when Bedrock API call fails
- Common causes: Invalid model ID, throttling, service unavailable
- Wrapped with error code and message: `BedrockInvocationError(f"Bedrock call failed: {error_code} - {message}")`
- Logged at ERROR level with request details

**ValidationException:**
- Raised when request body is malformed or exceeds limits
- Wrapped in: `BedrockValidationError("Invalid request format")`
- Includes details about which field failed validation

**ThrottlingException:**
- Raised when rate limits are exceeded
- Wrapped in: `BedrockThrottlingError("Rate limit exceeded, retry after backoff")`
- Includes retry-after header value if available

### Response Parsing Errors

**MalformedResponseError:**
- Raised when response JSON structure doesn't match Nova schema
- Includes the actual structure received for debugging
- Example: Missing `output.message.content` path

**EmptyResponseError:**
- Raised when response contains no text content blocks
- Indicates model returned only tool calls or empty response
- Includes stopReason for context

### Datadog LLMObs Errors

**LLMObs Initialization Failures:**
- If DD_API_KEY is invalid, LLMObs.enable() logs warning but doesn't crash application
- Application continues without tracing
- Logged at WARNING level: "Datadog LLM Observability initialization failed"

**Span Annotation Failures:**
- If LLMObs.annotate() fails (malformed data), exception is caught and logged
- LLM call continues normally, but span may lack metadata
- Logged at WARNING level with annotation data that failed

### Test Endpoint Error Responses

**/api/test/bedrock-health:**
```python
# Success (200)
{
  "status": "success",
  "model_id": "amazon.nova-pro-v1:0",
  "response_text": "...",
  "response_time_ms": 1234.56
}

# Error (500)
{
  "status": "error",
  "model_id": "amazon.nova-pro-v1:0",
  "response_text": null,
  "response_time_ms": 0,
  "error": "NoCredentialsError: AWS credentials not configured"
}
```

**/api/test/bedrock-diagnostics:**
```python
# Healthy (200)
{
  "status": "healthy",
  "aws_configured": true,
  "datadog_configured": true,
  "llmobs_enabled": true,
  "configuration": {
    "region": "us-east-1",
    "model_id": "amazon.nova-pro-v1:0",
    "ml_app": "aiops-backend"
  }
}

# Degraded (503)
{
  "status": "degraded",
  "aws_configured": false,
  "datadog_configured": true,
  "llmobs_enabled": false,
  "configuration": {...},
  "errors": ["AWS_ACCESS_KEY_ID not set", "LLMObs not enabled"]
}
```

### Error Handling Strategy

1. **Fail Fast on Configuration Errors:**
   - Missing AWS credentials during initialization → Raise exception in __init__
   - Invalid model ID → Fail on first invoke_model call with clear error

2. **Graceful Degradation for Observability:**
   - LLMObs initialization failure → Log warning, continue without tracing
   - Span annotation failure → Log warning, continue with LLM call

3. **Retry Logic (Not Implemented in Initial Version):**
   - Throttling errors: Defer to boto3's built-in retry logic
   - Service unavailable: Caller responsible for retry (FastAPI endpoint layer)

4. **Logging Standards:**
   - ERROR level: AWS authentication failures, Bedrock invocation failures, parsing errors
   - WARNING level: LLMObs failures, configuration issues that don't block functionality
   - INFO level: Successful LLM calls with token counts

## Testing Strategy

### Overview

This feature uses a **dual testing approach** combining example-based unit tests for specific scenarios and configuration checks with integration tests for AWS and Datadog connectivity.

**Property-based testing is NOT applicable** for this integration feature because:
- Most functionality involves AWS external service calls (integration behavior)
- Configuration and environment setup are one-time checks (smoke tests)
- Span decorator application is structural validation (code inspection)

However, the **core parsing and formatting logic** (properties 1-4) will be tested with **example-based unit tests** using multiple carefully chosen examples representing edge cases:
- Empty responses, single text block, multiple text blocks, mixed text/tool_use blocks
- Various metric/log/query combinations for prompt construction
- Different conversation history lengths and formats

### Unit Tests

**Target:** Core logic in `BedrockClient` and utility modules  
**Framework:** pytest  
**Mocking:** boto3 client, LLMObs

#### Test Cases for Response Parsing (Properties 1, 2)

```python
def test_parse_response_single_text_block():
    """Test extracting text from response with one text block"""
    
def test_parse_response_multiple_text_blocks():
    """Test concatenating text from multiple text blocks"""
    
def test_parse_response_empty_content():
    """Test handling response with no content blocks"""
    
def test_parse_response_mixed_text_and_tool_use():
    """Test extracting text while preserving tool_use blocks"""
    
def test_parse_response_tool_use_only():
    """Test response with only tool_use blocks, no text"""
    
def test_parse_response_malformed():
    """Test error handling for malformed Nova response"""
```

#### Test Cases for Prompt Construction (Property 3)

```python
def test_generate_incident_rca_formats_metrics():
    """Test prompt includes all service metrics (CPU, memory, latency)"""
    
def test_generate_incident_rca_formats_logs():
    """Test prompt includes all log entries with timestamps"""
    
def test_generate_incident_rca_includes_query():
    """Test user query is included in prompt"""
    
def test_generate_incident_rca_empty_metrics():
    """Test handling when metrics dict is empty"""
    
def test_generate_incident_rca_empty_logs():
    """Test handling when logs list is empty"""
```

#### Test Cases for Message Formatting (Property 4)

```python
def test_run_chat_turn_formats_single_message():
    """Test converting one-message history to Nova format"""
    
def test_run_chat_turn_formats_multi_turn():
    """Test converting multi-turn conversation to Nova format"""
    
def test_run_chat_turn_empty_history():
    """Test handling empty conversation history"""
    
def test_run_chat_turn_preserves_role_order():
    """Test user/assistant roles are preserved in order"""
```

#### Test Cases for Span Annotation (Properties 5, 6)

```python
def test_llm_annotates_input_data(mock_llmobs):
    """Test @llm method calls LLMObs.annotate with input_data"""
    
def test_llm_annotates_output_data(mock_llmobs):
    """Test @llm method calls LLMObs.annotate with output_data"""
    
def test_llm_annotates_tokens_when_present(mock_llmobs):
    """Test token tags added when response includes usage data"""
    
def test_llm_no_token_annotation_when_absent(mock_llmobs):
    """Test no error when response lacks usage data"""
```

#### Test Cases for Error Handling

```python
def test_invoke_model_no_credentials():
    """Test NoCredentialsError is wrapped in BedrockConfigurationError"""
    
def test_invoke_model_client_error():
    """Test ClientError is wrapped with error details"""
    
def test_invoke_model_throttling():
    """Test ThrottlingException is wrapped appropriately"""
    
def test_parse_response_missing_output_key():
    """Test MalformedResponseError for missing 'output' key"""
```

### Integration Tests

**Target:** End-to-end flows with real AWS and Datadog services  
**Prerequisites:** Valid AWS credentials and Datadog API keys in test environment  
**Framework:** pytest with integration marker

#### Test Cases for Bedrock Integration

```python
@pytest.mark.integration
def test_bedrock_health_endpoint_real_call():
    """Test /api/test/bedrock-health with actual Bedrock invocation"""
    
@pytest.mark.integration
def test_generate_incident_rca_real_bedrock():
    """Test generate_incident_rca with real AWS Bedrock call"""
    
@pytest.mark.integration
def test_run_chat_turn_real_bedrock():
    """Test run_chat_turn with real conversation"""
```

#### Test Cases for Datadog LLMObs Integration

```python
@pytest.mark.integration
def test_llmobs_trace_appears_in_datadog():
    """Test that LLM calls create traces visible in Datadog API"""
    
@pytest.mark.integration
def test_workflow_creates_nested_spans():
    """Test @workflow, @llm, @tool create hierarchical spans"""
```

### Smoke Tests

**Target:** Configuration, dependencies, endpoint registration  
**Framework:** pytest

#### Configuration Validation

```python
def test_env_example_documents_aws_credentials():
    """Test .env.example contains AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY"""
    
def test_env_example_documents_datadog_keys():
    """Test .env.example contains DD_API_KEY, DD_APP_KEY"""
    
def test_settings_has_aws_fields():
    """Test Settings class defines AWS credential fields"""
    
def test_settings_has_bedrock_model_id_default():
    """Test BEDROCK_MODEL_ID defaults to amazon.nova-pro-v1:0"""
```

#### Dependency Validation

```python
def test_requirements_includes_boto3():
    """Test requirements.txt contains boto3"""
    
def test_requirements_includes_ddtrace():
    """Test requirements.txt contains ddtrace"""
```

#### Endpoint Registration

```python
def test_bedrock_health_endpoint_registered():
    """Test /api/test/bedrock-health is accessible"""
    
def test_bedrock_diagnostics_endpoint_registered():
    """Test /api/test/bedrock-diagnostics is accessible"""
```

#### Decorator Application

```python
def test_generate_incident_rca_has_llm_decorator():
    """Test @llm decorator applied to generate_incident_rca"""
    
def test_run_chat_turn_has_llm_decorator():
    """Test @llm decorator applied to run_chat_turn"""
```

### Test Execution Order

1. **Smoke tests** (fast, no external dependencies)
2. **Unit tests** with mocks (fast, isolated)
3. **Integration tests** (slow, requires AWS/Datadog credentials)

### Test Coverage Goals

- **Line coverage:** >90% for BedrockClient, utility modules
- **Branch coverage:** >85% for error handling paths
- **Integration coverage:** All public methods called with real services at least once

### Continuous Integration

- Smoke and unit tests run on every commit
- Integration tests run nightly or on release branches (require secrets)
- Test results published to Datadog CI Visibility for tracking


## Data Models

### Bedrock Request/Response Structures

#### Chat Turn Request (to AWS Bedrock)

```json
{
  "messages": [
    {
      "role": "user",
      "content": [{"text": "First user message"}]
    },
    {
      "role": "assistant",
      "content": [{"text": "Assistant response"}]
    },
    {
      "role": "user",
      "content": [{"text": "Follow-up message"}]
    }
  ],
  "inferenceConfig": {
    "max_new_tokens": 2048,
    "temperature": 0.7,
    "topP": 0.9
  }
}
```

#### Chat Turn Response (from AWS Bedrock)

```json
{
  "output": {
    "message": {
      "role": "assistant",
      "content": [
        {
          "text": "Model response text here"
        }
      ]
    }
  },
  "stopReason": "end_turn",
  "usage": {
    "inputTokens": 150,
    "outputTokens": 200,
    "totalTokens": 350
  }
}
```

#### RCA Request Structure (Internal)

```python
{
    "service_metrics": {
        "cpu_usage": [75.2, 80.1, 95.3],
        "memory_usage": [60.5, 65.2, 70.1],
        "error_rate": [0.01, 0.05, 0.15]
    },
    "service_logs": [
        {
            "timestamp": "2024-01-15T10:30:00Z",
            "level": "ERROR",
            "message": "Connection timeout to database"
        }
    ],
    "query": "Why is the service experiencing high error rates?"
}
```


#### RCA Response Structure (Internal)

```python
{
    "status": "success",
    "data": {
        "summary": "High error rates detected starting at 10:25 AM",
        "root_cause": "Database connection pool exhaustion due to increased traffic",
        "recommendations": [
            "Increase database connection pool size",
            "Add connection timeout monitoring",
            "Review query performance for long-running queries"
        ],
        "confidence": 0.85
    }
}
```

### Pydantic Schema Updates

**Location:** `app/schemas/chat.py`

**New Schema for Model Selection:**

```python
class ChatMessageCreate(BaseModel):
    content: str
    model_id: Optional[str] = None  # New field for model selection
    
    class Config:
        json_schema_extra = {
            "example": {
                "content": "What is causing the high CPU usage?",
                "model_id": "amazon.nova-pro-v1:0"
            }
        }
```

**Test Endpoint Schemas:**

**Location:** `app/schemas/test.py` (new file)

```python
class BedrockHealthRequest(BaseModel):
    prompt: str
    model_id: Optional[str] = None

class BedrockHealthResponse(BaseModel):
    status: str  # "success" | "error"
    model_id: str
    response: Optional[str] = None
    response_time_ms: float
    error: Optional[str] = None

class BedrockDiagnosticsResponse(BaseModel):
    aws_configured: bool
    datadog_configured: bool
    llmobs_enabled: bool
    region: str
    model_id: str
    ml_app: str
```


### Database Schema

No changes to existing database schema required. The integration uses existing chat_sessions and chat_messages tables.

**Relevant existing tables:**

- `chat_sessions`: Stores conversation sessions
- `chat_messages`: Stores individual messages with role (user/assistant)

The model_id parameter is not persisted to the database in this iteration - it's only used at request time. Future enhancement could add a model_id column to chat_messages for tracking which model generated each response.

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property Reflection

After analyzing the acceptance criteria, most requirements fall into integration testing, example-based testing, or smoke testing categories. The primary candidates for property-based testing are:

1. **Response parsing logic** (Requirements 1.4, 8.1, 8.2, 8.3) - Our code that extracts text from various AWS response structures
2. Edge cases like multiple content blocks and mixed content types are handled by comprehensive property generators

These can be consolidated into a single comprehensive property about response parsing correctness.

Other requirements are:
- **Infrastructure/AWS integration** (1.2, 1.3, 3.2-3.7, 6.2, 9.1-9.5) - Testing external AWS behavior
- **Configuration checks** (2.1-2.5, 7.1-7.10) - One-time setup validation
- **Specific API contracts** (6.1, 6.3-6.6, 10.1-10.6) - Example-based tests
- **Error handling** (1.5, 8.4) - Specific error scenarios

### Property 1: Response Parsing Correctness

*For any* valid AWS Bedrock response structure containing content blocks of type "text" and/or "tool_use", the response parser SHALL correctly extract all text content, preserve tool_use information separately, and concatenate multiple text blocks in order.

**Validates: Requirements 1.4, 8.1, 8.2, 8.3**

**Test Strategy:**
- Generate random valid Nova response structures with:
  - Varying numbers of content blocks (0 to 10)
  - Mix of "text" and "tool_use" block types
  - Various text content (empty strings, unicode, long text)
  - Valid tool_use structures
- Verify extracted text matches expected concatenation
- Verify tool_use blocks are preserved
- Verify order is maintained


## Error Handling

### Error Categories

#### AWS Bedrock Errors

**BedrockInvocationError (Custom Exception)**

Wraps all AWS Bedrock invocation failures with enhanced context.

```python
class BedrockInvocationError(Exception):
    """Raised when AWS Bedrock invocation fails."""
    
    def __init__(self, message: str, original_error: Exception, model_id: str):
        self.message = message
        self.original_error = original_error
        self.model_id = model_id
        super().__init__(self.message)
```

**Common AWS Error Codes:**
- `ThrottlingException`: Rate limit exceeded
- `ValidationException`: Invalid request parameters
- `ModelNotReadyException`: Model is loading
- `AccessDeniedException`: Insufficient permissions
- `ResourceNotFoundException`: Model ID not found

**Handling Strategy:**
- Log error with full context (model_id, request params, AWS error code)
- Wrap in BedrockInvocationError with user-friendly message
- Return 500 to API client with sanitized error (no AWS account details)

#### Configuration Errors

**ConfigurationError (Custom Exception)**

```python
class ConfigurationError(Exception):
    """Raised when required configuration is missing or invalid."""
    pass
```

**Scenarios:**
- Missing AWS credentials (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
- Missing Datadog API keys (DD_API_KEY, DD_APP_KEY)
- Invalid region name
- Invalid model ID format

**Handling Strategy:**
- Raise at application startup if critical config missing
- Provide clear error message indicating which variable is missing
- Log to application logs
- Diagnostics endpoint returns 503 with missing config details


#### Response Parsing Errors

**ResponseParsingError (Custom Exception)**

```python
class ResponseParsingError(Exception):
    """Raised when Bedrock response cannot be parsed."""
    
    def __init__(self, message: str, response_body: dict):
        self.message = message
        self.response_body = response_body
        super().__init__(self.message)
```

**Scenarios:**
- Missing expected fields (output, message, content)
- Unexpected response structure
- Invalid JSON in response body
- Empty content array when text expected

**Handling Strategy:**
- Log full response body for debugging
- Raise ResponseParsingError with context
- Convert to 500 error at API level
- Include sanitized error message in API response

#### Database Errors

Existing database error handling remains unchanged. SQLAlchemy errors are caught at the repository level.

**Rollback Strategy:**
- If Bedrock call fails after user message persisted, message remains in DB
- No automatic cleanup (allows debugging and retry)
- Future enhancement: Add message status field (pending, completed, failed)

### Retry Logic

**Initial Implementation: No Automatic Retries**

Rationale: LLM calls are expensive and potentially non-idempotent. Let users retry manually via UI.

**Future Enhancement Considerations:**
- Add retry logic for transient errors (ThrottlingException, 5xx errors)
- Implement exponential backoff
- Max 3 retry attempts
- Only retry if request is idempotent (same prompt + history)

### Logging Strategy

**Log Levels:**

- **INFO**: Successful LLM calls with token counts
- **WARNING**: Configuration issues, missing optional settings
- **ERROR**: AWS invocation failures, parsing errors
- **DEBUG**: Full request/response bodies (sanitize sensitive data)

**Log Format:**

```python
logger.info(
    "Bedrock invocation successful",
    extra={
        "model_id": model_id,
        "input_tokens": usage.get("inputTokens"),
        "output_tokens": usage.get("outputTokens"),
        "response_time_ms": elapsed_ms
    }
)
```

**PII/Sensitive Data Handling:**
- Never log AWS credentials
- Sanitize user prompts in logs (truncate to 100 chars)
- Log full responses only at DEBUG level
- Redact Datadog API keys in diagnostic outputs


## Testing Strategy

### Testing Approach Overview

This integration involves multiple layers requiring different testing strategies:

1. **Property-Based Tests**: For response parsing logic (our code, pure functions)
2. **Unit Tests**: For specific behaviors, error handling, configuration loading
3. **Integration Tests**: For AWS Bedrock calls (mocked), Datadog tracing (mocked), endpoint contracts
4. **Smoke Tests**: For configuration validation, dependency checks
5. **Manual Tests**: For end-to-end AWS connectivity, Datadog trace visibility

### Property-Based Testing

**Scope:** Response parsing logic only

**Library:** `hypothesis` for Python

**Configuration:**
- Minimum 100 iterations per property test
- Use `@given` decorator with custom strategies
- Tag format: `# Feature: bedrock-integration, Property 1: Response Parsing Correctness`

**Test Structure:**

```python
from hypothesis import given, strategies as st
import pytest

# Strategy for generating valid Bedrock response structures
@st.composite
def bedrock_response_strategy(draw):
    num_blocks = draw(st.integers(min_value=0, max_value=10))
    content_blocks = []
    
    for _ in range(num_blocks):
        block_type = draw(st.sampled_from(["text", "tool_use"]))
        if block_type == "text":
            content_blocks.append({
                "text": draw(st.text(min_size=0, max_size=500))
            })
        else:
            content_blocks.append({
                "toolUse": {
                    "toolUseId": draw(st.uuids()).hex,
                    "name": draw(st.text(min_size=1, max_size=50)),
                    "input": draw(st.dictionaries(
                        st.text(min_size=1, max_size=20),
                        st.text(min_size=0, max_size=100)
                    ))
                }
            })
    
    return {
        "output": {
            "message": {
                "role": "assistant",
                "content": content_blocks
            }
        },
        "stopReason": draw(st.sampled_from(["end_turn", "tool_use", "max_tokens"]))
    }

# Feature: bedrock-integration, Property 1: Response Parsing Correctness
@given(response=bedrock_response_strategy())
def test_response_parsing_correctness(response):
    """
    Property: For any valid Bedrock response, parser extracts all text correctly.
    """
    from app.integrations.bedrock.parser import parse_bedrock_response
    
    result = parse_bedrock_response(response)
    
    # Verify text extraction
    expected_texts = [
        block["text"] 
        for block in response["output"]["message"]["content"] 
        if "text" in block
    ]
    expected_text = "".join(expected_texts)
    
    assert result["text"] == expected_text
    assert result["stop_reason"] == response["stopReason"]
    
    # Verify tool_use preservation
    tool_uses = [
        block["toolUse"] 
        for block in response["output"]["message"]["content"] 
        if "toolUse" in block
    ]
    if tool_uses:
        assert "tool_uses" in result
        assert len(result["tool_uses"]) == len(tool_uses)
```


### Unit Testing

**Scope:** Specific behaviors, edge cases, error handling

**Test Cases:**

1. **Configuration Loading**
   - Test Settings loads AWS credentials from environment
   - Test default values applied when env vars missing
   - Test ConfigurationError raised for invalid region format

2. **Error Handling**
   - Test BedrockInvocationError wraps AWS ClientError
   - Test ResponseParsingError for malformed JSON
   - Test missing required fields in response
   - Test empty content array handling

3. **Message Formatting**
   - Test conversation history converted to Bedrock message format
   - Test user/assistant roles preserved
   - Test empty history handled correctly

4. **RCA Prompt Construction**
   - Test metrics formatted into prompt correctly
   - Test logs included in prompt structure
   - Test query appended appropriately

**Example Unit Test:**

```python
import pytest
from unittest.mock import patch, MagicMock
from botocore.exceptions import ClientError
from app.integrations.bedrock.client import BedrockClient, BedrockInvocationError

def test_bedrock_invocation_error_wraps_aws_error():
    """Test that AWS ClientError is wrapped with context."""
    client = BedrockClient()
    
    aws_error = ClientError(
        {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}},
        "invoke_model"
    )
    
    with patch.object(client.client, 'invoke_model', side_effect=aws_error):
        with pytest.raises(BedrockInvocationError) as exc_info:
            client.run_chat_turn([], "test message")
        
        assert "ThrottlingException" in str(exc_info.value)
        assert exc_info.value.model_id == client.model_id

def test_empty_conversation_history():
    """Test handling of empty conversation history."""
    client = BedrockClient()
    
    with patch.object(client.client, 'invoke_model') as mock_invoke:
        mock_invoke.return_value = {
            "body": MagicMock(read=lambda: b'{"output":{"message":{"content":[{"text":"response"}]}},"stopReason":"end_turn"}')
        }
        
        result = client.run_chat_turn([], "first message")
        
        call_args = mock_invoke.call_args
        body = json.loads(call_args.kwargs['body'])
        
        assert len(body['messages']) == 1
        assert body['messages'][0]['role'] == 'user'
```


### Integration Testing (Mocked)

**Scope:** Verify components interact correctly without calling real AWS

**Test Cases:**

1. **Chat Endpoint Flow**
   - Mock BedrockClient to return canned response
   - Verify user message persisted to database
   - Verify assistant message persisted with correct content
   - Verify response returned with correct structure

2. **Test Endpoint Flow**
   - Mock BedrockClient invocation
   - Verify timing measured correctly
   - Verify success response structure
   - Verify error response structure on failure

3. **LLMObs Tracing (Mocked)**
   - Mock LLMObs.annotate
   - Verify annotate called with correct input_data
   - Verify annotate called with correct output_data
   - Verify tags set correctly

**Example Integration Test:**

```python
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from app.main import app

client = TestClient(app)

@patch('app.integrations.bedrock.client.BedrockClient.run_chat_turn')
@patch('app.repositories.chat_repository.ChatRepository.create_message')
@patch('app.repositories.chat_repository.ChatRepository.get_session_messages')
def test_chat_endpoint_full_flow(mock_get_messages, mock_create, mock_bedrock):
    """Integration test for chat message creation with Bedrock call."""
    
    # Setup mocks
    mock_bedrock.return_value = "This is a test response from Bedrock"
    mock_get_messages.return_value = []
    mock_create.return_value = MagicMock(
        id="123",
        role="assistant",
        content="This is a test response from Bedrock"
    )
    
    # Make request
    response = client.post(
        "/api/chat/sessions/test-session-id/messages",
        json={"content": "Hello", "model_id": "amazon.nova-pro-v1:0"}
    )
    
    # Verify
    assert response.status_code == 201
    assert mock_bedrock.called
    assert mock_create.call_count == 2  # user message + assistant message
    assert "This is a test response" in response.json()["content"]
```

### Smoke Testing

**Scope:** One-time checks for setup and configuration

**Test Cases:**

1. **Dependencies Present**
   - Parse requirements.txt
   - Verify boto3, ddtrace, botocore listed

2. **Environment Template Complete**
   - Parse .env.example
   - Verify all required variables documented
   - Verify defaults provided where appropriate

3. **Module Structure**
   - Verify utility modules importable
   - Verify expected functions exist
   - Verify classes have expected methods

4. **Configuration Defaults**
   - Verify Settings has correct default values
   - Verify BEDROCK_MODEL_ID defaults to Nova Pro

**Example Smoke Test:**

```python
def test_required_dependencies_present():
    """Verify required packages in requirements.txt."""
    with open('requirements.txt', 'r') as f:
        content = f.read()
    
    assert 'boto3' in content
    assert 'ddtrace' in content
    assert 'botocore' in content

def test_env_example_complete():
    """Verify .env.example documents all required variables."""
    with open('.env.example', 'r') as f:
        content = f.read()
    
    required_vars = [
        'AWS_ACCESS_KEY_ID',
        'AWS_SECRET_ACCESS_KEY',
        'AWS_REGION',
        'DD_API_KEY',
        'DD_APP_KEY',
        'DD_LLMOBS_ML_APP'
    ]
    
    for var in required_vars:
        assert var in content, f"Missing {var} in .env.example"
```


### Manual Testing

**Scope:** End-to-end verification with real AWS and Datadog services

**Prerequisites:**
- Valid AWS credentials configured in .env
- Valid Datadog API keys configured in .env
- Access to Datadog LLM Observability dashboard
- AWS Bedrock model access enabled in account

**Test Scenarios:**

1. **Bedrock Health Check**
   ```bash
   curl -X POST http://localhost:8000/api/test/bedrock-health \
     -H "Content-Type: application/json" \
     -d '{"prompt": "What is 2+2?", "model_id": "amazon.nova-pro-v1:0"}'
   ```
   Expected: 200 response with model answer and timing

2. **Bedrock Diagnostics**
   ```bash
   curl http://localhost:8000/api/test/bedrock-diagnostics
   ```
   Expected: Configuration status showing all systems configured

3. **Chat Flow**
   - Create chat session via UI
   - Send message: "Explain what AIOps means"
   - Verify response appears in UI
   - Check database for both messages
   - Verify trace appears in Datadog (app.datadoghq.com/llm/traces)

4. **Model Selection**
   - Send chat with `model_id: "amazon.nova-lite-v1:0"`
   - Send chat with `model_id: "amazon.nova-pro-v1:0"`
   - Compare response quality and timing
   - Verify different models appear in Datadog traces

5. **Error Scenarios**
   - Send request with invalid model_id
   - Verify 500 error with descriptive message
   - Temporarily remove AWS credentials
   - Verify configuration error reported

6. **Datadog Trace Verification**
   - Navigate to app.datadoghq.com/llm/traces
   - Filter by ml_app: "aiops-backend"
   - Verify traces show:
     - Workflow span (if using traced_workflow)
     - LLM span with model_name: "nova-pro"
     - Input/output annotations
     - Token counts (if available)

### Test Coverage Goals

- **Unit Tests**: >80% coverage of BedrockClient, parser, utilities
- **Integration Tests**: All API endpoints covered
- **Property Tests**: 100+ iterations for response parsing
- **Smoke Tests**: All configuration and dependencies verified
- **Manual Tests**: End-to-end flow verified before production deployment

### Continuous Integration

**CI Pipeline Steps:**

1. Install dependencies from requirements.txt
2. Run smoke tests (fast, no external calls)
3. Run unit tests with mocks
4. Run integration tests with mocks
5. Run property tests (hypothesis)
6. Generate coverage report
7. Lint with ruff/black
8. Type check with mypy

**No AWS/Datadog calls in CI** - All external services mocked to keep CI fast and avoid costs.

