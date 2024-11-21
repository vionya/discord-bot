-- SPDX-License-Identifier: AGPL-3.0-or-later
-- Copyright (C) 2024 vionya
-- Table: profiles | Documentation for settings --
COMMENT ON COLUMN profiles.receive_highlights IS
'Dictates whether you''ll receive highlights from fuchsia.

**Note:** If fuchsia fails to deliver a highlight to you due to being forbidden to do so, this setting will automatically change to `False` and will need to be manually re-enabled. This may occur if:
- You block fuchsia
- You no longer share any mutual servers with fuchsia

Expected Value Type: A boolean-like (`yes`/`no`) value
Default Value: `True`

**Current Value:** `{}`
';

COMMENT ON COLUMN profiles.hl_timeout IS
'Sets the amount of time (in minutes) that you must be inactive (send no messages) in a channel for highlights from that channel to be sent to you.

Expected Value Type: An integer (from 1 to 5)
Default Value: `1`

**Current Value:** `{}`
';

COMMENT ON COLUMN profiles.timezone IS
'Sets your local timezone.

This is used for localization for some features:
- Reminders - absolute reminders will be set in your configured timezone
- `/timestamp` - timestamps will be generated in your configured timezone by default

Expected Value Type: A valid IANA timezone [[list](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones#List)]
Default Value: `None`

**Current Value:** `{}`
';

COMMENT ON COLUMN profiles.default_ephemeral IS
'Dictates whether slash command responses will be sent ephemerally by default.

Ephemeral messages can be seen by you, and nobody else.

Expected Value Type: A boolean-like (`yes`/`no`) value
Default Value: `False`

**Current Value:** `{}`
';

COMMENT ON COLUMN profiles.silence_hl IS
'Dictates whether highlight messages will be sent as silent messages.

Silent messages will behave like normal messages, with the exception that they will **not** trigger mobile or desktop notifications.

Useful for when you want to have highlights while avoiding notifcation spam.

Expected Value Type: A boolean-like (`yes`/`no`) value
Default Value: `False`

**Current Value:** `{}`
';

COMMENT ON COLUMN profiles.reminders_in_channel IS
'Sets whether reminders will be sent where they were created by default (rather than in DMs).

If this is true, reminders will first try to be sent in the channel where the `/remind set` command was used.

If sending in a channel fails, reminders will still try to DM themselves to you so you don''t miss anything.

You can use the `send-here` parameter in `/remind set` to override this setting at any time.

Expected Value Type: A boolean-like (`yes`/`no`) value
Default Value: `False`

**Current Value:** `{}`
';

-- Table: guild_configs | Documentation for settings --
COMMENT ON COLUMN guild_configs.starboard IS
'Controls whether the server''s starboard is enabled.

Expected Value Type: A boolean-like (`yes`/`no`) value
Default Value: `False`

**Current Value:** `{}`
';

COMMENT ON COLUMN guild_configs.allow_highlights IS
'Controls whether messages in this server can trigger user highlights.

Expected Value Type: A boolean-like (`yes`/`no`) value
Default Value: `True`

**Current Value:** `{}`
';

-- Table: starboards | Documentation for settings --
COMMENT ON COLUMN starboards.channel IS
'Sets the channel that starred messages will be sent to when they exceed the configured star threshold.

**WARNING:** Changing this will delete __all__ current stars.

Expected Value Type: A channel mention

**Current Value:** `{}`
';

COMMENT ON COLUMN starboards.threshold IS
'The threshold which must be exceeded for a message to be sent to the starboard.

Expected Value Type: An integer
Default Value: `5`

**Current Value:** `{}`
';

COMMENT ON COLUMN starboards.super_mult IS
'A multiplier for the amount of stars a super reaction is worth.

If this value is 1, then super reactions behave identically to normal reactions. If it is greater than 1, super reactions will contribute more to the star count of a message.

For example, if a starboard has a threshold of 5, and a super multiplier of 5, then 1 super reaction will immediately star the message.

Or, if a starboard has a threshold of 5, and a super multiplier of 2, then 1 super reaction will bring the star count to 2/5.

Expected Value Type: An integer
Default Value: `1`

**Current Value:** `{}`
';

COMMENT ON COLUMN starboards.format IS
'The format for starred messages.

Expected Value Type: A string of text
Format Variables:
- `stars`: The number of stars a message has.
Default Value: `⭐ **{{stars}}**`

**Current Value:** `{}`
';

COMMENT ON COLUMN starboards.max_days IS
'The maximum age (in days) that a message can be before it can no longer be sent to starboard.

Expected Value Type: An integer
Default Value: `7`

**Current Value:** `{}`
';

COMMENT ON COLUMN starboards.emoji IS
'The emoji that will be used to star messages.
If this is set to an invalid emoji, starboard will cease to function.

**WARNING:** Changing this will delete __all__ current stars.

Expected Value Type: An emoji
Default Value: `⭐`

**Current Value:** {}
';