# Interview Preparation & Architecture Notes

This document provides clear, concise, and structured answers to all core design questions, architectural decisions, and trade-offs regarding the **Bulk Certificate Generator API**. Use this guide to explain the project naturally and confidently during an SDE interview.

---

### 1. Why FastAPI?
- **Asynchronous Throughput**: Built on Starlette and ASGI, FastAPI handles concurrent network connections efficiently without blocking worker threads.
- **Native Pydantic v2 Integration**: Incoming request payloads are validated automatically with strict data types, length limits, and regex patterns before hitting route logic.
- **Automatic OpenAPI Documentation**: Generates interactive Swagger (`/docs`) and ReDoc (`/redoc`) specifications directly from Python schemas.
- **Clean Dependency Injection**: Manages database sessions cleanly (`Depends(get_db)`), ensuring sessions are opened and disposed of reliably, and allowing effortless test database overrides.

---

### 2. Why SQLAlchemy?
- **Type Safety**: SQLAlchemy 2.0 uses type-annotated `Mapped` attributes and `mapped_column`, preventing runtime type bugs and ensuring static analysis works properly.
- **Multi-Dialect Abstraction**: Decouples application logic from specific SQL dialects. The application runs on SQLite for development and tests, and switches to PostgreSQL in production simply by setting `DATABASE_URL`.
- **Relational Integrity**: Automatically enforces foreign keys, cascades (`ondelete="CASCADE"`), and transaction commit/rollback boundaries.

---

### 3. Why a relational database?
The domain requires strong relational consistency and ACID guarantees:
- A strict **one-to-many parent-child relationship** exists between `GenerationJob` and `Certificate`.
- **ACID guarantees**: As certificates are rendered, counters (`successful_count`, `failed_count`) and statuses must be updated consistently without dirty reads or corrupted state.
- Relational tables allow straightforward indexing on `job_id`, `status`, and recipient emails.

---

### 4. Why SQLite?
- **Zero Configuration**: Requires no external server process, credentials, or network setup.
- **Frictionless Local Development & Testing**: An interviewer or evaluator can clone the repo and run the app or tests immediately without starting Docker or installing database servers.
- **Fast Ephemeral Testing**: Tests can create and dispose of lightweight isolated SQLite databases in milliseconds.

---

### 5. Why PostgreSQL?
- **Production Concurrency**: PostgreSQL supports multi-process concurrency with row-level locking (MVCC), which SQLite cannot handle under high write loads.
- **Enterprise Reliability**: Robust connection pooling, high availability, point-in-time recovery, and distributed deployment.
- **Docker Compose Integration**: The project includes a pre-configured PostgreSQL 15 service in `docker-compose.yml`, proving production readiness.

---

### 6. Why ReportLab?
- **Pure Python PDF Engine**: Generates vector-based PDF documents without heavy external system dependencies (such as Chromium, Puppeteer, or wkhtmltopdf).
- **Lightweight Output**: Generates crisp, high-resolution vector PDFs that are tiny in size (~2.5 KB per certificate).
- **Precise Layout Control**: Provides pixel-perfect coordinate placement for decorative multi-layer borders, headlines, recipient text, and vector medallions.

---

### 7. Why BackgroundTasks?
- **Simplicity Without Infrastructure Overhead**: For this assignment, FastAPI's built-in `BackgroundTasks` executes asynchronous jobs in the background without needing Redis, Celery, RabbitMQ, or worker processes.
- **Responsive API**: Prevents client HTTP timeouts by returning immediately while generating PDFs asynchronously.
- **No Overengineering**: Keeps the codebase self-contained, easy to run, and simple for an intern to explain.

---

### 8. Why HTTP 202 Accepted?
- **Standard REST Semantics**: RFC 9110 specifies `202 Accepted` for requests that have been validated and accepted for processing, but where batch processing is not yet complete.
- **Immediate Response**: The client immediately receives a `job_id` and tracking metadata, avoiding open connection starvation.

---

### 9. How does bulk processing work?
1. The client sends `POST /api/v1/certificates/generate` with event metadata and an array of recipients.
2. Pydantic validates the request structure (bounds, emails, ISO dates).
3. The API creates a `GenerationJob` (status `PENDING`) and child `Certificate` records (status `PENDING`) in a single database transaction.
4. The API dispatches `process_generation_job` to `BackgroundTasks` and returns `202 Accepted` with `job_id`.
5. The background worker fetches the pending certificates and iterates through them sequentially, generating each PDF and updating the database after each certificate.

---

### 10. How is progress calculated?
Progress is dynamically computed using the persisted counts in `GenerationJob`:
$$\text{processed} = \text{successful\_count} + \text{failed\_count}$$
$$\text{pending} = \max(0, \text{total\_count} - \text{processed})$$
$$\text{progress\_percentage} = \operatorname{round}\left(\frac{\text{processed}}{\text{total\_count}} \times 100.0, 2\right)$$
Because the background processor commits status updates after each certificate, clients polling `GET /jobs/{id}` see real-time increments in `progress_percentage`.

---

### 11. What happens when one certificate fails?
**Failure Isolation Rule**: The generation loop wraps every individual recipient in an isolated `try/except` block:
- If certificate #5 fails (e.g., rendering issue):
  - Certificate #5 is marked `FAILED` with `error_message` stored in the database.
  - `job.failed_count` is incremented.
  - The loop continues immediately to recipient #6 and subsequent certificates.
- At the end of the job:
  - If all succeed: Job is marked `COMPLETED`.
  - If some succeed and some fail: Job is marked `COMPLETED_WITH_ERRORS`.
  - If all fail: Job is marked `FAILED`.

---

### 12. How is path traversal prevented?
During file retrieval (`GET /certificates/{id}`):
1. The stored `file_path` is resolved to an absolute path.
2. The [validate_safe_path](file:///c:/Users/vijet/OneDrive/DSATM/oops/DL/CNS/Bulk%20Certificate%20Generator/app/utils/file_utils.py#L40) utility asserts that the resolved path is strictly located within `settings.certificates_dir_path` using Python's `Path.relative_to()`.
3. If an attacker tampers with a path (e.g., `../../etc/passwd` or `/etc/passwd`), `validate_safe_path` catches the escape and returns `HTTP 400 Bad Request`.
4. No raw filesystem paths are ever returned in API response bodies.

---

### 13. How would this scale to 100,000 certificates?
1. **Batch Partitioning (Chunking)**: Break the 100,000 batch into smaller tasks of 200–500 recipients.
2. **Distributed Queue (Celery + RabbitMQ / AWS SQS)**: Publish chunk tasks onto a distributed queue.
3. **Autoscaling Fleet**: Run dozens of worker containers (on Kubernetes or ECS) consuming tasks in parallel.
4. **Cloud Object Storage (AWS S3 / GCS)**: Workers upload generated PDFs directly to S3.
5. **Database Optimization**: Bulk insert rows using SQLAlchemy `bulk_insert_mappings` or `insert().values([...])` to avoid 100,000 individual insert roundtrips.

---

### 14. Why would Celery/SQS be better at scale?
- **Crash Durability**: Tasks in Celery/SQS persist in Redis or RabbitMQ. If a server restarts, tasks are not lost.
- **Worker Isolation**: Workers run in dedicated processes or separate machines, preventing heavy CPU/PDF rendering from starving the web server.
- **Built-in Resilience**: Dead-letter queues, exponential backoff retries, and task rate-limiting.

---

### 15. How would S3 be used in production?
1. Instead of local disk storage, the generator streams PDF bytes directly to an S3 bucket (e.g., `s3://company-bucket/certificates/job_1/cert_42.pdf`).
2. The database stores the S3 URI/key in `Certificate.file_path`.
3. When a client requests `GET /certificates/{id}`, the API generates an **S3 Pre-signed URL** (valid for 15 minutes) and returns an HTTP `307 Temporary Redirect`.
4. This offloads PDF download bandwidth completely to AWS CloudFront/S3, eliminating load on our API servers.

---

### 16. What happens if the server crashes during processing?
- In the current implementation with `BackgroundTasks`, uncompleted jobs would remain in `PROCESSING` status because memory tasks are not persistent across process restarts.
- **Production Recovery**:
  1. A startup recovery job or cron checks for jobs stuck in `PROCESSING` whose `started_at` is older than a timeout threshold (e.g., 10 minutes).
  2. The system re-enqueues only the certificates still marked `PENDING`.
  3. With Celery/SQS, task acknowledgments (ACKs) handle this automatically: unacknowledged tasks are re-delivered to surviving workers.

---

### 17. What are the limitations of this implementation?
- **Single-Node BackgroundTasks**: Background processing runs within the web server process; very large batches share CPU with HTTP requests.
- **Local Disk Storage**: PDFs are written to local disk (`generated_certificates/`), requiring volume mounts in Docker.
- **Polling Model**: Clients poll `GET /jobs/{id}` for status rather than receiving real-time WebSocket or Webhook events.

---

### 18. What would you improve in production?
1. **Alembic Database Migrations**: Track schema versions and automate database migrations.
2. **Webhook Notifications**: Allow clients to submit a `webhook_url` to be notified upon job completion.
3. **Template Customization**: Support multiple predefined designs (e.g., Classic, Gold, Modern) via a `template_id` field.
4. **CSV/Excel Upload**: Allow uploading participant spreadsheets directly via `multipart/form-data`.
