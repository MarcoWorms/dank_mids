
from typing import Any, Callable, Coroutine, Literal, Optional

from eth_utils.curried import (apply_formatter_if, apply_formatters_to_dict,
                               apply_key_map, is_null)
from eth_utils.toolz import assoc, complement, compose, merge
from hexbytes import HexBytes
from multicall.utils import get_async_w3
from web3 import Web3
from web3._utils.rpc_abi import RPC
from web3.providers.async_base import AsyncBaseProvider
from web3.providers.base import BaseProvider
from web3.types import Formatters, FormattersDict, RPCEndpoint, RPCResponse

from dank_mids.middleware import dank_middleware
from dank_mids.types import AsyncMiddleware


def setup_dank_w3(async_w3: Web3) -> Web3:
    """ Injects Dank Middleware into an async Web3 instance. """
    assert async_w3.eth.is_async and isinstance(async_w3.provider, AsyncBaseProvider)
    async_w3.middleware_onion.inject(dank_middleware, layer=0)
    async_w3.middleware_onion.add(geth_poa_middleware)
    return async_w3

def setup_dank_w3_from_sync(sync_w3: Web3) -> Web3:
    """ Creates a new async Web3 instance from `w3.provider.endpoint_uri` and injects it with Dank Middleware. """
    assert not sync_w3.eth.is_async and isinstance(sync_w3.provider, BaseProvider)
    return setup_dank_w3(get_async_w3(sync_w3))


# Everything below is in web3.py now, but dank_mids currently needs a version that predates them.

is_not_null = complement(is_null)

FORMATTER_DEFAULTS: FormattersDict = {
    "request_formatters": {},
    "result_formatters": {},
    "error_formatters": {},
}

remap_geth_poa_fields = apply_key_map(
    {
        "extraData": "proofOfAuthorityData",
    }
)

pythonic_geth_poa = apply_formatters_to_dict(
    {
        "proofOfAuthorityData": HexBytes,
    }
)

geth_poa_cleanup = compose(pythonic_geth_poa, remap_geth_poa_fields)

async def geth_poa_middleware(make_request: Callable[[RPCEndpoint, Any], Any], w3: Web3) -> AsyncMiddleware:
    middleware = await async_construct_formatting_middleware(
        result_formatters={
            RPC.eth_getBlockByHash: apply_formatter_if(is_not_null, geth_poa_cleanup),
            RPC.eth_getBlockByNumber: apply_formatter_if(is_not_null, geth_poa_cleanup),
        },
    )
    return await middleware(make_request, w3)

async def async_construct_formatting_middleware(
    request_formatters: Optional[Formatters] = None,
    result_formatters: Optional[Formatters] = None,
    error_formatters: Optional[Formatters] = None,
) -> AsyncMiddleware:
    async def ignore_web3_in_standard_formatters(
        _w3: "Web3",
        _method: RPCEndpoint,
    ) -> FormattersDict:
        return dict(
            request_formatters=request_formatters or {},
            result_formatters=result_formatters or {},
            error_formatters=error_formatters or {},
        )

    return await async_construct_web3_formatting_middleware(
        ignore_web3_in_standard_formatters
    )

async def async_construct_web3_formatting_middleware(
    async_web3_formatters_builder: Callable[
        ["Web3", RPCEndpoint], Coroutine[Any, Any, FormattersDict]
    ]
) -> Callable[
    [Callable[[RPCEndpoint, Any], Any], "Web3"], Coroutine[Any, Any, AsyncMiddleware]
]:
    async def formatter_middleware(
        make_request: Callable[[RPCEndpoint, Any], Any],
        async_w3: "Web3",
    ) -> AsyncMiddleware:
        async def middleware(method: RPCEndpoint, params: Any) -> RPCResponse:
            formatters = merge(
                FORMATTER_DEFAULTS,
                await async_web3_formatters_builder(async_w3, method),
            )
            request_formatters = formatters.pop("request_formatters")

            if method in request_formatters:
                formatter = request_formatters[method]
                params = formatter(params)
            response = await make_request(method, params)

            return _apply_response_formatters(
                method=method, response=response, **formatters
            )

        return middleware

    return formatter_middleware

def _apply_response_formatters(
    method: RPCEndpoint,
    response: RPCResponse,
    result_formatters: Formatters,
    error_formatters: Formatters,
) -> RPCResponse:
    def _format_response(
        response_type: Literal["result", "error"],
        method_response_formatter: Callable[..., Any],
    ) -> RPCResponse:
        appropriate_response = response[response_type]
        return assoc(
            response, response_type, method_response_formatter(appropriate_response)
        )

    if "result" in response and method in result_formatters:
        return _format_response("result", result_formatters[method])
    elif "error" in response and method in error_formatters:
        return _format_response("error", error_formatters[method])
    else:
        return response