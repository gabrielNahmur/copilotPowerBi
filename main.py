import os
import pandas as pd
from fastapi import FastAPI
from pydantic import BaseModel
import openai
from sqlalchemy import create_engine, text

app = FastAPI()

openai.api_key = os.getenv("OPENAI_API_KEY")
db_connection_str = os.getenv("DATABASE_URL")
engine = create_engine(db_connection_str)

def carregar_schema():
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
            return "ERRO: Nem a variável de ambiente DB_SCHEMA_DEFINITION nem o arquivo schema.txt foram encontrados."

schema_definition = carregar_schema()

class QuestionRequest(BaseModel):
    question: str

@app.post("/ask")
def ask_my_data(request: QuestionRequest):
    user_question = request.question

    prompt = f"""
    Sua tarefa é traduzir a pergunta de um usuário em uma consulta SQL válida para o Microsoft SQL Server, com base no esquema abaixo.

    Esquema da tabela TMPBI_VENDA_DETALHADA:
    {schema_definition}

    REGRAS IMPORTANTES:
    1. Regra de Agregação: Em cláusulas ORDER BY, quando ordenar por uma coluna agregada, SEMPRE repita a função de agregação (ex: ORDER BY SUM(QTD_VENDA) DESC). NUNCA use o alias da coluna.
    2. Regra de Filtro: NÃO adicione nenhuma cláusula WHERE a menos que o usuário peça explicitamente por um filtro de tempo, cliente, ou outro. Se a pergunta for geral (ex: 'quais os mais vendidos'), a consulta NÃO deve ter WHERE.
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
        
        print("--- SQL Limpo Enviado ao Banco ---")
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
    return {"message": "Bem-vindo à sua API de Análise de Dados! Use o endpoint /ask para fazer perguntas."}
