# Environment Keys Reference (Canonical)

This is the single reference for **valid environment keys consumed by jvspatial**.

For full examples and default values, see:
- `docs/md/environment-configuration.md`
- `.env.example` at the repository root

## Scope

- `JVSPATIAL_*` keys configure server/database/auth/cache/storage/webhooks/scheduler behavior.
- Runtime/platform keys (`AWS_*`, `SERVERLESS_MODE`, etc.) affect serverless detection and AWS integrations.
- Unknown `JVSPATIAL_*` keys are ignored unless your application explicitly reads them.

## jvspatial Keys

### API and server
- `JVSPATIAL_TITLE` - Server title override.
- `JVSPATIAL_DESCRIPTION` - Server description override.
- `JVSPATIAL_VERSION` - Server version override.
- `JVSPATIAL_API_TITLE` - Alias-style title override used by API config mapping.
- `JVSPATIAL_API_DESCRIPTION` - Alias-style description override used by API config mapping.
- `JVSPATIAL_API_VERSION` - Alias-style version override used by API config mapping.
- `JVSPATIAL_HOST` - Host bind address.
- `JVSPATIAL_PORT` - Port bind value.
- `JVSPATIAL_LOG_LEVEL` - Logging level.
- `JVSPATIAL_DEBUG` - Debug mode toggle.
- `JVSPATIAL_API_PREFIX` - API route prefix.
- `JVSPATIAL_API_HEALTH` - Health route path.
- `JVSPATIAL_API_ROOT` - Root route path.
- `JVSPATIAL_GRAPH_ENDPOINT_ENABLED` - Enables graph REST endpoint.

### CORS
- `JVSPATIAL_CORS_ENABLED` - Enables CORS middleware.
- `JVSPATIAL_CORS_ORIGINS` - Allowed origins (CSV).
- `JVSPATIAL_CORS_METHODS` - Allowed methods (CSV).
- `JVSPATIAL_CORS_HEADERS` - Allowed headers (CSV).

### Primary database
- `JVSPATIAL_DB_TYPE` - Backend type (`json`, `sqlite`, `mongodb`, `dynamodb`).
- `JVSPATIAL_DB_PATH` - JSON/SQLite path.
- `JVSPATIAL_MONGODB_URI` - MongoDB URI.
- `JVSPATIAL_MONGODB_DB_NAME` - MongoDB database name.
- `JVSPATIAL_MONGODB_MAX_POOL_SIZE` - Mongo max pool size.
- `JVSPATIAL_MONGODB_MIN_POOL_SIZE` - Mongo min pool size.
- `JVSPATIAL_DYNAMODB_TABLE_NAME` - DynamoDB table name.
- `JVSPATIAL_DYNAMODB_REGION` - DynamoDB region.
- `JVSPATIAL_DYNAMODB_ENDPOINT_URL` - DynamoDB endpoint (e.g. LocalStack).
- `JVSPATIAL_DYNAMODB_WAIT_FOR_INDEX` - Wait-for-index toggle.

### Auth and rate limit
- `JVSPATIAL_AUTH_ENABLED` - Enables auth.
- `JVSPATIAL_JWT_SECRET_KEY` - JWT signing secret.
- `JVSPATIAL_JWT_ALGORITHM` - JWT algorithm.
- `JVSPATIAL_JWT_EXPIRE_MINUTES` - Access token expiry (minutes).
- `JVSPATIAL_JWT_REFRESH_EXPIRE_DAYS` - Refresh token expiry (days).
- `JVSPATIAL_AUTH_STRICT_HASHING` - Disables weak hashing fallback.
- `JVSPATIAL_BCRYPT_ROUNDS` - Bcrypt rounds.
- `JVSPATIAL_BCRYPT_ROUNDS_SERVERLESS` - Bcrypt rounds in serverless.
- `JVSPATIAL_ARGON2_TIME_COST` - Argon2 tuning.
- `JVSPATIAL_ARGON2_MEMORY_COST` - Argon2 tuning.
- `JVSPATIAL_ARGON2_PARALLELISM` - Argon2 tuning.
- `JVSPATIAL_RATE_LIMIT_ENABLED` - Enables rate limiting.
- `JVSPATIAL_RATE_LIMIT_DEFAULT_REQUESTS` - Request budget per window.
- `JVSPATIAL_RATE_LIMIT_DEFAULT_WINDOW` - Window size in seconds.

### Collections and normalization
- `JVSPATIAL_COLLECTION_USERS` - Users collection name.
- `JVSPATIAL_COLLECTION_API_KEYS` - API keys collection name.
- `JVSPATIAL_COLLECTION_SESSIONS` - Sessions collection name.
- `JVSPATIAL_COLLECTION_WEBHOOKS` - Webhooks collection name.
- `JVSPATIAL_COLLECTION_WEBHOOK_REQUESTS` - Webhook request log collection name.
- `JVSPATIAL_COLLECTION_SCHEDULED_TASKS` - Scheduled tasks collection name.
- `JVSPATIAL_TEXT_NORMALIZATION_ENABLED` - Enables text normalization.

### File storage and proxy
- `JVSPATIAL_FILE_STORAGE_ENABLED` - Enables file storage features.
- `JVSPATIAL_FILE_STORAGE_PROVIDER` - Provider (`local` or `s3`).
- `JVSPATIAL_FILES_ROOT_PATH` - Local files root path.
- `JVSPATIAL_FILE_STORAGE_BASE_URL` - Public base URL for files.
- `JVSPATIAL_FILE_STORAGE_MAX_SIZE` - Max upload size (bytes).
- `JVSPATIAL_FILE_STORAGE_SERVERLESS_SHARED` - Marks local path as durable shared storage.
- `JVSPATIAL_FILES_PUBLIC_READ` - Public `GET` access for file routes.
- `JVSPATIAL_FILE_INTERFACE` - Default storage interface selection.
- `JVSPATIAL_S3_BUCKET_NAME` - S3 bucket.
- `JVSPATIAL_S3_REGION` - S3 region.
- `JVSPATIAL_S3_ACCESS_KEY` - S3 access key.
- `JVSPATIAL_S3_SECRET_KEY` - S3 secret key.
- `JVSPATIAL_S3_ENDPOINT_URL` - S3 endpoint override.
- `JVSPATIAL_PROXY_ENABLED` - Enables proxy URLs.
- `JVSPATIAL_PROXY_PREFIX` - Proxy route prefix.
- `JVSPATIAL_PROXY_DEFAULT_EXPIRATION` - Default proxy expiry.
- `JVSPATIAL_PROXY_MAX_EXPIRATION` - Max proxy expiry.

### Logging and retention
- `JVSPATIAL_DB_LOGGING_ENABLED` - Enables DB logging handler.
- `JVSPATIAL_DB_LOGGING_LEVELS` - Persisted log levels (CSV).
- `JVSPATIAL_DB_LOGGING_DB_NAME` - Logical logging DB name.
- `JVSPATIAL_DB_LOGGING_API_ENABLED` - Enables logging API routes.
- `JVSPATIAL_LOG_DB_TYPE` - Log DB backend type.
- `JVSPATIAL_LOG_DB_PATH` - Log DB JSON/SQLite path.
- `JVSPATIAL_LOG_DB_URI` - Log MongoDB URI.
- `JVSPATIAL_LOG_DB_NAME` - Log MongoDB DB name.
- `JVSPATIAL_LOG_DB_TABLE_NAME` - Log DynamoDB table.
- `JVSPATIAL_LOG_DB_REGION` - Log DynamoDB region.
- `JVSPATIAL_LOG_DB_ENDPOINT_URL` - Log DynamoDB endpoint.
- `JVSPATIAL_LOG_RETENTION_DEFAULT_DAYS` - Default retention days.
- `JVSPATIAL_DB_LOG_SERVERLESS_ASYNC` - Async serverless DB log writes.
- `JVSPATIAL_DB_LOG_SERVERLESS_JOIN_TIMEOUT` - Join timeout for serverless DB log thread.

### Cache
- `JVSPATIAL_CACHE_BACKEND` - Cache backend.
- `JVSPATIAL_CACHE_SIZE` - Cache size.
- `JVSPATIAL_L1_CACHE_SIZE` - Layered cache L1 size.
- `JVSPATIAL_REDIS_URL` - Redis URL.
- `JVSPATIAL_REDIS_TTL` - Redis default TTL.

### Webhooks
- `JVSPATIAL_WEBHOOK_HMAC_SECRET` - Global webhook secret.
- `JVSPATIAL_WEBHOOK_HMAC_ALGORITHM` - HMAC algorithm.
- `JVSPATIAL_WEBHOOK_MAX_PAYLOAD_SIZE` - Max payload bytes.
- `JVSPATIAL_WEBHOOK_IDEMPOTENCY_TTL` - Idempotency TTL.
- `JVSPATIAL_WEBHOOK_HTTPS_REQUIRED` - HTTPS-only webhook policy.

### Walker safety and deferred execution
- `JVSPATIAL_WALKER_PROTECTION_ENABLED` - Enables walker safety guards.
- `JVSPATIAL_WALKER_MAX_STEPS` - Step cap.
- `JVSPATIAL_WALKER_MAX_VISITS_PER_NODE` - Visit cap per node.
- `JVSPATIAL_WALKER_MAX_EXECUTION_TIME` - Max runtime seconds.
- `JVSPATIAL_WALKER_MAX_QUEUE_SIZE` - Queue size cap.
- `JVSPATIAL_ENABLE_DEFERRED_SAVES` - Enables deferred saves (non-serverless).
- `JVSPATIAL_DEFERRED_TASK_PROVIDER` - Deferred task backend selector.
- `JVSPATIAL_AWS_DEFERRED_TRANSPORT` - AWS deferred transport mode.
- `JVSPATIAL_AWS_SQS_QUEUE_URL` - SQS queue URL when SQS transport is used.
- `JVSPATIAL_DEFERRED_INVOKE_DISABLED` - Disable deferred invoke route mount.
- `JVSPATIAL_DEFERRED_INVOKE_SECRET` - Authorization secret for deferred invoke route.
- `JVSPATIAL_WORK_CLAIM_STALE_SECONDS` - Claim lease TTL in seconds.

### EventBridge scheduler
- `JVSPATIAL_EVENTBRIDGE_SCHEDULER_ENABLED` - Enables EventBridge scheduling.
- `JVSPATIAL_EVENTBRIDGE_ROLE_ARN` - IAM role ARN for scheduler.
- `JVSPATIAL_EVENTBRIDGE_LAMBDA_ARN` - Target Lambda ARN.
- `JVSPATIAL_EVENTBRIDGE_SCHEDULER_GROUP` - Scheduler group name.

### Runtime mode helpers
- `JVSPATIAL_ENVIRONMENT` - Environment mode helper (`development`, `production`, etc.).
- `JVSPATIAL_LWA_ENV_DEFAULTS` - Controls automatic AWS LWA env defaults.

## Runtime and Platform Keys Also Read by jvspatial

- `SERVERLESS_MODE` - Explicit serverless mode override.
- `AWS_REGION`, `AWS_DEFAULT_REGION` - AWS region fallback.
- `AWS_ACCOUNT_ID` - AWS account id used for ARN synthesis.
- `AWS_LAMBDA_FUNCTION_NAME` - Lambda function name for serverless/runtime detection and ARN synthesis.
- `AWS_LAMBDA_RUNTIME_API` - Lambda runtime detection.
- `AWS_LAMBDA_EXEC_WRAPPER` - LWA wrapper detection.
- `AWS_LWA_PORT` - LWA port override.
- `AWS_LWA_PASS_THROUGH_PATH` - LWA passthrough route path.
- `AWS_LWA_INVOKE_MODE` - LWA invoke mode.
- `FUNCTIONS_WORKER_RUNTIME` - Azure Functions detection.
- `K_SERVICE` - Cloud Run / Functions Gen2 detection.
- `VERCEL` - Vercel detection.

## Notes

- Removed legacy names are intentionally omitted from this list.
- If a key is not listed here, treat it as non-canonical for jvspatial configuration.
