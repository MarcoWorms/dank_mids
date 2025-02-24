import functools
from types import MethodType
from typing import Any, Coroutine, Dict, Optional, Tuple, Union

from brownie import Contract
from brownie.network.contract import ContractCall, ContractTx, OverloadedMethod
from dank_mids.brownie_patch.call import _patch_call
from web3 import Web3


def _patch_overloaded_method(call: OverloadedMethod, w3: Web3) -> None:
    @functools.wraps(call)
    async def coroutine(
        self: Contract,
        *args: Tuple[Any,...],
        block_identifier: Optional[Union[int, str, bytes]] = None,
        override: Optional[Dict[str, str]] = None
    ) -> Any:
        fn = self._get_fn_from_args(args)
        kwargs = {"block_identifier": block_identifier, "override": override}
        kwargs = {k: v for k, v in kwargs.items() if v is not None}
        return await fn.coroutine(*args, **kwargs)

    for args, method in call.__dict__['methods'].items():
        if isinstance(method, ContractCall) or isinstance(method, ContractTx):
            _patch_call(method, w3)
    # TODO implement this properly
        #elif isinstance(call, ContractTx):
            #_patch_tx(call, w3)
    
    call.coroutine = MethodType(coroutine, call)
