# Mnemosyne SDK

Python SDK for Mnemosyne - Experiential Memory Layer for AI Agents.

## Installation

```bash
pip install mnemosyne-sdk
```

## Quick Start

```python
from mnemosyne import MnemosyneClient

# Initialize client
client = MnemosyneClient(
    base_url="http://localhost:8000",
    agent_id="my-agent-v1"
)

# Retrieve relevant lessons before making a decision
lessons = client.retrieve(
    context="User is asking about refund policy",
    top_k=5
)

# Use the formatted context in your agent's prompt
print(lessons.context)

# After agent execution, report the trace
trace = client.ingest_trace(
    trace_data={
        "action": "processed_refund",
        "success": True,
        "details": {...}
    }
)
```

## Async Usage

```python
from mnemosyne import AsyncMnemosyneClient

async def main():
    client = AsyncMnemosyneClient(
        base_url="http://localhost:8000",
        agent_id="my-agent-v1"
    )

    lessons = await client.retrieve(context="...")
    trace = await client.ingest_trace(trace_data={...})
```
