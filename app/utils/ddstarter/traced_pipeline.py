import logging
from ddtrace.llmobs.decorators import llm, tool, workflow, task
from ddtrace.llmobs import LLMObs
from .basic_bedrock_call import ask_bedrock

logger = logging.getLogger(__name__)

@workflow
def run_traced_pipeline(prompt: str, model_id: str = None) -> str:
    """
    Traced pipeline that fetches context, calls the LLM, and formats the output.
    Uses @workflow, @tool, @llm, and @task decorators.
    """
    LLMObs.annotate(input_data=prompt)
    
    # 1. Fetch context (marked as @tool)
    context = fetch_pipeline_context(prompt)
    
    # 2. Call LLM (marked as @llm inside ask_bedrock or custom helper)
    response = call_pipeline_llm(prompt, context, model_id)
    
    # 3. Process and format results (marked as @task)
    formatted = format_pipeline_output(response)
    
    LLMObs.annotate(output_data=formatted)
    return formatted

@tool
def fetch_pipeline_context(prompt: str) -> str:
    """
    Helper tool to simulate context retrieval (e.g. system instructions or SRE documentation).
    """
    context_text = "Instructions: Prioritize service availability. Focus on root causes in microservices."
    LLMObs.annotate(
        input_data=prompt,
        output_data=context_text,
        tags={"context.type": "sre_instruction"}
    )
    return context_text

@llm(model_name="nova-pro", model_provider="bedrock")
def call_pipeline_llm(prompt: str, context: str, model_id: str = None) -> str:
    """
    Targeted LLM call combining context and user prompt.
    """
    full_prompt = f"{context}\n\nQuery: {prompt}"
    # Re-use ask_bedrock or call directly
    response = ask_bedrock(full_prompt, model_id=model_id)
    return response

@task
def format_pipeline_output(response: str) -> str:
    """
    Task to clean up or structure the response.
    """
    word_count = len(response.split())
    LLMObs.annotate(
        input_data=response,
        output_data=response,
        tags={"word_count": str(word_count)}
    )
    return response
