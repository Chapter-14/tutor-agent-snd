import os

import httpx

BUNNY_STORAGE_ZONE = os.getenv("BUNNY_STORAGE_ZONE", "")
BUNNY_API_KEY = os.getenv("BUNNY_STORAGE_API_KEY", "")
BUNNY_REGION = os.getenv("BUNNY_STORAGE_REGION", "storage")


def _validate_path(file_path: str) -> None:
    if ".." in file_path or file_path.startswith("/") or "\x00" in file_path:
        raise ValueError(f"Invalid file path: {file_path}")


async def fetch_md_from_bunny(file_path: str) -> str:
    _validate_path(file_path)
    url = f"https://{BUNNY_REGION}/{BUNNY_STORAGE_ZONE}/{file_path}"

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(url, headers={"AccessKey": BUNNY_API_KEY})
        response.raise_for_status()
        return response.text
