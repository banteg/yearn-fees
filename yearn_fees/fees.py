from ape import Contract
from ape.contracts import ContractInstance, ContractLog
from semantic_version import Version

from yearn_fees.types import Fees
from yearn_fees.vault_utils import get_fee_config_at_report, reports_from_block, reports_from_tx


def assess_fees(report: ContractLog) -> Fees:
    """
    A reimplementation of Vault._assessFees which supports all api versions.
    """
    vault = Contract(report.contract_address)
    strategy = Contract(report.strategy)
    pre_height = report.block_number - 1
    version = Version(vault.apiVersion())

    if version >= Version("0.4.0"):
        # 0.4.0 disallow harvesting the strategy twice in a block
        a = vault.strategies(strategy, height=pre_height)
        b = vault.strategies(strategy, height=report.block_number)
        duration = b.lastReport - a.lastReport
    elif version >= Version("0.3.5"):
        # the duration would be zero after the first harvest of the same strategy in the block
        block_reports = reports_from_block(report.block_number, strategy=vault.address)
        a = vault.strategies(strategy, height=pre_height)
        b = vault.strategies(strategy, height=report.block_number)
        # 0.4.0 asserts duration is non-zero
        duration = b.lastReport - a.lastReport if block_reports.index(report) == 0 else 0
    else:
        # the duration would be zero after the first harvest of the same vault in the block
        block_reports = reports_from_block(report.block_number, vault=vault.address)
        b = vault.lastReport(height=report.block_number)
        a = vault.lastReport(height=pre_height)
        duration = b - a if block_reports.index(report) == 0 else 0

    # 0.3.3 year changed from 365.25 to 365.2425 days
    if version >= Version("0.3.3"):
        SECS_PER_YEAR = 31_556_952
    else:
        SECS_PER_YEAR = 31_557_600

    # 0.4.0 no fees are charged if there was no gain
    if version >= Version("0.4.0"):
        if report.gain == 0:
            return {}
    # 0.3.5 read total debt and delegated assets from strategy
    if version >= Version("0.3.5"):
        total_debt = vault.strategies(strategy, height=pre_height).totalDebt
        delegated_assets = strategy.delegatedAssets(height=pre_height)
        total_assets = total_debt - delegated_assets
    # 0.3.4 don't charge the management fee on delegated assets
    elif version >= Version("0.3.4"):
        total_debt = vault.totalDebt(height=pre_height)
        delegated_assets = vault.delegatedAssets(height=pre_height)
        total_assets = total_debt - delegated_assets
    # 0.3.1 charge the management fee amount in strategies instead of vault assets
    elif version >= Version("0.3.1"):
        total_assets = vault.totalDebt(height=pre_height)
    elif version >= Version("0.3.0"):
        total_assets = vault.totalAssets(height=pre_height)
    else:
        raise ValueError("invalid version %s", version)

    MAX_BPS = 10_000
    conf = get_fee_config_at_report(report)
    print(f"{total_assets=} {duration=}")
    # 0.3.5 is the only verison that uses a precision factor
    if version == Version("0.3.5"):
        prec = 10 ** (18 - vault.decimals())
    else:
        prec = 1

    management_fee = (
        prec * total_assets * duration * conf.management_fee // MAX_BPS // SECS_PER_YEAR // prec
    )
    strategist_fee = prec * report.gain * conf.strategist_fee // MAX_BPS // prec
    performance_fee = prec * report.gain * conf.performance_fee // MAX_BPS // prec

    total_fee = management_fee + performance_fee + strategist_fee
    # 0.3.5 management fee is reduced if the total fee exceeds the gain
    if version >= Version("0.3.5"):
        if total_fee > report.gain:
            total_fee = report.gain
            management_fee = report.gain - performance_fee - strategist_fee

    return Fees(
        management_fee=management_fee,
        performance_fee=performance_fee,
        strategist_fee=strategist_fee,
        duration=duration,
        gain=report.gain,
    )
