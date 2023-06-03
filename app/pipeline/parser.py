from __future__ import annotations
import json
from enum import Enum
from app.infrastructure.cache import Cache
from pyflink.common.typeinfo import Types
from pyflink.common.types import Row

class SourceTypes(str, Enum):
    SYNTHETIC_FINANCIAL_DATASETS = "synthetic_financial_datasets"
    TARGET = "target"

class Parser:
    def __init__(
        self,
        source: str,
        target: str,
        source_parser_file_path: str,
        target_parser_file_path: str
    ):
        self._source_types = self.get_types(source_parser_file_path)
        self._target_types = self.get_types(target_parser_file_path)
        self._source = source
        self._target = target
        query = None

        if self._source == SourceTypes.SYNTHETIC_FINANCIAL_DATASETS and self._target == SourceTypes.TARGET:
            self.parse = self.from_sfd_to_target
            query = {
                'transaction_id' : 'uuid()',
                '"timestamp"' : 'toTimestamp(now())',
                'user_id' : '?',
                'account_id' : '?',
                'bank_id' : '?',
                'balance_before' : '?',
                'balance_after' : '?',
                'account_type' : '?',
                'counterparty_account_id' : '?',
                'counterparty_isinternal' : '?',
                'counterparty_type' : '?',
                'counterparty_name' : '?',
                'amount' : '?',
                'direction' : '?',
                'status' : '?',
                'source_location' : '?',
                'is_fraud' : '?',
                'fraud_confidence' : '?',
            }
        else:
            raise NotImplementedError(f"Parser from {self._source} to {self._target} not implemented")

        if query is not None:
            self.insert = f"""
            INSERT INTO fraud_detection.transactions
            ({','.join(query.keys())})
            VALUES
            ({','.join(query.values())})
            """

    @classmethod
    def get_types(cls, file: str):
        with open(file) as f:
            types = json.load(f)
        converted = {}
        for k,v in types.items():
            converted[k] = cls.convert_types(v)
        return Types.ROW_NAMED(
            list(converted.keys()),
            list(converted.values())
        )

    @classmethod
    def convert_types(cls, type_str: str) -> Types:
        type_str = type_str.lower().strip()
        if type_str in ["string", "text"]:
            return Types.STRING()
        elif type_str in ["double"]:
            return Types.DOUBLE()
        elif type_str in ["boolean", "bool"]:
            return Types.BOOLEAN()
        elif type_str in ["int", "integer"]:
            return Types.INT()
        elif type_str in ["float"]:
            return Types.FLOAT()
        elif type_str in ["floattuple"]:
            return Types.TUPLE([Types.FLOAT(), Types.FLOAT()])
        else:
            raise Exception(f"Unknown type {type_str}")

    @staticmethod
    def from_sfd_to_target(record, conf_cache, conf_logs):
        cache = Cache.from_conf(
            "parser-cache",
            conf_cache,
            conf_logs
        )
        #
        account = cache.read(record["nameOrig"], is_dict=True)
        counterparty_id = record["nameDest"]
        counterparty_type = None
        counterparty_isinternal = False
        if cache.key_exists(counterparty_id):
            counterparty = cache.read(record["nameDest"], is_dict=True)
            counterparty_id = counterparty["user_id"]
            counterparty_type = counterparty["type"]
            counterparty_isinternal = True
        #
        if float(record["oldbalanceOrg"]) > float(record["newbalanceOrig"]):
            direction = "inbound"
        else:
            direction = "outbound"
        #
        if record["amount"] > 5000:
            is_fraud = 1
        else:
            is_fraud = 0
        fraud_conf = 1.0
        #
        output = Row(
            user_id = account["user_id"],
            account_id = record["nameOrig"],
            bank_id = account["bank_id"],
            balance_before = record["oldbalanceOrg"],
            balance_after = record["newbalanceOrig"],
            account_type = account["type"],
            counterparty_account_id = counterparty_id,
            counterparty_isinternal = counterparty_isinternal,
            counterparty_type = counterparty_type,
            counterparty_name = None,
            amount = record["amount"],
            direction = direction,
            status = "confirmed",
            source_location = None,
            is_fraud = is_fraud,
            fraud_confidence = fraud_conf
        )
        return output

