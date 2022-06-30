from decimal import Decimal
from ape import Contract
from ape.contracts import ContractInstance, ContractLog
from semantic_version import Version


def assess_fees(vault: ContractInstance, report: ContractLog):
    """
    A reimplementation of Vault._assessFees which supports all api versions.
    """
    strategy = Contract(report.strategy)
    pre_height = report.block_number - 1
    gain = report.gain
    version = Version(vault.apiVersion())

    a = vault.strategies(strategy, height=pre_height)
    b = vault.strategies(strategy, height=report.block_number)
    # would be inaccurate if multiple harvests occured at the same block
    # 0.4.0 asserts duration is non-zero
    duration = b.lastReport - a.lastReport

    # 0.3.3 year changed from 365.25 to 365.2425 days
    if version >= Version("0.3.3"):
        SECS_PER_YEAR = 31_556_952
    else:
        SECS_PER_YEAR = 31_557_600

    # 0.4.0 no fees are charged if there was no gain
    if version >= Version("0.4.0"):
        if gain == 0:
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

    # NOTE the calculation is inaccurate if fees were changed in the same block as harvest
    management_fee_bps = vault.managementFee(height=pre_height)
    performance_fee_bps = vault.performanceFee(height=pre_height)
    strategist_fee_bps = vault.strategies(strategy, height=pre_height).performanceFee

    MAX_BPS = 10_000
    management_fee = total_assets * duration * management_fee_bps // MAX_BPS // SECS_PER_YEAR
    strategist_fee = gain * strategist_fee_bps // MAX_BPS
    performance_fee = gain * performance_fee_bps // MAX_BPS

    total_fee = management_fee + performance_fee + strategist_fee
    # 0.3.5 management fee is reduced if the total fee exceeds the gain
    if version >= Version("0.3.5"):
        if total_fee > gain:
            total_fee = gain
            management_fee = gain - performance_fee - strategist_fee
    scale = 10 ** vault.decimals()

    return {
        "management_fee": Decimal(management_fee) / scale,
        "performance_fee": Decimal(performance_fee) / scale,
        "governance_fee": Decimal(management_fee + performance_fee) / scale,
        "strategist_fee": Decimal(strategist_fee) / scale,
        "total_fee": Decimal(total_fee) / scale,
        "duration": duration,
        "gain": Decimal(gain) / scale,
    }
