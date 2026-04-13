# AX12 Research — Repo Restructure Plan

Plan for reorganizing `ax12-research` before the public launch as the
definitive AX12 reverse-engineering resource.

**Status:** DRAFT — review before executing.

---

## 1. Current State Assessment

### What Exists Today

```
ax12-research/
  .gitignore
  CLAUDE.md
  README.md
  dashboard.html                    <- generated output, orphaned at root
  captures/
    frames.json                     <- parsed frame data
    idle-analysis.md                <- analysis doc mixed with raw data
    idle-raw-10s.bin                <- raw binary capture
    idle-strace.txt                 <- truncated strace log
    idle-strace-full.txt            <- full strace log
    jitter-debug.txt                <- debug output
    jitter-test.txt                 <- test output
    timed-frames.json               <- timestamped frame data
  device-tree/
    all-nodes.txt                   <- flattened DT nodes
    ax12.dts                        <- decompiled device tree source
    compatible-nodes.txt            <- compatible string listing
    peripherals.txt                 <- peripheral summary
  docs/
    capture-session-guide.md        <- how-to guide
    checksum-investigation.md       <- research narrative
    control-map.json                <- data file, not a document
    device-tree.md                  <- reference doc
    elrs-telemetry-analysis.md      <- research narrative
    flyshark-lua-api.md             <- API reference (324 lines)
    hardware-map.md                 <- reference doc
    lua-scripting.md                <- overview (73 lines, overlaps flyshark-lua-api.md)
    native-lib-analysis.md          <- reference doc
    root-guide.md                   <- how-to guide
    system-audit.md                 <- reference doc
    umbus-protocol.md               <- protocol spec (core document)
  native-lib/                       <- gitignored contents, but dir is tracked
    RadioMasterAX.apk
    lib/arm64-v8a/libRadioMasterAX_arm64-v8a.so
  tools/
    __pycache__/                    <- leaked cache dir
    ax12-dashboard.lua              <- Lua script mixed with Python tools
    build-dashboard.py              <- generates dashboard.html
    calibrator.py                   <- 3-phase calibration tool
    capture-session.py              <- guided capture recording
    fm_radio.py                     <- MT6631 FM radio controller
    live-mapper.py                  <- interactive control mapper
    monitor.py                      <- live channel visualizer
    strace-parser.py                <- strace frame extractor
    umbus.py                        <- protocol library (core)
    umbus_server.py                 <- SSE server for live data
```

### What Is Good

- **README** is substantive: architecture diagram, key findings, device specs,
  methodology section. Better than 90% of RE project READMEs.
- **Protocol documentation** is thorough: frame formats, timing, CRC details,
  per-type breakdowns with hex examples.
- **Tool docstrings** are consistent and descriptive.
- **Commit history** is clean with meaningful messages.
- **CLAUDE.md** properly separates development config from public docs.
- **Methodology section** in README establishes credibility (passive captures,
  no decompilation).

### What Needs Work

1. **No LICENSE file.** Cannot go public without one.
2. **No CONTRIBUTING.md.** The README has a contributing section but it
   belongs in its own file with more detail.
3. **dashboard.html at root.** Generated output sitting next to README.
4. **docs/ is flat.** Mixes guides, references, research notes, and data
   files. No navigation hierarchy.
5. **Overlapping Lua docs.** `lua-scripting.md` (73 lines, overview) and
   `flyshark-lua-api.md` (324 lines, full API ref) cover the same topic.
   The overview should fold into the reference.
6. **control-map.json in docs/.** Data file, not documentation.
7. **idle-analysis.md in captures/.** Analysis narrative mixed with raw
   capture data.
8. **device-tree/ is an island.** Four files with no README or index. The
   corresponding `docs/device-tree.md` references them but a newcomer
   would not know to look.
9. **Lua script in tools/.** `ax12-dashboard.lua` is a device-side script,
   not a host-side Python tool.
10. **.gitignore is minimal.** Missing common patterns (editor backups, OS
    files, Python eggs, etc.).
11. **fm_radio.py has hardcoded shebang.** Still uses
    `/data/data/com.termux/files/usr/bin/python3` despite the portability
    commit.
12. **No tool usage overview.** Each tool has a docstring but there is no
    single document explaining the toolchain as a whole.

---

## 2. Proposed Directory Structure

```
ax12-research/
  .gitignore                        (expanded)
  CLAUDE.md                         (unchanged, development-only)
  CONTRIBUTING.md                   (new)
  LICENSE                           (new — MIT recommended)
  README.md                         (rewritten)

  docs/
    README.md                       (new — docs index/navigation)
    protocol/
      umbus-protocol.md             (moved from docs/)
      checksum-investigation.md     (moved from docs/)
      elrs-telemetry-analysis.md    (moved from docs/)
    hardware/
      hardware-map.md               (moved from docs/)
      device-tree.md                (moved from docs/)
      system-audit.md               (moved from docs/)
    software/
      native-lib-analysis.md        (moved from docs/)
      lua-api.md                    (merged: lua-scripting.md + flyshark-lua-api.md)
    guides/
      root-guide.md                 (moved from docs/)
      capture-session-guide.md      (moved from docs/)
      tool-usage.md                 (new — overview of all tools)

  tools/
    umbus.py                        (unchanged — core library)
    strace-parser.py                (unchanged)
    monitor.py                      (unchanged)
    calibrator.py                   (unchanged)
    capture-session.py              (unchanged)
    live-mapper.py                  (unchanged)
    umbus_server.py                 (unchanged)
    build-dashboard.py              (unchanged)
    fm_radio.py                     (fix shebang)

  captures/
    README.md                       (new — describes capture methodology)
    idle-strace.txt                 (unchanged)
    idle-strace-full.txt            (unchanged)
    idle-raw-10s.bin                (unchanged)
    frames.json                     (unchanged)
    timed-frames.json               (unchanged)
    jitter-debug.txt                (unchanged)
    jitter-test.txt                 (unchanged)

  data/                             (new directory)
    control-map.json                (moved from docs/)
    idle-analysis.md                (moved from captures/)

  device-tree/
    README.md                       (new — what these files are, how to regenerate)
    ax12.dts                        (unchanged)
    all-nodes.txt                   (unchanged)
    compatible-nodes.txt            (unchanged)
    peripherals.txt                 (unchanged)

  dashboard/                        (new directory)
    index.html                      (moved from dashboard.html)

  scripts/                          (new directory)
    ax12-dashboard.lua              (moved from tools/)
```

---

## 3. File Operations

### Moves

| From | To | Reason |
|------|----|--------|
| `dashboard.html` | `dashboard/index.html` | Generated output out of root |
| `docs/control-map.json` | `data/control-map.json` | Data file, not a document |
| `captures/idle-analysis.md` | `data/idle-analysis.md` | Analysis narrative, not raw capture |
| `tools/ax12-dashboard.lua` | `scripts/ax12-dashboard.lua` | Device-side Lua script, not a Python tool |

### Merges

| Files | Into | Reason |
|-------|------|--------|
| `docs/lua-scripting.md` + `docs/flyshark-lua-api.md` | `docs/software/lua-api.md` | Redundant overlap; the 73-line overview adds context that should lead into the 324-line API reference |

### Reorganize (moves within docs/)

| From | To |
|------|----|
| `docs/umbus-protocol.md` | `docs/protocol/umbus-protocol.md` |
| `docs/checksum-investigation.md` | `docs/protocol/checksum-investigation.md` |
| `docs/elrs-telemetry-analysis.md` | `docs/protocol/elrs-telemetry-analysis.md` |
| `docs/hardware-map.md` | `docs/hardware/hardware-map.md` |
| `docs/device-tree.md` | `docs/hardware/device-tree.md` |
| `docs/system-audit.md` | `docs/hardware/system-audit.md` |
| `docs/native-lib-analysis.md` | `docs/software/native-lib-analysis.md` |
| `docs/root-guide.md` | `docs/guides/root-guide.md` |
| `docs/capture-session-guide.md` | `docs/guides/capture-session-guide.md` |

### New Files

| File | Purpose |
|------|---------|
| `LICENSE` | MIT license (permissive, standard for RE research) |
| `CONTRIBUTING.md` | How to contribute captures, protocol findings, tooling |
| `docs/README.md` | Navigation index for all documentation |
| `docs/guides/tool-usage.md` | Overview of all tools with usage examples |
| `captures/README.md` | Describes capture format, methodology, how to add new captures |
| `device-tree/README.md` | What the DTS files are, how they were extracted |
| `dashboard/README.md` | What the dashboard is, how to regenerate it |

### Fixes

| File | Fix |
|------|-----|
| `tools/fm_radio.py` | Change shebang from hardcoded Termux path to `#!/usr/bin/env python3` |
| `.gitignore` | Expand to cover editor files, OS files, Python artifacts, build output |

### Deletions

| File | Reason |
|------|--------|
| `tools/__pycache__/` | Should never have been tracked; already in .gitignore |
| `docs/lua-scripting.md` | Content merged into `docs/software/lua-api.md` |

---

## 4. Internal Link Updates

Every `docs/*.md` file and the README contain relative links. All of these
must be updated after the directory restructure. Key link patterns to fix:

| Old Pattern | New Pattern |
|-------------|-------------|
| `docs/umbus-protocol.md` | `docs/protocol/umbus-protocol.md` |
| `docs/hardware-map.md` | `docs/hardware/hardware-map.md` |
| `docs/root-guide.md` | `docs/guides/root-guide.md` |
| `docs/native-lib-analysis.md` | `docs/software/native-lib-analysis.md` |
| `docs/device-tree.md` | `docs/hardware/device-tree.md` |
| `docs/system-audit.md` | `docs/hardware/system-audit.md` |
| `docs/lua-scripting.md` | `docs/software/lua-api.md` |
| `docs/flyshark-lua-api.md` | `docs/software/lua-api.md` |

Cross-references within docs themselves (e.g., hardware-map.md linking to
umbus-protocol.md) also need updating.

---

## 5. .gitignore Expansion

Current `.gitignore` (7 lines):
```
*.apk
*.so
*.bin
node_modules/
*.pyc
__pycache__/
native-lib/
```

Proposed additions:
```
# Editor / IDE
*.swp
*.swo
*~
.vscode/
.idea/

# OS
.DS_Store
Thumbs.db

# Python
*.egg-info/
dist/
build/
.eggs/

# Generated output
dashboard/index.html

# Claude Code
.claude/
```

Note: `dashboard/index.html` is generated by `build-dashboard.py`. It can
either be gitignored (regenerated on demand) or committed for convenience
(GitHub Pages). Decision needed — see Section 8.

---

## 6. README Rewrite Plan

The current README is good but was written as a research journal. The
rewrite should be structured for a first-time GitHub visitor.

### Proposed Structure

```
# RadioMaster AX12 — Reverse Engineering Reference

[one-line description]
[shields: license, python version, last commit]

## Overview
  2-3 paragraphs: what is the AX12, why this project exists,
  what you will find here

## Architecture
  ASCII diagram (keep the existing one, it is good)
  Brief explanation of each component

## Table of Contents
  Linked tree of all docs, organized by category:
  - Protocol (UMBUS spec, CRC, ELRS telemetry)
  - Hardware (hardware map, device tree, system audit)
  - Software (native lib analysis, Lua API)
  - Guides (root access, capture sessions, tool usage)

## Quick Start
  Three paths depending on what you want to do:
  1. "I want to read the protocol spec" -> link to UMBUS doc
  2. "I want to run the tools" -> prerequisites + first command
  3. "I want to capture my own data" -> link to capture guide

## Tools
  Table of all tools with one-line descriptions (keep existing
  format, add fm_radio.py and umbus_server.py which are missing)

## Key Findings
  Keep this section — it is the hook. Tighten the prose.
  Add the 33-channel and FM radio discoveries.

## Device Specifications
  Keep the existing table. Add kernel version and MCU model.

## Project Status
  Clean up the checklist. Add completed items from recent work
  (CRC cracked, control mapping confirmed, calibration tooling).

## Methodology
  Keep — establishes credibility. Move to bottom or a separate
  doc if it gets long.

## Contributing
  Brief pointer to CONTRIBUTING.md

## License
  One line + link to LICENSE file
```

### What to Remove from README

- The "Work in Progress" checklist should be converted to GitHub Issues or
  a ROADMAP.md, not cluttering the README.
- Inline contributing instructions — move to CONTRIBUTING.md.
- The license disclaimer paragraph — replace with actual LICENSE file.

### Shields / Badges

```markdown
![License: MIT](https://img.shields.io/badge/license-MIT-blue)
![Python 3.13](https://img.shields.io/badge/python-3.13-green)
![Platform: Android 9](https://img.shields.io/badge/platform-Android%209-brightgreen)
```

Keep it to three. No "build passing" badge (there is no CI) — that would
be dishonest.

---

## 7. CONTRIBUTING.md Outline

```
# Contributing

## What We Need
- Captures from different states (binding, flying, different models)
- DSC port loopback testing
- ELRS telemetry field identification
- Bootloader unlock attempts
- Lua script testing and new API discoveries

## How to Contribute Captures
- How to run strace-parser.py
- What to name files
- What metadata to include (firmware version, model config, etc.)

## Code Style
- Python 3.13, stdlib only
- Dataclass/enum patterns per tools/umbus.py
- Docstrings on all public functions
- No external dependencies

## Reporting Findings
- Open an issue with frame hex dumps
- Include firmware version and Flyshark app version
- Screenshots of the dashboard for visual context
```

---

## 8. Open Decisions

These need your input before execution:

### 8a. License Choice

**Recommendation: MIT.** It is the standard for RE research repos, maximally
permissive, and signals "use this knowledge freely." GPL would be unusual
for a documentation/research project. If you want to prevent commercial
use without attribution, consider CC BY 4.0 for the docs and MIT for the
code.

### 8b. Dashboard: Committed or Generated?

Option A: Gitignore `dashboard/index.html`, add instructions to regenerate.
Keeps the repo clean, avoids a 1000+ line HTML blob in git history.

Option B: Commit it for convenience. Visitors can open it directly from
GitHub or clone and view without running Python. Could enable GitHub Pages.

**Recommendation: Commit it.** The dashboard is a showcase artifact. Someone
browsing GitHub should be able to see the protocol visualizer. Enable GitHub
Pages on the `dashboard/` directory.

### 8c. Roadmap Location

Option A: `ROADMAP.md` at root — visible, easy to find.
Option B: GitHub Issues with labels — more granular, community-friendly.
Option C: Both — ROADMAP.md for the big picture, issues for specific tasks.

**Recommendation: Option C.** Convert the README checklist items into
GitHub Issues. Create a short ROADMAP.md linking to the issue tracker.

### 8d. data/ vs captures/analysis/

The `idle-analysis.md` and `control-map.json` files need a home. Options:

Option A: New `data/` directory for structured data and analysis writeups.
Option B: `captures/analysis/` subdirectory.

**Recommendation: Option A.** `data/` is cleaner. `control-map.json` is not
a capture — it is derived reference data.

### 8e. Lua Scripts Directory Name

The `ax12-dashboard.lua` device-side script needs to move out of `tools/`.
Options: `scripts/`, `lua/`, `device-scripts/`.

**Recommendation: `scripts/`** — generic enough for future non-Lua scripts,
matches common conventions.

---

## 9. Execution Order

If approved, execute in this order to keep the repo buildable at every
commit:

1. **Add LICENSE and CONTRIBUTING.md** (no breaking changes)
2. **Expand .gitignore** and remove `__pycache__/` from tracking
3. **Create new directories** (`dashboard/`, `data/`, `scripts/`,
   `docs/protocol/`, `docs/hardware/`, `docs/software/`, `docs/guides/`)
4. **Move files** using `git mv` to preserve history
5. **Merge lua-scripting.md into lua-api.md**
6. **Fix internal links** in all markdown files
7. **Add README files** to `docs/`, `captures/`, `device-tree/`, `dashboard/`
8. **Create docs/guides/tool-usage.md**
9. **Fix fm_radio.py shebang**
10. **Rewrite README.md**
11. **Create GitHub Issues** from the work-in-progress checklist
12. **Update CLAUDE.md** to reflect new paths

Each step should be a separate commit for clean history. Steps 3-6 could
be combined into a single "restructure" commit if you prefer fewer commits.

---

## 10. What This Does NOT Cover

- CI/CD setup (no tests exist yet — premature)
- GitHub Pages configuration (do after restructure)
- PyPI packaging of `umbus.py` (could be a future goal)
- Changelog / release notes (the git tag v0.1.0 exists; consider a
  v1.0.0 tag after restructure)
- Topic/description on the GitHub repo page (set via GitHub UI)
- Social preview image (would be nice — the architecture diagram as a PNG)
