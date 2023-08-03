CREATE TABLE if not exists users
(
    discord_id        bigint PRIMARY KEY NOT NULL,
    platform          ENUM ('pc', 'xbox', 'switch', 'ps4') DEFAULT 'pc',
    graph_style varchar(255) DEFAULT 'ggplot'
);

CREATE TABLE if not exists servers
(
    server_id         bigint PRIMARY KEY NOT NULL
);

CREATE TABLE if not exists fissure_log_channels
(
    server_id         bigint NOT NULL,
    channel_id        bigint NOT NULL,
    fissure_type      ENUM ('Normal', 'Steel Path', 'Void Storms'),
    PRIMARY KEY (server_id, channel_id, fissure_type),
    FOREIGN KEY (server_id) REFERENCES servers (server_id)
);

CREATE TABLE if not exists fissure_list_channels
(
    message_id        bigint NOT NULL PRIMARY KEY,
    server_id         bigint NOT NULL,
    channel_id        bigint NOT NULL,
    fissure_type      ENUM ('Normal', 'Steel Path', 'Void Storms'),
    FOREIGN KEY (server_id) REFERENCES servers (server_id)
);