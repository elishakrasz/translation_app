"""state.yaml: the state of each step for each unit, and the order the steps must follow (Appendix C)."""

import datetime as dt

import yaml

# Per-unit steps in order, with the steps each needs to have passed first.
STEPS = ["clean", "chunk", "translate", "sources", "notes", "review", "style", "build", "import",
         "fidelity", "footnotes", "glosses"]
NEEDS = {
    "chunk": ["clean"], "translate": ["chunk"], "sources": ["translate"], "notes": ["sources"],
    "review": ["notes"], "style": ["review"], "build": ["style"], "import": ["build"],
    "fidelity": ["import"], "footnotes": ["fidelity"], "glosses": ["footnotes"],
}
STATES = ("blocked", "ready", "running", "awaiting-gate", "passed", "stale")


def today():
    return dt.date.today().isoformat()


class State:
    def __init__(self, project):
        self.path = project.root / "state.yaml"
        self.data = yaml.safe_load(self.path.read_text(encoding="utf-8")) if self.path.exists() else None
        self.data = self.data or {}
        self.data.setdefault("text_of_record", {"default": "chapters"})
        self.data.setdefault("units", {})
        for u in project.units:
            self.data["units"].setdefault(u["id"], {})

    def step(self, uid, step):
        return self.data["units"].get(uid, {}).get(step, {})

    def state_of(self, uid, step):
        s = self.step(uid, step).get("state")
        if s:
            return s
        return "ready" if all(self.state_of(uid, n) == "passed" for n in NEEDS.get(step, [])) else "blocked"

    def can_start(self, uid, step):
        """(True, '') or (False, a plain reason)."""
        for need in NEEDS.get(step, []):
            s = self.state_of(uid, need)
            if s != "passed":
                where = self.step(uid, need).get("report")
                wait = f" (it is waiting for your decision{f' in {where}' if where else ''})" if s == "awaiting-gate" else ""
                return False, f"{uid}: {step} needs {need} to pass first; {need} is {s}{wait}."
        return True, ""

    def set(self, uid, step, state, **extra):
        rec = {"state": state, **{k: v for k, v in extra.items() if v is not None}}
        self.data["units"].setdefault(uid, {})[step] = rec
        # A step that is redone makes every later step that already passed stale.
        if state in ("running", "awaiting-gate"):
            for later in STEPS[STEPS.index(step) + 1:]:
                if self.step(uid, later).get("state") == "passed":
                    self.data["units"][uid][later]["state"] = "stale"

    def last_passed(self, uid):
        done = [s for s in STEPS if self.state_of(uid, s) == "passed"]
        return done[-1] if done else None

    def waiting_for(self, uid):
        for s in STEPS:
            st = self.state_of(uid, s)
            if st == "awaiting-gate":
                return f"your decision on {s}" + (f" ({self.step(uid, s)['report']})" if self.step(uid, s).get("report") else "")
            if st in ("ready", "stale"):
                return f"{s} ({st})"
        return "—"

    def save(self):
        self.path.write_text(yaml.safe_dump(self.data, allow_unicode=True, sort_keys=False), encoding="utf-8")
