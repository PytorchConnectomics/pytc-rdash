"""Shared read-only inspection. Three independent bounded channels.

The fixed worker source is defined once, installed here for tests/adapters and
sent unchanged over stdin-safe local/SSH transports. Card text never becomes code.
"""
_WORKER = r'''
"""Shared read-only inspection: fixed stdin protocol, independent channel budgets."""
import errno, io, json, math, os, re, selectors, shlex, stat, subprocess, sys, time
import hashlib
import threading
STAT_TIMEOUT = 30
MAX_OUTPUT = 256 * 1024
MAX_CONTENT_FILE = 1024 * 1024
MAX_CONTENT_OUTPUT = 4 * 1024 * 1024
MAX_INPUT = 256 * 1024
MAX_PATHS_PER_CALL = 250
ALIAS = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
CACHE_TTL = 10
_reapers = []
_reaper_lock = threading.Lock()

def _exchange(argv, payload, timeout=None, max_output=MAX_OUTPUT):
    """Deadline bounds exchange; cleanup may add at most two seconds.

    Retain complete received bytes on failure. Unreaped children are polled by
    subsequent calls, rather than blocking a request indefinitely.
    """
    with _reaper_lock:
        for child in list(_reapers):
            if child.poll() is not None:
                _reapers.remove(child)
    process = None
    output = bytearray()
    deadline = time.monotonic() + (STAT_TIMEOUT if timeout is None else timeout)
    try:
        process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)
        with selectors.DefaultSelector() as selector:
            for pipe, event in ((process.stdin, selectors.EVENT_WRITE),
                                (process.stdout, selectors.EVENT_READ),
                                (process.stderr, selectors.EVENT_READ)):
                os.set_blocking(pipe.fileno(), False)
                selector.register(pipe, event)
            offset = 0
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return bytes(output), "timeout"
                for key, _ in selector.select(remaining):
                    pipe = key.fileobj
                    if pipe is process.stdin:
                        try:
                            offset += os.write(pipe.fileno(), payload[offset:offset + 65536])
                        except BrokenPipeError:
                            offset = len(payload)
                        if offset == len(payload):
                            selector.unregister(pipe)
                            pipe.close()
                    else:
                        data = os.read(pipe.fileno(), 65536)
                        if not data:
                            selector.unregister(pipe)
                            pipe.close()
                        elif pipe is process.stdout:
                            room = max_output - len(output)
                            output.extend(data[:room])
                            if len(data) > room:
                                return bytes(output), "overflow"
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return bytes(output), "timeout"
            return bytes(output), "ok" if process.wait(timeout=remaining) == 0 else "failed"
    except (OSError, subprocess.SubprocessError):
        return bytes(output), "failed"
    finally:
        if process is not None:
            if process.poll() is None:
                try:
                    process.kill()
                    process.wait(timeout=2)
                except (OSError, subprocess.SubprocessError):
                    with _reaper_lock:
                        _reapers.append(process)
            for pipe in (process.stdin, process.stdout, process.stderr):
                if pipe is not None:
                    pipe.close()

ACTIVE = {"RUNNING", "PENDING", "COMPLETING", "CONFIGURING", "REQUEUED", "SUSPENDED", "RESIZING"}
DONE = {"COMPLETED"}

NAME_LIMIT = 80


def clean_name(value):
    """A scheduler-supplied name is display text, never a locator."""
    name = "".join(c for c in value if c.isprintable()).strip()
    return name[:NAME_LIMIT] if name not in ("", "(null)") else ""


def clean_time(value):
    """Slurm prints Unknown, N/A or None for a time it does not have yet."""
    value = value.strip()
    return value if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}", value) else ""


def _reduce(states):
    if not states:
        return "unknown"
    for state in states:
        if state in ACTIVE:
            return state
    for state in states:
        if state not in DONE and state != "unknown":
            return state
    return "COMPLETED" if DONE & set(states) else "unknown"

def _run(command):
    raw, status = _exchange(command, b"", timeout=10)
    return raw.decode("utf-8", errors="replace") if status == "ok" else None

def scheduler(ids):
    ids = [str(i) for i in ids if re.fullmatch(r"[0-9]{1,12}(?:_[0-9]+)?", str(i))]
    if not ids:
        return {}
    joined = ",".join(ids)
    tasks = {}
    # The two sources order their columns differently, so each carries its own
    # field names. The job name is last in both: a name containing the separator
    # keeps its tail instead of shifting every later column.
    queries = ((["squeue", "-j", joined, "-h", "-o", "%i|%T|%M|%S|%R|%j"],
                ("task", "state", "elapsed", "start", "reason", "name")),
               (["sacct", "-j", joined, "-X", "-n", "-P", "-o", "JobID,State,Elapsed,Start,End,JobName"],
                ("task", "state", "elapsed", "start", "end", "name")))
    for command, fields in queries:
        out = _run(command)
        if out is None:
            continue
        for line in out.splitlines():
            bits = line.strip().split("|", len(fields) - 1)
            if len(bits) < 2:
                bits = line.strip().split(None, 1)
            if len(bits) < 2:
                continue
            row = dict(zip(fields, (bit.strip() for bit in bits)))
            task, state = row["task"], row.get("state", "")
            if "." in task or not state:
                continue
            if not re.fullmatch(r"[0-9]+(?:_(?:[0-9]+|\[[0-9,%:-]+\]))?", task):
                continue
            tasks.setdefault(task, dict(state=state.split()[0].upper(),
                             elapsed=row.get("elapsed", ""), reason=row.get("reason", ""),
                             start=clean_time(row.get("start", "")), end=clean_time(row.get("end", "")),
                             name=clean_name(row.get("name", ""))))
    result = {}
    for job in ids:
        selected = {k: v for k, v in tasks.items() if k == job or k.startswith(job + "_")}
        result[job] = dict(tasks=selected, reduced=_reduce([v["state"] for v in selected.values()]))
    return result

def read_one(path, roots):
    """Walk from a pinned root descriptor; refuse symlinks at every step."""
    path = os.path.normpath(path)
    matches = [r for r in roots if os.path.isabs(r) and
               os.path.commonpath((r, path)) == r and r != path]
    if not matches:
        return dict(state="refused", reason="outside declared roots"), b""
    root = max(matches, key=len)
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
    descriptors = []
    try:
        try:
            fd = os.open(os.sep, flags | os.O_DIRECTORY)
            descriptors.append(fd)
            for component in root.strip(os.sep).split(os.sep):
                if component:
                    fd = os.open(component, flags | os.O_DIRECTORY, dir_fd=fd)
                    descriptors.append(fd)
        except OSError:
            return dict(state="unknown", reason="root_unavailable"), b""
        components = os.path.relpath(path, root).split(os.sep)
        for component in components[:-1]:
            st = os.stat(component, dir_fd=fd, follow_symlinks=False)
            if stat.S_ISLNK(st.st_mode):
                return dict(state="refused", reason="symlink_in_path"), b""
            fd = os.open(component, flags | os.O_DIRECTORY, dir_fd=fd)
            descriptors.append(fd)
        name = components[-1]
        st = os.stat(name, dir_fd=fd, follow_symlinks=False)
        if stat.S_ISLNK(st.st_mode):
            return dict(state="refused", reason="symlink_in_path"), b""
        if not stat.S_ISREG(st.st_mode):
            return dict(state="refused", reason="not_regular"), b""
        opened = os.open(name, flags, dir_fd=fd)
        descriptors.append(opened)
        actual = os.fstat(opened)
        if not stat.S_ISREG(actual.st_mode) or (actual.st_dev, actual.st_ino) != (st.st_dev, st.st_ino):
            return dict(state="unknown", reason="file_changed"), b""
        data = bytearray()
        while True:
            part = os.read(opened, min(65536, MAX_CONTENT_FILE + 1 - len(data)))
            data.extend(part)
            if len(data) > MAX_CONTENT_FILE:
                return dict(state="unreadable", reason="too_large"), b""
            if not part:
                break
        after = os.fstat(opened)
        if (actual.st_size, actual.st_mtime_ns, actual.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns) or len(data) != after.st_size:
            return dict(state="unknown", reason="file_changed"), b""
        return dict(state="present", size=actual.st_size, mtime=actual.st_mtime), bytes(data)
    except OSError as exc:
        if exc.errno in (errno.ENOENT, errno.ENOTDIR):
            return dict(state="absent"), b""
        return dict(state="unknown", reason=errno.errorcode.get(exc.errno, "unreadable")), b""
    finally:
        for fd in reversed(descriptors):
            os.close(fd)
RECEIPT_NAME = re.compile(r"[1-9][0-9]{0,11}\.json\Z")
MAX_RECEIPT_ROWS = 5000

def list_receipts(roots):
    """`<root>/<dir>/receipts/<job>.json` under each root; symlinks are never followed."""
    rows = []
    for i, root in enumerate(roots):
        try:
            projects = sorted(os.scandir(root), key=lambda e: e.name)
        except OSError:
            continue
        for project in projects:
            if project.is_symlink() or not project.is_dir(follow_symlinks=False):
                continue
            directory = os.path.join(project.path, "receipts")
            try:
                if not stat.S_ISDIR(os.lstat(directory).st_mode):
                    continue
                entries = list(os.scandir(directory))
            except OSError:
                continue
            for entry in entries:
                if not RECEIPT_NAME.match(entry.name) or entry.is_symlink() or not entry.is_file(follow_symlinks=False):
                    continue
                st = entry.stat(follow_symlinks=False)
                rows.append(dict(i=i, dir=project.name, name=entry.name, size=st.st_size, mtime=st.st_mtime))
                if len(rows) >= MAX_RECEIPT_ROWS:
                    return rows
    return rows

RECENT_FIELDS = ("job", "state", "submit", "workdir", "name")

def recent_jobs(since):
    """This user's jobs submitted since a date, one row per allocation (array tasks included)."""
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", since):
        return None
    import getpass
    # Older sacct has no --me (squeue does), so name the user.
    raw, status = _exchange(["sacct", "-u", getpass.getuser(), "-X", "-n", "-P", "-S", since,
                             "-o", "JobID,State,Submit,WorkDir,JobName"], b"", timeout=30,
                            max_output=MAX_CONTENT_OUTPUT)
    if status != "ok":
        return None
    rows = []
    for line in raw.decode("utf-8", errors="replace").splitlines():
        bits = line.strip().split("|", len(RECENT_FIELDS) - 1)
        if len(bits) != len(RECENT_FIELDS) or not re.fullmatch(r"[0-9]+(?:_(?:[0-9]+|\[[0-9,%:-]+\]))?", bits[0]):
            continue
        row = dict(zip(RECENT_FIELDS, (b.strip() for b in bits)))
        row["state"] = row["state"].split()[0].upper() if row["state"] else "unknown"
        row["submit"] = clean_time(row["submit"])
        row["name"] = clean_name(row["name"])
        row["workdir"] = row["workdir"][:512]
        rows.append(row)
        if len(rows) >= 20000:
            break
    return rows

def probe(source, target):
    for i, path in enumerate(json.load(source)):
        try:
            value = os.lstat(path)
            kind = ('file' if stat.S_ISREG(value.st_mode) else
                    'dir' if stat.S_ISDIR(value.st_mode) else
                    'symlink' if stat.S_ISLNK(value.st_mode) else 'other')
            row = dict(i=i, state='present', kind=kind,
                       size=value.st_size, mtime=value.st_mtime)
        except OSError as exc:
            row = dict(i=i, state='absent') if exc.errno in (errno.ENOENT, errno.ENOTDIR) else dict(
                i=i, state='unknown', reason=errno.errorcode.get(exc.errno, 'unreadable'))
        print(json.dumps(row), file=target)


'''
exec(_WORKER, globals())
import socket

def unknown(reason):
    return dict(state="unknown", reason=reason)


def parse_output(raw, count):
    rows = [unknown("missing_response") for _ in range(count)]
    seen = set()
    try:
        text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
    except UnicodeError:
        return [unknown("invalid_response") for _ in rows]
    for line in text.splitlines():
        try:
            row = json.loads(line)
        except (ValueError, RecursionError):
            continue
        if not isinstance(row, dict) or type(row.get("i")) is not int:
            continue
        i = row["i"]
        if not 0 <= i < count:
            continue
        if i in seen:
            rows[i] = unknown("duplicate_response")
            continue
        seen.add(i)
        state = row.get("state")
        valid = state in ("present", "absent", "unknown")
        if state == "present":
            valid = (row.get("kind") in ("file", "dir", "symlink", "other")
                     and type(row.get("size")) is int and row["size"] >= 0
                     and type(row.get("mtime")) in (int, float)
                     and math.isfinite(row["mtime"]))
        if state == "unknown":
            valid = isinstance(row.get("reason"), str) and len(row["reason"]) <= 120
        rows[i] = ({key: row[key] for key in ("state", "kind", "size", "mtime", "reason")
                    if key in row} if valid else unknown("invalid_response"))
    return rows


def chunks(paths):
    batch = []
    for path in paths:
        if len(json.dumps([path]).encode()) > MAX_INPUT:
            raise ValueError("Path exceeds input bound")
        if batch and (len(batch) == MAX_PATHS_PER_CALL or
                      len(json.dumps(batch + [path]).encode()) > MAX_INPUT):
            yield batch
            batch = []
        batch.append(path)
    if batch:
        yield batch



PROGRAM = _WORKER + r'''
if __name__ == '__main__':
    request = json.load(sys.stdin)
    channel, items = request['channel'], request['items']
    if channel == 'metadata':
        probe(io.StringIO(json.dumps(items)), sys.stdout)
    elif channel == 'jobs':
        rows = scheduler(items)
        for i, item in enumerate(items):
            print(json.dumps(dict(i=i, **rows.get(str(item), dict(tasks={}, reduced='unknown')))))
    elif channel == 'roots':
        for i, item in enumerate(items):
            print(json.dumps(dict(i=i, path=os.path.realpath(item))))
    elif channel == 'receipts':
        for row in list_receipts(items):
            print(json.dumps(row))
    elif channel == 'recent':
        rows = recent_jobs(items[0]) if len(items) == 1 and isinstance(items[0], str) else None
        if rows is None:
            sys.exit(3)
        for row in rows:
            print(json.dumps(row))
    elif channel == 'content':
        for i, item in enumerate(items):
            row, data = read_one(item, request['roots'])
            header = dict(row, i=i, len=len(data))
            sys.stdout.buffer.write(json.dumps(header).encode() + b'\n' + data + b'\n')
            sys.stdout.buffer.flush()
'''


# One multiplexed connection per host, owned by the board rather than by the
# hub's ~/.ssh/config: the page's 30-minute poll reuses it instead of paying a
# handshake per query. Persist outlives the poll interval; keepalives drop a
# master left stale by a network change instead of hanging every reuse. The
# socket is separate from interactive ones, so closing a shell never cuts it.
MUX = ("-o", "ControlMaster=auto", "-o", "ControlPath=~/.ssh/cm-rdash-%C",
       "-o", "ControlPersist=35m", "-o", "ServerAliveInterval=30",
       "-o", "ServerAliveCountMax=3")


def ssh_prefix(host):
    """Non-interactive, multiplexed ssh up to and including the host alias."""
    return ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "-o",
            "StrictHostKeyChecking=yes", "-o", "NumberOfPasswordPrompts=0", *MUX, host]


# A host that is down must not stall the board: each SSH attempt costs the full
# ConnectTimeout, and one card request makes several. Check reachability cheaply
# first (live master, else a short TCP connect) and remember it briefly.
REACH_TIMEOUT = 3
REACH_TTL = 60
_reach = {}


def _probe_reach(host):
    try:
        check = subprocess.run(ssh_prefix(host)[:-1] + ["-O", "check", host],
                               capture_output=True, timeout=REACH_TIMEOUT)
        if check.returncode == 0:
            return True
        config = subprocess.run(["ssh", "-G", host], capture_output=True, text=True,
                                timeout=REACH_TIMEOUT).stdout
    except (OSError, subprocess.SubprocessError):
        return True     # cannot tell; let the real call decide
    options = dict(line.split(" ", 1) for line in config.splitlines() if " " in line)
    if "hostname" not in options:
        return True     # not a real OpenSSH client (test doubles, wrappers)
    if options.get("proxycommand", "none") != "none" or options.get("proxyjump", "none") != "none":
        return True     # a direct connect says nothing about a proxied host
    try:
        socket.create_connection((options.get("hostname", host), int(options.get("port", 22))),
                                 timeout=REACH_TIMEOUT).close()
        return True
    except (OSError, ValueError):
        return False


def reachable(host):
    if not host:
        return True
    now = time.monotonic()
    hit = _reach.get(host)
    if hit is None or now - hit[1] >= REACH_TTL:
        hit = _reach[host] = (_probe_reach(host), now)
    return hit[0]


def _argv(host):
    if not host:
        return [sys.executable, "-B", "-c", PROGRAM]
    return ssh_prefix(host) + ["python3", "-B", "-c", shlex.quote(PROGRAM)]


def resolve_roots(host, roots, timeout=30):
    """Configuration-time resolution on the host owning the roots, once per load."""
    if host and (not isinstance(host, str) or not ALIAS.fullmatch(host)):
        return None
    if not reachable(host):
        return None
    resolved = []
    for batch in chunks(roots):
        payload = json.dumps(dict(channel="roots", items=batch)).encode()
        raw, status = _exchange(_argv(host), payload, timeout=timeout)
        if status != "ok":
            return None
        try:
            rows = [json.loads(line) for line in raw.splitlines()]
            if len(rows) != len(batch) or any(row.get('i') != i or not isinstance(row.get('path'), str)
                    or not os.path.isabs(row['path']) for i, row in enumerate(rows)):
                return None
            resolved.extend(row['path'] for row in rows)
        except (ValueError, TypeError, AttributeError, RecursionError):
            return None
    return tuple(resolved)


def parse_content(raw, count):
    rows = [unknown("missing_response") for _ in range(count)]
    offset, seen = 0, set()
    while offset < len(raw):
        end = raw.find(b"\n", offset)
        if end < 0 or end - offset > 4096:
            break
        try:
            header = json.loads(raw[offset:end])
            i, length = header["i"], header["len"]
            if type(i) is not int or not 0 <= i < count or type(length) is not int or not 0 <= length <= MAX_CONTENT_FILE:
                break
            start = end + 1
            if start + length >= len(raw) or raw[start + length:start + length + 1] != b"\n":
                break
            offset = start + length + 1
            if i in seen:
                rows[i] = unknown("duplicate_response")
                continue
            seen.add(i)
            if header.get("state") not in ("present", "absent", "unknown", "refused", "unreadable"):
                continue
            if header['state'] == 'present' and (type(header.get('mtime')) not in (int, float) or
                    not math.isfinite(header['mtime']) or type(header.get('size')) is not int or header['size'] < 0):
                continue
            rows[i] = {k: header[k] for k in ("state", "size", "mtime", "reason") if k in header}
            if header['state'] == 'present':
                rows[i]['data'] = raw[start:start + length]
        except (ValueError, KeyError, TypeError, RecursionError):
            break
    return rows


def _channel(host, channel, items, roots=(), timeout=30):
    if host and (not isinstance(host, str) or not ALIAS.fullmatch(host)):
        return [unknown("invalid_host") for _ in items], "failed"
    if not reachable(host):
        if channel in ("metadata", "content"):
            return [unknown("host_unreachable") for _ in items], "unreachable"
        return [dict(tasks={}, reduced="unknown", reason="host_unreachable") for _ in items], "unreachable"
    rows, status = [], "ok"
    # Reserve envelope space as well as item space in the input limit.
    batch = []
    batches = []
    def payload(values):
        return json.dumps(dict(channel=channel, items=values, roots=roots)).encode()
    for item in items:
        if len(payload([item])) > MAX_INPUT:
            return [unknown("input_too_large") for _ in items], "failed"
        if batch and (len(batch) >= 250 or len(payload(batch + [item])) > MAX_INPUT):
            batches.append(batch)
            batch = []
        batch.append(item)
    if batch:
        batches.append(batch)
    for batch in batches:
        raw, outcome = _exchange(_argv(host), payload(batch), timeout=timeout,
                                 max_output=MAX_CONTENT_OUTPUT if channel == "content" else MAX_OUTPUT)
        if outcome != "ok":
            status = outcome
        if channel == "metadata":
            rows.extend(parse_output(raw, len(batch)) if outcome == "ok" else
                        [unknown(outcome) for _ in batch])
        elif channel == "content":
            rows.extend(parse_content(raw, len(batch)))
        else:
            parsed = [dict(tasks={}, reduced="unknown") for _ in batch]
            if outcome == "ok":
                seen = set()
                for line in raw.splitlines():
                    try:
                        row = json.loads(line)
                        i = row['i']
                        if type(i) is int and 0 <= i < len(batch) and i not in seen:
                            tasks = row['tasks']
                            if not isinstance(tasks, dict) or not all(isinstance(k, str) and isinstance(v, dict)
                                    and all(isinstance(v.get(f), str) for f in ('state', 'elapsed', 'reason')) for k, v in tasks.items()):
                                continue
                            parsed[i] = dict(tasks=tasks, reduced=_reduce([v['state'] for v in tasks.values()]))
                            seen.add(i)
                    except (ValueError, KeyError, TypeError, RecursionError):
                        continue
            rows.extend(parsed)
    return rows, status


def json_lines(host, channel, items, timeout=60, max_output=MAX_CONTENT_OUTPUT):
    """Rows from a list-shaped channel (receipts, recent); None when the host did not answer."""
    if host and (not isinstance(host, str) or not ALIAS.fullmatch(host)):
        return None
    if not reachable(host):
        return None
    payload = json.dumps(dict(channel=channel, items=list(items))).encode()
    if len(payload) > MAX_INPUT:
        return None
    raw, outcome = _exchange(_argv(host), payload, timeout=timeout, max_output=max_output)
    if outcome != "ok":
        return None
    rows = []
    for line in raw.decode("utf-8", errors="replace").splitlines():
        try:
            row = json.loads(line)
        except (ValueError, RecursionError):
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def observe_paths(host, paths, timeout=30):
    rows, status = _channel(host, "metadata", paths, timeout=timeout)
    return dict(zip(paths, rows)), status


def probe_jobs(host, ids, timeout=30):
    rows, status = _channel(host, "jobs", ids, timeout=timeout)
    return dict(zip(ids, rows)), status


def read_files(host, specs, roots, timeout=30):
    rows, status = _channel(host, "content", specs, roots=roots, timeout=timeout)
    return dict(zip(specs, rows)), status


def probe_local(paths, timeout=30):
    return _channel("", "metadata", paths, timeout=timeout)[0]


def probe_remote(alias, paths, timeout=30):
    return _channel(alias, "metadata", paths, timeout=timeout)[0]


_cache = {}
_host_locks = {}
_host_locks_guard = threading.Lock()


def _host_lock(host):
    with _host_locks_guard:
        return _host_locks.setdefault(host, threading.Lock())


def policy_digest(roots):
    return hashlib.sha256(json.dumps(sorted(roots)).encode()).hexdigest()


def _publish(host, channel, observations, roots, started):
    for item, observation in observations.items():
        key = (host, channel, item, policy_digest(roots))
        if key not in _cache or _cache[key]["observed_at"] < started:
            _cache[key] = dict(value=observation, observed_at=started)


def cached(host, channel, items, roots=(), timeout=30):
    with _host_lock(host):
        started = time.monotonic()
        digest = policy_digest(roots)
        def key(item):
            return host, channel, item, digest
        missing = [item for item in dict.fromkeys(items) if key(item) not in _cache or
                   started - _cache[key(item)]['observed_at'] >= CACHE_TTL]
        offline = {}
        if missing:
            rows, status = _channel(host, channel, missing, roots=roots, timeout=timeout)
            if status == "unreachable":
                # Keep the last observation, marked stale, rather than erase it.
                offline = {item: dict(_cache[key(item)]['value'], stale=True) if key(item) in _cache else row
                           for item, row in zip(missing, rows)}
            else:
                _publish(host, channel, dict(zip(missing, rows)), roots, started)
        return {item: dict(offline[item]) if item in offline else dict(_cache[key(item)]['value'])
                for item in items}


def states_for(ids, host="", timeout=30):
    return {i: r.get("reduced", "unknown") for i, r in cached(host, "jobs", ids, timeout=timeout).items()}


def annotate(records):
    wanted = list(dict.fromkeys(i for r in records for i in r.get('job_ids', [])))
    states = states_for(wanted)
    for record in records:
        record['jobs'] = [dict(id=i, state=states[i]) for i in record.pop('job_ids', [])]
    return records


def paths_for(host, paths, timeout=30):
    return cached(host, "metadata", paths, timeout=timeout)

def resolve_host(settings, declared_host, host_ok):
    if not host_ok:
        return "none", "invalid_host"
    if declared_host is None or declared_host == settings.host_alias:
        return ("local", None) if settings.local_enabled else ("none", "local_stat_disabled")
    if declared_host in settings.ssh_hosts:
        return "ssh", None
    return "none", "host_not_permitted"



def path_permitted(settings, path):
    normalized = os.path.normpath(path)
    return not settings.stat_roots or any(
        os.path.isabs(root) and os.path.commonpath((normalized, os.path.normpath(root))) == os.path.normpath(root)
        for root in settings.stat_roots)


def job_times(state, tasks):
    """What a job card needs: in progress or done, and when it started and ended.

    An array starts with its first task and ends with its last; it has no end
    while any task is still queued or running.
    """
    from .attention import BUCKETS
    bucket = BUCKETS.get(str(state).upper(), "unknown")
    phase = {"run": "in progress", "wait": "in progress", "done": "done", "bad": "done"}.get(bucket, "unknown")
    starts = sorted(t["start"] for t in tasks.values() if t.get("start"))
    ends = sorted(t["end"] for t in tasks.values() if t.get("end"))
    finished = phase == "done" and len(ends) == len(tasks)
    return dict(phase=phase, start=starts[0] if starts else "", end=ends[-1] if finished and ends else "")


def annotate_status(records, settings, project=None):
    """Collect across all cards before any per-host observation is dispatched.

    A card's jobs are the IDs its probe-status fence lists (older launches) plus
    its receipts (receipts.annotate); each is observed on its own host.
    """
    from . import jobs
    from .config import roots_for
    groups = {}

    def group_for(host):
        return groups.setdefault(host, dict(paths=[], jobs=[], records=[]))
    for record in records:
        status = jobs.declared_status(record["body"])
        mode, reason = resolve_host(settings, status["host"], status["host_ok"])
        host = status["host"] if mode == "ssh" else ""
        record["jobs"] = []
        record["artifacts"] = []
        record.pop("job_ids", None)
        # Local scheduler reads retain their existing behavior on hostless cards.
        scheduler_ok = mode != "none" or (status["host_ok"] and
                         status["host"] in (None, settings.host_alias))
        group = group_for(host) if scheduler_ok else None
        seen = set()
        for job_id in status["jobs"]:
            seen.add((status["host"] or settings.host_alias, job_id))
            record["jobs"].append(dict(id=job_id, state="unknown", _group=host if scheduler_ok else None))
            if group is not None:
                group["jobs"].append(job_id)
        for receipt in record.get("receipts", []):
            if (receipt["host"], receipt["job"]) in seen:
                continue
            seen.add((receipt["host"], receipt["job"]))
            rmode, rreason = resolve_host(settings, receipt["host"], True)
            rhost = receipt["host"] if rmode == "ssh" else ""
            row = dict(id=receipt["job"], state="unknown", host=receipt["host"], via=receipt["via"],
                       _group=None if rmode == "none" else rhost)
            if rmode == "none":
                row["reason"] = rreason
            else:
                group_for(rhost)["jobs"].append(receipt["job"])
            record["jobs"].append(row)
        record["_card_group"] = host if group is not None else None
        if group is not None:
            group["records"].append(record)
        for receipt_host in {j["_group"] for j in record["jobs"] if j.get("_group") is not None} - {host}:
            group_for(receipt_host)["records"].append(record)
        for artifact in status["artifacts"]:
            error = reason if mode == "none" else (None if path_permitted(settings, artifact["path"]) else "path_not_permitted")
            row = dict(artifact, **unknown(error or "not_observed"))
            record["artifacts"].append(row)
            if error is None:
                group["paths"].append(artifact["path"])
    for host, group in groups.items():
        roots = tuple(root for root in roots_for(settings, project, host) if root is not None)
        job_rows = cached(host, "jobs", list(dict.fromkeys(group["jobs"])), roots=roots)
        observations = cached(host, "metadata", group["paths"], roots=roots) if group["paths"] else {}
        for record in dict((id(r), r) for r in group["records"]).values():
            for job in record["jobs"]:
                if job.get("_group") != host:
                    continue
                observed = job_rows.get(job["id"], {})
                job["state"] = observed.get("reduced", "unknown")
                job["tasks"] = observed.get("tasks", {})
                names = {t.get("name") for t in job["tasks"].values() if t.get("name")}
                if len(names) == 1:
                    job["name"] = names.pop()
                if len(job["tasks"]) == 1:
                    task = next(iter(job["tasks"].values()))
                    job.update(elapsed=task.get("elapsed", ""), reason=task.get("reason", ""))
                job.update(job_times(job["state"], job["tasks"]))
                if observed.get("reason") and not job.get("reason"):
                    job["reason"] = observed["reason"]
                if observed.get("stale"):
                    job["stale"] = True
            for artifact in record["artifacts"] if record["_card_group"] == host else ():
                if artifact.get("reason") == "not_observed":
                    artifact.pop("reason", None)
                    artifact.update(observations[artifact["path"]])
    for record in records:
        record.pop("_card_group", None)
        for job in record["jobs"]:
            job.pop("_group", None)
    return records
