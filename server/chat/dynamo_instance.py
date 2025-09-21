from typing import Optional
import boto3
import os

class DynamoDBConnection:
    _instance: Optional['DynamoDBConnection'] = None
    _table = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DynamoDBConnection, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        if self._table is None:
            dynamodb = boto3.resource(
                'dynamodb',
                aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
                aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
                region_name=os.getenv('AWS_REGION', 'us-east-1')
            )
            self._table = dynamodb.Table(os.getenv('DYNAMODB_TABLE_NAME', 'UserChat'))

    @property
    def table(self):
        return self._table

    @classmethod
    def get_instance(cls) -> 'DynamoDBConnection':
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance