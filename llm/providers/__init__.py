"""Provider adapters. Each exposes `name` and
`call(model, messages, tools, params) -> Reply`, raising `RateLimited`,
`TransientError` or `LLMError` from `llm.types`."""
