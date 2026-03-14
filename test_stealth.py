import asyncio
from playwright.async_api import async_playwright

async def main():
    try:
        from playwright_stealth import stealth_async
        print("IMPORTED stealth_async")
    except ImportError:
        try:
            from playwright_stealth import stealth
            print("IMPORTED stealth")
        except Exception as e:
            print(f"FAILED: {e}")

asyncio.run(main())
