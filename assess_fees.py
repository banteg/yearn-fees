from semantic_version import Version
from ape import Contract
from ape.contracts import ContractEvent


def assess_fees(
    vault: str,
    strategy: str,
    report: ContractEvent,
    duration: int,
    version: str,
):
    """
    A reimplementation of Vault._assessFees which supports all api versions.
    """
    version = Version(version)
    MAX_BPS = 10_000

    # 0.3.3 year changed from 365.25 to 365.2425 days
    if Version(version) >= Version("0.3.3"):
        SECS_PER_YEAR = 31_556_952
    else:
        SECS_PER_YEAR = 31_557_600

    vault = Contract(vault)
    strategy = Contract(strategy)
    pre_height = report["block_number"] - 1
    gain = report.gain

    # 0.4.0 no fees are charged if there was no gain
    if Version(version) >= Version("0.4.0"):
        if gain == 0:
            return {}
    # 0.3.5 read total debt and delegated assets from strategy
    if Version(version) >= Version("0.3.5"):
        total_debt = vault.strategies(strategy, height=pre_height).totalDebt
        delegated_assets = strategy.delegatedAssets(height=pre_height)
        total_assets = total_debt - delegated_assets
    # 0.3.4 don't charge the management fee on delegated assets
    elif Version(version) >= Version("0.3.4"):
        total_debt = vault.totalDebt(height=pre_height)
        delegated_assets = vault.delegatedAssets(height=pre_height)
        total_assets = total_debt - delegated_assets
    # 0.3.1 charge the management fee amount in strategies instead of vault assets
    elif Version(version) >= Version("0.3.1"):
        total_assets = vault.totalDebt(height=pre_height)
    elif Version(version) >= Version("0.3.0"):
        total_assets = vault.totalAssets(height=pre_height)
    else:
        raise ValueError("invalid version %s", version)

    # NOTE the calculation is inaccurate if fees were changed in the same block as harvest
    management_fee_bps = vault.managementFee(height=pre_height)
    performance_fee_bps = vault.performanceFee(height=pre_height)
    strategist_fee_bps = vault.strategies(strategy, height=pre_height).performanceFee

    management_fee = total_assets * duration * management_fee_bps // MAX_BPS // SECS_PER_YEAR
    strategist_fee = gain * strategist_fee_bps // MAX_BPS
    performance_fee = gain * performance_fee_bps // MAX_BPS

    total_fee = management_fee + performance_fee + strategist_fee
    # 0.3.5 management fee is reduced if the total fee exceeds the gain
    if Version(version) >= Version("0.3.5"):
        if total_fee > gain:
            total_fee = gain
            management_fee = gain - performance_fee - strategist_fee

    return {
        "management_fee": management_fee,
        "performance_fee": performance_fee,
        "governance_fee": management_fee + performance_fee,
        "strategist_fee": strategist_fee,
        "total_fee": total_fee,
        "duration": duration,
        "gain": gain,
    }
