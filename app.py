from flask import Flask, render_template, request
from datetime import datetime
import os
import psycopg2


# ==========================================================
# APLICAÇÃO FLASK
# ==========================================================

app = Flask(__name__)


# ==========================================================
# CONEXÃO COM O POSTGRESQL
# ==========================================================

def conectar_banco():

    return psycopg2.connect(
        os.environ.get("DATABASE_URL")
    )


# ==========================================================
# CRIAR TABELA DE AGENDAMENTOS
# ==========================================================

def criar_tabela():

    conexao = conectar_banco()
    cursor = conexao.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agendamentos (

            id SERIAL PRIMARY KEY,

            nome TEXT NOT NULL,

            telefone TEXT NOT NULL,

            servico TEXT NOT NULL,

            data DATE NOT NULL,

            horario TIME NOT NULL,

            observacoes TEXT,

            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP

        )
    """)

    conexao.commit()

    cursor.close()
    conexao.close()


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
        # SALVAR NO POSTGRESQL
        # --------------------------------------------------

        conexao = conectar_banco()
        cursor = conexao.cursor()

        cursor.execute("""
            INSERT INTO agendamentos
            (
                nome,
                telefone,
                servico,
                data,
                horario,
                observacoes
            )
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            nome,
            telefone,
            servico,
            data,
            horario,
            observacoes
        ))

        conexao.commit()

        cursor.close()
        conexao.close()


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

        print("AGENDAMENTO SALVO NO POSTGRESQL")

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
# PREPARA O BANCO DE DADOS
# ==========================================================

criar_tabela()


# ==========================================================
# INICIA O SERVIDOR LOCAL
# ==========================================================

if __name__ == "__main__":

    app.run(debug=True)
