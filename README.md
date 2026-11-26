# AuditReg — protótipo acadêmico

Python 3.11 ou superior. Use apenas dados fictícios.

## Instalação (Windows / PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edite `.env` com sua própria chave Gemini. Não publique esse arquivo.

```powershell
.\.venv\Scripts\python.exe app.py
```

Abra http://127.0.0.1:5000. O banco existente é preservado; se ausente, as tabelas são criadas vazias. Gere registros fictícios pela interface. Relatórios são exportados pelo diálogo de impressão do navegador.

## Testes

```powershell
.\.venv\Scripts\python.exe -m unittest -v test_retificacao
```

Ambiente local, sem autenticação: não exponha à internet. A IA é auxiliar e não altera o banco.
