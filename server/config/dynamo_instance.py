from typing import Optional
import boto3
import os

class DynamoDBConnection:
    _instance: Optional['DynamoDBConnection'] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DynamoDBConnection, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        # Establish a reusable DynamoDB resource connection (not table-specific)
        self._dynamodb = boto3.resource(
            'dynamodb',
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            region_name=os.getenv('AWS_REGION', 'us-east-1')
        )

    def get_table(self, table_name: Optional[str] = None):
        """
        Returns a table resource for the specified table name.
        If no table name is provided, falls back to default env table.
        """
        if not table_name:
            table_name = os.getenv('DYNAMODB_TABLE_NAME', 'UserChat')
        return self._dynamodb.Table(table_name)

    @classmethod
    def get_instance(cls) -> 'DynamoDBConnection':
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance