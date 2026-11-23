from ia import analisar_divergencias
from flask import Flask, render_template, request
from banco import consultar_registro, comparar_registros

app = Flask(__name__)


@app.route("/", methods=["GET", "POST"])
def inicio():
    codigo = ""
    resultado = None
    comparacao = None
    analise_ia = None
    mensagem = None

    if request.method == "POST":
        codigo = request.form.get("codigo", "").strip().upper()

        if not codigo:
            mensagem = "Informe um código de registro."
        else:
            resultado = consultar_registro(codigo)

            if not resultado["principal"] and not resultado["secundario"]:
                mensagem = "Registro não encontrado."
            else:
                comparacao = comparar_registros(
                    resultado["principal"],
                    resultado["secundario"]
                )

                analise_ia = analisar_divergencias(comparacao)

    return render_template(
        "index.html",
        codigo=codigo,
        resultado=resultado,
        comparacao=comparacao,
        mensagem=mensagem,
        analise_ia=analise_ia
    )


if __name__ == "__main__":
    app.run(debug=True)
