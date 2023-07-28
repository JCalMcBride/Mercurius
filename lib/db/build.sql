CREATE TABLE if not exists users
(
    discord_id        bigint PRIMARY KEY NOT NULL,
    platform          ENUM ('pc', 'xbox', 'switch', 'ps4') DEFAULT 'pc'
);