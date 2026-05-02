# Pipeline Prompts

This directory holds editable prompt templates. The pipeline reads them at runtime, so you can iterate without touching the Python code.

## Versioning rule

Each prompt has a `prompt_version` constant defined in the Python that uses it (`PROMPT_VERSION = "enrich_v1.0"` etc.). When you meaningfully edit a prompt, **bump the version**. The next pipeline run will then re-process records that were enriched at older versions, while skipping ones already at the new version.

## Files

| File | Used by | Purpose |
|---|---|---|
| `enrich_system.md` | `03_enrich.py` | The system prompt for the enrichment LLM call. Defines required output fields and reasoning rules. |
| `synth_gap.md` | `04_synth.py` | The system prompt for the gap-finding synthesis report. |

## How to edit safely

1. Read the existing prompt and proposed changes side-by-side.
2. Edit the `.md` file.
3. Bump the `PROMPT_VERSION` constant in the corresponding Python file.
4. Run `python 03_enrich.py` (or `04_synth.py`) — only previously-stale records get re-processed.

## Cost discipline

Prompts that grow without limit blow up token costs. Two rules:

- **Truncate per-record context** going INTO the prompt. The pipeline already truncates `description` to 1500 chars and `anticipated_benefits` to 800 chars per record. Don't pass the full `raw_path` JSON.
- **Constrain output** to JSON. The system prompt asks for `{"results": [...]}` shape — keep it that way.
