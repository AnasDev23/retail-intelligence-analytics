"""Fallback runner used only if pytest is unavailable: python -m tests.run_without_pytest"""
import importlib, sys, traceback
mods = ["tests.test_cleaning", "tests.test_kpis", "tests.test_segmentation_quality"]
passed = failed = 0
for m in mods:
    mod = importlib.import_module(m)
    for name in sorted(n for n in dir(mod) if n.startswith("test_")):
        try:
            getattr(mod, name)(); passed += 1; print("PASS", m, name)
        except Exception:
            failed += 1; print("FAIL", m, name); traceback.print_exc()
print(f"{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
