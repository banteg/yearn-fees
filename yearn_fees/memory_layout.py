import json

# output by a modified vyper compiler
# https://gist.github.com/banteg/5e89aeeb2b1f5a5f982dc6d340c52b09
MEMORY_LAYOUT = {
    "0.3.0": {
        "_assessFees": {
            "#internal_0": 12,
            "strategy": 10,
            "gain": 11,
            "governance_fee": 13,
            "strategist_fee": 14,
            "total_fee": 15,
        }
    },
    "0.3.1": {
        "_assessFees": {
            "#internal_0": 12,
            "strategy": 10,
            "gain": 11,
            "governance_fee": 13,
            "strategist_fee": 14,
            "total_fee": 15,
        }
    },
    "0.3.2": {
        "_assessFees": {
            "#internal_0": 12,
            "strategy": 10,
            "gain": 11,
            "governance_fee": 13,
            "strategist_fee": 14,
            "total_fee": 15,
        }
    },
    "0.3.3": {
        "_assessFees": {
            "#internal_0": 12,
            "strategy": 10,
            "gain": 11,
            "governance_fee": 13,
            "strategist_fee": 14,
            "total_fee": 15,
        }
    },
    "0.3.4": {
        "_assessFees": {
            "#internal_0": 12,
            "strategy": 10,
            "gain": 11,
            "governance_fee": 13,
            "strategist_fee": 14,
            "total_fee": 15,
        }
    },
    "0.3.5": {
        "_assessFees": {
            "#internal_0": 12,
            "strategy": 10,
            "gain": 11,
            "precisionFactor": 13,
            "management_fee": 14,
            "strategist_fee": 15,
            "performance_fee": 16,
            "total_fee": 17,
        }
    },
    "0.4.0": {
        "_assessFees": {
            "#internal_0": 12,
            "strategy": 10,
            "gain": 11,
            "duration": 13,
            "management_fee": 14,
            "strategist_fee": 15,
            "performance_fee": 16,
            "total_fee": 17,
        }
    },
    "0.4.1": {
        "_assessFees": {
            "#internal_0": 12,
            "strategy": 10,
            "gain": 11,
            "duration": 13,
            "management_fee": 14,
            "strategist_fee": 15,
            "performance_fee": 16,
            "total_fee": 17,
        }
    },
    "0.4.2": {
        "_assessFees": {
            "#internal_0": 12,
            "strategy": 10,
            "gain": 11,
            "duration": 13,
            "management_fee": 14,
            "strategist_fee": 15,
            "performance_fee": 16,
            "total_fee": 17,
        }
    },
    "0.4.3": {
        "_assessFees": {
            "#internal_0": 12,
            "strategy": 10,
            "gain": 11,
            "duration": 13,
            "management_fee": 14,
            "strategist_fee": 15,
            "performance_fee": 16,
            "total_fee": 17,
        }
    },
}

# computed from combining source_map and ast outputs
PROGRAM_COUNTERS = json.load(open("metadata/pcs_by_version.json"))
