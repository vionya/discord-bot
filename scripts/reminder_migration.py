# type: ignore
# flake8: noqa

from uuid import uuid4

for record in await bot.db.fetch("SELECT * FROM reminders"):
    _id = uuid4()
    await bot.db.execute(
        """
        UPDATE reminders
        SET
            reminder_id=$1
        WHERE
            user_id=$2 AND
            message_id=$3
        """,
        _id,
        record["user_id"],
        record["message_id"],
    )
