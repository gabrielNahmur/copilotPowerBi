import os
import pandas as pd
from fastapi import FastAPI
from pydantic import BaseModel
import openai
from sqlalchemy import create_engine, text


app = FastAPI()


openai.api_key = os.getenv("OPENAI_API_KEY")
db_connection_str = os.getenv("DATABASE_URL")


if not db_connection_str:
    print("ERRO CRÍTICO: A variável de ambiente DATABASE_URL não foi encontrada.")
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
        print("--- Schema carregado da variável de ambiente ---")
        return schema
    else:
        try:
            with open("schema.txt", "r", encoding="utf-8") as f:
                print("--- Schema carregado do arquivo local schema.txt ---")
                return f.read()
        except FileNotFoundError:
            print("ERRO CRÍTICO: Nem a variável de ambiente DB_SCHEMA_DEFINITION nem o arquivo schema.txt foram encontrados.")
            return "ERRO DE CONFIGURAÇÃO DO SCHEMA"


schema_definition = carregar_schema()



class QuestionRequest(BaseModel):
    question: str

@app.post("/ask")
def ask_my_data(request: QuestionRequest):
    user_question = request.question

    
    if engine is None:
        return {"error": "A conexão com o banco de dados não foi configurada corretamente no servidor."}
    if "ERRO DE CONFIGURAÇÃO" in schema_definition:
        return {"error": schema_definition}


    
    prompt = f"""
    Sua tarefa é traduzir a pergunta de um usuário em uma consulta SQL válida para o PostgreSQL, com base no esquema abaixo.

    Esquema da tabela:
    {schema_definition}

    REGRAS IMPORTANTES:
    1. Para selecionar um número específico de itens (ex: "top 5", "os 10 mais"), use a sintaxe 'LIMIT numero' no final da consulta.
    2. Regra de Filtro: NÃO adicione nenhuma cláusula WHERE a menos que o usuário peça explicitamente por um filtro (de tempo, cliente, etc.).
    3. Responda APENAS com o código SQL, sem explicações, acentos graves (```) ou comentários.

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
        
        print("--- SQL Limpo (PostgreSQL) Enviado ao Banco ---")
        print(generated_sql)

    except Exception as e:
        return {"error": f"Erro ao chamar a API da OpenAI: {e}"}

    try:
        
        with engine.connect() as connection:
            result_df = pd.read_sql_query(sql=text(generated_sql), con=connection)
        
        return result_df.to_dict(orient="records")
    except Exception as e:
        return {"error": f"Erro ao executar a consulta no banco de dados: {e}\n[SQL Gerado que falhou: {generated_sql}]"}


@app.get("/")
def read_root():
    return {"message": "Bem-vindo à sua API de Análise de Dados! Conectado ao Neon."}

