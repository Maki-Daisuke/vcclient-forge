# VCClient Forge: Agent Guidelines & Instructions

> **「できることが同じなら、コードもドキュメントも少ないほうが正義！」**  
> *(Core Philosophy: If the outcome and capabilities are identical, less code and concise documentation is the ultimate virtue.)*

VCClient Forge is a Windows-first, local real-time RVC (Retrieval-based Voice Conversion) application.
It features a pure-ONNX inference engine, a native PortAudio/WASAPI audio pipeline, a FastAPI + Socket.IO backend, and a Wails v3 (Go) desktop interface.

---

## 1. Development & Quality Assurance Commands

Always run commands from the repository root. Backend Python dependencies and tooling are managed with `uv`.

### Build & Run

| Task                                | Command                                                                                 |
| ----------------------------------- | --------------------------------------------------------------------------------------- |
| Run backend from source             | `npm start` (or `uv run --project backend python backend/main.py`)                      |
| Build all components (default: universal) | `npm run build` or `npm run build -- --edition <edition>` (`universal`, `cuda`) |
| Build frontend assets only          | `npm run build:frontend`                                                                |
| Package prebuilt distribution       | `npm run package -- --edition <edition>`                                                |

### Testing & Verification

| Task                     | Command                                                                    |
| ------------------------ | -------------------------------------------------------------------------- |
| Run full test suite      | `npm test`                                                                 |
| Run backend pytest suite | `npm run test:backend`                                                     |
| Run single test file     | `uv run --project backend pytest backend/tests/test_pipeline_slot_sync.py` |
| Run desktop tests        | `npm run test:desktop` (or `cd desktop && go test .`)                      |

### Formatting & Linting

| Task                  | Command                     |
| --------------------- | --------------------------- |
| Check formatting      | `npm run format:check`      |
| Apply formatting      | `npm run format`            |
| Check lint            | `npm run lint`              |
| Fix lint issues       | `npm run lint:fix`          |
| Run backend typecheck | `npm run typecheck:backend` |

---

## 2. Command-Line Efficiency: coreutils & ripgrep (`rg`)

When exploring the codebase, searching text, or inspecting files via terminal commands:

- **Prefer `rg` (ripgrep) over PowerShell cmdlets**: Use `rg` for high-speed pattern matching across the repository. Avoid slow recursive `Get-ChildItem` or `Select-String`.
- **Leverage `coreutils`**: Utilize standard tools (`grep`, `find`, `xargs`, `head`, `tail`, `sed`, `awk`) for fast streaming, batch processing, and piping instead of writing multi-step verbose scripts.
- **Scope file searches**: When searching within Python code, use `rg -g "*.py" <pattern>` or `git grep <pattern>` to avoid scanning build artifacts, caches, or `.venv`.

---

## 3. Architecture & Core Invariants

### 1. Pure-ONNX Inference Engine

- **Inference is 100% pure ONNX Runtime**: Feature extraction (`ContentVec`), pitch estimation (`RMVPE` / `FCPE`), and neural synthesis (`RVC`) run entirely on ONNX Runtime and NumPy.
- **No PyTorch in Inference Hot Paths**: PyTorch (`torch`) is strictly a CPU-only utility used during offline model import to export legacy `.pth` models to `.onnx` (`export_pth_to_onnx`). Never introduce `torch` or `torch.Tensor` into `voice_changer.py`, `rvc_pipeline.py`, or any audio streaming path.

### 2. Audio Processing Hot Path

- Audio callbacks in `local_voice_changer_interface.py` run on real-time PortAudio threads.
- Keep memory allocations inside callbacks and the conversion loop to the absolute minimum. No unnecessary copying, zero eagerly formatted debug strings, and no blocking I/O on audio threads.
- Crossfade and SOLA overlap-add algorithms in `crossfade_processor.py` manage seamless chunk stitching.

---

## 4. Strict Logging Guidelines

The logging architecture in `backend/vcclient/` is strictly centralized and performance-optimized. All agents modifying backend code must adhere to these rules:

1. **Import the Unified Singleton Logger**:

   Always import `logger` directly:

   ```python
   from vcclient.logger import logger
   ```

2. **Absolute Ban on f-strings in Logging (`logger.*`)**:

   Always use printf-style argument formatting (`%s`, `%d`, etc.):

   ```python
   # CORRECT: Lazy evaluation; arguments are not converted to strings if log level is inactive
   logger.info("Loaded model slot %s successfully from %s", slot_index, path)
   logger.error("load index failed. %s", index_file)

   # FORBIDDEN: Eager string concatenation allocates memory on every invocation, causing GC jitter in hot audio loops
   logger.info(f"Loaded model slot {slot_index} successfully from {path}")
   ```

---

## 5. Architectural Documentation & Roadmaps (`okf/`)

Architectural decisions, specifications, and migration roadmaps are maintained in the `okf/` directory (see `okf/index.md`).

- **Keep Docs in Sync with Reality**: Whenever introducing major architectural changes, refactoring core subsystems, or making progress against roadmap milestones, you **MUST** update the corresponding documents under `okf/` so they accurately match the actual codebase.
- **Distinguish Roadmap from Current State**: Always distinguish implemented features from planned roadmap goals before modifying code based on `okf/` documents.
