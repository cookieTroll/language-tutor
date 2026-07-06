"""
Repeats each judge evaluator N times to measure variance in judge verdicts and
executor output quality across runs. Config lives in a YAML file (default:
scripts/judge_variance.yaml) — see that file for the parameters.

Processes one judge module fully (all executor/judge config combos x all repeats)
before moving to the next, so a crash partway through the batch still leaves
every already-finished judge's result JSONs on disk.

Each repeat is tagged (via env vars LTUT_BATCH_ID / LTUT_REPEAT_INDEX, picked up
by tests/judge/utils.run_metadata()) so its output JSON records which batch,
repeat index, and model configs produced it — needed to group repeats together
and compare across model sweeps during expost analysis.

Usage:
    python -m scripts.run_judge_variance
    python -m scripts.run_judge_variance --config scripts/judge_variance.yaml
    python -m scripts.run_judge_variance --dry-run
"""
import argparse
import datetime
import itertools
import os
import subprocess
import sys

import yaml

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CONFIG = os.path.join(PROJECT_ROOT, "scripts", "judge_variance.yaml")


def _load_config(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    cfg.setdefault("repeats", 1)
    cfg.setdefault("executor_configs", ["config.test.yaml"])
    cfg.setdefault("judge_configs", ["config.test.yaml"])
    cfg.setdefault("case_filter", None)
    cfg.setdefault("on_error", "continue")
    cfg.setdefault("log_dir", "tests/judge/results/logs")
    if not cfg.get("judges"):
        raise ValueError(f"{path}: 'judges' must list at least one judge module")
    if cfg["on_error"] not in ("continue", "stop"):
        raise ValueError(f"{path}: on_error must be 'continue' or 'stop', got {cfg['on_error']!r}")
    return cfg


def _slug(config_path: str) -> str:
    return os.path.splitext(os.path.basename(config_path))[0]


def _run_one(judge: str, executor_cfg: str, judge_cfg: str, repeat_i: int, total_repeats: int,
             batch_id: str, cfg: dict) -> int:
    module_path = os.path.join("tests", "judge", f"{judge}.py")
    if not os.path.isfile(os.path.join(PROJECT_ROOT, module_path)):
        print(f"  [!] {module_path} not found - skipping")
        return 127

    args = [sys.executable, "-m", "pytest", module_path, "-v", "-s", "-m", "judge"]
    if cfg["case_filter"]:
        args += ["-k", cfg["case_filter"]]

    env = os.environ.copy()
    env["LTUT_CONFIG"] = executor_cfg
    env["LTUT_JUDGE_CONFIG"] = judge_cfg
    env["LTUT_BATCH_ID"] = batch_id
    env["LTUT_REPEAT_INDEX"] = str(repeat_i)

    log_dir = os.path.join(PROJECT_ROOT, cfg["log_dir"], batch_id)
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, f"{judge}_{_slug(executor_cfg)}_{_slug(judge_cfg)}_rep{repeat_i}.log")

    print(f"  repeat {repeat_i}/{total_repeats}  executor={executor_cfg}  judge={judge_cfg}  -> {log_path}")
    with open(log_path, "w", encoding="utf-8") as log_f:
        result = subprocess.run(args, cwd=PROJECT_ROOT, env=env, stdout=log_f, stderr=subprocess.STDOUT)

    if result.returncode == 0:
        print("    -> all cases PASS/PARTIAL")
    elif result.returncode == 1:
        print("    -> at least one case FAILed its verdict assertion (recorded in the result JSON, not a crash)")
    else:
        print(f"    -> CRASH (pytest exit {result.returncode}) - see {log_path}")
    return result.returncode


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default=DEFAULT_CONFIG, help="Path to the YAML run config")
    parser.add_argument("--dry-run", action="store_true", help="Print the run plan without invoking pytest")
    args = parser.parse_args()

    cfg = _load_config(args.config)
    batch_id = str(cfg.get("batch_id") or datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))

    combos = list(itertools.product(cfg["executor_configs"], cfg["judge_configs"]))
    total_runs = len(cfg["judges"]) * len(combos) * cfg["repeats"]

    print(f"Batch: {batch_id}")
    print(f"{len(cfg['judges'])} judge(s) x {len(combos)} config combo(s) x {cfg['repeats']} repeat(s) "
          f"= {total_runs} pytest invocations")

    if args.dry_run:
        for judge in cfg["judges"]:
            for executor_cfg, judge_cfg in combos:
                for repeat_i in range(1, cfg["repeats"] + 1):
                    print(f"  [dry-run] {judge}  executor={executor_cfg}  judge={judge_cfg}  repeat={repeat_i}")
        return

    crashes = []
    soft_fails = []
    for judge in cfg["judges"]:
        print(f"\n=== {judge} ===")
        for executor_cfg, judge_cfg in combos:
            for repeat_i in range(1, cfg["repeats"] + 1):
                rc = _run_one(judge, executor_cfg, judge_cfg, repeat_i, cfg["repeats"], batch_id, cfg)
                run_id = (judge, executor_cfg, judge_cfg, repeat_i)
                if rc == 1:
                    soft_fails.append(run_id)
                elif rc != 0:
                    crashes.append(run_id + (rc,))
                    if cfg["on_error"] == "stop":
                        print("\non_error=stop - aborting remaining runs. "
                              "Result JSONs for already-completed judges are still on disk.")
                        _print_summary(batch_id, total_runs, soft_fails, crashes)
                        sys.exit(1)

    _print_summary(batch_id, total_runs, soft_fails, crashes)


def _print_summary(batch_id: str, total_runs: int, soft_fails: list, crashes: list) -> None:
    print(f"\nBatch {batch_id}: {total_runs - len(soft_fails) - len(crashes)} clean, "
          f"{len(soft_fails)} with a FAIL verdict, {len(crashes)} crashed.")
    if crashes:
        print("Crashed runs (no result JSON written for these):")
        for judge, executor_cfg, judge_cfg, repeat_i, rc in crashes:
            print(f"  - {judge} executor={executor_cfg} judge={judge_cfg} repeat={repeat_i} (exit {rc})")
    print(f"Result JSONs: tests/judge/results/*.json - filter on metadata.batch_id == '{batch_id}'")


if __name__ == "__main__":
    main()
