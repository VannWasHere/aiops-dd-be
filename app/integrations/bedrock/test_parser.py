"""
Unit tests for Bedrock response parser
"""
import pytest
from app.integrations.bedrock.parser import (
    extract_text_from_content,
    parse_bedrock_response,
    BedrockParsingError
)


class TestExtractTextFromContent:
    """Tests for extract_text_from_content function"""
    
    def test_single_text_block(self):
        """Test extraction of single text block"""
        content = [{"text": "Hello, world!"}]
        result = extract_text_from_content(content)
        assert result == "Hello, world!"
    
    def test_multiple_text_blocks(self):
        """Test concatenation of multiple text blocks"""
        content = [
            {"text": "Hello"},
            {"text": " world"},
            {"text": "!"}
        ]
        result = extract_text_from_content(content)
        assert result == "Hello world!"
    
    def test_mixed_text_and_tool_use(self):
        """Test extraction ignores toolUse blocks"""
        content = [
            {"text": "Here's the result: "},
            {"toolUse": {"toolUseId": "123", "name": "calculator", "input": {}}},
            {"text": "Done!"}
        ]
        result = extract_text_from_content(content)
        assert result == "Here's the result: Done!"
    
    def test_empty_content_list(self):
        """Test empty content list returns empty string"""
        content = []
        result = extract_text_from_content(content)
        assert result == ""
    
    def test_no_text_blocks(self):
        """Test content with only non-text blocks"""
        content = [
            {"toolUse": {"toolUseId": "123", "name": "tool1"}},
            {"toolUse": {"toolUseId": "456", "name": "tool2"}}
        ]
        result = extract_text_from_content(content)
        assert result == ""
    
    def test_invalid_content_type(self):
        """Test error on non-list content"""
        with pytest.raises(BedrockParsingError, match="Content must be a list"):
            extract_text_from_content("not a list")
    
    def test_invalid_block_type(self):
        """Test error on non-dict content block"""
        content = [{"text": "valid"}, "invalid block"]
        with pytest.raises(BedrockParsingError, match="Content block must be a dict"):
            extract_text_from_content(content)


class TestParseBedrockResponse:
    """Tests for parse_bedrock_response function"""
    
    def test_simple_text_response(self):
        """Test parsing simple text response"""
        response = {
            "output": {
                "message": {
                    "content": [{"text": "This is a response."}]
                }
            },
            "stopReason": "end_turn"
        }
        result = parse_bedrock_response(response)
        assert result["text"] == "This is a response."
        assert result["stop_reason"] == "end_turn"
        assert "usage" not in result
        assert "tool_use" not in result
    
    def test_response_with_usage(self):
        """Test parsing response with token usage data"""
        response = {
            "output": {
                "message": {
                    "content": [{"text": "Response text"}]
                }
            },
            "stopReason": "end_turn",
            "usage": {
                "inputTokens": 10,
                "outputTokens": 20,
                "totalTokens": 30
            }
        }
        result = parse_bedrock_response(response)
        assert result["text"] == "Response text"
        assert result["usage"]["inputTokens"] == 10
        assert result["usage"]["outputTokens"] == 20
        assert result["usage"]["totalTokens"] == 30
    
    def test_response_with_tool_use(self):
        """Test parsing response with tool use blocks"""
        response = {
            "output": {
                "message": {
                    "content": [
                        {"text": "Let me check that for you."},
                        {
                            "toolUse": {
                                "toolUseId": "abc123",
                                "name": "get_weather",
                                "input": {"location": "Seattle"}
                            }
                        }
                    ]
                }
            },
            "stopReason": "tool_use"
        }
        result = parse_bedrock_response(response)
        assert result["text"] == "Let me check that for you."
        assert result["stop_reason"] == "tool_use"
        assert "tool_use" in result
        assert len(result["tool_use"]) == 1
        assert result["tool_use"][0]["name"] == "get_weather"
    
    def test_multiple_tool_uses(self):
        """Test parsing response with multiple tool use blocks"""
        response = {
            "output": {
                "message": {
                    "content": [
                        {"text": "Executing tools..."},
                        {"toolUse": {"toolUseId": "1", "name": "tool1", "input": {}}},
                        {"toolUse": {"toolUseId": "2", "name": "tool2", "input": {}}}
                    ]
                }
            },
            "stopReason": "tool_use"
        }
        result = parse_bedrock_response(response)
        assert len(result["tool_use"]) == 2
    
    def test_missing_output_field(self):
        """Test error on missing output field"""
        response = {"stopReason": "end_turn"}
        with pytest.raises(BedrockParsingError, match="Response missing 'output' field"):
            parse_bedrock_response(response)
    
    def test_missing_message_field(self):
        """Test error on missing message field"""
        response = {
            "output": {},
            "stopReason": "end_turn"
        }
        with pytest.raises(BedrockParsingError, match="Output missing 'message' field"):
            parse_bedrock_response(response)
    
    def test_missing_content_field(self):
        """Test error on missing content field"""
        response = {
            "output": {
                "message": {}
            },
            "stopReason": "end_turn"
        }
        with pytest.raises(BedrockParsingError, match="Message missing 'content' field"):
            parse_bedrock_response(response)
    
    def test_invalid_response_type(self):
        """Test error on non-dict response"""
        with pytest.raises(BedrockParsingError, match="Response body must be a dict"):
            parse_bedrock_response("not a dict")
    
    def test_missing_stop_reason(self):
        """Test default stop reason when not provided"""
        response = {
            "output": {
                "message": {
                    "content": [{"text": "text"}]
                }
            }
        }
        result = parse_bedrock_response(response)
        assert result["stop_reason"] == "unknown"
