---
description: Step 1 — chunk the cleaned units and assign the permanent block IDs (dry run first)
argument-hint: [unit | unit,unit | all]
---
Run `{{TRANSLATOR}} chunk $ARGUMENTS` in the project folder (a dry run) and show me, per unit, the blocks, notes and
chunk sizes. A unit whose clean gate hasn't passed is refused; tell me which.

IDs are permanent once written, so run `--write` only when I say so. After writing, show `translator status`.
