# Local Guidelines

- Think before coding — surface assumptions/tradeoffs, ask when unclear, push back on overcomplication.
- Simplicity first — minimum code, nothing speculative, no unrequested abstractions.
- Surgical changes — touch only what's needed, match existing style, don't refactor or "improve" adjacent code, leave pre-existing dead code (just mention it).
- Goal-driven execution — define success criteria and verify. Backend → test-first; frontend/Dash UI → tested live via your hot-reload debug server, no unit-style verify commands ([[debug-server-no-verify]]).
