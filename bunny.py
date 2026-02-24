from dotenv import load_dotenv
import os
import httpx

load_dotenv()

BUNNY_STORAGE_ZONE = os.getenv("BUNNY_STORAGE_ZONE")
BUNNY_API_KEY = os.getenv("BUNNY_STORAGE_API_KEY")
BUNNY_REGION = os.getenv("BUNNY_STORAGE_REGION", "storage")

client = httpx.AsyncClient(timeout=20.0)

async def fetch_md_from_bunny(file_path: str) -> str:
    url = f"https://{BUNNY_REGION}/{BUNNY_STORAGE_ZONE}/{file_path}"

    response = await client.get(
        url,
        headers={"AccessKey": BUNNY_API_KEY}
    )
    response.raise_for_status()
    return response.text