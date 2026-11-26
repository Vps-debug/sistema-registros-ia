import sqlite3
import json
import re
from datetime import date, timedelta
from random import choice
from pathlib import Path
from contextlib import closing, contextmanager


# ==================================================
# CONFIGURAÇÕES DO BANCO
# ==================================================
CAMINHO_BANCO = Path(__file__).parent / "registros.db"
LIMITE_REGISTROS = 50
LIMITE_GERACAO = 20
REGISTROS_POR_PAGINA = 10
CAMPOS_COMPARADOS = (
    "nome",
    "cpf",
    "tipo_registro",
    "data_registro",
    "status"
)
FONTES = {
    "principal": "cadastro_principal",
    "secundario": "sistema_secundario"
}
CAMPOS_RETIFICAVEIS = {
    "Nome": "nome",
    "Cpf": "cpf",
    "Tipo registro": "tipo_registro",
    "Data registro": "data_registro",
    "Status": "status"
}


# ==================================================
# CONEXÕES E TRANSAÇÕES
# ==================================================


def criar_tabelas_fontes():
    """Inicializa as fontes sem alterar registros existentes."""
    with _transacao() as conexao:
        for tabela in FONTES.values():
            conexao.execute(f"""CREATE TABLE IF NOT EXISTS {tabela} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo_registro TEXT NOT NULL UNIQUE,
                nome TEXT NOT NULL, cpf TEXT NOT NULL,
                tipo_registro TEXT NOT NULL, data_registro TEXT NOT NULL,
                status TEXT NOT NULL
            )""")


@contextmanager
def _transacao():

    with closing(sqlite3.connect(CAMINHO_BANCO)) as conexao, conexao:
        conexao.row_factory = sqlite3.Row
        conexao.execute("PRAGMA foreign_keys = ON")
        conexao.execute("BEGIN IMMEDIATE")
        yield conexao


@contextmanager
def _leitura():

    with closing(sqlite3.connect(CAMINHO_BANCO)) as conexao, conexao:
        conexao.row_factory = sqlite3.Row
        conexao.execute("BEGIN")
        yield conexao


# ==================================================
# CONSULTA DE REGISTROS
# ==================================================


def consultar_registro(codigo, conexao=None):

    if conexao is None:

        with _leitura() as conexao:
            return consultar_registro(codigo, conexao)
    resultado = {}

    for fonte, tabela in FONTES.items():
        linha = conexao.execute(
            f"""
            SELECT *
            FROM {tabela}
            WHERE codigo_registro = ?
            """,
            (codigo,)
        ).fetchone()
        resultado[fonte] = dict(linha) if linha else None

    return resultado


# ==================================================
# COMPARAÇÃO DE REGISTROS
# ==================================================


def comparar_registros(principal, secundario):

    if principal is None or secundario is None:

        if principal is None and secundario is None:
            fonte_ausente = "Ambas as fontes"

        elif principal is None:
            fonte_ausente = "Cadastro principal"

        else:
            fonte_ausente = "Sistema secundário"

        return {
            "situacao": "Registro ausente em uma das fontes",
            "divergencias": {},
            "fonte_ausente": fonte_ausente
        }
    divergencias = {}

    for campo in CAMPOS_COMPARADOS:

        if principal[campo] != secundario[campo]:
            divergencias[campo] = {
                "principal": principal[campo],
                "secundario": secundario[campo]
            }

    return {
        "situacao": (
            "Divergência encontrada"
            if divergencias
            else "Registros correspondentes"
        ),
        "divergencias": divergencias,
        "fonte_ausente": None
    }


def _comparar(codigo, conexao):
    resultado = consultar_registro(codigo, conexao)

    return comparar_registros(
        resultado["principal"],
        resultado["secundario"]
    )


# ==================================================
# LISTAGEM DE REGISTROS
# ==================================================


def listar_registros(conexao=None):

    if conexao is None:

        with _leitura() as conexao:
            return listar_registros(conexao)
    codigos = conexao.execute("""
        SELECT codigo_registro FROM cadastro_principal

        UNION

        SELECT codigo_registro FROM sistema_secundario

        ORDER BY codigo_registro
    """).fetchall()
    registros = []

    for linha in codigos:
        codigo = linha["codigo_registro"]
        resultado = consultar_registro(codigo, conexao)
        principal = resultado["principal"]
        secundario = resultado["secundario"]
        comparacao = comparar_registros(
            principal,
            secundario
        )
        dados = principal or secundario
        registros.append({
            "codigo": codigo,
            "nome": dados["nome"],
            "tipo": dados["tipo_registro"],
            "situacao": comparacao["situacao"],
            "divergencias": comparacao["divergencias"],
            "fonte_ausente": comparacao["fonte_ausente"]
        })

    return registros


# ==================================================
# INDICADORES DO DASHBOARD
# ==================================================


def obter_indicadores(registros):
    indicadores = {
        "total": len(registros),
        "correspondentes": 0,
        "divergentes": 0,
        "ausentes": 0
    }

    for registro in registros:

        if registro["fonte_ausente"]:
            indicadores["ausentes"] += 1

        elif registro["divergencias"]:
            indicadores["divergentes"] += 1

        else:
            indicadores["correspondentes"] += 1

    return indicadores


# ==================================================
# GESTÃO DE PENDÊNCIAS
# ==================================================


def criar_tabela_pendencias():

    with _transacao() as conexao:
        conexao.execute("""
            CREATE TABLE IF NOT EXISTS pendencias (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                codigo_registro TEXT NOT NULL,

                descricao TEXT NOT NULL,

                status TEXT NOT NULL DEFAULT 'Pendente'
                    CHECK (
                        status IN (
                            'Pendente',
                            'Em análise',
                            'Resolvida'
                        )
                    ),

                observacao TEXT DEFAULT '',

                data_criacao TEXT DEFAULT CURRENT_TIMESTAMP,

                data_atualizacao TEXT DEFAULT CURRENT_TIMESTAMP,

                UNIQUE (codigo_registro, descricao)

            )
        """)


def _descricao(campo):

    return campo.replace("_", " ").capitalize()


def _sincronizar(conexao, codigo, comparacao):
    fonte_ausente = comparacao.get("fonte_ausente")
    inconsistencias = {
        _descricao(campo)
        for campo in comparacao["divergencias"]
    }

    if fonte_ausente:
        inconsistencias.add(
            "Fonte ausente: " + fonte_ausente
        )

    # Cria pendências para novas inconsistências.

    for descricao in inconsistencias:
        conexao.execute("""
            INSERT OR IGNORE INTO pendencias (
                codigo_registro,
                descricao
            )

            VALUES (?, ?)
        """, (codigo, descricao))
    pendencias = conexao.execute("""
        SELECT id, descricao, status
        FROM pendencias
        WHERE codigo_registro = ?
    """, (codigo,)).fetchall()

    for pendencia in pendencias:
        descricao = pendencia["descricao"]
        status = pendencia["status"]

        # Reabre uma pendência caso a inconsistência retorne.

        if descricao in inconsistencias and status == "Resolvida":
            conexao.execute("""
                UPDATE pendencias

                SET status = 'Pendente',
                    observacao = ?,
                    data_atualizacao = CURRENT_TIMESTAMP

                WHERE id = ?
            """, (
                "Inconsistência identificada novamente.",
                pendencia["id"]
            ))

        # Resolve inconsistências que não existem mais,
        # desde que ambas as fontes estejam disponíveis.

        elif (
            not fonte_ausente
            and descricao not in inconsistencias
            and status != "Resolvida"
        ):
            conexao.execute("""
                UPDATE pendencias

                SET status = 'Resolvida',
                    observacao = ?,
                    data_atualizacao = CURRENT_TIMESTAMP

                WHERE id = ?
            """, (
                "Inconsistência não identificada na comparação atual.",
                pendencia["id"]
            ))


def sincronizar_pendencias(conexao=None):

    if conexao is None:

        with _transacao() as conexao:
            return sincronizar_pendencias(conexao)
    codigos = conexao.execute("""
        SELECT codigo_registro FROM cadastro_principal

        UNION

        SELECT codigo_registro FROM sistema_secundario
    """).fetchall()

    for linha in codigos:
        codigo = linha["codigo_registro"]
        comparacao = _comparar(codigo, conexao)
        _sincronizar(
            conexao,
            codigo,
            comparacao
        )


def listar_pendencias(conexao=None):

    if conexao is None:

        with _leitura() as conexao:
            return listar_pendencias(conexao)
    cursor = conexao.execute("""
        SELECT *
        FROM pendencias

        ORDER BY

            CASE status

                WHEN 'Pendente' THEN 1
                WHEN 'Em análise' THEN 2
                WHEN 'Resolvida' THEN 3

            END,

            codigo_registro,
            id
    """)

    return [dict(linha) for linha in cursor.fetchall()]


def atualizar_pendencia(id_pendencia, status, observacao):
    status_validos = [
        "Pendente",
        "Em análise",
        "Resolvida"
    ]
    observacao = observacao.strip()

    if status not in status_validos:
        return False

    if len(observacao) > 2000:
        return False

    if status == "Resolvida" and not observacao:
        return False

    try:

        with _transacao() as conexao:
            pendencia = conexao.execute("""
                SELECT *
                FROM pendencias
                WHERE id = ?
            """, (id_pendencia,)).fetchone()

            if not pendencia:
                return False

            if status == "Resolvida":
                comparacao = _comparar(
                    pendencia["codigo_registro"],
                    conexao
                )
                campo = CAMPOS_RETIFICAVEIS.get(
                    pendencia["descricao"]
                )

                if comparacao.get("fonte_ausente"):
                    return False

                if campo in comparacao["divergencias"]:
                    return False

                if (
                    not campo
                    and not pendencia["descricao"].startswith(
                        "Fonte ausente:"
                    )
                ):
                    return False
            cursor = conexao.execute("""
                UPDATE pendencias

                SET status = ?,
                    observacao = ?,
                    data_atualizacao = CURRENT_TIMESTAMP

                WHERE id = ?
            """, (
                status,
                observacao,
                id_pendencia
            ))

            return cursor.rowcount > 0

    except sqlite3.Error as erro:
        print("Erro ao atualizar pendência:", erro)

        return False


def obter_indicadores_pendencias(pendencias):

    return {
        "total": len(pendencias),
        "pendentes": sum(
            p["status"] == "Pendente"
            for p in pendencias
        ),
        "em_analise": sum(
            p["status"] == "Em análise"
            for p in pendencias
        ),
        "resolvidas": sum(
            p["status"] == "Resolvida"
            for p in pendencias
        )
    }


# ==================================================
# RETIFICAÇÃO DE REGISTROS
# ==================================================


def criar_tabela_retificacoes():

    with _transacao() as conexao:
        conexao.execute("""
            CREATE TABLE IF NOT EXISTS retificacoes (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                id_pendencia INTEGER NOT NULL,

                codigo_registro TEXT NOT NULL,

                campo TEXT NOT NULL,

                fonte TEXT NOT NULL,

                valor_anterior TEXT,

                valor_novo TEXT NOT NULL,

                justificativa TEXT NOT NULL,

                resultado TEXT NOT NULL,

                data_retificacao TEXT DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (id_pendencia)
                    REFERENCES pendencias(id)

            )
        """)


def obter_dados_retificacao(pendencia):
    campo = CAMPOS_RETIFICAVEIS.get(
        pendencia["descricao"]
    )

    if not campo:
        return None
    resultado = consultar_registro(
        pendencia["codigo_registro"]
    )
    comparacao = comparar_registros(
        resultado["principal"],
        resultado["secundario"]
    )

    return comparacao["divergencias"].get(campo)


def retificar_registro(
    id_pendencia,
    fonte,
    valor_novo,
    justificativa,
    valor_principal,
    valor_secundario
):
    valor_novo = valor_novo.strip()
    justificativa = justificativa.strip()

    if fonte not in FONTES:
        return False

    if not valor_novo or not justificativa:
        return False

    if len(valor_novo) > 255:
        return False

    if len(justificativa) > 2000:
        return False

    try:

        with _transacao() as conexao:
            pendencia = conexao.execute("""
                SELECT *
                FROM pendencias
                WHERE id = ?
            """, (id_pendencia,)).fetchone()

            if not pendencia:
                return False

            if pendencia["status"] == "Resolvida":
                return False
            campo = CAMPOS_RETIFICAVEIS.get(
                pendencia["descricao"]
            )

            if not campo:
                return False
            codigo = pendencia["codigo_registro"]
            registros = consultar_registro(
                codigo,
                conexao
            )
            comparacao = comparar_registros(
                registros["principal"],
                registros["secundario"]
            )

            if campo not in comparacao["divergencias"]:
                return False

            # Verifica se os valores foram alterados
            # desde a abertura do formulário.

            if (
                str(registros["principal"][campo])
                != valor_principal
                or
                str(registros["secundario"][campo])
                != valor_secundario
            ):
                return False
            valor_anterior = registros[fonte][campo]
            outra_fonte = (
                "secundario"
                if fonte == "principal"
                else "principal"
            )

            # A retificação deve eliminar a divergência.

            if valor_novo != str(
                registros[outra_fonte][campo]
            ):
                return False
            tabela = FONTES[fonte]
            cursor = conexao.execute(f"""
                UPDATE {tabela}

                SET {campo} = ?

                WHERE codigo_registro = ?
            """, (
                valor_novo,
                codigo
            ))

            if cursor.rowcount != 1:
                raise sqlite3.IntegrityError(
                    "Não foi possível atualizar o registro."
                )

            # Confere novamente os dados.
            nova_comparacao = _comparar(
                codigo,
                conexao
            )

            if (
                nova_comparacao.get("fonte_ausente")
                or
                campo in nova_comparacao["divergencias"]
            ):
                raise sqlite3.IntegrityError(
                    "A divergência não foi eliminada."
                )

            # Registra a retificação no histórico.
            conexao.execute("""
                INSERT INTO retificacoes (

                    id_pendencia,
                    codigo_registro,
                    campo,
                    fonte,
                    valor_anterior,
                    valor_novo,
                    justificativa,
                    resultado

                )

                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                id_pendencia,
                codigo,
                campo,
                fonte,
                valor_anterior,
                valor_novo,
                justificativa,
                "Divergência eliminada"
            ))

            # Atualiza a pendência correspondente.
            conexao.execute("""
                UPDATE pendencias

                SET status = 'Resolvida',
                    observacao = ?,
                    data_atualizacao = CURRENT_TIMESTAMP

                WHERE id = ?
            """, (
                justificativa,
                id_pendencia
            ))

            # Sincroniza outras inconsistências do registro.
            _sincronizar(
                conexao,
                codigo,
                nova_comparacao
            )

            return True

    except sqlite3.Error as erro:
        print("Erro na retificação:", erro)

        return False


def listar_retificacoes(conexao=None):

    if conexao is None:

        with _leitura() as conexao:
            return listar_retificacoes(conexao)
    cursor = conexao.execute("""
        SELECT *
        FROM retificacoes

        ORDER BY
            data_retificacao DESC,
            id DESC
    """)

    return [dict(linha) for linha in cursor.fetchall()]


# ==================================================
# HISTÓRICO DE AUDITORIAS
# ==================================================


def criar_tabela_historico():

    with _transacao() as conexao:
        conexao.execute("""
            CREATE TABLE IF NOT EXISTS historico_auditorias (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                codigo_registro TEXT NOT NULL,

                situacao TEXT NOT NULL,

                divergencias TEXT NOT NULL,

                fonte_ausente TEXT,

                analise_ia TEXT,

                data_conferencia TEXT DEFAULT CURRENT_TIMESTAMP

            )
        """)


def registrar_auditoria(codigo, comparacao, analise_ia):
    divergencias_json = json.dumps(
        comparacao["divergencias"],
        ensure_ascii=False
    )

    with _transacao() as conexao:
        cursor = conexao.execute("""
            INSERT INTO historico_auditorias (

                codigo_registro,
                situacao,
                divergencias,
                fonte_ausente,
                analise_ia

            )

            VALUES (?, ?, ?, ?, ?)
        """, (
            codigo,
            comparacao["situacao"],
            divergencias_json,
            comparacao.get("fonte_ausente"),
            analise_ia
        ))

        return cursor.lastrowid


def consultar_auditoria(id_auditoria):

    with _leitura() as conexao:
        linha = conexao.execute("""
            SELECT *
            FROM historico_auditorias
            WHERE id = ?
        """, (id_auditoria,)).fetchone()

        if linha is None:
            return None
        auditoria = dict(linha)
        auditoria["divergencias"] = json.loads(
            auditoria["divergencias"]
        )

        return auditoria


def listar_historico():

    with _leitura() as conexao:
        cursor = conexao.execute("""
            SELECT *
            FROM historico_auditorias

            ORDER BY
                data_conferencia DESC,
                id DESC
        """)
        auditorias = []

        for linha in cursor.fetchall():
            auditoria = dict(linha)
            auditoria["divergencias"] = json.loads(
                auditoria["divergencias"]
            )
            auditorias.append(auditoria)

        return auditorias


def obter_indicadores_historico(auditorias):
    correspondentes = sum(
        auditoria["situacao"] == "Registros correspondentes"

        for auditoria in auditorias
    )

    return {
        "total": len(auditorias),
        "correspondentes": correspondentes,
        "inconsistentes": (
            len(auditorias) - correspondentes
        )
    }


# ==================================================
# CONTEXTO DO ASSISTENTE IA
# ==================================================


def obter_contexto_assistente():

    with _transacao() as conexao:
        sincronizar_pendencias(conexao)
        registros = listar_registros(conexao)
        pendencias = listar_pendencias(conexao)
        retificacoes = listar_retificacoes(conexao)
    contexto = {
        "indicadores_registros":
            obter_indicadores(registros),
        "indicadores_pendencias":
            obter_indicadores_pendencias(pendencias),
        "registros": [],
        "pendencias": [],
        "retificacoes": []
    }

    # Informações dos registros.

    for registro in registros:
        contexto["registros"].append({
            "codigo": registro["codigo"],
            "tipo": registro["tipo"],
            "situacao": registro["situacao"],
            "campos_divergentes":
                list(registro["divergencias"].keys()),
            "fonte_ausente":
                registro["fonte_ausente"]
        })

    # Informações das pendências.

    for pendencia in pendencias:
        contexto["pendencias"].append({
            "codigo": pendencia["codigo_registro"],
            "descricao": pendencia["descricao"],
            "status": pendencia["status"]
        })

    # Informações das retificações.
    # Evita enviar nomes, CPFs e justificativas livres.

    for item in retificacoes:
        retificacao = {
            "codigo": item["codigo_registro"],
            "campo": item["campo"],
            "fonte": item["fonte"],
            "resultado": item["resultado"],
            "data": item["data_retificacao"]
        }

        if item["campo"] in (
            "status",
            "tipo_registro",
            "data_registro"
        ):
            retificacao["valor_anterior"] = (
                item["valor_anterior"]
            )
            retificacao["valor_novo"] = (
                item["valor_novo"]
            )
        contexto["retificacoes"].append(retificacao)

    return contexto


# ==================================================
# GERENCIAMENTO DE CADASTROS FICTÍCIOS
# ==================================================


def criar_tabela_edicoes():

    with _transacao() as conexao:
        conexao.execute("""
            CREATE TABLE IF NOT EXISTS edicoes_cadastros (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo_registro TEXT NOT NULL,
                fonte TEXT NOT NULL,
                dados_anteriores TEXT NOT NULL,
                dados_novos TEXT NOT NULL,
                data_edicao TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)


def criar_tabela_exclusoes():

    with _transacao() as conexao:
        conexao.execute("""
            CREATE TABLE IF NOT EXISTS exclusoes_cadastros (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo_registro TEXT NOT NULL,
                fonte TEXT NOT NULL,
                dados_excluidos TEXT NOT NULL,
                data_exclusao TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)


def contar_registros(conexao=None):

    if conexao is None:

        with _leitura() as conexao:
            return contar_registros(conexao)

    return conexao.execute("""
        SELECT COUNT(*) FROM (
            SELECT codigo_registro FROM cadastro_principal
            UNION
            SELECT codigo_registro FROM sistema_secundario
        )
    """).fetchone()[0]


def obter_capacidade():
    total = contar_registros()

    return {
        "total": total,
        "limite": LIMITE_REGISTROS,
        "disponiveis": max(0, LIMITE_REGISTROS - total),
        "percentual": min(100, round(
            total / LIMITE_REGISTROS * 100
        ))
    }


def _verificar_capacidade(conexao, quantidade):
    disponiveis = max(
        0, LIMITE_REGISTROS - contar_registros(conexao)
    )

    if quantidade > disponiveis:
        raise ValueError(
            f"Limite de {LIMITE_REGISTROS} registros. "
            f"Existem apenas {disponiveis} vagas disponíveis."
        )


def _proximo_numero(conexao):
    codigos = conexao.execute("""
        SELECT codigo_registro FROM cadastro_principal

        UNION
        SELECT codigo_registro FROM sistema_secundario

        UNION
        SELECT codigo_registro FROM exclusoes_cadastros

        UNION
        SELECT codigo_registro FROM historico_auditorias

        UNION
        SELECT codigo_registro FROM retificacoes

        UNION
        SELECT codigo_registro FROM edicoes_cadastros

        UNION
        SELECT codigo_registro FROM pendencias
    """).fetchall()
    numeros = []

    for linha in codigos:
        codigo = linha["codigo_registro"]

        if re.fullmatch(r"REG-[0-9]+", codigo):
            numeros.append(int(codigo[4:]))

    return max(numeros, default=0) + 1


def _inserir_cadastro(conexao, fonte, codigo, dados):
    tabela = FONTES[fonte]
    conexao.execute(f"""
        INSERT INTO {tabela} (
            codigo_registro,
            nome,
            cpf,
            tipo_registro,
            data_registro,
            status
        )
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        codigo,
        dados["nome"],
        dados["cpf"],
        dados["tipo_registro"],
        dados["data_registro"],
        dados["status"]
    ))


def _validar_cadastro(dados):

    for campo in CAMPOS_COMPARADOS:
        valor = dados.get(campo, "").strip()

        if not valor or len(valor) > 255:
            raise ValueError("Preencha todos os campos.")
        dados[campo] = valor

    if not re.fullmatch(r"[0-9]{11}", dados["cpf"]):
        raise ValueError("Informe um CPF fictício com 11 dígitos.")

    # CPFs válidos não são permitidos neste ambiente.
    numeros = [int(n) for n in dados["cpf"]]

    if len(set(numeros)) != 1:
        primeiro = (
            sum(numeros[i] * (10 - i) for i in range(9))
            * 10 % 11
        ) % 10
        segundo = (
            sum(numeros[i] * (11 - i) for i in range(10))
            * 10 % 11
        ) % 10

        if numeros[9:] == [primeiro, segundo]:
            raise ValueError("Utilize somente CPFs fictícios inválidos.")

    try:
        date.fromisoformat(dados["data_registro"])
    except ValueError:
        raise ValueError("Informe uma data válida.")

    if dados["status"] not in [
        "Ativo", "Pendente", "Inativo"
    ]:
        raise ValueError("Status inválido.")

    return dados


def gerar_registros(quantidade, modo):

    if not 1 <= quantidade <= LIMITE_GERACAO:
        raise ValueError("Quantidade inválida.")

    if modo not in [
        "correto", "divergente", "ausente", "misto"
    ]:
        raise ValueError("Modo de geração inválido.")
    codigos = []

    with _transacao() as conexao:
        _verificar_capacidade(conexao, quantidade)
        numero_inicial = _proximo_numero(conexao)

        for i in range(quantidade):
            numero = numero_inicial + i
            codigo = f"REG-{numero:03d}"

            # Identificador propositalmente inválido.
            base_cpf = f"{numero % 1000000000:09d}"
            primeiro = (
                sum(
                    int(n) * (10 - j)
                    for j, n in enumerate(base_cpf)
                ) * 10 % 11
            ) % 10
            cpf = base_cpf + str((primeiro + 1) % 10) + "0"
            dados = {
                "nome": f"Pessoa Fictícia {numero:03d}",
                "cpf": cpf,
                "tipo_registro": choice([
                    "Imóvel",
                    "Nascimento",
                    "Casamento",
                    "Procuração"
                ]),
                "data_registro": (
                    date.today() - timedelta(days=numero % 365)
                ).isoformat(),
                "status": "Ativo"
            }
            secundario = dados.copy()
            tipo = modo

            if modo == "misto":
                tipo = [
                    "correto",
                    "divergente",
                    "ausente"
                ][i % 3]

            if tipo == "divergente":
                campo = choice([
                    "nome",
                    "data_registro",
                    "status",
                    "tipo_registro"
                ])

                if campo == "nome":
                    secundario[campo] += " - Divergente"

                elif campo == "status":
                    secundario[campo] = "Pendente"

                elif campo == "data_registro":
                    secundario[campo] = (
                        date.fromisoformat(dados[campo])
                        + timedelta(days=2)
                    ).isoformat()

                elif campo == "tipo_registro":
                    secundario[campo] = "Outro"

            if tipo == "ausente":
                fonte = choice(["principal", "secundario"])
                _inserir_cadastro(
                    conexao, fonte, codigo, dados
                )

            else:
                _inserir_cadastro(
                    conexao, "principal", codigo, dados
                )
                _inserir_cadastro(
                    conexao, "secundario", codigo, secundario
                )
            _sincronizar(
                conexao,
                codigo,
                _comparar(codigo, conexao)
            )
            codigos.append(codigo)

    return codigos


def criar_cadastro(dados, fonte):
    dados = _validar_cadastro(dados)

    if fonte not in ["principal", "secundario", "ambas"]:
        raise ValueError("Fonte inválida.")

    with _transacao() as conexao:
        _verificar_capacidade(conexao, 1)
        numero = _proximo_numero(conexao)
        codigo = f"REG-{numero:03d}"
        fontes = (
            ["principal", "secundario"]
            if fonte == "ambas"
            else [fonte]
        )

        for item in fontes:
            _inserir_cadastro(
                conexao, item, codigo, dados
            )
        _sincronizar(
            conexao,
            codigo,
            _comparar(codigo, conexao)
        )

        return codigo


def editar_cadastro(codigo, fonte, dados):
    dados = _validar_cadastro(dados)

    if fonte not in FONTES:
        raise ValueError("Fonte inválida.")

    with _transacao() as conexao:
        registros = consultar_registro(codigo, conexao)
        anterior = registros[fonte]

        if anterior is None:
            raise ValueError("Cadastro não encontrado nesta fonte.")
        dados_anteriores = {
            campo: anterior[campo]
            for campo in CAMPOS_COMPARADOS
        }

        if dados_anteriores == dados:
            return False
        tabela = FONTES[fonte]
        cursor = conexao.execute(f"""
            UPDATE {tabela}

            SET nome = ?,
                cpf = ?,
                tipo_registro = ?,
                data_registro = ?,
                status = ?

            WHERE codigo_registro = ?
        """, (
            dados["nome"],
            dados["cpf"],
            dados["tipo_registro"],
            dados["data_registro"],
            dados["status"],
            codigo
        ))

        if cursor.rowcount != 1:
            raise ValueError("Não foi possível atualizar o cadastro.")
        conexao.execute("""
            INSERT INTO edicoes_cadastros (
                codigo_registro,
                fonte,
                dados_anteriores,
                dados_novos
            )
            VALUES (?, ?, ?, ?)
        """, (
            codigo,
            fonte,
            json.dumps(dados_anteriores, ensure_ascii=False),
            json.dumps(dados, ensure_ascii=False)
        ))
        _sincronizar(
            conexao,
            codigo,
            _comparar(codigo, conexao)
        )

        return True


def excluir_cadastro(codigo, fonte):

    if fonte not in ["principal", "secundario", "ambas"]:
        raise ValueError("Fonte inválida.")

    with _transacao() as conexao:
        registros = consultar_registro(codigo, conexao)
        fontes = (
            ["principal", "secundario"]
            if fonte == "ambas"
            else [fonte]
        )
        excluidos = 0

        for item in fontes:
            dados = registros[item]

            if dados is None:
                continue
            tabela = FONTES[item]

            # Preserva os dados excluídos para rastreabilidade.
            conexao.execute("""
                INSERT INTO exclusoes_cadastros (
                    codigo_registro,
                    fonte,
                    dados_excluidos
                )
                VALUES (?, ?, ?)
            """, (
                codigo,
                item,
                json.dumps(dados, ensure_ascii=False)
            ))
            cursor = conexao.execute(f"""
                DELETE FROM {tabela}
                WHERE codigo_registro = ?
            """, (codigo,))

            if cursor.rowcount != 1:
                raise sqlite3.IntegrityError(
                    "Não foi possível excluir o cadastro."
                )
            excluidos += 1

        if excluidos == 0:
            raise ValueError(
                "Nenhum cadastro encontrado para exclusão."
            )
        resultado = consultar_registro(codigo, conexao)

        # Exclusão completa do registro.

        if not resultado["principal"] and not resultado["secundario"]:
            conexao.execute("""
                UPDATE pendencias

                SET status = 'Resolvida',
                    observacao = ?,
                    data_atualizacao = CURRENT_TIMESTAMP

                WHERE codigo_registro = ?
                AND status != 'Resolvida'
            """, (
                "Pendência encerrada por exclusão do "
                "cadastro fictício, sem retificação.",
                codigo
            ))

        # Exclusão de apenas uma fonte.

        else:
            comparacao = comparar_registros(
                resultado["principal"],
                resultado["secundario"]
            )
            _sincronizar(
                conexao,
                codigo,
                comparacao
            )

        return excluidos


# ==================================================
# TESTE LOCAL
# ==================================================

if __name__ == "__main__":
    resultado = consultar_registro("REG-001")
    comparacao = comparar_registros(
        resultado["principal"],
        resultado["secundario"]
    )
    print(comparacao)
