# OpenClaw Agent Configuration Examples

This directory contains example agent configurations for integrating Brain From Cero with OpenClaw.

## Files

### Provider Configuration
- **`provider-config.yaml`** - Provider configuration for connecting OpenClaw to Brain From Cero
  - Copy to: `~/.openclaw/providers/brain-local.yaml`
  - Defines available models and their capabilities
  - Configure API key if authentication is enabled

### Agent Examples

1. **`agent-general-chat.yaml`** - General Purpose Chat Agent
   - Multi-channel (Telegram, Discord, Slack)
   - Balanced temperature for natural conversation
   - Suitable for everyday Q&A and assistance

2. **`agent-customer-support.yaml`** - Customer Support Specialist
   - Optimized for support workflows
   - Lower temperature for consistent responses
   - Includes escalation guidelines and business hours

3. **`agent-code-assistant.yaml`** - Code Review & Programming Help
   - Uses specialized `qwen2.5-coder-3b` model
   - Very low temperature for deterministic code
   - Focused on code review, debugging, and best practices

## Quick Start

### 1. Install OpenClaw

```bash
# Follow OpenClaw installation instructions
# (refer to OpenClaw documentation)
```

### 2. Configure Provider

```bash
# Copy provider configuration
mkdir -p ~/.openclaw/providers
cp provider-config.yaml ~/.openclaw/providers/brain-local.yaml

# Edit if needed (e.g., add API key)
nano ~/.openclaw/providers/brain-local.yaml
```

### 3. Set Up an Agent

```bash
# Create agents directory
mkdir -p ~/.openclaw/agents

# Copy desired agent configuration
cp agent-general-chat.yaml ~/.openclaw/agents/general-chat.yaml

# Customize the agent
nano ~/.openclaw/agents/general-chat.yaml
```

### 4. Start Brain From Cero

```bash
# Using Docker
cd /path/to/brainFromCero
docker-compose up -d

# Verify it's running
curl http://localhost:8000/health
```

### 5. Launch OpenClaw Agent

```bash
# Start specific agent
openclaw run general-chat

# Or start all agents
openclaw start
```

## Customization Guide

### Model Selection

Choose the right model for your use case:

| Use Case | Recommended Model | Why |
|----------|------------------|-----|
| General chat | `qwen2.5-3b-instruct` | Fast, versatile, good quality |
| Complex reasoning | `qwen2.5-7b-instruct` | Better at complex tasks |
| Code tasks | `qwen2.5-coder-3b` | Specialized for programming |
| Image analysis | `moondream2` | Vision capabilities |
| Custom task | Fine-tuned adapter | Specialized performance |

### Temperature Settings

Adjust `temperature` based on task:

- **0.0 - 0.3**: Deterministic (code, facts, support)
- **0.4 - 0.7**: Balanced (general chat, Q&A)
- **0.8 - 1.0**: Creative (storytelling, brainstorming)

### System Prompt Tips

Effective system prompts:
1. **Be Specific**: Define exact behaviors and guidelines
2. **Include Examples**: Show desired response formats
3. **Set Boundaries**: Clearly state what NOT to do
4. **Add Context**: Explain the agent's role and purpose
5. **Keep It Concise**: Long prompts may be truncated

Example structure:
```yaml
systemPrompt: |
  # Role
  You are a [specific role].

  # Goals
  Your mission is to [primary objective].

  # Guidelines
  1. [Guideline 1]
  2. [Guideline 2]

  # Boundaries
  Never [prohibited action].

  # Response Format
  Always [format requirement].
```

## Using Fine-Tuned Models

After training a LoRA adapter in Brain From Cero:

1. **Train the Model**
   - Use Brain dashboard to upload training data
   - Start training job with desired configuration
   - Wait for completion (monitor in dashboard)

2. **Test the Adapter**
   - Use Brain dashboard to test with sample inputs
   - Evaluate quality metrics
   - Compare with base model

3. **Update Agent Configuration**
   ```yaml
   # Change from:
   model: qwen2.5-3b-instruct

   # To (format: base_model:adapter_name):
   model: qwen2.5-3b-instruct:support_specialist_v1
   ```

4. **Restart OpenClaw Agent**
   ```bash
   openclaw restart agent-name
   ```

## Advanced Features

### Multi-Channel Deployment

Deploy same agent across multiple platforms:

```yaml
channels:
  - telegram  # @your_bot on Telegram
  - discord   # Bot on Discord server
  - slack     # App in Slack workspace
```

### Fallback Providers

Configure fallback to cloud providers:

```yaml
# In provider config
providers:
  - id: brain-local
    priority: 1  # Try local first
    models: [...]

  - id: openai
    priority: 2  # Fallback to OpenAI
    apiKey: sk-...
    models: [...]
```

### Rate Limiting

Protect your resources:

```yaml
rateLimits:
  requestsPerMinute: 10    # Per user
  requestsPerHour: 100     # Per user
  burstAllowance: 3        # Allow brief spikes
```

### Business Hours

Auto-message during off-hours:

```yaml
businessHours:
  timezone: "America/New_York"
  weekdays: "9:00-17:00"
  saturday: "10:00-14:00"
  sunday: "closed"
  afterHoursMessage: "Our team returns Monday at 9am ET."
```

## Troubleshooting

### Agent won't start

1. Check Brain is running: `curl http://localhost:8000/health`
2. Verify model is downloaded in Brain dashboard
3. Check OpenClaw logs: `openclaw logs agent-name`
4. Validate YAML syntax: `yamllint agent-config.yaml`

### Slow responses

1. **Use smaller model**: Try `qwen2.5-3b-instruct` instead of `7b`
2. **Enable GPU**: Configure `n_gpu_layers` in Brain
3. **Reduce max_tokens**: Lower `maxTokens` in agent config
4. **Preload model**: Keep model in memory between requests

### Out of memory

1. **Use Q4 quantization**: Smaller model files
2. **Close other apps**: Free up RAM
3. **Reduce context**: Lower `maxHistory` in config
4. **Use smaller model**: 3B instead of 7B

### Inconsistent responses

1. **Lower temperature**: Set to 0.2-0.4 for consistency
2. **Add examples**: Include examples in system prompt
3. **Fine-tune model**: Train on your specific use case
4. **Use fixed seed**: Enable deterministic generation

## Best Practices

1. **Start Simple**: Begin with general-chat agent, then specialize
2. **Test Thoroughly**: Use Brain dashboard to test prompts first
3. **Monitor Performance**: Check response times and quality
4. **Iterate Prompts**: Refine system prompts based on results
5. **Version Control**: Keep agent configs in git
6. **Document Changes**: Note what works and what doesn't
7. **Backup Models**: Export fine-tuned adapters regularly

## Example Workflows

### Workflow 1: Creating a Support Bot

1. Collect support conversation data (tickets, chats)
2. Format as JSONL training data
3. Upload to Brain via dashboard
4. Train LoRA adapter (3-5 epochs)
5. Evaluate on test set
6. Copy `agent-customer-support.yaml` and update model
7. Deploy to Discord/Telegram
8. Monitor and collect feedback
9. Retrain with new data periodically

### Workflow 2: Code Review Bot

1. Download `qwen2.5-coder-3b` in Brain
2. Copy `agent-code-assistant.yaml`
3. Customize for your tech stack
4. Deploy to Slack dev channel
5. Test with real code snippets
6. Adjust system prompt based on feedback
7. Optionally fine-tune on your codebase

### Workflow 3: Multi-Language Assistant

1. Fine-tune on multi-language dataset
2. Set system prompt with language instructions
3. Deploy to Telegram (international audience)
4. Monitor language detection accuracy
5. Add language-specific guidelines to prompt

## Resources

- **Brain From Cero Docs**: [../../docs/](../../docs/)
- **Training Guide**: [../../docs/architecture/LORA_TRAINING_ARCHITECTURE.md](../../docs/architecture/LORA_TRAINING_ARCHITECTURE.md)
- **API Reference**: http://localhost:8000/docs
- **OpenClaw Docs**: https://docs.openclaw.ai (hypothetical - adjust to actual URL)

## Support

If you encounter issues:
1. Check Brain logs: `docker logs brain-server`
2. Check OpenClaw logs: `openclaw logs`
3. Verify configurations are valid YAML
4. Test Brain API manually with `curl`
5. Review this README and main docs

---

**Happy agent building!** 🦞🤖
