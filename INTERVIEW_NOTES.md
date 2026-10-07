# Interview Preparation & Architecture Notes

This document provides clear, concise answers to core design questions and trade-offs regarding the **Bulk Certificate Generator API**. Use this guide to confidently explain your technical decisions during an SDE interview.

---

### 1. What problem does this project solve?
In event hosting, online education, and employee onboarding, organizations must issue customized certificates to hundreds or thousands of participants. Generating PDFs synchronously inside an HTTP request freezes the connection, triggers client timeouts, starves web server threads, and fails completely if one recipient has bad data.

This project provides an asynchronous REST API that:
- Accepts bulk generation requests instantly (`202 Accepted`).
- Validates data up-front.
- Renders PDF certificates in the background using a clean ReportLab layout.
- Protects the batch so that if one certificate fails, all others complete.
- Exposes real-time progress and download endpoints.

---

### 2. Why FastAPI?
- **Asynchronous Performance**: Built on Starlette and ASGI, FastAPI handles concurrent requests efficiently.
- **Built-in Pydantic v2 Integration**: Automatically validates incoming JSON payloads and generates strict schema definitions.
- **Auto-generated Documentation**: Automatically provides interactive Swagger (`/docs`) and ReDoc (`/redoc`) interfaces without manual documentation maintenance.
- **Dependency Injection**: Cleanly injects database sessions (`Depends(get_db)`) and background workers, simplifying unit testing and mocking.

---

### 3. Why SQLAlchemy?
- **Type Safety & Maintainability**: SQLAlchemy 2.0 uses type-annotated `Mapped` attributes and `mapped_column`, preventing runtime type bugs.
- **Database Abstraction**: Decouples application logic from specific SQL dialects. The application can run on SQLite for local development and easily switch to PostgreSQL in staging and production simply by changing `DATABASE_URL`.
- **Relational Integrity**: Automatically enforces foreign keys, cascades, and transaction rollbacks on failure.

---

### 4. Why a relational database?
The domain requires strict parent-child relationships and transaction guarantees:
- One `GenerationJob` has many `Certificate` entries.
- We need ACID guarantees so that counts (`successful_count`, `failed_count`) and statuses remain consistent even under concurrent operations.
- Relational tables allow straightforward indexing on `job_id`, `status`, and recipient emails.

---

### 5. Why background processing?
Generating a PDF involves disk I/O, canvas drawing, font rendering, and layout calculation. Doing this for 500 recipients could take 15–30 seconds.
- Keeping an HTTP connection open that long leads to gateway timeouts (e.g., Nginx or Cloudflare 504 errors) and poor user experience.
- Moving the work to a background task allows the API to respond in **under 20 milliseconds** with `202 Accepted` and a `job_id`, freeing the client to poll for status.

---

### 6. How does bulk processing work?
1. The client sends a single `POST /api/v1/certificates/generate` containing metadata (course, title, organization, date) and an array of recipient names and emails.
2. The endpoint validates the schema via Pydantic.
3. In a single database transaction, the API inserts:
   - One `GenerationJob` (status `PENDING`).
   - Multiple `Certificate` records (status `PENDING`).
4. A background task is scheduled with the `job_id`.
5. The API responds immediately with `202 Accepted`.
6. The background worker fetches the pending certificates, loops through them one-by-one, renders the PDFs, and updates statuses and counts in the database in real-time.

---

### 7. What happens if one certificate fails?
**Failure Isolation Rule**: The generation loop wraps every individual recipient in an isolated `try/except` block:
- If certificate #5 encounters an unexpected error (e.g., rendering issue):
  - Certificate #5 is marked `FAILED` with `error_message` stored in the database.
  - `job.failed_count` is incremented.
  - The loop continues immediately to recipient #6 and subsequent certificates.
- At the end of the job:
  - If all succeed: Job is marked `COMPLETED`.
  - If some succeed and some fail: Job is marked `COMPLETED_WITH_ERRORS`.
  - If all fail: Job is marked `FAILED`.

---

### 8. How is progress calculated?
Progress is computed dynamically from the job's persisted state:
$$\text{processed} = \text{successful\_count} + \text{failed\_count}$$
$$\text{pending} = \max(0, \text{total\_count} - \text{processed})$$
$$\text{progress\_percentage} = \operatorname{round}\left(\frac{\text{processed}}{\text{total\_count}} \times 100.0, 2\right)$$
Because the background processor commits status updates after each certificate, clients polling `GET /jobs/{id}` see real-time increments in `progress_percentage`.

---

### 9. How are generated files stored?
Files are stored locally in the configured directory (`generated_certificates/`).
- Filenames follow a deterministic, sanitized pattern:
  `cert_j{job_id}_c{cert_id}_{sanitized_recipient_name}.pdf`
- Recipient names are stripped of dangerous characters (`..`, `/`, `\`, non-alphanumeric chars) to prevent filesystem security issues.

---

### 10. How does certificate retrieval work?
- `GET /api/v1/certificates/{certificate_id}`:
  1. Checks if the certificate exists in the database (returns `404` if not found).
  2. Verifies the status is `GENERATED` (returns `400` if still `PENDING` or `FAILED`).
  3. Validates that the file path does not escape the configured root directory (`validate_safe_path`), preventing directory traversal attacks.
  4. Streams the PDF via FastAPI's `FileResponse` with proper `application/pdf` MIME type and a clean download filename.
- A ZIP download endpoint (`GET /jobs/{id}/zip`) is also provided to download all generated PDFs for a job at once.

---

### 11. How would you scale this to 100,000 certificates?
1. **Partition into Chunks**: Break the 100,000 batch into smaller chunks (e.g., 200–500 recipients per task).
2. **Distributed Queue (Celery / RabbitMQ / AWS SQS)**: Push chunk tasks to a distributed queue.
3. **Autoscaling Worker Fleet**: Run multiple worker containers on Kubernetes or AWS ECS that consume chunk tasks concurrently.
4. **Cloud Object Storage (S3 / GCS)**: Store rendered PDFs directly in S3 rather than local disks.
5. **Database Optimization**: Batch insert rows using SQLAlchemy `bulk_insert_mappings` or `insert().values([...])` to avoid 100,000 individual insert roundtrips.

---

### 12. Why might you replace BackgroundTasks with Celery/RQ?
- **Process Crash Resilience**: FastAPI `BackgroundTasks` runs in-memory within the web server process. If the server crashes, restarts, or deploys, any uncompleted in-memory tasks are lost.
- **Worker Isolation**: Celery workers run in separate operating system processes or machines, meaning heavy PDF generation won't consume CPU cycles needed by the FastAPI web server to handle incoming HTTP requests.
- **Retry Semantics & Rate Limiting**: Dedicated task queues offer automatic retries, exponential backoff, dead-letter queues, and task prioritization out of the box.

---

### 13. How would you use S3/object storage in production?
1. Instead of writing PDFs to local disk, the generator streams the PDF bytes to an Amazon S3 bucket (e.g., using `boto3`).
2. Store the resulting S3 key (`s3://bucket/certificates/job_1/cert_42.pdf`) in `Certificate.file_path`.
3. When retrieving a certificate:
   - Either stream the file from S3 via the API, OR
   - Generate a short-lived **S3 Pre-signed URL** (e.g., valid for 15 minutes) and issue a `307 Temporary Redirect` to the client. This offloads PDF download bandwidth entirely from our application servers to AWS CloudFront/S3!

---

### 14. How would you prevent duplicate jobs?
- **Idempotency Key**: Accept an `Idempotency-Key` HTTP header in `POST /generate`. Store the key in a database table or Redis cache for 24 hours. If the same key is received, return the existing `job_id` instead of creating a new job.
- **Content Hashing**: Compute an SHA-256 hash of the request payload (course + title + date + sorted recipient list). If a job with the identical hash was created recently and is active, return that job.

---

### 15. What would you improve with more time?
1. **Alembic Database Migrations**: Add Alembic to manage database schema versions smoothly over time.
2. **Webhook Notifications**: Allow clients to provide a `webhook_url` in the request to be notified automatically when `job.status == COMPLETED` instead of polling.
3. **Multiple Certificate Templates**: Support selectable templates (e.g., Gold, Modern, Minimalist) using a template identifier in the request.
4. **CSV/Excel File Upload**: Accept a `.csv` or `.xlsx` file upload directly via `multipart/form-data` to populate recipient lists easily.

---

### 16. What are the current limitations?
- **Single-Node Execution**: Background generation runs on the same instance as the API; large batches will share CPU with HTTP requests.
- **Local Ephemeral Disk**: Docker containers must mount a persistent volume, or generated PDFs will be lost when a container is destroyed.
- **Job Polling**: Clients must poll `GET /jobs/{id}` periodically to check for completion rather than receiving real-time WebSocket or Webhook events.
