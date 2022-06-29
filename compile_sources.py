import json
from pathlib import Path

import vvm
from ape_vyper import compiler
from git import Repo
from git.exc import NoSuchPathError
from rich.console import Console
from rich.progress import Progress
from semantic_version import Version
from vvm.install import get_executable
from vvm.wrapper import vyper_wrapper

FIRST_PRODUCTION_VERSION = Version("0.3.0")
console = Console()


def get_repo():
    try:
        repo = Repo("yearn-vaults")
    except NoSuchPathError:
        console.log("clone repo")
        repo = Repo.clone_from("https://github.com/yearn/yearn-vaults.git", "yearn-vaults")

    return repo


def install_vyper(pragma_spec):
    if not pragma_spec.select(vvm.get_installed_vyper_versions()):
        vyper_version = pragma_spec.select(vvm.get_installable_vyper_versions())
        console.log(f"install vyper {vyper_version}")
        vvm.install_vyper(vyper_version, show_progress=True)

    return pragma_spec.select(vvm.get_installed_vyper_versions())


def compile_contract(vyper_version, source_files, formats):
    f = ",".join(formats)
    vyper_binary = get_executable(vyper_version)
    stdoutdata, stderrdata, command, proc = vyper_wrapper(
        vyper_binary=vyper_binary,
        source_files=source_files,
        f=",".join(formats),
    )
    return {f: json.loads(line) for f, line in zip(formats, stdoutdata.splitlines())}


def main():
    repo = get_repo()
    tags = [
        tag.name
        for tag in repo.tags
        if "-" not in tag.name  # patch releases like v0.4.3-1 only touch strategies
        and Version(tag.name.lstrip("v")) >= FIRST_PRODUCTION_VERSION
    ]

    with Progress(console=console) as progress:
        task = progress.add_task("compile sources", total=len(tags))
        for tag in tags:
            progress.update(task, description=f"compile {tag}")
            # check out the tag
            repo.git.checkout(tag)
            source = Path("yearn-vaults/contracts/Vault.vy").read_text()

            # install vyper if needed
            pragma_spec = compiler.get_pragma_spec(source)
            vyper_version = install_vyper(pragma_spec)

            # compile the contracts
            source_file = Path(repo.working_dir) / "contracts" / "Vault.vy"
            compiler_output = compile_contract(vyper_version, source_file, ["source_map", "ast"])

            # write metadata
            source_copy = Path("sources") / f"Vault_{tag}.vy"
            source_copy.write_text(source_file.read_text())
            metadata_path = Path("metadata") / f"{tag}.json"
            metadata = {
                "vyper_version": str(vyper_version),
                "api_version": tag,
                "source": source_file.read_text(),
                **compiler_output,
            }
            metadata_path.write_text(json.dumps(metadata, indent=2))
            progress.update(task, advance=1)


if __name__ == "__main__":
    main()
