CREATE DATABASE IF NOT EXISTS nst_studio
CHARACTER SET utf8mb4;

USE nst_studio;

CREATE TABLE IF NOT EXISTS generations (
    run_id CHAR(32) PRIMARY KEY,
    completed_at_utc DATETIME(6) NOT NULL,
    iterations INT UNSIGNED NOT NULL,
    style_weight DOUBLE NOT NULL,
    content_weight DOUBLE NOT NULL,
    total_variation_weight DOUBLE NOT NULL,
    max_dimension INT UNSIGNED NOT NULL,
    runtime_seconds DECIMAL(12, 2) NOT NULL
);