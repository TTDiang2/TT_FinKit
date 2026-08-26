"""One-shot: run evaluate_all_factors to fill factor_evaluations (IC/win rate)."""
import asyncio
import sys

sys.path.insert(0, ".")


async def main() -> None:
    from sqlalchemy import select
    from app.database import async_session_maker

    async with async_session_maker() as db:
        uid = (await db.execute(
            __import__("sqlalchemy").text("SELECT id FROM users ORDER BY created_at LIMIT 1")
        )).scalar()
        from app.services.factor_evaluation import evaluate_all_factors
        r = await evaluate_all_factors(db, uid)
        print("evaluated:", len(r.get("evaluated", [])), "skipped:", len(r.get("skipped", [])))
        for e in r.get("evaluated", [])[:8]:
            print(f"  {e.get('factor_key')}: ic={e.get('ic_mean')} win={e.get('win_rate')} passed={e.get('passed')}")
        await db.commit()


asyncio.run(main())