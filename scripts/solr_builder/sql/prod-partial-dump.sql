COPY (
    WITH modified_things AS (
        SELECT * FROM thing WHERE "last_modified" >= :'lo_date' AND "type" IN (58, 52, 17872418)
    )

    SELECT "type", "key", "latest_revision", "last_modified", "data" FROM modified_things
    LEFT JOIN data ON "thing_id" = "id" AND "revision" = "latest_revision"
) TO STDOUT;