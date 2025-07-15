import os
import pandas as pd
from fastapi import FastAPI, Response
from pydantic import BaseModel
import openai
from sqlalchemy import create_engine, text
import json
from decimal import Decimal
import datetime
import math # Importa a biblioteca de matemática para checagem

# --- Configuração Inicial ---
app = FastAPI()

# --- Tradutor JSON Definitivo e Robusto ---
# Esta classe é a solução final. Ela lida com todos os tipos de dados
# que podem causar problemas na conversão para JSON.
class FinalJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        # Se o objeto for do tipo Decimal
        if isinstance(obj, Decimal):
            # Se for um Decimal especial (Infinito, NaN), retorna nulo
            if obj.is_nan() or obj.is_infinite():
                return None
            # Senão, converte para float
            return float(obj)
        # Se o objeto for do tipo float
        if isinstance(obj, float):
            # Se for um float especial (Infinito, NaN), retorna nulo
            if not math.isfinite(obj):
                return None
            # Senão, retorna o float normal
            return obj
        # Se for um objeto de data ou hora
        if isinstance(obj, (datetime.datetime, datetime.date)):
            return obj.isoformat()
        # Para qualquer outro tipo, usa o comportamento padrão
        return super().default(obj)

# Esta classe de resposta usa nosso tradutor final
class FinalJSONResponse(Response):
    media_type = "application/json"
    def render(self, content: any) -> bytes:
        return json.dumps(
            content,
            ensure_ascii=False,
            allow_nan=False,
            indent=None,
            separators=(",", ":"),
            cls=FinalJSONEncoder, # Usa nosso tradutor final
        ).encode("utf-8")


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


# --- Endpoints da API ---
@app.post("/ask")
def ask_my_data(request: QuestionRequest):
    user_question = request.question

    if engine is None or "ERRO" in schema_definition:
        return FinalJSONResponse(status_code=500, content={"error": "Erro de configuração do servidor."})

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
        return FinalJSONResponse(status_code=500, content={"error": f"Erro ao chamar a API da OpenAI: {e}"})

    try:
        with engine.connect() as connection:
            result_df = pd.read_sql_query(sql=text(generated_sql), con=connection)
        
        data = result_df.to_dict(orient="records")
        
        # Usa nossa resposta final e robusta
        return FinalJSONResponse(content=data)
        
    except Exception as e:
        error_content = {"error": f"Erro ao executar a consulta no banco de dados: {e}", "sql_que_falhou": generated_sql}
        return FinalJSONResponse(status_code=500, content=error_content)

@app.get("/")
def read_root():
    return {"message": "Bem-vindo à sua API de Análise de Dados! Conectado ao Neon."}
