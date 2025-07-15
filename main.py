import os
import pandas as pd
from fastapi import FastAPI, Response
from pydantic import BaseModel
import openai
from sqlalchemy import create_engine, text
import json
from decimal import Decimal
import datetime
import math

# --- Configuração Inicial ---
app = FastAPI()

# --- Carregamento de Configurações ---
openai.api_key = os.getenv("OPENAI_API_KEY")
db_connection_str = os.getenv("DATABASE_URL")

if not db_connection_str:
    engine = None
else:
    engine = create_engine(db_connection_str)

def carregar_schema():
    schema = os.getenv("DB_SCHEMA_DEFINITION")
    if schema:
        return schema
    else:
        try:
            with open("schema.txt", "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            return "ERRO DE CONFIGURAÇÃO DO SCHEMA"

schema_definition = carregar_schema()

class QuestionRequest(BaseModel):
    question: str

# --- Função de Limpeza Manual e Explícita ---
def clean_value(value):
    """
    Verifica e limpa um único valor para garantir que ele seja compatível com JSON.
    """
    if isinstance(value, (Decimal, float)):
        # Se for um número especial (Infinito, NaN), retorna nulo.
        if not math.isfinite(value):
            return None
        # Senão, converte para float padrão.
        return float(value)
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.isoformat()
    return value

# --- Endpoints da API ---
@app.post("/ask")
def ask_my_data(request: QuestionRequest):
    user_question = request.question

    if engine is None or "ERRO" in schema_definition:
        return Response(content=json.dumps({"error": "Erro de configuração do servidor."}), media_type="application/json", status_code=500)

    prompt = f"""
    Sua tarefa é traduzir a pergunta de um usuário em uma consulta SQL válida para o PostgreSQL.

    Esquema:
    {schema_definition}

    REGRAS CRÍTICAS:
    1. Para respeitar as letras maiúsculas, SEMPRE coloque os nomes das colunas e tabelas entre aspas duplas. Exemplo: SELECT "DESCRICAO_ITEM", SUM("QTD_VENDA") FROM "vendas_detalhadas".
    2. A única tabela que você deve usar é "vendas_detalhadas".
    3. Para selecionar "top 5", use 'LIMIT 5'.

    Pergunta do Usuário: "{user_question}"
    
    SQL:
    """

    try:
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0
        )
        raw_text = response.choices[0].message.content
        generated_sql = raw_text.replace("```sql", "").replace("```", "").replace("\n", " ").replace("\r", " ").strip()
        print("--- SQL Final (com aspas) Enviado ao Banco ---")
        print(generated_sql)
    except Exception as e:
        return Response(content=json.dumps({"error": f"Erro ao chamar a API da OpenAI: {e}"}), media_type="application/json", status_code=500)

    try:
        with engine.connect() as connection:
            result = connection.execute(text(generated_sql))
            
            # --- LÓGICA DE CONVERSÃO MANUAL ---
            # Em vez de usar pandas.to_dict, construímos a resposta manualmente.
            
            # Pega os nomes das colunas do resultado
            column_names = [desc[0] for desc in result.cursor.description]
            
            # Cria uma lista de dicionários, limpando cada valor individualmente
            data = [
                {column_names[i]: clean_value(value) for i, value in enumerate(row)}
                for row in result.fetchall()
            ]

        # Retorna os dados limpos como uma resposta JSON padrão do FastAPI
        return data
        
    except Exception as e:
        error_content = {"error": f"Erro ao executar a consulta no banco de dados: {e}", "sql_que_falhou": generated_sql}
        return Response(content=json.dumps(error_content), media_type="application/json", status_code=500)

@app.get("/")
def read_root():
    return {"message": "Bem-vindo à sua API de Análise de Dados! Conectado ao Neon."}
