
import sqlite3
from pathlib import Path

CAMINHO_BANCO = Path(__file__).parent / "registros.db"


def consultar_registro(codigo):
    conexao = sqlite3.connect(CAMINHO_BANCO)
    conexao.row_factory = sqlite3.Row

    try:
        cursor = conexao.cursor()

        cursor.execute(
            "SELECT * FROM cadastro_principal WHERE codigo_registro = ?",
            (codigo,)
        )
        principal = cursor.fetchone()

        cursor.execute(
            "SELECT * FROM sistema_secundario WHERE codigo_registro = ?",
            (codigo,)
        )
        secundario = cursor.fetchone()

        return {
            "principal": dict(principal) if principal else None,
            "secundario": dict(secundario) if secundario else None
        }

    finally:
        conexao.close()


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

    campos = [
        "nome",
        "cpf",
        "tipo_registro",
        "data_registro",
        "status"
    ]

    for campo in campos:
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
        "divergencias": divergencias
    }


if __name__ == "__main__":
    resultado = consultar_registro("REG-001")

    comparacao = comparar_registros(
        resultado["principal"],
        resultado["secundario"]
    )

    print(comparacao)
