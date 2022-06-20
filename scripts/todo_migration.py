# type: ignore
# flake8: noqa

from uuid import uuid4
import discord

for record in await bot.db.fetch("SELECT * FROM todos"):
    _id = uuid4()
    await bot.db.execute(
        """
        UPDATE todos
        SET
            todo_id=$1,
            created_at=$2
        WHERE
            user_id=$3 AND
            message_id=$4
        """,
        _id,
        discord.utils.snowflake_time(record["message_id"]),
        record["user_id"],
        record["message_id"],
    )
