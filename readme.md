# yearn fees

_a quest for accurate accounting_

<details>
   <summary>👀 <strong>click to see screenshots</strong></summary>
   
   ### $ yearn-fees index
   <img alt="yearn-fees index" src="https://user-images.githubusercontent.com/4562643/177218660-d0924fbc-3766-4add-bbf7-2c08a041066a.png">

   ### $ yearn-fees layout
   <img alt="yearn-fees layout" src="https://user-images.githubusercontent.com/4562643/177218709-559f6b79-8c6d-4fd7-8cb4-48f7278f4191.png">
</details>

## what is this

a set of tools to extract accurate management/performance/strategist fees from yearn harvests.

## why it's needed

none of v2 vault releases emit a log with said fees, but their composition is useful and should be available for analysis.

## how it works

you can read a detailed explanation [in this blog post](https://banteg.mirror.xyz/vZySVJ4Wvf4tKhgskbEIcHAlqG20wifUy807bzfEsp8).

## installation

note: this project uses some aspirational apis, so it's recommended to run in a separate virtual environment.

1. install `pyenv`
1. install python
1. install [poetry](https://python-poetry.org/docs/master/#installing-with-the-official-installer)
1. create a virtualenv
1. install this project
   ```bash
   gh repo clone banteg/yearn-fees
   cd yearn-fees
   poetry install
   ```
1. install ape patches
   ```bash
   gh repo clone banteg/ape
   cd ape
   git checkout bunny-patch
   pip install -e .
   ```
1. if you plan to index the data, install postgres and create a db
   ```bash
   createdb yearn-fees
   ```

## usage

index everything into postgres

```
yearn-fees index
```

show a memory layout

```
yearn-fees layout <version>
yearn-fees layout <tx>
```

compare if the two methods return the same data

```
yearn-fees compare <version>
yearn-fees compare <tx>
```

find positions when a non-memory value was seen on the stack

```
yearn-fees find-durations <version>
yearn-fees find-durations <tx>
```

## module walkthrough

- [assess.py](yearn_fees/assess.py) reimplements the `_assessFees` function for all vault versions 0.3.0…0.4.3.
- [cache.py](yearn_fees/cache.py) implements a pickled + gzipped file cache as a `diskcache.Disk`.
- [cli.py](yearn_fees/cli.py) is the `click` entrypoint to cli commands.
- [compare.py](yearn_fees/compare.py) laces the two methods together and shows a comparison between them.
- [compile_sources.py](yearn_fees/compile_sources.py) checks out all version tags from the [yearn-vaults](http://github.com/yearn/yearn-vaults) repo, compiles them with `vvm` and saves the metadata as well as versioned sources for further reference.
- [find_program_counters.py](yearn_fees/find_program_counters.py) reads `source_map` and `ast` output from vyper compiler and finds the jumps occuring the function.
- [indexer.py](yearn_fees/indexer.py) loads the reports enriched with the fee split data into postgres. it also implements several interesting things like a global `rich` console running in the main process where `dask` workers can log from another process. the indexer runs in strict mode, meaning it won't save reports where the two methods don't reconcile.
- [memory_layout.py](yearn_fees/memory_layout.py) holds the extracted memory layout and program counters for each version, as well as provides a memory viewer tool which helps to find the program counters where certain values appear.
- [models.py](yearn_fees/models.py) contains database models.
- [scanner.py](yearn_fees/scanner.py) can search for values appearing across stack and memory, as well as show a highlighted memory layout.
- [traces.py](yearn_fees/traces.py) can split traces of transactions containing multiple harvests and can extract the fee values from the trace.
- [types.py](yearn_fees/types.py) contains `pydantic` models for fees, fee history and minimal models for traces. it also contains `AsofDict` utility which simlifies reading the fee configuration from fee history.
- [utils.py](yearn_fees/utils.py) contains most of blockchain interacting functions, as well as opmized and cached methods to get all vaults, all reports, sample harvests, vault fee config history, and getting reports from blocks and txs.
- [this gist](https://gist.github.com/banteg/5e89aeeb2b1f5a5f982dc6d340c52b09) contains a vyper patch to print memory layout
