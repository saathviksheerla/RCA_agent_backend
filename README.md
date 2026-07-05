# Cloud Incident Memory & RCA Engine

Still in development phase ...

---

## Setup

```bash
uv sync
# Rename .env.example to .env
uv run main.py
```
**Important**: Make sure to fill in the .env file with the correct values. i am using GROK (https://console.groq.com/keys) and Gemini (https://aistudio.google.com/app/apikey) for embedding only.

open `http://localhost:8000/docs`

## Endpoints

### `POST /incidents`

create an incident. backend pulls similar past incidents from Cognee, feeds them to LLM, gets back root cause + confidence + fix + first action, stores everything, remembers it in Cognee.

**why:** this is where the main thingy happens. new incident → recall memory → reason → remember.

### `GET /incidents`

list all incidents stored locally.

**why:** you need to see what's happened.

### `GET /incidents/{id}`

get one incident details.

**why:** drill into a specific incident.

### `POST /incidents/{id}/resolve`

confirm the actual fix that worked. backend updates the incident, re-remembers it in Cognee with the confirmed root cause + fix, then calls `improve()` so Cognee's knowledge graph gets richer.

**why:** this is how the system gets smarter. without this, Cognee never learns if the predicted RCA was right.

## How it works (Cognee deep-dive)

this is NOT a chatbot or a monitoring dashboard. this is institutional memory.

### `cognee.remember()`

converts an incident into text, stores it in Cognee's vector database. on resolve, remembers again with the confirmed fix so the stored memory gets better over time.

### `cognee.recall()`

takes the new incident's service, environment, and symptoms, builds a query, and finds similar historical incidents. returns text chunks from past incidents. this is what the LLM uses as context.

### `cognee.improve()`

called only on resolve. enriches the knowledge graph with the confirmed root cause + fix. this makes future `recall()` results more relevant because Cognee now knows which incident patterns were actually correct.

### the order matters

we intentionally call `recall()` BEFORE `remember()` on create. otherwise Cognee might return the incident you just inserted as a "similar" incident. flow:

```
create → recall() [get history] → LLM reasons → remember() [store] → respond
resolve → remember() [update] → improve() [enrich] → respond
```

### tech stack

- **Cognee SDK v1.2.2** — memory layer
- **FastAPI** — backend
- **LangChain Groq** — LLM calls
- **Groq API** — inference
- **In-memory list** — local store (no postgres, no redis, no auth, no docker. mvp.)

### project structure

```
app/
  api.py               # routes
  schemas/incident.py  # pydantic models
  action/
    remember_incident.py       # cognee.remember()
    recall_similar_incidents.py # cognee.recall()
    generate_rca.py            # LLM reasoning
  services/
    incident_service.py  # business logic
```

### the philosophy

Cognee stores memory. Cognee retrieves memory. Cognee does NOT perform RCA. OpenAI reasons. Cognee provides context. one function, one responsibility, never mix them.

### Architecture Diagram
<img src="images/architecture.png" alt="Project Architecture" width="500">

## Testing examples

paste these in Swagger UI at `http://localhost:8000/docs`

### Create incident

incident 1
```json
{
  "title": "API gateway timeout on payment service",
  "severity": "high",
  "service": "payment-gateway",
  "environment": "production",
  "symptoms": "users getting 504 errors when checking out. p99 latency spiked from 200ms to 12s. error rate jumped to 34%."
}
```

incident 2
```json
{
  "title": "CDN cache invalidation failure",
  "severity": "high",
  "service": "cdn-edge",
  "environment": "production",
  "symptoms": "stale assets served to users. cache purge requests failing with 502. image load times increased 300%."
}
```
incident 3 (let's test with this one)
```json
{
  "title": "Order processing queue backpressure",
  "severity": "critical",
  "service": "order-service",
  "environment": "production",
  "symptoms": "orders stuck in pending state. rabbitmq queue depth at 50k. consumer pod OOM kills recurring."
}
```
you'll get back the incident + predicted RCA. copy the `id` from the response.

### Resolve incident

replace `{id}` with the actual id from create response.

```json
{
  "fix_applied": "Increased connection pool from 50 to 200 and added circuit breaker for downstream billing service"
}
```

### Finally testing recall

create a 4th incident with similar symptoms to incident 3 to test recall
```json
{
  "title": "Payment service degraded after deploy",
  "severity": "high",
  "service": "payment-gateway",
  "environment": "production",
  "symptoms": "transactions failing with 502 after new deployment. latency spikes from 100ms to 8s."
}
```

**Check the response**, the `recalled_from` field should show similar incidents from your previous ones.
### List incidents

`GET /incidents` — no body needed. just hit it.

### Get one incident

`GET /incidents/{id}` — put the id in the path. no body.
