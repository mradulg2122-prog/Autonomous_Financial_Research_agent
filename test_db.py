import asyncio
import asyncpg

async def test():
    try:
        conn = await asyncpg.connect('postgresql://ara1_user:ara1_secure_password_change_me@localhost:5432/ara1')
        print('Connected to PostgreSQL!')
        await conn.close()
    except Exception as e:
        print(f'Error: {e}')

asyncio.run(test())
