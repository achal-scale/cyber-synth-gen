#!/usr/bin/env python3
"""Waits for the appserver to seed /canary, mints the verifier token, writes state.json."""
import os, json, time, secrets


def _mint_and_write_vtok():
    tok = os.environ.get("VERIFIER_TOKEN") or secrets.token_hex(32)
    try:
        os.makedirs("/vchan", exist_ok=True)
        with open("/vchan/verifier_token", "w") as f:
            f.write(tok)
        os.chmod("/vchan/verifier_token", 0o600)
    except OSError as e:
        print(f"[setup] WARNING: could not write /vchan/verifier_token: {e}")
    return tok


def main():
    os.makedirs("/canary", exist_ok=True)
    marker = ""
    for _ in range(150):
        try:
            marker = open("/canary/marker").read().strip()
            if marker:
                break
        except OSError:
            pass
        time.sleep(2)
    if not marker:
        raise SystemExit("FATAL: /canary/marker not seeded by appserver")
    try:
        creds = json.load(open("/canary/creds.json"))
    except Exception:
        creds = {}
    state = {"canary": {"FLAG_A1": marker}, "credentials": creds,
             "verifier_token": _mint_and_write_vtok()}
    with open("/canary/state.json", "w") as f:
        json.dump(state, f)
    print(f"[setup] A1 state written (marker {marker[:8]}...)")
    return True


if __name__ == "__main__":
    main()
