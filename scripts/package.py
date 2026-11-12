"""Build a deterministic Splunk app archive using only the Python standard library."""

import argparse
import configparser
import gzip
import hashlib
import io
import json
import re
import tarfile
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "app" / "openshare"
ENTRIES = ("README", "README.txt", "app.manifest", "appserver", "bin", "default", "metadata")


def app_files():
    for name in ENTRIES:
        entry = APP / name
        if entry.is_file():
            yield entry
            continue
        for path in sorted(entry.rglob("*")):
            if path.is_file() and path.suffix not in {".pyc", ".pyo"}:
                relative = path.relative_to(APP)
                if not any(
                    part.startswith(".") or part == "__pycache__" for part in relative.parts
                ):
                    yield path


def version():
    config = configparser.ConfigParser(interpolation=None)
    config.read(APP / "default/app.conf", encoding="utf-8")
    manifest = json.loads((APP / "app.manifest").read_text(encoding="utf-8"))["info"]["id"]
    release = config["launcher"]["version"]
    if {config["package"]["id"], config["id"]["name"], manifest["name"]} != {APP.name}:
        raise ValueError("The app folder, package ID, and manifest name must match.")
    if not re.fullmatch(r"\d+\.\d+\.\d+", release) or {
        config["id"]["version"],
        manifest["version"],
    } != {release}:
        raise ValueError("The package and manifest must use the same release version.")
    return release


def build(output):
    output.mkdir(parents=True, exist_ok=True)
    name = f"{APP.name}-{version()}.spl"
    with TemporaryDirectory(dir=output) as temporary:
        archive = Path(temporary) / name
        with (
            archive.open("wb") as raw,
            gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed,
            tarfile.open(fileobj=compressed, mode="w") as tar,
        ):
            for path in app_files():
                data = path.read_bytes()
                member = tarfile.TarInfo(path.relative_to(APP.parent).as_posix())
                member.size = len(data)
                member.mode = 0o644
                tar.addfile(member, io.BytesIO(data))
        checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
        sidecar = archive.with_suffix(".spl.sha256")
        sidecar.write_text(f"{checksum}  {name}\n", encoding="ascii")
        archive.replace(output / name)
        sidecar.replace(output / sidecar.name)
    return output / name


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", nargs="?", type=Path, default=ROOT / "packages")
    print(build(parser.parse_args().output.resolve()))
