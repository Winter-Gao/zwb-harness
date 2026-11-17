"""SDK entry points for the official CPU trainer included in image 6."""
import json
import os
import tempfile
from functools import lru_cache
from pathlib import Path

from baselines.model import Model, checkpoint_digest
from baselines.predict import predict as baseline_predict
from baselines.train import train_run
from pytrio_tools import parse_strategy


PREDICT_ARGV = ["python3", "/app/harness.py", "predict"]
CONFIGS = Path(__file__).resolve().parent / "configs"


def bearing_trial(rnd, parent, history, trials):
    def summary(t):
        return {k: t[k] for k in ("learning_rate", "batch_size", "initial_epochs",
                                  "final_epochs", "validation_after") if k in t}

    meta = Model.load(parent).meta
    recent = []
    for item in history[-3:]:
        config = item.get("configuration") or {}
        recent.append({"reason": str(item.get("reason", ""))[:300],
                       "trials": [summary(t) for t in config.get("trials", [])[:3]]})
    context = {"round": rnd.round_index, "objective": "Minimize bearing RUL RMSE in minutes",
               "parent": {k: meta[k] for k in ("learning_rate", "epochs", "batch_size")},
               "parent_validation": trials[0]["validation_before"], "train_rows": trials[0]["train_rows"],
               "completed_fixed_trials": [summary(t) for t in trials], "recent_rounds": recent}
    prompt = (
        'Propose one complementary third trial from the same parent. Return one line: '
        'experiment(name="trial", data="full", epochs=2, learning_rate=0.0005, '
        'batch_size=256, reason="explain your choice"). Use 1-8 epochs, learning rate '
        '0.00001-0.003, and batch size 64, 128 or 256. Choose different parameters '
        'from both fixed trials. The best public RMSE is adopted if it matches or beats the parent.\n'
        + json.dumps(context, allow_nan=False))
    receipt = rnd.model([{"role": "user", "content": prompt}], temperature=0,
                        max_tokens=min(1024, rnd.max_output_tokens), enable_thinking=False)
    source = receipt.text.strip()
    if source.startswith(("```python\n", "```\n")) and source.endswith("```"):
        source = source.split("\n", 1)[1][:-3].strip()
    try:
        proposal, = parse_strategy(source, data_strategies=("full",))
        params = proposal["learning_rate"], proposal["epochs"], proposal["batch_size"]
        if any(params == (t["learning_rate"], t["final_epochs"] - t["initial_epochs"], t["batch_size"])
               for t in trials):
            raise ValueError("duplicate fixed trial")
        return params, receipt, proposal["name"], True, proposal["reason"]
    except ValueError as error:
        return (0.0005, 2, 256), receipt, "conservative", False, f"Fallback: {error}"


def train(rnd):
    key = rnd.dataset_key
    if key not in ("A", "B", "C"):
        raise ValueError("unknown dataset")
    profile = CONFIGS / (key + ".json")
    defaults = json.loads(profile.read_bytes())
    if defaults["task"] != rnd.task["task"]:
        raise ValueError("platform task differs from baseline profile")
    parent = rnd.parent.path("checkpoint.npz")
    parent_digest = checkpoint_digest(parent)
    metric = "macro_f1" if defaults["task"] == "classification" else "rmse"
    higher = metric == "macro_f1"
    history = rnd.history()
    short = (0.00025, 1, 256)
    regular = (0.001, 3, 128)
    alternatives = {"conservative": (0.0005, 2, 256), "standard": (0.0015, 3, 128)}
    prompt = {
        "dataset": key, "round": rnd.round_index, "metric": metric,
        "recent_rounds": [str(row.get("reason", ""))[:300] for row in history[-3:]],
        "fixed_trials_lr_epochs_batch": [short, regular],
        "third_trial_options": alternatives,
        "request": "Choose a complementary third trial. Reply only conservative or standard.",
    }
    plans = [short, regular]
    rationale = "Compare short and longer updates from the same mounted parent."
    if key != "B":
        receipt = rnd.model([{"role": "user", "content": json.dumps(prompt)}],
                            max_tokens=min(128, rnd.max_output_tokens), temperature=0)
        reply = receipt.text.strip().strip('"').lower()
        recognized = reply in alternatives
        option = reply if recognized else "conservative"
        plans.append(alternatives[option])
    work = Path(os.environ.get("CONTEST_WORK", "/workspace"))
    work.mkdir(exist_ok=True, parents=True)
    root = Path(tempfile.mkdtemp(prefix="trials-", dir=work))
    trials = []
    for index in range(3):
        if key == "B" and index == 2:
            third, receipt, option, recognized, rationale = bearing_trial(rnd, parent, history, trials)
            plans.append(third)
        lr, epochs, batch = plans[index]
        result = root / str(index)
        report = train_run(profile, rnd.data.train_path, rnd.data.validation_path, result,
                           resume=parent, epochs=epochs, learning_rate=lr, batch_size=batch,
                           stage_id=rnd.stage_id or str(rnd.round_index))
        if (report["parent_checkpoint_sha256"] != parent_digest
                or report["final_steps"] <= report["initial_steps"]
                or report["checkpoint_sha256"] == parent_digest):
            raise ValueError("trainer did not produce a child of the mounted checkpoint")
        trials.append({field: report[field] for field in (
            "learning_rate", "batch_size", "initial_steps", "final_steps", "final_epochs",
            "initial_epochs", "parent_checkpoint_sha256", "checkpoint_sha256",
            "train_rows", "validation_rows", "train_sha256", "validation_sha256",
            "validation_before", "validation_after", "seed")})
    choose = max if higher else min
    best = choose(range(len(trials)), key=lambda i: trials[i]["validation_after"][metric])
    trial = trials[best]
    score = trial["validation_after"][metric]
    previous = trial["validation_before"][metric]
    adopt = score >= previous if higher else score <= previous
    config = {"trials": trials, "candidate_trial": best, "third_trial": option,
              "model_choice_recognized": recognized, "model_call_id": receipt.call_id}
    if key == "B":
        config["third_trial_source"] = "pytrio" if recognized else "fallback"
    declaration = dict(hypothesis=rationale,
                       change_summary="Ran three CPU baseline updates on the current training projection.",
                       configuration=config, seed=trial["seed"])
    submitted = rnd.submit_candidate(root / str(best), checkpoint_paths=["checkpoint.npz"],
                                     code_paths=[], predict_argv=PREDICT_ARGV, **declaration)
    child_id = submitted["artifact_id"]
    selected = child_id if adopt else rnd.parent.artifact_id
    decision = "adopt_child" if adopt else "keep_existing_parent"
    rnd.finish(selected_artifact_id=selected, reason=(
        f"{decision}: public {metric}, parent={previous}, best child={score}."),
        **{**declaration, "configuration": {**config, "candidate_artifact_id": child_id,
                                           "parent_artifact_id": rnd.parent.artifact_id,
                                           "decision": decision}})


@lru_cache(maxsize=1)
def load_model(path):
    return Model.load(path)


def predict(sample, model_dir):
    model = load_model(Path(model_dir) / "checkpoint.npz")
    if model.meta["task"] != sample.task or (
            sample.dataset_key and model.meta["profile"] != sample.dataset_key):
        raise ValueError("prediction context differs from selected checkpoint")
    return baseline_predict(model, sample.inputs)["outputs"]
