"""Talk to a voice agent from the keyboard, through the same WebSocket protocol a telephony bridge uses.

    python -m northcx.voice_sim ws://localhost:3000/v1/voice/stream --key <channel key> [--language es] [--from +15551234567]

Type what the caller says and press Enter. `/dtmf 0` presses keys, `/silence` simulates a quiet caller, `/hangup` ends the call.
What the agent says is printed; it is treated as played in full a moment later (type over it to interrupt).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys


async def main(url: str, key: str | None, language: str | None, caller: str) -> int:
    import websockets
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    async with websockets.connect(url, additional_headers=headers) as ws:
        await ws.send(json.dumps({"type": "start", "callId": "sim", "from": caller, "to": "+15550000000", **({"language": language} if language else {})}))
        loop = asyncio.get_running_loop()

        async def listen() -> None:
            async for raw in ws:
                m = json.loads(raw)
                if m["type"] == "say":
                    print(f"  agent [{m['language']}]: {m['text']}")
                    await asyncio.sleep(0.4)           # pretend the audio takes a moment to play
                    await ws.send(json.dumps({"type": "speech_ended", "utteranceId": m["id"], "completed": True}))
                elif m["type"] == "stop_speaking":
                    print("  (agent stopped talking)")
                else:
                    print(f"  >> {m}")
                    if m["type"] in ("transfer", "hangup"):
                        return

        task = asyncio.create_task(listen())
        while not task.done():
            line = await loop.run_in_executor(None, sys.stdin.readline)
            if not line:
                break
            line = line.strip()
            if line == "/hangup":
                await ws.send(json.dumps({"type": "end"}))
                break
            if line.startswith("/dtmf "):
                await ws.send(json.dumps({"type": "dtmf", "digits": line[6:]}))
            elif line == "/silence":
                await ws.send(json.dumps({"type": "silence", "seconds": 8}))
            elif line:
                await ws.send(json.dumps({"type": "transcript", "text": line, "final": True}))
        await asyncio.sleep(0.5)
        task.cancel()
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("url")
    p.add_argument("--key")
    p.add_argument("--language")
    p.add_argument("--from", dest="caller", default="+15551234567")
    a = p.parse_args()
    sys.exit(asyncio.run(main(a.url, a.key, a.language, a.caller)))
