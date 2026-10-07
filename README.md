# Bulk Certificate Generator API

A high-performance, asynchronous, fault-tolerant REST API built with **FastAPI**, **SQLAlchemy**, and **ReportLab** to generate bulk PDF certificates from a unified template with real-time status tracking and individual failure isolation.

---

## Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Tech Stack](#tech-stack)
- [System Architecture](#system-architecture)
- [Database Design](#database-design)
- [API Endpoints](#api-endpoints)
- [Installation & Local Setup](#installation--local-setup)
- [Running the Application](#running-the-application)
- [Docker & Docker Compose](#docker--docker-compose)
- [Automated Testing](#automated-testing)
- [Design Decisions](#design-decisions)
- [Trade-offs & Scalability](#trade-offs--scalability)

---

## Overview

Educational platforms, hackathons, and enterprise training programs regularly need to issue hundreds or thousands of certificates simultaneously. Generating high-resolution PDF documents synchronously within a single HTTP request causes socket timeouts, high latency, server thread starvation, and catastrophic failures if even one recipient contains malformed data.

The **Bulk Certificate Generator API** solves this by:
1. **Decoupling ingestion from generation**: Accepting batches asynchronously via `HTTP 202 Accepted`.
2. **Isolating per-certificate failures**: Ensuring that a rendering failure for one recipient does **not** abort the generation of remaining certificates.
3. **Providing live progress tracking**: Calculating real-time execution statistics (total, completed, failed, pending, progress percentage).
4. **Delivering secure PDF asset retrieval**: Serving individual certificate downloads and bundled ZIP archives with path-traversal protection.

---

## Key Features

- **Bulk Generation**: Generate up to 1,000 certificates in a single API call.
- **Asynchronous Processing**: Non-blocking generation utilizing FastAPI's native background worker model.
- **Strict Input Validation**: Pydantic v2 schemas validating email formats, non-blank names, ISO date patterns, and batch size boundaries.
- **Per-Certificate Failure Isolation**: Fault-tolerant iteration loop recording errors individually (`COMPLETED_WITH_ERRORS` status).
- **Professional PDF Template**: Clean, high-resolution vector PDF certificate generation via ReportLab with decorative dual-line borders, gold medallions, and typography hierarchy.
- **Real-Time Status & Progress**: Queryable progress tracking endpoint with percentage completion and recipient item breakdown.
- **Secure File Retrieval**: Path validation preventing directory traversal attacks (`/etc/passwd`, `../`), with single-click PDF downloads and bulk ZIP archive export.
- **Database Portability**: Runs with zero configuration on SQLite for local development; switchable to PostgreSQL via `DATABASE_URL`.
- **Comprehensive Test Suite**: 23 automated tests covering validation, happy path, individual failure isolation, and security checks.

---

## Tech Stack

| Component | Technology | Rationale |
| :--- | :--- | :--- |
| **Framework** | [FastAPI](https://fastapi.tiangolo.com/) (Python 3.11+) | Asynchronous ASGI, high throughput, automatic OpenAPI documentation |
| **Validation** | [Pydantic v2](https://docs.pydantic.dev/) | Type safety, strict schema validation, fast Rust-based core |
| **ORM** | [SQLAlchemy 2.x](https://www.sqlalchemy.org/) | Type-safe declarative models, relational integrity, multi-dialect support |
| **Database** | SQLite (Dev) / PostgreSQL (Prod) | Zero-setup local development with seamless migration to PostgreSQL |
| **PDF Engine** | [ReportLab](https://www.reportlab.com/) | Pure Python vector graphics generation, precise coordinates, zero binary tool dependencies (e.g., no wkhtmltopdf) |
| **Web Server** | [Uvicorn](https://www.uvicorn.org/) | Lightning-fast ASGI web server implementation |
| **Testing** | [pytest](https://docs.pytest.org/) & [httpx](https://www.python-httpx.org/) | Deterministic unit and API integration testing with fixture isolation |
| **Containerization**| Docker & Docker Compose | Repeatable, containerized deployment across environments |

---

## System Architecture

```text
                  +-----------------------------------+
                  |           Client / UI             |
                  +-----------------------------------+
                                    |
                 1. POST /generate  |  3. GET /jobs/{id}
                                    v
                  +-----------------------------------+
                  |        FastAPI Application        |
                  |     - Pydantic v2 Validation      |
                  |     - REST API Controllers        |
                  +-----------------------------------+
                        |                       |
       2. Record Job    |                       | 4. Dispatch Task
          & Recipients  v                       v
      +---------------------+        +--------------------+
      |  Relational DB      |        | Background Worker  |
      | (SQLite/PostgreSQL) |<-------| (Job Processor)    |
      +---------------------+ Update +--------------------+
                               State            |
                                                | 5. Render
                                                v
                                     +--------------------+
                                     | Certificate        |
                                     | Generator Engine   |
                                     | (ReportLab)        |
                                     +--------------------+
                                                |
                                                | 6. Save PDF
                                                v
                                     +--------------------+
                                     | Local File Storage |
                                     | (generated_certs/) |
                                     +--------------------+
```

---

## Database Design

The relational schema uses two models linked by a foreign key with cascade deletion:

```text
+---------------------------------------+         +---------------------------------------+
|            generation_jobs            |         |              certificates             |
+---------------------------------------+         +---------------------------------------+
| id               : Integer (PK)       | 1     * | id                : Integer (PK)      |
| title            : String(200)        |<------->| job_id            : Integer (FK)      |
| course           : String(200)        |         | recipient_name    : String(200)       |
| organization     : String(200)        |         | recipient_email   : String(255)       |
| event_date       : String(50)         |         | certificate_title : String(200)       |
| status           : JobStatus (Enum)   |         | course            : String(200)       |
| total_count      : Integer            |         | organization      : String(200)       |
| successful_count : Integer            |         | event_date        : String(50)        |
| failed_count     : Integer            |         | status            : CertStatus (Enum) |
| created_at       : DateTime (UTC)     |         | file_path         : String(500)       |
| started_at       : DateTime (UTC)     |         | error_message     : Text              |
| completed_at     : DateTime (UTC)     |         | created_at        : DateTime (UTC)    |
+---------------------------------------+         +---------------------------------------+
```

### State Transitions

- **`JobStatus`**:
  - `PENDING`: Job recorded and queued for background execution.
  - `PROCESSING`: Worker is currently iterating over recipients.
  - `COMPLETED`: All recipient certificates rendered successfully (`failed_count == 0`).
  - `COMPLETED_WITH_ERRORS`: Some certificates generated, but at least one failed (`successful > 0` and `failed > 0`).
  - `FAILED`: All certificates in the job failed generation (`successful == 0` and `failed > 0`).

- **`CertificateStatus`**:
  - `PENDING`: Awaiting generation.
  - `GENERATED`: PDF successfully created and saved to disk.
  - `FAILED`: Generation encountered an error; `error_message` holds diagnostic details.

---

## API Endpoints

| Method | Endpoint | Description | Status Code |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/certificates/generate` | Create a bulk certificate generation job | `202 Accepted` |
| `GET` | `/api/v1/certificates/jobs/{job_id}` | Fetch real-time job status, progress %, and recipient results | `200 OK` / `404 Not Found` |
| `GET` | `/api/v1/certificates/{certificate_id}` | Download generated PDF certificate | `200 OK` / `400` / `404` |
| `GET` | `/api/v1/certificates/jobs/{job_id}/zip` | Download all certificates of a job as a ZIP file | `200 OK` / `400` / `404` |
| `GET` | `/health` | Service health status check | `200 OK` |
| `GET` | `/docs` | Interactive OpenAPI Swagger UI | `200 OK` |

---

## Installation & Local Setup

### 1. Clone Repository

```bash
git clone https://github.com/your-username/bulk-certificate-generator-api.git
cd bulk-certificate-generator-api
```

### 2. Set Up Virtual Environment

**On Windows (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\activate
```

**On Linux / macOS:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Copy the provided example environment file:

```bash
cp .env.example .env
```

Contents of `.env`:
```ini
APP_NAME="Bulk Certificate Generator API"
APP_ENV="development"
DEBUG=true
DATABASE_URL=sqlite:///./certificates.db
GENERATED_CERTIFICATES_DIR=generated_certificates
MAX_BULK_LIMIT=1000
```

---

## Running the Application

Start the development server with Uvicorn:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- **Interactive API Documentation (Swagger)**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **Alternative ReDoc UI**: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)
- **Health Check**: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)

---

## API Usage Examples

### 1. Submit Bulk Certificate Generation Job

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/certificates/generate" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Certificate of Completion",
    "course": "Python Backend Development",
    "organization": "Aereo",
    "event_date": "2026-10-07",
    "recipients": [
      {
        "name": "Rahul Kumar",
        "email": "rahul@example.com"
      },
      {
        "name": "Priya Sharma",
        "email": "priya@example.com"
      }
    ]
  }'
```

**Response (`202 Accepted`):**
```json
{
  "job_id": 1,
  "status": "PENDING",
  "total_count": 2,
  "message": "Certificate generation job accepted and processing in background"
}
```

---

### 2. Poll Job Status & Progress

```bash
curl -X GET "http://127.0.0.1:8000/api/v1/certificates/jobs/1"
```

**Response (`200 OK`):**
```json
{
  "job_id": 1,
  "status": "COMPLETED",
  "total": 2,
  "successful": 2,
  "failed": 0,
  "pending": 0,
  "progress_percentage": 100.0,
  "created_at": "2026-10-07T12:00:00Z",
  "started_at": "2026-10-07T12:00:01Z",
  "completed_at": "2026-10-07T12:00:02Z",
  "certificates": [
    {
      "certificate_id": 1,
      "recipient_name": "Rahul Kumar",
      "recipient_email": "rahul@example.com",
      "status": "GENERATED",
      "download_url": "/api/v1/certificates/1",
      "error_message": null
    },
    {
      "certificate_id": 2,
      "recipient_name": "Priya Sharma",
      "recipient_email": "priya@example.com",
      "status": "GENERATED",
      "download_url": "/api/v1/certificates/2",
      "error_message": null
    }
  ]
}
```

---

### 3. Download Generated Certificate PDF

```bash
curl -X GET "http://127.0.0.1:8000/api/v1/certificates/1" \
  -o "Certificate_Rahul_Kumar.pdf"
```

---

### 4. Download All Certificates in Bulk (ZIP)

```bash
curl -X GET "http://127.0.0.1:8000/api/v1/certificates/jobs/1/zip" \
  -o "Job_1_Certificates.zip"
```

---

## Docker & Docker Compose

To run the entire system including PostgreSQL using Docker:

```bash
# Build and run containers in background
docker compose up -d --build

# View real-time logs
docker compose logs -f api

# Tear down containers
docker compose down
```

The API will be available at `http://localhost:8000`.

---

## Automated Testing

The project contains a thorough test suite using `pytest` and `httpx`.

All tests run in total isolation: each test uses an ephemeral in-memory/temp SQLite database and temporary storage directory to prevent any mutation of production data.

### Run Tests

```bash
pytest -v
```

### Coverage Highlights

- **`test_create_job.py`**: Validates asynchronous job creation, payload parsing, database insertion, and correct HTTP 202 response.
- **`test_validation.py`**: Validates request bounds (empty lists, invalid emails, whitespace-only names, malformed date formats, missing fields).
- **`test_generation.py`**: Unit tests ReportLab PDF generation, verifying file creation, PDF magic bytes (`%PDF-`), and file sizing.
- **`test_job_status.py`**: Tests real-time computation of pending certificates, completion percentages, 404 responses, and pagination.
- **`test_failure_handling.py`**: **Critical Requirement** — Simulates a failure on recipient Bob among Alice, Bob, and Charlie. Verifies Alice is `GENERATED`, Bob is `FAILED`, and Charlie is `GENERATED`. Verifies job status becomes `COMPLETED_WITH_ERRORS`.
- **`test_retrieval.py`**: Tests PDF download, pending/failed HTTP 400 guards, 404 missing files, directory traversal security (`/etc/passwd`), and ZIP packaging.
- **`test_health_and_docs.py`**: Verifies `/health` and OpenAPI schema endpoints.

---

## Design Decisions

1. **Why FastAPI?**  
   FastAPI provides asynchronous request handling, automatic OpenAPI/Swagger documentation, and native dependency injection. Its seamless Pydantic integration ensures request bodies are validated before hitting service logic.

2. **Why SQLAlchemy 2.x?**  
   SQLAlchemy 2.0 provides modern, type-hinted Mapped columns and clean separation between ORM models and database queries. It abstracts SQL dialect differences, allowing the codebase to run against SQLite during development and PostgreSQL in production without code modifications.

3. **Why Background Tasks?**  
   Rendering dozens or hundreds of PDF files involves substantial CPU and I/O overhead. Performing this synchronously would block HTTP connections and result in timeouts. FastAPI `BackgroundTasks` executes the rendering asynchronously while immediately responding to the user with a tracking ID (`202 Accepted`).

4. **Why Per-Certificate Failure Isolation?**  
   In bulk batch operations, one bad record (e.g., rendering issue) must never invalidate an entire batch of 500 recipients. Wrapping each certificate generation inside an isolated `try/except` block ensures unaffected recipients are successfully processed and downloaded, while failures are clearly recorded for re-processing.

5. **Why ReportLab for PDFs?**  
   ReportLab generates vector-based PDF documents natively in pure Python with precise layout control, standard typography, and cryptographic document structures. It eliminates heavyweight external browser dependencies (like Puppeteer or Chromium) or system binaries (like wkhtmltopdf).

6. **Why Path Traversal Validation?**  
   Filesystem downloads are vulnerable to path traversal if user-supplied data influences paths. The application resolves and strictly validates all certificate filepaths against the designated storage root before serving files.

---

## Trade-offs & Scalability

While the current architecture is clean, maintainable, and completely self-contained for an intern take-home assignment, a production environment scaling to hundreds of thousands of certificates would consider the following trade-offs:

1. **In-Process BackgroundTasks vs. Distributed Message Queue (Celery / RQ)**:
   - *Current*: `BackgroundTasks` runs in the same process threadpool. If the web server process restarts, pending background tasks could be dropped.
   - *Production Scale*: A dedicated message broker (RabbitMQ or Redis) paired with Celery or RQ workers provides persistent task queues, worker scaling across multiple machines, automatic retries with exponential backoff, and rate limiting.

2. **Local Disk Storage vs. Cloud Object Storage (AWS S3 / GCS)**:
   - *Current*: PDF files are saved to the local filesystem (`generated_certificates/`).
   - *Production Scale*: Multi-instance deployments cannot share local filesystems without distributed mounts. Storing PDFs in AWS S3 or Google Cloud Storage enables pre-signed download URLs, lifecycle policies, and infinite scaling.

3. **Synchronous Iteration vs. Chunked Parallel Processing**:
   - *Current*: Certificates are generated sequentially in a loop within the background task.
   - *Production Scale*: For 100,000 certificates, the batch should be partitioned into chunks (e.g., 500 recipients per task) distributed across a fleet of worker nodes.
