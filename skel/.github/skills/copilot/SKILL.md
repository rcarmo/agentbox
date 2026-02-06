---
name: Copilot instruction layering
description: instruction layering with reusable, conditional instruction files
---

# Skill: Copilot instruction layering

## Goal
Provide a small set of reusable Copilot instruction files that can be copied into new repos and applied conditionally based on project type.

## Files
- `.github/copilot-instructions.md` (high-level, Makefile-first)
- `.github/instructions/*.instructions.md` (stack-specific guidance)

## Conventions
- Keep instructions short and actionable.
- Prefer conditional language ("Applies when...") so these files can coexist in mixed repos.
