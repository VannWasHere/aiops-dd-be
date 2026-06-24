from abc import ABC, abstractmethod
from typing import Dict, Any, List

class BaseBedrockClient(ABC):
    """
    Future AWS Bedrock integration base class interface.
    This defines the interface for calling LLMs on AWS Bedrock.
    """

    @abstractmethod
    def generate_incident_rca(self, service_metrics: Dict[str, Any], service_logs: List[Dict[str, Any]], query: str) -> Dict[str, Any]:
        """
        Generate RCA, summary, recommendations, and timeline using AWS Bedrock.
        """
        pass

    @abstractmethod
    def run_chat_turn(self, history: List[Dict[str, str]], message: str) -> str:
        """
        Send a conversational message to Bedrock to help debug the incident.
        """
        pass
