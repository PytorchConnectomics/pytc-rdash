"""Stage a card's committed job scripts on its host, submit the job, leave a receipt.

Run it anywhere -- normally on the machine that holds the code (`dashboard/bin/rsub`
wraps it). On the card's own host every step runs locally; elsewhere it stages
and submits over SSH. Either way the record is the same: a receipt written beside
the run (receipts.py), never an edit to the card. The hub collects receipts.

A card opts in through its probe-status fence; the script path is relative to
the project directory and must sit under its `scripts/`:

    {"schema_version": 1, "host": "cajal",
     "launch": {"script": "scripts/slurm/job.sbatch",
                "args": ["--flag", "value"], "cwd": "/abs/workdir"},
     "jobs": []}

Each host has one runs root in projects/config/rdash-launch.yaml (cajal:
/data/runs, group-writable), and each project one directory under it:

    <root>/<project>/stage/<tree hash>/   committed scripts, as run
    <root>/<project>/results/             job outputs ($RDASH_RESULTS)
    <root>/<project>/results/slurm/       Slurm logs (%x_%j.out)

Policy: only committed scripts run. The project's `scripts/` must have no
uncommitted or untracked change in this checkout (with `--ref R`, card and scripts
are read from commit R instead, and the working tree is not consulted); the
committed git tree is archived and unpacked into stage/. A snapshot is content-addressed and never
rewritten, so the tree hash names exactly what ran. No host checkout is
involved and nothing goes through a git remote. The job sees `RDASH_SNAPSHOT`
(sbatch copies the batch script to its spool, so `dirname $0` does not find
helpers), `RDASH_RESULTS`, `RDASH_REVISION` and `RDASH_PROJECT`; `--chdir`
defaults to the snapshot. Jobs are submitted with umask 002, so outputs stay
writable for the runs group.

Only `tar` (staging) and `sbatch --parsable` run remotely, over the board's
multiplexed SSH. Card text never reaches a shell unvalidated: every token
matches a closed character set and is quoted again. Resources live in the
script's #SBATCH lines.

    python3 -B -m dashboard.app.launch --project P --card cards/x.md [--step S] [--test-only] [--ref R]

Receipt: <root>/<project>/receipts/<job>.json, with the research revision and
scripts tree, the snapshot, results folder and sbatch argv, and -- when the launch
names a `code` path (or its `cwd` is inside a git work tree) -- that repository's
commit. Uncommitted changes there do not block the launch; they are saved as
<job>.patch beside the receipt and the receipt says `dirty`. A launch block may
name the code explicitly: "code": "/abs/path/to/repo".

A batch card (one incoming volume run through a fixed pipeline) declares one launch
per step under `steps` instead of a single `launch`, plus a `batch` map of plain
parameters:

    {"schema_version": 1, "host": "bc",
     "batch": {"name": "brain3", "input": "/projects/.../Brain3.czi"},
     "steps": {"info": {"script": "scripts/pipeline/info.sbatch", "jobs": []}, ...},
     "jobs": []}

`--step S` launches steps[S]; the job is named rdash-<card>-<S> and sees
RDASH_STEP=S and RDASH_BATCH_<KEY>=value for each batch entry. Its ID is recorded
in its receipt as `step`, which the board joins to the card's step.
"""
import argparse
import hashlib
import json
import os
import re
import shlex
import socket
import subprocess
import sys

from . import inspection, receipts
from .cards import _path, steps as steps_checklist
from .config import Settings, load_roots
from .jobs import FENCE
from .safety import Error, agent_lock_state, card_ref, project_id

TOKEN = re.compile(r"[A-Za-z0-9._/=:,+@%-]{1,256}")
PATH = re.compile(r"/[A-Za-z0-9._/+@-]{1,511}")
SCRIPT = re.compile(r"scripts/[A-Za-z0-9._/+@-]{1,300}")
TREE = re.compile(r"[0-9a-f]{40}")
STEP = re.compile(r"[a-z][a-z0-9-]{0,31}")
BATCH_KEY = re.compile(r"[a-z][a-z0-9_]{0,31}")
# sbatch --export is comma separated, so batch values exclude commas and '='.
BATCH_VALUE = re.compile(r"[A-Za-z0-9._/:+@%-]{1,256}")
MAX_BATCH = 16
MAX_ARGS = 32
MAX_ARCHIVE = 64 * 1024 * 1024
MAX_PATCH = 8 * 1024 * 1024
GIT_REF = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/@{}^~-]{0,127}")


def declared_launch(text, step=None):
    match = FENCE.search(text or "")
    if not match:
        raise Error(422, "missing_fence", "Card has no probe-status fence")
    try:
        fence = json.loads(match.group(1))
    except (ValueError, RecursionError):
        raise Error(422, "invalid_fence", "probe-status fence is not JSON")
    if not isinstance(fence, dict):
        raise Error(422, "no_launch", "Card declares no launch block")
    batch = {}
    if step is None:
        launch = fence.get("launch")
        if not isinstance(launch, dict):
            raise Error(422, "no_launch", "Card declares no launch block")
    else:
        if not isinstance(step, str) or not STEP.fullmatch(step):
            raise Error(422, "invalid_step", "Step must match " + STEP.pattern)
        steps = fence.get("steps")
        launch = steps.get(step) if isinstance(steps, dict) else None
        if not isinstance(launch, dict) or not launch.get("script"):
            raise Error(422, "no_step", "Card declares no launchable step " + step)
        needs = launch.get("needs", [])
        if not isinstance(needs, list) or not all(isinstance(n, str) for n in needs):
            raise Error(422, "invalid_step", "needs must be a list of step names")
        ticked = {item["key"] for item in steps_checklist(text) if item["checked"]}
        unmet = [n for n in needs if n not in ticked]
        if unmet:
            raise Error(409, "needs_unmet", "Step %s needs %s ticked first" % (step, ", ".join(unmet)))
        batch = fence.get("batch", {})
        if (not isinstance(batch, dict) or len(batch) > MAX_BATCH or
                not all(isinstance(k, str) and BATCH_KEY.fullmatch(k) and isinstance(v, str) and BATCH_VALUE.fullmatch(v)
                        for k, v in batch.items())):
            raise Error(422, "invalid_batch", "batch must be at most %d plain key/value pairs" % MAX_BATCH)
    host, script = fence.get("host"), launch.get("script")
    args, cwd, code = launch.get("args", []), launch.get("cwd"), launch.get("code")
    if not isinstance(host, str) or not inspection.ALIAS.fullmatch(host):
        raise Error(422, "invalid_host", "Launch needs a valid declared host")
    if (not isinstance(script, str) or not SCRIPT.fullmatch(script)
            or any(part in ("", ".", "..") for part in script.split("/"))):
        raise Error(422, "invalid_script", "Script must be a plain path under the project's scripts/")
    if cwd is not None and (not isinstance(cwd, str) or not PATH.fullmatch(cwd)):
        raise Error(422, "invalid_cwd", "cwd must be a plain absolute path")
    if code is not None and (not isinstance(code, str) or not PATH.fullmatch(code)):
        raise Error(422, "invalid_code", "code must be a plain absolute path")
    if (not isinstance(args, list) or len(args) > MAX_ARGS
            or not all(isinstance(a, str) and TOKEN.fullmatch(a) for a in args)):
        raise Error(422, "invalid_args", "args must be at most %d plain tokens" % MAX_ARGS)
    return dict(host=host, script=script, args=args, cwd=cwd, code=code, step=step, batch=batch)


def job_name(ref, step=None):
    stem = os.path.splitext(os.path.basename(ref))[0]
    name = "rdash-" + re.sub(r"[^A-Za-z0-9._-]", "-", stem)[:58]
    return name + "-" + step if step else name


def _git(repo, *args, binary=False):
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, timeout=60)
    if result.returncode != 0:
        raise Error(500, "git_failed", "git %s failed: %s" % (args[0], result.stderr.decode(errors="replace")[:200]))
    return result.stdout if binary else result.stdout.decode().strip()


def committed_scripts(repo, project, script, ref=None):
    """Policy (b): the scripts tree must equal HEAD (or come from `ref`). Returns (revision, tree, archive)."""
    scope = "projects/%s/scripts" % project
    if ref is None:
        dirty = _git(repo, "status", "--porcelain", "--untracked-files=all", "--", scope)
        if dirty:
            raise Error(409, "uncommitted_scripts", "Commit the project's scripts/ before launching:\n" + dirty[:800])
    commit = ref or "HEAD"
    try:
        tree = _git(repo, "rev-parse", commit + ":" + scope)
    except Error:
        raise Error(409, "uncommitted_scripts", scope + " is not in the committed tree")
    if not TREE.fullmatch(tree):
        raise Error(500, "git_failed", "Unexpected tree id")
    if _git(repo, "ls-tree", "--name-only", tree, script[len("scripts/"):]) != script[len("scripts/"):]:
        raise Error(422, "script_not_committed", script + " is not in the committed scripts tree")
    archive = _git(repo, "archive", "--format=tar", tree, binary=True)
    if len(archive) > MAX_ARCHIVE:
        raise Error(413, "scripts_too_large", "scripts/ archive exceeds %d MB" % (MAX_ARCHIVE >> 20))
    return _git(repo, "rev-parse", "--short=12", commit), tree, archive


def card_text(settings, project, ref, git_ref=None):
    """The card as of `git_ref`, or the working tree's addressable card."""
    if git_ref is None:
        path = _path(settings, project, ref)
        agent_lock_state(path.parents[1])
        return path.read_text(encoding="utf-8")
    project_id(project)
    card_ref(ref)
    agent_lock_state(settings.repo_root / "projects" / project)
    if not GIT_REF.fullmatch(git_ref) or ".." in git_ref:
        raise Error(400, "invalid_ref", "Invalid git ref")
    try:
        return _git(settings.repo_root, "show", "%s:projects/%s/cards/%s" % (git_ref, project, ref))
    except Error:
        raise Error(404, "unknown_card", "No card %s/%s at %s" % (project, ref, git_ref))


def is_local(settings, host):
    """True when the card's host is this machine: launch without SSH."""
    names = {settings.host_alias, socket.gethostname().split(".")[0]} - {""}
    return host in names


def _remote(host, argv, timeout=30, payload=b"", local=False, binary=False, max_output=None):
    limits = {} if max_output is None else dict(max_output=max_output)
    if local:
        raw, status = inspection._exchange(list(argv), payload, timeout=timeout, **limits)
    else:
        command = " ".join(shlex.quote(a) for a in argv)
        raw, status = inspection._exchange(inspection.ssh_prefix(host) + [command], payload, timeout=timeout, **limits)
    return (raw if binary else raw.decode("utf-8", errors="replace")), status


# Unpack into a temporary sibling and rename, so a snapshot directory exists only
# when complete; an existing complete snapshot is reused, never rewritten. A
# directory another stager left without the marker is reused only if it holds
# exactly this tree (then marked); anything else in it fails the launch.
STAGE = r'''set -e
umask 002
d=$1; rev=$2; mkdir -p "$3/slurm"
if [ -f "$d/.rdash-complete" ]; then cat >/dev/null; echo "$d"; exit 0; fi
t="$d.tmp.$$"; mkdir -p "$t"; tar -xf - -C "$t"; echo "$rev" > "$t/.rdash-complete"
if mv -T "$t" "$d" 2>/dev/null; then echo "$d"; exit 0; fi
if [ ! -f "$d/.rdash-complete" ] && diff -r -q -x .rdash-complete "$t" "$d" >/dev/null 2>&1; then
    cp "$t/.rdash-complete" "$d/.rdash-complete.tmp.$$" && mv "$d/.rdash-complete.tmp.$$" "$d/.rdash-complete"
fi
rm -rf "$t"
[ -f "$d/.rdash-complete" ] || { echo "snapshot $d exists, unmarked, and differs from this tree" >&2; exit 1; }
echo "$d"'''


def stage(host, root, project, tree, revision, archive, local=False):
    target = "%s/%s/stage/%s" % (root, project, tree)
    results = "%s/%s/results" % (root, project)
    out, status = _remote(host, ["sh", "-c", STAGE, "rdash-stage", target, revision, results],
                          timeout=120, payload=archive, local=local)
    if status != "ok" or out.strip() != target:
        raise Error(502, "staging_failed", "Could not stage scripts on %s (%s): %r" % (host, status, out[:200]))
    return target


def _inside(path, roots):
    return any(os.path.commonpath([path, root]) == root for root in roots)


# The code a job runs, read on its host just before submission: the repository
# holding `path`, its commit and remote, and -- when the work tree differs from
# HEAD -- the diff, so "which code" stays answerable for a dirty launch.
CODE = r'''
import json, re, subprocess, sys
path, limit = sys.argv[1], int(sys.argv[2])
def git(*args):
    r = subprocess.run(["git", "-C", path] + list(args), capture_output=True, timeout=60)
    return r.stdout if r.returncode == 0 else None
top = git("rev-parse", "--show-toplevel")
if top is None:
    print(json.dumps(dict(repo=False))); sys.exit(0)
row = dict(repo=True, top=top.decode().strip(), commit=(git("rev-parse", "HEAD") or b"").decode().strip(),
           # Never copy credentials embedded in a remote URL into a receipt.
           remote=re.sub(r"//[^/@]*@", "//", (git("remote", "get-url", "origin") or b"").decode().strip())[:300])
status = git("status", "--porcelain", "--untracked-files=no") or b""
row["dirty"] = bool(status.strip())
patch = git("diff", "HEAD", "--binary") if row["dirty"] else b""
row["patch_bytes"] = len(patch or b"")
sys.stdout.write(json.dumps(row) + "\n")
sys.stdout.flush()
if patch and len(patch) <= limit:
    sys.stdout.buffer.write(patch)
'''


def code_state(host, path, local=False):
    """(code row for the receipt, patch bytes or b"")."""
    raw, status = _remote(host, ["python3", "-B", "-c", CODE, path, str(MAX_PATCH)], timeout=90,
                          local=local, binary=True, max_output=MAX_PATCH + 4096)
    if status != "ok":
        return dict(path=path, error="could not read the code's git state (%s)" % status), b""
    head, _, patch = raw.partition(b"\n")
    try:
        row = json.loads(head.decode("utf-8", errors="replace"))
    except ValueError:
        return dict(path=path, error="unreadable git state"), b""
    if not row.get("repo"):
        return dict(path=path, error="not a git work tree"), b""
    code = dict(path=row.get("top") or path, dirty=bool(row.get("dirty")))
    if re.fullmatch(r"[0-9a-f]{40}", row.get("commit", "")):
        code["commit"] = row["commit"]
    if row.get("remote") and re.fullmatch(r"[\x20-\x7e]{1,300}", row["remote"]):
        code["remote"] = row["remote"]
    data = patch if code["dirty"] else b""
    if code["dirty"] and row.get("patch_bytes", 0) > MAX_PATCH:
        code["error"] = "diff of %d bytes exceeds %d; not saved" % (row["patch_bytes"], MAX_PATCH)
        data = b""
    return code, data


# Write receipt files once: link from a temporary sibling, never overwrite.
PUT = r'''set -e
umask 002
d=$1; f=$2; mkdir -p "$d"; t="$d/.$f.tmp.$$"
cat > "$t"
if ln "$t" "$d/$f" 2>/dev/null; then rm -f "$t"; echo stored; else rm -f "$t"; echo exists; exit 3; fi'''


def put(host, directory, name, data, local=False):
    out, status = _remote(host, ["sh", "-c", PUT, "rdash-receipt", directory, name],
                          timeout=60, payload=data, local=local)
    if status != "ok" or out.strip() != "stored":
        raise Error(502, "receipt_failed", "Could not write %s/%s on %s (%s): %r"
                    % (directory, name, host, status, out[:200]))


def launch(settings, project, ref, test_only=False, step=None, git_ref=None):
    spec = declared_launch(card_text(settings, project, ref, git_ref), step)
    host = spec["host"]
    local = is_local(settings, host)
    if not local and host not in settings.ssh_hosts:
        raise Error(403, "host_not_permitted", host + " is not this machine and not in RDASH_SSH_HOSTS")
    owner = "local" if local else host
    roots = [r for h, r in load_roots(settings.config_dir, host if local else settings.host_alias,
                                      () if local else settings.ssh_hosts, name="rdash-launch.yaml") if h == owner]
    if None in roots or len(roots) != 1:
        raise Error(403, "no_launch_root", "Need exactly one resolvable launch root for " + host)
    revision, tree, archive = committed_scripts(settings.repo_root, project, spec["script"], git_ref)
    name = job_name(ref, step)
    queued, status = _remote(host, ["squeue", "-h", "--me", "-n", name, "-o", "%i"], local=local)
    if status != "ok":
        raise Error(503, "scheduler_unknown", "Could not check for a live job with this name")
    if queued.split():
        raise Error(409, "already_queued", "Job %s already queued as %s" % (queued.split()[0], name))
    snapshot = stage(host, roots[0], project, tree, revision, archive, local=local)
    resolved = inspection.resolve_roots("" if local else host, [snapshot])
    if not resolved or not _inside(resolved[0], roots):
        raise Error(403, "snapshot_outside_roots", "Snapshot does not resolve inside the launch root")
    script = snapshot + "/" + spec["script"][len("scripts/"):]
    results = "%s/%s/results" % (roots[0], project)
    export = ("ALL,RDASH_SNAPSHOT=%s,RDASH_RESULTS=%s,RDASH_REVISION=%s,RDASH_PROJECT=%s"
              % (snapshot, results, revision, project))
    if step:
        export += ",RDASH_STEP=" + step + "".join(
            ",RDASH_BATCH_%s=%s" % (k.upper(), v) for k, v in sorted(spec["batch"].items()))
    argv = ["sbatch", "--parsable", "--job-name=" + name,
            "--comment=rdash:%s:%s" % (revision, tree[:12]),
            "--export=" + export,
            "--output=%s/slurm/%%x_%%j.out" % results,
            "--chdir=" + (spec["cwd"] or snapshot)]
    if test_only:
        argv.append("--test-only")
    argv += [script] + spec["args"]
    code_path = spec["code"] or spec["cwd"]
    code, patch = code_state(host, code_path, local=local) if code_path else (None, b"")
    # sbatch hands the submitting umask to the job (SLURM_UMASK).
    out, status = _remote(host, ["sh", "-c", 'umask 002; exec "$@"', "rdash-sbatch"] + argv, local=local)
    result = dict(host=host, job_name=name, revision=revision, scripts_tree=tree,
                  snapshot=snapshot, results=results, argv=argv, local=local)
    if code is not None:
        result["code"] = code
    if step:
        result["step"] = step
    if test_only:
        if status != "ok":
            raise Error(422, "sbatch_rejected", "sbatch --test-only rejected the job")
        return dict(result, test_only=True)
    match = re.fullmatch(r"\s*([1-9][0-9]{0,11})(?:;[A-Za-z0-9._-]+)?\s*", out)
    if status != "ok" or not match:
        raise Error(502, "ambiguous_submission",
                    "sbatch returned %r (%s); check `squeue -n %s` before retrying" % (out[:200], status, name))
    job_id = match.group(1)
    directory = "%s/%s/receipts" % (roots[0], project)
    receipt = dict(schema=receipts.SCHEMA, job=int(job_id), host=host, via="rsub", project=project,
                   card=ref, step=step, job_name=name, submitted_at=receipts.now(),
                   submitted_by=receipts.submitter(),
                   research=dict(ref=git_ref or "HEAD", revision=revision, scripts_tree=tree),
                   snapshot=snapshot, results=results, argv=argv, code=code)
    try:
        if patch:
            put(host, directory, job_id + ".patch", patch, local=local)
            receipt["code"] = dict(code, patch=job_id + ".patch", patch_sha256=hashlib.sha256(patch).hexdigest())
        receipt = receipts.validate(receipt)
        put(host, directory, job_id + ".json", receipts.encode(receipt), local=local)
    except (Error, ValueError) as exc:
        # The job exists either way; never let a recording failure hide it.
        message = exc.payload["message"] if isinstance(exc, Error) else str(exc)
        raise Error(getattr(exc, "status", 500), "unrecorded_job",
                    "Submitted job %s on %s but did not write its receipt: %s; record it with "
                    "`hub.sh attach %s %s %s cards/%s`" % (job_id, host, message, host, job_id, project, ref),
                    job_id=job_id)
    return dict(result, job_id=job_id, receipt="%s/%s.json" % (directory, job_id))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--project", required=True)
    parser.add_argument("--card", required=True, help="path relative to the project's cards/")
    parser.add_argument("--step", help="launch this step of a batch card's `steps`")
    parser.add_argument("--test-only", action="store_true", help="stage, then sbatch --test-only; records nothing")
    parser.add_argument("--ref", help="read the card and scripts from this git commit, not the working tree")
    parser.add_argument("--print-host", action="store_true", help="print the card's declared host and exit")
    args = parser.parse_args(argv)
    ref = args.card[len("cards/"):] if args.card.startswith("cards/") else args.card
    try:
        settings = Settings.from_env()
        if args.print_host:
            print(declared_launch(card_text(settings, args.project, ref, args.ref), args.step)["host"])
            return 0
        result = launch(settings, args.project, ref, test_only=args.test_only, step=args.step, git_ref=args.ref)
    except Error as exc:
        print(json.dumps(exc.payload), file=sys.stderr)
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
