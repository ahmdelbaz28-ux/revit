# Security

- **API Key authentication**: required for all design endpoints.
- **Rate limiting**: enforced via slowapi (30/10 req/min).
- **Input sanitization**: room IDs stripped of control characters, SQL metacharacters, and quotes; lengths limited.
- **File upload**: size capped at 50 MB, allowed extensions restricted.
- **Exception handling**: global handler prevents stack traces from leaking to clients.
- **Audit trail**: immutable, records all rejections and design decisions.