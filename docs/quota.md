# Measured API quotas

Written automatically by `llm/client.py` whenever a provider returns a 429 that names its quota. Throttle settings in `config/default.yaml` follow these.

| first seen (UTC) | provider | model | quota id | limit | per day |
|---|---|---|---|---|---|
| 2026-10-30 10:53 | gemini | gemini-3.1-flash-lite | GenerateRequestsPerMinutePerProjectPerModel-FreeTier | 15 | no |
| 2026-10-30 10:59 | gemini | gemini-3.1-flash-lite | GenerateContentInputTokensPerModelPerMinute-FreeTier | 250000 | no |
| 2026-10-30 11:30 | gemini | gemini-3.1-flash-lite | GenerateRequestsPerDayPerProjectPerModel-FreeTier | 500 | yes |
| 2026-10-30 11:45 | groq | openai/gpt-oss-120b | TPM | 8000 | no |
| 2026-10-30 11:56 | groq | openai/gpt-oss-120b | TPD | 200000 | yes |
