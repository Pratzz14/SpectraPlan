"""Fetch immutable, public embedding artifacts; never needs project secrets."""
import hashlib
import json
import os
from pathlib import Path
from urllib.request import urlopen

REVISION = 'aa8f8b060edb00e03bfdd08813a2949946c8ba55'
FILES = {
    'config.json':'13582bcf2effc85b7bf3d3f5532e686bc1c9ce86bb009d10f0ec33cbe92299dd',
    'model_optimized.onnx':'51f1bd0addd6e859e42c2c8021a5e5461385bb676a649f4b269aa445449f2431',
    'special_tokens_map.json':'5d5b662e421ea9fac075174bb0688ee0d9431699900b90662acd44b2a350503a',
    'tokenizer.json':'d241a60d5e8f04cc1b2b3e9ef7a4921b27bf526d9f6050ab90f9267a1f9e5c66',
    'tokenizer_config.json':'0b29c7bfc889e53b36d9dd3e686dd4300f6525110eaa98c76a5dafceb2029f53',
}


def main():
    root=Path(os.environ['EMBEDDING_CACHE_DIR'])/'models--Qdrant--bge-small-en-v1.5-onnx-Q'
    snapshot=root/'snapshots'/REVISION
    snapshot.mkdir(parents=True,exist_ok=True)
    for name,expected in FILES.items():
        with urlopen(f'https://huggingface.co/Qdrant/bge-small-en-v1.5-onnx-Q/resolve/{REVISION}/{name}',timeout=120) as response:
            data=response.read()
        if hashlib.sha256(data).hexdigest()!=expected:
            raise ValueError('Embedding artifact checksum mismatch: '+name)
        (snapshot/name).write_bytes(data)
    (root/'refs').mkdir(exist_ok=True)
    (root/'refs/main').write_text(REVISION,encoding='utf-8')


if __name__=='__main__':main()
