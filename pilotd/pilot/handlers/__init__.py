"""
RPC handler modules.

Each submodule exposes a module-level ``METHODS`` dict::

    METHODS = {"action_name": async_callable, ...}

``pilot.sockserver`` stitches them into ``{category}.{action}`` routes.
"""
