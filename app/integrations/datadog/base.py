from abc import ABC, abstractmethod
from typing import Dict, Any

class BaseDatadogClient(ABC):
    """
    Future Datadog MCP integration base class interface.
    This defines the interface for fetching observability data from Datadog.
    """

    @abstractmethod
    def get_service_metrics(self, service_name: str, hours: int = 1) -> Dict[str, Any]:
        """
        Fetch latency, error rates, and throughput metrics for a service.
        """
        pass

    @abstractmethod
    def get_service_logs(self, service_name: str, hours: int = 1) -> Dict[str, Any]:
        """
        Fetch error logs for a specific service.
        """
        pass

    @abstractmethod
    def query_active_alerts(self) -> Dict[str, Any]:
        """
        Fetch active alerts firing in Datadog.
        """
        pass
