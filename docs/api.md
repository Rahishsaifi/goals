# API

Base prefix: `/api/v1`

## Health

- `GET /health/live`
- `GET /health/ready`

## Auth

- `POST /auth/login`
- `POST /auth/logout`
- `GET /auth/me`
- `POST /auth/accept-invitation`
- `POST /auth/verify-email`
- `POST /auth/forgot-password`
- `POST /auth/reset-password`
- `POST /auth/invitations`

## Resumes

- `POST /resumes/upload-sessions`
- `POST /resumes/complete-upload`
- `GET /resumes`
- `GET /resumes/{resume_id}`
- `DELETE /resumes/{resume_id}`

## Job profiles

- `POST /job-profiles`
- `GET /job-profiles`
- `GET /job-profiles/{id}`
- `POST /job-profiles/{id}/versions`
- `POST /job-profiles/{id}/validate-weights`

## Evaluations

- `POST /evaluations`
- `GET /evaluations/{run_id}`
- `GET /evaluations/{run_id}/results`
- `POST /evaluations/{run_id}/export`
- `POST /evaluations/{run_id}/cancel`

## Usage

- `GET /usage/summary`
- `GET /usage/events`
- `GET /usage/pricing`
