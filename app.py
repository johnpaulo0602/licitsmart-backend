import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
from crewai import Agent, Task, Crew, Process
from crewai_tools import PDFSearchTool
from dotenv import load_dotenv
from flask_sqlalchemy import SQLAlchemy

# Configuração do Flask
app = Flask(__name__)
CORS(app)

# Configuração da pasta de uploads
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {'pdf'}

# Configuração do banco de dados
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'postgresql://postgres:postgres@db:5432/postgres')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Modelo do banco de dados
class PDFFile(db.Model):
    __tablename__ = 'pdf_files'
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    data = db.Column(db.LargeBinary, nullable=False)

# Criar as tabelas antes da primeira requisição
@app.before_first_request
def create_tables():
    db.create_all()

# Função para validar o arquivo
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Rota para upload de arquivos
@app.route('/upload', methods=['POST'])
def upload():
    if 'file' not in request.files:
        return jsonify({'error': 'Nenhum arquivo enviado'}), 400

    file = request.files['file']

    if file.filename == '':
        return jsonify({'error': 'Nenhum arquivo selecionado'}), 400

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        # Salva o arquivo na pasta de uploads
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        # Salva no banco de dados
        file.seek(0)
        data = file.read()
        pdf_file = PDFFile(filename=filename, data=data)
        db.session.add(pdf_file)
        db.session.commit()
        return jsonify({'success': 'Arquivo salvo com sucesso!', 'filename': filename}), 200
    else:
        return jsonify({'error': 'Tipo de arquivo não permitido'}), 400

# Rota para listar os arquivos
@app.route('/files', methods=['GET'])
def list_files():
    files = PDFFile.query.all()
    filenames = [file.filename for file in files]
    return jsonify({'files': filenames}), 200

# Rota para processar o PDF
@app.route('/process', methods=['POST'])
def process_pdf():
    # Receber o nome do arquivo do PDF
    data = request.get_json()
    filename = data.get('filename')

    if not filename:
        return jsonify({'error': 'Nome do arquivo não fornecido'}), 400

    # Localizar o PDF na pasta de uploads
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if not os.path.exists(file_path):
        return jsonify({'error': 'Arquivo não encontrado'}), 404

    # Processar o PDF usando o script fornecido
    try:
        # Carregar as variáveis de ambiente
        load_dotenv()
        os.environ['OPENAI_API_KEY'] = os.getenv("OPENAI_API_KEY")

        # Aqui, inclua o conteúdo real das variáveis
        solicitacoes = """
        \n<solicitacoes>\n
        1 - OBJETIVOS - Identificação dos Objetivos: Realize uma análise cuidadosa do conteúdo do trabalho para extrair os objetivos principais. Resuma esses objetivos em um parágrafo claro e conciso, capturando a essência das metas e intenções do estudo.\n
        2 - GAP - Identificação do GAP: Analise o conteúdo do trabalho para identificar o GAP científico que ele aborda, mesmo que não esteja explicitamente mencionado. Formule um parágrafo conciso, focando em destacar a questão central que o estudo procura resolver ou elucidar.\n
        3 - METODOLOGIA - Extração Detalhada da Metodologia do Trabalho: Identificação e Descrição da Metodologia: Proceda com uma análise minuciosa do trabalho para identificar a metodologia utilizada. Detalhe cada aspecto da metodologia, incluindo o desenho do estudo, as técnicas e ferramentas empregadas, os procedimentos de coleta e análise de dados, os passos do método e quaisquer metodologias específicas ou inovadoras adotadas. Formule uma descrição compreensiva em texto corrido, limitando-se a um máximo de 250 palavras para manter a concisão sem sacrificar detalhes importantes.\n
        4 - DATASET - Identifique os datasets usados no trabalho. Descreva-os brevemente em texto corrido, limitando-se a 40 palavras. Quero somente o nome dos dataset na mesma linha e separados por virgula. Se o dataset foi criado pelos autores escreve "OWN DATASET"\n
        5 - RESULTADOS - Escreva em um parágrafo os resultados obitidos estudo dando enfase a dados quantitativos, quero dados numéricos explicitamente. Nesse paragrafo também dê enfase a comparação ao melhor trabalho anterior em relação ao trabalho proposto. Não use superlativos. Deixe o tom neuro e científico.\n
        6 - LIMITAÇÕES - Produza um texto parafraseado das limitações do trabalho.\n
        7 - CONCLUSÃO - Resuma as conclusões dos autores em relação ao trabalho.\n
        8 - FUTURO - Extraia as Recomendações para Pesquisa Futura: Aponte recomendações para futuras investigações baseadas nas conclusões do artigo.\n
        9 - AVALIAÇÃO - Faça uma avalição crítica ao trabalho. Não seja generalista faça uma crítica aprofundada.\n
        </solicitacoes>\n
        """

        controles = """
        \n<controle>\n
        NÍVEIS DE CONTROLE:\n
        1. Entonação:Formal Científico.\n
        2. Foco de Tópico: Você deve reponder sempre com alto foco no texto do artigo científico.\n
        3. Língua: Responda sempre em Português do Brasil como os Brasileiros costumam escrever textos científicos aderindo aos padrões de redação científica do país a não ser o que será especificado para não traduzir.\n
        4. Controle de Sentimento: Neutro e científico. Evite superlativos como: inovador, revolucionário e etc\n
        5. Nível Originalidade: 10, onde 1 é pouco original e 10 é muito original. Em hipótese alguma copie frases do texto original.\n
        6. Nível de Abstração: 1, onde 1 é muito concreto e real e 10 é muito abstrado e irreal.\n
        7. Tempo Verbal: Escreva no passado.\n
        </controle>\n
        """

        restricoes = """
        \n<restricoes>\n
        O QUE NÃO DEVE SER TRADUZIDO DO INGLÊS PARA PORTUGUÊS:\n
        1. Termos técnicos em inglês amplamente aceitos e usado nos textos em português. \n
        2. Nome de algoritmos de machine learning.\n
        3. Métricas usadas no trabalho.\n
        4. Nome dos datasets.\n
        5. Não envolva o retorno do YAML com ```yaml. \n
        6. Não coloque ``` nem ´´´ no texto de retorno. \n
        </restricoes>\n
        """

        # Modelo de referência para o YAML
        template = """
        \n<template>\n
        ARTIGO:\n
        - ARQUIVO: "nome do arquivo.pdf"\n
        - OBJETIVOS: "Objetivo geral e específicos"\n
        - GAP: "Gap científico"\n
        - METODOLOGIA: "Metodologia"\n
        - DATASET: "Datasets utilizados"\n
        - RESULTADOS: "Resultados do artigo"\n
        - LIMITAÇÕES: "Limitações do artigo científico"\n
        - CONCLUSÃO: "Conclusões"\n
        - AVALIAÇÃO: "Análise do artigo"\n
        </template>\n
        """

        # Criar os agentes e tarefas
        gpt = ChatOpenAI(model="gpt-4-turbo")
        pdf_tool = PDFSearchTool(file_path)
        agent_leitor = Agent(
            role='PDF Reader',
            goal="Ler PDFs e extrair informações específicas conforme definido nas solicitações em <solicitacoes>. "
                 "Gerar um YAML de acordo com o modelo especificado em <template>. {solicitacoes} {template}.",
            backstory="Você é um especialista em leitura e análise de artigos científicos. "
                      "Sua missão é extrair informações cruciais, compreendendo o contexto semântico completo dos artigos. "
                      "Sua função é fundamental para avaliar a relevância dos artigos analisados. "
                      "Ao responder às solicitações delimitadas por <solicitacoes></solicitacoes>, "
                      "você deve levar em consideração as definições de controles em <controle></controle> "
                      "e as restrições em <restrições></restrições>. "
                      "{solicitacoes} {template} {restricoes} {controles}",
            tools=[pdf_tool],
            verbose=True,
            memory=False,
            llm=gpt
        )
        task_leitor = Task(
            description="Leia o PDF e responda em YAML às solicitações definidas em <solicitacoes> "
                        "usando o modelo definido em <template>. "
                        "{solicitacoes} {template}",
            expected_output="YAML com as respostas às solicitações definidas em "
                            "<solicitacoes>, usando o modelo definido em <template>.",
            agent=agent_leitor
        )

        agent_revisor = Agent(
            role='Revisor',
            goal="Leia os dados extraídos pelo Agente Revisor e verifique se um YAML foi produzido "
                 "de acordo com o template proposto em <template>, "
                 "com os dados solicitados em <solicitacoes>. "
                 "Como resultado do seu trabalho, você deve retornar um YAML "
                 "revisado no mesmo formato do template proposto. {solicitacoes} {template}",
            backstory="Você é um especialista na revisão de informações em YAML, "
                      "especialmente de resumos de artigos científicos. "
                      "Sua função é garantir que os dados extraídos reflitam "
                      "com precisão as solicitações definidas em <solicitacoes> "
                      "e estejam formatados conforme o template proposto em <template>. "
                      "Sua atenção aos detalhes assegura que os resultados finais "
                      "sejam precisos e conformes às expectativas. {solicitacoes} {template}",
            verbose=True,
            memory=False,
            llm=gpt
        )
        task_revisor = Task(
            description="Revise o YAML produzido pelo agente leitor para garantir que ele esteja de acordo com o template definido em <template> "
                        "e contenha todas as informações solicitadas em <solicitacoes>. {solicitacoes} {template}",
            expected_output="YAML revisado que esteja de acordo com o template definido em <template> "
                            "e contenha todas as informações solicitadas em <solicitacoes>. {solicitacoes} {template}",
            agent=agent_revisor
        )

        crew = Crew(
            agents=[agent_leitor, agent_revisor],
            tasks=[task_leitor, task_revisor],
            process=Process.sequential
        )

        # Kickoff do processo
        ipt = {
            'solicitacoes': solicitacoes,
            'template': template,
            'restricoes': restricoes,
            'controles': controles
        }

        results = crew.kickoff(inputs=ipt)

        # Extrair a saída como string
        output_str = str(results)

        return jsonify({'success': 'PDF processado com sucesso!', 'results': output_str}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    # Ajuste o host para '0.0.0.0' para que o Docker possa expor a porta corretamente
    app.run(debug=True, host='0.0.0.0')
