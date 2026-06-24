import os
from pydantic_settings import BaseSettings
from pydantic import Field

class Settings(BaseSettings):
    DATABASE_URL: str = Field(default="postgresql://postgres:postgrespassword@localhost:5432/cable3_ops")
    BEDROCK_REGION: str = Field(default="us-east-1")
    BEDROCK_MODEL_ID: str = Field(default="anthropic.claude-3-sonnet-20240229-v1:0")
    DATADOG_API_KEY: str = Field(default="")
    DATADOG_APP_KEY: str = Field(default="")
    MCP_SERVER_URL: str = Field(default="")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

settings = Settings()
