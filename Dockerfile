# Use a imagem base do Python 3.9 slim
FROM python:3.9-slim

# Define o diretório de trabalho
WORKDIR /app

# Copia o arquivo requirements.txt
COPY requirements.txt .

# Instala as dependências
RUN pip install --no-cache-dir -r requirements.txt

# Copia o restante da aplicação
COPY . .

# Expõe a porta que o Flask usa
EXPOSE 5000

# Comando para iniciar a aplicação
CMD ["python", "app.py"]
