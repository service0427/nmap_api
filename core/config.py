import os
from dotenv import load_dotenv

# Path to .env file
ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')

class Config:
    @classmethod
    def load(cls):
        """Force reload environment variables from .env"""
        load_dotenv(ENV_PATH, override=True)

    @classmethod
    def get_db_config(cls):
        import pymysql
        cls.load() # Ensure variables are loaded
        
        db_user = os.getenv('DB_USER', 'nmap')
        db_pass = os.getenv('DB_PASSWORD', 'Tech1324')
        db_name = os.getenv('DB_NAME', 'nmap_api')
        db_host = os.getenv('DB_HOST')
        db_port = int(os.getenv('DB_PORT', 3306))
        db_socket = os.getenv('DB_SOCKET')
        db_ssl_ca = os.getenv('DB_SSL_CA')
        
        conf = {
            'user': db_user,
            'password': db_pass,
            'database': db_name,
            'charset': 'utf8mb4',
            'cursorclass': pymysql.cursors.DictCursor,
            'init_command': "SET time_zone='+09:00'"
        }
        
        if db_host:
            conf['host'] = db_host
            conf['port'] = db_port
        elif db_socket:
            conf['unix_socket'] = db_socket
        else:
            # Fallback for local development
            conf['unix_socket'] = '/var/run/mysqld/mysqld.sock'
            
        if db_ssl_ca:
            conf['ssl'] = {'ca': db_ssl_ca}
            
        return conf

    @classmethod
    def get_source_fsd_config(cls):
        import pymysql
        cls.load()
        return {
            'host': os.getenv('DB_SOURCE_HOST'),
            'user': os.getenv('DB_SOURCE_USER'),
            'password': os.getenv('DB_SOURCE_PASSWORD'),
            'database': os.getenv('DB_SOURCE_NAME'),
            'charset': 'utf8mb4',
            'cursorclass': pymysql.cursors.DictCursor
        }

    @staticmethod
    def get_hmac_key():
        load_dotenv(ENV_PATH)
        return os.getenv('NAVER_HMAC_KEY', '').encode('utf-8')

    @staticmethod
    def get_api_port():
        load_dotenv(ENV_PATH)
        return int(os.getenv('API_PORT', 8000))
