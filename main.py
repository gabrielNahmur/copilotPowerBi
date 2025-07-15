import os
import pandas as pd
from fastapi import FastAPI
from pydantic import BaseModel
import openai
from sqlalchemy import create_engine, text
import numpy as np 

app = FastAPI()

openai.api_key = os.getenv("OPENAI_API_KEY")
db_connection_str = os.getenv("DATABASE_URL")

if not db_connection_str:
    engine = None
else:
    engine = create_engine(db_connection_str)

def carregar_schema():
    """
    Carrega o schema do banco de dados a partir de uma variável de ambiente (para produção no Render)
    ou de um arquivo local (para desenvolvimento no seu computador).
    """
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

@app.post("/ask")
def ask_my_data(request: QuestionRequest):
    user_question = request.question

    if engine is None or "ERRO" in schema_definition:
        return {"error": "Erro de configuração do servidor."}

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
        return {"error": f"Erro ao chamar a API da OpenAI: {e}"}

    try:
        with engine.connect() as connection:
            result_df = pd.read_sql_query(sql=text(generated_sql), con=connection)
        
        result_df.replace([np.inf, -np.inf], np.nan, inplace=True)
        
        return result_df.to_dict(orient="records")
        
    except Exception as e:
        return {"error": f"Erro ao executar a consulta no banco de dados: {e}\n[SQL Gerado que falhou: {generated_sql}]"}

@app.get("/")
def read_root():
    return {"message": "Bem-vindo à sua API de Análise de Dados! Conectado ao Neon."}
