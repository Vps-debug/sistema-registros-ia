# Revisão técnica

Redução principalmente por remoção de linhas em branco, sem minificação. Barra de capacidade com progress; criação de tabelas de origem; debug desativado; limite de requisição de 128 KiB; integração Gemini compartilhada, sem valores divergentes pessoais no prompt de conferência; dependências e testes atualizados. Banco preservado byte a byte.

| Arquivo | Antes | Depois |
|---|---:|---:|
| app.py | 586 | 506 |
| banco.py | 1546 | 1370 |
| ia.py | 166 | 155 |
| static/script.js | 201 | 201 |
| static/style.css | 1750 | 1745 |
| templates/assistente.html | 135 | 93 |
| templates/base.html | 127 | 93 |
| templates/conferencia.html | 360 | 232 |
| templates/erro_retificacao.html | 10 | 10 |
| templates/form_retificacao.html | 34 | 34 |
| templates/historico.html | 400 | 250 |
| templates/historico_retificacoes.html | 29 | 29 |
| templates/index.html | 173 | 122 |
| templates/pendencias.html | 524 | 365 |
| templates/registros.html | 847 | 496 |
| templates/relatorio.html | 576 | 438 |
| test_retificacao.py | 144 | 61 |
| teste_gemini.py | 20 | 20 |
| Total | 7628 | 6220 |

Testes SQLite: 3 aprovados. Sintaxe Python e Jinja: aprovada. Flask e Gemini indisponíveis neste ambiente; rotas HTTP, API real, CSS visual e impressão não testados. CSS e JS não receberam refatoração estrutural ampla. Sem autenticação ou proteção CSRF completa; uso exclusivamente local. Dependências com faixas de versão não verificadas em instalação limpa.
