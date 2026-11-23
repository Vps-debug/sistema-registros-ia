import os
from dotenv import load_dotenv
from google import genai

load_dotenv()


def analisar_divergencias(comparacao):
    if comparacao["situacao"] == "Registros correspondentes":
        return "Os registros apresentam informações correspondentes."

    chave = os.getenv("GEMINI_API_KEY")

    if not chave:
        return "A chave da API Gemini não foi configurada."

    try:
        cliente = genai.Client(api_key=chave)

        prompt = f"""
        Você é um assistente de conferência de registros cartorários fictícios.

        Situação da conferência:
        {comparacao["situacao"]}

        Fonte em que o registro está ausente:
        {comparacao.get("fonte_ausente", "Nenhuma")}

        Diferenças entre os campos:
        {comparacao["divergencias"]}

        Sua tarefa:
        Explique o problema encontrado e oriente o funcionário
        sobre o que deve ser conferido.

        Se o registro estiver ausente em uma das fontes,
        explique qual fonte não possui o registro e recomende
        verificar a documentação de origem.

        Se houver diferenças entre os campos, explique
        essas diferenças e sugira uma conferência manual.

        Regras:
        - Responda em português brasileiro.
        - Não invente informações.
        - Não afirme qual fonte está correta.
        - Não sugira alterações automáticas.
        - Não repita dados pessoais desnecessariamente.
        - Responda sem Markdown ou asteriscos.
        - Utilize no máximo 120 palavras.
        """

        resposta = cliente.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=prompt
        )

        return resposta.text or "A IA não retornou uma explicação."

    except Exception as erro:
        print(f"Erro na integração Gemini: {erro}")

        if getattr(erro, "code", None) == 503:
            return (
                "O Gemini está temporariamente sobrecarregado. "
                "Os registros foram comparados normalmente. "
                "Tente novamente mais tarde."
            )

        return "Não foi possível obter a análise da IA no momento."
