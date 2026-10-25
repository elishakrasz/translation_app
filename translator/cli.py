"""The translator command line.

    translator init PATH [--title T] [--house koren]    make a project folder (never overwrites)
    translator status                                   where every unit stands; rewrites state.md
    translator doctor                                   check the Mac and the project
    translator upgrade                                  refresh the project's slash commands from the engine
    translator clean [UNITS] [--write]                  Step 1: proofread pages -> source/cleaned/ (dry run first)
    translator chunk [UNITS] [--write]                  Step 1: cleaned units -> chunks with permanent IDs
    translator gate UNIT|all STEP --accept|--reject [--note N]   record your decision at a step's gate
    translator glossary merge|page|apply [FILE] [--write]   Step 2b: the glossary and its review page
    translator translate prompts [UNITS] [--chunks 3,7]     Step 4: each chunk's prompt, from the foundations
    translator verses check|vocalise [UNITS] [--write]      check the pointed verses / point the unpointed ones, from Sefaria

UNITS: ch01, ch01,ch02, intro-ch02 or all (the default).
"""

import argparse
import sys

from . import bootstrap, chunk, clean, generate, glossary, records, translate, verses
from .project import Project, ProjectError
from .state import STEPS, State, today


def cmd_init(a):
    project, made = bootstrap.init(a.path, a.title, a.house)
    print(f"Project: {project.root}")
    print("Made: " + (", ".join(made) if made else "nothing (everything was already there)"))
    print(f"Next: put the publisher's files or scans in {project.root}/source/original/, then /ocr in Claude Code.")


def cmd_status(a):
    project = Project()
    state = State(project)
    generate.state_md(project, state)
    print(f"{project.title}  ({project.root})\n")
    width = max(len(u["id"]) for u in project.units) if project.units else 4
    print(f"{'unit':<{width}}  {'last passed':<12}  waiting for")
    for u in project.units:
        print(f"{u['id']:<{width}}  {state.last_passed(u['id']) or '—':<12}  {state.waiting_for(u['id'])}")
    v = bootstrap.commands_version(project)
    from . import __version__
    if v != __version__:
        print(f"\n⚠ The project's slash commands are from engine {v}; the engine is {__version__}. Run `translator upgrade`.")


def cmd_doctor(a):
    try:
        project = Project()
    except ProjectError:
        project = None
    bad = 0
    for ok, what, detail in bootstrap.doctor(project):
        mark = "✓" if ok else ("·" if ok is None else "✗")
        bad += ok is False
        print(f"{mark} {what}" + (f"  — {detail}" if detail and not ok or (ok and detail and what.startswith(('Python', 'LibreOffice'))) else ""))
    print("\nAll required checks pass." if not bad else f"\n{bad} required check(s) failed.")
    return 1 if bad else 0


def cmd_upgrade(a):
    project = Project()
    made = bootstrap.upgrade(project)
    generate.claude_md(project)
    generate.state_md(project)
    print("Updated: " + (", ".join(made) if made else "nothing; already current"))


def refuse_if_blocked(state, units, step, force):
    blocked = [msg for u in units for ok, msg in [state.can_start(u["id"], step)] if not ok]
    if blocked and not force:
        for msg in blocked:
            print("✗ " + msg)
        sys.exit(1)


def cmd_clean(a):
    project = Project()
    units = project.select(a.units)
    state = State(project)
    done = [u["id"] for u in units if project.unit_dir(u).joinpath("blocks.jsonl").exists()]
    if done and a.write and not a.force:
        sys.exit(f"✗ {', '.join(done)} already chunked: its IDs are permanent, so its source isn't re-cleaned here.")
    results, rep, problems = clean.run(project, units, write=a.write)
    for p in problems:
        print("✗ " + p)
    for r in results:
        status = f"{len(r.errors)} error(s)" if r.errors else "ok"
        print(f"{r.unit['id']:<8} pages {r.pages[0] if r.pages else '—'}–{r.pages[-1] if r.pages else '—'}  "
              f"blocks {sum(1 for b in r.blocks if b.kind != 'page')}  notes {len(r.notes)}  {status}")
    print(f"\nReport: {rep.relative_to(project.root)}")
    failed = problems or any(r.errors for r in results)
    if a.write and not failed:
        for r in results:
            state.set(r.unit["id"], "clean", "awaiting-gate", report=str(rep.relative_to(project.root)), date=today())
        state.save()
        generate.state_md(project, state)
        print("Written to source/cleaned/. Each unit now waits for your decision: "
              "`translator gate <unit> clean --accept` once you have read it.")
    elif a.write:
        print("Nothing written: fix the errors in the report first.")
    else:
        print("Dry run: previews in work/clean/preview/. Run again with --write to write source/cleaned/.")
    return 1 if failed else 0


def cmd_chunk(a):
    project = Project()
    units = project.select(a.units)
    state = State(project)
    refuse_if_blocked(state, units, "chunk", a.force)
    bad = 0
    for u in units:
        summary, problem = chunk.run(project, u, write=a.write)
        if problem:
            print("✗ " + problem)
            bad += 1
            continue
        if summary["unchanged"]:
            print(f"{u['id']:<8} already chunked, unchanged ({summary['blocks']} blocks)")
            continue
        sizes = ", ".join(f"{n}:{c}" for n, c, *_ in summary["chunks"])
        print(f"{u['id']:<8} {summary['blocks']} blocks ({summary['notes']} notes) → {len(summary['chunks'])} chunks "
              f"[blocks:chars {sizes}]")
        if a.write:
            state.set(u["id"], "chunk", "passed", date=today(), note="IDs assigned")
    if a.write:
        state.save()
        generate.state_md(project, state)
        print("\nWritten to units/. IDs are now permanent.")
    else:
        print("\nDry run: nothing written. Run again with --write to write units/ and assign the IDs.")
    return 1 if bad else 0


def cmd_gate(a):
    project = Project()
    units = project.select(a.unit)
    state = State(project)
    rows = []
    for u in units:
        s = state.state_of(u["id"], a.step)
        if s != "awaiting-gate":
            print(f"✗ {u['id']}: {a.step} is {s}, not waiting for a decision")
            continue
        new = "passed" if a.accept else "ready"
        state.set(u["id"], a.step, new, date=today(), note=a.note, report=state.step(u["id"], a.step).get("report"))
        rows.append({"step": a.step, "unit": u["id"], "question": f"pass the {a.step} gate?",
                     "answer": "accepted" if a.accept else "rejected", "note": a.note})
        print(f"{u['id']}: {a.step} {'passed' if a.accept else 'sent back (ready to redo)'}")
    if rows:
        records.append(project, "decisions", rows, by="translator gate")
        state.save()
        generate.state_md(project, state)


def cmd_glossary(a):
    project = Project()
    if a.action == "merge":
        labels, merged = glossary.merge(project)
        s = glossary.summary(labels, merged)
        print(f"Merged {', '.join(labels)}: {s['terms']} terms — {s['agree']} agree, {s['differ']} differ, "
              f"{s['only_one']} found by one extractor; {s['in_reference']} also in a reference glossary.")
        print("By category: " + ", ".join(f"{k} {v}" for k, v in s["by_category"].items()))
        print("Written: work/glossary/merged.json. Next: `translator glossary page`.")
    elif a.action == "page":
        out, s = glossary.page(project)
        print(f"Review page: {out.relative_to(project.root)} ({s['terms']} terms). Open it, decide, and download "
              f"the decisions; then `translator glossary apply <glossary-decisions.json>`.")
    elif a.action == "apply":
        if not a.file:
            sys.exit("✗ apply needs the decisions file the review page downloaded")
        terms, problems, undecided, resolved = glossary.apply(project, a.file, write=a.write)
        for alias, term in resolved:
            print(f"· {alias!r} dropped as an alias of {term!r}: it has its own entry")
        for p in problems:
            print("✗ " + p)
        print(f"{len(terms)} terms to write; {len(undecided)} not decided yet.")
        if a.write and not problems:
            print("Written: terms/glossary.json.")
        elif not a.write:
            print("Dry run: run again with --write to write terms/glossary.json.")
        return 1 if problems else 0


def cmd_translate(a):
    project = Project()
    units = project.select(a.units)
    state = State(project)
    refuse_if_blocked(state, units, "translate", a.force)
    try:
        f = translate.foundations(project)
    except translate.FoundationsMissing as e:
        sys.exit(f"✗ {e}")
    chunks = [c for c in a.chunks.split(",")] if a.chunks else None
    for u in units:
        built = translate.build(project, u, f, chunks)
        terms = sum(b[2] for b in built)
        print(f"{u['id']:<8} {len(built)} prompts → {(project.work('translate') / project.unit_name(u)).relative_to(project.root)}/"
              f"  (term-table rows {terms}, decided terms {sum(b[3] for b in built)})")


def cmd_verses(a):
    project = Project()
    for u in project.select(a.units):
        if not list(project.unit_dir(u).glob("output_chunk*.md")):
            continue
        if a.action == "vocalise":
            changes = verses.vocalise(project, u, write=a.write)
            print(f"{u['id']}: {len(changes)} unpointed verse quotation(s) " + ("vocalised" if a.write else "to vocalise"))
            for bid, ref, before, after in changes:
                print(f"  {bid} {ref}: {before}  →  {after}")
            if changes and not a.write:
                print("  Dry run: --write applies them and records them in edits.jsonl.")
            continue
        fixes, singles, missing, chapters = verses.check(project, u, write=a.write)
        print(f"{u['id']}: {len(chapters)} chapters checked against Sefaria — {len(fixes)} correction(s), "
              f"{len(singles)} single word(s) differing, {len(missing)} phrase(s) not found")
        for _, bid, ref, before, after in fixes:
            print(f"  fix  {bid} {ref}: {before}  →  {after}")
        for _, bid, ref, before, good in singles:
            print(f"  word {bid} {ref}: {before} (Sefaria: {good}) — left as it is")
        for _, bid, run in missing:
            print(f"  ?    {bid}: {run}")
        if not a.write and fixes:
            print("  Dry run: --write applies the corrections and records them in edits.jsonl.")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="translator", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init", help="make a project folder")
    p.add_argument("path")
    p.add_argument("--title")
    p.add_argument("--house", default="koren")
    sub.add_parser("status", help="where every unit stands")
    sub.add_parser("doctor", help="check the Mac and the project")
    sub.add_parser("upgrade", help="refresh the project's slash commands")
    for name, help_ in (("clean", "Step 1: proofread pages -> cleaned units"), ("chunk", "Step 1: chunks and IDs")):
        p = sub.add_parser(name, help=help_)
        p.add_argument("units", nargs="?", default="all")
        p.add_argument("--write", action="store_true", help="write the files (default: dry run)")
        p.add_argument("--force", action="store_true", help="for emergencies; recorded")
    p = sub.add_parser("gate", help="record your decision at a gate")
    p.add_argument("unit")
    p.add_argument("step", choices=STEPS)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--accept", action="store_true")
    g.add_argument("--reject", action="store_true")
    p.add_argument("--note")
    p = sub.add_parser("translate", help="Step 4: build each chunk's prompt from the foundations")
    p.add_argument("action", choices=["prompts"])
    p.add_argument("units", nargs="?", default="all")
    p.add_argument("--chunks", help="only these chunks, e.g. 3,7")
    p.add_argument("--force", action="store_true")
    p = sub.add_parser("verses", help="check the vocalised Bible verses against Sefaria")
    p.add_argument("action", choices=["check", "vocalise"])
    p.add_argument("units", nargs="?", default="all")
    p.add_argument("--write", action="store_true")
    p = sub.add_parser("glossary", help="Step 2b: merge the extractions, build the review page, apply decisions")
    p.add_argument("action", choices=["merge", "page", "apply"])
    p.add_argument("file", nargs="?", help="for apply: the downloaded glossary-decisions.json")
    p.add_argument("--write", action="store_true")
    a = ap.parse_args(argv)
    try:
        return {"init": cmd_init, "status": cmd_status, "doctor": cmd_doctor, "upgrade": cmd_upgrade,
                "clean": cmd_clean, "chunk": cmd_chunk, "gate": cmd_gate, "glossary": cmd_glossary, "translate": cmd_translate, "verses": cmd_verses}[a.cmd](a) or 0
    except ProjectError as e:
        sys.exit(f"✗ {e}")


if __name__ == "__main__":
    sys.exit(main())
