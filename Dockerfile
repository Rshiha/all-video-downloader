FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \n    ffmpeg \n    curl \n    unzip \n    nodejs \n    npm \n    && rm -rf /var/lib/apt/lists/* \n    && curl -fsSL https://deno.land/install.sh | sh \n    && mv /root/.deno/bin/deno /usr/local/bin/deno

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN if [ -f package.json ]; then npm install && npm run build; fi

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
