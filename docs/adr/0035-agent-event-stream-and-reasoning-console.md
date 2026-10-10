# Agent Event Stream and Real-Time Reasoning Console

**Status**: Accepted

To provide real-time observability into LLM reasoning traces, executed tool commands, and execution outputs without incurring cloud networking overhead or altering host process isolation, we decided to introduce the **Agent Event Stream**—a structured telemetry pipeline that streams in-sandbox `@earendil-works/pi-agent-core` events across Modal container stdout via JSON envelopes into the host `JobRegistry` and Server-Sent Events (SSE).

## Considered Options

- **Raw Unstructured Terminal Logs**: Emitting only raw terminal text logs from container stdout. Rejected because LLM thinking traces flood the terminal with thousands of verbose tokens, obscuring executed commands and forcing fragile regex scraping in the frontend.
- **Dedicated Out-of-Band Webhook / WebSocket Daemon**: Running a WebSocket or HTTP sidecar in the sandbox connecting directly to the host. Rejected because it introduces inbound port exposure, complex firewall/NAT tunneling, and failure modes when network boundaries disconnect.
- **Tagged Stdout JSON Envelopes over Modal Stream (`__SF_EVENT__`)**: Accepted because Modal natively captures container stdout/stderr reliably without open ports. Emitting tagged JSON envelopes (`__SF_EVENT__:{...}`) allows the host `JobRegistry` to demux structured telemetry from plain terminal logs into dual channels (`job.logs` and `job.events`), streaming live to both the Factory Testing Console and Factory Studio via SSE.

## Consequences

- The canonical term **Agent Event Stream** is incorporated into `CONTEXT.md`.
- In-sandbox `AgentEventStream` in `sandbox/factory/` subscribes to `@earendil-works/pi-agent-core` events, emitting 100ms micro-batched thinking deltas, tool starts, and tool results.
- `factory/ui/registry.py` intercepts `__SF_EVENT__:` envelopes, populates `job.events`, keeps `job.logs` clean for plain-text copying, and broadcasts SSE events.
- Factory Testing Console renders interactive collapsible thinking accordions, command execution cards with windowed output (last 100 lines + expand), and tool chips.
- Factory Studio renders inline reasoning disclosures and step chips within chat messages, backed by an expandable slide-over Agent Activity drawer.
