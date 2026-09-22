from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from datetime import datetime, date, timedelta
import os
import psycopg2
from functools import wraps
import uuid
import json


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
# SERVIÇOS
# ==========================================================

SERVICOS = {
    "Esmaltação simples": {
        "duracao": 30,
        "preco": 30.00
    },

    "Esmaltação em Gel": {
        "duracao": 90,
        "preco": 50.00
    },

    "Blindagem de unhas": {
        "duracao": 60,
        "preco": 30.00
    },

    "Alongamento de unhas": {
        "duracao": 120,
        "preco": 60.00
    },

    "Plano mensal": {
        "duracao": 90,
        "preco": 150.00
    }
}


# ==========================================================
# DURAÇÃO DO SERVIÇO
# ==========================================================

def obter_duracao(servico):

    dados = SERVICOS.get(servico)

    if dados:
        return dados["duracao"]

    return 30


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
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            grupo_plano TEXT,
            numero_plano INTEGER
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

    # ==========================================================
    # BLOQUEIOS POR INTERVALO
    # ==========================================================

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

    cursor.execute("""
        ALTER TABLE bloqueios_horarios
        ALTER COLUMN periodo DROP NOT NULL
    """)

    # ==========================================================
    # CONVERTE BLOQUEIOS ANTIGOS
    # ==========================================================

    cursor.execute("""
        UPDATE bloqueios_horarios
        SET
            inicio = '07:30',
            fim = '11:00',
            motivo = COALESCE(motivo, 'Bloqueio antigo')
        WHERE periodo = 'manha'
          AND inicio IS NULL
          AND fim IS NULL
    """)

    cursor.execute("""
        UPDATE bloqueios_horarios
        SET
            inicio = '13:30',
            fim = '20:00',
            motivo = COALESCE(motivo, 'Bloqueio antigo')
        WHERE periodo = 'tarde'
          AND inicio IS NULL
          AND fim IS NULL
    """)

    cursor.execute("""
        UPDATE bloqueios_horarios
        SET
            inicio = '00:00',
            fim = '23:59',
            motivo = COALESCE(motivo, 'Bloqueio antigo')
        WHERE periodo = 'dia'
          AND inicio IS NULL
          AND fim IS NULL
    """)

    # ==========================================================
    # STATUS
    # ==========================================================

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

    # ==========================================================
    # CAMPOS DO PLANO MENSAL
    # ==========================================================

    cursor.execute("""
        ALTER TABLE agendamentos
        ADD COLUMN IF NOT EXISTS grupo_plano TEXT
    """)

    cursor.execute("""
        ALTER TABLE agendamentos
        ADD COLUMN IF NOT EXISTS numero_plano INTEGER
    """)

    conexao.commit()

    cursor.close()
    conexao.close()


# ==========================================================
# HORÁRIOS DE FUNCIONAMENTO
# ==========================================================

def obter_periodos(data_agendamento):

    dia_semana = data_agendamento.weekday()

    # Domingo
    if dia_semana == 6:
        return []

    # Segunda, terça, quinta e sexta
    if dia_semana in [0, 1, 3, 4]:

        return [
            ("07:30", "11:00"),
            ("13:30", "20:00")
        ]

    # Quarta
    if dia_semana == 2:

        return [
            ("07:30", "11:00"),
            ("13:30", "15:00")
        ]

    # Sábado
    if dia_semana == 5:

        return [
            ("09:00", "16:00")
        ]

    return []


# ==========================================================
# VERIFICAR SE O HORÁRIO ESTÁ DENTRO DO FUNCIONAMENTO
# ==========================================================

def horario_dentro_do_funcionamento(
    data_agendamento,
    horario,
    duracao
):

    try:

        periodos = obter_periodos(
            data_agendamento
        )

        inicio_agendamento = datetime.combine(
            data_agendamento,
            datetime.strptime(
                horario,
                "%H:%M"
            ).time()
        )

        fim_agendamento = (
            inicio_agendamento
            + timedelta(minutes=duracao)
        )

    except (ValueError, TypeError):

        return False


    for inicio, fim in periodos:

        inicio_periodo = datetime.combine(
            data_agendamento,
            datetime.strptime(
                inicio,
                "%H:%M"
            ).time()
        )

        fim_periodo = datetime.combine(
            data_agendamento,
            datetime.strptime(
                fim,
                "%H:%M"
            ).time()
        )

        # O atendimento precisa terminar
        # dentro do período de funcionamento.

        if (
            inicio_agendamento >= inicio_periodo
            and fim_agendamento <= fim_periodo
        ):

            return True

    return False


# ==========================================================
# VERIFICAR CONFLITO COM OUTRO AGENDAMENTO
# ==========================================================

def existe_conflito_agendamento(
    cursor,
    data_agendamento,
    horario,
    duracao
):

    cursor.execute("""
        SELECT
            id,
            horario,
            servico
        FROM agendamentos
        WHERE data = %s
          AND status <> 'Cancelado'
    """, (data_agendamento,))

    agendamentos = cursor.fetchall()

    novo_inicio = datetime.combine(
        data_agendamento,
        datetime.strptime(
            horario,
            "%H:%M"
        ).time()
    )

    novo_fim = (
        novo_inicio
        + timedelta(minutes=duracao)
    )

    for agendamento in agendamentos:

        horario_existente = agendamento[1]

        inicio_existente = datetime.combine(
            data_agendamento,
            horario_existente
        )

        duracao_existente = obter_duracao(
            agendamento[2]
        )

        fim_existente = (
            inicio_existente
            + timedelta(minutes=duracao_existente)
        )

        # Verifica sobreposição real.

        if (
            novo_inicio < fim_existente
            and novo_fim > inicio_existente
        ):

            return True

    return False


# ==========================================================
# VERIFICAR CONFLITO COM BLOQUEIO
# ==========================================================

def existe_conflito_bloqueio(
    cursor,
    data_agendamento,
    horario,
    duracao
):

    cursor.execute("""
        SELECT
            inicio,
            fim,
            motivo
        FROM bloqueios_horarios
        WHERE data = %s
          AND inicio IS NOT NULL
          AND fim IS NOT NULL
    """, (data_agendamento,))

    bloqueios = cursor.fetchall()

    novo_inicio = datetime.combine(
        data_agendamento,
        datetime.strptime(
            horario,
            "%H:%M"
        ).time()
    )

    novo_fim = (
        novo_inicio
        + timedelta(minutes=duracao)
    )

    for bloqueio in bloqueios:

        inicio_bloqueio = datetime.combine(
            data_agendamento,
            bloqueio[0]
        )

        fim_bloqueio = datetime.combine(
            data_agendamento,
            bloqueio[1]
        )

        # Verifica sobreposição real.

        if (
            novo_inicio < fim_bloqueio
            and novo_fim > inicio_bloqueio
        ):

            return bloqueio

    return None


# ==========================================================
# VALIDAR UM HORÁRIO
# ==========================================================

def validar_horario(
    cursor,
    data_agendamento,
    horario,
    servico
):

    try:

        data_obj = datetime.strptime(
            data_agendamento,
            "%Y-%m-%d"
        ).date()

        datetime.strptime(
            horario,
            "%H:%M"
        )

    except (ValueError, TypeError):

        return "Data ou horário inválido."


    duracao = obter_duracao(
        servico
    )


    # ------------------------------------------------------
    # FUNCIONAMENTO
    # ------------------------------------------------------

    if not horario_dentro_do_funcionamento(
        data_obj,
        horario,
        duracao
    ):

        return (
            "Este horário está fora "
            "do horário de atendimento."
        )


    # ------------------------------------------------------
    # OUTRO AGENDAMENTO
    # ------------------------------------------------------

    if existe_conflito_agendamento(
        cursor,
        data_obj,
        horario,
        duracao
    ):

        return "Este horário já está ocupado."


    # ------------------------------------------------------
    # BLOQUEIO
    # ------------------------------------------------------

    bloqueio = existe_conflito_bloqueio(
        cursor,
        data_obj,
        horario,
        duracao
    )

    if bloqueio:

        return (
            f"Este horário está bloqueado "
            f"das {bloqueio[0].strftime('%H:%M')} "
            f"às {bloqueio[1].strftime('%H:%M')}."
        )


    return None


# ==========================================================
# PÁGINA INICIAL
# ==========================================================

@app.route("/")
def inicio():

    return render_template(
        "index.html"
    )


# ==========================================================
# PÁGINA DE AGENDAMENTO
# ==========================================================

@app.route(
    "/agendar",
    methods=["GET", "POST"]
)
def agendar():

    if request.method == "POST":

        nome = request.form.get(
            "nome"
        )

        telefone = request.form.get(
            "telefone"
        )

        servico = request.form.get(
            "servico"
        )

        data = request.form.get(
            "data"
        )

        horario = request.form.get(
            "horario"
        )

        observacoes = request.form.get(
            "observacoes"
        )


        # ==================================================
        # VERIFICAR DADOS BÁSICOS
        # ==================================================

        if (
            not nome
            or not telefone
            or not servico
            or not data
        ):

            return render_template(
                "agendar.html",
                erro=(
                    "Preencha todos os "
                    "campos obrigatórios."
                )
            )


        if servico not in SERVICOS:

            return render_template(
                "agendar.html",
                erro="Serviço inválido."
            )


        # ==================================================
        # CONECTAR BANCO
        # ==================================================

        conexao = conectar_banco()
        cursor = conexao.cursor()


        try:

            # ==================================================
            # PLANO MENSAL
            # ==================================================

            if servico == "Plano mensal":

                # --------------------------------------------------
                # RECEBER OS 4 HORÁRIOS DO HTML
                # --------------------------------------------------

                horarios_plano_raw = request.form.get(
                    "horarios_plano"
                )


                horarios_plano = []


                if horarios_plano_raw:

                    try:

                        horarios_plano = json.loads(
                            horarios_plano_raw
                        )

                    except (
                        ValueError,
                        TypeError
                    ):

                        horarios_plano = []


                # --------------------------------------------------
                # GARANTIR QUE SEJA UMA LISTA
                # --------------------------------------------------

                if not isinstance(
                    horarios_plano,
                    list
                ):

                    horarios_plano = []


                # --------------------------------------------------
                # COMPATIBILIDADE COM HTML ANTIGO
                # --------------------------------------------------

                if not horarios_plano:

                    if not horario:

                        conexao.rollback()

                        return render_template(
                            "agendar.html",
                            erro=(
                                "Escolha um horário "
                                "para o plano mensal."
                            )
                        )


                    horarios_plano = [
                        horario,
                        horario,
                        horario,
                        horario
                    ]


                # --------------------------------------------------
                # PRECISA TER EXATAMENTE 4
                # --------------------------------------------------

                if len(horarios_plano) != 4:

                    conexao.rollback()

                    return render_template(
                        "agendar.html",
                        erro=(
                            "O plano mensal precisa "
                            "ter 4 horários."
                        )
                    )


                # --------------------------------------------------
                # DATA INICIAL
                # --------------------------------------------------

                try:

                    data_inicial = datetime.strptime(
                        data,
                        "%Y-%m-%d"
                    ).date()

                except (
                    ValueError,
                    TypeError
                ):

                    conexao.rollback()

                    return render_template(
                        "agendar.html",
                        erro="Data inválida."
                    )


                # --------------------------------------------------
                # GERAR AS 4 DATAS
                # --------------------------------------------------

                datas_plano = [

                    data_inicial,

                    data_inicial
                    + timedelta(days=7),

                    data_inicial
                    + timedelta(days=14),

                    data_inicial
                    + timedelta(days=21)

                ]


                # --------------------------------------------------
                # IDENTIFICADOR ÚNICO DO PLANO
                # --------------------------------------------------

                grupo_plano = str(
                    uuid.uuid4()
                )


                # --------------------------------------------------
                # VALIDAR OS 4 ATENDIMENTOS
                # --------------------------------------------------

                erros_plano = []


                for indice in range(4):

                    data_atendimento = (
                        datas_plano[indice]
                    )

                    horario_atendimento = (
                        horarios_plano[indice]
                    )


                    # Garantir que o horário
                    # seja texto.

                    if not isinstance(
                        horario_atendimento,
                        str
                    ):

                        erros_plano.append(
                            f"{indice + 1}º atendimento "
                            f"possui horário inválido."
                        )

                        continue


                    erro = validar_horario(
                        cursor,
                        data_atendimento.strftime(
                            "%Y-%m-%d"
                        ),
                        horario_atendimento,
                        servico
                    )


                    if erro:

                        erros_plano.append(
                            f"{indice + 1}º atendimento "
                            f"("
                            f"{data_atendimento.strftime('%d/%m/%Y')}"
                            f" às "
                            f"{horario_atendimento}"
                            f"): "
                            f"{erro}"
                        )


                # --------------------------------------------------
                # SE ALGUM FALHAR, NÃO SALVA NENHUM
                # --------------------------------------------------

                if erros_plano:

                    conexao.rollback()

                    return render_template(
                        "agendar.html",
                        erro=(
                            "Não foi possível reservar "
                            "o plano mensal. "
                            + " ".join(erros_plano)
                        )
                    )


                # --------------------------------------------------
                # SALVAR OS 4 AGENDAMENTOS
                # --------------------------------------------------

                ids_criados = []


                for indice in range(4):

                    cursor.execute("""
                        INSERT INTO agendamentos
                        (
                            nome,
                            telefone,
                            servico,
                            data,
                            horario,
                            observacoes,
                            status,
                            grupo_plano,
                            numero_plano
                        )
                        VALUES (
                            %s,
                            %s,
                            %s,
                            %s,
                            %s,
                            %s,
                            %s,
                            %s,
                            %s
                        )
                        RETURNING id
                    """, (
                        nome,
                        telefone,
                        servico,
                        datas_plano[indice],
                        horarios_plano[indice],
                        observacoes,
                        "Confirmado",
                        grupo_plano,
                        indice + 1
                    ))


                    novo_id = cursor.fetchone()[0]


                    ids_criados.append(
                        novo_id
                    )


                conexao.commit()


                # --------------------------------------------------
                # LOG
                # --------------------------------------------------

                print(
                    "\n=============================="
                )

                print(
                    "NOVO PLANO MENSAL"
                )

                print(
                    "=============================="
                )

                print(
                    "Nome:",
                    nome
                )

                print(
                    "Telefone:",
                    telefone
                )

                print(
                    "Grupo:",
                    grupo_plano
                )


                for indice in range(4):

                    print(
                        f"{indice + 1}º atendimento:",
                        datas_plano[indice].strftime(
                            "%d/%m/%Y"
                        ),
                        horarios_plano[indice]
                    )


                print(
                    "IDs:",
                    ids_criados
                )

                print(
                    "STATUS: Confirmado"
                )

                print(
                    "PLANO MENSAL SALVO "
                    "NO POSTGRESQL"
                )

                print(
                    "==============================\n"
                )


                                # --------------------------------------------------
                # PREPARAR DADOS PARA CONFIRMAÇÃO
                # --------------------------------------------------

                atendimentos_plano = []

                for indice in range(4):

                    atendimentos_plano.append({

                        "numero": indice + 1,

                        "data": datas_plano[indice].strftime(
                            "%d/%m/%Y"
                        ),

                        "horario": horarios_plano[indice]

                    })

                return render_template(
                    "confirmacao.html",
                    nome=nome,
                    telefone=telefone,
                    servico=servico,
                    data_formatada=data_inicial.strftime(
                        "%d/%m/%Y"
                    ),
                    horario=horarios_plano[0],
                    observacoes=observacoes,
                    plano_mensal=True,
                    atendimentos_plano=atendimentos_plano
                )


            # ==================================================
            # SERVIÇOS NORMAIS
            # ==================================================

            erro = validar_horario(
                cursor,
                data,
                horario,
                servico
            )


            if erro:

                conexao.rollback()

                return render_template(
                    "agendar.html",
                    erro=erro
                )


            # --------------------------------------------------
            # SALVAR AGENDAMENTO NORMAL
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
                VALUES (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s
                )
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


            # --------------------------------------------------
            # LOG
            # --------------------------------------------------

            print(
                "\n=============================="
            )

            print(
                "NOVO AGENDAMENTO"
            )

            print(
                "=============================="
            )

            print(
                "Nome:",
                nome
            )

            print(
                "Telefone:",
                telefone
            )

            print(
                "Serviço:",
                servico
            )

            print(
                "Data:",
                data
            )

            print(
                "Horário:",
                horario
            )

            print(
                "Observações:",
                observacoes
            )

            print(
                "Status: Confirmado"
            )

            print(
                "AGENDAMENTO SALVO "
                "NO POSTGRESQL"
            )

            print(
                "==============================\n"
            )


            # --------------------------------------------------
            # FORMATAR DATA
            # --------------------------------------------------

            data_formatada = datetime.strptime(
                data,
                "%Y-%m-%d"
            ).strftime(
                "%d/%m/%Y"
            )


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


        except Exception as erro:

            conexao.rollback()

            print(
                "ERRO AO SALVAR AGENDAMENTO:",
                erro
            )

            return render_template(
                "agendar.html",
                erro=(
                    "Não foi possível concluir "
                    "o agendamento. "
                    "Tente novamente."
                )
            )


        finally:

            cursor.close()
            conexao.close()


    return render_template(
        "agendar.html"
    )


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

            "inicio":
                resultado[0].strftime(
                    "%H:%M"
                ),

            "fim":
                resultado[1].strftime(
                    "%H:%M"
                ),

            "motivo":
                resultado[2] or ""

        })


    return jsonify(
        bloqueios
    )


# ==========================================================
# PROTEÇÃO DO PAINEL ADMINISTRATIVO
# ==========================================================

def login_obrigatorio(funcao):

    @wraps(funcao)
    def verificar_login(
        *args,
        **kwargs
    ):

        if not session.get(
            "admin_logado"
        ):

            return redirect(
                url_for("login")
            )

        return funcao(
            *args,
            **kwargs
        )

    return verificar_login


# ==========================================================
# LOGIN ADMINISTRATIVO
# ==========================================================

@app.route(
    "/login",
    methods=["GET", "POST"]
)
def login():

    if request.method == "POST":

        usuario = request.form.get(
            "usuario"
        )

        senha = request.form.get(
            "senha"
        )

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
            erro=(
                "Usuário ou senha incorretos."
            )
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
            status,
            grupo_plano,
            numero_plano
        FROM agendamentos
        ORDER BY data ASC, horario ASC
    """)

    resultados = cursor.fetchall()

    cursor.close()
    conexao.close()

    agendamentos = []


    for agendamento in resultados:

        agendamentos.append({

            "id":
                agendamento[0],

            "nome":
                agendamento[1],

            "telefone":
                agendamento[2],

            "servico":
                agendamento[3],

            "data":
                agendamento[4].strftime(
                    "%d/%m/%Y"
                ),

            "horario":
                agendamento[5].strftime(
                    "%H:%M"
                ),

            "observacoes":
                agendamento[6],

            "status":
                agendamento[7]
                or "Confirmado",

            "grupo_plano":
                agendamento[8],

            "numero_plano":
                agendamento[9]

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
def cancelar_agendamento(
    agendamento_id
):

    conexao = conectar_banco()
    cursor = conexao.cursor()

    cursor.execute("""
        UPDATE agendamentos
        SET status = 'Cancelado'
        WHERE id = %s
    """, (
        agendamento_id,
    ))

    conexao.commit()

    cursor.close()
    conexao.close()

    return redirect(
        url_for(
            "admin_agendamentos"
        )
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

            "id":
                bloqueio[0],

            "data":
                bloqueio[1].strftime(
                    "%d/%m/%Y"
                ),

            "inicio":
                bloqueio[2].strftime(
                    "%H:%M"
                ),

            "fim":
                bloqueio[3].strftime(
                    "%H:%M"
                ),

            "motivo":
                bloqueio[4]
                or "Sem motivo"

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

    data = request.form.get(
        "data"
    )

    inicio = request.form.get(
        "inicio"
    )

    fim = request.form.get(
        "fim"
    )

    motivo = request.form.get(
        "motivo"
    )


    # ------------------------------------------------------
    # VERIFICAR CAMPOS
    # ------------------------------------------------------

    if (
        not data
        or not inicio
        or not fim
    ):

        return redirect(
            url_for(
                "admin_horarios"
            )
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
            url_for(
                "admin_horarios"
            )
        )


    # ------------------------------------------------------
    # HORÁRIO FINAL PRECISA SER MAIOR
    # ------------------------------------------------------

    if fim_obj <= inicio_obj:

        return redirect(
            url_for(
                "admin_horarios"
            )
        )


    # ------------------------------------------------------
    # CONECTAR BANCO
    # ------------------------------------------------------

    conexao = conectar_banco()
    cursor = conexao.cursor()


    # ------------------------------------------------------
    # VERIFICAR BLOQUEIO SOBREPOSTO
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
            url_for(
                "admin_horarios"
            )
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
        VALUES (
            %s,
            %s,
            %s,
            %s
        )
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
        url_for(
            "admin_horarios"
        )
    )


# ==========================================================
# REMOVER BLOQUEIO
# ==========================================================

@app.route(
    "/admin/horarios/remover/<int:bloqueio_id>",
    methods=["POST"]
)
@login_obrigatorio
def remover_bloqueio(
    bloqueio_id
):

    conexao = conectar_banco()
    cursor = conexao.cursor()

    cursor.execute("""
        DELETE FROM bloqueios_horarios
        WHERE id = %s
    """, (
        bloqueio_id,
    ))

    conexao.commit()

    cursor.close()
    conexao.close()

    return redirect(
        url_for(
            "admin_horarios"
        )
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

    telefone = request.args.get(
        "telefone"
    )


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
            status,
            grupo_plano,
            numero_plano
        FROM agendamentos
        WHERE telefone = %s
        ORDER BY data ASC, horario ASC
    """, (
        telefone,
    ))

    resultados = cursor.fetchall()

    cursor.close()
    conexao.close()


    # ------------------------------------------------------
    # TRANSFORMAR RESULTADOS
    # ------------------------------------------------------

    agendamentos = []


    for agendamento in resultados:

        agendamentos.append({

            "id":
                agendamento[0],

            "nome":
                agendamento[1],

            "telefone":
                agendamento[2],

            "servico":
                agendamento[3],

            "data":
                agendamento[4].strftime(
                    "%d/%m/%Y"
                ),

            "horario":
                agendamento[5].strftime(
                    "%H:%M"
                ),

            "observacoes":
                agendamento[6],

            "status":
                agendamento[7]
                or "Confirmado",

            "grupo_plano":
                agendamento[8],

            "numero_plano":
                agendamento[9]

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

    app.run(
        debug=True
    )
