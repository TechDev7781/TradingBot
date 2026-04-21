FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.5.7 /uv /uvx /bin/

COPY . /app

WORKDIR  /app

ARG ENV

ENV UV_HTTP_TIMEOUT=300
ENV UV_RESOLVER_PREFERENCE=lowest-direct

# Р•СЃР»Рё `ENV=build`, РЅРµ СѓСЃС‚Р°РЅР°РІР»РёРІР°С‚СЊ Р·Р°РІРёСЃРёРјРѕСЃС‚Рё dev (РЅСѓР¶РЅС‹ С‚РѕР»СЊРєРѕ РґР»СЏ СЂР°Р·СЂР°Р±РѕС‚РєРё Рё С‚РµСЃС‚РѕРІ).       
# Р’ РїСЂРѕС‚РёРІРЅРѕРј СЃР»СѓС‡Р°Рµ СѓСЃС‚Р°РЅРѕРІРёС‚СЊ РІСЃРµ Р·Р°РІРёСЃРёРјРѕСЃС‚Рё.

RUN if [ "$ENV" = "build" ]; then \
      uv sync --no-dev; \
    else \
      uv sync --all-groups --link-mode=copy; \
    fi

ENV PATH="/app/.venv/bin:$PATH"