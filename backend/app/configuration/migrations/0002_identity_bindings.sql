CREATE TABLE configuration_identity_policies (
    publication_id VARCHAR(36) PRIMARY KEY REFERENCES configuration_publications(id),
    settings JSON NOT NULL
);
CREATE TABLE configuration_identity_bindings (
    publication_id VARCHAR(36) NOT NULL REFERENCES configuration_identity_policies(publication_id),
    profile VARCHAR(80) NOT NULL,
    position INTEGER NOT NULL CHECK (position >= 0),
    definition JSON NOT NULL,
    PRIMARY KEY (publication_id, profile),
    UNIQUE (publication_id, position)
);
