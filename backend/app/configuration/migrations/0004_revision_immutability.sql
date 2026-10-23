ALTER TABLE configuration_publications
    ADD COLUMN created_txid BIGINT NOT NULL DEFAULT txid_current();

CREATE FUNCTION configuration_reject_revision_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Published configuration revisions are immutable; publish a new revision'
        USING ERRCODE = '55000';
END;
$$;

CREATE FUNCTION configuration_guard_new_entry() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    publication_transaction BIGINT;
BEGIN
    EXECUTE format('SELECT created_txid FROM %I.configuration_publications WHERE id = $1', TG_TABLE_SCHEMA)
        INTO publication_transaction USING NEW.publication_id;
    IF publication_transaction IS DISTINCT FROM txid_current() THEN
        RAISE EXCEPTION 'Entries may only be added in the transaction creating their publication'
            USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;

DO $$
DECLARE
    table_name TEXT;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'configuration_publications', 'configuration_entries',
        'configuration_identity_policies', 'configuration_identity_bindings',
        'configuration_family_rule_scopes', 'configuration_family_rule_members'
    ] LOOP
        EXECUTE format('CREATE TRIGGER configuration_no_rewrite BEFORE UPDATE OR DELETE OR TRUNCATE ON %I.%I FOR EACH STATEMENT EXECUTE FUNCTION configuration_reject_revision_mutation()', current_schema(), table_name);
        IF table_name <> 'configuration_publications' THEN
            EXECUTE format('CREATE TRIGGER configuration_same_transaction BEFORE INSERT ON %I.%I FOR EACH ROW EXECUTE FUNCTION configuration_guard_new_entry()', current_schema(), table_name);
        END IF;
    END LOOP;
    IF to_regclass(format('%I.configurations', current_schema())) IS NOT NULL THEN
        EXECUTE format('CREATE TRIGGER configuration_no_rewrite BEFORE UPDATE OR DELETE OR TRUNCATE ON %I.configurations FOR EACH STATEMENT EXECUTE FUNCTION configuration_reject_revision_mutation()', current_schema());
    END IF;
END;
$$;
