"""Load and validate a frozen host inference profile."""

import tomllib
from urllib.parse import urlsplit

from benchmarking.files import Asset, keys, read_file, text

from .contracts import InferenceConfig
from .registry import wire_adapter


def load_inference_config(path):
    path = path.absolute()
    source = Asset(read_file(path.parent, path.name), "toml")
    data = tomllib.loads(source.content.decode())
    keys(data, {"base_url", "model", "api_key_env", "max_requests",
                "request_timeout_seconds", "wire_api"},
         {"max_input_tokens", "max_output_tokens", "max_wall_seconds", "proxy_url"}, "inference profile")
    url = urlsplit(text(data["base_url"], "inference endpoint"))
    if (url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password or url.query
            or url.fragment or ".." in url.path or "%" in url.path):
        raise ValueError("Inference requires a fixed HTTP(S) base URL without credentials, query or fragment")
    if url.port is not None and not 1 <= url.port <= 65535:
        raise ValueError("Invalid inference endpoint port")
    if 'proxy_url' in data:
        proxy = urlsplit(text(data['proxy_url'], 'inference proxy'))
        if (proxy.scheme != 'http' or not proxy.hostname or proxy.username or proxy.password
                or proxy.path not in {'', '/'} or proxy.query or proxy.fragment
                or proxy.port is not None and not 1 <= proxy.port <= 65535):
            raise ValueError('Inference proxy requires a fixed HTTP origin without credentials or a path')
    text(data["model"], "model")
    if not text(data["api_key_env"], "key environment variable").isidentifier():
        raise ValueError("Invalid credential environment variable name")
    for name in ("max_requests", "request_timeout_seconds"):
        if type(data[name]) is not int or data[name] <= 0:
            raise ValueError(f"{name} must be a positive integer")
    for name in ("max_input_tokens", "max_output_tokens", "max_wall_seconds"):
        if name in data and (type(data[name]) is not int or data[name] <= 0):
            raise ValueError(f"{name} must be a positive integer")
    wire_api = text(data["wire_api"], "inference wire_api")
    wire_adapter(wire_api)
    return InferenceConfig(*(data[k] for k in ("base_url", "model", "api_key_env", "max_requests",
                                             "request_timeout_seconds")), source, wire_api,
                           *(data.get(k) for k in ("max_input_tokens", "max_output_tokens",
                                                   "max_wall_seconds", "proxy_url")))
