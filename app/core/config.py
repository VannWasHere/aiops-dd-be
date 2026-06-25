import os
from dotenv import load_dotenv
from pydantic_settings import BaseSettings
from pydantic import Field

# Load environment variables from .env file into os.environ
load_dotenv()

class Settings(BaseSettings):
    DATABASE_URL: str = Field(default="postgresql://postgres:postgrespassword@localhost:5432/cable3_ops")
    
    # AWS Bedrock Configuration
    AWS_ACCESS_KEY_ID: str = Field(default="")
    AWS_SECRET_ACCESS_KEY: str = Field(default="")
    AWS_REGION: str = Field(default="us-east-1")
    BEDROCK_MODEL_ID: str = Field(default="amazon.nova-pro-v1:0")
    
    # Legacy field for backward compatibility
    BEDROCK_REGION: str = Field(default="us-east-1")
    
    # Datadog Configuration
    DD_API_KEY: str = Field(default="")
    DD_APP_KEY: str = Field(default="")
    DD_LLMOBS_ML_APP: str = Field(default="aiops-backend")
    DD_SITE: str = Field(default="datadoghq.com")
    
    # Legacy fields for backward compatibility
    DATADOG_API_KEY: str = Field(default="")
    DATADOG_APP_KEY: str = Field(default="")
    
    MCP_SERVER_URL: str = Field(default="https://mcp.datadoghq.com/v1/mcp?toolsets=all")

    @property
    def datadog_api_key_val(self) -> str:
        return self.DD_API_KEY or self.DATADOG_API_KEY or os.environ.get("DD_API_KEY", "")

    @property
    def datadog_app_key_val(self) -> str:
        return self.DD_APP_KEY or self.DATADOG_APP_KEY or os.environ.get("DD_APP_KEY", "")

    @property
    def mcp_server_url_val(self) -> str:
        val = self.MCP_SERVER_URL or os.environ.get("MCP_SERVER_URL", "")
        if not val or val.strip() == "":
            return "https://mcp.datadoghq.com/v1/mcp?toolsets=all"
        return val

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

settings = Settings()
