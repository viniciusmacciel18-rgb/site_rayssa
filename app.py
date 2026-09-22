from flask import Flask, render_template, request, redirect, url_for, session, jsonify
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
# CRIAR TABELAS
# ==========================================================

def criar_tabela():

    conexao = conectar_banco()
    cursor = conexao.cursor()

    # ------------------------------------------------------
    # AGENDAMENTOS
    # ------------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agendamentos (
            id SERIAL PRIMARY KEY,
            nome TEXT NOT NULL,
            telefone TEXT NOT NULL,
            servico TEXT NOT NULL,
            data DATE NOT NULL,
            horario TIME NOT NULL,
            observacoes TEXT,
            status TEXT DEFAULT 'Confirmado',
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ------------------------------------------------------
    # BLOQUEIOS DE HORÁRIOS
    # ------------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bloqueios_horarios (
            id SERIAL PRIMARY KEY,
            data DATE NOT NULL,
            periodo TEXT,
            inicio TIME,
            fim TIME,
            motivo TEXT,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conexao.commit()

    cursor.close()
    conexao.close()


# ==========================================================
# ATUALIZAR TABELAS EXISTENTES
# ==========================================================

def atualizar_tabela():

    conexao = conectar_banco()
    cursor = conexao.cursor()

    # ------------------------------------------------------
    # GARANTIR STATUS DOS AGENDAMENTOS
    # ------------------------------------------------------

    cursor.execute("""
        ALTER TABLE agendamentos
        ADD COLUMN IF NOT EXISTS status
        TEXT DEFAULT 'Confirmado'
    """)

    cursor.execute("""
        UPDATE agendamentos
        SET status = 'Confirmado'
        WHERE status IS NULL
    """)

    # ------------------------------------------------------
    # GARANTIR NOVAS COLUNAS DOS BLOQUEIOS
    # ------------------------------------------------------

    cursor.execute("""
        ALTER TABLE bloqueios_horarios
        ADD COLUMN IF NOT EXISTS inicio TIME
    """)

    cursor.execute("""
        ALTER TABLE bloqueios_horarios
        ADD COLUMN IF NOT EXISTS fim TIME
    """)

    cursor.execute("""
        ALTER TABLE bloqueios_horarios
        ADD COLUMN IF NOT EXISTS motivo TEXT
    """)

    # ------------------------------------------------------
    # MIGRAR BLOQUEIOS ANTIGOS
    #
    # Caso existam bloqueios antigos usando:
    # manha / tarde / dia
    #
    # eles serão convertidos para intervalos.
    # ------------------------------------------------------

    cursor.execute("""
        UPDATE bloqueios_horarios
        SET
            inicio = '07:30',
            fim = '11:00'
        WHERE periodo = 'manha'
          AND inicio IS NULL
    """)

    cursor.execute("""
        UPDATE bloqueios_horarios
        SET
            inicio = '13:30',
            fim = '20:00'
        WHERE periodo = 'tarde'
          AND inicio IS NULL
    """)

    cursor.execute("""
        UPDATE bloqueios_horarios
        SET
            inicio = '00:00',
            fim = '23:59'
        WHERE periodo = 'dia'
          AND inicio IS NULL
    """)

    # ------------------------------------------------------
    # MOTIVO PADRÃO PARA BLOQUEIOS ANTIGOS
    # ------------------------------------------------------

    cursor.execute("""
        UPDATE bloqueios_horarios
        SET motivo = 'Bloqueio antigo'
        WHERE motivo IS NULL
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
        # VERIFICAR SE O HORÁRIO ESTÁ BLOQUEADO
        # --------------------------------------------------

        conexao = conectar_banco()
        cursor = conexao.cursor()

        cursor.execute("""
            SELECT
                inicio,
                fim
            FROM bloqueios_horarios
            WHERE data = %s
              AND inicio IS NOT NULL
              AND fim IS NOT NULL
              AND %s::time >= inicio
              AND %s::time < fim
            LIMIT 1
        """, (
            data,
            horario,
            horario
        ))

        bloqueio = cursor.fetchone()

        if bloqueio:

            cursor.close()
            conexao.close()

            return render_template(
                "agendar.html",
                erro=(
                    f"Este horário está bloqueado "
                    f"das {bloqueio[0].strftime('%H:%M')} "
                    f"às {bloqueio[1].strftime('%H:%M')}."
                )
            )

        # --------------------------------------------------
        # SALVAR AGENDAMENTO
        # --------------------------------------------------

        cursor.execute("""
            INSERT INTO agendamentos
            (
                nome,
                telefone,
                servico,
                data,
                horario,
                observacoes,
                status
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            nome,
            telefone,
            servico,
            data,
            horario,
            observacoes,
            "Confirmado"
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
        print("Status: Confirmado")
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
# CONSULTAR BLOQUEIOS DE UMA DATA
# ==========================================================

@app.route("/bloqueios/<data>")
def consultar_bloqueios(data):

    conexao = conectar_banco()
    cursor = conexao.cursor()

    cursor.execute("""
        SELECT
            inicio,
            fim,
            motivo
        FROM bloqueios_horarios
        WHERE data = %s
          AND inicio IS NOT NULL
          AND fim IS NOT NULL
        ORDER BY inicio ASC
    """, (data,))

    resultados = cursor.fetchall()

    cursor.close()
    conexao.close()

    bloqueios = []

    for resultado in resultados:

        bloqueios.append({
            "inicio": resultado[0].strftime("%H:%M"),
            "fim": resultado[1].strftime("%H:%M"),
            "motivo": resultado[2] or ""
        })

    return jsonify(bloqueios)


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
# PAINEL ADMINISTRATIVO
# ==========================================================

@app.route("/admin")
@login_obrigatorio
def admin():

    return render_template(
        "admin.html"
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
            observacoes,
            status
        FROM agendamentos
        ORDER BY data ASC, horario ASC
    """)

    resultados = cursor.fetchall()

    cursor.close()
    conexao.close()

    agendamentos = []

    for agendamento in resultados:

        agendamentos.append({

            "id": agendamento[0],

            "nome": agendamento[1],

            "telefone": agendamento[2],

            "servico": agendamento[3],

            "data": agendamento[4].strftime("%d/%m/%Y"),

            "horario": agendamento[5].strftime("%H:%M"),

            "observacoes": agendamento[6],

            "status": agendamento[7] or "Confirmado"

        })

    return render_template(
        "admin_agendamentos.html",
        agendamentos=agendamentos
    )


# ==========================================================
# CANCELAR AGENDAMENTO
# ==========================================================

@app.route(
    "/admin/cancelar/<int:agendamento_id>",
    methods=["POST"]
)
@login_obrigatorio
def cancelar_agendamento(agendamento_id):

    conexao = conectar_banco()
    cursor = conexao.cursor()

    cursor.execute("""
        UPDATE agendamentos
        SET status = 'Cancelado'
        WHERE id = %s
    """, (agendamento_id,))

    conexao.commit()

    cursor.close()
    conexao.close()

    return redirect(
        url_for("admin_agendamentos")
    )


# ==========================================================
# HORÁRIOS / BLOQUEIOS
# ==========================================================

@app.route("/admin/horarios")
@login_obrigatorio
def admin_horarios():

    conexao = conectar_banco()
    cursor = conexao.cursor()

    cursor.execute("""
        SELECT
            id,
            data,
            inicio,
            fim,
            motivo
        FROM bloqueios_horarios
        WHERE inicio IS NOT NULL
          AND fim IS NOT NULL
        ORDER BY data ASC, inicio ASC
    """)

    resultados = cursor.fetchall()

    cursor.close()
    conexao.close()

    bloqueios = []

    for bloqueio in resultados:

        bloqueios.append({

            "id": bloqueio[0],

            "data": bloqueio[1].strftime("%d/%m/%Y"),

            "inicio": bloqueio[2].strftime("%H:%M"),

            "fim": bloqueio[3].strftime("%H:%M"),

            "motivo": bloqueio[4] or "Sem motivo"

        })

    return render_template(
        "horarios.html",
        bloqueios=bloqueios
    )


# ==========================================================
# CRIAR BLOQUEIO DE HORÁRIO
# ==========================================================

@app.route(
    "/admin/horarios/bloquear",
    methods=["POST"]
)
@login_obrigatorio
def bloquear_horario():

    data = request.form.get("data")
    inicio = request.form.get("inicio")
    fim = request.form.get("fim")
    motivo = request.form.get("motivo")

    # ------------------------------------------------------
    # VERIFICAR CAMPOS
    # ------------------------------------------------------

    if not data or not inicio or not fim:

        return redirect(
            url_for("admin_horarios")
        )

    # ------------------------------------------------------
    # VERIFICAR HORÁRIOS
    # ------------------------------------------------------

    try:

        inicio_obj = datetime.strptime(
            inicio,
            "%H:%M"
        )

        fim_obj = datetime.strptime(
            fim,
            "%H:%M"
        )

    except ValueError:

        return redirect(
            url_for("admin_horarios")
        )

    # ------------------------------------------------------
    # HORÁRIO FINAL PRECISA SER MAIOR
    # ------------------------------------------------------

    if fim_obj <= inicio_obj:

        return redirect(
            url_for("admin_horarios")
        )

    # ------------------------------------------------------
    # CONECTAR BANCO
    # ------------------------------------------------------

    conexao = conectar_banco()
    cursor = conexao.cursor()

    # ------------------------------------------------------
    # VERIFICAR SE JÁ EXISTE BLOQUEIO SOBREPOSTO
    # ------------------------------------------------------

    cursor.execute("""
        SELECT id
        FROM bloqueios_horarios
        WHERE data = %s
          AND inicio IS NOT NULL
          AND fim IS NOT NULL
          AND inicio < %s::time
          AND fim > %s::time
        LIMIT 1
    """, (
        data,
        fim,
        inicio
    ))

    bloqueio_existente = cursor.fetchone()

    if bloqueio_existente:

        cursor.close()
        conexao.close()

        return redirect(
            url_for("admin_horarios")
        )

    # ------------------------------------------------------
    # SALVAR NOVO BLOQUEIO
    # ------------------------------------------------------

    cursor.execute("""
        INSERT INTO bloqueios_horarios
        (
            data,
            inicio,
            fim,
            motivo
        )
        VALUES (%s, %s, %s, %s)
    """, (
        data,
        inicio,
        fim,
        motivo
    ))

    conexao.commit()

    cursor.close()
    conexao.close()

    return redirect(
        url_for("admin_horarios")
    )


# ==========================================================
# REMOVER BLOQUEIO
# ==========================================================

@app.route(
    "/admin/horarios/remover/<int:bloqueio_id>",
    methods=["POST"]
)
@login_obrigatorio
def remover_bloqueio(bloqueio_id):

    conexao = conectar_banco()
    cursor = conexao.cursor()

    cursor.execute("""
        DELETE FROM bloqueios_horarios
        WHERE id = %s
    """, (bloqueio_id,))

    conexao.commit()

    cursor.close()
    conexao.close()

    return redirect(
        url_for("admin_horarios")
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
            observacoes,
            status
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

            "observacoes": agendamento[6],

            "status": agendamento[7] or "Confirmado"

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
atualizar_tabela()


# ==========================================================
# INICIA O SERVIDOR LOCAL
# ==========================================================

if __name__ == "__main__":

    app.run(debug=True)
