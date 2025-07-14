FROM python:3.11-slim-bullseye


ENV DEBIAN_FRONTEND=noninteractive
ENV ACCEPT_EULA=Y


RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gnupg \
    unixodbc-dev \
    ca-certificates \
    curl && \
    \
    
    curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg && \
    \
    
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/debian/11/prod bullseye main" > /etc/apt/sources.list.d/mssql-release.list && \
    \
   
    apt-get update && \
    \
   
    apt-get install -y --no-install-recommends msodbcsql18 && \
    \
  
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 10000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "10000"]
