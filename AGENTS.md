# StateInk agent guide

- Phase 2 adds only the FastAPI/OpenCV recognition boundary. Keep it human-reviewed; do not add cloud vision, persistence, accounts, AI chat, or code generation.
- Keep framework-agnostic domain logic in `src/core`; React Flow types belong only in UI code. Samples are data, never special cases in the engine.
- UI copy is Japanese-first and should explain technical findings in beginner-friendly language.
- Read `docs/product.md` and `docs/architecture.md` before changing scope or boundaries.
- Run `npm run check` before committing. Add core tests for every analysis/simulation behavior change.
- Run `PYTHONPATH=backend pytest backend/tests` for recognition changes; never add fixture-name-specific recognition branches.
