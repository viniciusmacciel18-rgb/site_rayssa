from flask import Flask, render_template, request, redirect, url_for, session
from datetime import datetime
import os
import psycopg2
from functools import wraps


# ==========================================================
# APLICAÇÃO FLASK
# ==========================================================

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "chave-temporaria"
)


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
        # LOG
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
        # FORMATAR DATA
        # --------------------------------------------------

        data_formatada = datetime.strptime(
            data,
            "%Y-%m-%d"
        ).strftime("%d/%m/%Y")


        # --------------------------------------------------
        # CONFIRMAÇÃO
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


    return render_template("agendar.html")


# ==========================================================
# PROTEÇÃO DO PAINEL ADMINISTRATIVO
# ==========================================================

def login_obrigatorio(funcao):

    @wraps(funcao)
    def verificar_login(*args, **kwargs):

        if not session.get("admin_logado"):

            return redirect(url_for("login"))

        return funcao(*args, **kwargs)

    return verificar_login


# ==========================================================
# LOGIN ADMINISTRATIVO
# ==========================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        usuario = request.form.get("usuario")
        senha = request.form.get("senha")


        usuario_correto = os.environ.get(
            "ADMIN_USERNAME"
        )

        senha_correta = os.environ.get(
            "ADMIN_PASSWORD"
        )


        if (
            usuario == usuario_correto
            and senha == senha_correta
        ):

            session["admin_logado"] = True

            return redirect(
                url_for("admin")
            )


        return render_template(
            "login.html",
            erro="Usuário ou senha incorretos."
        )


    return render_template(
        "login.html"
    )


# ==========================================================
# AGENDAMENTOS DO PAINEL
# ==========================================================

@app.route("/admin/agendamentos")
@login_obrigatorio
def admin_agendamentos():

    conexao = conectar_banco()
    cursor = conexao.cursor()

    cursor.execute("""
        SELECT
            id,
            nome,
            telefone,
            servico,
            data,
            horario,
            observacoes
        FROM agendamentos
        ORDER BY data ASC, horario ASC
    """)

    resultados = cursor.fetchall()

    cursor.close()
    conexao.close()


    # ------------------------------------------------------
    # TRANSFORMAR OS RESULTADOS
    # ------------------------------------------------------

    agendamentos = []

    for agendamento in resultados:

        agendamentos.append({

            "id": agendamento[0],

            "nome": agendamento[1],

            "telefone": agendamento[2],

            "servico": agendamento[3],

            "data": agendamento[4].strftime("%d/%m/%Y"),

            "horario": agendamento[5].strftime("%H:%M"),

            "observacoes": agendamento[6]

        })


    return render_template(
        "admin_agendamentos.html",
        agendamentos=agendamentos
    )


# ==========================================================
# SAIR DO PAINEL
# ==========================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(
        url_for("login")
    )


# ==========================================================
# MEUS AGENDAMENTOS
# ==========================================================

@app.route("/meus-agendamentos")
def meus_agendamentos():

    telefone = request.args.get("telefone")


    # ------------------------------------------------------
    # SE NÃO INFORMOU TELEFONE
    # ------------------------------------------------------

    if not telefone:

        return render_template(
            "meus_agendamentos.html",
            agendamentos=[]
        )


    # ------------------------------------------------------
    # BUSCAR AGENDAMENTOS
    # ------------------------------------------------------

    conexao = conectar_banco()
    cursor = conexao.cursor()

    cursor.execute("""
        SELECT
            id,
            nome,
            telefone,
            servico,
            data,
            horario,
            observacoes
        FROM agendamentos
        WHERE telefone = %s
        ORDER BY data ASC, horario ASC
    """, (telefone,))


    resultados = cursor.fetchall()

    cursor.close()
    conexao.close()


    # ------------------------------------------------------
    # TRANSFORMAR RESULTADOS
    # ------------------------------------------------------

    agendamentos = []

    for agendamento in resultados:

        agendamentos.append({

            "id": agendamento[0],

            "nome": agendamento[1],

            "telefone": agendamento[2],

            "servico": agendamento[3],

            "data": agendamento[4].strftime("%d/%m/%Y"),

            "horario": agendamento[5].strftime("%H:%M"),

            "observacoes": agendamento[6]

        })


    # ------------------------------------------------------
    # MOSTRAR RESULTADOS
    # ------------------------------------------------------

    return render_template(
        "meus_agendamentos.html",
        agendamentos=agendamentos,
        telefone=telefone
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
