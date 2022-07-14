-- SPDX-License-Identifier: AGPL-3.0-or-later
-- Copyright (C) 2022 sardonicism-04
CREATE
OR REPLACE FUNCTION get_column_description(
    _database_name TEXT,
    _table_name TEXT,
    _column_name TEXT
) RETURNS TEXT AS $$
DECLARE
    result TEXT;
BEGIN
    SELECT (
        SELECT
            pg_catalog.col_description(
                c.oid,
                cols.ordinal_position::int
            )
        FROM pg_catalog.pg_class c
        WHERE
            c.oid     = (SELECT cols.table_name::regclass::oid) AND
            c.relname = cols.table_name
        ) as column_comment
    INTO result
    FROM information_schema.columns cols
    WHERE
        cols.table_catalog = _database_name AND
        cols.table_name    = _table_name    AND
        cols.column_name   = _column_name;
    RETURN result;
END;
$$ LANGUAGE plpgsql;

CREATE
OR REPLACE FUNCTION is_valid_todo_category(
    _user_id BIGINT,
    _cat_name VARCHAR(100) DEFAULT NULL
) RETURNS BOOLEAN AS $$
BEGIN
    -- If no category name is provided, the todo is
    -- uncategorized, so it's fine
    IF _cat_name IS NULL THEN
        RETURN TRUE;
    ELSE
    -- Otherwise, return the boolean result of checking
    -- if the category name exists in the associated
    -- todo category column
        RETURN _cat_name = ANY ((
            SELECT todo_categories
            FROM profiles
            WHERE user_id = _user_id
        )::VARCHAR(100)[]);
    END IF;
END;
$$ LANGUAGE plpgsql
   CALLED ON NULL INPUT;