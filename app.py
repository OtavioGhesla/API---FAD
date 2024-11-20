from flask import Flask, jsonify, request, send_file, Response  
from flask_pymongo import MongoClient                
from flask_cors import CORS                          
from werkzeug.security import generate_password_hash, check_password_hash 
import jwt                                           
import datetime                                      
import io                            
import yaml
from dotenv import load_dotenv
import os
from bson.objectid import ObjectId

load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")
CORS(app, resources={r"/*": {"origins": "*"}}, expose_headers=["Authorization"])

app.config["MONGO_URI"] = os.getenv("MONGO_URI")

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
    dockerfile_content = f"# Dockerfile Gerado\n\nFROM {base_image}\n\n"
    if framework:
        dockerfile_content += f"# Instalar framework de IA\nRUN pip install {framework}\n\n"
    if dependencies:
        dockerfile_content += f"# Instalar dependências adicionais\nRUN pip install {dependencies}\n\n"
    if use_requirements:
        dockerfile_content += "COPY requirements.txt .\nRUN pip install --no-cache-dir -r requirements.txt\n\n"
    if gpu_support:
        dockerfile_content += "RUN apt-get update && apt-get install -y cuda\n\n"
    if env_vars:
        dockerfile_content += "# Variáveis de Ambiente\n" + add_env_vars(env_vars) + "\n\n"
    if ports:
        dockerfile_content += "# Expor portas\n" + add_ports(ports) + "\n\n"
    if startup_script:
        startup_command = '["' + '", "'.join(startup_script.split()) + '"]'
        dockerfile_content += f'CMD {startup_command}\n'

    # Dockerfile em memória
    dockerfile_bytes = io.BytesIO(dockerfile_content.encode('utf-8'))

    # Dados para o banco, se o usuário estiver logado
    if user_id:
        dockerfile_data = {
            "base_image": base_image,
            "framework": framework,
            "dependencies": dependencies,
            "gpu_support": gpu_support,
            "env_vars": env_vars,
            "ports": ports,
            "startup_script": startup_script,
            "use_requirements": use_requirements,
            "created_at": datetime.datetime.utcnow(),
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
    base_image = form_dockercompose.get('baseImage')
    framework = form_dockercompose.get('framework', '').strip()
    dependencies = form_dockercompose.get('dependencies', '').strip()
    gpu_support = form_dockercompose.get('gpuSupport', False)
    env_vars = form_dockercompose.get('envVars', '').strip()
    ports = form_dockercompose.get('ports', '').strip()
    startup_script = form_dockercompose.get('startupScript', '').strip()
    use_requirements = form_dockercompose.get('useRequirements', False)

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
                'image': base_image
            }
        }
    }

    # Adiciona as configurações apenas se houverem valores válidos
    if ports:
        docker_compose_content['services'][service_name]['ports'] = add_ports(ports)
    if env_vars:
        docker_compose_content['services'][service_name]['environment'] = add_env_vars(env_vars)
    if startup_script:
        docker_compose_content['services'][service_name]['command'] = startup_script.split()

    # Adiciona a seção de build apenas se for necessário
    if framework or dependencies or use_requirements:
        docker_compose_content['services'][service_name]['build'] = {
            'context': '.',
            'dockerfile': 'Dockerfile'
        }
        if use_requirements:
            docker_compose_content['services'][service_name].setdefault('volumes', []).append('./requirements.txt:/app/requirements.txt')

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
            "framework": framework,
            "dependencies": dependencies,
            "gpu_support": gpu_support,
            "env_vars": env_vars,
            "ports": ports,
            "startup_script": startup_script,
            "use_requirements": use_requirements,
            "created_at": datetime.datetime.utcnow(),
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

# Rota protegida de exemplo
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

    # Monta o Dockerfile
    dockerfile_content = f"FROM {base_image}\n\n"
    if framework:
        dockerfile_content += f"# Instalar framework de IA\nRUN pip install {framework}\n\n"
    if dependencies:
        dockerfile_content += f"# Instalar dependências adicionais\nRUN pip install {dependencies}\n\n"
    if use_requirements:
        dockerfile_content += "COPY requirements.txt .\nRUN pip install --no-cache-dir -r requirements.txt\n\n"
    if gpu_support:
        dockerfile_content += "RUN apt-get update && apt-get install -y cuda\n\n"
    if env_vars:
        dockerfile_content += "# Variáveis de Ambiente\n" + add_env_vars(env_vars) + "\n\n"
    if ports:
        dockerfile_content += "# Expor portas\n" + add_ports(ports) + "\n\n"
    if startup_script:
        startup_command = '["' + '", "'.join(startup_script.split()) + '"]'
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
                "framework": dockercompose_data.get("framework", ""),
                "dependencies": dockercompose_data.get("dependencies", ""),
                "gpu_support": dockercompose_data.get("gpu_support", False),
                "env_vars": dockercompose_data.get("env_vars", ""),
                "ports": dockercompose_data.get("ports", ""),
                "startup_script": dockercompose_data.get("startup_script", ""),
                "use_requirements": dockercompose_data.get("use_requirements", False),
                "created_at": dockercompose_data.get("created_at", ""),
                "content": dockercompose_data.get("content", "")
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
    base_image = form_data.get('base_image')
    framework = form_data.get('framework', '').strip() or None
    dependencies = form_data.get('dependencies', '').strip() or None
    gpu_support = form_data.get('gpu_support', False)
    env_vars = form_data.get('env_vars', '').strip() or None
    ports = form_data.get('ports', '').strip() or None
    startup_script = form_data.get('startup_script', '').strip() or None
    use_requirements = form_data.get('use_requirements', False)

    # Função auxiliar para configurar variáveis de ambiente
    def add_env_vars(env_vars):
        return {env.split('=')[0].strip(): env.split('=')[1].strip() for env in env_vars.split(',') if '=' in env}

    # Função auxiliar para configurar portas
    def add_ports(ports):
        return [port.strip() for port in ports.split(',') if port.strip()]

    # Cria o conteúdo do docker-compose.yml
    dockercompose_content = {
        'version': '3.8',
        'services': {
            service_name: {
                'image': base_image
            }
        }
    }

    # Adiciona as configurações apenas se houverem valores válidos
    if ports:
        dockercompose_content['services'][service_name]['ports'] = add_ports(ports)
    if env_vars:
        dockercompose_content['services'][service_name]['environment'] = add_env_vars(env_vars)
    if startup_script:
        dockercompose_content['services'][service_name]['command'] = startup_script.split()

    # Adiciona a seção de build apenas se for necessário
    if framework or dependencies or use_requirements:
        dockercompose_content['services'][service_name]['build'] = {
            'context': '.',
            'dockerfile': 'Dockerfile'
        }
        if use_requirements:
            dockercompose_content['services'][service_name].setdefault('volumes', []).append('./requirements.txt:/app/requirements.txt')

    # Adiciona suporte a GPU apenas se necessário
    if gpu_support:
        dockercompose_content['services'][service_name]['runtime'] = 'nvidia'

    # Gera o arquivo docker-compose.yml em memória
    dockercompose_yaml = yaml.dump(dockercompose_content, default_flow_style=False)
    dockercompose_bytes = io.BytesIO(dockercompose_yaml.encode('utf-8'))

    return send_file(dockercompose_bytes, as_attachment=True, download_name="docker-compose.yml", mimetype="text/plain")

if __name__ == '__main__':
    app.run(port=5000, debug=True)
