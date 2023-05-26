drop table if exists item_statistics;

CREATE TABLE temp_role_tasks (
    id INT NOT NULL AUTO_INCREMENT,
    role_id BIGINT NOT NULL,
    member_id BIGINT NOT NULL,
    removal_date DATETIME NOT NULL,
    removal_date I
)