"""Opt-in physical checks. Reads credentials over SSH; never persists them.

Run from the repository root with --control to exercise and restore lock/temperature.
Only the child-room thermostat receives a temporary 0.5 degree reduction.
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from custom_components.trv_scheduler.gateway import GatewayError, ShellyGateway


async def main(control):
    raw = await asyncio.to_thread(
        subprocess.check_output,
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            "root@10.0.12.15",
            "cat /config/.storage/core.config_entries",
        ],
    )
    entries = json.loads(raw)["data"]["entries"]
    config = next(e["data"] for e in entries if e["entry_id"] == "01K9JD7YV2ZK7RTS62T3VQR2ZA")
    shared = asyncio.Lock()
    baseline = {}
    async with httpx.AsyncClient() as client:
        gateways = {i: ShellyGateway(client, lambda: config, i, shared) for i in (200, 201, 202)}
        for component, gateway in gateways.items():
            try:
                ui = await gateway._rpc("Sys.GetConfig")
                state = await gateway._rpc("TRV.GetStatus", {"id": 0})
            except GatewayError:
                print(
                    json.dumps({"component": component, "unreachable": True, "changed": False}),
                    flush=True,
                )
                continue
            baseline[component] = {"ui": ui["ui"], "target_C": state["target_C"]}
            print(json.dumps({"component": component, "baseline": baseline[component]}), flush=True)
        fd = os.open("/tmp/trv-live-baseline.json", os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump(baseline, stream, indent=2)
        if not control:
            return
        for component, gateway in gateways.items():
            if component not in baseline:
                continue
            original = baseline[component]
            touched_temperature = False
            try:
                assert await gateway.async_set_lock(True) is True
                print(json.dumps({"component": component, "lock_confirmed": True}), flush=True)
                if component == 202:
                    target = max(4, original["target_C"] - 0.5)
                    touched_temperature = True
                    await gateway._rpc("TRV.SetTarget", {"id": 0, "target_C": target})
                    status = await gateway._rpc("TRV.GetStatus", {"id": 0})
                    assert abs(status["target_C"] - target) < 0.05
                    assert await gateway.async_read_lock() is True
                    print(
                        json.dumps(
                            {"component": component, "remote_setpoint_while_locked": target}
                        ),
                        flush=True,
                    )
            finally:
                # Always attempt both independent restorations, even after a partial failure.
                errors = []
                if touched_temperature:
                    try:
                        await gateway._rpc(
                            "TRV.SetTarget", {"id": 0, "target_C": original["target_C"]}
                        )
                        state = await gateway._rpc("TRV.GetStatus", {"id": 0})
                        assert abs(state["target_C"] - original["target_C"]) < 0.05
                    except Exception as err:
                        errors.append(type(err).__name__)
                try:
                    await gateway.async_set_lock(original["ui"]["lock"])
                    config_now = await gateway._rpc("Sys.GetConfig")
                    assert config_now["ui"] == original["ui"]
                except Exception as err:
                    errors.append(type(err).__name__)
                print(
                    json.dumps({"component": component, "restored": not errors, "errors": errors}),
                    flush=True,
                )
                if errors:
                    raise RuntimeError(
                        "Restoration incomplete; inspect /tmp/trv-live-baseline.json"
                    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--control", action="store_true")
    asyncio.run(main(parser.parse_args().control))
