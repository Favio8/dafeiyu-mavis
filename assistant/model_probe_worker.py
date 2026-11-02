"""Interruptible diagnostic API calls, fixed provider/vault reference and no tools."""
import asyncio
import json
import os
import sys

from .ipc import Message,MAX_MESSAGE,Receiver,decode,encode


def main():
    from .credentials import Credentials,CredentialUnavailable
    from .provider import DeepSeekProvider,ProviderSettings,ProviderError
    from .model_diagnostics import probe
    import threading
    first=decode(sys.stdin.buffer.readline(MAX_MESSAGE+1))
    if first.kind!="hello" or first.role!="host" or first.seq!=1:return 2
    receiver=Receiver(first.session,"host",first.task_id,first.generation)
    receiver.accept(encode(first))
    sequence=0
    def reply(kind,payload):
        nonlocal sequence
        sequence+=1
        sys.stdout.buffer.write(encode(Message(session=first.session,role="worker",seq=sequence,task_id=first.task_id,generation=first.generation,kind=kind,payload=payload)))
        sys.stdout.buffer.flush()
    reply("ready",str(os.getpid()))
    while data:=sys.stdin.buffer.readline(MAX_MESSAGE+1):
        request=receiver.accept(data)
        if request.kind=="stop":return 0
        if request.kind!="model_probe":return 2
        value=json.loads(request.payload)
        try:
            settings=ProviderSettings.model_validate_json(json.dumps(value["settings"]))
            secret=Credentials().read("deepseek/default")
            if not secret:raise ProviderError("CREDENTIAL_MISSING")
            client=DeepSeekProvider(settings,secret)
            result=asyncio.run(probe(client,value["kind"],threading.Event()))
            reply("model_result",json.dumps(result))
        except (ProviderError,CredentialUnavailable,ValueError) as exc:
            reply("model_result",json.dumps({"passed":False,"error":str(exc) if isinstance(exc,(ProviderError,CredentialUnavailable)) else "INVALID_PROBE_SETTINGS"}))
    return 0


if __name__=="__main__":raise SystemExit(main())
