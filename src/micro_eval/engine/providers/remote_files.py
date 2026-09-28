"""Bounded transfer primitives shared by remote providers.

There is no trusted filesystem inside an agent's sandbox. Paths and bodies
are checked again at the host boundary; links and special entries are never
followed. The remote helper uses directory descriptors to close symlink races.
"""

from __future__ import annotations

import os
import stat
import uuid
from pathlib import Path
from typing import Iterator

from micro_eval.engine.providers.git_worktree import WorkspaceProviderError

TRANSFER_CHUNK = 48 * 1024
TRANSFER_LIMIT = 50 * 1024 * 1024
ENTRY_LIMIT = 4096
CONTROL_NAMES = frozenset({".git", ".micro-eval", ".scratch", ".codex", ".agents"})


def safe_relative(value: str) -> Path:
    path = Path(value)
    if (not value or not path.parts or len(value.encode()) > 4096 or path.is_absolute()
            or any(part in {"..", "."} | CONTROL_NAMES for part in path.parts)
            or "\x00" in value or "\\" in value):
        raise WorkspaceProviderError("unsafe remote transfer path")
    return path


def source_files(source: Path, project_root: Path) -> Iterator[tuple[Path, Path]]:
    """Inspect the original source, before a copy could dereference links."""
    try:
        source.relative_to(project_root)
        current = source
        while current != project_root:
            if current.is_symlink():
                raise WorkspaceProviderError("workspace source contains a symlink")
            current = current.parent
        source.resolve(strict=True).relative_to(project_root)
    except (OSError, ValueError) as exc:
        raise WorkspaceProviderError("workspace source escapes project root or is missing") from exc
    if source.is_file():
        pairs = [(source, Path(source.name))]
    else:
        pairs = _walk_source(source)
    count = total = 0
    for entry, relative in pairs:
        if any(part in CONTROL_NAMES for part in relative.parts):
            continue
        safe_relative(str(relative))
        info = entry.lstat()
        is_directory = stat.S_ISDIR(info.st_mode)
        if (not (stat.S_ISREG(info.st_mode) or is_directory)
                or (not is_directory and info.st_nlink != 1) or entry.is_symlink()):
            raise WorkspaceProviderError("workspace source contains a linked or special file")
        count += 1
        total += 0 if is_directory else info.st_size
        if count > ENTRY_LIMIT or total > TRANSFER_LIMIT:
            raise WorkspaceProviderError("workspace source exceeds remote transfer limits")
        yield entry, relative


def _walk_source(source: Path) -> Iterator[tuple[Path, Path]]:
    count = 0

    def walk(directory: Path) -> Iterator[tuple[Path, Path]]:
        nonlocal count
        with os.scandir(directory) as entries:
            for entry in entries:
                count += 1
                if count > ENTRY_LIMIT:
                    raise WorkspaceProviderError("workspace source exceeds remote entry limit")
                if entry.name in CONTROL_NAMES:
                    continue
                if entry.is_symlink():
                    raise WorkspaceProviderError("workspace source contains a symlink")
                path = Path(entry.path)
                if entry.is_dir(follow_symlinks=False):
                    yield path, path.relative_to(source)
                    yield from walk(path)
                else:
                    yield path, path.relative_to(source)

    yield from walk(source)


def read_source(path: Path, remaining: int, root: Path) -> bytes:
    # Anchor every component, including parents that could have been replaced
    # since enumeration. O_NOFOLLOW on the final entry alone is insufficient.
    relative = path.relative_to(root)
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in relative.parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        target = os.open(relative.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        with os.fdopen(target, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > remaining:
                raise WorkspaceProviderError("unsafe or oversized workspace source")
            data = stream.read(remaining + 1)
        if len(data) > remaining:
            raise WorkspaceProviderError("workspace source grew beyond transfer limit")
        return data
    finally:
        os.close(fd)


def write_host_file(root: Path, relative: Path, data: bytes) -> None:
    """Write a verified body without following host destination links."""
    safe_relative(str(relative))
    root.mkdir(parents=True, exist_ok=True)
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in relative.parts[:-1]:
            try:
                os.mkdir(part, mode=0o700, dir_fd=fd)
            except FileExistsError:
                pass
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        try:
            existing = os.stat(relative.name, dir_fd=fd, follow_symlinks=False)
        except FileNotFoundError:
            existing = None
        if existing is not None and (not stat.S_ISREG(existing.st_mode) or existing.st_nlink != 1):
            raise WorkspaceProviderError("unsafe host transfer destination")
        temporary = ".micro-eval-transfer-" + uuid.uuid4().hex
        target = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=fd)
        try:
            with os.fdopen(target, "wb") as stream:
                stream.write(data)
            os.replace(temporary, relative.name, src_dir_fd=fd, dst_dir_fd=fd)
        finally:
            try:
                os.unlink(temporary, dir_fd=fd)
            except FileNotFoundError:
                pass
    finally:
        os.close(fd)


# Fixed code only. Data is a base64 JSON argv parameter, never shell source.
# Each read returns one capped chunk; listing has both an entry and name cap.
REMOTE_FILES = r'''
import os,sys,json,base64,stat
p=json.loads(base64.b64decode(sys.argv[1]))
F=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW
blocked={'.git','.micro-eval','.scratch','.codex','.agents','.tmp'}
def directory(path,create=False):
    if not path.startswith('/') or '..' in path.split('/'):
        raise ValueError('path')
    fd=os.open('/',F)
    try:
        for part in path.split('/'):
            if not part: continue
            if create:
                try: os.mkdir(part,0o700,dir_fd=fd)
                except FileExistsError: pass
            child=os.open(part,F,dir_fd=fd)
            os.close(fd);fd=child
        return fd
    except BaseException:
        os.close(fd);raise
try:
    op=p['op']; path=p['path']
    if op=='mkdir':
        fd=directory(path,True);os.close(fd);result=True
    elif op=='list':
        fd=directory(path);result={'entries':[],'skipped':False}; seen=[0]
        inventory_bytes=[len(json.dumps({'ok':True,'value':result},ensure_ascii=True).encode())+1]
        inventory_full=[False]
        def walk(fd,prefix):
            with os.scandir(fd) as entries:
                for entry in entries:
                    seen[0]+=1
                    if seen[0]>4096:
                        result['skipped']=True;return
                    name=entry.name;rel=prefix+name
                    if name in blocked or (not prefix and name=='input.txt'):continue
                    if len(rel.encode())>4096:
                        result['skipped']=True;continue
                    info=entry.stat(follow_symlinks=False)
                    if stat.S_ISDIR(info.st_mode):
                        try: child=os.open(name,F,dir_fd=fd)
                        except OSError: result['skipped']=True;continue
                        try: walk(child,rel+'/')
                        finally: os.close(child)
                    elif stat.S_ISREG(info.st_mode) and info.st_nlink==1:
                        record={'path':rel,'size':info.st_size}
                        encoded_size=len(json.dumps(record,ensure_ascii=True).encode())
                        if result['entries']:encoded_size+=2
                        if inventory_bytes[0]+encoded_size>524288:
                            result['skipped']=True;inventory_full[0]=True;return
                        inventory_bytes[0]+=encoded_size
                        result['entries'].append(record)
                    else: result['skipped']=True
                    if seen[0]>4096 or inventory_full[0]:return
        try: walk(fd,'')
        finally:os.close(fd)
    else:
        parent,name=os.path.split(path);fd=directory(parent,op=='write')
        try:
            if op=='exists':
                try:
                    info=os.stat(name,dir_fd=fd,follow_symlinks=False)
                    result=stat.S_ISREG(info.st_mode) and info.st_nlink==1 or stat.S_ISDIR(info.st_mode)
                except FileNotFoundError:result=False
            else:
                flags=(os.O_WRONLY|os.O_CREAT if op=='write' else os.O_RDONLY)|os.O_NOFOLLOW|os.O_NONBLOCK
                f=os.open(name,flags,0o600,dir_fd=fd)
                try:
                    info=os.fstat(f)
                    if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1:raise ValueError('file')
                    if op=='write':
                        data=base64.b64decode(p['data'],validate=True)
                        if len(data)>49152:raise ValueError('size')
                        if p['offset']==0:os.ftruncate(f,0)
                        if os.fstat(f).st_size!=p['offset']:raise ValueError('offset')
                        os.lseek(f,p['offset'],0)
                        while data:
                            n=os.write(f,data);data=data[n:]
                        os.fchmod(f,p.get('mode',384)&511);result=True
                    elif op=='read':
                        if info.st_size!=p['size'] or p['size']>p['limit']:raise ValueError('size')
                        os.lseek(f,p['offset'],0)
                        data=os.read(f,min(49152,p['size']-p['offset']))
                        result=base64.b64encode(data).decode()
                    else:raise ValueError('operation')
                finally:os.close(f)
        finally:os.close(fd)
    print(json.dumps({'ok':True,'value':result},ensure_ascii=True))
except FileNotFoundError:
    print(json.dumps({'ok':p['op']=='exists','value':False}))
except Exception:
    print('{"ok":false}')
'''
