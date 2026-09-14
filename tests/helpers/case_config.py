"""Bind an already materialized test case to its local input snapshots."""

import tomllib

import tomli_w


def standalone_config(config):
    data = tomllib.loads(config)
    for entry in data["task"]["inputs"].values():
        entry.pop("source", None)
        entry.pop("collection_source", None)
    return tomli_w.dumps(data)
