---
name: tinyfish-web-automation
description: Runs interactive web tasks through TinyFish MCP with schema-safe structured output, user-visible run display, and timeout recovery. Use when a user asks to operate a website, fill forms, calculate prices, extract exact values from dynamic pages, or avoid invalid output_schema errors in Qoder/QoderWork.
version: 1.0.1
install_source: connector-market
install_method: connector_bundle
connector_market_id: tinyfish
connector_server_id: tinyfish
skill_id: tinyfish-web-automation
enabled_at: 1783065580922
name_zh: TinyFish 网页自动化
description_zh: 指导在 QoderWork 中正确使用 TinyFish MCP 网页自动化能力。
---

# TinyFish Web Automation

## Workflow

Use TinyFish MCP for interactive browser work: forms, buttons, multi-step calculators, login/session workflows, or dynamic pages that require navigation beyond reading one URL.

In QoderWork lazy MCP mode, call TinyFish raw tools through `qw_mcp_call`. Use runtime tool names in the format `mcp__tinyfish__<raw_tool_name>`:

- Raw tool `search` -> `toolName: "mcp__tinyfish__search"`
- Raw tool `fetch_content` -> `toolName: "mcp__tinyfish__fetch_content"`
- Raw tool `run_web_automation` -> `toolName: "mcp__tinyfish__run_web_automation"`
- Raw tool `run_web_automation_async` -> `toolName: "mcp__tinyfish__run_web_automation_async"`

1. If the URL is unknown, call `qw_mcp_get` for `mcp__tinyfish__search`, then call `qw_mcp_call` with `toolName: "mcp__tinyfish__search"`.
2. If the task only reads URL content, call `qw_mcp_get` for `mcp__tinyfish__fetch_content`, then call `qw_mcp_call` with `toolName: "mcp__tinyfish__fetch_content"`.
3. For one interactive workflow, call `qw_mcp_get` for `mcp__tinyfish__run_web_automation`, then call `qw_mcp_call` with `toolName: "mcp__tinyfish__run_web_automation"` and top-level `"timeout": 600` so the TinyFish run UI/SSE display is available. Use `toolName: "mcp__tinyfish__run_web_automation_async"` only when the UI display is not needed or sync is unavailable.
4. If the client stops waiting before TinyFish finishes, treat that as the normal handoff to polling. Do not retry, cancel, or ask the user what to do.
5. For the same workflow across 2+ URLs, call `qw_mcp_get` for `mcp__tinyfish__batch_create`, then call `qw_mcp_call` with `toolName: "mcp__tinyfish__batch_create"`.

## Run Arguments

1. Put the target page in `url`.
2. Put only task instructions in `goal`; do not repeat `Navigate to ...` because `url` already supplies the page.
3. Generate a fresh UUID v4 for `session_id`.
4. Remember the `url`, `goal`, `session_id`, and call start time so a timed-out client call can be recovered.
5. Before calling, verify `"timeout": 600` is outside `arguments`.
6. Add `output_schema` only when the caller needs structured output or the harness expects it.
7. Keep `output_schema` minimal and shaped to the user's requested fields.
8. If the tool errors or times out, do not retry blindly. Recover the existing run, then poll it.

## Timeout Handling

- Assume Qoder may stop waiting for a single MCP call before TinyFish finishes; this is expected for long-running web automation.
- If using QoderWork's `qw_mcp_call` bridge, set a top-level `"timeout": 600` next to `toolName` and `arguments` when a long wait is useful. Do not put `timeout` inside TinyFish `arguments`.
- Treat `"timeout": 600` as best-effort. The client may still cap the wait earlier, so the recovery flow below is required.
- Do not cancel a `RUNNING` TinyFish run just because the original MCP call timed out.
- Treat a timed-out call with a `RUNNING` run as normal long-running execution.
- Do not ask the user whether to restart while a matching `RUNNING` run exists; keep polling and return the result when it completes.
- Cancel only if the user asks, the run is on the wrong URL, or the run goal is wrong.

## Timeout Recovery

After `MCP error -32001: Request timed out`:

1. Do not retry `run_web_automation`.
2. Do not call `cancel_run`.
3. Do not ask the user whether to restart.
4. Call `qw_mcp_get` for `mcp__tinyfish__discover_run`, then call `qw_mcp_call` with `toolName: "mcp__tinyfish__discover_run"` if available; otherwise call `qw_mcp_call` with `toolName: "mcp__tinyfish__list_runs"`.
5. Match the run by recent start time, `session_id`, URL, and goal.
6. Call `qw_mcp_call` with `toolName: "mcp__tinyfish__get_run"` on the matching `run_id`.
7. Poll with `qw_mcp_call` and `toolName: "mcp__tinyfish__get_run"` every 30 seconds for up to 12 minutes.
8. Return the result when status is `COMPLETED`; report the error if status is `FAILED`.

## Schema Rules

- Top-level `output_schema` must be an object with `type: "object"`.
- Use only: `anyOf`, `enum`, `format`, `items`, `maxItems`, `maximum`, `minItems`, `minimum`, `nullable`, `properties`, `propertyOrdering`, `required`, `type`.
- Do not use `oneOf`, `const`, `additionalProperties`, `$schema`, `$defs`, `description`, `default`, or type arrays.
- For optional nullable strings, use `{ "type": "string", "nullable": true }`.
- Every `required` field must also exist in `properties`.

## QoderWork Bridge Shape

```json
{
  "toolName": "mcp__tinyfish__run_web_automation",
  "arguments": {
    "url": "https://example.com/",
    "goal": "Complete the user-requested workflow on this page. Extract the exact requested values from the final page state.",
    "session_id": "GENERATE_A_NEW_UUID_V4",
    "output_schema": {
      "type": "object",
      "properties": {
        "answer": { "type": "string" },
        "evidence": { "type": "string" }
      },
      "required": ["answer", "evidence"]
    }
  },
  "timeout": 600
}
```

## Example: Calculator Price Extraction

For a shipping, tax, insurance, booking, or similar calculator, name fields after the requested values. Do not hard-code this schema unless the user asks for these fields.

```json
{
  "type": "object",
  "properties": {
    "item_or_service": { "type": "string" },
    "retail_price": { "type": "string" },
    "estimated_time": { "type": "string", "nullable": true },
    "evidence": { "type": "string" }
  },
  "required": ["item_or_service", "retail_price", "evidence"]
}
```

## Final Answer

Return exactly what the user asked for, using the tool result. If TinyFish uses equivalent keys such as `shipping_cost` for `retail_price` or `estimated_delivery_time` for `estimated_time`, map them without rerunning.
