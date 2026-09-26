#!/usr/bin/env python3
# DESC: Serve the published Laya "english" bundle alongside one fine-tuned checkpoint directory under its own model name, for system-one's laya backend when SYSTEM_ONE_MODEL_DIR is set
"""
Shim around laya.serve so system-one can serve a fine-tuned checkpoint
directory side by side with the published `convaiinnovations/laya` "english"
bundle, both preloaded, the checkpoint under a name of our choosing (e.g.
"full-v1") that clients put in the request's `model` field as they would
"english".

`laya.serve.build_router()` reads LAYA_MODELS to decide which of the three
published checkpoints to preload; it has no way to point an arbitrary
directory at a model name. This script does what `laya.serve.main()` does,
step for step, with one difference before the Router is built: the checkpoint
is registered as a fourth model name.

How the name is registered. Every name a request or the Router sees goes
through `laya.router.normalise_name`, which accepts a name iff it is a key of
the module dict `laya.router.DEFAULT_MODELS` (or an alias of one), and
`laya.serve._resolve_model` additionally requires the normalised key to be in
the module set `laya.serve._KNOWN_MODELS` (else it treats the field as a
foreign Jev model id and auto-routes). Both are plain module globals read at
call time, so adding the checkpoint's name to each, before `Router()` is
constructed, makes the whole stack -- Router.__init__/load/preload/predict,
_resolve_model, /health's `loaded` list, the response's `model` field --
carry the friendly name natively. Nothing is monkeypatched: no function is
replaced, two module-level containers gain one entry each. The published
"multilingual" and "typed-decisions" slots are removed from the Router's
model map so that no request can make this process attempt to load (i.e.
download) either; a request naming one answers 500 like any unknown
checkpoint. (`normalise_name` still accepts the two names, so they fail at
`Router.load`, not at parsing; same client-visible outcome.)

Everything else is laya's own code -- the LAYA_THREADS cap, the preload, the
single-worker inference pool and its asyncio gate, the /health and
/v1/systemone routes, the port validation, the uvicorn call -- so /health,
latency and error handling are those of `laya-serve`; only the model map and
the loaded-model count differ.

The name must be a lowercase `[a-z0-9._-]+` token (normalise_name lowercases
before the lookup, so a mixed-case name could never match its own key) and
must not be one of laya's slot names or aliases (english, multilingual,
typed-decisions, en, laya, default, typed, decisions, ...).

Env vars honoured, same names, meaning and defaults as laya.serve.main()
(the wrapper sets LAYA_HOST/LAYA_PORT; the rest pass through):
  LAYA_HOST       bind address (default 0.0.0.0, as laya-serve; the wrapper
                  always passes 127.0.0.1)
  LAYA_PORT       bind port (default 8000), validated as laya-serve does
  LAYA_DEVICE     torch device (default: auto)
  LAYA_PRELOAD    build both models at startup, not on the first request
                  (default 1)
  LAYA_THREADS    cap torch intra-op threads for CPU inference (default: torch's)
  LAYA_API_KEY    if set, require Authorization: Bearer <it>
  LAYA_LOG_LEVEL  uvicorn log level (default info)
LAYA_MODELS is not read: the models served are "english" and the checkpoint.
HF_HUB_OFFLINE is not set here; the wrapper sets it on every start. Set it
yourself when running this by hand and the bundle is already cached.

Usage:
    system-one-serve.py --model-dir <checkpoint dir> --name <model name>
"""
import argparse
import os
import re
import sys

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Serve the published Laya 'english' bundle plus one checkpoint "
                    "directory under --name, over laya.serve's /v1/systemone and /health routes.",
        epilog=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model-dir", required=True,
                        help="Path to a Laya checkpoint directory "
                             "(loadable with laya.Agent(dir)).")
    parser.add_argument("--name", required=True,
                        help="Model name the checkpoint is served under (a request's "
                             "`model` field; shows in /health's `loaded`). Lowercase "
                             "[a-z0-9._-], not one of laya's own slot names or aliases.")
    args = parser.parse_args()

    model_dir = os.path.abspath(args.model_dir)
    if not os.path.isdir(model_dir):
        sys.exit("system-one-serve: not a directory: %s" % (model_dir,))
    for fname in ("rl_agent_config.json", "model.safetensors"):
        if not os.path.isfile(os.path.join(model_dir, fname)):
            sys.exit("system-one-serve: not a Laya checkpoint directory (no %s): %s" % (fname, model_dir))
    name = args.name
    if not NAME_RE.match(name):
        sys.exit("system-one-serve: --name must be lowercase [a-z0-9._-]: %r" % (name,))

    # The same private helpers main() uses, in the same order: the thread cap
    # before torch does any work, the port check before the model load so a
    # bad port fails in milliseconds rather than after a multi-second preload.
    from laya import router as laya_router, serve as laya_serve
    from laya.router import Router
    from laya.serve import _apply_thread_limit, _env_bool, _resolve_port, create_app

    # The two registries described in the module docstring. Checked by
    # attribute so a laya release that renames either fails here with a
    # sentence, not deep inside a request with a 500.
    for mod, attr, kind in ((laya_router, "DEFAULT_MODELS", dict),
                            (laya_router, "_ALIASES", dict),
                            (laya_serve, "_KNOWN_MODELS", set)):
        if not isinstance(getattr(mod, attr, None), kind):
            sys.exit("system-one-serve: this laya version has no %s.%s (%s); the shim needs updating"
                     % (mod.__name__, attr, kind.__name__))
    if name in laya_router.DEFAULT_MODELS or name in laya_router._ALIASES:
        sys.exit("system-one-serve: --name %r is one of laya's own model names or aliases; pick another"
                 % (name,))

    port = _resolve_port()
    _apply_thread_limit()
    device = os.environ.get("LAYA_DEVICE") or None

    # Register the checkpoint under its own name (see the docstring), then
    # build the Router exactly as build_router() would: it copies
    # DEFAULT_MODELS, so the new entry is in its map with no `models=`
    # override needed. The two published slots this setup never uses are
    # dropped from that map so nothing can ask this process to fetch them.
    laya_router.DEFAULT_MODELS[name] = (model_dir, None)
    laya_serve._KNOWN_MODELS.add(name)
    router = Router(device=device, max_loaded=2,
                    auto_task_detection=_env_bool("LAYA_AUTO_TASK", False))
    for unused in ("multilingual", "typed-decisions"):
        router.models.pop(unused, None)
    if _env_bool("LAYA_PRELOAD", True):
        router.preload(["english", name])

    import uvicorn
    uvicorn.run(
        create_app(router),
        host=os.environ.get("LAYA_HOST", "0.0.0.0"),
        port=port,
        log_level=os.environ.get("LAYA_LOG_LEVEL", "info"),
    )


if __name__ == "__main__":
    main()
