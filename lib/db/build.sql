CREATE TABLE IF NOT EXISTS users (
    discord_id BIGINT PRIMARY KEY NOT NULL,
    platform ENUM('pc', 'xbox', 'switch', 'ps4') DEFAULT 'pc',
    graph_style VARCHAR(255) DEFAULT 'ggplot',
    fissure_notification_type ENUM('DM', 'Thread') DEFAULT 'DM',
    thread_notification_server_id BIGINT,
    fissure_notifications_enabled BOOLEAN DEFAULT true,
    mute_market_notifications BOOLEAN DEFAULT true
);


CREATE TABLE if not exists servers
(
    server_id bigint PRIMARY KEY NOT NULL
);

CREATE TABLE if not exists fissure_log_channels
(
    server_id    bigint NOT NULL,
    channel_id   bigint NOT NULL,
    fissure_type ENUM ('Normal', 'Steel Path', 'Void Storms'),
    PRIMARY KEY (server_id, channel_id, fissure_type),
    FOREIGN KEY (server_id) REFERENCES servers (server_id)
);

CREATE TABLE if not exists fissure_list_channels
(
    id           SERIAL PRIMARY KEY,
    server_id    bigint NOT NULL,
    channel_id   bigint NOT NULL,
    message_id   bigint,
    max_tier     int,
    show_lith    boolean DEFAULT true,
    show_meso    boolean DEFAULT true,
    show_neo     boolean DEFAULT true,
    show_axi     boolean DEFAULT true,
    show_requiem boolean DEFAULT true,
    show_omnia   boolean DEFAULT true,
    display_type ENUM ('Discord', 'Time Left') DEFAULT 'Discord',
    show_normal  boolean DEFAULT true,
    show_steel_path boolean DEFAULT false,
    show_void_storms boolean DEFAULT false,
    CONSTRAINT at_least_one_fissure_type CHECK (show_normal OR show_steel_path OR show_void_storms),
    FOREIGN KEY (server_id) REFERENCES servers (server_id)
);


CREATE TABLE if not exists fissure_list_defaults
(
    user_id      bigint PRIMARY KEY,
    show_normal  boolean DEFAULT true,
    show_steel_path boolean DEFAULT false,
    show_void_storms boolean DEFAULT false,
    max_tier     int DEFAULT 5,
    show_lith    boolean DEFAULT true,
    show_meso    boolean DEFAULT true,
    show_neo     boolean DEFAULT true,
    show_axi     boolean DEFAULT true,
    show_requiem boolean DEFAULT true,
    show_omnia   boolean DEFAULT true,
    FOREIGN KEY (user_id) REFERENCES users (discord_id)
);

CREATE TABLE if not exists fissure_subscriptions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    fissure_type ENUM('Normal', 'Steel Path', 'Void Storms') NULL,
    era ENUM('Lith', 'Meso', 'Neo', 'Axi', 'Requiem', 'Omnia') NULL,
    node VARCHAR(50) NULL,
    mission VARCHAR(50) NULL,
    planet VARCHAR(50) NULL,
    tileset VARCHAR(50) NULL,
    enemy VARCHAR(50) NULL,
    max_tier INT NULL,
    CONSTRAINT unique_subscription UNIQUE (user_id, fissure_type, era, node, mission, planet, tileset, enemy, max_tier)
);

CREATE TABLE IF NOT EXISTS fissure_views (
    id INT AUTO_INCREMENT PRIMARY KEY,
    message_text VARCHAR(255) NOT NULL,
    button_configs JSON NOT NULL,
    channel_id BIGINT NOT NULL,
    message_id BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS fissure_notification_status (
    user_id BIGINT PRIMARY KEY,
    online BOOLEAN DEFAULT true,
    idle BOOLEAN DEFAULT true,
    dnd BOOLEAN DEFAULT true,
    offline BOOLEAN DEFAULT true,
    FOREIGN KEY (user_id) REFERENCES users (discord_id)
);

CREATE TABLE IF NOT EXISTS item_settings (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    item_id VARCHAR(255) NOT NULL,
    plat_notification_threshold INT,
    daily_messages BOOLEAN,
    favorite BOOLEAN DEFAULT true,
    FOREIGN KEY (user_id) REFERENCES users (discord_id),
    UNIQUE (user_id, item_id)
);
