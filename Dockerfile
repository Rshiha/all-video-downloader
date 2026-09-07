FROM node:20-slim AS frontend-build
WORKDIR /app
COPY package*.json frontend/package*.json ./
RUN if [ -f package.json ]; then npm install; elif [ -f frontend/package.json ]; then cd frontend && npm install; fi
COPY . .
RUN if [ -f package.json ]; then npm run build; elif [ -f frontend/package.json ]; then cd frontend && npm run build; fi

FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends \n    ffmpeg \n    curl \n    unzip \n    && rm -rf /var/lib/apt/lists/* \n    && curl -fsSL https://deno.land/install.sh | sh \n    && mv /root/.deno/bin/deno /usr/local/bin/deno

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN if [ -d frontend/dist ]; then cp -r frontend/dist ./static; elif [ -d dist ]; then cp -r dist ./static; fi

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
