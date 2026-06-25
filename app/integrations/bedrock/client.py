"""
AWS Bedrock Client Implementation

This module provides the real AWS Bedrock client implementation using boto3,
with Datadog LLM Observability tracing through @llm decorators.
"""
import json
import logging
from typing import Dict, Any, List, Optional
import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from ddtrace.llmobs.decorators import llm
from ddtrace.llmobs import LLMObs

from app.integrations.bedrock.base import BaseBedrockClient
from app.integrations.bedrock.parser import parse_bedrock_response, BedrockParsingError
from app.core.config import settings


logger = logging.getLogger(__name__)


class BedrockInvocationError(Exception):
    """Raised when AWS Bedrock invocation fails."""
    def __init__(self, message: str, error_type: str = "unknown", original_error: Exception = None):
        super().__init__(message)
        self.error_type = error_type
        self.original_error = original_error


class BedrockClient(BaseBedrockClient):
    """
    AWS Bedrock client using boto3 bedrock-runtime for real LLM invocations.
    
    Supports Amazon Nova models with structured message format and Datadog
    LLM Observability tracing.
    """

    def __init__(self, region: str = None, model_id: str = None):
        """
        Initialize boto3 bedrock-runtime client.
        
        Args:
            region: AWS region (defaults to settings.AWS_REGION)
            model_id: Bedrock model ID (defaults to settings.BEDROCK_MODEL_ID)
        """
        self.region = region or settings.AWS_REGION
        self.model_id = model_id or settings.BEDROCK_MODEL_ID
        
        try:
            # Initialize boto3 bedrock-runtime client using explicit credentials from settings
            self.client = boto3.client(
                service_name='bedrock-runtime',
                region_name=self.region,
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID or None,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY or None
            )
            logger.info(f"Initialized Bedrock client for region {self.region} with model {self.model_id}")
        except NoCredentialsError as e:
            logger.error("AWS credentials not configured")
            raise BedrockInvocationError(
                "AWS credentials not found. Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY.",
                error_type="NoCredentials",
                original_error=e
            )
        except Exception as e:
            logger.error(f"Failed to initialize Bedrock client: {e}")
            raise BedrockInvocationError(
                f"Failed to initialize Bedrock client: {str(e)}",
                error_type="InitializationError",
                original_error=e
            )

    @llm(model_name="nova-pro", model_provider="bedrock")
    def generate_incident_rca(
        self, 
        service_metrics: Dict[str, Any], 
        service_logs: List[Dict[str, Any]], 
        query: str
    ) -> Dict[str, Any]:
        """
        Generate root cause analysis for an incident using AWS Bedrock.
        
        Constructs a structured prompt with service metrics, logs, and query,
        then invokes Bedrock to generate analysis.
        
        Args:
            service_metrics: Performance metrics (CPU, memory, latency)
            service_logs: Recent error logs with timestamp and message
            query: User's investigation query
            
        Returns:
            Dict with summary, root_cause, and recommendations
            
        Raises:
            BedrockInvocationError: If AWS call fails
        """
        # Construct structured prompt for RCA
        prompt = self._build_rca_prompt(service_metrics, service_logs, query)
        
        # Build messages in Nova format
        messages = [
            {
                "role": "user",
                "content": [{"text": prompt}]
            }
        ]
        
        # Annotate span with input data
        LLMObs.annotate(
            input_data=[{"role": "user", "content": prompt}]
        )
        
        try:
            # Invoke Bedrock
            response = self._invoke_model(messages, max_tokens=2048)
            parsed = parse_bedrock_response(response)
            
            # Extract RCA components from response
            response_text = parsed["text"]
            
            # Annotate span with output data
            LLMObs.annotate(
                output_data=[{"role": "assistant", "content": response_text}]
            )
            
            # Annotate with token usage if available
            if "usage" in parsed:
                usage = parsed["usage"]
                LLMObs.annotate(
                    tags={
                        "model.tokens.input": str(usage.get("inputTokens", 0)),
                        "model.tokens.output": str(usage.get("outputTokens", 0)),
                        "model.tokens.total": str(usage.get("totalTokens", 0))
                    }
                )
            
            # Parse structured response (expecting JSON or structured text)
            # For simplicity, return the full text response structured
            return {
                "status": "success",
                "data": {
                    "summary": response_text,
                    "root_cause": response_text,
                    "recommendations": []
                }
            }
            
        except BedrockInvocationError:
            raise
        except BedrockParsingError as e:
            logger.error(f"Failed to parse Bedrock response: {e}")
            raise BedrockInvocationError(
                f"Failed to parse Bedrock response: {str(e)}",
                error_type="ParsingError",
                original_error=e
            )
        except Exception as e:
            logger.error(f"Unexpected error in generate_incident_rca: {e}")
            raise BedrockInvocationError(
                f"Unexpected error: {str(e)}",
                error_type="UnexpectedError",
                original_error=e
            )

    @llm(model_name="nova-pro", model_provider="bedrock")
    def run_chat_turn(
        self, 
        history: List[Dict[str, str]], 
        message: str,
        model_id: Optional[str] = None
    ) -> str:
        """
        Execute one turn of conversational chat with AWS Bedrock.
        
        Converts conversation history to Nova message format and invokes
        the model to generate a response.
        
        Args:
            history: List of {role, content} message objects
            message: New user message
            model_id: Optional model ID override
            
        Returns:
            Assistant's text response
            
        Raises:
            BedrockInvocationError: If AWS call fails
        """
        # Convert history to Nova message format
        messages = self._convert_history_to_messages(history)
        
        # Add new user message
        messages.append({
            "role": "user",
            "content": [{"text": message}]
        })
        
        # Annotate span with input data
        input_data = [{"role": msg["role"], "content": msg["content"][0]["text"]} for msg in messages]
        LLMObs.annotate(input_data=input_data)
        
        try:
            # Invoke Bedrock with optional model override
            response = self._invoke_model(messages, max_tokens=1024, model_id=model_id)
            parsed = parse_bedrock_response(response)
            
            response_text = parsed["text"]
            
            # Annotate span with output data
            LLMObs.annotate(
                output_data=[{"role": "assistant", "content": response_text}]
            )
            
            # Annotate with token usage if available
            if "usage" in parsed:
                usage = parsed["usage"]
                LLMObs.annotate(
                    tags={
                        "model.tokens.input": str(usage.get("inputTokens", 0)),
                        "model.tokens.output": str(usage.get("outputTokens", 0)),
                        "model.tokens.total": str(usage.get("totalTokens", 0))
                    }
                )
            
            return response_text
            
        except BedrockInvocationError:
            raise
        except BedrockParsingError as e:
            logger.error(f"Failed to parse Bedrock response: {e}")
            raise BedrockInvocationError(
                f"Failed to parse Bedrock response: {str(e)}",
                error_type="ParsingError",
                original_error=e
            )
        except Exception as e:
            logger.error(f"Unexpected error in run_chat_turn: {e}")
            raise BedrockInvocationError(
                f"Unexpected error: {str(e)}",
                error_type="UnexpectedError",
                original_error=e
            )

    def _invoke_model(
        self, 
        messages: List[Dict], 
        max_tokens: int = 1024,
        model_id: Optional[str] = None
    ) -> Dict:
        """
        Low-level Bedrock invocation using boto3.
        
        Args:
            messages: Nova-format messages [{"role": "user", "content": [...]}]
            max_tokens: Maximum tokens to generate
            model_id: Optional model ID override
            
        Returns:
            Raw Bedrock response dict
            
        Raises:
            BedrockInvocationError: If AWS call fails
        """
        request_body = {
            "messages": messages,
            "inferenceConfig": {
                "max_new_tokens": max_tokens
            }
        }
        
        target_model = model_id or self.model_id
        
        try:
            logger.debug(f"Invoking Bedrock model {target_model}")
            response = self.client.invoke_model(
                modelId=target_model,
                body=json.dumps(request_body),
                contentType="application/json",
                accept="application/json"
            )
            
            # Parse response body
            response_body = json.loads(response['body'].read())
            logger.debug(f"Bedrock invocation successful")
            
            return response_body
            
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            error_message = e.response.get('Error', {}).get('Message', str(e))
            logger.error(f"AWS Bedrock ClientError [{error_code}]: {error_message}")
            raise BedrockInvocationError(
                f"AWS Bedrock invocation failed: {error_message}",
                error_type=error_code,
                original_error=e
            )
        except NoCredentialsError as e:
            logger.error("AWS credentials not found")
            raise BedrockInvocationError(
                "AWS credentials not found. Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY.",
                error_type="NoCredentials",
                original_error=e
            )
        except Exception as e:
            logger.error(f"Unexpected error invoking Bedrock: {e}")
            raise BedrockInvocationError(
                f"Unexpected error invoking Bedrock: {str(e)}",
                error_type="UnexpectedError",
                original_error=e
            )

    def _build_rca_prompt(
        self, 
        service_metrics: Dict[str, Any], 
        service_logs: List[Dict[str, Any]], 
        query: str
    ) -> str:
        """
        Construct structured prompt for root cause analysis.
        
        Args:
            service_metrics: Performance metrics
            service_logs: Error logs
            query: Investigation query
            
        Returns:
            Formatted prompt string
        """
        prompt_parts = [
            "You are an incident investigation assistant. Analyze the following information and provide a root cause analysis.",
            "",
            "## Investigation Query",
            query,
            "",
            "## Service Metrics"
        ]
        
        # Format metrics
        for key, value in service_metrics.items():
            prompt_parts.append(f"- {key}: {value}")
        
        prompt_parts.append("")
        prompt_parts.append("## Recent Logs")
        
        # Format logs
        for log in service_logs[:10]:  # Limit to recent 10 logs
            timestamp = log.get("timestamp", "unknown")
            message = log.get("message", "")
            prompt_parts.append(f"[{timestamp}] {message}")
        
        prompt_parts.append("")
        prompt_parts.append("Please provide a root cause analysis with summary and recommendations.")
        
        return "\n".join(prompt_parts)

    def _convert_history_to_messages(self, history: List[Dict[str, str]]) -> List[Dict]:
        """
        Convert conversation history to Nova message format.
        
        Args:
            history: List of {"role": "user"|"assistant", "content": "text"} dicts
            
        Returns:
            List of Nova-format messages
        """
        messages = []
        for msg in history:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            
            messages.append({
                "role": role,
                "content": [{"text": content}]
            })
        
        return messages
