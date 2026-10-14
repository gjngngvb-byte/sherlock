# Sherlock Web 🔎

Interface web em português para pesquisar usernames em plataformas públicas usando o mecanismo open source [Sherlock](https://github.com/sherlock-project/sherlock).

## Recursos
- Busca por username com validação
- Filtro opcional por plataforma
- Indicador de execução e resultados com links
- Histórico local no navegador
- Exportação CSV
- API FastAPI e endpoint de saúde

> **Uso responsável:** resultados não confirmam identidade. Um username igual em sites diferentes não prova que as contas pertencem à mesma pessoa. Use apenas fontes públicas, respeite termos de uso e leis aplicáveis.

## Executar localmente
Requer Python 3.11+ e conexão com a internet para consultar as plataformas.

```bash
python -m venv .venv
# macOS/Linux
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Abra http://127.0.0.1:8000.

## Docker
```bash
docker build -t sherlock-web .
docker run --rm -p 8000:8000 sherlock-web
```

## Publicar no Render
1. Conecte este repositório ao Render.
2. Selecione **New → Blueprint**.
3. O Render detecta `render.yaml` e configura o serviço Docker.
4. Após o deploy, verifique `/api/health`.

Planos gratuitos podem dormir após inatividade e ter limites de CPU, memória e duração. A disponibilidade do plano depende das regras atuais do provedor. Hospedagem estática sozinha não executa o Sherlock.

## API
- `GET /api/health`
- `POST /api/search` com JSON `{"username":"exemplo","timeout":15,"sites":[]}`

## Limitações e segurança
Esta é uma base para uso pessoal/demonstração, não um serviço multiusuário endurecido para produção. Antes de abrir publicamente, adicione autenticação, rate limiting, limites de concorrência, monitoramento e proteção contra abuso. Os resultados são mantidos em memória e se perdem ao reiniciar o processo.

## Licença
A interface deste repositório é MIT. Sherlock é um projeto independente com seus próprios termos e autoria; consulte o repositório upstream.