from typing import Dict, Union, Tuple, List

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
