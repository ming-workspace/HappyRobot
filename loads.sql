CREATE TABLE loads (
    id SERIAL PRIMARY KEY,
    reference_number VARCHAR(20) NOT NULL,
    origin VARCHAR(50) NOT NULL,
    destination VARCHAR(50) NOT NULL,
    equipment_type VARCHAR(50) NOT NULL,
    rate NUMERIC(10,2) NOT NULL,
    commodity VARCHAR(50) NOT NULL
);

CREATE INDEX idx_reference ON loads (reference_number);
CREATE INDEX idx_origin_dest ON loads (origin, destination);
CREATE INDEX idx_equipment ON loads USING gin (equipment_type gin_trgm_ops);