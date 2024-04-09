-- SPDX-License-Identifier: AGPL-3.0-or-later
-- Copyright (C) 2023 sardonicism-04
CREATE TABLE profiles (
    user_id              BIGINT PRIMARY KEY,
    created_at           TIMESTAMP WITH TIME ZONE DEFAULT (NOW() AT TIME ZONE 'UTC'),
    -- Public settings, directly modified by user
    receive_highlights   BOOLEAN DEFAULT TRUE,
    timezone             TEXT DEFAULT NULL,
    hl_timeout           INT CHECK (hl_timeout >= 1 AND hl_timeout <= 5) DEFAULT 1,
    default_ephemeral    BOOLEAN DEFAULT FALSE,
    silence_hl           BOOLEAN DEFAULT FALSE,
    reminders_in_channel BOOLEAN DEFAULT FALSE,
    -- Private settings, indirectly modified
    hl_blocks            BIGINT[] DEFAULT ARRAY[]::BIGINT[],
);

CREATE TABLE guild_configs (
    guild_id          BIGINT PRIMARY KEY,
    starboard         BOOLEAN DEFAULT FALSE,
    allow_highlights  BOOLEAN DEFAULT TRUE,
);

CREATE TABLE highlights (
    user_id BIGINT NOT NULL,
    content TEXT NOT NULL,
    PRIMARY KEY (user_id, content),
    FOREIGN KEY (user_id) REFERENCES profiles (user_id) ON DELETE CASCADE
);

CREATE TABLE todos (
    user_id    BIGINT NOT NULL,
    content    TEXT NOT NULL,
    todo_id    UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    FOREIGN KEY (user_id) REFERENCES profiles (user_id) ON DELETE CASCADE
);

-- Use foreign keys so that, if a config is deleted from the guild_configs
-- table, all related entries in starboard tables are also deleted
CREATE TABLE starboards (
    guild_id    BIGINT PRIMARY KEY,
    channel     BIGINT,
    threshold   INT CHECK (threshold >= 1) DEFAULT 5,
    super_mult  INT CHECK (super_mult >= 1) DEFAULT 1,
    format      VARCHAR(200) DEFAULT '⭐ **{stars}**',
    max_days    INT CHECK (max_days >= 1) DEFAULT 7,
    emoji       TEXT DEFAULT '⭐',
    ignored     BIGINT[] DEFAULT ARRAY[]::BIGINT[],
    FOREIGN KEY (guild_id) REFERENCES guild_configs (guild_id) ON DELETE CASCADE
);

-- Same as above with foreign keys
CREATE TABLE stars (
    guild_id             BIGINT NOT NULL,
    message_id           BIGINT NOT NULL,
    channel_id           BIGINT NOT NULL,
    stars                INT NOT NULL,
    starboard_message_id BIGINT NOT NULL,
    PRIMARY KEY (guild_id, message_id, channel_id),
    FOREIGN KEY (guild_id) REFERENCES starboards (guild_id) ON DELETE CASCADE
);

CREATE TABLE reminders (
    user_id       BIGINT NOT NULL,
    reminder_id   UUID NOT NULL,
    content       VARCHAR(1000) NOT NULL,
    -- For one-time reminders, this is the time of creation
    -- For repeating reminders, this is the rollover point for each cycle
    epoch         TIMESTAMP WITH TIME ZONE NOT NULL,
    -- The amount of time until the reminder is next triggered
    delta         INTERVAL NOT NULL,
    repeating     BOOLEAN DEFAULT FALSE,
    -- If not null, a channel ID to send to
    deliver_in    BIGINT DEFAULT NULL,
    FOREIGN KEY (user_id) REFERENCES profiles (user_id) ON DELETE CASCADE
);

CREATE TABLE tags (
    -- tags will exist on a per-user level
    user_id BIGINT NOT NULL,
    -- tags have a name
    name    VARCHAR(100) NOT NULL,
    -- tags have content
    content VARCHAR(2000) DEFAULT NULL,
    PRIMARY KEY (user_id, name),
    FOREIGN KEY (user_id) REFERENCES profiles (user_id) ON DELETE CASCADE
);
