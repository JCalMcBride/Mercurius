import json
from collections import defaultdict
from typing import Dict, Union, Tuple, List, Any, Optional

import pymysql
from pymysql import Connection, OperationalError


class MercuriusDatabase:
    _SET_PLATFORM_QUERY = """INSERT INTO users (discord_id, platform) 
                             VALUES (%s, %s) 
                             ON DUPLICATE KEY UPDATE platform=VALUES(platform)
                          """

    _GET_PLATFORM_QUERY = """SELECT platform FROM users WHERE discord_id = %s"""

    _SET_GRAPH_STYLE_QUERY = """INSERT INTO users (discord_id, graph_style) 
                             VALUES (%s, %s)
                             ON DUPLICATE KEY UPDATE graph_style=VALUES(graph_style)
                          """

    _GET_GRAPH_STYLE_QUERY = """SELECT graph_style FROM users WHERE discord_id = %s"""

    _SET_FISSURE_LOG_CHANNEL_QUERY = """
    INSERT INTO fissure_log_channels (server_id, channel_id, fissure_type) 
    VALUES (%s, %s, %s)"""

    _UNSET_FISSURE_LOG_CHANNEL_QUERY = """
    DELETE FROM fissure_log_channels WHERE 
    server_id = %s AND channel_id = %s AND fissure_type = %s
    """

    _GET_FISSURE_LOG_CHANNEL_QUERY = """SELECT fissure_type, server_id, channel_id FROM fissure_log_channels"""

    _SET_FISSURE_LIST_CHANNEL_QUERY = """
    INSERT INTO fissure_list_channels (server_id, channel_id, message_id, max_tier, show_lith, show_meso, show_neo, 
                                        show_axi, show_requiem, show_omnia, display_type, show_normal, show_steel_path, 
                                        show_void_storms) 
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE
        message_id = VALUES(message_id),
        max_tier = VALUES(max_tier),
        show_lith = VALUES(show_lith),
        show_meso = VALUES(show_meso),
        show_neo = VALUES(show_neo),
        show_axi = VALUES(show_axi),
        show_requiem = VALUES(show_requiem),
        show_omnia = VALUES(show_omnia),
        display_type = VALUES(display_type),
        show_normal = VALUES(show_normal),
        show_steel_path = VALUES(show_steel_path),
        show_void_storms = VALUES(show_void_storms)
    """

    _UNSET_FISSURE_LIST_CHANNEL_QUERY = """
    DELETE FROM fissure_list_channels 
    WHERE server_id = %s AND channel_id = %s AND message_id = %s
    """

    _GET_FISSURE_LIST_MESSAGE_ID_QUERY = """
    SELECT message_id 
    FROM fissure_list_channels 
    WHERE server_id = %s AND channel_id = %s
    """

    _GET_FISSURE_LIST_CHANNEL_QUERY = """
    SELECT id, server_id, channel_id, message_id, max_tier, show_lith, show_meso, show_neo, show_axi, show_requiem, 
           show_omnia, display_type, show_normal, show_steel_path, show_void_storms 
    FROM fissure_list_channels
    """

    _SET_FISSURE_LIST_MESSAGE_ID_QUERY = """
    UPDATE fissure_list_channels 
    SET message_id = %s
    WHERE id = %s
    """

    _INSERT_SERVER_QUERY = """INSERT IGNORE INTO servers (server_id) VALUES (%s)"""

    _SET_FISSURE_LIST_DEFAULTS_QUERY = """
    INSERT INTO fissure_list_defaults (user_id, show_normal, show_steel_path, show_void_storms, max_tier, 
                                       show_lith, show_meso, show_neo, show_axi, show_requiem, show_omnia)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE 
        show_normal = VALUES(show_normal),
        show_steel_path = VALUES(show_steel_path),
        show_void_storms = VALUES(show_void_storms),
        max_tier = VALUES(max_tier),
        show_lith = VALUES(show_lith),
        show_meso = VALUES(show_meso),
        show_neo = VALUES(show_neo),
        show_axi = VALUES(show_axi),
        show_requiem = VALUES(show_requiem),
        show_omnia = VALUES(show_omnia)
    """

    _GET_FISSURE_LIST_DEFAULTS_QUERY = """
    SELECT show_normal, show_steel_path, show_void_storms, max_tier, 
           show_lith, show_meso, show_neo, show_axi, show_requiem, show_omnia
    FROM fissure_list_defaults
    WHERE user_id = %s
    """

    _USER_EXISTS_QUERY = """
    SELECT EXISTS(SELECT 1 FROM users WHERE discord_id = %s)
    """

    _CREATE_USER_QUERY = """
    INSERT IGNORE INTO users (discord_id) VALUES (%s)
    """

    _ADD_FISSURE_SUBSCRIPTION_QUERY = """
    INSERT INTO fissure_subscriptions (user_id, fissure_type, era, node, mission, planet, tileset, enemy, max_tier)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """

    _REMOVE_FISSURE_SUBSCRIPTION_QUERY = """DELETE FROM fissure_subscriptions WHERE user_id = %s"""

    _GET_FISSURE_SUBSCRIPTIONS_QUERY = """
    SELECT fissure_type, era, node, mission, planet, tileset, enemy, max_tier
    FROM fissure_subscriptions
    WHERE user_id = %s
    """

    _SAVE_FISSURE_VIEW_QUERY = """
    INSERT INTO fissure_views (message_text, button_configs, channel_id, message_id)
    VALUES (%s, %s, %s, %s)
    """

    _GET_ALL_FISSURE_VIEWS_QUERY = """
    SELECT message_text, button_configs, channel_id, message_id
    FROM fissure_views
    """

    _GET_FISSURE_VIEW_BY_MESSAGE_ID_QUERY = """
    SELECT message_text, button_configs, channel_id, message_id
    FROM fissure_views
    WHERE message_id = %s
    """

    _UPDATE_FISSURE_VIEW_QUERY = """
    UPDATE fissure_views
    SET message_text = %s, button_configs = %s
    WHERE message_id = %s
    """

    _GET_FISSURE_NOTIFICATION_TYPE_QUERY = """
    SELECT fissure_notification_type 
    FROM users 
    WHERE discord_id = %s
    """

    _SET_FISSURE_NOTIFICATION_TYPE_QUERY = """
    UPDATE users
    SET fissure_notification_type = %s
    WHERE discord_id = %s
    """

    _GET_FISSURE_NOTIFICATIONS_ENABLED_QUERY = """
        SELECT fissure_notifications_enabled
        FROM users
        WHERE discord_id = %s
        """

    _SET_FISSURE_NOTIFICATIONS_ENABLED_QUERY = """
        UPDATE users
        SET fissure_notifications_enabled = %s
        WHERE discord_id = %s
        """


    _SET_ITEM_SETTINGS_QUERY = """
    INSERT INTO item_settings (user_id, item_id, plat_notification_threshold, daily_messages, favorite)
    VALUES (%s, %s, %s, %s, %s)
    """

    _GET_ITEM_SETTINGS_BY_USER_QUERY = """
    SELECT item_id, plat_notification_threshold, daily_messages, favorite
    FROM item_settings
    WHERE user_id = %s
    """

    _GET_ITEM_SETTINGS_BY_USER_AND_ITEM_QUERY = """
    SELECT plat_notification_threshold, daily_messages, favorite
    FROM item_settings
    WHERE user_id = %s AND item_id = %s
    """

    _REMOVE_ITEM_SETTINGS_BY_USER_AND_ITEM_QUERY = """
    DELETE FROM item_settings
    WHERE user_id = %s AND item_id = %s
    """

    _REMOVE_ALL_ITEM_SETTINGS_BY_USER_QUERY = """
    DELETE FROM item_settings
    WHERE user_id = %s
    """

    _SET_MARKET_NOTIFICATIONS_MUTE_STATUS_QUERY = """
    UPDATE users
    SET mute_market_notifications = %s
    WHERE discord_id = %s
    """

    _GET_MARKET_NOTIFICATIONS_MUTE_STATUS_QUERY = """
    SELECT mute_market_notifications
    FROM users
    WHERE discord_id = %s
    """

    _STORE_TAG_QUERY = """
    INSERT INTO tags (tag_name, content, autodelete, dm)
    VALUES (%s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE
        content = VALUES(content),
        autodelete = VALUES(autodelete),
        dm = VALUES(dm)
    """

    _TAG_SERVER_LINK_SUBQUERY = """
    SELECT tag_id
    FROM tag_server_link
    WHERE server_id IN (
        SELECT server_id
        FROM linked_servers
        WHERE linked_server_id = %s
        UNION
        SELECT linked_server_id
        FROM linked_servers
        WHERE server_id = %s
        UNION
        SELECT %s
    )
    """

    _LINK_TAG_TO_SERVER_QUERY = """
    INSERT INTO tag_server_link (tag_id, server_id)
    VALUES (%s, %s)
    """

    _LINK_SERVERS_QUERY = """
    INSERT INTO linked_servers (server_id, linked_server_id)
    SELECT %s, %s
    WHERE NOT EXISTS (
        SELECT 1 FROM linked_servers
        WHERE (server_id = %s AND linked_server_id = %s)
           OR (server_id = %s AND linked_server_id = %s)
    )
    """




    def __init__(self, user: str, password: str, host: str, database: str) -> None:
        try:
            self.connection: Connection = pymysql.connect(user=user,
                                                          password=password,
                                                          host=host,
                                                          database=database)
        except OperationalError:
            with pymysql.connect(user=user,
                                 password=password,
                                 host=host) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(f"create database if not exists {database};")

            self.connection = pymysql.connect(user=user,
                                              password=password,
                                              host=host,
                                              database=database)

    def build_database(self) -> None:
        with open("lib/db/build.sql", "r") as f:
            sql = f.read()

        for sql in sql.split(";"):
            if sql.strip() != "":
                self._execute_query(sql)

    def _execute_query(self, query: str, *params, fetch: str = 'all',
                       commit: bool = False, many: bool = False) -> Union[Tuple, List[Tuple], None]:
        self.connection.ping(reconnect=True)

        with self.connection.cursor() as cur:
            if many:
                cur.executemany(query, params[0])
            else:
                cur.execute(query, params)

            if commit:
                self.connection.commit()

            if fetch == 'one':
                return cur.fetchone()
            elif fetch == 'all':
                return cur.fetchall()

    def insert_servers(self, servers: List[int]) -> None:
        self._execute_query(self._INSERT_SERVER_QUERY, servers, many=True, commit=True)

    def set_platform(self, user: str, platform: str) -> None:
        self._execute_query(self._SET_PLATFORM_QUERY, user, platform, commit=True)

    def get_platform(self, user: str) -> str:
        platform = self._execute_query(self._GET_PLATFORM_QUERY, user, fetch='one')
        return platform[0] if platform else 'pc'

    def set_graph_style(self, user: str, style: str) -> None:
        self._execute_query(self._SET_GRAPH_STYLE_QUERY, user, style, commit=True)

    def get_graph_style(self, user: str) -> str:
        style = self._execute_query(self._GET_GRAPH_STYLE_QUERY, user, fetch='one')
        return style[0] if style else 'ggplot'

    def set_fissure_log_channel(self, server_id: int, channel_id: int, fissure_type: str) -> None:
        self._execute_query(self._SET_FISSURE_LOG_CHANNEL_QUERY, server_id, channel_id, fissure_type, commit=True)

    def unset_fissure_log_channel(self, server_id: int, channel_id: int, fissure_type: str) -> None:
        self._execute_query(self._UNSET_FISSURE_LOG_CHANNEL_QUERY, server_id, channel_id, fissure_type, commit=True)

    def get_fissure_log_channels(self) -> defaultdict:
        results = self._execute_query(self._GET_FISSURE_LOG_CHANNEL_QUERY, fetch='all')

        fissure_log_dict = defaultdict(lambda: defaultdict(list))
        for fissure_type, server_id, channel_id in results:
            fissure_log_dict[fissure_type][server_id].append(channel_id)

        return fissure_log_dict

    def set_fissure_list_channel(self, server_id: int, channel_id: int, message_id: int, max_tier: int,
                                 show_lith: bool, show_meso: bool, show_neo: bool, show_axi: bool,
                                 show_requiem: bool, show_omnia: bool, display_type: str,
                                 show_normal: bool, show_steel_path: bool, show_void_storms: bool) -> None:
        self._execute_query(self._SET_FISSURE_LIST_CHANNEL_QUERY, server_id, channel_id, message_id, max_tier,
                            show_lith, show_meso, show_neo, show_axi, show_requiem, show_omnia, display_type,
                            show_normal, show_steel_path, show_void_storms, commit=True)

    def unset_fissure_list_channel(self, server_id: int, channel_id: int, message_id: int) -> None:
        self._execute_query(self._UNSET_FISSURE_LIST_CHANNEL_QUERY, server_id, channel_id, message_id, commit=True)

    def set_fissure_list_message_id(self, fissure_list_id: int, message_id: int) -> None:
        self._execute_query(self._SET_FISSURE_LIST_MESSAGE_ID_QUERY, message_id, fissure_list_id, commit=True)

    def get_fissure_list_channels(self) -> defaultdict:
        results = self._execute_query(self._GET_FISSURE_LIST_CHANNEL_QUERY, fetch='all')

        fissure_list_dict = defaultdict(list)
        for row in results:
            channel_config = {
                "id": row[0],
                "server_id": row[1],
                "channel_id": row[2],
                "message_id": row[3],
                "max_tier": row[4],
                "show_lith": row[5],
                "show_meso": row[6],
                "show_neo": row[7],
                "show_axi": row[8],
                "show_requiem": row[9],
                "show_omnia": row[10],
                "display_type": row[11],
                "show_normal": row[12],
                "show_steel_path": row[13],
                "show_void_storms": row[14]
            }
            fissure_list_dict[row[1]].append(channel_config)

        return fissure_list_dict

    def set_fissure_list_defaults(self, user_id: int, **kwargs) -> None:
        query = """
        INSERT INTO fissure_list_defaults (user_id, show_normal, show_steel_path, show_void_storms, max_tier, 
                                           show_lith, show_meso, show_neo, show_axi, show_requiem, show_omnia)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE 
            show_normal = COALESCE(VALUES(show_normal), show_normal),
            show_steel_path = COALESCE(VALUES(show_steel_path), show_steel_path),
            show_void_storms = COALESCE(VALUES(show_void_storms), show_void_storms),
            max_tier = COALESCE(VALUES(max_tier), max_tier),
            show_lith = COALESCE(VALUES(show_lith), show_lith),
            show_meso = COALESCE(VALUES(show_meso), show_meso),
            show_neo = COALESCE(VALUES(show_neo), show_neo),
            show_axi = COALESCE(VALUES(show_axi), show_axi),
            show_requiem = COALESCE(VALUES(show_requiem), show_requiem),
            show_omnia = COALESCE(VALUES(show_omnia), show_omnia)
        """
        params = [user_id] + [kwargs.get(field, None) for field in [
            'show_normal', 'show_steel_path', 'show_void_storms', 'max_tier',
            'show_lith', 'show_meso', 'show_neo', 'show_axi', 'show_requiem', 'show_omnia'
        ]]
        self._execute_query(query, *params, commit=True)

    def update_fissure_list_defaults(self, user_id: int, **kwargs) -> None:
        update_fields = [f"{field} = %s" for field in kwargs]
        if not update_fields:
            return

        query = f"""
        UPDATE fissure_list_defaults
        SET {', '.join(update_fields)}
        WHERE user_id = %s
        """
        params = list(kwargs.values()) + [user_id]
        self._execute_query(query, *params, commit=True)

    def get_fissure_list_defaults(self, user_id: int) -> Dict[str, Any]:
        defaults = self._execute_query(self._GET_FISSURE_LIST_DEFAULTS_QUERY, user_id, fetch='one')
        if defaults:
            return {
                "show_normal": defaults[0],
                "show_steel_path": defaults[1],
                "show_void_storms": defaults[2],
                "max_tier": defaults[3],
                "show_lith": defaults[4],
                "show_meso": defaults[5],
                "show_neo": defaults[6],
                "show_axi": defaults[7],
                "show_requiem": defaults[8],
                "show_omnia": defaults[9]
            }
        return None

    def add_fissure_subscription(self, user_id: int, fissure_type: str = None, era: str = None, node: str = None,
                                 mission: str = None, planet: str = None, tileset: str = None, enemy: str = None,
                                 tier: int = None) -> None:
        if not any([fissure_type, era, node, mission, planet, tileset, enemy, tier]):
            raise ValueError("Cannot add a blank subscription")

        # Get existing subscriptions for the user
        existing_subscriptions = self.get_fissure_subscriptions(user_id)

        # Check if the new subscription already exists
        new_subscription = {
            "fissure_type": fissure_type,
            "era": era,
            "node": node,
            "mission": mission,
            "planet": planet,
            "tileset": tileset,
            "enemy": enemy,
            "max_tier": tier
        }

        if new_subscription in existing_subscriptions:
            raise ValueError("You're already subscribed to this fissure. To manage subscriptions type /listfissuresubscriptions")

        self._execute_query(self._ADD_FISSURE_SUBSCRIPTION_QUERY, user_id, fissure_type, era, node, mission, planet,
                            tileset, enemy, tier, commit=True)

    def remove_fissure_subscription(self, user_id: int, fissure_type: str = None, era: str = None, node: str = None,
                                    mission: str = None, planet: str = None, tileset: str = None, enemy: str = None,
                                    max_tier: int = None) -> None:
        conditions = [
            ("fissure_type", fissure_type),
            ("era", era),
            ("node", node),
            ("mission", mission),
            ("planet", planet),
            ("tileset", tileset),
            ("enemy", enemy),
            ("max_tier", max_tier)
        ]

        query = str(self._REMOVE_FISSURE_SUBSCRIPTION_QUERY)
        params = [user_id]

        for column, value in conditions:
            if value is not None:
                query += f" AND {column} = %s"
                params.append(value)

        self._execute_query(query, *params, commit=True)

    def remove_all_fissure_subscriptions(self, user_id: int) -> None:
        self._execute_query(self._REMOVE_FISSURE_SUBSCRIPTION_QUERY, user_id, commit=True)

    def get_fissure_subscriptions(self, user_id: int) -> List[Dict[str, Union[str, int]]]:
        subscriptions = self._execute_query(self._GET_FISSURE_SUBSCRIPTIONS_QUERY, user_id, fetch='all')
        return [
            {
                "fissure_type": row[0],
                "era": row[1],
                "node": row[2],
                "mission": row[3],
                "planet": row[4],
                "tileset": row[5],
                "enemy": row[6],
                "max_tier": row[7]
            }
            for row in subscriptions
        ]

    def get_all_fissure_subscriptions(self, notification_type: str = 'DM') -> List[Dict[str, Union[str, int]]]:
        query = """
        SELECT fs.user_id, fs.fissure_type, fs.era, fs.node, fs.mission, fs.planet, fs.tileset, fs.enemy, fs.max_tier
        FROM fissure_subscriptions fs
        JOIN users u ON fs.user_id = u.discord_id
        WHERE u.fissure_notification_type = %s
        AND u.fissure_notifications_enabled = true
        """
        subscriptions = self._execute_query(query, notification_type, fetch='all')
        return [
            {
                "user_id": row[0],
                "fissure_type": row[1],
                "era": row[2],
                "node": row[3],
                "mission": row[4],
                "planet": row[5],
                "tileset": row[6],
                "enemy": row[7],
                "max_tier": row[8]
            }
            for row in subscriptions
        ]

    def user_exists(self, user_id: int) -> bool:
        exists = self._execute_query(self._USER_EXISTS_QUERY, user_id, fetch='one')
        return exists[0] == 1

    def create_user(self, user_id: int) -> None:
        self._execute_query(self._CREATE_USER_QUERY, user_id, commit=True)

    def save_fissure_view(self, message_text: str, button_configs: List[dict], channel_id: int, message_id: int) -> None:
        self._execute_query(self._SAVE_FISSURE_VIEW_QUERY, message_text, json.dumps(button_configs), channel_id, message_id, commit=True)

    def get_all_fissure_views(self) -> List[dict]:
        results = self._execute_query(self._GET_ALL_FISSURE_VIEWS_QUERY, fetch='all')
        return [
            {
                "message_text": row[0],
                "button_configs": json.loads(row[1]),
                "channel_id": row[2],
                "message_id": row[3]
            }
            for row in results
        ]

    def get_fissure_view_by_message_id(self, message_id: int) -> Union[dict, None]:
        result = self._execute_query(self._GET_FISSURE_VIEW_BY_MESSAGE_ID_QUERY, message_id, fetch='one')
        if result:
            return {
                "message_text": result[0],
                "button_configs": json.loads(result[1]),
                "channel_id": result[2],
                "message_id": result[3]
            }
        return None

    def update_fissure_view(self, message_text: str, button_configs: List[dict], message_id: int) -> None:
        self._execute_query(self._UPDATE_FISSURE_VIEW_QUERY, message_text, json.dumps(button_configs), message_id,
                            commit=True)

    def delete_all_fissure_views(self) -> None:
        self._execute_query("DELETE FROM fissure_views", commit=True)

    def get_fissure_notification_type(self, user_id: int) -> str:
        result = self._execute_query(self._GET_FISSURE_NOTIFICATION_TYPE_QUERY, user_id, fetch='one')
        return result[0] if result else 'DM'

    def set_fissure_notification_type(self, user_id: int, notification_type: str) -> None:
        self._execute_query(self._SET_FISSURE_NOTIFICATION_TYPE_QUERY, notification_type, user_id, commit=True)

    def set_thread_notification_server(self, user_id: int, server_id: int) -> None:
        query = """
        UPDATE users
        SET thread_notification_server_id = %s
        WHERE discord_id = %s
        """
        self._execute_query(query, server_id, user_id, commit=True)

    def get_thread_notification_server(self, user_id: int) -> int:
        query = """
        SELECT thread_notification_server_id
        FROM users
        WHERE discord_id = %s
        """
        result = self._execute_query(query, user_id, fetch='one')
        return result[0] if result else None

    def get_fissure_notifications_enabled(self, user_id: int) -> bool:
        result = self._execute_query(self._GET_FISSURE_NOTIFICATIONS_ENABLED_QUERY, user_id, fetch='one')
        return result[0] if result else True

    def set_fissure_notifications_enabled(self, user_id: int, enabled: bool) -> None:
        self._execute_query(self._SET_FISSURE_NOTIFICATIONS_ENABLED_QUERY, enabled, user_id, commit=True)

    def get_fissure_notification_status(self, user_id: int) -> dict:
        query = """
        SELECT online, idle, dnd, offline
        FROM fissure_notification_status
        WHERE user_id = %s
        """
        result = self._execute_query(query, user_id, fetch='one')
        if result:
            return {
                'online': result[0],
                'idle': result[1],
                'dnd': result[2],
                'offline': result[3]
            }
        else:
            return {
                'online': True,
                'idle': True,
                'dnd': True,
                'offline': True
            }

    def set_fissure_notification_status(self, user_id: int, status: str, enabled: bool) -> None:
        query = f"""
        INSERT INTO fissure_notification_status (user_id, {status})
        VALUES (%s, %s)
        ON DUPLICATE KEY UPDATE {status} = VALUES({status})
        """
        self._execute_query(query, user_id, enabled, commit=True)

    def set_item_settings(self, user_id: int, item_id: str, plat_notification_threshold: int = None,
                          daily_messages: bool = False, favorite: bool = True) -> None:
        self._execute_query(self._SET_ITEM_SETTINGS_QUERY, user_id, item_id, plat_notification_threshold, daily_messages,
                            favorite, commit=True)

    def get_item_settings_by_user(self, user_id: int) -> List[Dict[str, Union[str, int, bool]]]:
        results = self._execute_query(self._GET_ITEM_SETTINGS_BY_USER_QUERY, user_id, fetch='all')
        return [
            {
                "item_id": row[0],
                "plat_notification_threshold": row[1],
                "daily_messages": row[2],
                "favorite": row[3]
            }
            for row in results
        ]

    def get_item_settings_by_user_and_item(self, user_id: int, item_id: str) -> Union[Dict[str, Union[int, bool]], None]:
        result = self._execute_query(self._GET_ITEM_SETTINGS_BY_USER_AND_ITEM_QUERY, user_id, item_id, fetch='one')
        if result:
            return {
                "plat_notification_threshold": result[0],
                "daily_messages": result[1],
                "favorite": result[2]
            }
        return None

    def remove_item_settings_by_user_and_item(self, user_id: int, item_id: str) -> None:
        self._execute_query(self._REMOVE_ITEM_SETTINGS_BY_USER_AND_ITEM_QUERY, user_id, item_id, commit=True)

    def remove_all_item_settings_by_user(self, user_id: int) -> None:
        self._execute_query(self._REMOVE_ALL_ITEM_SETTINGS_BY_USER_QUERY, user_id, commit=True)

    def set_market_notifications_mute_status(self, user_id: int, mute_status: bool) -> None:
        self._execute_query(self._SET_MARKET_NOTIFICATIONS_MUTE_STATUS_QUERY, mute_status, user_id, commit=True)

    def get_market_notifications_mute_status(self, user_id: int) -> bool:
        result = self._execute_query(self._GET_MARKET_NOTIFICATIONS_MUTE_STATUS_QUERY, user_id, fetch='one')
        return result[0] if result else True

    def store_tag(self, tag_name: str, content: str, autodelete: bool, dm: bool, server_id: int) -> None:
        self._execute_query(self._STORE_TAG_QUERY, tag_name, content, autodelete, dm, commit=True)
        tag_id = self._execute_query(f"SELECT id FROM tags WHERE tag_name = %s", (tag_name,), fetch='one')[0]
        self.link_tag_to_server(tag_id, server_id)

    def retrieve_tag(self, tag_name: str, server_id: int) -> Optional[Dict[str, Any]]:
        tag_id = self.get_tag_id(tag_name, server_id)
        if tag_id:
            query = f"SELECT content, autodelete, dm FROM tags WHERE id = %s AND id IN ({self._TAG_SERVER_LINK_SUBQUERY})"
            result = self._execute_query(query, tag_id, server_id, server_id, server_id, fetch='one')
            if result:
                return {
                    "content": result[0],
                    "autodelete": result[1],
                    "dm": result[2]
                }
        return None

    def delete_tag(self, tag_id: int, server_id: int) -> None:
        tag_server_link_query = "DELETE FROM tag_server_link WHERE tag_id = %s AND server_id = %s"
        self._execute_query(tag_server_link_query, tag_id, server_id, commit=True)

        try:
            query = f"DELETE FROM tags WHERE id = %s AND id IN ({self._TAG_SERVER_LINK_SUBQUERY})"
            self._execute_query(query, tag_id, server_id, server_id, server_id, commit=True)
        except pymysql.err.IntegrityError:
            pass

    def update_autodelete(self, tag_id: int, autodelete: bool, server_id: int) -> None:
        query = f"UPDATE tags SET autodelete = %s WHERE id = %s AND id IN ({self._TAG_SERVER_LINK_SUBQUERY})"
        self._execute_query(query, autodelete, tag_id, server_id, server_id, server_id, commit=True)

    def update_dm(self, tag_id: int, dm: bool, server_id: int) -> None:
        query = f"UPDATE tags SET dm = %s WHERE id = %s AND id IN ({self._TAG_SERVER_LINK_SUBQUERY})"
        self._execute_query(query, dm, tag_id, server_id, server_id, server_id, commit=True)

    def link_tag_to_server(self, tag_id: int, server_id: int) -> None:
        self._execute_query(self._LINK_TAG_TO_SERVER_QUERY, tag_id, server_id, commit=True)

    def link_servers(self, server_id: int, linked_server_id: int) -> None:
        self._execute_query(self._LINK_SERVERS_QUERY, server_id, linked_server_id,
                            server_id, linked_server_id, linked_server_id, server_id, commit=True)

    def bulk_insert_tags(self, tags: Dict[str, Dict[str, Any]], server_ids: List[int]) -> None:
        tag_data = [(tag_name, tag_info["content"], tag_info["autodelete"], tag_info["dm"]) for tag_name, tag_info in tags.items()]
        self._execute_query(self._STORE_TAG_QUERY, tag_data, many=True, commit=True)

        tag_ids = [self._execute_query(f"SELECT id FROM tags WHERE tag_name = %s", (tag_name,), fetch='one')[0] for tag_name in tags.keys()]

        for server_id in server_ids:
            link_data = [(tag_id, server_id) for tag_id in tag_ids]
            self._execute_query(self._LINK_TAG_TO_SERVER_QUERY, link_data, many=True, commit=True)

    def get_tag_id(self, tag_name: str, server_id: int) -> Optional[int]:
        query = f"SELECT id FROM tags WHERE tag_name = %s AND id IN ({self._TAG_SERVER_LINK_SUBQUERY})"
        result = self._execute_query(query, tag_name, server_id, server_id, server_id, fetch='one')
        return result[0] if result else None

    def get_server_tags(self, server_id: int) -> List[Dict[str, Any]]:
        query = f"""
        SELECT t.id, t.tag_name, t.content, t.autodelete, t.dm
        FROM tags t
        JOIN tag_server_link tsl ON t.id = tsl.tag_id
        WHERE tsl.server_id IN (
            SELECT server_id
            FROM linked_servers
            WHERE linked_server_id = %s
            UNION
            SELECT linked_server_id
            FROM linked_servers
            WHERE server_id = %s
            UNION
            SELECT %s
        )
        """
        results = self._execute_query(query, server_id, server_id, server_id, fetch='all')
        return [
            {
                "id": row[0],
                "tag_name": row[1],
                "content": row[2],
                "autodelete": row[3],
                "dm": row[4]
            }
            for row in results
        ]
