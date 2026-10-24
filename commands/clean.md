---
description: Step 1 — clean the proofread pages into one file per unit (dry run first)
argument-hint: [unit | unit,unit | all]
---
Run `{{TRANSLATOR}} clean $ARGUMENTS` in the project folder. This is a dry run: it writes previews to
work/clean/preview/ and the report to work/clean/report.md.

Read the report and tell me, per unit: errors (these stop the step), warnings, the headings found, what was
dropped as running heads or labels, and every hyphen kept at a line break. Look at the start and end of each
preview, and at two page joins, and tell me if anything looks wrong. Don't fix the source by hand.

When I say so, run it again with `--write`. Then each unit waits at the clean gate for my decision; I run
`translator gate <unit> clean --accept` myself.
