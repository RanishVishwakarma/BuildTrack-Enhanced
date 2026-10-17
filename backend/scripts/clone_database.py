"""Copy every collection of one MongoDB database into another on the same cluster.

Used to create the `buildtrack_demo` working copy so migrations and demo data
never touch the shared `buildtrack` database.

    python scripts/clone_database.py --source buildtrack --target buildtrack_demo

The source is only read. The target must differ from the source and must not
already exist unless --replace is given.
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

from app.core.config import settings  # noqa: E402

PROTECTED = {"buildtrack"}


async def clone(source: str, target: str, replace: bool) -> None:
    if source == target:
        raise SystemExit("Source and target must differ.")
    if target in PROTECTED:
        raise SystemExit(f"Refusing to write to protected database '{target}'.")

    client = AsyncIOMotorClient(settings.mongodb_url)
    existing = await client.list_database_names()
    if source not in existing:
        raise SystemExit(f"Source database '{source}' not found.")
    if target in existing:
        if not replace:
            raise SystemExit(f"Target '{target}' already exists. Pass --replace to overwrite it.")
        await client.drop_database(target)

    src, dst = client[source], client[target]
    for name in sorted(await src.list_collection_names()):
        docs = await src[name].find({}).to_list(None)
        if docs:
            await dst[name].insert_many(docs, ordered=False)
        else:
            await dst.create_collection(name)
        async for index in src[name].list_indexes():
            if index["name"] == "_id_":
                continue
            options = {k: v for k, v in index.items() if k not in {"v", "key", "ns"}}
            await dst[name].create_index(list(index["key"].items()), **options)
        print(f"{name}: {len(docs)} documents")
    print(f"Copied '{source}' -> '{target}'.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", default="buildtrack")
    parser.add_argument("--target", required=True)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    asyncio.run(clone(args.source, args.target, args.replace))
