import json
from collections import defaultdict
from typing import Dict, Union, Tuple, List, Any

import pymysql
from pymysql import Connection


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
    INSERT INTO fissure_list_defaults (user_id, show_normal, show_steel_path, show_void_storm, max_tier, 
                                       show_lith, show_meso, show_neo, show_axi, show_requiem, show_omnia)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE 
        show_normal = VALUES(show_normal),
        show_steel_path = VALUES(show_steel_path),
        show_void_storm = VALUES(show_void_storm),
        max_tier = VALUES(max_tier),
        show_lith = VALUES(show_lith),
        show_meso = VALUES(show_meso),
        show_neo = VALUES(show_neo),
        show_axi = VALUES(show_axi),
        show_requiem = VALUES(show_requiem),
        show_omnia = VALUES(show_omnia)
    """

    _GET_FISSURE_LIST_DEFAULTS_QUERY = """
    SELECT show_normal, show_steel_path, show_void_storm, max_tier, 
           show_lith, show_meso, show_neo, show_axi, show_requiem, show_omnia
    FROM fissure_list_defaults
    WHERE user_id = %s
    """

    _USER_EXISTS_QUERY = """
    SELECT EXISTS(SELECT 1 FROM users WHERE discord_id = %s)
    """

    _CREATE_USER_QUERY = """
    INSERT INTO users (discord_id) VALUES (%s)
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

    def __init__(self, user: str, password: str, host: str, database: str) -> None:
        self.connection: Connection = pymysql.connect(user=user,
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

    def get_fissure_list_message_id(self, server_id: int, channel_id: int, fissure_types: List[str]) -> Union[
        int, None]:
        column_mapping = {
            "Void Storms": "show_void_storms",
            "Normal": "show_normal",
            "Steel Path": "show_steel_path"
        }

        columns = [column_mapping[fissure_type] for fissure_type in fissure_types]
        conditions = [f"{column} = TRUE" for column in columns]

        # Add conditions for columns not in fissure_types
        remaining_columns = set(column_mapping.values()) - set(columns)
        conditions.extend(f"{column} = FALSE" for column in remaining_columns)

        conditions_str = " AND ".join(conditions)

        query = f"""
        SELECT message_id
        FROM fissure_list_channels
        WHERE server_id = %s AND channel_id = %s AND {conditions_str}
        """

        message_id = self._execute_query(query, server_id, channel_id, fetch='one')
        return message_id[0] if message_id else None
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
    def set_fissure_list_defaults(self, user_id: int, show_normal: bool, show_steel_path: bool, show_void_storm: bool,
                                  max_tier: int, show_lith: bool, show_meso: bool, show_neo: bool, show_axi: bool,
                                  show_requiem: bool, show_omnia: bool) -> None:
        self._execute_query(self._SET_FISSURE_LIST_DEFAULTS_QUERY, user_id, show_normal, show_steel_path,
                            show_void_storm, max_tier, show_lith, show_meso, show_neo, show_axi, show_requiem,
                            show_omnia, commit=True)

    def get_fissure_list_defaults(self, user_id: int) -> Dict[str, Any]:
        defaults = self._execute_query(self._GET_FISSURE_LIST_DEFAULTS_QUERY, user_id, fetch='one')
        if defaults:
            return {
                "show_normal": defaults[0],
                "show_steel_path": defaults[1],
                "show_void_storm": defaults[2],
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
            raise ValueError("You're already subscribed to this fissure. To manage subscriptions type /list_fissure_subscriptions")

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

    def get_all_fissure_subscriptions(self) -> List[Dict[str, Union[str, int]]]:
        query = """
        SELECT user_id, fissure_type, era, node, mission, planet, tileset, enemy, max_tier
        FROM fissure_subscriptions
        """
        subscriptions = self._execute_query(query, fetch='all')
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
