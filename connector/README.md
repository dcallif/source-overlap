# Source Overlap connector

A small command-line relay that connects LM Studio on your computer to a hosted
Source Overlap app. The connector opens an outbound WebSocket to the app, so you
do not need a public IP, port forwarding, or a tunnel.

## Requirements

- Python 3.10 or newer.
- LM Studio with a chat model loaded.
- LM Studio's local server running at `http://127.0.0.1:1234/v1` (the default).

## Install

From the repository root:

```powershell
cd connector
python -m pip install .
```

Or, with [pipx](https://pipx.pypa.io/):

```powershell
pipx install .\connector
```

## Use

1. Open the hosted Source Overlap site and create a pairing code.
2. Run the command shown on the site, for example:

```powershell
source-overlap-connect --server https://source-overlap.onrender.com --code ABCD-1234
```

3. Keep the terminal open while you use the app. Press `Ctrl+C` to stop.

The connector checks LM Studio every 25 seconds and reconnects automatically if
the network drops. If the pairing code expires or the hosted service restarts,
create a new code on the site and run the command again.

## Options

| Option | Default | Purpose |
|---|---|---|
| `--server` | required | Hosted app URL |
| `--code` | required | One-time pairing code from the app |
| `--lm-studio-url` | `http://127.0.0.1:1234/v1` | Local LM Studio OpenAI-compatible endpoint |

The connector only forwards `/v1/models` and `/v1/chat/completions` requests. It
does not expose your local filesystem, shell, or any other local service.
