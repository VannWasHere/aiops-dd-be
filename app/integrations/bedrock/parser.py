"""
AWS Bedrock Response Parser

This module provides utilities for parsing AWS Bedrock API responses,
specifically handling Amazon Nova model response structures.
"""
from typing import Dict, Any, List


class BedrockParsingError(Exception):
    """Raised when a Bedrock response cannot be parsed."""
    pass


def extract_text_from_content(content: List[Dict[str, Any]]) -> str:
    """
    Extract text from Bedrock response content blocks.
    
    Processes Nova-format content arrays and extracts text from all blocks
    with type "text", concatenating them in order. Non-text blocks (like
    toolUse) are ignored.
    
    Args:
        content: Response content array from output.message.content
        
    Returns:
        Concatenated text from all text blocks
        
    Example:
        content = [{"text": "Hello"}, {"text": " world"}]
        result = "Hello world"
        
    Raises:
        BedrockParsingError: If content structure is invalid
    """
    if not isinstance(content, list):
        raise BedrockParsingError(f"Content must be a list, got {type(content)}")
    
    text_parts = []
    for block in content:
        if not isinstance(block, dict):
            raise BedrockParsingError(f"Content block must be a dict, got {type(block)}")
        
        # Extract text blocks only
        if "text" in block:
            text_parts.append(block["text"])
    
    return "".join(text_parts)


def parse_bedrock_response(response_body: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parse full Bedrock response into structured format.
    
    Handles Amazon Nova response schema:
    {
      "output": {
        "message": {
          "content": [{"text": "..."}, {"toolUse": {...}}]
        }
      },
      "stopReason": "end_turn",
      "usage": {"inputTokens": 10, "outputTokens": 20, "totalTokens": 30}
    }
    
    Args:
        response_body: JSON response from invoke_model
        
    Returns:
        {
            "text": str,
            "stop_reason": str,
            "usage": dict (if available),
            "tool_use": list of tool use blocks (if any)
        }
        
    Raises:
        BedrockParsingError: If response cannot be parsed
    """
    if not isinstance(response_body, dict):
        raise BedrockParsingError(f"Response body must be a dict, got {type(response_body)}")
    
    # Extract output message
    if "output" not in response_body:
        raise BedrockParsingError("Response missing 'output' field")
    
    output = response_body["output"]
    if not isinstance(output, dict):
        raise BedrockParsingError(f"Output must be a dict, got {type(output)}")
    
    if "message" not in output:
        raise BedrockParsingError("Output missing 'message' field")
    
    message = output["message"]
    if not isinstance(message, dict):
        raise BedrockParsingError(f"Message must be a dict, got {type(message)}")
    
    if "content" not in message:
        raise BedrockParsingError("Message missing 'content' field")
    
    content = message["content"]
    
    # Extract text content
    text = extract_text_from_content(content)
    
    # Extract tool use blocks separately
    tool_use_blocks = []
    for block in content:
        if isinstance(block, dict) and "toolUse" in block:
            tool_use_blocks.append(block["toolUse"])
    
    # Build result
    result = {
        "text": text,
        "stop_reason": response_body.get("stopReason", "unknown"),
    }
    
    # Add usage data if available
    if "usage" in response_body:
        result["usage"] = response_body["usage"]
    
    # Add tool use data if present
    if tool_use_blocks:
        result["tool_use"] = tool_use_blocks
    
    return result
