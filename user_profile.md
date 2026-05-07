---
name: User profile
description: Bima Lucian — primary developer of BIMA_CORE, communicates in Bahasa Indonesia
type: user
originSessionId: 07d21ec6-6ef8-426e-ad55-f6b6a740d738
---
Email: bimachaktiadi.s@gmail.com. Goes by Bima.

Communicates primarily in casual Bahasa Indonesia (mixed with English technical terms). Prefers concise, direct answers without ceremony.

Develops BIMA_CORE solo on Windows 11 + WSL Ubuntu. Working directory accessed from Windows side via `\\wsl.localhost\Ubuntu\home\bima_lucian\BIMA_CORE`.

**Strong preferences (user-stated 2026-05-02):**
- **Action over chatter** — maximize concrete actions (read code, run tools, edit files), minimize basa-basi/preamble/recap. Don't ask for approval on read-only exploration when the rules already permit it; just do it and report findings.
- **Never break the operating rules** — strict adherence to EXPLORE→PLAN→CODE→VERIFY in `feedback_operating_rules.md` and the project's `Rules for agent.md`. No suggestions, recommendations, or assumptions about the codebase without first reading the relevant files. If tempted to answer from memory/intuition alone, stop and EXPLORE first.

**How to apply:** Reply in Bahasa Indonesia by default unless the user switches to English. Keep technical terms in English (e.g. "skill", "stack", "install", "deploy") — that matches how the user writes. Be brief; the user dislikes filler. When running shell commands, route through `wsl -d Ubuntu -- bash -lc "..."` since the harness shell is Windows PowerShell but the project lives in WSL. Lead with the action/result; explanation only if asked or non-obvious.
