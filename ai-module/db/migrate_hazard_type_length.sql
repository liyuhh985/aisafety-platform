-- Widen the persisted hazard type so it can hold major/subcategory codes.
ALTER TABLE tb_hazard
    MODIFY COLUMN hazard_type VARCHAR(64) NOT NULL;
