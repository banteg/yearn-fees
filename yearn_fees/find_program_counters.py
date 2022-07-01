import json
from pathlib import Path
import click
from rich import print


def map_source(data):
    source_lines = data["source"].splitlines()
    jump_map = data["source_map"]["pc_jump_map"]
    pos_map = data["source_map"]["pc_pos_map"]
    ast = data["ast"]["ast"]["body"]
    api_version = data["api_version"]
    print(f"[bold yellow]{api_version}[/]")

    fn = next(item for item in ast if item.get("name") == "_assessFees")
    found_pcs = []

    for pc, (start_line, start_column, end_line, end_column) in pos_map.items():
        # if pc not in jump_map:
        #     continue
        if start_line < fn["lineno"] or end_line > fn["end_lineno"]:
            continue

        found_pcs.append(str(pc))

        for row, line in enumerate(source_lines[start_line:end_line], start_line):
            lineno = f"[dim]{row}[/]  "
            if row == start_line:
                print(f"pc={pc} {jump_map[pc]=} {start_line=}")
                line = line[start_column:]
            elif row == end_line:
                line = line[:end_column]

            print(f"{lineno}{line}")

    return found_pcs


@click.command()
@click.option("--version", default=None)
def main(version):
    pcs_by_version = {}

    for path in Path("metadata").glob("v*.json"):
        data = json.loads(path.read_text())
        api_version = data["api_version"].lstrip("v")
        if version and api_version != version:
            continue
        pcs_by_version[api_version] = map_source(data)

    if version is None:
        Path("metadata/pcs_by_version.json").write_text(json.dumps(pcs_by_version, indent=2))


if __name__ == "__main__":
    main()
