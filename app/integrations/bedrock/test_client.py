"""
Unit tests for BedrockClient
"""
import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from botocore.exceptions import ClientError, NoCredentialsError

from app.integrations.bedrock.client import BedrockClient, BedrockInvocationError


class TestBedrockClientInitialization:
    """Tests for BedrockClient initialization"""
    
    @patch('app.integrations.bedrock.client.boto3.client')
    def test_successful_initialization(self, mock_boto_client):
        """Test successful client initialization"""
        mock_boto_client.return_value = Mock()
        
        client = BedrockClient()
        
        assert client.region == "us-east-1"  # From default settings
        assert client.model_id == "amazon.nova-pro-v1:0"
        from app.core.config import settings
        mock_boto_client.assert_called_once_with(
            service_name='bedrock-runtime',
            region_name='us-east-1',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID or None,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY or None
        )
    
    @patch('app.integrations.bedrock.client.boto3.client')
    def test_custom_region_and_model(self, mock_boto_client):
        """Test initialization with custom region and model"""
        mock_boto_client.return_value = Mock()
        
        client = BedrockClient(region="us-west-2", model_id="anthropic.claude-v2")
        
        assert client.region == "us-west-2"
        assert client.model_id == "anthropic.claude-v2"
    
    @patch('app.integrations.bedrock.client.boto3.client')
    def test_no_credentials_error(self, mock_boto_client):
        """Test initialization fails gracefully without credentials"""
        mock_boto_client.side_effect = NoCredentialsError()
        
        with pytest.raises(BedrockInvocationError, match="AWS credentials not found"):
            BedrockClient()


class TestPromptConstruction:
    """Tests for prompt building methods"""
    
    @patch('app.integrations.bedrock.client.boto3.client')
    def test_rca_prompt_includes_all_components(self, mock_boto_client):
        """Test RCA prompt includes metrics, logs, and query"""
        mock_boto_client.return_value = Mock()
        client = BedrockClient()
        
        metrics = {"cpu_usage": 95, "memory_usage": 80}
        logs = [
            {"timestamp": "2024-01-01T10:00:00", "message": "Error: Connection timeout"},
            {"timestamp": "2024-01-01T10:01:00", "message": "Error: Database unreachable"}
        ]
        query = "Why is the service failing?"
        
        prompt = client._build_rca_prompt(metrics, logs, query)
        
        assert "Why is the service failing?" in prompt
        assert "cpu_usage" in prompt
        assert "95" in prompt
        assert "Connection timeout" in prompt
        assert "Database unreachable" in prompt
    
    @patch('app.integrations.bedrock.client.boto3.client')
    def test_message_format_conversion(self, mock_boto_client):
        """Test history conversion to Nova message format"""
        mock_boto_client.return_value = Mock()
        client = BedrockClient()
        
        history = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"}
        ]
        
        messages = client._convert_history_to_messages(history)
        
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[0]["content"][0]["text"] == "Hello"
        assert messages[1]["role"] == "assistant"
        assert messages[1]["content"][0]["text"] == "Hi there!"


class TestBedrockInvocation:
    """Tests for Bedrock API invocation"""
    
    @patch('app.integrations.bedrock.client.boto3.client')
    def test_successful_invoke_model(self, mock_boto_client):
        """Test successful model invocation"""
        mock_client = Mock()
        mock_boto_client.return_value = mock_client
        
        # Mock response
        mock_response = {
            'body': Mock()
        }
        mock_response['body'].read.return_value = json.dumps({
            "output": {
                "message": {
                    "content": [{"text": "This is the response"}]
                }
            },
            "stopReason": "end_turn",
            "usage": {
                "inputTokens": 10,
                "outputTokens": 20,
                "totalTokens": 30
            }
        }).encode('utf-8')
        mock_client.invoke_model.return_value = mock_response
        
        client = BedrockClient()
        messages = [{"role": "user", "content": [{"text": "Hello"}]}]
        
        response = client._invoke_model(messages)
        
        assert response["output"]["message"]["content"][0]["text"] == "This is the response"
        mock_client.invoke_model.assert_called_once()
    
    @patch('app.integrations.bedrock.client.boto3.client')
    def test_invoke_model_client_error(self, mock_boto_client):
        """Test handling of AWS ClientError"""
        mock_client = Mock()
        mock_boto_client.return_value = mock_client
        
        error_response = {
            'Error': {
                'Code': 'ValidationException',
                'Message': 'Invalid model ID'
            }
        }
        mock_client.invoke_model.side_effect = ClientError(error_response, 'invoke_model')
        
        client = BedrockClient()
        messages = [{"role": "user", "content": [{"text": "Hello"}]}]
        
        with pytest.raises(BedrockInvocationError) as exc_info:
            client._invoke_model(messages)
        
        assert "Invalid model ID" in str(exc_info.value)
        assert exc_info.value.error_type == "ValidationException"


class TestGenerateIncidentRCA:
    """Tests for generate_incident_rca method"""
    
    @patch('app.integrations.bedrock.client.boto3.client')
    @patch('app.integrations.bedrock.client.LLMObs')
    def test_successful_rca_generation(self, mock_llmobs, mock_boto_client):
        """Test successful RCA generation"""
        mock_client = Mock()
        mock_boto_client.return_value = mock_client
        
        # Mock Bedrock response
        mock_response = {
            'body': Mock()
        }
        mock_response['body'].read.return_value = json.dumps({
            "output": {
                "message": {
                    "content": [{"text": "Root cause: Database connection pool exhausted"}]
                }
            },
            "stopReason": "end_turn",
            "usage": {
                "inputTokens": 100,
                "outputTokens": 50,
                "totalTokens": 150
            }
        }).encode('utf-8')
        mock_client.invoke_model.return_value = mock_response
        
        client = BedrockClient()
        metrics = {"cpu_usage": 90}
        logs = [{"timestamp": "2024-01-01T10:00:00", "message": "Error"}]
        query = "What's wrong?"
        
        result = client.generate_incident_rca(metrics, logs, query)
        
        assert result["status"] == "success"
        assert "Database connection pool exhausted" in result["data"]["summary"]
        
        # Verify LLMObs annotations were called
        assert mock_llmobs.annotate.called


class TestRunChatTurn:
    """Tests for run_chat_turn method"""
    
    @patch('app.integrations.bedrock.client.boto3.client')
    @patch('app.integrations.bedrock.client.LLMObs')
    def test_successful_chat_turn(self, mock_llmobs, mock_boto_client):
        """Test successful chat turn"""
        mock_client = Mock()
        mock_boto_client.return_value = mock_client
        
        # Mock Bedrock response
        mock_response = {
            'body': Mock()
        }
        mock_response['body'].read.return_value = json.dumps({
            "output": {
                "message": {
                    "content": [{"text": "I'm here to help!"}]
                }
            },
            "stopReason": "end_turn"
        }).encode('utf-8')
        mock_client.invoke_model.return_value = mock_response
        
        client = BedrockClient()
        history = [{"role": "user", "content": "Hello"}]
        message = "Can you help me?"
        
        response = client.run_chat_turn(history, message)
        
        assert response == "I'm here to help!"
        
        # Verify model was invoked
        assert mock_client.invoke_model.called
    
    @patch('app.integrations.bedrock.client.boto3.client')
    @patch('app.integrations.bedrock.client.LLMObs')
    def test_chat_turn_with_custom_model(self, mock_llmobs, mock_boto_client):
        """Test chat turn with custom model ID"""
        mock_client = Mock()
        mock_boto_client.return_value = mock_client
        
        # Mock response
        mock_response = {
            'body': Mock()
        }
        mock_response['body'].read.return_value = json.dumps({
            "output": {
                "message": {
                    "content": [{"text": "Response"}]
                }
            },
            "stopReason": "end_turn"
        }).encode('utf-8')
        mock_client.invoke_model.return_value = mock_response
        
        client = BedrockClient()
        history = []
        message = "Hello"
        custom_model = "anthropic.claude-3-sonnet-20240229-v1:0"
        
        response = client.run_chat_turn(history, message, model_id=custom_model)
        
        # Verify custom model was used
        call_args = mock_client.invoke_model.call_args
        assert call_args[1]['modelId'] == custom_model
