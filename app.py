from flask import Flask, render_template, request

from datetime import datetime


# ==========================================================
# APLICAÇÃO FLASK
# ==========================================================

app = Flask(__name__)


# ==========================================================
# PÁGINA INICIAL
# ==========================================================

@app.route("/")
def inicio():

    return render_template("index.html")


# ==========================================================
# PÁGINA DE AGENDAMENTO
# ==========================================================

@app.route("/agendar", methods=["GET", "POST"])
def agendar():

    # ------------------------------------------------------
    # Quando a cliente enviar o formulário
    # ------------------------------------------------------

    if request.method == "POST":

        nome = request.form.get("nome")
        telefone = request.form.get("telefone")
        servico = request.form.get("servico")
        data = request.form.get("data")
        horario = request.form.get("horario")
        observacoes = request.form.get("observacoes")


        # --------------------------------------------------
        # TESTE NO TERMINAL
        # --------------------------------------------------

        print("\n==============================")
        print("NOVO AGENDAMENTO")
        print("==============================")

        print("Nome:", nome)
        print("Telefone:", telefone)
        print("Serviço:", servico)
        print("Data:", data)
        print("Horário:", horario)
        print("Observações:", observacoes)

        print("==============================\n")


        # --------------------------------------------------
        # FORMATAR A DATA
        # --------------------------------------------------

        data_formatada = datetime.strptime(
            data,
            "%Y-%m-%d"
        ).strftime("%d/%m/%Y")


        # --------------------------------------------------
        # MOSTRAR PÁGINA DE CONFIRMAÇÃO
        # --------------------------------------------------

        return render_template(
            "confirmacao.html",
            nome=nome,
            telefone=telefone,
            servico=servico,
            data_formatada=data_formatada,
            horario=horario,
            observacoes=observacoes
        )


    # ------------------------------------------------------
    # Quando apenas abrir a página
    # ------------------------------------------------------

    return render_template("agendar.html")


# ==========================================================
# MEUS AGENDAMENTOS
# ==========================================================

@app.route("/meus-agendamentos")
def meus_agendamentos():

    return render_template(
        "meus_agendamentos.html"
    )


# ==========================================================
# INICIA O SERVIDOR
# ==========================================================

if __name__ == "__main__":

    app.run(debug=True)
