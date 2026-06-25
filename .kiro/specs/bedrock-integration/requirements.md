# Requirements Document

## Introduction

This document specifies the requirements for integrating AWS Bedrock connectivity into the AIOps backend system. The integration replaces the existing mocked BedrockClient implementation with a real AWS Bedrock runtime client, adds Datadog LLM observability using span decorators, incorporates DDStarter hackathon pack patterns, and creates test endpoints to verify connectivity.

## Glossary

- **Bedrock_Client**: The AWS Bedrock runtime client component responsible for invoking AWS Bedrock foundation models
- **AIOps_Backend**: The FastAPI-based backend application that orchestrates incident investigation and chat functionality
- **DDStarter_Pack**: The hackathon starter pack containing AWS Bedrock integration patterns (basic-bedrock-call.py, bedrock-decorator-example.py, bedrock-mcp-agent.py)
- **LLM_Observability**: Datadog's observability feature that traces LLM calls, tool executions, and workflows
- **Configuration_System**: The Pydantic settings-based configuration management system in app/core/config.py
- **Environment_File**: The .env file containing AWS credentials, Datadog API keys, and service configuration
- **Test_Endpoint**: A FastAPI endpoint created specifically to verify AWS Bedrock connectivity
- **Dependency_Manager**: The requirements.txt file managing Python package dependencies
- **Span_Decorator**: Datadog ddtrace decorators (@workflow, @llm, @tool, @task) that mark functions as specific trace span types
- **MCP_Client**: Model Context Protocol client that communicates with the Datadog MCP server for tool execution

## Requirements

### Requirement 1: Replace Mocked Bedrock Implementation with Real AWS Client

**User Story:** As a backend developer, I want the BedrockClient to use real AWS Bedrock API calls, so that the system can generate actual LLM responses instead of mocked data.

#### Acceptance Criteria

1. THE Bedrock_Client SHALL initialize a boto3 bedrock-runtime client using the AWS_REGION from Configuration_System
2. WHEN generate_incident_rca is called with service metrics, service logs, and a query, THE Bedrock_Client SHALL invoke the AWS Bedrock model specified in Configuration_System with a structured prompt
3. WHEN run_chat_turn is called with conversation history and a new message, THE Bedrock_Client SHALL invoke the AWS Bedrock model and return the model's text response
4. THE Bedrock_Client SHALL extract and return text content from AWS Bedrock response JSON following the Nova model response structure
5. IF AWS Bedrock invocation fails with an error, THEN THE Bedrock_Client SHALL raise an exception with descriptive error information

### Requirement 2: Configure AWS Credentials and Service Settings

**User Story:** As a DevOps engineer, I want AWS credentials and Bedrock configuration stored in environment variables, so that the system can authenticate with AWS services without hardcoding credentials.

#### Acceptance Criteria

1. THE Environment_File SHALL contain AWS_ACCESS_KEY_ID for AWS authentication
2. THE Environment_File SHALL contain AWS_SECRET_ACCESS_KEY for AWS authentication
3. THE Environment_File SHALL contain AWS_REGION to specify the AWS Bedrock service region
4. THE Configuration_System SHALL load AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, and AWS_REGION from Environment_File
5. THE Configuration_System SHALL provide a BEDROCK_MODEL_ID setting with default value "amazon.nova-pro-v1:0"
6. THE Environment_File SHALL contain DD_API_KEY for Datadog API authentication
7. THE Environment_File SHALL contain DD_APP_KEY for Datadog application-level operations
8. THE Environment_File SHALL contain DD_LLMOBS_ML_APP to identify the application in Datadog LLM Observability
9. THE Configuration_System SHALL load DD_API_KEY, DD_APP_KEY, and DD_LLMOBS_ML_APP from Environment_File

### Requirement 3: Integrate Datadog LLM Observability

**User Story:** As a platform engineer, I want all LLM calls traced in Datadog LLM Observability, so that I can monitor performance, costs, and errors in production.

#### Acceptance Criteria

1. WHEN AIOps_Backend starts, THE AIOps_Backend SHALL enable LLMObs with agentless mode using DD_API_KEY from Configuration_System
2. WHEN AIOps_Backend starts, THE AIOps_Backend SHALL configure LLMObs with ml_app name from DD_LLMOBS_ML_APP in Configuration_System
3. THE Bedrock_Client SHALL apply the @llm span decorator to methods that invoke AWS Bedrock models
4. WHEN an LLM call is made, THE Bedrock_Client SHALL annotate the span with input_data containing the prompt or messages
5. WHEN an LLM call completes, THE Bedrock_Client SHALL annotate the span with output_data containing the model response
6. THE Bedrock_Client SHALL set model_name and model_provider attributes on @llm decorated methods
7. WHEN AIOps_Backend shuts down gracefully, THE AIOps_Backend SHALL call LLMObs.flush to ensure all traces are sent to Datadog

### Requirement 4: Add Required Python Dependencies

**User Story:** As a backend developer, I want all required packages documented in requirements.txt, so that the application can be installed with all necessary dependencies.

#### Acceptance Criteria

1. THE Dependency_Manager SHALL include boto3 with version constraint for AWS SDK functionality
2. THE Dependency_Manager SHALL include ddtrace with version constraint for Datadog tracing and LLM observability
3. THE Dependency_Manager SHALL include botocore with version constraint for AWS core functionality
4. WHEN dependencies are installed from Dependency_Manager, THEN all AWS Bedrock and Datadog LLM observability functionality SHALL be available

### Requirement 5: Create DDStarter Utility Modules

**User Story:** As a backend developer, I want reusable utility modules based on DDStarter patterns, so that I can easily implement traced LLM workflows throughout the application.

#### Acceptance Criteria

1. THE AIOps_Backend SHALL provide a basic_bedrock_call utility module implementing simple LLM invocation with tracing
2. THE AIOps_Backend SHALL provide a traced_pipeline utility module implementing @workflow, @llm, @tool, and @task decorators
3. THE AIOps_Backend SHALL provide an mcp_client utility module implementing DatadogMCPClient for tool execution
4. WHEN traced_pipeline is used, THE traced_pipeline SHALL create nested spans visible in Datadog with workflow as root span
5. THE mcp_client SHALL implement initialize, list_tools, and call_tool methods following the DDStarter bedrock-mcp-agent.py pattern
6. THE mcp_client SHALL manage MCP session state using Mcp-Session-Id headers

### Requirement 6: Create Test Endpoint for Bedrock Connectivity Verification

**User Story:** As a QA engineer, I want a test API endpoint that verifies AWS Bedrock connectivity, so that I can confirm the integration is working before deploying to production.

#### Acceptance Criteria

1. THE AIOps_Backend SHALL expose a POST endpoint at /api/test/bedrock-health
2. WHEN the /api/test/bedrock-health endpoint receives a request with a test prompt, THE AIOps_Backend SHALL invoke AWS Bedrock with that prompt
3. WHEN the AWS Bedrock call succeeds, THE Test_Endpoint SHALL return HTTP 200 with the model response and metadata including model_id and response_time
4. IF the AWS Bedrock call fails, THEN THE Test_Endpoint SHALL return HTTP 500 with error details including error message and error type
5. THE Test_Endpoint SHALL accept an optional model_id parameter to test different AWS Bedrock models
6. THE Test_Endpoint SHALL measure and return the elapsed time for the AWS Bedrock invocation

### Requirement 7: Update Environment Configuration Files

**User Story:** As a deployment engineer, I want .env.example updated with all required environment variables, so that I can properly configure new environments.

#### Acceptance Criteria

1. THE Environment_File template (.env.example) SHALL document AWS_ACCESS_KEY_ID with placeholder value
2. THE Environment_File template SHALL document AWS_SECRET_ACCESS_KEY with placeholder value
3. THE Environment_File template SHALL document AWS_REGION with default value "us-east-1"
4. THE Environment_File template SHALL document BEDROCK_MODEL_ID with default value "amazon.nova-pro-v1:0"
5. THE Environment_File template SHALL document DD_API_KEY with placeholder value
6. THE Environment_File template SHALL document DD_APP_KEY with placeholder value
7. THE Environment_File template SHALL document DD_LLMOBS_ML_APP with example value
8. THE Environment_File template SHALL document DD_SITE with default value "datadoghq.com"
9. THE Environment_File (.env) SHALL contain actual AWS credentials provided by the user
10. THE Environment_File (.env) SHALL contain actual Datadog API keys provided by the user

### Requirement 8: Implement Bedrock Response Parsing

**User Story:** As a backend developer, I want robust response parsing from AWS Bedrock, so that the system correctly extracts text content from various response formats.

#### Acceptance Criteria

1. THE Bedrock_Client SHALL parse AWS Bedrock responses following the Amazon Nova response schema (output.message.content[0].text)
2. WHEN a Bedrock response contains multiple content blocks, THE Bedrock_Client SHALL extract text from all blocks with type "text"
3. WHEN a Bedrock response contains tool_use blocks, THE Bedrock_Client SHALL preserve tool use information separately from text content
4. IF a Bedrock response cannot be parsed, THEN THE Bedrock_Client SHALL raise a descriptive parsing exception
5. THE Bedrock_Client SHALL handle streaming responses if the invoke_model_with_response_stream API is used

### Requirement 9: Integrate DDStarter Patterns into Existing Methods

**User Story:** As a backend developer, I want existing BedrockClient methods to follow DDStarter patterns, so that all LLM operations benefit from proper tracing and observability.

#### Acceptance Criteria

1. THE Bedrock_Client generate_incident_rca method SHALL apply @llm decorator with model_name and model_provider attributes
2. THE Bedrock_Client run_chat_turn method SHALL apply @llm decorator with model_name and model_provider attributes
3. WHEN generate_incident_rca constructs a prompt, THE Bedrock_Client SHALL format service metrics and logs into a structured analysis request
4. WHEN run_chat_turn processes conversation history, THE Bedrock_Client SHALL convert history into AWS Bedrock message format with roles and content
5. THE Bedrock_Client SHALL annotate spans with metadata tags including token counts if available in response

### Requirement 10: Create Health Check and Diagnostics

**User Story:** As a site reliability engineer, I want diagnostic endpoints that verify AWS and Datadog connectivity, so that I can quickly troubleshoot integration issues.

#### Acceptance Criteria

1. THE AIOps_Backend SHALL expose a GET endpoint at /api/test/bedrock-diagnostics
2. WHEN the /api/test/bedrock-diagnostics endpoint is called, THE AIOps_Backend SHALL verify AWS credentials are configured
3. WHEN the /api/test/bedrock-diagnostics endpoint is called, THE AIOps_Backend SHALL verify Datadog API keys are configured
4. THE diagnostics endpoint SHALL return configuration status including region, model_id, and ml_app name
5. THE diagnostics endpoint SHALL indicate whether LLMObs is enabled and operational
6. THE diagnostics endpoint SHALL return HTTP 200 with status "healthy" if all checks pass, or HTTP 503 with specific missing configurations if checks fail
