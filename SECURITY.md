# Security Policy

## Disclaimer

Brain is an experimental R&D project for local AI infrastructure. It is **NOT** intended for production use with sensitive data. This project is designed for:

- Local development and testing
- Learning AI infrastructure patterns
- Research and experimentation

**DO NOT** use Brain in production environments or with sensitive/confidential data.

## Security Considerations

### Local-First Design

Brain is designed to run locally on your hardware:
- All inference happens on your machine
- No data is sent to external services by default
- Models are stored and run locally
- API endpoints are meant for local access only

### Known Security Limitations

1. **No Authentication**: The API server has no built-in authentication
2. **No Encryption**: Local API communication is unencrypted
3. **File Access**: Tool functions can read/write local files (sandboxed to data directory)
4. **Low Test Coverage**: ~14% test coverage may hide security issues
5. **Experimental Code**: Many features are partially implemented

### Deployment Recommendations

If you choose to deploy Brain despite the warnings:

1. **Never expose to public internet** without proper authentication/authorization
2. **Use reverse proxy** (nginx, Caddy) with TLS and authentication
3. **Restrict file system access** via Docker or system permissions
4. **Monitor resource usage** as inference can be resource-intensive
5. **Validate all inputs** especially for tool calling features
6. **Run in isolated environment** (container, VM)

## Reporting Security Issues

If you discover a security vulnerability:

1. **DO NOT** create a public GitHub issue
2. Instead, please report it privately via:
   - GitHub Security Advisory feature (once repository is public)
   - Or create a private issue with details

Include in your report:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

## Security Best Practices for Contributors

When contributing code:

1. **Never commit secrets** (API keys, passwords, tokens)
2. **Validate inputs** for all user-facing functions
3. **Use parameterized queries** for any database operations
4. **Limit file operations** to designated directories
5. **Add input size limits** to prevent DoS
6. **Document security implications** of new features

## Third-Party Dependencies

Brain uses several third-party libraries. Security considerations:

- **llama-cpp-python**: Handles model inference
- **FastAPI**: Web framework with built-in security features
- **ChromaDB**: Vector database for embeddings
- **Transformers**: Hugging Face models

Keep dependencies updated for security patches:
```bash
pip install --upgrade -r requirements.txt
```

## Data Privacy

Brain processes data locally:

- **Models**: Downloaded models stay on your machine
- **Conversations**: Stored locally in PostgreSQL/SQLite
- **Embeddings**: Cached locally in ChromaDB
- **Logs**: Written to local filesystem

No telemetry or analytics are collected by Brain itself.

## Responsible AI Use

When using Brain:

- Be aware of model biases and limitations
- Don't use for critical decision-making
- Validate all AI-generated content
- Consider ethical implications of your use case
- Follow model licenses and terms of use

## Contact

For security concerns or questions about this policy, please open a GitHub issue (for non-sensitive topics) or contact via security advisory (for vulnerabilities).

Remember: Brain is an experimental project for learning and research. Use at your own risk.