import json
import logging
import boto3
from ddtrace.llmobs.decorators import llm
from ddtrace.llmobs import LLMObs
from app.core.config import settings

logger = logging.getLogger(__name__)

@llm(model_name="nova-pro", model_provider="bedrock")
def ask_bedrock(prompt: str, model_id: str = None) -> str:
    """
    Simple helper to ask AWS Bedrock, traced with Datadog LLMObs.
    """
    target_model = model_id or settings.BEDROCK_MODEL_ID or 'amazon.nova-pro-v1:0'
    region = settings.AWS_REGION or 'us-east-1'
    
    # Annotate span with input
    LLMObs.annotate(
        input_data=[{"role": "user", "content": prompt}]
    )
    
    try:
        client = boto3.client(
            'bedrock-runtime',
            region_name=region,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID or None,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY or None
        )
        response = client.invoke_model(
            modelId=target_model,
            body=json.dumps({
                'messages': [
                    {'role': 'user', 'content': [{'text': prompt}]}
                ],
                'inferenceConfig': {
                    'max_new_tokens': 1024
                }
            }),
            contentType='application/json'
        )
        result_body = json.loads(response['body'].read())
        # Parse Nova-style output
        text = result_body['output']['message']['content'][0]['text']
        
        # Annotate span with output
        LLMObs.annotate(
            output_data=[{"role": "assistant", "content": text}]
        )
        
        # Annotate with token usage if available
        if "usage" in result_body:
            usage = result_body["usage"]
            LLMObs.annotate(
                tags={
                    "model.tokens.input": str(usage.get("inputTokens", 0)),
                    "model.tokens.output": str(usage.get("outputTokens", 0)),
                    "model.tokens.total": str(usage.get("totalTokens", 0))
                }
            )
        return text
    except Exception as e:
        logger.error(f"Error in ask_bedrock: {e}")
        LLMObs.annotate(
            tags={"error": "true", "error.message": str(e)}
        )
        raise e
