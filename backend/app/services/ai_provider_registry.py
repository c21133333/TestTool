from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, status

from backend.app.core.config import settings


@dataclass(slots=True)
class AiGenerationRuntimeConfig:
    provider: str
    endpoint: str
    model: str
    api_key: str
    timeout_seconds: int
    use_env_proxy: bool = False


class AiProviderRegistry:
    def resolve_runtime(
        self,
        *,
        provider: str = "",
        model: str = "",
        base_url: str = "",
        api_key: str = "",
        timeout_seconds: int | None = None,
    ) -> AiGenerationRuntimeConfig:
        provider_value = provider or settings.ai_provider
        endpoint_value = base_url or settings.ai_endpoint
        model_value = model or settings.ai_model
        api_key_value = api_key or settings.ai_api_key
        timeout_value = timeout_seconds or settings.ai_timeout_seconds

        if provider_value != "openai_compatible":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported AI provider: {provider_value or 'unknown'}")
        if not endpoint_value:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="AI endpoint is required.")
        if not model_value:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="AI model is required.")
        if not api_key_value:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="AI API key is required.")

        return AiGenerationRuntimeConfig(
            provider=provider_value,
            endpoint=endpoint_value,
            model=model_value,
            api_key=api_key_value,
            timeout_seconds=timeout_value,
            use_env_proxy=settings.ai_use_env_proxy,
        )
