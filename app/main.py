from fastapi import FastAPI

app = FastAPI(
    title="Tachyon",
    description="Многопользовательский трекер доходов и расходов",
    version="0.1.0",
)


@app.get("/health", tags=["Система"])
async def health() -> dict[str, str]:
    return {"status": "ok"}