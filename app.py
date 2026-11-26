import os
from secrets import compare_digest
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, jsonify, abort
from ia import analisar_divergencias, responder_assistente
from banco import (
    criar_tabelas_fontes,
    consultar_registro,
    comparar_registros,
    listar_registros,
    obter_indicadores,
    criar_tabela_pendencias,
    sincronizar_pendencias,
    listar_pendencias,
    atualizar_pendencia,
    obter_indicadores_pendencias,
    obter_contexto_assistente,
    criar_tabela_historico,
    consultar_auditoria,
    registrar_auditoria,
    listar_historico,
    obter_indicadores_historico,
    criar_tabela_retificacoes,
    retificar_registro,
    listar_retificacoes,
    obter_dados_retificacao,
    criar_tabela_edicoes,
    gerar_registros,
    criar_cadastro,
    editar_cadastro,
    criar_tabela_exclusoes,
    excluir_cadastro,
    obter_capacidade,
    LIMITE_GERACAO,
    REGISTROS_POR_PAGINA
)
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 128 * 1024
criar_tabelas_fontes()
criar_tabela_pendencias()
sincronizar_pendencias()
criar_tabela_historico()
criar_tabela_retificacoes()
criar_tabela_edicoes()
criar_tabela_exclusoes()

# Proteção de acesso à demonstração online
@app.before_request
def proteger_acesso():
    usuario = os.getenv("DEMO_USER", "auditreg")
    senha = os.getenv("DEMO_PASSWORD")

    if not senha:
        if os.getenv("RENDER") == "true":
            abort(503)
        return

    auth = request.authorization

    if (
        auth
        and auth.type == "basic"
        and compare_digest(
            (auth.username or "").encode(),
            usuario.encode()
        )
        and compare_digest(
            (auth.password or "").encode(),
            senha.encode()
        )
    ):
        return

    return (
        "Acesso restrito à demonstração.",
        401,
        {"WWW-Authenticate": 'Basic realm="AuditReg"'}
    )

# Página inicial
@app.route("/")
def inicio():
    registros = listar_registros()
    indicadores = obter_indicadores(registros)
    pendencias = [
        registro for registro in registros
        if registro["divergencias"] or registro["fonte_ausente"]
    ]

    return render_template(
        "index.html",
        indicadores=indicadores,
        pendencias=pendencias
    )

# Relatório individual de auditoria
@app.route("/relatorio/<int:id_auditoria>")
def relatorio(id_auditoria):
    auditoria = consultar_auditoria(id_auditoria)

    if auditoria is None:
        abort(404)

    return render_template(
        "relatorio.html",
        auditoria=auditoria
    )

# Página de conferência
@app.route("/conferencia", methods=["GET", "POST"])
def conferencia():
    codigo = request.values.get("codigo", "").strip().upper()
    resultado = None
    comparacao = None
    analise_ia = None
    mensagem = None
    id_auditoria = None

    if codigo:
        resultado = consultar_registro(codigo)

        if not resultado["principal"] and not resultado["secundario"]:
            mensagem = "Registro não encontrado."

        else:
            comparacao = comparar_registros(
                resultado["principal"],
                resultado["secundario"]
            )
            analise_ia = analisar_divergencias(comparacao)
            id_auditoria = registrar_auditoria(
                codigo,
                comparacao,
                analise_ia
            )

    elif request.method == "POST":
        mensagem = "Informe um código de registro."

    return render_template(
        "conferencia.html",
        codigo=codigo,
        resultado=resultado,
        comparacao=comparacao,
        mensagem=mensagem,
        analise_ia=analise_ia,
        id_auditoria=id_auditoria
    )

# Gerar registros fictícios em lote
@app.route("/registros/gerar", methods=["POST"])
def gerar_cadastros():

    try:
        quantidade = int(
            request.form.get("quantidade", "1")
        )
        modo = request.form.get("modo", "misto")
        codigos = gerar_registros(quantidade, modo)
        mensagem = (
            f"{len(codigos)} registro(s) gerado(s) com sucesso."
        )

    except ValueError as erro:
        mensagem = str(erro)

    except sqlite3.Error:
        mensagem = "Não foi possível gerar os registros."

    return redirect(url_for(
        "registros",
        mensagem=mensagem
    ))

# Obter os campos enviados pelos formulários
def dados_formulario():

    return {
        campo: request.form.get(campo, "").strip()
        for campo in [
            "nome",
            "cpf",
            "tipo_registro",
            "data_registro",
            "status"
        ]
    }

# Criar cadastro manual
@app.route("/registros/criar", methods=["POST"])
def novo_cadastro():

    try:
        codigo = criar_cadastro(
            dados_formulario(),
            request.form.get("fonte", "")
        )
        mensagem = f"Cadastro {codigo} criado com sucesso."

    except ValueError as erro:
        mensagem = str(erro)

    except sqlite3.Error:
        mensagem = "Não foi possível criar o cadastro."

    return redirect(url_for(
        "registros",
        mensagem=mensagem
    ))

# Editar cadastro existente
@app.route("/registros/<codigo>/editar", methods=["POST"])
def salvar_edicao(codigo):

    try:
        alterado = editar_cadastro(
            codigo,
            request.form.get("fonte", ""),
            dados_formulario()
        )
        mensagem = (
            "Cadastro atualizado com sucesso."
            if alterado
            else "Nenhuma alteração identificada."
        )

    except ValueError as erro:
        mensagem = str(erro)

    except sqlite3.Error:
        mensagem = "Não foi possível editar o cadastro."

    return redirect(url_for(
        "registros",
        mensagem=mensagem
    ))


@app.route("/registros/<codigo>/excluir", methods=["POST"])
def remover_cadastro(codigo):

    try:

        if request.form.get("confirmacao") != "sim":
            raise ValueError("Confirme a exclusão do cadastro.")
        fonte = request.form.get("fonte", "")
        excluir_cadastro(codigo, fonte)
        mensagem = f"Exclusão de {codigo} realizada com sucesso."

    except ValueError as erro:
        mensagem = str(erro)

    except sqlite3.Error:
        mensagem = "Não foi possível excluir o cadastro."

    return redirect(url_for(
        "registros",
        mensagem=mensagem
    ))

# Página de registros
@app.route("/registros")
def registros():
    busca = request.args.get("busca", "").strip()
    situacao = request.args.get("situacao", "")
    mensagem = request.args.get("mensagem", "")
    editar = request.args.get("editar", "").strip().upper()
    pagina = request.args.get("pagina", 1, type=int)
    pagina = max(1, pagina)
    lista = listar_registros()
    total = len(lista)
    capacidade = obter_capacidade()

    if busca:
        lista = [
            registro for registro in lista
            if busca.casefold() in registro["codigo"].casefold()
            or busca.casefold() in registro["nome"].casefold()
        ]

    if situacao == "correspondente":
        lista = [
            r for r in lista
            if not r["divergencias"]
            and not r["fonte_ausente"]
        ]

    elif situacao == "divergente":
        lista = [
            r for r in lista
            if r["divergencias"]
        ]

    elif situacao == "ausente":
        lista = [
            r for r in lista
            if r["fonte_ausente"]
        ]

    # Paginação após a aplicação dos filtros.
    total_filtrado = len(lista)
    total_paginas = max(
        1,
        (total_filtrado + REGISTROS_POR_PAGINA - 1)
        // REGISTROS_POR_PAGINA
    )
    pagina = min(pagina, total_paginas)
    inicio = (pagina - 1) * REGISTROS_POR_PAGINA
    fim = inicio + REGISTROS_POR_PAGINA
    lista = lista[inicio:fim]
    cadastro_edicao = (
        consultar_registro(editar)
        if editar else None
    )

    return render_template(
        "registros.html",
        registros=lista,
        busca=busca,
        situacao=situacao,
        total=total,
        mensagem=mensagem,
        editar=editar,
        cadastro_edicao=cadastro_edicao,
        capacidade=capacidade,
        limite_geracao=LIMITE_GERACAO,
        pagina=pagina,
        total_paginas=total_paginas,
        total_filtrado=total_filtrado,
        inicio=inicio,
        fim=min(fim, total_filtrado)
    )

# Página de pendências
@app.route("/pendencias")
def pendencias():
    sincronizar_pendencias()
    lista = listar_pendencias()
    indicadores = obter_indicadores_pendencias(lista)

    for pendencia in lista:
        pendencia["retificacao"] = obter_dados_retificacao(
            pendencia
        )
    busca = request.args.get("busca", "").strip()
    status = request.args.get("status", "")
    mensagem = request.args.get("mensagem", "")

    if busca:
        lista = [
            p for p in lista
            if busca.casefold() in p["codigo_registro"].casefold()
            or busca.casefold() in p["descricao"].casefold()
        ]

    if status:
        lista = [
            p for p in lista
            if p["status"] == status
        ]

    return render_template(
        "pendencias.html",
        pendencias=lista,
        indicadores=indicadores,
        busca=busca,
        status=status,
        mensagem=mensagem
    )

# Atualizar uma pendência
@app.route("/pendencias/<int:id_pendencia>/atualizar",
           methods=["POST"])
def salvar_pendencia(id_pendencia):
    status = request.form.get("status", "")
    observacao = request.form.get("observacao", "").strip()
    sucesso = atualizar_pendencia(
        id_pendencia,
        status,
        observacao
    )

    return redirect(url_for(
        "pendencias",
        mensagem="sucesso" if sucesso else "erro"
    ))


@app.route(
    "/pendencias/<int:id_pendencia>/retificar",
    methods=["POST"]
)
def salvar_retificacao(id_pendencia):
    fonte = request.form.get("fonte", "")
    valor_novo = request.form.get(
        "valor_novo", ""
    ).strip()
    justificativa = request.form.get(
        "justificativa", ""
    ).strip()
    sucesso = retificar_registro(
        id_pendencia,
        fonte,
        valor_novo,
        justificativa,
        request.form.get("valor_principal", ""),
        request.form.get("valor_secundario", "")
    )

    return redirect(url_for(
        "pendencias",
        mensagem=(
            "retificacao_sucesso"
            if sucesso
            else "retificacao_erro"
        )
    ))

# Página do assistente
@app.route("/assistente")
def assistente():

    return render_template("assistente.html")

# API de comunicação com o assistente
@app.route("/api/assistente", methods=["POST"])
def api_assistente():
    dados = request.get_json(silent=True)

    if not isinstance(dados, dict):

        return jsonify({
            "erro": "Requisição inválida."
        }), 400
    pergunta = dados.get("pergunta", "")

    if not isinstance(pergunta, str):

        return jsonify({
            "erro": "Pergunta inválida."
        }), 400
    pergunta = pergunta.strip()

    if not pergunta:

        return jsonify({
            "erro": "Informe uma pergunta."
        }), 400

    if len(pergunta) > 2000:

        return jsonify({
            "erro": "A pergunta é muito longa."
        }), 400
    historico = dados.get("historico", [])

    if not isinstance(historico, list):
        historico = []
    historico_validado = []

    for mensagem in historico[-6:]:

        if not isinstance(mensagem, dict):
            continue
        papel = mensagem.get("papel")
        texto = mensagem.get("texto")

        if (
            papel in ["usuario", "assistente"]
            and isinstance(texto, str)
        ):
            historico_validado.append({
                "papel": papel,
                "texto": texto[:2000]
            })
    contexto = obter_contexto_assistente()
    resposta = responder_assistente(
        pergunta,
        contexto,
        historico_validado
    )

    return jsonify({
        "resposta": resposta
    })


@app.route("/historico")
def historico():
    auditorias = listar_historico()
    indicadores = obter_indicadores_historico(auditorias)
    busca = request.args.get("busca", "").strip()
    situacao = request.args.get("situacao", "")
    data = request.args.get("data", "")

    if busca:
        auditorias = [
            a for a in auditorias
            if busca.casefold() in a["codigo_registro"].casefold()
        ]

    if situacao == "correspondente":
        auditorias = [
            a for a in auditorias
            if a["situacao"] == "Registros correspondentes"
        ]

    elif situacao == "divergente":
        auditorias = [
            a for a in auditorias
            if a["situacao"] == "Divergência encontrada"
        ]

    elif situacao == "ausente":
        auditorias = [
            a for a in auditorias
            if a["fonte_ausente"]
        ]

    if data:
        auditorias = [
            a for a in auditorias
            if a["data_conferencia"].startswith(data)
        ]
    retificacoes = [
        item for item in listar_retificacoes()
        if busca.casefold() in item["codigo_registro"].casefold()
        and item["data_retificacao"].startswith(data)
    ]
    return render_template(
        "historico.html",
        retificacoes=retificacoes,
        auditorias=auditorias,
        indicadores=indicadores,
        busca=busca,
        situacao=situacao,
        data=data
    )

if __name__ == "__main__":
    app.run()
