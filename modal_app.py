import sys
import modal

image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("libpq-dev")
    .uv_pip_install(
        "cognee[postgres]>=1.2.2",
        "fastapi>=0.138.2",
        "langchain-openai>=1.3.3",
        "uvicorn[standard]>=0.49.0",
        "python-dotenv>=1.2.2",
        "psycopg2-binary>=2.9.9",
    )
    .add_local_python_source("app")
)

app = modal.App("rca-agent-backend")


@app.function(
    image=image,
    secrets=[modal.Secret.from_dotenv()],
)
@modal.concurrent(max_inputs=100)
@modal.asgi_app()
def fastapi_app():
    from app.app import app as fastapi_app
    return fastapi_app