"""The translator command line.

    translator init PATH [--title T] [--house koren]    make a project folder (never overwrites)
    translator status                                   where every unit stands; rewrites state.md
    translator doctor                                   check the Mac and the project
    translator upgrade                                  refresh the project's slash commands from the engine
    translator clean [UNITS] [--write]                  Step 1: proofread pages -> source/cleaned/ (dry run first)
    translator chunk [UNITS] [--write]                  Step 1: cleaned units -> chunks with permanent IDs
    translator gate UNIT|all STEP --accept|--reject [--note N]   record your decision at a step's gate (refused while `check` has errors)
    translator check [UNITS]                                every check: structure, quotation lock, style, bibliography
    translator glossary merge|page|apply [FILE] [--write]   Step 2b: the glossary and its review page
    translator translate prompts [UNITS] [--chunks 3,7]     Step 4: each chunk's prompt, from the foundations
    translator verses check|vocalise [UNITS] [--write]      check the pointed verses / point the unpointed ones, from Sefaria
    translator sources list|find|text|integrate …          Step 5: provisional quotations → verified originals
    translator notes input|page|write UNIT [FILE] [--write] Step 6: the notes in house style, and the bibliography
    translator review pairs|page|apply|stats [UNIT] [FILE]  Step 8: two reviewers' findings, your decisions
    translator style pairs|page|apply UNIT [FILE]           Step 9: the five style passes, your decisions
    translator build koren [UNITS]                          Step 10: the Koren draft, docx + pdf, bookmarked by block ID

UNITS: ch01, ch01,ch02, intro-ch02 or all (the default).
"""

import argparse
import sys

from . import bootstrap, check, chunk, clean, generate, glossary, notes, records, review, sources, translate, verses
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
    results = check.run(project, units) if a.accept else {}
    for u in units:
        if a.accept and (errs := check.errors(results, u["id"])):
            print(f"✗ {u['id']}: {len(errs)} error(s) from `translator check` — the gate can't pass until they're fixed")
            for _, name, where, msg in errs[:10]:
                print(f"    {name} {where}: {msg}")
            continue
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


def cmd_sources(a):
    project = Project()
    if a.action == "find":
        for ref, version, snippet in sources.find(" ".join(a.args), size=a.size):
            print(f"{ref}  [{version}]\n    {snippet}")
        return
    if a.action == "text":
        t = sources.text(" ".join(a.args))
        print(f"{t['ref']}  [{t['version']}]")
        for i, seg in enumerate(t["segments"], 1):
            print(f"  {i}: {seg}")
        return
    unit = project.unit(a.args[0]) if a.args else sys.exit("✗ name the unit")
    if a.action == "list":
        items, out = sources.write_list(project, unit)
        print(f"{unit['id']}: {len(items)} provisional quotation(s) → {out.relative_to(project.root)}")
        return
    bundles = a.args[1:] or sorted(str(p) for p in project.work("sources").glob(f"{unit['id']}-bundle*.json"))
    state = State(project)
    refuse_if_blocked(state, [unit], "sources", a.force)
    bad = 0
    for b in bundles:
        for item, status, detail in sources.integrate(project, unit, b, write=a.write):
            bad += status == "FAILS"
            print(f"  {status:<14} {item:<16} {detail}")
    if a.write and not bad:
        print("Written. The quotations are recorded in records/quotations.jsonl: they are now locked.")
    elif bad:
        print(f"✗ {bad} entr(ies) fail: nothing written. Fix the bundle and run again.")
    else:
        print("Dry run: --write puts the verified originals in.")


def cmd_notes(a):
    project = Project()
    unit = project.unit(a.unit)
    if a.action == "input":
        refuse_if_blocked(State(project), [unit], "notes", a.force)
        items, out = notes.write_input(project, unit)
        print(f"{unit['id']}: {len(items)} notes → {out.relative_to(project.root)} ({sum(bool(i['locked']) for i in items)} with locked quotations)")
    elif a.action == "page":
        out, n, changed = notes.page(project, unit)
        print(f"Review page: {out.relative_to(project.root)} ({n} notes, {changed} changed). Decide, download the decisions, "
              f"then `translator notes write {unit['id']} <notes-decisions-{unit['id']}.json> --write`.")
    else:
        if not a.file:
            sys.exit("✗ write needs the decisions file the review page downloaded")
        applied, problems = notes.write(project, unit, a.file, write=a.write)
        for p in problems:
            print("✗ " + p)
        print(f"{len(applied)} note(s) to change." + ("" if a.write else " Dry run: --write applies them."))
        if a.write and not problems:
            state = State(project)
            state.set(unit["id"], "notes", "awaiting-gate", report=f"review/notes/{unit['id']}/", date=today())
            state.save()
            generate.state_md(project, state)
            print("Written. The notes wait at the gate: `translator gate " + unit["id"] + " notes --accept`.")
        return 1 if problems else 0


def cmd_check(a):
    project = Project()
    results = check.run(project, project.select(a.units))
    bad = 0
    for uid, rows in results.items():
        if not rows:
            continue
        e = [r for r in rows if r[0] == "error"]
        flags = sum(int(r[3].split()[0]) for r in rows if r[1] == "flags")
        print(f"{uid}: {len(e)} error(s), {flags} open flag(s)")
        for level, name, where, msg in rows:
            if level != "info":
                print(f"  {level:<7} {name:<11} {where:<14} {msg}")
        bad += len(e)
    print("All checks pass." if not bad else f"{bad} error(s).")
    return 1 if bad else 0


def cmd_review(a):
    project = Project()
    if a.action == "stats":
        for reviewer, cats in review.stats(project).items():
            print(reviewer)
            for cat, d in sorted(cats.items()):
                total = sum(d.values())
                print(f"  {cat:<16} {total:>3}  " + "  ".join(f"{k} {v}" for k, v in sorted(d.items())))
        return
    unit = project.unit(a.unit)
    if a.action == "external":
        from . import external
        print(f"{unit['id']}: reviewer '{a.name}' = {a.provider} {a.model}")
        path, found, usage, bad = external.review(project, unit, a.provider, a.model, a.name)
        print(f"{len(found)} finding(s) → {path.relative_to(project.root)}; tokens in {usage['prompt_tokens']}, "
              f"out {usage['completion_tokens']}" + (f"; {bad} batch(es) not valid JSON" if bad else ""))
        print("Rebuild the page: `translator review page " + unit["id"] + "`.")
        return
    if a.action == "pairs":
        refuse_if_blocked(State(project), [unit], "review", a.force)
        items, md = review.write_pairs(project, unit)
        print(f"{unit['id']}: {len(items)} pairs → {md.relative_to(project.root)} "
              f"({sum(bool(i['locked']) for i in items)} blocks with locked quotations)")
    elif a.action == "page":
        out, summary, problems = review.page(project, unit)
        for p in problems:
            print("  · " + p)
        print(summary)
        print(f"Review page: {out.relative_to(project.root)}. Decide, download, then `translator review apply {unit['id']} <file> --write`.")
    else:
        if not a.file:
            sys.exit("✗ apply needs the decisions file the review page downloaded")
        applied, problems = review.apply(project, unit, a.file, write=a.write)
        for p in problems:
            print("✗ " + p)
        print(f"{len(applied)} change(s) to make." + ("" if a.write else " Dry run: --write makes them."))
        if a.write and not problems:
            state = State(project)
            state.set(unit["id"], "review", "awaiting-gate", report=f"review/review/{unit['id']}/", date=today())
            state.save()
            generate.state_md(project, state)
            print("Written, and every finding recorded with its decision. Gate: `translator gate " + unit["id"] + " review --accept`.")
        return 1 if problems else 0


def cmd_style(a):
    project = Project()
    unit = project.unit(a.unit)
    if a.action == "pairs":
        refuse_if_blocked(State(project), [unit], "style", a.force)
        items, md = review.write_pairs(project, unit, step="style")
        print(f"{unit['id']}: {len(items)} pairs → {md.relative_to(project.root)}")
    elif a.action == "page":
        out, summary, problems = review.page(project, unit, step="style")
        for p in problems:
            print("  · " + p)
        print(summary)
        print(f"Style page: {out.relative_to(project.root)}. Decide, download, then `translator style apply {unit['id']} <file> --write`.")
    else:
        if not a.file:
            sys.exit("✗ apply needs the decisions file the style page downloaded")
        applied, problems = review.apply(project, unit, a.file, write=a.write, step="style")
        for p in problems:
            print("✗ " + p)
        print(f"{len(applied)} change(s) to make." + ("" if a.write else " Dry run: --write makes them."))
        if a.write and not problems:
            state = State(project)
            state.set(unit["id"], "style", "awaiting-gate", report=f"review/style/{unit['id']}/", date=today())
            state.save()
            generate.state_md(project, state)
            print("Written. Gate: `translator gate " + unit["id"] + " style --accept`.")
        return 1 if problems else 0


def cmd_build(a):
    from . import build
    project = Project()
    state = State(project)
    for u in project.select(a.units):
        ok, msg = state.can_start(u["id"], "build")
        if not ok and not a.force:
            print("✗ " + msg)
            continue
        try:
            r = build.build(project, u)
        except RuntimeError as e:
            print(f"✗ {u['id']}: {e}")
            continue
        problems = ([f"notes referenced but missing: {r['missing_notes']}"] if r["missing_notes"] else []) + \
                   ([f"{len(r['missing_bookmarks'])} block(s) without a bookmark: {r['missing_bookmarks'][:5]}"] if r["missing_bookmarks"] else []) + \
                   ([f"blank page(s) in the pdf: {r['blank_pages']}"] if r.get("blank_pages") else [])
        print(f"{u['id']}: {r['docx'].relative_to(project.root)} — {r['paragraphs']} paragraphs, {r['notes']} notes, "
              f"{r['bookmarks']} bookmarks" + (f", {r['pages']} pages (pdf)" if r.get("pages") else ""))
        for p in problems:
            print("  ✗ " + p)
        if r["unused_notes"]:
            print(f"  · notes with no reference in the text: {r['unused_notes']}")
        if not problems:
            state.set(u["id"], "build", "awaiting-gate", report=str(r["docx"].relative_to(project.root)), date=today(),
                      sha256=r["sha256"])
    state.save()
    generate.state_md(project, state)


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
    p = sub.add_parser("review", help="Step 8: pairs for the reviewers, the review page, applying decisions, statistics")
    p.add_argument("action", choices=["pairs", "page", "apply", "stats", "external"])
    p.add_argument("--provider", default="openai")
    p.add_argument("--model", default="gpt-6.1-sol")
    p.add_argument("--name", default="openai")
    p.add_argument("unit", nargs="?")
    p.add_argument("file", nargs="?")
    p.add_argument("--write", action="store_true")
    p.add_argument("--force", action="store_true")
    p = sub.add_parser("style", help="Step 9: the style passes — pairs, page, apply")
    p.add_argument("action", choices=["pairs", "page", "apply"])
    p.add_argument("unit")
    p.add_argument("file", nargs="?")
    p.add_argument("--write", action="store_true")
    p.add_argument("--force", action="store_true")
    p = sub.add_parser("build", help="Step 10: the Koren draft (docx + pdf), every block bookmarked by its ID")
    p.add_argument("target", choices=["koren"])
    p.add_argument("units", nargs="?", default="all")
    p.add_argument("--force", action="store_true")
    p = sub.add_parser("check", help="every check on the text: structure, quotation lock, style, bibliography")
    p.add_argument("units", nargs="?", default="all")
    p = sub.add_parser("notes", help="Step 6: the notes in house style, and the bibliography")
    p.add_argument("action", choices=["input", "page", "write"])
    p.add_argument("unit")
    p.add_argument("file", nargs="?", help="for write: the downloaded notes-decisions file")
    p.add_argument("--write", action="store_true")
    p.add_argument("--force", action="store_true")
    p = sub.add_parser("sources", help="Step 5: list the provisional quotations, find originals on Sefaria, put them in")
    p.add_argument("action", choices=["list", "find", "text", "integrate"])
    p.add_argument("args", nargs="*", help="list/integrate: UNIT [bundle…]; find: Hebrew words; text: a Sefaria ref")
    p.add_argument("--size", type=int, default=8)
    p.add_argument("--write", action="store_true")
    p.add_argument("--force", action="store_true")
    p = sub.add_parser("glossary", help="Step 2b: merge the extractions, build the review page, apply decisions")
    p.add_argument("action", choices=["merge", "page", "apply"])
    p.add_argument("file", nargs="?", help="for apply: the downloaded glossary-decisions.json")
    p.add_argument("--write", action="store_true")
    a = ap.parse_args(argv)
    try:
        return {"init": cmd_init, "status": cmd_status, "doctor": cmd_doctor, "upgrade": cmd_upgrade,
                "clean": cmd_clean, "chunk": cmd_chunk, "gate": cmd_gate, "glossary": cmd_glossary, "translate": cmd_translate, "verses": cmd_verses, "sources": cmd_sources, "notes": cmd_notes, "check": cmd_check, "review": cmd_review, "style": cmd_style, "build": cmd_build}[a.cmd](a) or 0
    except ProjectError as e:
        sys.exit(f"✗ {e}")


if __name__ == "__main__":
    sys.exit(main())
