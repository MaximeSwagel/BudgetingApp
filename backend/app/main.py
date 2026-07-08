import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.database import engine, async_session
from app.models import Base, CategoryGroup, Category
from app.routers import upload, transactions, categories, budget, dashboard

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="BudgetingApp API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload.router)
app.include_router(transactions.router)
app.include_router(categories.router)
app.include_router(budget.router)
app.include_router(dashboard.router)

SEED_CATEGORIES = {
    "Home Expenses": ["Rent", "Utilities: Gas, Electric, Water", "Internet, TV"],
    "Household Expenses": [
        "Groceries", "ATM Withdrawals", "Clothing", "Furniture & Equipment",
        "Laundry & Dry Cleaning", "Cell Phone",
    ],
    "Insurance, Tax & Bank Fees": [
        "Renters Insurance", "Other Insurance", "Income Tax", "Bank Fees",
    ],
    "Health Care": ["Health Insurance", "Dental Insurance", "Doctor & Dentist"],
    "Discretionary": [
        "Restaurants & Coffee Shops", "Classes", "Subscriptions",
        "Concerts & Shows", "Gym/Sports", "Travel/Vacation",
    ],
}


@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        result = await session.execute(select(CategoryGroup))
        if result.scalars().first() is None:
            for order, (group_name, cats) in enumerate(SEED_CATEGORIES.items()):
                group = CategoryGroup(name=group_name, display_order=order)
                session.add(group)
                await session.flush()
                for cat_order, cat_name in enumerate(cats):
                    session.add(Category(name=cat_name, group_id=group.id, display_order=cat_order))
            await session.commit()


@app.get("/api/health")
async def health():
    return {"status": "ok"}
