CREATE TABLE reference_datasets (
    organization VARCHAR(80) NOT NULL,
    dataset_id VARCHAR(120) NOT NULL,
    digest VARCHAR(64) NOT NULL,
    payload JSON NOT NULL,
    PRIMARY KEY (organization, dataset_id),
    UNIQUE (organization, dataset_id)
);
CREATE TRIGGER reference_dataset_no_rewrite
    BEFORE UPDATE OR DELETE OR TRUNCATE ON reference_datasets
    FOR EACH STATEMENT EXECUTE FUNCTION configuration_reject_revision_mutation();
