## Description

Briefly describe the change, its rationale, and what issue or feature it resolves.

## Type of Change

- [ ] Bug fix (non-breaking change which fixes an issue)
- [ ] New feature (non-breaking change which adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] Documentation update
- [ ] Architecture refactor / deep module decomposition

## Checklist

- [ ] My code follows the repository's coding standards.
- [ ] Universal File Line Budget (ADR 0057 / AGENTS.md): No modified or added Python file exceeds 500 lines.
- [ ] I have executed `pytest tests/test_standards.py` and all line budgets pass.
- [ ] I have run the full hermetic test suite with `pytest` and all unit tests pass cleanly.
- [ ] I have updated relevant documentation (`readme.md`, `GLOSSARY.md`, ADRs) if applicable.
