import os
from dotenv import load_dotenv
from google import genai

load_dotenv()

cliente = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)

try:
    resposta = cliente.models.generate_content(
        model="gemini-3.5-flash-lite",
        contents="Responda apenas: Teste realizado com sucesso."
    )

    print("Resposta:", resposta.text)

except Exception as erro:
    print("Erro:", erro)
