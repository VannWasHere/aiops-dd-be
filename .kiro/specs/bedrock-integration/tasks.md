# Implementation Plan: AWS Bedrock Integration with Datadog LLM Observability

## Overview

This implementation plan converts the design into a series of actionable coding tasks. The implementation replaces the mocked BedrockClient with a real AWS Bedrock runtime client using boto3, adds Datadog LLM Observability tracing with span decorators, creates DDStarter utility modules, implements test endpoints, and updates the chat endpoint to support model selection.

## Tasks

- [ ] 1. Update dependencies and configuration system
  - [ ] 1.1 Add boto3, ddtrace, and botocore to requirements.txt
    - Add `boto3>=1.34.0` for AWS SDK
    - Add `ddtrace>=2.8.0` for Datadog tracing and LLM observability
    - Add `botocore>=1.34.0` for AWS core functionality
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [ ] 1.2 Update Settings class in app/core/config.py
    - Add AWS_ACCESS_KEY_ID field (default empty string)
    - Add AWS_SECRET_ACCESS_KEY field (default empty string)
    - Update AWS_REGION field (keep default "us-east-1")
    - Update BEDROCK_MODEL_ID field (change default to "amazon.nova-pro-v1:0")
    - Add DD_API_KEY field (default empty string)
    - Add DD_APP_KEY field (default empty string)
    - Add DD_LLMOBS_ML_APP field (default "aiops-backend")
    - Add DD_SITE field (default "datadoghq.com")
    - Remove DATADOG_API_KEY and DATADOG_APP_KEY fields (replace with DD_API_KEY and DD_APP_KEY)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9_

  - [ ] 1.3 Update .env.example file with new configuration variables
    - Update AWS_ACCESS_KEY_ID with placeholder value
    - Update AWS_SECRET_ACCESS_KEY with placeholder value
    - Keep AWS_REGION with default "us-east-1"
    - Update BEDROCK_MODEL_ID with default "amazon.nova-pro-v1:0"
    - Replace DATADOG_API_KEY with DD_API_KEY and placeholder value
    - Replace DATADOG_APP_KEY with DD_APP_KEY and placeholder value
    - Add DD_LLMOBS_ML_APP with example value "aiops-backend"
    - Add DD_SITE with default value "datadoghq.com"
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8_

  - [ ] 1.4 Update .env file with actual AWS and Datadog credentials
    - Prompt user to provide AWS_ACCESS_KEY_ID
    - Prompt user to provide AWS_SECRET_ACCESS_KEY
    - Prompt user to provide DD_API_KEY
    - Prompt user to provide DD_APP_KEY
    - Update configuration values in .env file
    - _Requirements: 7.9, 7.10_

- [ ] 2. Checkpoint - Verify configuration changes
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 3. Implement Bedrock response parser
  - [ ] 3.1 Create app/integrations/bedrock/parser.py module
    - Implement `extract_text_from_content()` function to extract text from Nova response content blocks
    - Implement `parse_bedrock_response()` function to parse full Bedrock response into structured format
    - Handle multiple content blocks by concatenating text
    - Preserve toolUse blocks separately from text content
    - Raise descriptive parsing exceptions for malformed responses
    - _Requirements: 8.1, 8.2, 8.3, 8.4_

  - [ ]* 3.2 Write unit tests for response parser
    - Test single text block extraction
    - Test multiple text block concatenation
    - Test mixed text and toolUse block handling
    - Test malformed response error handling
    - _Requirements: 8.1, 8.2, 8.3, 8.4_

- [ ] 4. Implement real BedrockClient with AWS Bedrock API
  - [ ] 4.1 Update app/integrations/bedrock/client.py with boto3 integration
    - Initialize boto3 bedrock-runtime client in `__init__()` using settings.AWS_REGION
    - Implement `_invoke_model()` method using `client.invoke_model()` with Nova message format
    - Apply @llm decorator to `generate_incident_rca()` with model_name="nova-pro" and model_provider="bedrock"
    - Apply @llm decorator to `run_chat_turn()` with model_name="nova-pro" and model_provider="bedrock"
    - Implement prompt construction in `generate_incident_rca()` with service metrics, logs, and query
    - Implement message format conversion in `run_chat_turn()` from history to Nova format
    - Use response parser to extract text from Bedrock responses
    - Wrap AWS ClientError exceptions in custom BedrockInvocationError
    - Annotate spans with input_data using LLMObs.annotate()
    - Annotate spans with output_data using LLMObs.annotate()
    - Annotate spans with token metadata tags if available in response
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 9.1, 9.2, 9.3, 9.4, 9.5_

  - [ ]* 4.2 Write unit tests for BedrockClient
    - Test boto3 client initialization
    - Test prompt construction in generate_incident_rca
    - Test message format conversion in run_chat_turn
    - Test error handling for missing credentials
    - Test error handling for API failures
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

- [ ] 5. Add Datadog LLM Observability to application lifecycle
  - [ ] 5.1 Update app/main.py with LLMObs initialization
    - Import LLMObs from ddtrace.llmobs
    - Add startup event handler to enable LLMObs with agentless mode
    - Configure LLMObs with ml_app from settings.DD_LLMOBS_ML_APP
    - Configure LLMObs with api_key from settings.DD_API_KEY
    - Configure LLMObs with site from settings.DD_SITE
    - Add shutdown event handler to call LLMObs.flush()
    - Add logging for LLMObs initialization and flush operations
    - _Requirements: 3.1, 3.2, 3.7_

  - [ ]* 5.2 Write integration tests for LLMObs lifecycle
    - Test LLMObs enables successfully on startup with valid credentials
    - Test LLMObs handles missing credentials gracefully
    - Test LLMObs flushes on shutdown
    - _Requirements: 3.1, 3.2, 3.7_

- [ ] 6. Create DDStarter utility modules
  - [ ] 6.1 Create app/utils/ddstarter/ directory and __init__.py
    - Create directory structure for utility modules
    - _Requirements: 5.1, 5.2, 5.3_

  - [ ] 6.2 Implement app/utils/ddstarter/basic_bedrock.py
    - Implement `invoke_bedrock_simple()` function with @llm decorator
    - Accept prompt and optional model_id parameters
    - Use boto3 bedrock-runtime client to invoke model
    - Return parsed response text
    - Follow DDStarter basic-bedrock-call.py pattern
    - _Requirements: 5.1_

  - [ ] 6.3 Implement app/utils/ddstarter/traced_workflow.py
    - Implement `execute_traced_pipeline()` function with @workflow decorator
    - Implement `fetch_context()` function with @tool decorator
    - Implement `analyze_with_llm()` function with @llm decorator
    - Implement `process_llm_result()` function with @task decorator
    - Create nested span structure for multi-step workflows
    - Follow DDStarter bedrock-decorator-example.py pattern
    - _Requirements: 5.2, 5.4_

  - [ ] 6.4 Implement app/utils/ddstarter/mcp_integration.py
    - Create DatadogMCPClient class with __init__, initialize, list_tools, and call_tool methods
    - Store api_key and app_key from initialization parameters
    - Implement MCP initialize handshake with protocol version
    - Implement list_tools to retrieve available Datadog MCP tools
    - Apply @tool decorator to call_tool method for tracing
    - Manage MCP session state using Mcp-Session-Id headers
    - Follow DDStarter bedrock-mcp-agent.py pattern
    - _Requirements: 5.3, 5.5, 5.6_

  - [ ]* 6.5 Write unit tests for DDStarter utility modules
    - Test basic_bedrock.py simple invocation
    - Test traced_workflow.py nested span creation
    - Test mcp_integration.py client initialization and tool calling
    - _Requirements: 5.1, 5.2, 5.3_

- [ ] 7. Checkpoint - Verify core integration works
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 8. Create test endpoints for connectivity verification
  - [ ] 8.1 Create app/api/endpoints/test.py module
    - Create router with prefix "/test"
    - Import BedrockClient and settings
    - Set up logging for test endpoints
    - _Requirements: 6.1, 10.1_

  - [ ] 8.2 Implement POST /api/test/bedrock-health endpoint
    - Accept optional prompt and model_id parameters in request body
    - Invoke BedrockClient with test prompt
    - Measure response time using time.time()
    - Return 200 with status="success", model_id, response text, and response_time_ms on success
    - Return 500 with status="error", model_id, error message, and error type on failure
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

  - [ ] 8.3 Implement GET /api/test/bedrock-diagnostics endpoint
    - Check if AWS_ACCESS_KEY_ID is configured (non-empty)
    - Check if DD_API_KEY is configured (non-empty)
    - Check if LLMObs is enabled (DD_API_KEY and DD_LLMOBS_ML_APP both configured)
    - Return configuration status with aws_configured, datadog_configured, llmobs_enabled flags
    - Include region, model_id, and ml_app in response
    - Return 200 with status="healthy" if all checks pass
    - Return 503 with status="degraded" if any check fails
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6_

  - [ ] 8.4 Register test router in app/api/router.py
    - Import test router
    - Include test router with prefix "/api/test"
    - _Requirements: 6.1, 10.1_

  - [ ]* 8.5 Write integration tests for test endpoints
    - Test bedrock-health returns 200 with valid credentials
    - Test bedrock-health returns 500 with invalid credentials
    - Test bedrock-diagnostics shows correct configuration status
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 10.1, 10.2, 10.3_

- [ ] 9. Update chat endpoint with model selection and real Bedrock integration
  - [ ] 9.1 Update app/api/endpoints/chat.py create_chat_message endpoint
    - Add optional model_id parameter to endpoint signature
    - Import BedrockClient
    - Persist user message to database using ChatRepository
    - Retrieve conversation history from database
    - Format history as list of {"role": "user"|"assistant", "content": "..."} dictionaries
    - Invoke BedrockClient.run_chat_turn() with history, new message, and optional model_id
    - Persist assistant response to database using ChatRepository
    - Catch BedrockInvocationError and return 500 with error details
    - Validate session exists before processing (return 404 if not found)
    - Rollback database transaction on failure
    - Return assistant message in response
    - _Requirements: 1.3, 1.4, 1.5_

  - [ ]* 9.2 Write integration tests for updated chat endpoint
    - Test chat endpoint creates messages with default model
    - Test chat endpoint accepts custom model_id parameter
    - Test chat endpoint returns 404 for non-existent session
    - Test chat endpoint returns 500 for Bedrock invocation failures
    - _Requirements: 1.3_

- [ ] 10. Final checkpoint and documentation
  - [ ] 10.1 Verify all components integrate correctly
    - Test Bedrock connectivity using /api/test/bedrock-health
    - Test diagnostics endpoint returns correct status
    - Test chat endpoint generates real responses
    - Check Datadog LLMObs dashboard for traces
    - Ensure all environment variables are documented
    - _Requirements: 6.1, 6.2, 6.3, 10.1, 10.2, 10.3_

  - [ ] 10.2 Update inline code documentation
    - Add docstrings to BedrockClient methods
    - Add docstrings to response parser functions
    - Add docstrings to DDStarter utility modules
    - Add docstrings to test endpoints
    - Document error handling patterns
    - _Requirements: 1.1, 1.2, 1.3, 8.1, 8.2_

- [ ] 11. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional test-related sub-tasks that can be skipped for faster MVP
- Each task references specific requirements from the requirements document for traceability
- The implementation uses Python with boto3 for AWS integration and ddtrace for Datadog observability
- Checkpoints ensure incremental validation at key milestones
- The design document uses Python (not pseudocode), so all implementation uses Python
- The user mentioned fixing a 500 error on the chat endpoint - task 9.1 addresses this by implementing real Bedrock integration
- Configuration changes include updating field names from DATADOG_* to DD_* to match Datadog conventions

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3"] },
    { "id": 1, "tasks": ["1.4", "3.1"] },
    { "id": 2, "tasks": ["3.2", "4.1", "6.1"] },
    { "id": 3, "tasks": ["4.2", "5.1", "6.2", "6.3", "6.4"] },
    { "id": 4, "tasks": ["5.2", "6.5", "8.1"] },
    { "id": 5, "tasks": ["8.2", "8.3", "8.4"] },
    { "id": 6, "tasks": ["8.5", "9.1"] },
    { "id": 7, "tasks": ["9.2", "10.1", "10.2"] }
  ]
}
```
