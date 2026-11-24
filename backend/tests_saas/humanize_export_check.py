# In-process check: does the display-name pass alter exported dbt/Databricks code or other technical strings?
import sys
sys.path.insert(0, "/app/backend")
from app.config import settings
from app.store import Store
from app.engine import TrustEngine
from app import exports as exporter_mod
from app.humanize import humanize

store = Store.from_dir(settings.data_dir)
eng = TrustEngine(store, settings.now)
exp = getattr(exporter_mod, "export", None) or exporter_mod
changed = 0
for mid in list(store.metrics):
    for f in ("dbt", "databricks"):
        try:
            raw = exporter_mod.export(store, mid, f)
        except Exception as e:  # noqa
            print("ERR", mid, f, e); continue
        h = humanize(raw, store)
        if h != raw:
            changed += 1
            print("CHANGED export", mid, f)
for m in store.metrics.values():
    f = getattr(m, "formula", "")
    if f and humanize(f, store) != f:
        print("CHANGED formula", m.id, repr(f), "->", repr(humanize(f, store)))
print("exports changed:", changed)
ids = [i for i, (_t, n) in store.node_names.items() if n and n != i and "_" in i]
print("rewritable ids:", len(ids), ids[:40])
