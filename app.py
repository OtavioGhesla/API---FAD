from flask import Flask, jsonify, request, send_file, Response  
from flask_pymongo import MongoClient                
from flask_cors import CORS                          
from werkzeug.security import generate_password_hash, check_password_hash 
import jwt                                           
import datetime                                      
import io                            
import yaml
import os
from bson.objectid import ObjectId

app = Flask(__name__)
app.config["SECRET_KEY"] = "127319762836dbybxqtvxf65143cxv1gzv897xercre8x1csfqx1r6cx81e"
CORS(app, resources={r"/*": {"origins": "*"}}, expose_headers=["Authorization"])

app.config["MONGO_URI"] = "mongodb+srv://otaviofetterg:XK3vyzB91lTOPrTS@fad.vikvn.mongodb.net/fad?retryWrites=true&w=majority&appName=fad"

# Testa a conexão com o banco MongoDB
try:
    client = MongoClient(app.config["MONGO_URI"])
    mongo = client["fad"]
    print("Conectado ao banco MongoDB")
except Exception as e:
    print(f"Erro ao conectar ao MongoDB: {e}")

@app.route('/createDockerfile', methods=['POST'])
def createDockerfile():
    form_dockerfile = request.get_json()

    # Verificação do Token
    token = request.headers.get("Authorization")
    user_id = None  # Inicializa a variável que armazenará o ID do usuário

    if token:
        try:
            # Decodificando o token JWT
            decoded_token = jwt.decode(token.split(" ")[1], app.config["SECRET_KEY"], algorithms=["HS256"])
            user_id = decoded_token["user_id"]
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
            print ("Token inválido ou expirado"), 401

    # Recebe os valores do JSON
    base_image = form_dockerfile.get('baseImage')
    workdir = form_dockerfile.get('workdir')
    framework = form_dockerfile.get('framework', '').strip() or None
    dependencies = form_dockerfile.get('dependencies', '').strip() or None
    gpu_support = form_dockerfile.get('gpuSupport', False)
    env_vars = form_dockerfile.get('envVars', '').strip() or None
    ports = form_dockerfile.get('ports', '').strip() or None
    startup_script = form_dockerfile.get('startupScript', '').strip() or None
    use_requirements = form_dockerfile.get('useRequirements', False)

    # Funções auxiliares
    def add_env_vars(env_vars):
        return "\n".join([f"ENV {env.strip()}" for env in env_vars.split(',') if env.strip()])

    def add_ports(ports):
        return "\n".join([f"EXPOSE {port.strip()}" for port in ports.split(',') if port.strip()])

    # Monta o Dockerfile
    dockerfile_content = f"# Dockerfile Gerado\n\n# Imagem base\nFROM {base_image}\n\n"

    # Instalar o APT e Python, se necessário
    if base_image not in ["python:latest", "nvidia/cuda:11.8-cudnn8-devel-ubuntu20.04"]:
        dockerfile_content += "# Atualizar o APT\nRUN apt-get update && \\\n    apt-get install -y python3 python3-pip && \\\n    apt-get clean && rm -rf /var/lib/apt/lists/*\n\n"

    # Definir o diretório de trabalho, se fornecido
    if workdir:
        dockerfile_content += f"# Setando o ambiente de trabalho\nWORKDIR {workdir}\n\n"

    # Instalar dependências adicionais, se fornecidas
    if dependencies:
        dockerfile_content += f"# Instalar dependências adicionais\nRUN python3 -m pip install {dependencies}\n\n"

    # Copiar e instalar do requirements.txt, se solicitado
    if use_requirements:
        dockerfile_content += f"# Copiando o requirements.txt\nCOPY requirements.txt {workdir}/requirements.txt\n\n"
        dockerfile_content += f"# Instalando dependências do requirements.txt\nRUN python3 -m pip install --no-cache-dir -r {workdir}/requirements.txt\n\n"

    # Instalar framework de IA, se especificado
    if framework:
        dockerfile_content += f"# Instalar framework de IA\nRUN python3 -m pip install {framework}\n\n"

    dockerfile_content += f"# Copia os arquivos do diretório\nCOPY . .\n\n"

    # Instalar CUDA, se GPU estiver habilitado
    if gpu_support not in["nvidia/cuda:11.8-cudnn8-devel-ubuntu20.04"]:
        dockerfile_content += "# Instalando o CUDA\n"
        dockerfile_content += "RUN wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2004/x86_64/cuda-keyring_1.0-1_all.deb && \\\n    dpkg -i cuda-keyring_1.0-1_all.deb && apt-get update && \\\n    apt-get install -y cuda && \\\n    apt-get clean && rm -rf /var/lib/apt/lists/*\n\n"

    # Adicionar variáveis de ambiente, se fornecidas
    if env_vars:
        dockerfile_content += "# Variáveis de Ambiente\n"
        dockerfile_content += add_env_vars(env_vars) + "\n\n"

    # Expor portas, se fornecido
    if ports:
        dockerfile_content += "# Expor portas\n"
        dockerfile_content += add_ports(ports) + "\n\n"

    # Definir o comando de inicialização, se fornecido
    if startup_script:
        startup_command = '# Comando para iniciar a aplicação \n["' + '", "'.join(startup_script.split()) + '"]'
        dockerfile_content += f'CMD {startup_command}\n'

    # Dockerfile em memória
    dockerfile_bytes = io.BytesIO(dockerfile_content.encode('utf-8'))

    # Dados para o banco, se o usuário estiver logado
    if user_id:
        dockerfile_data = {
            "base_image": base_image,
            "workdir": workdir,
            "framework": framework,
            "dependencies": dependencies,
            "gpu_support": gpu_support,
            "env_vars": env_vars,
            "ports": ports,
            "startup_script": startup_script,
            "use_requirements": use_requirements,
            "created_at": datetime.datetime.now(datetime.timezone.utc),
            "user_id": user_id
        }
        # Remove campos nulos ou vazios antes de salvar
        dockerfile_data = {key: value for key, value in dockerfile_data.items() if value not in [None, '', [], {}]}
        # Salva o Dockerfile no banco de dados se o usuário estiver logado
        dockerfile_id = mongo["dockerfile"].insert_one({
            "content": dockerfile_data,
        }).inserted_id

    # Retorna o Dockerfile gerado para download
    return send_file(dockerfile_bytes, as_attachment=True, download_name="Dockerfile", mimetype="text/plain")

@app.route('/createDockerCompose', methods=['POST'])
def createDockerCompose():
    form_dockercompose = request.get_json()

    # Recebe os valores do JSON
    service_name = form_dockercompose.get('service')
    base_image = form_dockercompose.get('baseImage', '')
    workdir = form_dockercompose.get('workdir', '')
    gpu_support = form_dockercompose.get('gpuSupport', False)
    env_vars = form_dockercompose.get('envVars', '').strip()
    ports = form_dockercompose.get('ports', '').strip()
    startup_script = form_dockercompose.get('startupScript', '').strip()
    use_requirements = form_dockercompose.get('useRequirements', False)
    use_dockerfile = form_dockercompose.get('useDockerfile', False)
    context = form_dockercompose.get('context', '')

    # Função auxiliar para configurar variáveis de ambiente
    def add_env_vars(env_vars):
        return {env.split('=')[0].strip(): env.split('=')[1].strip() for env in env_vars.split(',') if '=' in env}

    # Função auxiliar para configurar portas
    def add_ports(ports):
        return [port.strip() for port in ports.split(',') if port.strip()]

    # Cria o conteúdo do docker-compose.yml
    docker_compose_content = {
        'version': '3.8',
        'services': {
            service_name: {
            }
        }
    }

    # Adiciona as configurações apenas se houverem valores válidos
    if base_image and not use_dockerfile:
        docker_compose_content['services'][service_name]['image'] = base_image
    if workdir and not use_dockerfile:
        docker_compose_content['services'][service_name]['working_dir'] = workdir
    if ports:
        docker_compose_content['services'][service_name]['ports'] = add_ports(ports)
    if env_vars:
        docker_compose_content['services'][service_name]['environment'] = add_env_vars(env_vars)
    if startup_script:
        docker_compose_content['services'][service_name]['command'] = startup_script.split()

    # Adiciona a seção de build apenas se for necessário
    if use_dockerfile:
        docker_compose_content['services'][service_name]['build'] = {
            'context': context,
            'dockerfile': 'Dockerfile'
        }

    # Adiciona suporte a GPU apenas se necessário
    if gpu_support:
        docker_compose_content['services'][service_name]['runtime'] = 'nvidia'

    # Gera o arquivo docker-compose.yml em memória
    docker_compose_yaml = yaml.dump(docker_compose_content, default_flow_style=False)
    docker_compose_bytes = io.BytesIO(docker_compose_yaml.encode('utf-8'))

    # Verificação do Token
    token = request.headers.get("Authorization")
    user_id = None

    if token:
        try:
            # Decodificando o token JWT
            decoded_token = jwt.decode(token.split(" ")[1], app.config["SECRET_KEY"], algorithms=["HS256"])
            user_id = decoded_token["user_id"]
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
            print("Token inválido ou expirado")

    # Dados para o banco, se o usuário estiver logado
    if user_id:
        dockercompose_data = {
            "service_name": service_name,
            "base_image": base_image,
            "use_dockerfile": use_dockerfile,
            "workdir": workdir,
            "gpu_support": gpu_support,
            "env_vars": env_vars,
            "ports": ports,
            "startup_script": startup_script,
            "context": context,
            "created_at": datetime.datetime.now(datetime.timezone.utc),
            "user_id": user_id
        }
        # Remove campos nulos ou vazios antes de salvar
        dockercompose_data = {key: value for key, value in dockercompose_data.items() if value not in [None, '', [], {}]}
        # Salva o Docker Compose no banco de dados se o usuário estiver logado
        dockercompose_id = mongo["dockercompose"].insert_one({
            "content": dockercompose_data,
        }).inserted_id

    # Envia o arquivo para download
    return send_file(docker_compose_bytes, as_attachment=True, download_name="docker-compose.yml", mimetype="text/plain")

@app.route('/register', methods=['POST'])
def register_user():
    # Recebe os valores do JSON
    data = request.get_json()
    name = data.get("name")
    password = data.get("password")

    # Procura se já existe um usuário com o mesmo nome cadastrado
    if mongo["user"].find_one({"name": name}):
        return jsonify({"error": "Esse nome de usuário já está cadastrado"}), 409

    # Criptografa a senha
    hashed_password = generate_password_hash(password)

    # Salva o usuário e a senha criptografada no banco
    user_id = mongo["user"].insert_one({
        "name": name,
        "password": hashed_password
    }).inserted_id

    return jsonify({"message": "Usuário cadastrado com sucesso", "user_id": str(user_id)}), 201

# Rota de login com geração de JWT
@app.route('/login', methods=['POST'])
def login_user():
    data = request.get_json()
    name = data.get("name")
    password = data.get("password")

    user = mongo["user"].find_one({"name": name})

    if user and check_password_hash(user["password"], password):
        # Criação do token JWT com expiração de 1 hora
        token = jwt.encode({
            "user_id": str(user["_id"]),
            "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=1)
        }, app.config["SECRET_KEY"], algorithm="HS256")

        return jsonify({"message": "Login bem-sucedido", "token": token}), 200
    else:
        return jsonify({"error": "Nome de usuário ou senha incorretos"}), 401

# Rota protegida
@app.route('/protected', methods=['GET'])
def protected_route():
    token = request.headers.get("Authorization")

    if not token:
        return jsonify({"error": "Token ausente"}), 403

    try:
        # Decodificar o token
        decoded_token = jwt.decode(token, app.config["SECRET_KEY"], algorithms=["HS256"])
        return jsonify({"message": "Acesso autorizado", "user_id": decoded_token["user_id"]}), 200
    except jwt.ExpiredSignatureError:
        return jsonify({"error": "Token expirado"}), 401
    except jwt.InvalidTokenError:
        return jsonify({"error": "Token inválido"}), 401

@app.route('/dockerfileHistory', methods=['GET'])
def dockerfile_history():
    token = request.headers.get("Authorization")

    if not token:
        return jsonify({"error": "Token ausente"}), 403

    try:
        # Decodificar o token para obter o user_id
        decoded_token = jwt.decode(token.split(" ")[1], app.config["SECRET_KEY"], algorithms=["HS256"])
        user_id = decoded_token["user_id"]
    except jwt.ExpiredSignatureError:
        return jsonify({"error": "Token expirado"}), 401
    except jwt.InvalidTokenError:
        return jsonify({"error": "Token inválido"}), 401

    try:
        # Buscar Dockerfiles no banco de dados para o user_id
        dockerfiles = mongo["dockerfile"].find({"content.user_id": user_id})

        # Transformar os resultados em uma lista
        history = []
        for dockerfile in dockerfiles:
            dockerfile_data = dockerfile["content"]

            # Adiciona o _id ao dockerfile, mas não o exibe para o usuário
            dockerfile_data["_id"] = str(dockerfile["_id"])

            # Remover o user_id do retorno para não exibir para o usuário
            dockerfile_data["user_id"] = str(dockerfile_data.get("user_id"))

            # Organizando as informações
            dockerfile_data = {
                "_id": str(dockerfile["_id"]),
                "base_image": dockerfile_data.get("base_image", ""),
                "workdir": dockerfile_data.get("workdir", ""),
                "framework": dockerfile_data.get("framework", ""),
                "dependencies": dockerfile_data.get("dependencies", ""),
                "gpu_support": dockerfile_data.get("gpu_support", False),
                "env_vars": dockerfile_data.get("env_vars", ""),
                "ports": dockerfile_data.get("ports", ""),
                "startup_script": dockerfile_data.get("startup_script", ""),
                "use_requirements": dockerfile_data.get("use_requirements", False),
                "created_at": dockerfile_data.get("created_at", ""),
                "content": dockerfile_data.get("content", "")
            }

            history.append(dockerfile_data)

        return jsonify({"message": "Histórico recuperado com sucesso", "history": history}), 200
    except Exception as e:
        return jsonify({"error": f"Erro ao recuperar histórico: {str(e)}"}), 500

@app.route('/dockerfileHistoryDelete', methods=['DELETE'])
def dockerfile_history_delete():
    token = request.headers.get("Authorization")
    data = request.get_json()
    dockerfile_id = data.get("_id")

    if not token:
        return jsonify({"error": "Token ausente"}), 403

    try:
        # Decodificar o token para obter o user_id
        decoded_token = jwt.decode(token.split(" ")[1], app.config["SECRET_KEY"], algorithms=["HS256"])
        user_id = decoded_token["user_id"]
        print(f"User ID decodificado: {user_id}")  # Log para verificar o user_id
    except jwt.ExpiredSignatureError:
        return jsonify({"error": "Token expirado"}), 401
    except jwt.InvalidTokenError:
        return jsonify({"error": "Token inválido"}), 401

    try:
        # Verificar se o Dockerfile pertence ao usuário antes de excluir
        dockerfile_id_obj = ObjectId(dockerfile_id)  # Converte a string _id para um ObjectId
        print(f"Tentando excluir Dockerfile com ID: {dockerfile_id_obj}")  # Log para verificar o ID do Dockerfile
        result = mongo["dockerfile"].delete_one({
            "_id": dockerfile_id_obj,
            "content.user_id": user_id
        })

        if result.deleted_count == 0:
            return jsonify({"error": "Dockerfile não encontrado ou não pertence ao usuário"}), 404

        return jsonify({"message": "Dockerfile excluído com sucesso"}), 200
    except Exception as e:
        return jsonify({"error": f"Erro ao excluir Dockerfile: {str(e)}"}), 500

@app.route('/createDockerfileHistory', methods=['POST'])
def create_dockerfile_history():
    form_data = request.get_json()

    # Verificação do Token
    token = request.headers.get("Authorization")
    user_id = None  # Inicializa a variável que armazenará o ID do usuário

    if token:
        try:
            # Decodificando o token JWT
            decoded_token = jwt.decode(token.split(" ")[1], app.config["SECRET_KEY"], algorithms=["HS256"])
            user_id = decoded_token["user_id"]
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
            return "Token inválido ou expirado", 401

    # Recebe as informações do Dockerfile
    base_image = form_data.get('base_image')
    workdir = form_data.get('workdir')
    framework = form_data.get('framework', '').strip() or None
    dependencies = form_data.get('dependencies', '').strip() or None
    gpu_support = form_data.get('gpu_support', False)
    env_vars = form_data.get('env_vars', '').strip() or None
    ports = form_data.get('ports', '').strip() or None
    startup_script = form_data.get('startup_script', '').strip() or None
    use_requirements = form_data.get('use_requirements', False)

    # Funções auxiliares
    def add_env_vars(env_vars):
        return "\n".join([f"ENV {env.strip()}" for env in env_vars.split(',') if env.strip()])

    def add_ports(ports):
        return "\n".join([f"EXPOSE {port.strip()}" for port in ports.split(',') if port.strip()])

    # Funções auxiliares
    def add_env_vars(env_vars):
        return "\n".join([f"ENV {env.strip()}" for env in env_vars.split(',') if env.strip()])

    def add_ports(ports):
        return "\n".join([f"EXPOSE {port.strip()}" for port in ports.split(',') if port.strip()])

    # Monta o Dockerfile
    dockerfile_content = f"# Dockerfile Gerado\n\nFROM {base_image}\n\n"

    # Instalar o APT e Python, se necessário
    if base_image not in ["python:latest", "nvidia/cuda:11.8-cudnn8-devel-ubuntu20.04"]:
        dockerfile_content += "# Atualizar o APT\nRUN apt-get update && \\\n    apt-get install -y python3 python3-pip && \\\n    apt-get clean && rm -rf /var/lib/apt/lists/*\n\n"

    # Definir o diretório de trabalho, se fornecido
    if workdir:
        dockerfile_content += f"# Setando o ambiente de trabalho\nWORKDIR {workdir}\n\n"

    # Instalar dependências adicionais, se fornecidas
    if dependencies:
        dockerfile_content += f"# Instalar dependências adicionais\nRUN python3 -m pip install {dependencies}\n\n"

    # Copiar e instalar do requirements.txt, se solicitado
    if use_requirements:
        dockerfile_content += f"# Copiando o requirements.txt\nCOPY requirements.txt {workdir}/requirements.txt\n\n"
        dockerfile_content += f"# Instalando dependências do requirements.txt\nRUN python3 -m pip install --no-cache-dir -r {workdir}/requirements.txt\n\n"

    # Instalar framework de IA, se especificado
    if framework:
        dockerfile_content += f"# Instalar framework de IA\nRUN python3 -m pip install {framework}\n\n"

    dockerfile_content += f"# Copia os arquivos do diretório\nCOPY . .\n\n"

    # Instalar CUDA, se GPU estiver habilitado
    if gpu_support not in["nvidia/cuda:11.8-cudnn8-devel-ubuntu20.04"]:
        dockerfile_content += "# Instalando o CUDA\n"
        dockerfile_content += "RUN wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2004/x86_64/cuda-keyring_1.0-1_all.deb && \\\n    dpkg -i cuda-keyring_1.0-1_all.deb && apt-get update && \\\n    apt-get install -y cuda && \\\n    apt-get clean && rm -rf /var/lib/apt/lists/*\n\n"

    # Adicionar variáveis de ambiente, se fornecidas
    if env_vars:
        dockerfile_content += "# Variáveis de Ambiente\n"
        dockerfile_content += add_env_vars(env_vars) + "\n\n"

    # Expor portas, se fornecido
    if ports:
        dockerfile_content += "# Expor portas\n"
        dockerfile_content += add_ports(ports) + "\n\n"

    # Definir o comando de inicialização, se fornecido
    if startup_script:
        startup_command = '# Comando para iniciar a aplicação \n["' + '", "'.join(startup_script.split()) + '"]'
        dockerfile_content += f'CMD {startup_command}\n'

    # Enviar o Dockerfile como um arquivo para o frontend
    return Response(dockerfile_content, mimetype='text/plain', headers={"Content-Disposition": "attachment;filename=Dockerfile"})

@app.route('/dockerComposeHistory', methods=['GET'])
def dockercompose_history():
    token = request.headers.get("Authorization")

    if not token:
        return jsonify({"error": "Token ausente"}), 403

    try:
        # Decodificar o token para obter o user_id
        decoded_token = jwt.decode(token.split(" ")[1], app.config["SECRET_KEY"], algorithms=["HS256"])
        user_id = decoded_token["user_id"]
    except jwt.ExpiredSignatureError:
        return jsonify({"error": "Token expirado"}), 401
    except jwt.InvalidTokenError:
        return jsonify({"error": "Token inválido"}), 401

    try:
        # Buscar Docker Compose no banco de dados para o user_id
        dockercomposes = mongo["dockercompose"].find({"content.user_id": user_id})

        # Transformar os resultados em uma lista
        history = []
        for dockercompose in dockercomposes:
            dockercompose_data = dockercompose["content"]

            # Adiciona o _id ao dockerfile, mas não o exibe para o usuário
            dockercompose_data["_id"] = str(dockercompose["_id"])

            # Remover o user_id do retorno para não exibir para o usuário
            dockercompose_data["user_id"] = str(dockercompose_data.get("user_id"))

            # Organizando as informações
            dockercompose_data = {
                "_id": str(dockercompose["_id"]),
                "service_name": dockercompose_data.get("service_name", ""),
                "base_image": dockercompose_data.get("base_image", ""),
                "use_dockerfile": dockercompose_data.get("use_dockerfile", False),
                "workdir": dockercompose_data.get("workdir", ""),
                "gpu_support": dockercompose_data.get("gpu_support", False),
                "env_vars": dockercompose_data.get("env_vars", ""),
                "ports": dockercompose_data.get("ports", ""),
                "startup_script": dockercompose_data.get("startup_script", ""),
                "context": dockercompose_data.get("context", ""),
                "created_at": dockercompose_data.get("created_at", ""),
            }

            history.append(dockercompose_data)

        return jsonify({"message": "Histórico recuperado com sucesso", "history": history}), 200
    except Exception as e:
        return jsonify({"error": f"Erro ao recuperar histórico: {str(e)}"}), 500

@app.route('/dockerComposeHistoryDelete', methods=['DELETE'])
def dockercompose_history_delete():
    token = request.headers.get("Authorization")
    data = request.get_json()
    dockercompose_id = data.get("_id")

    if not token:
        return jsonify({"error": "Token ausente"}), 403

    try:
        # Decodificar o token para obter o user_id
        decoded_token = jwt.decode(token.split(" ")[1], app.config["SECRET_KEY"], algorithms=["HS256"])
        user_id = decoded_token["user_id"]
        print(f"User ID decodificado: {user_id}")  # Log para verificar o user_id
    except jwt.ExpiredSignatureError:
        return jsonify({"error": "Token expirado"}), 401
    except jwt.InvalidTokenError:
        return jsonify({"error": "Token inválido"}), 401

    try:
        # Verificar se o Dockerfile pertence ao usuário antes de excluir
        dockercompose_id_obj = ObjectId(dockercompose_id)  # Converte a string _id para um ObjectId
        print(f"Tentando excluir Docker Compose com ID: {dockercompose_id_obj}")  # Log para verificar o ID do Dockerfile
        result = mongo["dockercompose"].delete_one({
            "_id": dockercompose_id_obj,
            "content.user_id": user_id
        })

        if result.deleted_count == 0:
            return jsonify({"error": "Docker Compose não encontrado ou não pertence ao usuário"}), 404

        return jsonify({"message": "Docker Compose excluído com sucesso"}), 200
    except Exception as e:
        return jsonify({"error": f"Erro ao excluir Docker Compose: {str(e)}"}), 500
    
@app.route('/createDockerComposeHistory', methods=['POST'])
def create_dockercompose_history():
    form_data = request.get_json()

    # Verificação do Token
    token = request.headers.get("Authorization")
    user_id = None  # Inicializa a variável que armazenará o ID do usuário

    if token:
        try:
            # Decodificando o token JWT
            decoded_token = jwt.decode(token.split(" ")[1], app.config["SECRET_KEY"], algorithms=["HS256"])
            user_id = decoded_token["user_id"]
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
            return "Token inválido ou expirado", 401

    # Recebe as informações do Dockerfile
    service_name = form_data.get('service_name')
    base_image = form_data.get('base_image', '')
    use_dockerfile = form_data.get('use_dockerfile', False)
    workdir = form_data.get('workdir', '')
    gpu_support = form_data.get('gpu_support', False)
    env_vars = form_data.get('env_vars', '').strip() or None
    ports = form_data.get('ports', '').strip() or None
    context = form_data.get('context', '')
    startup_script = form_data.get('startup_script', '').strip() or None

    print(f"Service Name Recebido: {service_name}")

    # Função auxiliar para configurar variáveis de ambiente
    def add_env_vars(env_vars):
        return {env.split('=')[0].strip(): env.split('=')[1].strip() for env in env_vars.split(',') if '=' in env}

    # Função auxiliar para configurar portas
    def add_ports(ports):
        return [port.strip() for port in ports.split(',') if port.strip()]

    # Cria o conteúdo do docker-compose.yml
    docker_compose_content = {
        'version': '3.8',
        'services': {
            service_name: {
            }
        }
    }

    # Adiciona as configurações apenas se houverem valores válidos
    if base_image and not use_dockerfile:
        docker_compose_content['services'][service_name]['image'] = base_image
    if workdir and not use_dockerfile:
        docker_compose_content['services'][service_name]['working_dir'] = workdir
    if ports:
        docker_compose_content['services'][service_name]['ports'] = add_ports(ports)
    if env_vars:
        docker_compose_content['services'][service_name]['environment'] = add_env_vars(env_vars)
    if startup_script:
        docker_compose_content['services'][service_name]['command'] = startup_script.split()

    # Adiciona a seção de build apenas se for necessário
    if use_dockerfile:
        docker_compose_content['services'][service_name]['build'] = {
            'context': context,
            'dockerfile': 'Dockerfile'
        }

    # Adiciona suporte a GPU apenas se necessário
    if gpu_support:
        docker_compose_content['services'][service_name]['runtime'] = 'nvidia'

    # Gera o arquivo docker-compose.yml em memória
    dockercompose_yaml = yaml.dump(docker_compose_content, default_flow_style=False)
    dockercompose_bytes = io.BytesIO(dockercompose_yaml.encode('utf-8'))

    return send_file(dockercompose_bytes, as_attachment=True, download_name="docker-compose.yml", mimetype="text/plain")

if __name__ == '__main__':
    app.run(port=5000, debug=True)
