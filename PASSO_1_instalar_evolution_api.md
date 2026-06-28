# Passo 1 — Instalar Evolution API com Docker

## O que você vai precisar
- Computador com Windows 10/11, Mac ou Linux
- 15 minutos

---

## 1. Instalar o Docker Desktop

Acesse e baixe: **https://www.docker.com/products/docker-desktop/**

Instale normalmente e abra o Docker Desktop. Espere aparecer o ícone de baleia verde na barra de tarefas.

---

## 2. Criar a pasta do projeto

Crie uma pasta no seu computador chamada `evolution-api`, por exemplo em `C:\evolution-api` (Windows) ou `~/evolution-api` (Mac/Linux).

---

## 3. Criar o arquivo docker-compose.yml

Dentro da pasta `evolution-api`, crie um arquivo chamado `docker-compose.yml` com o seguinte conteúdo:

```yaml
version: '3.8'

services:
  evolution-api:
    image: atendai/evolution-api:latest
    container_name: evolution_api
    restart: always
    ports:
      - "8080:8080"
    environment:
      - SERVER_URL=http://localhost:8080
      - AUTHENTICATION_TYPE=apikey
      - AUTHENTICATION_API_KEY=minha-chave-secreta-123
      - AUTHENTICATION_EXPOSE_IN_FETCH_INSTANCES=true
      - LOG_LEVEL=ERROR
      - DEL_INSTANCE=false
      - STORE_MESSAGES=true
      - STORE_MESSAGE_UP=true
      - STORE_CONTACTS=true
      - STORE_CHATS=true
    volumes:
      - evolution_store:/evolution/store
      - evolution_instances:/evolution/instances

volumes:
  evolution_store:
  evolution_instances:
```

> **Importante:** Anote a chave `minha-chave-secreta-123` — você vai usar ela nos scripts.
> Pode trocar por qualquer senha de sua preferência.

---

## 4. Iniciar a Evolution API

Abra o **Terminal** (Mac/Linux) ou **Prompt de Comando / PowerShell** (Windows), navegue até a pasta e rode:

```bash
cd C:\evolution-api
docker-compose up -d
```

Aguarde o download (primeira vez pode demorar ~2 minutos). Quando terminar, acesse:

**http://localhost:8080**

Se aparecer uma tela da Evolution API, funcionou!

---

## 5. Criar uma instância e conectar seu WhatsApp

### Via interface web (mais fácil):

Acesse: **http://localhost:8080/manager**

1. Clique em **"Create Instance"**
2. Nome da instância: `corretor-maringa`
3. Clique em **"Create"**
4. Clique em **"Connect"** → aparecerá um QR Code
5. Abra o WhatsApp no celular → **Dispositivos Conectados → Conectar Dispositivo**
6. Escaneie o QR Code

Pronto! Seu WhatsApp está conectado à API.

---

## 6. Testar se está funcionando

Acesse no navegador (substitua pela sua chave):

```
http://localhost:8080/instance/fetchInstances
```

Com o header `apikey: minha-chave-secreta-123`

Ou use o Swagger (documentação interativa) em:

**http://localhost:8080/docs**

---

## Próximos passos

Com a API rodando, execute o script `extrair_contatos_grupo.py` para puxar os contatos do grupo.
