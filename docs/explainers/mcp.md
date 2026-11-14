# Explainer: the MCP server (E6)  · owner: Aditya

## Problem
The analysis and execution tools (code graph, slicing, probes, mutation, patch validation) are useful to any AI
application, not only ours. The Model Context Protocol (MCP) is a standard way to offer tools to AI clients across
processes. Can our tools be offered that way without changing any result?

## How it works (plain words)
`mcp_server/server.py` is a FastMCP server (mcp SDK 1.x) that talks MCP over stdin/stdout. Started for one question
(`--library click --commit <sha>`), it builds that question's workspace, Docker sandbox session and code graph, and
exposes 12 tools: `run_probe`, `trace`, `graph_candidates`, `graph_summary`, `call_graph`, `static_slice`,
`run_experiments`, `experiment_results`, `validate_patch`, `snippet`, `stats`. Each tool calls the same function the
in-process backend calls and returns JSON text. `mcp_server/client.py` (`MCPBackend`) starts the server, keeps one
connection open in a background asyncio thread, and offers the orchestrator exactly the methods of
`experiments/backend.py:InProcessBackend`. So E6 is E5 with a different transport.

## Worked example
`tests/mcp_server/test_mcp_roundtrip.py` runs the toylib question twice through the orchestrator, once in-process and
once with `MCPBackend(["--toylib"])` (a trusted local backend for the hand-written toylib probes only). The rankings,
the verdict of every experiment and the patch validation are identical; the MCP run made 5+ tool calls over the
protocol.

## Weaknesses
- One server process per question: start-up costs a few seconds.
- The agents' read-only search tools are not routed through MCP (they are cheap and in-process).
- mcp 2.x renamed FastMCP; we pin `mcp<2`.

## Viva Q&A
1. **What does MCP add if results are identical?** Reuse: any MCP client (an IDE assistant, another agent) can call our
   sandboxed probe and mutation tools with the same safety rules. E6 checks that the transport changes nothing.
2. **Is LLM-written code safer or less safe through MCP?** The same: the server runs probes in the same Docker sandbox
   with the same AST policy; MCP only moves the request.
3. **Why stdio and not HTTP?** The server is local and per question; stdio needs no port and dies with the client.
4. **Why a background thread in the client?** The SDK is async, the orchestrator is synchronous; one long-lived task
   opens, serves and closes the connection, because the SDK's connection must be closed by the task that opened it.
5. **What does E6 measure?** That answers equal E5's (the LLM cache replays identical prompts) and the time overhead of the
   protocol (`backend_stats.mcp_seconds`).
